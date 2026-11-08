#!/usr/bin/env python3
"""Tạo schema.sql và reviews_preload.sql (DDL + dữ liệu) để nạp vào PostgreSQL.
Chạy: python build_preload_sql.py --out ../01_data/preload
Nạp: psql -d <db> -f schema.sql  rồi  psql -d <db> -f reviews_preload.sql   (hoặc chỉ file preload vì đã gồm DDL)
Chuỗi được trích dẫn theo chuẩn SQL (nhân đôi dấu nháy đơn); ổn với standard_conforming_strings=on (mặc định của PostgreSQL).
"""
import argparse, json, math
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

DDL = """-- Schema phần A (đề xuất; thống nhất với CH01). Các cột giả lập được ghi rõ trong data_dictionary.xlsx
CREATE TABLE IF NOT EXISTS issue_types (
  issue_type   TEXT PRIMARY KEY,
  description  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
  review_id      TEXT PRIMARY KEY,                 -- id gốc Kaggle (khóa idempotent cho WF1)
  review_text    TEXT NOT NULL,                    -- GỐC
  rating         SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),   -- GỐC
  customer_id    TEXT NOT NULL,                    -- GIẢ LẬP
  customer_tier  TEXT NOT NULL CHECK (customer_tier IN ('VIP','Regular')),  -- GIẢ LẬP (20% VIP)
  product_id     TEXT NOT NULL,                    -- GIẢ LẬP
  lot_id         TEXT NOT NULL,                    -- GIẢ LẬP
  created_at     TIMESTAMPTZ NOT NULL              -- GIẢ LẬP
);

-- Nhãn và thông tin chia tập tách riêng để workflow không vô tình đọc nhãn gốc
CREATE TABLE IF NOT EXISTS review_gold (
  review_id          TEXT PRIMARY KEY REFERENCES reviews(review_id),
  label_original     TEXT NOT NULL CHECK (label_original IN ('positive','negative')),  -- GỐC (suy ra từ số sao, chưa kiểm chứng)
  rating_label_flag  TEXT NOT NULL,
  split              TEXT NOT NULL CHECK (split IN ('few_shot_pool','validation','test_main','test_skew','reserve')),
  skew_group         TEXT,
  dup_group          INTEGER NOT NULL,
  label_human        TEXT CHECK (label_human IN ('positive','negative'))   -- điền sau khi gán nhãn Test lệch
);

CREATE TABLE IF NOT EXISTS scenario_reviews (
  scenario_review_id TEXT PRIMARY KEY,
  scenario_set       TEXT NOT NULL CHECK (scenario_set IN ('tune','eval')),
  scenario_id        TEXT NOT NULL,
  source_review_id   TEXT NOT NULL,
  review_text        TEXT NOT NULL,
  rating             SMALLINT NOT NULL,
  label              TEXT NOT NULL,
  issue_type         TEXT NOT NULL REFERENCES issue_types(issue_type),
  issue_type_source  TEXT NOT NULL,                -- rule_packaging | rule | none_positive (KHÔNG phải nhãn người)
  lot_id             TEXT NOT NULL,
  product_id         TEXT NOT NULL,
  customer_id        TEXT NOT NULL,
  customer_tier      TEXT NOT NULL,
  window_start       TIMESTAMPTZ NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS scenario_checkpoints (
  checkpoint_id        TEXT PRIMARY KEY,
  scenario_set         TEXT NOT NULL,
  scenario_id          TEXT NOT NULL,
  description          TEXT NOT NULL,
  sim_now              TIMESTAMPTZ NOT NULL,
  window_start         TIMESTAMPTZ NOT NULL,
  window_hours         INTEGER NOT NULL,
  focus_lot_id         TEXT NOT NULL,
  focus_issue_type     TEXT NOT NULL,
  max_cluster_size     INTEGER NOT NULL,
  reference_threshold  INTEGER NOT NULL,
  expected_alert       BOOLEAN NOT NULL,
  rerun_of             TEXT
);
"""


def q(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "NULL"
    if isinstance(v, (bool,)):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int,)) or (hasattr(v, "dtype") and "int" in str(v.dtype)):
        return str(int(v))
    if hasattr(v, "dtype") and "bool" in str(v.dtype):
        return "TRUE" if bool(v) else "FALSE"
    s = str(v).replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return "'" + s.replace("'", "''") + "'"


def inserts(table, df, cols, batch=200):
    out = []
    for i in range(0, len(df), batch):
        chunk = df.iloc[i:i + batch]
        vals = ",\n".join("(" + ", ".join(q(r[c]) for c in cols) + ")" for _, r in chunk.iterrows())
        out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{vals};")
    return "\n".join(out)


def main(a):
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rv = pd.read_csv(a.reviews, dtype={"review_id": str})
    gd = pd.read_csv(a.gold, dtype={"review_id": str})
    gd["skew_group"] = gd["skew_group"].where(gd["skew_group"].notna() & (gd["skew_group"] != ""), None)
    gd["label_human"] = None
    sr = pd.read_csv(a.scen_reviews, dtype={"source_review_id": str})
    sc = pd.read_csv(a.scen_cp)
    sc["rerun_of"] = sc["rerun_of"].where(sc["rerun_of"].notna(), None)
    cat = json.load(open(a.catalog, encoding="utf-8"))["issue_types"]
    it = pd.DataFrame({"issue_type": list(cat), "description": list(cat.values())})
    (out / "schema.sql").write_text(DDL, encoding="utf-8")
    parts = ["-- Dữ liệu nạp sẵn phần A. Mã hóa UTF-8.", "-- Với psql: \\encoding UTF8", "BEGIN;", DDL,
             inserts("issue_types", it, ["issue_type", "description"]),
             inserts("reviews", rv, ["review_id", "review_text", "rating", "customer_id", "customer_tier", "product_id", "lot_id", "created_at"]),
             inserts("review_gold", gd, ["review_id", "label_original", "rating_label_flag", "split", "skew_group", "dup_group", "label_human"]),
             inserts("scenario_reviews", sr, ["scenario_review_id", "scenario_set", "scenario_id", "source_review_id", "review_text", "rating", "label",
                                              "issue_type", "issue_type_source", "lot_id", "product_id", "customer_id", "customer_tier", "window_start", "created_at"]),
             inserts("scenario_checkpoints", sc, ["checkpoint_id", "scenario_set", "scenario_id", "description", "sim_now", "window_start", "window_hours",
                                                  "focus_lot_id", "focus_issue_type", "max_cluster_size", "reference_threshold", "expected_alert", "rerun_of"]),
             "COMMIT;"]
    (out / "reviews_preload.sql").write_text("\n".join(parts) + "\n", encoding="utf-8")
    print({"reviews": len(rv), "review_gold": len(gd), "scenario_reviews": len(sr), "scenario_checkpoints": len(sc), "issue_types": len(it)})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviews", default=str(ROOT / "01_data" / "reviews.csv"))
    ap.add_argument("--gold", default=str(ROOT / "01_data" / "review_gold.csv"))
    ap.add_argument("--scen-reviews", dest="scen_reviews", default=str(ROOT / "02_scenarios" / "scenario_reviews.csv"))
    ap.add_argument("--scen-cp", dest="scen_cp", default=str(ROOT / "02_scenarios" / "scenario_checkpoints.csv"))
    ap.add_argument("--catalog", default=str(ROOT / "03_prompt" / "issue_type_catalog.json"))
    ap.add_argument("--out", default=str(ROOT / "01_data" / "preload"))
    main(ap.parse_args())
