# Phần A - Dữ liệu và phân loại: sản phẩm cuối (Bản hoàn tất)

Đọc trước: `Tai_lieu_thuc_hien_PhanA_HoanTat.docx` (tổng hợp toàn bộ quá trình, giải thích sản phẩm, số liệu đo đạc thực tế, nghiệm thu hoàn tất).

| Thư mục | Nội dung chính |
|---|---|
| **01_data** | `reviews.csv` (9.594 reviews sạch kèm trường giả lập), `review_gold.csv` (nhãn chuẩn, phân chia split và nhóm gần trùng), `test_unaccented.csv` (300 mẫu test không dấu), `data_dictionary.xlsx`, `preload/schema.sql`, `preload/reviews_preload.sql` |
| **02_scenarios** | `scenario_reviews.csv`, `scenario_checkpoints.csv`, `scenario_report.json` (dành cho Phần C / WF2 cảnh báo khủng hoảng) |
| **03_prompt** | `prompt_v3.json` (đã chọn và đóng băng **Prompt v3** gồm 10 few-shot + 5 quy tắc ca khó), `output_schema.json`, `fewshot_examples.json`, `issue_type_catalog.json` |
| **04_labeling** | Đã hoàn tất 100%: 4 phiếu gán nhãn thô (`phieu_gan_nhan_nua1_rater1.csv`...`rater4.csv`), `kappa_report.csv` (Cohen's Kappa = 0.9133 & 1.0), `to_reconcile.csv` (6 ca đối soát), `human_labels_final.csv` (197 nhãn người chốt), `huong_dan_gan_nhan.md` |
| **05_scripts** | Toàn bộ 15 script dữ liệu, script đánh giá, và script tự động hóa trọn gói `chay_gemini_va_danh_gia.py`, `run_error_analysis.py`, `run_pipeline.sh` |
| **06_reports** | `metrics.csv` (đầy đủ chỉ số trên Validation, Test chính và Test lệch), `phan_tich_loi.md`, các file `errors_*.csv` (đã điền category & notes), `bao_cao_kiem_tra_du_lieu.md`, các ma trận nhầm lẫn PNG, `cleaning_log.json`, `split_report.json`, `preload_check.json`, `cache.sqlite` |

- **Mô hình & Prompt đánh giá chính thức:** Đã chốt sử dụng **Gemini 3.8 Flash** (`gemini-3.8-flash`) và **Prompt v3** (Phương án B: bỏ qua so sánh v1/v2 trên Validation để tiết kiệm quota, tập trung đánh giá thẳng trên các tập Test).
- **Chạy thực nghiệm Gemini 3.8 (1-click):** Chạy file `chay_phan_a.bat` ở thư mục gốc và nhập API Key (tự động chạy model `gemini-3.8-flash` với Prompt v3 trên Test chính r1/r2, Test không dấu, Test lệch và ghi nhận kết quả vào `06_reports/metrics.csv`).
- **Tái dựng toàn bộ từ dữ liệu thô:** `bash 05_scripts/run_pipeline.sh <thư mục chứa shopee_reviews_dataset.jsonl và aug_unaccented_reviews.jsonl>`
