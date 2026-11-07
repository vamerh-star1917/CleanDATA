#!/usr/bin/env python3
"""Tạo phiếu gán nhãn độc lập cho Test lệch (CH04/A06).
Chia Test lệch thành hai nửa; mỗi nửa do MỘT CẶP gán độc lập (4 file, mỗi người một file).
Phiếu chỉ có nội dung review: KHÔNG có rating, nhãn gốc hay kết quả Gemini.
Chạy: python make_labeling_sheets.py --out ../04_labeling
"""
import argparse
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent

def main(a):
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rv = pd.read_csv(a.reviews, dtype={"review_id": str}); gd = pd.read_csv(a.gold, dtype={"review_id": str})
    x = rv.merge(gd, on="review_id"); x = x[x["split"] == "test_skew"][["review_id", "review_text"]]
    x = x.sample(frac=1.0, random_state=a.seed).reset_index(drop=True)   # xáo để thứ tự không lộ nhóm lệch
    half = len(x) // 2
    parts = {"nua1": x.iloc[:half], "nua2": x.iloc[half:]}
    for name, df in parts.items():
        for r in (("rater1", "rater2") if name == "nua1" else ("rater3", "rater4")):
            s = df.copy(); s["label"] = ""; s["unsure"] = ""; s["note"] = ""
            s.to_csv(out / f"phieu_gan_nhan_{name}_{r}.csv", index=False, encoding="utf-8-sig")
    print({k: len(v) for k, v in parts.items()})

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviews", default=str(ROOT / "01_data" / "reviews.csv"))
    ap.add_argument("--gold", default=str(ROOT / "01_data" / "review_gold.csv"))
    ap.add_argument("--out", default=str(ROOT / "04_labeling"))
    ap.add_argument("--seed", type=int, default=42)
    main(ap.parse_args())
