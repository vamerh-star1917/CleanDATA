#!/usr/bin/env python3
"""Tạo phiếu phân tích lỗi cho HAI người chấm từ các file errors_*.csv của Gemini.

Nguyên tắc (thay thế việc gán nhóm lỗi bằng từ khóa):
- Chỉ lấy lỗi của hệ thống Gemini (bỏ file baseline), mặc định chỉ lần chạy r1 để không đếm trùng.
- Hai người chấm cùng đọc TOÀN BỘ ca lỗi, độc lập, theo 07_error_analysis/huong_dan_phan_tich_loi.md.
- Ca lỗi kỹ thuật (status != ok) tự gán nhóm 'ky_thuat', không đưa vào phiếu.
- Với Test không dấu, phiếu hiển thị đúng văn bản không dấu mà mô hình đã nhận.

Cách dùng (sau khi đã chạy Gemini và evaluate.py):
  python make_error_sheets.py
  python make_error_sheets.py --runs r1 r2 --splits test_main test_skew
"""
import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FNAME = re.compile(r"errors_(?P<split>.+?)__(?P<system>.+)\.csv$")


def main(a):
    rep = Path(a.reports)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    gold = pd.read_csv(a.gold, dtype={"review_id": str})
    keep = [c for c in ["review_id", "label_original", "skew_group"] if c in gold.columns]
    gold = gold[keep]
    unacc = pd.read_csv(a.unaccented, dtype={"review_id": str})[["review_id", "review_unaccented"]]

    frames = []
    for f in sorted(rep.glob("errors_*.csv")):
        m = FNAME.match(f.name)
        if not m:
            continue
        split, system = m["split"], m["system"]
        if system.startswith("baseline") or system.startswith("MOCK"):
            continue
        run = re.search(r"_(r\d+)$", system)
        if not run or run.group(1) not in a.runs or split not in a.splits:
            continue
        d = pd.read_csv(f, dtype={"review_id": str}).fillna({"status": "", "reason": "", "issue_type": ""})
        d["split"], d["system"] = split, system
        frames.append(d)
    if not frames:
        raise SystemExit("Không thấy errors_*.csv của Gemini. Hãy chạy chay_gemini_va_danh_gia.py (hoặc evaluate.py --pred ...) trước.")

    e = pd.concat(frames, ignore_index=True).merge(gold, on="review_id", how="left")
    e = e.merge(unacc, on="review_id", how="left")
    e["review_text_goc"] = e["review_text"]
    mask = e["split"] == "test_unaccented"
    e.loc[mask, "review_text"] = e.loc[mask, "review_unaccented"].fillna(e.loc[mask, "review_text"])

    tech = e[e["status"] != "ok"].copy()
    ok = e[e["status"] == "ok"].copy()
    ok["error_type"] = ok.apply(lambda r: "FN" if r["gold"] == "negative" else "FP", axis=1)  # FN: bỏ sót negative
    tech["error_type"] = "KT"
    tech["error_category"] = "ky_thuat"
    tech[["split", "review_id", "error_type", "status", "error_category"]].to_csv(out / "ky_thuat_auto.csv", index=False, encoding="utf-8")

    ok = ok.rename(columns={"pred_used": "model_pred", "reason": "model_reason"})
    cols = ["split", "review_id", "error_type", "review_text", "rating", "label_original", "gold",
            "model_pred", "model_reason", "skew_group", "review_text_goc"]
    ok = ok[[c for c in cols if c in ok.columns]].reset_index(drop=True)
    ok.to_csv(out / "errors_master.csv", index=False, encoding="utf-8")

    for k, seed in ((1, a.seed), (2, a.seed + 1)):  # thứ tự trộn khác nhau để tránh hiệu ứng neo
        s = ok.sample(frac=1, random_state=seed).reset_index(drop=True)
        s.insert(0, "stt", range(1, len(s) + 1))
        s["error_category"] = ""
        s["unsure"] = ""
        s["note"] = ""
        s.drop(columns=["review_text_goc"], errors="ignore").to_csv(out / f"phieu_loi_coder{k}.csv", index=False, encoding="utf-8-sig")

    print(f"Số ca lỗi cần chấm: {len(ok)} (lỗi kỹ thuật tự gán: {len(tech)})")
    print(ok.groupby(["split", "error_type"]).size().to_string())
    print(f"Đã ghi 2 phiếu vào {out}. Phát mỗi người MỘT file; không trao đổi trước khi nộp.")
    if len(ok) > 150:
        print("Lưu ý: hơn 150 ca; cân nhắc --splits để giới hạn hoặc chia nhỏ thời gian chấm.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default=str(ROOT / "06_reports"))
    ap.add_argument("--gold", default=str(ROOT / "01_data" / "review_gold.csv"))
    ap.add_argument("--unaccented", default=str(ROOT / "01_data" / "test_unaccented.csv"))
    ap.add_argument("--out", default=str(ROOT / "07_error_analysis"))
    ap.add_argument("--runs", nargs="+", default=["r1"])
    ap.add_argument("--splits", nargs="+", default=["test_main", "test_skew", "test_unaccented"])
    ap.add_argument("--seed", type=int, default=42)
    main(ap.parse_args())
