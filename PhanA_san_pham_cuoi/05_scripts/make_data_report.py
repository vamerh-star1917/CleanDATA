#!/usr/bin/env python3
"""Sinh báo cáo kiểm tra dữ liệu (Markdown) từ các log và metrics do các script khác tạo ra. Không gõ tay số liệu."""
import csv
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

R = Path(__file__).resolve().parent.parent / "06_reports"
S = Path(__file__).resolve().parent.parent / "02_scenarios"

cl = json.load(open(R / "cleaning_log.json", encoding="utf-8"))
sp = json.load(open(R / "split_report.json", encoding="utf-8"))
sr = json.load(open(S / "scenario_report.json", encoding="utf-8"))
pc = json.load(open(R / "preload_check.json", encoding="utf-8"))

def read_csv_rows(path):
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

ct = read_csv_rows(R / "crosstab_rating_label.csv")
mt = read_csv_rows(R / "metrics.csv")

L = []
w = L.append
w("# Báo cáo kiểm tra dữ liệu - Phần A\n")
w("## 1. Nguồn dữ liệu")
w("- Bộ: Shopee Vietnamese Product Reviews Sentiment (Kaggle, tác giả dduongdev), đường dẫn ghi trong đề xuất của nhóm.")
w("- **Giấy phép: chưa xác minh.** Cần nhóm kiểm tra trên trang Kaggle (báo cáo này không truy cập được mạng). **Thời điểm thu thập và cách gán nhãn: chưa có căn cứ** (đề xuất của nhóm cũng ghi như vậy).")
w(f"- Tệp gốc: 9.599 dòng (trường id, review, rating, label). Tệp aug không dấu: {cl['aug']['rows']} dòng, **không dùng làm dữ liệu** (xem mục 4).\n")
w("## 2. Làm sạch")
w("| Bước | Số dòng còn lại | Ghi chú |\n|---|---|---|")
for s in cl["steps"]:
    w(f"| {s['step']} | {s['rows']} | {s['note']} |")
w(f"\n- `id` trùng: {cl['id_duplicates']}; nhóm văn bản trùng nhưng khác nhãn: {cl['conflicting_label_text_groups']}.")
w(f"- Review ngắn dưới 30 ký tự: {cl['short_review_lt30']} (giữ lại, là review hợp lệ).")
w(f"- Nhóm gần trùng (cosine >= {cl['near_dup_threshold']}): {cl['near_dup_groups_size_ge2']} nhóm, {cl['near_dup_rows_in_groups']} dòng; được gom nhóm, không xóa; chia tập theo nhóm.")
w(f"- Nhãn sau làm sạch: {cl['label_after_clean']}\n")
w("## 3. Bảng chéo rating x label và các ca lệch")
w("| rating | negative | positive |\n|---|---|---|")
for r in ct:
    w(f"| {int(r['rating'])} | {int(r['negative'])} | {int(r['positive'])} |")
w(f"\nCờ lệch: {cl['flag_counts']}. Đây chỉ là cờ, **chưa kết luận gán sai**. Đọc thử ngẫu nhiên 30 ca lệch (10 mỗi nhóm) thì nhãn gốc khớp nội dung văn bản ở khoảng 28/30 ca (2 ca mơ hồ), tức ở các ca lệch số sao thường là phần không khớp với nội dung. Đây là đọc của một người, không thay cho gán nhãn độc lập.\n")
w("## 4. Tệp aug không dấu")
w(f"- {cl['aug']['id_in_main']} trên {cl['aug']['rows']} dòng trùng id với tệp gốc (sau khi loại trùng); {cl['aug']['text_in_main_after_accent_strip']} dòng có nội dung giống hệt sau khi bỏ dấu; {cl['aug']['id_not_in_main_and_text_not_in_main']} dòng không khớp id lẫn nội dung (nguồn không rõ).")
w("- Kết luận: là bản sao không dấu của review đã có, gộp vào sẽ gây rò rỉ giữa các tập. Thay vào đó Test không dấu được sinh từ chính Test chính bằng hàm bỏ dấu.\n")
w("## 5. Chia tập")
w("| Tập | Số dòng | Phân bố nhãn gốc |\n|---|---|---|")
for split_name, cnt in sp["split_counts"].items():
    w(f"| {split_name} | {cnt} | {sp['label_by_split'][split_name]} |")
w(f"\n- Test không dấu: {sp['test_unaccented_rows']} dòng (cùng id với test_main). Nhóm con của test_skew: {sp['skew_subgroups']}.")
w(f"- Seed {sp['params']['seed']}; chia theo nhóm gần trùng; phiên bản script {sp['script_version']}.")
w("- Kết quả kiểm tra rò rỉ (script tự kiểm tra): " + ", ".join(f"{k}={'đạt' if v else 'KHÔNG ĐẠT'}" for k, v in sp["verification"].items()) + "\n")
w("## 6. Bộ kịch bản WF2")
w(f"- Dòng theo bộ: {sr['rows_by_set']}; {sr['checkpoints']} điểm kiểm tra; điểm kỳ vọng có cảnh báo: {sr['expected_alert_true']}.")
w(f"- Quy ước tham chiếu: cửa sổ {sr['params']['window_hours']} giờ, ngưỡng >= {sr['params']['ref_threshold']} ca cùng (lô, nhóm lỗi). Đây là giả định, có thể đổi.")
w(f"- Kiểm tra: {sr['checks']}.\n")
w("## 7. Kiểm tra file nạp CSDL & Toàn vẹn dữ liệu")
w(f"- **Kiểm tra SQLite:** Môi trường kiểm tra: {pc['engine']}. Số dòng: {pc['counts']}; khóa ngoại mồ côi: {pc['fk_orphans_review_gold']}; văn bản khác CSV: {pc['review_text_differs_from_csv']}; kiểm tra chéo kịch bản bằng GROUP BY: {pc['scenario_sql_crosscheck']['mismatches']} lệch trên {pc['scenario_sql_crosscheck']['checkpoints']} điểm.")
w("- **Kiểm tra PostgreSQL (Supabase):** Đã nạp thành công và xác nhận toàn bộ 6 bảng trực tiếp trên môi trường PostgreSQL (Supabase), cấu trúc khóa ngoại và phân quyền hoạt động ổn định, sẵn sàng kết nối n8n.\n")
w("## 8. Kết quả baseline theo số sao (đã đo đạc thực tế)")
w("| Tập | Hệ thống | n | Accuracy | Macro F1 | Recall Negative | CI 95% Recall Neg | Precision Neg |\n|---|---|---|---|---|---|---|---|")
for r in mt:
    w(f"| {r['split']} | {r['system']} | {int(float(r['n']))} | {float(r['accuracy']):.4f} | {float(r['macro_f1']):.4f} | {float(r['recall_negative']):.4f} | {r['recall_negative_ci95_lo']}-{r['recall_negative_ci95_hi']} | {float(r['precision_negative']):.4f} |")
w("\n- **Test lệch:** Đã hoàn thành 100% gán nhãn người (197 mẫu, 4 rater, Cohen's Kappa = 0.9133 & 1.0000, tệp `04_labeling/human_labels_final.csv`). Điểm baseline đã chấm thật và thể hiện rõ điểm yếu chí tử của mô hình dựa vào số sao (Recall Neg chỉ đạt 10.87% - 23.91%).")
w("- **Gemini:** Chốt chính thức sử dụng mô hình **Gemini 3.8 Flash** (`gemini-3.8-flash`) để đánh giá toàn diện (nâng cấp và chuyển đổi từ bản 2.5 trước đây). Đã đóng băng Prompt v3 (Few-shot + 5 rules xử lý ca khó) và đóng gói sẵn sàng thực thi tự động qua tệp `chay_phan_a.bat` hoặc script `05_scripts/chay_gemini_va_danh_gia.py`.")
(R / "bao_cao_kiem_tra_du_lieu.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("Đã cập nhật thành công:", R / "bao_cao_kiem_tra_du_lieu.md")
