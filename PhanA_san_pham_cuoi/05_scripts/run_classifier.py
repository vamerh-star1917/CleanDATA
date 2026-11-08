#!/usr/bin/env python3
"""Chạy phân loại Positive/Negative cho một tập, có bộ nhớ đệm kết quả và cấu hình tái lập.

Ví dụ (Gemini thật - chốt sử dụng gemini-3.8-flash thay cho 2.5; cần biến GEMINI_API_KEY):
  python run_classifier.py --split validation --prompt-version v2 --run-id r1 --max-api-calls 300 --model gemini-3.8-flash
Chạy thử pipeline không gọi API:  thêm  --mode mock   (kết quả ghi model = MOCK-HEURISTIC, KHÔNG dùng để báo cáo)

Điểm thiết kế:
- Cache khóa = hash(model, prompt_hash, văn bản, tham số sinh, run_id). Chạy lại cùng cấu hình không tốn lời gọi.
  Muốn đo độ nhất quán (A10) thì đổi --run-id (khóa khác nên gọi lại thật) hoặc dùng --no-cache.
- --max-api-calls chặn số lời gọi THẬT mỗi lần chạy để không đốt hạn mức; chạy tiếp được vì phần đã xong nằm trong cache.
- Mỗi phản hồi được kiểm tra schema; ca lỗi (JSON sai, API lỗi) được ghi status riêng, không bị bỏ im lặng.
- Hàm call_gemini() là chỗ DUY NHẤT phụ thuộc SDK: nếu SDK/tham số đổi, chỉ sửa hàm này (kiểm tra tài liệu hiện hành).
"""
import argparse, hashlib, json, os, random, re, sqlite3, sys, time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LABELS = ["positive", "negative"]


def load_prompt(version):
    p = json.load(open(ROOT / "03_prompt" / f"prompt_{version}.json", encoding="utf-8"))
    schema = json.load(open(ROOT / "03_prompt" / p["output_schema_file"], encoding="utf-8"))
    return p, schema


def load_inputs(split, reviews_path, gold_path, unacc_path):
    rv = pd.read_csv(reviews_path, dtype={"review_id": str})
    gd = pd.read_csv(gold_path, dtype={"review_id": str})
    if split == "test_unaccented":
        tu = pd.read_csv(unacc_path, dtype={"review_id": str})
        return tu.rename(columns={"review_unaccented": "text"})[["review_id", "text"]]
    ids = set(gd.loc[gd["split"] == split, "review_id"])
    assert ids, f"không có dòng nào thuộc split={split}"
    x = rv[rv["review_id"].isin(ids)].rename(columns={"review_text": "text"})
    return x[["review_id", "text"]].sort_values("review_id").reset_index(drop=True)


# ---------------- cache ----------------
def open_cache(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, response TEXT, model TEXT, prompt_version TEXT, created_at TEXT)")
    return con


def cache_key(model, prompt_hash, text, params, run_id):
    raw = json.dumps([model, prompt_hash, text, params, run_id], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------- gọi mô hình ----------------
def build_contents(prompt, text):
    contents = []
    for ex in prompt["few_shot"]:
        contents.append({"role": "user", "parts": [{"text": ex["user"]}]})
        contents.append({"role": "model", "parts": [{"text": ex["model"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt["user_template"].format(review=text)}]})
    return contents


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


def call_gemini(model, prompt, schema, text, temperature):
    """Gọi Gemini và trả về văn bản thô theo SDK `google-genai`.
    Lưu ý: Để chạy tự động không phụ thuộc thư viện ngoài, có thể dùng trực tiếp script `chay_gemini_va_danh_gia.py` (REST API)."""
    from google import genai  # noqa
    from google.genai import types  # noqa
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    clean_schema = sanitize_gemini_schema(schema)
    cfg = dict(system_instruction=prompt["system_instruction"], response_mime_type="application/json",
               response_json_schema=clean_schema)
    if temperature is not None:
        cfg["temperature"] = temperature
    resp = client.models.generate_content(model=model, contents=build_contents(prompt, text),
                                          config=types.GenerateContentConfig(**cfg))
    return resp.text


NEG_WORDS = re.compile(r"(tệ|kém|thất vọng|móp|méo|rách|vỡ|bể|hỏng|thiếu|chậm|không (có|được|tặng)|ko (có|được|tặng)|lỗi|dở|chán)", re.I)


def call_mock(text):
    """Bộ phân loại GIẢ theo từ khóa, chỉ để thử đường ống. Không phản ánh bất kỳ mô hình nào."""
    neg = bool(NEG_WORDS.search(text))
    return json.dumps({"label": "negative" if neg else "positive", "issue_type": "other" if neg else "none",
                       "reason": "mock"}, ensure_ascii=False)


def parse_and_validate(raw, schema):
    """Trả về (dict|None, status). status: ok | bad_json | bad_schema."""
    if raw is None:
        return None, "error"
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        obj = json.loads(s)
    except Exception:
        return None, "bad_json"
    if not isinstance(obj, dict):
        return None, "bad_schema"
    props = schema["properties"]
    for k in schema["required"]:
        if k not in obj:
            return None, "bad_schema"
    if obj["label"] not in props["label"]["enum"] or obj["issue_type"] not in props["issue_type"]["enum"]:
        return None, "bad_schema"
    if not isinstance(obj["reason"], str):
        return None, "bad_schema"
    return obj, "ok"


def main(a):
    prompt, schema = load_prompt(a.prompt_version)
    model = "MOCK-HEURISTIC" if a.mode == "mock" else (a.model or os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"))
    if model in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
        print(f"[Thong bao] Mo hinh '{model}' (the he 2.5/1.5) da duoc chot nang cap sang 'gemini-3.8-flash'...")
        model = "gemini-3.8-flash"
    if not model:
        sys.exit("Thiếu tên model: đặt --model hoặc biến môi trường GEMINI_MODEL (kiểm tra tên model hiện hành trong tài liệu Gemini).")
    if a.mode == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        sys.exit("Thiếu biến môi trường GEMINI_API_KEY.")
    data = load_inputs(a.split, a.reviews, a.gold, a.unaccented)
    if a.limit:
        data = data.head(a.limit)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    con = open_cache(out / "cache.sqlite")
    params = {"temperature": a.temperature}
    rng = random.Random(0)
    rows, api_calls, hits = [], 0, 0
    stopped_by_budget = False
    for _, r in data.iterrows():
        key = cache_key(model, prompt["prompt_hash"], r["text"], params, "" if a.no_cache_key else a.run_id)
        row = None if a.no_cache else con.execute("SELECT response FROM cache WHERE key=?", (key,)).fetchone()
        raw, from_cache, lat, status_override = None, False, 0.0, None
        if row is not None:
            raw, from_cache = row[0], True
            hits += 1
        else:
            if a.mode == "gemini" and api_calls >= a.max_api_calls:
                stopped_by_budget = True
                break
            t0 = time.time()
            for attempt in range(a.max_retries + 1):
                try:
                    raw = call_mock(r["text"]) if a.mode == "mock" else call_gemini(model, prompt, schema, r["text"], a.temperature)
                    break
                except Exception as e:  # 429, 5xx, mạng...
                    status_override = "error"
                    if attempt == a.max_retries:
                        print(f"[lỗi] {r['review_id']}: {str(e)[:120]}", file=sys.stderr)
                        raw = None
                        break
                    time.sleep(min(60, (2 ** attempt) * 2) + rng.random())
            lat = time.time() - t0
            api_calls += 1 if a.mode == "gemini" else 0
            if raw is not None:
                status_override = None
                con.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?)",
                            (key, raw, model, a.prompt_version, datetime.now(timezone.utc).isoformat()))
                con.commit()
            if a.sleep_sec:
                time.sleep(a.sleep_sec)
        obj, status = parse_and_validate(raw, schema)
        if status_override:
            status = status_override
        rows.append({"review_id": r["review_id"], "split": a.split, "model": model, "prompt_version": a.prompt_version,
                     "run_id": a.run_id, "label_pred": obj["label"] if obj else "", "issue_type": obj["issue_type"] if obj else "",
                     "reason": obj["reason"] if obj else "", "status": status,
                     "issue_consistent": (obj is not None) and ((obj["label"] == "positive") == (obj["issue_type"] == "none")),
                     "from_cache": from_cache, "latency_s": round(lat, 3), "raw_response": raw if status != "ok" else ""})
    pred = pd.DataFrame(rows)
    tag = ("MOCK_" if a.mode == "mock" else "") + f"{a.split}__{a.prompt_version}__{a.run_id}"
    pred.to_csv(out / f"pred_{tag}.csv", index=False, encoding="utf-8")
    cfg = {"run_date_utc": datetime.now(timezone.utc).isoformat(), "mode": a.mode, "model": model,
           "prompt_version": a.prompt_version, "prompt_hash": prompt["prompt_hash"], "split": a.split, "run_id": a.run_id,
           "params": params, "n_requested": int(len(data)), "n_done": int(len(pred)), "api_calls": api_calls, "cache_hits": hits,
           "status_counts": pred["status"].value_counts().to_dict() if len(pred) else {},
           "stopped_by_max_api_calls": stopped_by_budget, "max_api_calls": a.max_api_calls,
           "note": "KẾT QUẢ MOCK - không dùng để báo cáo" if a.mode == "mock" else ""}
    (out / f"config_{tag}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    if stopped_by_budget:
        print("Đã dừng vì chạm --max-api-calls. Chạy lại lệnh này để tiếp tục (phần đã xong lấy từ cache).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=["validation", "test_main", "test_skew", "test_unaccented", "few_shot_pool"])
    ap.add_argument("--prompt-version", dest="prompt_version", required=True, choices=["v1", "v2", "v3"])
    ap.add_argument("--run-id", dest="run_id", default="r1")
    ap.add_argument("--mode", choices=["gemini", "mock"], default="gemini")
    ap.add_argument("--model", default=None)
    ap.add_argument("--temperature", type=float, default=None, help="mặc định không gửi tham số này")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-api-calls", dest="max_api_calls", type=int, default=300)
    ap.add_argument("--max-retries", dest="max_retries", type=int, default=4)
    ap.add_argument("--sleep-sec", dest="sleep_sec", type=float, default=0.0, help="nghỉ giữa các lời gọi để tránh vượt RPM")
    ap.add_argument("--no-cache", dest="no_cache", action="store_true", help="bỏ qua cache khi đọc (vẫn ghi mới)")
    ap.add_argument("--run-id-ignored-in-key", dest="no_cache_key", action="store_true", help="cache dùng chung giữa các run-id")
    ap.add_argument("--reviews", default=str(ROOT / "01_data" / "reviews.csv"))
    ap.add_argument("--gold", default=str(ROOT / "01_data" / "review_gold.csv"))
    ap.add_argument("--unaccented", default=str(ROOT / "01_data" / "test_unaccented.csv"))
    ap.add_argument("--out", default=str(ROOT / "06_reports" / "predictions"))
    main(ap.parse_args())
