#!/usr/bin/env python3
"""Tổng hợp phân tích lỗi từ hai phiếu đã chấm độc lập.

Bước 1 (chưa --finalize): kiểm tra phiếu, tính tỷ lệ đồng thuận + Cohen's kappa theo nhóm lỗi,
  xuất to_reconcile_errors.csv (các ca hai người chấm khác nhau hoặc có đánh dấu unsure).
Bước 2 (--finalize): sau khi nhóm điền cột final_category + reconcile_note trong to_reconcile_errors.csv,
  xuất errors_final.csv, bảng tổng hợp (CSV + Markdown) và danh sách ví dụ gợi ý.

Cách dùng:
  python summarize_errors.py
  python summarize_errors.py --finalize
"""
import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CATS = ["nhan_goc_nhieu", "mia_mai", "khen_che_lan_lon", "tieng_long_viet_tat", "mo_ho", "khac_loi_mo_hinh"]
CAT_VI = {
    "nhan_goc_nhieu": "Nhãn gốc nhiễu (mô hình hợp lý hơn nhãn)",
    "mia_mai": "Mỉa mai",
    "khen_che_lan_lon": "Khen chê lẫn lộn",
    "tieng_long_viet_tat": "Tiếng lóng / viết tắt / không dấu / lỗi gõ",
    "mo_ho": "Mơ hồ, ranh giới",
    "khac_loi_mo_hinh": "Lỗi mô hình khác",
    "ky_thuat": "Lỗi kỹ thuật (API/JSON)",
}
KEY = ["split", "review_id"]


def cohen_kappa(x, y):
    n = len(x)
    if n == 0:
        return float("nan")
    po = sum(a == b for a, b in zip(x, y)) / n
    cx, cy = Counter(x), Counter(y)
    pe = sum((cx[c] / n) * (cy[c] / n) for c in set(cx) | set(cy))
    return 1.0 if pe >= 1 else (po - pe) / (1 - pe)


def load_sheet(path, who):
    d = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    d["error_category"] = d["error_category"].astype(str).str.strip()
    blank = d[d["error_category"] == ""]
    bad = d[(d["error_category"] != "") & (~d["error_category"].isin(CATS))]
    if len(blank):
        raise SystemExit(f"{who}: còn {len(blank)} ca chưa điền error_category (vd stt {blank['stt'].head(5).tolist()}).")
    if len(bad):
        raise SystemExit(f"{who}: giá trị không hợp lệ {sorted(bad['error_category'].unique())}. Chỉ dùng: {CATS}")
    return d


def main(a):
    od = Path(a.dir)
    s1 = load_sheet(od / "phieu_loi_coder1.csv", "coder1")
    s2 = load_sheet(od / "phieu_loi_coder2.csv", "coder2")
    m = s1[KEY + ["error_type", "review_text", "rating", "label_original", "gold", "model_pred", "model_reason", "error_category", "unsure", "note"]].merge(
        s2[KEY + ["error_category", "unsure", "note"]], on=KEY, suffixes=("_1", "_2"), validate="one_to_one")
    if len(m) != len(s1) or len(m) != len(s2):
        raise SystemExit("Hai phiếu không cùng tập ca lỗi. Tạo lại bằng make_error_sheets.py rồi chấm lại.")

    agree = (m["error_category_1"] == m["error_category_2"]).mean()
    kappa = cohen_kappa(m["error_category_1"].tolist(), m["error_category_2"].tolist())
    print(f"Số ca: {len(m)} | đồng thuận thô: {agree:.3f} | Cohen's kappa (nhóm lỗi): {kappa:.3f}")
    print("Lưu ý: kappa thấp dù đồng thuận cao có thể do phân bố nhóm lệch (ít nhóm chiếm đa số); báo cáo cả hai số.")
    print("Ma trận bất đồng (hàng = coder1, cột = coder2):")
    print(pd.crosstab(m["error_category_1"], m["error_category_2"]).to_string())

    m["can_thong_nhat"] = (m["error_category_1"] != m["error_category_2"]) | (m["unsure_1"].astype(str) != "") | (m["unsure_2"].astype(str) != "")
    rec = m[m["can_thong_nhat"]].copy()
    rec["final_category"] = ""
    rec["reconcile_note"] = ""
    rec_cols = KEY + ["error_type", "review_text", "gold", "model_pred", "error_category_1", "note_1", "error_category_2", "note_2", "final_category", "reconcile_note"]
    rec_path = od / "to_reconcile_errors.csv"

    (od / "error_kappa.json").write_text(
        pd.Series({"n": len(m), "agreement": round(float(agree), 4), "cohen_kappa": round(float(kappa), 4),
                   "n_can_thong_nhat": int(len(rec))}).to_json(), encoding="utf-8")

    if not a.finalize:
        rec[rec_cols].to_csv(rec_path, index=False, encoding="utf-8-sig")
        print(f"\n{len(rec)} ca cần thống nhất -> {rec_path.name}. Điền final_category (+ lý do), rồi chạy lại với --finalize.")
        return

    if not rec_path.exists():
        raise SystemExit("Chưa có to_reconcile_errors.csv. Chạy bước 1 trước.")
    r = pd.read_csv(rec_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    r["final_category"] = r["final_category"].astype(str).str.strip()
    bad = r[~r["final_category"].isin(CATS)]
    if len(bad):
        raise SystemExit(f"to_reconcile_errors.csv: {len(bad)} ca chưa có final_category hợp lệ.")
    fin = m.merge(r[KEY + ["final_category", "reconcile_note"]], on=KEY, how="left")
    fin["category"] = fin["final_category"].where(fin["final_category"].notna() & (fin["final_category"] != ""), fin["error_category_1"])
    fin["so_chuyen_dong_y"] = fin["error_category_1"] == fin["error_category_2"]

    tech_p = od / "ky_thuat_auto.csv"
    tech = pd.read_csv(tech_p, dtype={"review_id": str}) if tech_p.exists() else pd.DataFrame(columns=KEY + ["error_type", "error_category"])
    allf = pd.concat([fin[KEY + ["error_type", "category"]],
                      tech.rename(columns={"error_category": "category"})[KEY + ["error_type", "category"]]], ignore_index=True)
    fin.to_csv(od / "errors_final.csv", index=False, encoding="utf-8-sig")

    allf["Nhóm lỗi"] = allf["category"].map(CAT_VI)
    t_split = pd.crosstab(allf["Nhóm lỗi"], allf["split"], margins=True, margins_name="Tổng")
    t_type = pd.crosstab(allf["Nhóm lỗi"], allf["error_type"], margins=True, margins_name="Tổng")
    pct = (allf["Nhóm lỗi"].value_counts(normalize=True) * 100).round(1).rename("Tỷ lệ % trên tổng lỗi")
    t_split.to_csv(od / "summary_theo_tap.csv", encoding="utf-8-sig")
    t_type.to_csv(od / "summary_FN_FP.csv", encoding="utf-8-sig")

    soft = allf["category"].isin(["nhan_goc_nhieu", "mo_ho"]).mean() * 100
    fin["rating"] = pd.to_numeric(fin["rating"], errors="coerce")
    by_rating = pd.crosstab(fin["rating"], fin["category"].map(CAT_VI), margins=True, margins_name="Tổng")
    by_rating.to_csv(od / "summary_theo_so_sao.csv", encoding="utf-8-sig")
    skew = fin[fin["split"] == "test_skew"]
    diff_orig = float((skew["label_original"] != skew["gold"]).mean() * 100) if len(skew) else float("nan")

    md = ["# Tổng hợp phân tích lỗi (Gemini)", "",
          f"- Số ca lỗi: {len(allf)}; đồng thuận thô giữa hai người chấm: {agree:.3f}; Cohen's kappa: {kappa:.3f}",
          f"- Tỷ lệ lỗi có thể không phải lỗi thực của mô hình (nhãn gốc nhiễu + mơ hồ): {soft:.1f}%",
          (f"- Test lệch: {diff_orig:.1f}% ca lỗi có nhãn gốc khác nhãn người" if len(skew) else ""),
          "", "## Theo tập", "", t_split.to_markdown(), "", "## Theo loại lỗi (FN = bỏ sót negative; FP = báo nhầm negative)", "",
          t_type.to_markdown(), "", "## Tỷ lệ", "", pct.to_markdown(), "",
          "Cỡ mẫu lỗi nhỏ: các tỷ lệ chỉ mang tính mô tả, không dùng để so sánh thống kê giữa các tập."]
    (od / "summary_loi.md").write_text("\n".join(md), encoding="utf-8")

    ex = fin.assign(len_text=fin["review_text"].astype(str).str.len())
    ex = ex.sort_values(["category", "len_text"]).groupby("category").head(3)
    ex[["category", "split", "review_id", "error_type", "review_text", "gold", "model_pred", "model_reason", "chon_vi_du"] if "chon_vi_du" in ex else
       ["category", "split", "review_id", "error_type", "review_text", "gold", "model_pred", "model_reason"]].to_csv(
        od / "vi_du_goi_y.csv", index=False, encoding="utf-8-sig")
    print(f"Đã xuất errors_final.csv, summary_loi.md, summary_*.csv, vi_du_goi_y.csv trong {od}")
    print("vi_du_goi_y.csv chỉ là GỢI Ý (ca ngắn nhất mỗi nhóm): nhóm tự chọn 1-2 ví dụ đại diện cho mỗi nhóm.")
    print(t_split.to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "07_error_analysis"))
    ap.add_argument("--finalize", action="store_true")
    main(ap.parse_args())
