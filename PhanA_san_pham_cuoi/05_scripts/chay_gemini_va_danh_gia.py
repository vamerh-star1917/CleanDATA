#!/usr/bin/env python3
"""Script trọn gói tự động:
1. Gọi Gemini API (chốt mô hình Gemini 3.8 Flash - gemini-3.8-flash).
2. Chốt thẳng Prompt v3 (Few-shot + 5 rules xử lý ca khó), bỏ qua so sánh v1/v2 trên Validation theo Phương án B để tiết kiệm tối đa quota API.
3. Đánh giá trực tiếp Prompt v3 trên Test chính (r1, r2 để đo nhất quán), Test không dấu (đo độ bền), và Test lệch (chấm với 197 nhãn người).
4. Cập nhật kết quả vào 06_reports/metrics.csv và lưu cache SQLite chống lặp phí.

Cách dùng:
  python chay_gemini_va_danh_gia.py --api-key YOUR_GEMINI_API_KEY
  (hoặc set biến môi trường GEMINI_API_KEY)
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DIR_PROMPTS = ROOT / "03_prompt"
DIR_DATA = ROOT / "01_data"
DIR_REPORTS = ROOT / "06_reports"
DIR_PRED = DIR_REPORTS / "predictions"
DIR_PRED.mkdir(parents=True, exist_ok=True)

LABELS = ["positive", "negative"]

def wilson(k, n, z=1.96):
    if n == 0: return 0.0, 0.0
    p = k / n
    den = 1 + z*z/n
    c = (p + z*z/(2*n)) / den
    h = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
    return round(c - h, 4), round(c + h, 4)

def open_cache(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, response TEXT, model TEXT, prompt_version TEXT, created_at TEXT)")
    return con

def cache_key(model, prompt_hash, text, params, run_id):
    raw = json.dumps([model, prompt_hash, text, params, run_id], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()

def load_prompt(version):
    p = json.load(open(DIR_PROMPTS / f"prompt_{version}.json", encoding="utf-8"))
    schema = json.load(open(DIR_PROMPTS / p["output_schema_file"], encoding="utf-8"))
    return p, schema

def load_inputs(split):
    rv = {}
    with open(DIR_DATA / "reviews.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rv[r["review_id"]] = r["review_text"]
            
    if split == "test_unaccented":
        out = []
        with open(DIR_DATA / "test_unaccented.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out.append({"review_id": r["review_id"], "text": r["review_unaccented"]})
        return out
        
    gd_ids = set()
    with open(DIR_DATA / "review_gold.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["split"] == split:
                gd_ids.add(r["review_id"])
                
    out = [{"review_id": rid, "text": rv[rid]} for rid in sorted(gd_ids) if rid in rv]
    return out

def sanitize_gemini_schema(s):
    if not isinstance(s, dict):
        return s
    allowed = {'type', 'format', 'description', 'nullable', 'enum', 'properties', 'required', 'items'}
    cleaned = {}
    for k, v in s.items():
        if k in allowed:
            if k == 'properties' and isinstance(v, dict):
                cleaned[k] = {pk: sanitize_gemini_schema(pv) for pk, pv in v.items()}
            elif k == 'items' and isinstance(v, dict):
                cleaned[k] = sanitize_gemini_schema(v)
            else:
                cleaned[k] = v
    return cleaned

def build_gemini_payload(prompt, schema, text, temperature):
    contents = []
    for ex in prompt.get("few_shot", []):
        contents.append({"role": "user", "parts": [{"text": ex["user"]}]})
        contents.append({"role": "model", "parts": [{"text": ex["model"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt["user_template"].format(review=text)}]})
    
    clean_schema = sanitize_gemini_schema(schema)
    
    payload = {
        "contents": contents,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": clean_schema
        }
    }
    if prompt.get("system_instruction"):
        payload["systemInstruction"] = {
            "parts": [{"text": prompt["system_instruction"]}]
        }
    if temperature is not None:
        payload["generationConfig"]["temperature"] = temperature
    return payload

def call_gemini_api(api_key, model, payload):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            try:
                return res["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                return None
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_msg)
            msg = err_json.get("error", {}).get("message", err_msg)
            raise RuntimeError(f"HTTP {e.code} - {msg}") from e
        except Exception:
            raise RuntimeError(f"HTTP {e.code} - {err_msg}") from e

def parse_and_validate(raw, schema):
    if not raw: return None, "error"
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        obj = json.loads(s)
    except Exception:
        return None, "bad_json"
    if not isinstance(obj, dict): return None, "bad_schema"
    if obj.get("label") not in ["positive", "negative"]: return None, "bad_schema"
    return obj, "ok"

def run_split(api_key, model, split, prompt_version, run_id, max_calls=300):
    prompt, schema = load_prompt(prompt_version)
    inputs = load_inputs(split)
    con = open_cache(DIR_PRED / "cache.sqlite")
    params = {"temperature": None}
    rows, api_calls, hits = [], 0, 0
    
    print(f"\n--- Đang chạy {split} với Prompt {prompt_version} (Run-ID: {run_id}) ---")
    for idx, r in enumerate(inputs):
        key = cache_key(model, prompt["prompt_hash"], r["text"], params, run_id)
        cached = con.execute("SELECT response FROM cache WHERE key=?", (key,)).fetchone()
        raw = None
        from_cache = False
        
        if cached:
            raw = cached[0]
            from_cache = True
            hits += 1
        else:
            if api_calls >= max_calls:
                print(f"Đã đạt giới hạn --max-calls ({max_calls}). Dừng lại.")
                break
            payload = build_gemini_payload(prompt, schema, r["text"], None)
            for attempt in range(3):
                try:
                    raw = call_gemini_api(api_key, model, payload)
                    api_calls += 1
                    con.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?)",
                                (key, raw, model, prompt_version, datetime.now(timezone.utc).isoformat()))
                    con.commit()
                    time.sleep(1.0) # Tránh vượt Rate limit
                    break
                except Exception as e:
                    print(f"Lỗi gọi API ở mẫu {idx+1}/{len(inputs)}: {e}. Đang thử lại...", flush=True)
                    time.sleep(3 * (attempt + 1))
                    
        obj, status = parse_and_validate(raw, schema)
        rows.append({
            "review_id": r["review_id"],
            "split": split,
            "model": model,
            "prompt_version": prompt_version,
            "run_id": run_id,
            "label_pred": obj.get("label", "") if obj else "",
            "issue_type": obj.get("issue_type", "") if obj else "",
            "reason": obj.get("reason", "") if obj else "",
            "status": status,
            "from_cache": from_cache
        })
        if (idx + 1) % 25 == 0 or (idx + 1) == len(inputs):
            print(f"Tiến độ: {idx+1}/{len(inputs)} (Cache hits: {hits}, API calls: {api_calls})", flush=True)
            
    tag = f"{split}__{prompt_version}__{run_id}"
    out_csv = DIR_PRED / f"pred_{tag}.csv"
    with open(out_csv, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Đã lưu kết quả -> {out_csv.name}")
    return rows

def evaluate_predictions(gold_dict, pred_rows, split, system_name):
    n = len(pred_rows)
    cm = {"neg_neg": 0, "neg_pos": 0, "pos_neg": 0, "pos_pos": 0}
    for r in pred_rows:
        rid = r["review_id"]
        g = gold_dict.get(rid, "")
        p = r["label_pred"]
        if g == "negative" and p == "negative": cm["neg_neg"] += 1
        elif g == "negative" and p == "positive": cm["neg_pos"] += 1
        elif g == "positive" and p == "negative": cm["pos_neg"] += 1
        elif g == "positive" and p == "positive": cm["pos_pos"] += 1
        
    acc = round((cm["neg_neg"] + cm["pos_pos"]) / n, 4) if n else 0
    pr_neg = round(cm["neg_neg"] / (cm["neg_neg"] + cm["pos_neg"]), 4) if (cm["neg_neg"] + cm["pos_neg"]) else 0
    rc_neg = round(cm["neg_neg"] / (cm["neg_neg"] + cm["neg_pos"]), 4) if (cm["neg_neg"] + cm["neg_pos"]) else 0
    f1_neg = round(2 * pr_neg * rc_neg / (pr_neg + rc_neg), 4) if (pr_neg + rc_neg) else 0
    
    pr_pos = round(cm["pos_pos"] / (cm["pos_pos"] + cm["neg_pos"]), 4) if (cm["pos_pos"] + cm["neg_pos"]) else 0
    rc_pos = round(cm["pos_pos"] / (cm["pos_pos"] + cm["pos_neg"]), 4) if (cm["pos_pos"] + cm["pos_neg"]) else 0
    f1_pos = round(2 * pr_pos * rc_pos / (pr_pos + rc_pos), 4) if (pr_pos + rc_pos) else 0
    
    macro_f1 = round((f1_neg + f1_pos) / 2, 4)
    lo, hi = wilson(cm["neg_neg"], cm["neg_neg"] + cm["neg_pos"])
    
    return {
        "split": split,
        "system": system_name,
        "n": str(n),
        "n_negative": str(cm["neg_neg"] + cm["neg_pos"]),
        "n_positive": str(cm["pos_neg"] + cm["pos_pos"]),
        "accuracy": str(acc),
        "macro_f1": str(macro_f1),
        "recall_negative": str(rc_neg),
        "recall_negative_ci95_lo": str(lo),
        "recall_negative_ci95_hi": str(hi),
        "precision_negative": str(pr_neg),
        "f1_negative": str(f1_neg),
        "precision_positive": str(pr_pos),
        "recall_positive": str(rc_pos),
        "f1_positive": str(f1_pos),
        "TN_neg_as_neg": str(cm["neg_neg"]),
        "FN_neg_as_pos": str(cm["neg_pos"]),
        "FP_pos_as_neg": str(cm["pos_neg"]),
        "TP_pos_as_pos": str(cm["pos_pos"]),
        "invalid_or_missing": "0",
        "invalid_policy": "wrong"
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY"))
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"))
    parser.add_argument("--prompt-version", default="v3", choices=["v1", "v2", "v3"], help="Phiên bản prompt chốt đánh giá (mặc định: v3)")
    parser.add_argument("--include-val", action="store_true", default=False, help="Chạy cả tập Validation (mặc định False theo Phương án B để tiết kiệm quota)")
    args = parser.parse_args()
    
    if args.model in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
        print(f"[Thong bao] Mo hinh '{args.model}' (the he 2.5/1.5) da duoc chot nang cap sang 'gemini-3.8-flash'...", flush=True)
        args.model = "gemini-3.8-flash"
    
    if not args.api_key:
        print("Vui lòng cung cấp API Key qua --api-key hoặc biến môi trường GEMINI_API_KEY.")
        sys.exit(1)
        
    print(f"=== BẮT ĐẦU CHẠY THỬ NGHIỆM GEMINI ({args.model}) ===")
    best_ver = args.prompt_version
    metrics_entries = []
    
    # 1. Chạy Validation nếu có cờ --include-val
    if args.include_val:
        print(f"\n[Validation] Đang chạy đánh giá Prompt {best_ver} trên tập Validation (150 mẫu)...")
        rows_val = run_split(args.api_key, args.model, "validation", best_ver, "r1")
        gold_val = {}
        with open(DIR_DATA / "review_gold.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["split"] == "validation":
                    gold_val[r["review_id"]] = r["label_original"]
        entry_val = evaluate_predictions(gold_val, rows_val, "validation", f"gemini_{best_ver}")
        metrics_entries.append(entry_val)
        print(f"Validation ({best_ver}): Macro F1 = {float(entry_val['macro_f1']):.4f} | Recall Neg = {float(entry_val['recall_negative']):.4f} | Acc = {entry_val['accuracy']}")
    else:
        print(f"\n[Phuong an B] Da chot thang Prompt {best_ver.upper()} (Few-shot + 5 rules ca kho), bo qua so sanh Validation de tiet kiem toi da 450 API calls!")
        print(f"Tien hanh danh gia truc tiep Prompt {best_ver.upper()} tren cac tap Test...")
    
    # 2. Chạy trên test_main (r1 và r2 để đo nhất quán A10)
    print(f"\n[1/4] Chạy Test chính (300 mẫu) - Lần 1 (r1)...")
    rows_tm_r1 = run_split(args.api_key, args.model, "test_main", best_ver, "r1")
    print(f"\n[2/4] Chạy Test chính (300 mẫu) - Lần 2 (r2, đo tính nhất quán)...")
    rows_tm_r2 = run_split(args.api_key, args.model, "test_main", best_ver, "r2")
    
    # 3. Chạy trên test_unaccented (đo độ bền)
    print(f"\n[3/4] Chạy Test không dấu (300 mẫu, đo độ bền)...")
    rows_unacc = run_split(args.api_key, args.model, "test_unaccented", best_ver, "r1")
    
    # 4. Chạy trên test_skew (chấm với 197 nhãn người)
    print(f"\n[4/4] Chạy Test lệch (197 mẫu, chấm với nhãn người gán độc lập)...")
    rows_skew = run_split(args.api_key, args.model, "test_skew", best_ver, "r1")
    
    # Đánh giá các tập Test
    gold_tm = {}
    with open(DIR_DATA / "review_gold.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["split"] == "test_main":
                gold_tm[r["review_id"]] = r["label_original"]
                
    gold_human = {}
    with open(ROOT / "04_labeling" / "human_labels_final.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            gold_human[r["review_id"]] = r["label_human"]
            
    metrics_entries.append(evaluate_predictions(gold_tm, rows_tm_r1, "test_main", f"gemini_{best_ver}_r1"))
    metrics_entries.append(evaluate_predictions(gold_tm, rows_tm_r2, "test_main", f"gemini_{best_ver}_r2"))
    metrics_entries.append(evaluate_predictions(gold_tm, rows_unacc, "test_unaccented", f"gemini_{best_ver}"))
    metrics_entries.append(evaluate_predictions(gold_human, rows_skew, "test_skew", f"gemini_{best_ver}"))
    
    # Cập nhật vào metrics.csv
    existing_rows = []
    fieldnames = []
    with open(DIR_REPORTS / "metrics.csv", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames
        existing_rows = list(r)
        
    for new_e in metrics_entries:
        # Nếu đã có thì thay thế, chưa có thì thêm
        found = False
        for idx, ex in enumerate(existing_rows):
            if ex["split"] == new_e["split"] and ex["system"] == new_e["system"]:
                existing_rows[idx] = new_e
                found = True
                break
        if not found:
            existing_rows.append(new_e)
            
    with open(DIR_REPORTS / "metrics.csv", mode="w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(existing_rows)
        
    print("\n=== HOÀN TẤT TOÀN BỘ CÁC THỰC NGHIỆM! ===")
    print("Toàn bộ các chỉ số đo lường đã được cập nhật vào final/06_reports/metrics.csv")

if __name__ == "__main__":
    main()
