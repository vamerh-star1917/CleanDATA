#!/usr/bin/env python3
"""Script test bắn dữ liệu mẫu vào n8n Webhook Trigger (CRM Workflow).
Hỗ trợ kiểm tra cả 2 trường hợp:
1. Đánh giá tiêu cực của khách VIP (kích hoạt Claude VIP + Alert Telegram).
2. Đánh giá tích cực (kích hoạt nhánh Positive -> lưu DB).
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Dữ liệu mẫu tiêu cực của khách VIP (Sữa bị bể do đóng gói)
SAMPLE_VIP_NEGATIVE = {
    "review_id": "10464410783",
    "review_text": "Nên bọc chống sốc cho khách chứ k may sữa bị bể rất mất thời gian",
    "rating": 1,
    "customer_id": "C02286",
    "customer_name": "Nguyễn Văn VIP",
    "customer_tier": "VIP",
    "product_id": "P09",
    "lot_id": "L09-1",
    "created_at": "2026-10-27T00:26:56+07:00"
}

# Dữ liệu mẫu tích cực của khách Regular
SAMPLE_REGULAR_POSITIVE = {
    "review_id": "10466418455",
    "review_text": "Màu sắc: các màu. Quần cotton, co giãn tốt, hàng đẹp. Shop gửi hàng nhanh, chu đáo.",
    "rating": 5,
    "customer_id": "C03963",
    "customer_name": "Trần Thị Khách",
    "customer_tier": "Regular",
    "product_id": "P05",
    "lot_id": "L05-2",
    "created_at": "2026-10-23T16:45:15+07:00"
}

def send_payload(url, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[THÀNH CÔNG] HTTP {resp.status} - Đã bắn payload vào Webhook:")
            print(f"  Review ID: {payload['review_id']} | Khách: {payload['customer_name']} ({payload['customer_tier']}) | Số sao: {payload['rating']}")
    except urllib.error.HTTPError as e:
        print(f"[LỖI HTTP {e.code}] {e.reason}")
    except Exception as e:
        print(f"[LỖI KẾT NỐI] {e}")

def main():
    parser = argparse.ArgumentParser(description="Test n8n Webhook Trigger")
    parser.add_argument("--url", default="https://vamerg.app.n8n.cloud/webhook-test/crm-webhook-input", help="n8n Webhook URL")
    parser.add_argument("--type", choices=["vip", "pos", "both"], default="vip", help="Loại review mẫu để gửi")
    args = parser.parse_args()

    print(f"Đang gửi dữ liệu tới n8n Webhook: {args.url}\n")
    if args.type in ["vip", "both"]:
        print("--> Đang gửi mẫu: VIP Negative Review...")
        send_payload(args.url, SAMPLE_VIP_NEGATIVE)
        print()

    if args.type in ["pos", "both"]:
        print("--> Đang gửi mẫu: Regular Positive Review...")
        send_payload(args.url, SAMPLE_REGULAR_POSITIVE)
        print()

if __name__ == "__main__":
    main()
