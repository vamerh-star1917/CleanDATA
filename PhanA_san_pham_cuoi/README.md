# Phần A - Dữ liệu và phân loại: sản phẩm cuối (Bản hoàn tất)

Đọc trước: `Tai_lieu_thuc_hien_PhanA_HoanTat.docx` (tổng hợp toàn bộ quá trình, giải thích sản phẩm, số liệu đo đạc thực tế, nghiệm thu hoàn tất).

| Thư mục | Nội dung chính |
|---|---|
| **01_data** | `reviews.csv` (1.164 reviews sạch), `review_gold.csv` (nhãn chuẩn và phân chia tập), `test_set.csv`, `test_hard.csv`, `data_dictionary.xlsx`, `preload/schema.sql`, `preload/reviews_preload.sql` |
| **02_scenarios** | `scenario_reviews.csv`, `scenario_checkpoints.csv`, `scenario_report.json` (dành cho WF2) |
| **03_prompt** | `prompt_v3.json` (đã chọn và đóng băng **Prompt v3** gồm 10 few-shot + 5 quy tắc ca khó), `output_schema.json`, `issue_type_catalog.json` |
| **04_labeling** | Đã hoàn tất 100%: 4 phiếu gán nhãn, `kappa_report.csv` (Cohen's Kappa = 0.9133 & 1.0), `to_reconcile.csv` (6 ca đã đối soát), `human_labels_final.csv` (197 nhãn người) |
| **05_scripts** | Toàn bộ script dữ liệu, script đánh giá, và script tự động hóa trọn gói `chay_gemini_va_danh_gia.py` |
| **06_reports** | `metrics.csv` (đầy đủ chỉ số trên Validation, Test chính và Test lệch), `phan_tich_loi.md`, các file `errors_*.csv` (đã điền category & notes), `bao_cao_kiem_tra_du_lieu.md`, các ma trận nhầm lẫn PNG |

- **Mô hình & Prompt đánh giá chính thức:** Đã chốt sử dụng **Gemini 3.8 Flash** (`gemini-3.8-flash`) và **Prompt v3** (Phương án B: bỏ qua so sánh v1/v2 trên Validation để tiết kiệm quota, tập trung đánh giá thẳng trên các tập Test).
- **CRM Workflow n8n tích hợp Gemini 3.8:** File [`CRM_Workflow_GeminiV3.json`](./CRM_Workflow_GeminiV3.json) — Workflow 12 nodes nạp review thô vào Postgres, gọi Gemini 3.8 Flash REST API với Prompt v3, phân loại label + issue_type, sinh response_draft theo mẫu sự cố, phân luồng VIP/Regular và bắn Telegram Alert kèm nút Duyệt/Sửa/Từ chối.
- **Chạy thực nghiệm Gemini 3.8 (1-click):** Chạy file `chay_phan_a.bat` ở thư mục gốc và nhập API Key (tự động chạy model `gemini-3.8-flash` với Prompt v3 trên Test chính r1/r2, Test không dấu, Test lệch và ghi nhận kết quả vào `06_reports/metrics.csv`).
- **Tái dựng toàn bộ từ dữ liệu thô:** `bash 05_scripts/run_pipeline.sh <thư mục chứa shopee_reviews_dataset.jsonl và aug_unaccented_reviews.jsonl>`
