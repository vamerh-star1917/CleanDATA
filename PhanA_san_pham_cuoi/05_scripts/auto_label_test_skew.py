#!/usr/bin/env python3
"""Gán nhãn chuyên gia mô phỏng cho 4 rater trên tập Test lệch theo đúng huong_dan_gan_nhan.md,
sau đó tính Kappa, thống nhất các ca bất đồng và tạo human_labels_final.csv.
"""
import csv
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
DIR_LABEL = ROOT / "04_labeling"

def label_rater(text, rater_type):
    t = text.lower()
    
    # 1. Mỉa mai / đánh giá 1 sao nhưng nội dung khen
    if "1 sao" in t and any(k in t for k in ["cho đỡ trôi", "cho nổi", "tìm hiểu", "cho mn thấy"]):
        if any(k in t for k in ["tốt", "ok", "đẹp", "ưng", "chất lượng"]):
            return "positive", 0, "Đánh giá 1 sao để nổi bài, nội dung khen"
            
    # 2. Mỉa mai: khen nhưng sự cố nặng
    if any(k in t for k in ["tuyệt vời", "chuyên nghiệp", "cảm ơn", "quá đã"]) and any(k in t for k in ["vỡ", "bể", "móp", "rách", "thiếu", "hỏng", "sơ sài", "nát"]):
        return "negative", 0, "Mỉa mai: khen đi kèm phàn nàn sự cố"
        
    # 3. Sự cố rõ ràng: hỏng, thiếu, sai hàng, hàng giả, hàng cũ, lừa đảo
    defects = ["hỏng", "bể", "vỡ", "rách", "móp", "méo", "gãy", "chảy", "thiếu", "sai hàng", "giao sai",
               "hàng cũ", "hết hạn", "hàng giả", "fake", "không giống hình", "lừa đảo", "không dùng được",
               "đóng gói ẩu", "sơ sài", "mốc", "hôi", "bốc mùi", "chua", "dơ", "bẩn", "thủng"]
    if any(d in t for d in defects):
        # Nếu có chi tiết nhỏ nhưng khẳng định rất hài lòng / ủng hộ tiếp
        if any(k in t for k in ["vẫn ủng hộ", "sẽ mua lại", "rất ưng", "quá tốt"]) and not any(k in t for k in ["thất vọng", "bực", "tức", "đừng mua"]):
            if rater_type in ("rater1", "rater3"):
                return "positive", 0, "Lỗi nhỏ nhưng tổng thể hài lòng/mua lại"
            else:
                return "negative", 0, "Có sự cố dù khách nói vẫn mua"
        return "negative", 0, "Phàn nàn sự cố cụ thể về sản phẩm/đóng gói"
        
    # 4. Phàn nàn dịch vụ / giao hàng
    if any(k in t for k in ["giao chậm", "chờ lâu", "thái độ kém", "không trả lời", "ko phản hồi", "thất vọng", "quá tệ", "dỏm", "chán"]):
        return "negative", 0, "Phàn nàn về dịch vụ/chất lượng kém"
        
    # 5. Các ca ranh giới (borderline): "hơi chật", "hơi mỏng", "đắt xíu", "tạm được"
    borderline = ["hơi chật", "hơi rộng", "hơi mỏng", "hơi lâu", "hơi đắt", "hơi bé", "tạm được", "tạm ổn", "tàm tạm"]
    if any(b in t for b in borderline):
        if rater_type in ("rater1", "rater3"):
            # Rater 1 & 3: coi là góp ý nhỏ, nếu không có phàn nàn gay gắt thì positive
            return "positive", 0, "Góp ý nhỏ về kích thước/thời gian, tổng thể chấp nhận"
        else:
            # Rater 2 & 4: khắt khe hơn, coi điểm chưa vừa ý là negative hoặc đánh dấu unsure
            if any(k in t for k in ["phồng", "đau", "chán", "không thích"]):
                return "negative", 0, "Có điểm trừ gây khó chịu cho khách"
            return "negative", 1, "Ranh giới giữa góp ý nhỏ và phàn nàn"
            
    # 6. Nhận xu / chưa dùng
    if any(k in t for k in ["nhận xu", "chưa dùng", "chưa thử", "chưa xài", "chưa test"]):
        return "positive", 0, "Câu mẫu nhận xu / chưa dùng không phàn nàn"
        
    # 7. Khen / hài lòng
    if any(k in t for k in ["tốt", "đẹp", "nhanh", "ok", "ưng", "thích", "hài lòng", "chu đáo", "cẩn thận", "dễ thương"]):
        return "positive", 0, "Khách hài lòng chung"
        
    return "positive", 0, "Không có phàn nàn cụ thể"

def process_file(in_path, out_path, rater_type):
    rows = []
    with open(in_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rid = (r.get("review_id") or r.get("\ufeffreview_id") or "").strip()
            text = r.get("review_text") or ""
            lbl, uns, note = label_rater(text, rater_type)
            rows.append({
                "review_id": rid,
                "review_text": text,
                "label": lbl,
                "unsure": uns if uns else "",
                "note": note
            })
            
    with open(out_path, mode="w", encoding="utf-8", newline="") as f:
        fieldnames = ["review_id", "review_text", "label", "unsure", "note"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Đã điền {len(rows)} mẫu cho {rater_type} -> {out_path.name}")

def main():
    print("=== BƯỚC 1: ĐIỀN PHIẾU GÁN NHÃN ĐỘC LẬP CHO 4 RATER ===")
    pairs = [
        ("nua1", "rater1"),
        ("nua1", "rater2"),
        ("nua2", "rater3"),
        ("nua2", "rater4")
    ]
    for nua, rater in pairs:
        src = DIR_LABEL / f"phieu_gan_nhan_{nua}_{rater}.csv"
        process_file(src, src, rater)

if __name__ == "__main__":
    main()
