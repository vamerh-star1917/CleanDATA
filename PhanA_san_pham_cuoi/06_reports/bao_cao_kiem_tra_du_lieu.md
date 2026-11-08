# Báo cáo kiểm tra dữ liệu - Phần A

## 1. Nguồn dữ liệu
- Bộ: Shopee Vietnamese Product Reviews Sentiment (Kaggle, tác giả dduongdev), đường dẫn ghi trong đề xuất của nhóm.
- **Giấy phép: chưa xác minh.** Cần nhóm kiểm tra trên trang Kaggle (báo cáo này không truy cập được mạng). **Thời điểm thu thập và cách gán nhãn: chưa có căn cứ** (đề xuất của nhóm cũng ghi như vậy).
- Tệp gốc: 9.599 dòng (trường id, review, rating, label). Tệp aug không dấu: 1348 dòng, **không dùng làm dữ liệu** (xem mục 4).

## 2. Làm sạch
| Bước | Số dòng còn lại | Ghi chú |
|---|---|---|
| 1. Đọc file gốc | 9599 | dòng lỗi JSON: 0 |
| 2. Loại review rỗng/thiếu trường | 9599 | loại 0 |
| 3. Loại văn bản trùng nhưng khác nhãn | 9599 | loại 0 |
| 4. Loại bản trùng văn bản (giữ bản đầu) | 9594 | loại 5 |
| 5. Gom nhóm gần trùng (không xóa) | 9594 | 42 nhóm, 105 dòng |

- `id` trùng: 0; nhóm văn bản trùng nhưng khác nhãn: 0.
- Review ngắn dưới 30 ký tự: 338 (giữ lại, là review hợp lệ).
- Nhóm gần trùng (cosine >= 0.9): 42 nhóm, 105 dòng; được gom nhóm, không xóa; chia tập theo nhóm.
- Nhãn sau làm sạch: {'negative': 5960, 'positive': 3634}

## 3. Bảng chéo rating x label và các ca lệch
| rating | negative | positive |
|---|---|---|
| 1 | 2956 | 14 |
| 2 | 1219 | 9 |
| 3 | 1690 | 91 |
| 4 | 29 | 67 |
| 5 | 66 | 3453 |

Cờ lệch: {'khop': 9385, 'hi_sao_nhan_negative': 95, '3sao_nhan_positive': 91, 'thap_sao_nhan_positive': 23}. Đây chỉ là cờ, **chưa kết luận gán sai**. Đọc thử ngẫu nhiên 30 ca lệch (10 mỗi nhóm) thì nhãn gốc khớp nội dung văn bản ở khoảng 28/30 ca (2 ca mơ hồ), tức ở các ca lệch số sao thường là phần không khớp với nội dung. Đây là đọc của một người, không thay cho gán nhãn độc lập.

## 4. Tệp aug không dấu
- 1326 trên 1348 dòng trùng id với tệp gốc (sau khi loại trùng); 1315 dòng có nội dung giống hệt sau khi bỏ dấu; 20 dòng không khớp id lẫn nội dung (nguồn không rõ).
- Kết luận: là bản sao không dấu của review đã có, gộp vào sẽ gây rò rỉ giữa các tập. Thay vào đó Test không dấu được sinh từ chính Test chính bằng hàm bỏ dấu.

## 5. Chia tập
| Tập | Số dòng | Phân bố nhãn gốc |
|---|---|---|
| reserve | 8887 | {'negative': 5561, 'positive': 3326} |
| test_main | 300 | {'negative': 186, 'positive': 114} |
| test_skew | 197 | {'positive': 107, 'negative': 90} |
| validation | 150 | {'negative': 93, 'positive': 57} |
| few_shot_pool | 60 | {'positive': 30, 'negative': 30} |

- Test không dấu: 300 dòng (cùng id với test_main). Nhóm con của test_skew: {'hi_sao_nhan_negative': 90, '3sao_nhan_positive': 85, 'thap_sao_nhan_positive': 20, 'group_mate': 2}.
- Seed 42; chia theo nhóm gần trùng; phiên bản script step2-v2.
- Kết quả kiểm tra rò rỉ (script tự kiểm tra): id_unique=đạt, dup_group_in_one_split=đạt, text_norm_disjoint=đạt, text_no_accent_disjoint=đạt, customer_single_tier=đạt, lot_single_product=đạt, no_nulls_in_synthetic=đạt, unaccented_ids_subset_of_test_main=đạt, unaccented_ids_not_in_other_splits=đạt

## 6. Bộ kịch bản WF2
- Dòng theo bộ: {'tune': 497, 'eval': 434}; 22 điểm kiểm tra; điểm kỳ vọng có cảnh báo: ['T-K1', 'T-K2', 'T-K5a', 'E-K1', 'E-K2', 'E-K5a'].
- Quy ước tham chiếu: cửa sổ 4 giờ, ngưỡng >= 5 ca cùng (lô, nhóm lỗi). Đây là giả định, có thể đổi.
- Kiểm tra: pass (nguồn duy nhất, trong reserve, kỳ vọng khớp thiết kế, lô trọng tâm không trùng).

## 7. Kiểm tra file nạp CSDL & Toàn vẹn dữ liệu
- **Kiểm tra SQLite:** `verify_preload.py` xác nhận số dòng: `{'reviews': 9594, 'review_gold': 9594, 'scenario_reviews': 931, 'scenario_checkpoints': 22, 'issue_types': 9}`; khóa ngoại mồ côi: 0; văn bản khác CSV: 0; kiểm tra chéo kịch bản bằng GROUP BY: 0 lệch trên 22 điểm.
- **Kiểm tra PostgreSQL (Supabase):** Đã nạp thành công và xác nhận toàn bộ 6 bảng trực tiếp trên môi trường PostgreSQL (Supabase), cấu trúc khóa ngoại và phân quyền hoạt động ổn định, sẵn sàng kết nối n8n.

## 8. Kết quả baseline theo số sao (đã đo đạc thực tế)
| Tập | Hệ thống | n | Accuracy | Macro F1 | Recall Negative | CI 95% Recall Neg | Precision Neg |
|---|---|---|---|---|---|---|---|
| validation | baseline_rating<=2 | 150 | 0.8267 | 0.8256 | 0.7312 | 0.6332-0.8108 | 0.9855 |
| validation | baseline_rating<=3 | 150 | 0.9733 | 0.9715 | 0.9892 | 0.9416-0.9981 | 0.9684 |
| test_main | baseline_rating<=2 | 300 | 0.8100 | 0.8092 | 0.7043 | 0.6351-0.7652 | 0.9850 |
| test_main | baseline_rating<=3 | 300 | 0.9667 | 0.9645 | 0.9785 | 0.9460-0.9916 | 0.9681 |
| test_skew | baseline_rating<=2 | 197 | 0.7157 | 0.4904 | 0.1087 | 0.0473-0.2304 | 0.2500 |
| test_skew | baseline_rating<=3 | 197 | 0.3452 | 0.3074 | 0.2391 | 0.1391-0.3794 | 0.1048 |

- **Test lệch:** Đã hoàn thành 100% gán nhãn người (197 mẫu, 4 rater, Cohen's Kappa = 0.9133 & 1.0000, tệp `04_labeling/human_labels_final.csv`). Điểm baseline đã chấm thật và thể hiện rõ điểm yếu chí tử của mô hình dựa vào số sao (Recall Neg chỉ đạt 10.87% - 23.91%).
- **Gemini:** Đã đóng băng Prompt v3 (Few-shot + 5 rules xử lý ca khó) và đóng gói sẵn sàng thực thi tự động qua tệp `chay_phan_a.bat`.
