# Hướng dẫn gán nhãn Test lệch (Positive / Negative)

**Mục đích.** Tạo nhãn "theo nội dung văn bản" cho các review mà số sao và nhãn gốc của bộ Kaggle không khớp nhau. Nhãn này dùng làm chuẩn để chấm Test lệch và để tính Cohen's kappa giữa người gán.

## 1. Quy tắc làm việc
1. Mỗi người điền **một file riêng** (`phieu_gan_nhan_<nua>_<rater>.csv`), gán **độc lập**, **không bàn nhau và không xem file của người kia**.
2. Chỉ dựa vào **nội dung chữ** của review. Phiếu cố ý không có số sao, nhãn gốc hay kết quả của Gemini. Không tra cứu các thông tin đó.
3. Điền cột `label` bằng đúng một trong hai giá trị: `positive` hoặc `negative` (viết thường).
4. Nếu thực sự không quyết định được, điền nhãn bạn nghiêng về, đặt `unsure` = `1` và ghi lý do ngắn vào `note`. Ca `unsure` sẽ được đưa vào bước thống nhất, không tính vào kappa.

## 2. Định nghĩa nhãn (giống định nghĩa trong prompt phân loại)
- **negative:** khách không hài lòng vì một sự cố hoặc điểm kém cụ thể (hàng hỏng/móp/vỡ, thiếu hoặc sai hàng, thiếu quà tặng, giao chậm, chất lượng kém, không đúng mô tả, thái độ phục vụ kém) và không thể hiện sự hài lòng chung.
- **positive:** khách hài lòng chung. Góp ý nhỏ mà khách vẫn khen hoặc nói sẽ mua lại vẫn là positive. Không có phàn nàn cụ thể nào thì là positive.

## 3. Các tình huống khó
| Tình huống | Cách gán | Ví dụ (rút gọn) |
|---|---|---|
| Mỉa mai: câu khen đi kèm nội dung nêu lỗi | Xét theo nội dung thực, thường là negative | "tuyệt vời, đóng hàng sơ sài, vỡ sữa" → negative |
| Khen chê lẫn lộn, có sự cố cụ thể và khách buồn/thất vọng | negative | "chất lượng ok nhưng thiếu quà tặng, hơi buồn" → negative |
| Khen chê lẫn lộn, lỗi chỉ là chi tiết nhỏ và khách vẫn hài lòng | positive | "kem tốt, hộp hơi móp, còn lại rất ok, nên mua thử" → positive |
| Chỉ có câu mẫu "hình ảnh và video chỉ mang tính chất minh họa/nhận xu" | Không phải phàn nàn → positive nếu không có ý chê khác | |
| Chưa dùng sản phẩm, không có phàn nàn | positive | |
| Review không liên quan sản phẩm hoặc không đọc hiểu được | Gán theo ý nghiêng nhiều hơn, đặt `unsure` = 1 | |
| Có trường mẫu của Shopee ở đầu (ví dụ "Chất lượng sản phẩm:tốt") | Đọc cả phần nhận xét tự do ở sau rồi mới quyết định | |

## 4. Quy trình
1. Hai người trong cặp điền xong phiếu của mình (không trao đổi).
2. Chạy `python 05_scripts/compute_kappa.py --dir 04_labeling` để xem kappa từng cặp và tạo `to_reconcile.csv` (các ca bất đồng hoặc `unsure`).
3. Hai người trong cặp ngồi bàn và điền `final_label` (và `ly_do`) cho từng ca trong `to_reconcile.csv`.
4. Chạy lại với `--finalize` để tạo `human_labels_final.csv`; dùng file này với `evaluate.py --human`.

## 5. Cần báo cáo
- Cohen's kappa **trước** khi thống nhất, cho từng cặp (file `kappa_report.csv`).
- Số mẫu mỗi lớp sau thống nhất và tỷ lệ nhãn người khác nhãn gốc.
- Số ca `unsure` và cách xử lý. Cỡ mẫu Test lệch nhỏ nên mọi kết quả trên tập này cần ghi kèm cỡ mẫu và khoảng tin cậy.
- Lưu ý: kappa của Test lệch thường thấp hơn các tập thông thường vì đây là các ca vốn mơ hồ (số sao và nội dung không khớp). Điều này là bình thường, nhưng cần nói rõ khi báo cáo.
