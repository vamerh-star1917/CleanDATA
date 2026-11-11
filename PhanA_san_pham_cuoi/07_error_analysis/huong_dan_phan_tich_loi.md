# Hướng dẫn phân tích lỗi của bộ phân loại (Gemini)

Mục đích: với mỗi review mà mô hình dự đoán sai so với nhãn chuẩn (`gold`), xác định **vì sao** sai. Kết quả dùng cho mục "Phân tích lỗi" của báo cáo. Các nhóm lỗi dưới đây được xác định **trước khi xem lỗi của Gemini**; nếu trong lúc chấm xuất hiện một kiểu lỗi lặp lại mà không nhóm nào chứa được, ghi vào cột `note` và đề xuất thêm nhóm ở bước thống nhất, không tự đặt tên nhóm mới trong cột `error_category`.

## Quy tắc chung

- Mỗi người chấm **một file riêng** (`phieu_loi_coder1.csv` hoặc `phieu_loi_coder2.csv`), chấm độc lập, không bàn nhau và không xem file của người kia.
- **Đọc nội dung `review_text` trước**, tự quyết định review nói điều gì, rồi mới so với `gold` và `model_pred`. Với Test không dấu, `review_text` là đúng văn bản mô hình đã nhận.
- Chọn **một** nhóm chính cho cột `error_category` theo thứ tự ưu tiên bên dưới (dừng ở nhóm đầu tiên đúng). Nếu thật sự không quyết được, chọn nhóm gần nhất, đặt `unsure = 1` và ghi `note`.
- `gold` của Test chính/Test không dấu là nhãn gốc Shopee/Kaggle. `gold` của Test lệch là **nhãn người**.
- `error_type`: **FN** = review gold negative nhưng mô hình dự đoán positive (bỏ sót, nghiêm trọng nhất với CRM); **FP** = gold positive nhưng dự đoán negative.

## Các nhóm (thứ tự ưu tiên)

| Giá trị `error_category` | Khi nào chọn | Ví dụ minh họa (từ tập few-shot, không phải Test) |
|---|---|---|
| `nhan_goc_nhieu` | Sau khi đọc riêng nội dung, bạn thấy **nhãn `gold` mâu thuẫn rõ với nội dung** và dự đoán của mô hình hợp lý hơn nhãn. Chỉ áp dụng cho **Test chính và Test không dấu** (nhãn gốc). Không dùng cho Test lệch, vì gold ở đó là nhãn người. | Review chê rõ ràng nhưng gold = positive. |
| `mia_mai` | Có lời khen hoặc biểu tượng cười gượng đi kèm nội dung nêu lỗi, ý thật là chê. Mô hình hiểu theo nghĩa đen. | "Hương vị:ngon tuyệt vời Đóng hàng sơ sài giao hàng vỡ sữa"; "...Ủa là s dị 🙂" |
| `khen_che_lan_lon` | Review vừa khen vừa nêu một sự cố cụ thể; nhãn phụ thuộc quy tắc "khách có thất vọng/yêu cầu cải thiện hay vẫn hài lòng". Mô hình nghiêng sai về một phía. | "Bao bì đóng gói kĩ nhưng khi khui ra thì 1 hộp bị móp, shop vui lòng..." |
| `tieng_long_viet_tat` | Lỗi do cách viết: tiếng lóng, viết tắt, teencode, sai chính tả, **mất dấu** (Test không dấu), emoji thay chữ, khiến mô hình đọc sai. | "ko", "r", "k mùi", văn bản không dấu |
| `mo_ho` | Review thật sự ranh giới: không có phàn nàn rõ ràng hoặc phàn nàn rất nhẹ, hai người đọc có thể gán nhãn khác nhau; dự đoán của mô hình **bảo vệ được**. | "giao hàng khá lâu" (không nói thất vọng) |
| `khac_loi_mo_hinh` | Nội dung rõ ràng, gold hợp lý, không có đặc điểm ở các nhóm trên mà mô hình vẫn sai (ví dụ bỏ sót phàn nàn nằm sau các trường mẫu Shopee, hoặc bị lời khen dài che lấp). Ghi chú ngắn nguyên nhân nếu thấy. | |

Lỗi kỹ thuật (API lỗi, JSON sai, `status` khác `ok`) được script tự gán nhóm `ky_thuat`; bạn không phải chấm.

## Cách ghi

- `error_category`: đúng một giá trị trong bảng (viết liền, chữ thường, đúng chính tả).
- `unsure`: để trống hoặc `1`.
- `note`: một câu ngắn, ví dụ "khen 'tuyệt vời' nhưng nêu vỡ sữa".

## Sau khi chấm

1. Mỗi người gửi lại file đã điền cho nhóm trưởng.
2. `python summarize_errors.py` tính tỷ lệ đồng thuận, Cohen's kappa theo nhóm lỗi và xuất `to_reconcile_errors.csv`.
3. Hai người thống nhất các ca bất đồng, điền `final_category` và `reconcile_note`.
4. `python summarize_errors.py --finalize` xuất bảng tổng hợp và ví dụ gợi ý. Nhóm chọn 1 đến 2 ví dụ mỗi nhóm cho báo cáo.

## Điều cần ghi trong báo cáo

- Số ca lỗi từng tập, kappa trước khi thống nhất, cách thống nhất.
- Số lỗi nhỏ nên các tỷ lệ chỉ mang tính mô tả.
- Tỷ lệ lỗi thuộc `nhan_goc_nhieu` + `mo_ho` cho biết mức độ lỗi **không hẳn do mô hình**; trình bày riêng với các nhóm lỗi thực của mô hình.
