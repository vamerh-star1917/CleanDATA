#!/usr/bin/env python3
"""Chạy Gemini trên các tập Test rồi đánh giá bằng evaluate.py (một nguồn duy nhất cho mọi chỉ số).

Các bước:
1. Gọi thử 1 lần (preflight): sai tên model, sai key hoặc hết hạn mức sẽ báo ngay, không đốt hàng nghìn lần thử lại.
2. Chạy Prompt v3 trên Test chính (r1, r2 đo nhất quán), Test không dấu, Test lệch. Cache SQLite chống tính phí lặp.
3. Gọi evaluate.py: tạo metrics.csv, ma trận nhầm lẫn PNG và errors_*.csv cho TỪNG hệ thống (hai baseline + Gemini).
4. Bước kế tiếp (thủ công): make_error_sheets.py -> hai người chấm độc lập -> summarize_errors.py.

Cách dùng:
  python chay_gemini_va_danh_gia.py --api-key YOUR_GEMINI_API_KEY [--model TEN_MODEL]
  (hoặc đặt biến môi trường GEMINI_API_KEY, GEMINI_MODEL)
Tên model KHÔNG bị script tự đổi: hãy đối chiếu với tài liệu hiện hành của Google trước khi chạy.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if (HERE.parent / "01_data").exists() else HERE
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
            
    if not rows:
        print(f"[Canh bao] {split}: khong co dong nao de ghi.")
        return rows
    from collections import Counter
    print("Thong ke status:", dict(Counter(x["status"] for x in rows)))
    if len(rows) < len(inputs):
        print(f"[Canh bao] Moi chay {len(rows)}/{len(inputs)} mau (dung do --max-calls). Chay lai de tiep tuc tu cache; mau thieu se bi tinh la sai.")
    tag = f"{split}__{prompt_version}__{run_id}"
    out_csv = DIR_PRED / f"pred_{tag}.csv"
    with open(out_csv, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Đã lưu kết quả -> {out_csv.name}")
    return rows

def preflight(api_key, model, prompt, schema):
    """Gọi thử 1 lần trước khi chạy hàng loạt."""
    payload = build_gemini_payload(prompt, schema, "Hàng đẹp, giao nhanh, đóng gói cẩn thận.", None)
    try:
        raw = call_gemini_api(api_key, model, payload)
    except Exception as e:
        print(f"[LOI] Goi thu that bai voi model '{model}': {e}")
        print("Kiem tra: ten model, API key, han muc. Chua chay mau nao.")
        sys.exit(2)
    _, status = parse_and_validate(raw, schema)
    if status != "ok":
        print(f"[LOI] Goi thu tra ve dinh dang khong hop le (status={status}). Chua chay mau nao.")
        sys.exit(2)
    print(f"Goi thu thanh cong (model={model}).")


def run_evaluation():
    """Chạy evaluate.py: metrics.csv + ma trận nhầm lẫn PNG + errors_*.csv cho mọi hệ thống."""
    ev = next((c for c in (HERE / "evaluate.py", ROOT / "05_scripts" / "evaluate.py") if c.exists()), None)
    if ev is None:
        print("[LOI] Khong tim thay evaluate.py. Chay tay: python evaluate.py --pred ... --human ...")
        return
    cmd = [sys.executable, str(ev),
           "--pred", str(DIR_PRED / "pred_*.csv"),
           "--human", str(ROOT / "04_labeling" / "human_labels_final.csv"),
           "--out", str(DIR_REPORTS)]
    print("\nDang danh gia:", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("[LOI] evaluate.py that bai (ma %s). Xem thong bao phia tren." % r.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY"))
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"))
    parser.add_argument("--prompt-version", default="v3", choices=["v1", "v2", "v3"], help="Phiên bản prompt (mặc định: v3)")
    parser.add_argument("--include-val", action="store_true", default=False, help="Chạy thêm Validation (mặc định tắt để tiết kiệm quota)")
    parser.add_argument("--skip-eval", action="store_true", default=False, help="Chỉ chạy dự đoán, không gọi evaluate.py")
    args = parser.parse_args()

    if not args.api_key:
        print("Vui lòng cung cấp API Key qua --api-key hoặc biến môi trường GEMINI_API_KEY.")
        sys.exit(1)

    ver = args.prompt_version
    prompt, schema = load_prompt(ver)
    print(f"=== CHAY GEMINI ({args.model}), Prompt {ver} ===")
    preflight(args.api_key, args.model, prompt, schema)

    if args.include_val:
        print("\n[Validation] 150 mau...")
        run_split(args.api_key, args.model, "validation", ver, "r1")
    else:
        print(f"\nBo qua Validation (Prompt {ver} duoc chon truoc, KHONG phai ket qua so sanh v1/v2/v3: phai khai bao dung nhu vay trong bao cao).")

    print("\n[1/4] Test chinh - lan 1 (r1)")
    run_split(args.api_key, args.model, "test_main", ver, "r1")
    print("\n[2/4] Test chinh - lan 2 (r2, do nhat quan)")
    run_split(args.api_key, args.model, "test_main", ver, "r2")
    print("\n[3/4] Test khong dau (do do ben)")
    run_split(args.api_key, args.model, "test_unaccented", ver, "r1")
    print("\n[4/4] Test lech (cham bang nhan nguoi)")
    run_split(args.api_key, args.model, "test_skew", ver, "r1")

    if not args.skip_eval:
        run_evaluation()
    print("\n=== XONG ===")
    print("Ket qua: 06_reports/metrics.csv, confusion_*.png, errors_*.csv, consistency.csv")
    print("Buoc ke tiep: python make_error_sheets.py  (tao phieu phan tich loi cho 2 nguoi cham)")


if __name__ == "__main__":
    main()
