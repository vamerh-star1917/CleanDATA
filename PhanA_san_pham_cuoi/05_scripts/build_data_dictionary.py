#!/usr/bin/env python3
"""Tạo data_dictionary.xlsx (A04): mọi cột kèm nguồn (Gốc / Giả lập / Suy ra / Quy tắc / Người gán), cách sinh, ràng buộc, ví dụ.
Số liệu về các tập lấy từ split_report.json và scenario_report.json (không gõ tay)."""
import argparse, json
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
FILL = {"Gốc": "E2EFDA", "Giả lập": "FCE4D6", "Suy ra": "DDEBF7", "Quy tắc": "FFF2CC", "Người gán": "EDEDED"}
THIN = Side(style="thin", color="BFBFBF")


def sheet(wb, name, headers, rows, widths, source_col=None, title=None, note=None):
    ws = wb.create_sheet(name)
    r0 = 1
    if title:
        ws.cell(1, 1, title).font = Font(name="Arial", size=12, bold=True); r0 = 2
    if note:
        ws.cell(r0, 1, note).font = Font(name="Arial", size=9, italic=True); ws.cell(r0, 1).alignment = Alignment(wrap_text=False); r0 += 1
    r0 += 1
    for j, h in enumerate(headers, 1):
        c = ws.cell(r0, j, h); c.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color="305496"); c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
    for i, row in enumerate(rows, r0 + 1):
        for j, v in enumerate(row, 1):
            c = ws.cell(i, j, v); c.font = Font(name="Arial", size=10)
            c.alignment = Alignment(wrap_text=True, vertical="top"); c.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
        if source_col is not None:
            key = str(row[source_col]).split(" ")[0] if str(row[source_col]).split(" ")[0] in FILL else str(row[source_col]).split(" (")[0]
            for k, f in FILL.items():
                if str(row[source_col]).startswith(k):
                    ws.cell(i, source_col + 1).fill = PatternFill("solid", start_color=f)
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(r0 + 1, 1)
    return ws


def main(a):
    rv = pd.read_csv(a.reviews, dtype={"review_id": str}); gd = pd.read_csv(a.gold, dtype={"review_id": str})
    sr = pd.read_csv(a.scen_reviews, dtype={"source_review_id": str}); sc = pd.read_csv(a.scen_cp)
    tu = pd.read_csv(a.unaccented, dtype={"review_id": str})
    sp = json.load(open(a.split_report, encoding="utf-8")); scr = json.load(open(a.scen_report, encoding="utf-8"))
    cat = json.load(open(a.catalog, encoding="utf-8"))["issue_types"]
    ex = lambda df, c: str(df[c].iloc[0]).replace("\n", " ")[:90]
    H = ["Cột", "Kiểu (PostgreSQL)", "Nguồn", "Mô tả / cách sinh", "Ràng buộc", "Ví dụ"]
    W = [22, 18, 13, 62, 34, 34]
    wb = Workbook(); wb.remove(wb.active)

    ws = wb.create_sheet("Hướng dẫn đọc")
    lines = [("Data dictionary - Phần A (Dữ liệu và phân loại)", True),
             ("Mỗi sheet là một bảng/tệp. Cột 'Nguồn' có 5 giá trị, tô màu để phân biệt cột gốc và cột giả lập:", False),
             ("Gốc: lấy nguyên từ bộ Shopee Vietnamese Product Reviews Sentiment (Kaggle).", False),
             ("Giả lập: do script sinh bằng hàm băm (seed + khóa); KHÔNG có quan hệ thật với nội dung review, không dùng để đánh giá mô hình.", False),
             ("Suy ra: do script tính từ cột khác (ví dụ cờ rating-label, nhóm gần trùng, tập chia).", False),
             ("Quy tắc: nhãn gán bằng quy tắc từ khóa (issue_type của dữ liệu kịch bản); là ước lượng, chưa được người kiểm chứng đầy đủ.", False),
             ("Người gán: do các thành viên nhóm gán nhãn độc lập và đối soát (label_human); đã hoàn tất 100% cho 197 mẫu Test lệch.", False),
             ("", False),
             ("Lưu ý quan trọng: label_original của Kaggle gần như suy ra từ số sao (xem báo cáo kiểm tra dữ liệu), nên KHÔNG phải ground truth tuyệt đối của cảm xúc văn bản.", False),
             (f"Seed chia tập và sinh trường giả lập: {sp['params']['seed']}. Phiên bản script chia tập: {sp['script_version']}.", False),
             ("Số liệu bên dưới đọc từ split_report.json và scenario_report.json do script tạo.", False)]
    for i, (t, b) in enumerate(lines, 1):
        c = ws.cell(i, 1, t); c.font = Font(name="Arial", size=12 if b else 10, bold=b)
    for k, f in FILL.items():
        pass
    ws.column_dimensions["A"].width = 140
    for i, (k, f) in enumerate(FILL.items(), 14):
        ws.cell(i, 1, k).fill = PatternFill("solid", start_color=f); ws.cell(i, 1).font = Font(name="Arial", size=10)

    P = sp["params"]
    reviews_rows = [
        ["review_id", "TEXT (PK)", "Gốc", "Mã đánh giá, lấy từ trường id của bộ Kaggle. Dùng làm khóa idempotent cho WF1 (không dùng mã đơn hàng).", "NOT NULL, duy nhất", ex(rv, "review_id")],
        ["review_text", "TEXT", "Gốc", "Nội dung đánh giá, nguyên văn (gồm cả các trường mẫu Shopee như 'Chất lượng sản phẩm:tốt'; có emoji, viết tắt, sai chính tả). Không chỉnh sửa.", "NOT NULL", ex(rv, "review_text")],
        ["rating", "SMALLINT", "Gốc", "Số sao 1-5.", "CHECK 1..5", ex(rv, "rating")],
        ["customer_id", "TEXT", "Giả lập", f"Mã khách giả, sinh bằng hàm băm của (seed|review_id); {P['n_customers']} mã khả dĩ, {sp['n_customers_used']} mã thực tế xuất hiện; một khách có thể có nhiều review.", "NOT NULL", ex(rv, "customer_id")],
        ["customer_tier", "TEXT", "Giả lập", f"Hạng khách VIP/Regular, sinh bằng hàm băm của customer_id (tỷ lệ VIP mục tiêu {int(P['vip_ratio']*100)}%); mỗi khách đúng một hạng.", "CHECK IN ('VIP','Regular')", ex(rv, "customer_tier")],
        ["product_id", "TEXT", "Giả lập", f"Mã sản phẩm giả ({P['n_products']} sản phẩm), không kèm tên sản phẩm để tránh lệch với nội dung review. Suy ra từ lô.", "NOT NULL", ex(rv, "product_id")],
        ["lot_id", "TEXT", "Giả lập", f"Mã lô giả ({sp['n_lots_used']} lô = {P['n_products']} sản phẩm x {P['lots_per_product']} lô); mỗi lô thuộc đúng một sản phẩm.", "NOT NULL", ex(rv, "lot_id")],
        ["created_at", "TIMESTAMPTZ", "Giả lập", f"Thời điểm giả, {P['days']} ngày từ {P['start_date']} (múi giờ +07:00), phân phối theo giờ có đỉnh trưa và tối. Không phải thời điểm review thật.", "NOT NULL", ex(rv, "created_at")]]
    sheet(wb, "reviews", H, reviews_rows, W, 2, "Bảng reviews (nạp sẵn)", f"Tệp: 01_data/reviews.csv; {len(rv)} dòng. Không chứa nhãn.")

    gold_rows = [
        ["review_id", "TEXT (PK, FK)", "Gốc", "Khóa tới reviews.review_id.", "FK", ex(gd, "review_id")],
        ["label_original", "TEXT", "Gốc", "Nhãn positive/negative của bộ Kaggle. Gần như suy ra từ số sao (<=3 sao là negative), nên chưa phải chuẩn độc lập về cảm xúc.", "CHECK IN ('positive','negative')", ex(gd, "label_original")],
        ["rating_label_flag", "TEXT", "Suy ra", "khop = nhãn khớp quy tắc (<=3 sao negative, >=4 sao positive); hi_sao_nhan_negative = 4-5 sao nhưng negative; thap_sao_nhan_positive = 1-2 sao nhưng positive; 3sao_nhan_positive = 3 sao nhưng positive. Chỉ là cờ, chưa kết luận gán sai.", "NOT NULL", ex(gd, "rating_label_flag")],
        ["split", "TEXT", "Suy ra", "Tập chia: few_shot_pool, validation, test_main, test_skew, reserve. Chia theo dup_group để bản gần trùng không bị tách tập.", "CHECK IN (...)", ex(gd, "split")],
        ["skew_group", "TEXT", "Suy ra", "Chỉ có giá trị với test_skew: nhóm lệch (như rating_label_flag) hoặc group_mate (cùng nhóm gần trùng với ca lệch).", "NULL nếu không phải test_skew", "hi_sao_nhan_negative"],
        ["dup_group", "INTEGER", "Suy ra", "Mã nhóm gần trùng: TF-IDF ký tự (3-5), cosine >= 0.90, gom thành phần liên thông. Số nguyên không có ý nghĩa khác ngoài so nhóm.", "NOT NULL", ex(gd, "dup_group")],
        ["label_human", "TEXT", "Người gán", "Nhãn do người gán theo nội dung và đã thống nhất, dùng chấm Test lệch. HIỆN TRỐNG, điền sau khi hoàn thành CH04.", "CHECK IN ('positive','negative'), NULL", "(trống)"]]
    sheet(wb, "review_gold", H, gold_rows, W, 2, "Bảng review_gold (nhãn và thông tin chia tập)", "Tệp: 01_data/review_gold.csv. Tách riêng để workflow không đọc được nhãn gốc.")

    tu_rows = [["review_id", "TEXT", "Gốc", "Khóa tới reviews; chỉ gồm id thuộc test_main.", "FK", ex(tu, "review_id")],
               ["review_unaccented", "TEXT", "Suy ra", "Bản không dấu của review_text, sinh bằng hàm unaccent trong build_splits.py (bỏ dấu tiếng Việt, đ->d, bỏ emoji). Hàm tái tạo 1.318/1.326 dòng của file aug gốc; chênh lệch chỉ ở emoji.", "NOT NULL", ex(tu, "review_unaccented")]]
    sheet(wb, "test_unaccented", H, tu_rows, W, 2, "Tệp test_unaccented.csv (kiểm tra độ bền không dấu)", f"{len(tu)} dòng; nhãn lấy từ review_gold theo review_id.")

    sr_rows = [
        ["scenario_review_id", "TEXT (PK)", "Suy ra", "Mã sự kiện kịch bản: S-T-xxxxx (bộ tune) hoặc S-E-xxxxx (bộ eval).", "duy nhất", ex(sr, "scenario_review_id")],
        ["scenario_set", "TEXT", "Suy ra", "tune = bộ chỉnh ngưỡng; eval = bộ đánh giá. Hai bộ dùng review nguồn và lô trọng tâm khác nhau.", "CHECK IN ('tune','eval')", ex(sr, "scenario_set")],
        ["scenario_id", "TEXT", "Suy ra", "Mã kịch bản: K1, K2, K3, K4, K5a, K5b, K0b, K7, hoặc BG (nền) / BG_single (ca bao bì lẻ làm mức nền).", "NOT NULL", ex(sr, "scenario_id")],
        ["source_review_id", "TEXT", "Gốc", "review_id gốc trong bộ Kaggle (thuộc reserve); mỗi review nguồn chỉ dùng một lần.", "thuộc reserve", ex(sr, "source_review_id")],
        ["review_text", "TEXT", "Gốc", "Nội dung gốc của review nguồn.", "NOT NULL", ex(sr, "review_text")],
        ["rating", "SMALLINT", "Gốc", "Số sao gốc.", "1..5", ex(sr, "rating")],
        ["label", "TEXT", "Gốc", "Nhãn gốc Kaggle của review nguồn.", "positive|negative", ex(sr, "label")],
        ["issue_type", "TEXT", "Quy tắc", "Nhóm lỗi nạp sẵn để WF2 không phải chờ WF1. Ca bao bì chọn bằng quy tắc từ khóa (đọc mẫu 30 ca thấy phần lớn đúng; chưa kiểm định độc lập); nhóm khác theo quy tắc từ khóa nên là ước lượng; positive = none.", "FK issue_types", ex(sr, "issue_type")],
        ["issue_type_source", "TEXT", "Suy ra", "rule_packaging | rule | none_positive: cách gán issue_type. Không có giá trị 'người gán' nào.", "NOT NULL", ex(sr, "issue_type_source")],
        ["lot_id", "TEXT", "Giả lập", "Lô của sự kiện. Với kịch bản, lô được chọn theo thiết kế (không ngẫu nhiên hoàn toàn).", "NOT NULL", ex(sr, "lot_id")],
        ["product_id", "TEXT", "Giả lập", "Suy ra từ lô.", "NOT NULL", ex(sr, "product_id")],
        ["customer_id", "TEXT", "Giả lập", "Mã khách giả.", "NOT NULL", ex(sr, "customer_id")],
        ["customer_tier", "TEXT", "Giả lập", "Hạng khách giả.", "VIP|Regular", ex(sr, "customer_tier")],
        ["window_start", "TIMESTAMPTZ", "Giả lập", "Đầu cửa sổ 4 giờ chứa sự kiện (đã tính sẵn để gom nhóm bằng GROUP BY).", "NOT NULL", ex(sr, "window_start")],
        ["created_at", "TIMESTAMPTZ", "Giả lập", "Thời điểm giả trong cửa sổ.", "NOT NULL", ex(sr, "created_at")]]
    sheet(wb, "scenario_reviews", H, sr_rows, W, 2, "Bảng scenario_reviews (kịch bản WF2)", f"Tệp: 02_scenarios/scenario_reviews.csv; {len(sr)} dòng ({scr['rows_by_set']}).")

    cp_rows = [
        ["checkpoint_id", "TEXT (PK)", "Suy ra", "T-<kịch bản> (tune) hoặc E-<kịch bản> (eval).", "duy nhất", ex(sc, "checkpoint_id")],
        ["scenario_set / scenario_id", "TEXT", "Suy ra", "Bộ và kịch bản của điểm kiểm tra.", "", f"{sc['scenario_set'].iloc[1]} / {sc['scenario_id'].iloc[1]}"],
        ["description", "TEXT", "Suy ra", "Mô tả kịch bản bằng tiếng Việt.", "", ex(sc, "description")],
        ["sim_now", "TIMESTAMPTZ", "Giả lập", "Thời điểm giả lập khi chạy WF2 (cuối cửa sổ).", "", ex(sc, "sim_now")],
        ["window_start / window_hours", "TIMESTAMPTZ / INT", "Giả lập", "Đầu và độ dài cửa sổ (4 giờ).", "", f"{sc['window_start'].iloc[1]} / {sc['window_hours'].iloc[1]}"],
        ["focus_lot_id / focus_issue_type", "TEXT", "Suy ra", "Lô và nhóm lỗi trọng tâm theo thiết kế; MULTI cho K4 (nhiều lô); '-' cho kịch bản không lỗi.", "", f"{sc['focus_lot_id'].iloc[1]} / {sc['focus_issue_type'].iloc[1]}"],
        ["max_cluster_size", "INTEGER", "Suy ra", "Số ca lớn nhất cùng (lô, nhóm lỗi) trong cửa sổ, TÍNH từ dữ liệu (không gõ tay).", "", ex(sc, "max_cluster_size")],
        ["reference_threshold", "INTEGER", "Giả lập", "Ngưỡng THAM CHIẾU (5 ca) để tính expected_alert. Đây là giả định của người dựng dữ liệu, V3 có thể đổi ngưỡng và tính lại bằng max_cluster_size.", "", ex(sc, "reference_threshold")],
        ["expected_alert", "BOOLEAN", "Suy ra", "True nếu max_cluster_size >= reference_threshold; các dòng chạy lặp (K6a, K6b) luôn False vì cụm đã được báo trước đó (rerun_of).", "", ex(sc, "expected_alert")],
        ["rerun_of", "TEXT", "Suy ra", "Điểm kiểm tra gốc nếu đây là lần chạy lặp.", "NULL nếu không", "(trống)"]]
    sheet(wb, "scenario_checkpoints", H, cp_rows, W, 2, "Bảng scenario_checkpoints (kỳ vọng WF2)", f"Tệp: 02_scenarios/scenario_checkpoints.csv; {len(sc)} điểm kiểm tra, {int(sc['expected_alert'].sum())} điểm kỳ vọng có cảnh báo.")

    it_rows = [[k, v, "ĐỀ XUẤT - chờ nhóm chốt ở CH01"] for k, v in cat.items()]
    sheet(wb, "issue_types", ["issue_type", "Ý nghĩa", "Trạng thái"], it_rows, [26, 90, 36], None, "Danh mục issue_type (đề xuất)")

    lb = sp["label_by_split"]
    split_rows = [
        ["few_shot_pool", sp["split_counts"]["few_shot_pool"], "Kho chọn ví dụ few-shot (cân bằng nhãn).", "Không dùng chấm điểm."],
        ["validation", sp["split_counts"]["validation"], "Chọn phiên bản prompt (v1/v2/v3).", "Không dùng few-shot từ tập này; có 4 ca lệch tự nhiên."],
        ["test_main", sp["split_counts"]["test_main"], "Test chính: ngẫu nhiên, phân tầng theo nhãn gốc.", "Chỉ chạy sau khi đóng băng prompt."],
        ["test_skew", sp["split_counts"]["test_skew"], "Test lệch: các ca rating-label bất đồng (+2 ca cùng nhóm gần trùng).", "Chấm bằng nhãn người, không phải nhãn gốc."],
        ["reserve", sp["split_counts"]["reserve"], "Kho dự trữ; nguồn của bộ kịch bản và ví dụ few-shot bổ sung.", "Không dùng để chấm điểm."],
        ["test_unaccented (tệp riêng)", sp["test_unaccented_rows"], "Bản không dấu của test_main.", "Kiểm tra độ bền; nhãn lấy theo review_id."]]
    sheet(wb, "Các tập dữ liệu", ["Tập", "Số dòng", "Mục đích", "Quy tắc sử dụng"], split_rows, [30, 12, 70, 56], None, "Các tập sau khi chia",
          f"Seed {P['seed']}; chia theo nhóm gần trùng; kiểm tra rò rỉ: {sum(sp['verification'].values())}/{len(sp['verification'])} đạt.")
    wb.save(a.out)
    print("đã ghi", a.out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviews", default=str(ROOT / "01_data" / "reviews.csv"))
    ap.add_argument("--gold", default=str(ROOT / "01_data" / "review_gold.csv"))
    ap.add_argument("--unaccented", default=str(ROOT / "01_data" / "test_unaccented.csv"))
    ap.add_argument("--scen-reviews", dest="scen_reviews", default=str(ROOT / "02_scenarios" / "scenario_reviews.csv"))
    ap.add_argument("--scen-cp", dest="scen_cp", default=str(ROOT / "02_scenarios" / "scenario_checkpoints.csv"))
    ap.add_argument("--split-report", dest="split_report", default=str(ROOT / "06_reports" / "split_report.json"))
    ap.add_argument("--scen-report", dest="scen_report", default=str(ROOT / "02_scenarios" / "scenario_report.json"))
    ap.add_argument("--catalog", default=str(ROOT / "03_prompt" / "issue_type_catalog.json"))
    ap.add_argument("--out", default=str(ROOT / "01_data" / "data_dictionary.xlsx"))
    main(ap.parse_args())
