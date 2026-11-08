# Báo cáo Phân tích Lỗi (Error Analysis) - Phần A

> Ngày thực hiện: 08/11/2026 · Phân tích trên tập Validation và Test chính của hai hệ thống Baseline

---

## 1. Tổng quan phân loại lỗi

Dựa trên kết quả đo đạc của hai baseline:
- **Baseline rating <= 2:** Có 57 ca sai trên Test chính (Recall Negative đạt 0.704, bỏ sót 55 ca negative ở mức 3 sao).
- **Baseline rating <= 3:** Có 10 ca sai trên Test chính (Accuracy 0.967, sai ở 10 ca lệch giữa số sao và nội dung thực tế).

### Bảng phân bố loại lỗi trên Test chính (Baseline rating <= 3 - 10 ca lệch)
| STT | Mã Review | Số sao | Nhãn gốc (Gold) | Baseline đoán | Nhóm lỗi (Category) | Giải thích ngắn |
|:---:|:---:|:---:|:---:|:---:|:---|:---|
| 1 | `11966055238` | 5 sao | negative | positive | **khen chê lẫn lộn** | Khen mọi thứ ok nhưng phàn nàn kho chuẩn bị hàng quá lâu |
| 2 | `22925077822` | 2 sao | positive | negative | **nhãn gốc nhiễu** | "Hương vị tốt, giao nhanh" nhưng chấm 2 sao (bấm nhầm sao) |
| 3 | `30066454958` | 5 sao | negative | positive | **khen chê lẫn lộn** | Khen máy sấy rẻ đẹp nhưng chê mức sấy không đủ nóng, tóc lâu khô |
| 4 | `35851470890` | 4 sao | negative | positive | **mỉa mai** | Chê đóng gói "tệ hơn cả điểm kiểm tra môn CNXH 🙃", mỉa mai sâu cay |
| 5 | `60360003131` | 3 sao | positive | negative | **khác (câu nhận xu)** | Khen rất ok, kèm câu mẫu nhận xu, khách chỉ chấm 3 sao |
| 6 | `62666444286` | 3 sao | positive | negative | **khác (3 sao khen)** | Khen toàn diện (giao nhanh, đóng gói chắn chắn, sp đẹp) nhưng ấn 3 sao |
| 7 | `74109523612` | 2 sao | positive | negative | **nhãn gốc nhiễu** | Khen dầu gội thơm, giao nhanh, giá sale rẻ nhưng chấm 2 sao |
| 8 | `75550701447` | 4 sao | negative | positive | **khen chê lẫn lộn** | Khen serum mềm mượt nhưng chê lỗi nút nhấn kẹt không ra |
| 9 | `76412785773` | 3 sao | positive | negative | **khác (nói 5 sao ấn 3)** | Khách ghi "cho shop 5 sao" nhưng tay lại bấm 3 sao |
| 10 | `82735910951` | 3 sao | positive | negative | **tiếng lóng/viết tắt** | "Ăn rất ngon, ĐÁNH GIÁ 5 SAO BẠN SÍP NHIỆT TINH" nhưng ấn 3 sao |

---

## 2. Phân tích chi tiết từng nhóm lỗi phức tạp & Ví dụ tiêu biểu

### Nhóm 1: Mỉa mai (Sarcasm)
- **Đặc trưng:** Khách hàng sử dụng các từ ngữ khen ngợi mang tính châm biếm, biểu tượng cảm xúc cười gượng (`🙃`, `🙂`, `:))`), so sánh hài hước nhưng nội dung thực chất là chỉ trích gay gắt lỗi sản phẩm hoặc dịch vụ.
- **Ví dụ điển hình:**
  > **Review `35851470890` (4 sao):**
  > *"Dầu gội thì đầy... Mà shop ko bọc được cái chống sốc vào à. Thấy nhiều ng phản ánh việc này lắm rồi mà vẫn ko rút kinh nghiệm à... Shop lớn mà khâu đóng gói còn tệ hơn cả điểm kiểm tra môn chủ nghĩa xã hội của t nữa🙃. Mong shop sau chuẩn bị hàng có tâm hơn"*
- **Hạn chế của Baseline:** Baseline chỉ nhìn vào số sao (4 sao $\ge$ 3) nên tự động gán là Positive $ightarrow$ **Bỏ sót hoàn toàn sự cố đóng gói nghiêm trọng**. Đây là lý do cốt lõi cần LLM (Gemini/Claude) có khả năng hiểu ngữ dụng học (pragmatics).

---

### Nhóm 2: Khen chê lẫn lộn (Mixed Sentiment)
- **Đặc trưng:** Review gồm nhiều vế câu, trong đó khách hài lòng về một khía cạnh (sản phẩm, giá cả) nhưng thất vọng về một khía cạnh khác (giao hàng, đóng gói, lỗi bộ phận).
- **Ví dụ điển hình:**
  > **Review `75550701447` (4 sao):**
  > *"Serum vào nếp thơm suôn mềm mượt. Điểm trừ là nút nhấn bị kẹt, nhấn ko ra serum, phải mở nắp chai để dùng"*
  > 
  > **Review `11966055238` (5 sao):**
  > *"Lại một lần nữa tất cả mọi thứ đều oke cho đến lúc kho smart chuẩn bị rất là lâu"*
- **Ý nghĩa trong bài toán CRM:** Dù khách cho 4-5 sao, đây vẫn là các ca phát sinh lỗi kỹ thuật (`product_defect`) hoặc vận chuyển (`delivery_issue`) cần bộ phận CRM tiếp nhận hỗ trợ.

---

### Nhóm 3: Tiếng lóng, Viết tắt và Lỗi gõ phím (Slang & Typos)
- **Đặc trưng:** Khách hàng viết sai chính tả, teencode hoặc từ địa phương (`síp`, `ddeoj`, `thietes`, `sâyd`).
- **Ví dụ điển hình:**
  > **Review `82735910951` (3 sao):**
  > *"Ngon mình đã mua thư ăn rất ngon moi người lên mua ăn nha đánh giá 5 SAO BẠN SÍP NHIỆT TINH"*
- **Phân tích:** Khách khen shipper nhiệt tình, khẳng định đánh giá 5 sao bằng chữ hoa, nhưng thao tác chọn nhầm 3 sao.

---

### Nhóm 4: Nhãn gốc bị nhiễu (Label Noise / Bấm nhầm sao)
- **Đặc trưng:** Khách hoàn toàn khen ngợi từ đầu đến cuối nhưng chấm 1-2 sao (do bấm nhầm trên điện thoại hoặc thói quen "cho 1 sao để nổi bật").
- **Ví dụ điển hình:**
  > **Review `74109523612` (2 sao):**
  > *"Làm đẹp:mọi loại tóc Mẹo:sử dụng dầu gội hàng ngày Bao bì:thietes kế chai nhựa 840g Giáo hàng nhanh, mua sale giá rẻ hơn, chất lượng tốt, hương gió biển thơm"*
- **Giải pháp:** Cần đối chiếu giữa nhãn gốc và nhãn người gán (Human Label) để làm sạch ground truth.

---

## 3. Kết luận & Khuyến nghị cho Bộ phân loại AI
1. **Baseline rating <= 2** bị điểm yếu chí mạng là **Recall Negative thấp (70.4%)**, bỏ sót tới 55 review 3 sao chứa phàn nàn bao bì/chất lượng.
2. **Baseline rating <= 3** đạt độ chính xác cao trên bề mặt (96.7%), nhưng **hoàn toàn bất lực trước các ca mỉa mai và khen chê lẫn lộn** (như ca 35851470890 và 75550701447).
3. **Giá trị vượt trội của Gemini/LLM:** Khả năng đọc hiểu nội dung thực chất, bóc tách chính xác loại sự cố (`issue_type`) và xử lý các ca mỉa mai phức tạp mà không bị phụ thuộc vào số sao.
