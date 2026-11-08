#!/usr/bin/env python3
"""Gộp phiếu gán nhãn đã điền, tính Cohen's kappa cho từng cặp, xuất danh sách bất đồng để thống nhất.
Bước 1: python compute_kappa.py --dir ../04_labeling      -> kappa + to_reconcile.csv
Bước 2: điền cột final_label trong to_reconcile.csv (hai người bàn bạc), rồi chạy lại với --finalize
        -> human_labels_final.csv (cột review_id, label_human) dùng cho evaluate.py --human
Quy ước: label chỉ nhận positive|negative; ô trống hoặc unsure=1 được đưa vào danh sách thống nhất, và KHÔNG tính vào kappa.
"""
import argparse
import csv
import math
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

LAB = {"positive", "negative"}

def kappa(x, y):
    n = len(x)
    if n == 0:
        return float("nan"), float("nan")
    po = sum(a == b for a, b in zip(x, y)) / n
    pe = sum((sum(a == c for a in x) / n) * (sum(b == c for b in y) / n) for c in LAB)
    return (float("nan") if pe == 1 else (po - pe) / (1 - pe)), po

def load(p):
    data = {}
    with open(p, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rid = (r.get("review_id") or r.get("\ufeffreview_id") or "").strip()
            if rid:
                lbl = (r.get("label") or "").strip().lower()
                unsure = (r.get("unsure") or "").strip()
                text = r.get("review_text") or ""
                note = r.get("note") or ""
                data[rid] = {"review_id": rid, "review_text": text, "label": lbl, "unsure": unsure, "note": note}
    return data

def main(a):
    D = Path(a.dir); rep = []; recon = []
    for name, (r1, r2) in {"nua1": ("rater1", "rater2"), "nua2": ("rater3", "rater4")}.items():
        p1, p2 = D / f"phieu_gan_nhan_{name}_{r1}.csv", D / f"phieu_gan_nhan_{name}_{r2}.csv"
        A, B = load(p1), load(p2)
        ids = [i for i in A if i in B]
        ok = [i for i in ids if A[i]["label"] in LAB and B[i]["label"] in LAB and str(A[i]["unsure"]) != "1" and str(B[i]["unsure"]) != "1"]
        if ok:
            k, po = kappa([A[i]["label"] for i in ok], [B[i]["label"] for i in ok])
            rep.append({"cap": f"{r1}-{r2}", "n_total": len(ids), "n_tinh_kappa": len(ok), "ti_le_dong_y": round(po, 4), "cohen_kappa": round(k, 4)})
        for i in ids:
            la, lb = A[i]["label"], B[i]["label"]
            if la != lb or la not in LAB or str(A[i]["unsure"]) == "1" or str(B[i]["unsure"]) == "1":
                recon.append({"review_id": i, "review_text": A[i]["review_text"], "label_a": la, "label_b": lb, "final_label": "", "ly_do": ""})
    
    # Ghi kappa_report.csv
    rep_path = D / "kappa_report.csv"
    with open(rep_path, mode="w", encoding="utf-8", newline="") as f:
        if rep:
            writer = csv.DictWriter(f, fieldnames=list(rep[0].keys()))
            writer.writeheader()
            writer.writerows(rep)
            for row in rep:
                print(row)
    
    rc = D / "to_reconcile.csv"
    if not a.finalize:
        with open(rc, mode="w", encoding="utf-8-sig", newline="") as f:
            fieldnames = ["review_id", "review_text", "label_a", "label_b", "final_label", "ly_do"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(recon)
        print("Số ca cần thống nhất:", len(recon), "->", rc)
        return
    
    # Đọc to_reconcile.csv khi finalize
    fin_map = {}
    with open(rc, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rid = (r.get("review_id") or "").strip()
            fl = (r.get("final_label") or "").strip().lower()
            assert fl in LAB, f"Ca {rid} chưa có final_label hợp lệ ({fl})"
            fin_map[rid] = fl
            
    out = []
    for name, (r1, r2) in {"nua1": ("rater1", "rater2"), "nua2": ("rater3", "rater4")}.items():
        A = load(D / f"phieu_gan_nhan_{name}_{r1}.csv")
        B = load(D / f"phieu_gan_nhan_{name}_{r2}.csv")
        for i in [k for k in A if k in B]:
            out.append({"review_id": i, "label_human": fin_map.get(i, A[i]["label"])})
            
    out_path = D / "human_labels_final.csv"
    with open(out_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["review_id", "label_human"])
        writer.writeheader()
        writer.writerows(out)
    print("Đã ghi", len(out), "nhãn người ->", out_path)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent / "04_labeling"))
    ap.add_argument("--finalize", action="store_true")
    main(ap.parse_args())

