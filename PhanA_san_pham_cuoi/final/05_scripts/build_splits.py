#!/usr/bin/env python3
"""Bước 2 - Sinh trường giả lập + chia tập + Test không dấu + kiểm tra rò rỉ.

Chạy:  python build_splits.py --clean ../step1_clean/shopee_clean.csv --out out/
Toàn bộ trường giả lập sinh bằng HÀM BĂM (seed + khóa) nên không phụ thuộc thứ tự dòng.
Chia tập theo dup_group (nhóm gần trùng) để các bản gần giống nhau không bị tách sang tập khác.
Tham số có thể đổi bằng CLI; cấu hình thực tế ghi vào config_step2.json.
"""
import argparse, hashlib, json, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_VERSION = "step2-v2"
# Trọng số theo giờ (0-23): thấp ban đêm, đỉnh trưa và tối - chỉ là giả lập, ghi trong data dictionary
HOUR_W = [1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 8, 6, 5, 5, 6, 7, 8, 9, 9, 8, 5, 2]
PUNCT = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "..."})


# ---------- tiện ích ----------
def u(key: str, seed: int) -> float:
    """Số thực [0,1) xác định từ (seed, key)."""
    h = hashlib.sha256(f"{seed}|{key}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def unaccent(s: str) -> str:
    """Bỏ dấu tiếng Việt, bỏ emoji/ký tự ngoài ASCII (tái tạo ~99% file aug gốc; emoji bị bỏ thay vì phiên âm)."""
    s = s.replace("₫", "D").replace("đ", "d").replace("Đ", "D").translate(PUNCT)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.encode("ascii", "ignore").decode("ascii")


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------- trường giả lập ----------
def add_synthetic(df, a):
    seed = a.seed
    n_lots = a.n_products * a.lots_per_product
    cust = [int(u(i + "|cust", seed) * a.n_customers) for i in df["id"]]
    df["customer_id"] = [f"C{c:05d}" for c in cust]
    df["customer_tier"] = ["VIP" if u(c + "|tier", seed) < a.vip_ratio else "Regular" for c in df["customer_id"]]
    lot = [int(u(i + "|lot", seed) * n_lots) for i in df["id"]]
    prod = [l // a.lots_per_product for l in lot]
    df["product_id"] = [f"P{p + 1:02d}" for p in prod]
    df["lot_id"] = [f"L{p + 1:02d}-{(l % a.lots_per_product) + 1}" for p, l in zip(prod, lot)]
    cdf = np.cumsum(HOUR_W) / sum(HOUR_W)
    tz = timezone(timedelta(hours=7))
    start = datetime.fromisoformat(a.start_date).replace(tzinfo=tz)
    ts = []
    for i in df["id"]:
        day = int(u(i + "|day", seed) * a.days)
        hour = int(np.searchsorted(cdf, u(i + "|hour", seed), side="right"))
        hour = min(hour, 23)
        mi, se = int(u(i + "|min", seed) * 60), int(u(i + "|sec", seed) * 60)
        ts.append((start + timedelta(days=day, hours=hour, minutes=mi, seconds=se)).isoformat())
    df["created_at"] = ts
    return df


# ---------- chia tập theo nhóm ----------
def draw(pool, targets, rng):
    """Chọn nhóm cho đến khi đủ số dòng mỗi lớp (cho phép vượt nhẹ do kích thước nhóm)."""
    chosen = []
    for lab, t in targets.items():
        g = pool[pool["label"] == lab].sort_index()
        for gid in rng.permutation(g.index.to_numpy()):
            tot = sum(int(pool.at[c, "size"]) for c in chosen if pool.at[c, "label"] == lab)
            if tot >= t:
                break
            sz = int(g.at[gid, "size"])
            if sz > 1 and tot + sz > t + 3:
                continue
            chosen.append(gid)
    return chosen


def split(df, a):
    grp = df.groupby("dup_group").agg(
        size=("id", "size"),
        label=("label", lambda x: x.mode().iat[0]),
        flagged=("rating_label_flag", lambda x: bool((x != "khop").any())))
    share = df["label"].value_counts(normalize=True)
    assign = {}
    avail = grp.copy()

    def take(name, gids):
        nonlocal avail
        for g in gids:
            assign[g] = name
        avail = avail.drop(index=gids)

    # 1) Test chính: ngẫu nhiên, phân tầng theo nhãn, lấy từ TOÀN BỘ dữ liệu (đúng đề xuất)
    t = {l: round(a.n_test_main * share[l]) for l in share.index}
    take("test_main", draw(avail, t, np.random.default_rng([a.seed, 1])))
    # 2) Validation: ngẫu nhiên theo tỷ lệ tự nhiên, lấy TRƯỚC khi gom ca lệch để Validation giữ đúng tỷ lệ nhiễu nhãn tự nhiên
    t = {l: round(a.n_val * share[l]) for l in share.index}
    take("validation", draw(avail, t, np.random.default_rng([a.seed, 2])))
    # 3) Test lệch: mọi nhóm còn lại có dòng rating-label bất đồng
    take("test_skew", list(avail[avail["flagged"]].index))
    # 4) Kho few-shot: cân bằng nhãn
    t = {"negative": a.n_fewshot // 2, "positive": a.n_fewshot - a.n_fewshot // 2}
    take("few_shot_pool", draw(avail, t, np.random.default_rng([a.seed, 3])))
    df["split"] = df["dup_group"].map(assign).fillna("reserve")
    # nhóm con của Test lệch
    df["skew_group"] = np.where(df["split"] == "test_skew",
                                np.where(df["rating_label_flag"] != "khop", df["rating_label_flag"], "group_mate"), "")
    return df


# ---------- kiểm tra rò rỉ ----------
def unaccent_key(s):  # khóa so trùng không phân biệt dấu
    import re
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"(.)\1{2,}", r"\1", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", unaccent(s)).strip()


def verify(df, tu):
    res = {}
    res["id_unique"] = bool(df["id"].is_unique)
    res["dup_group_in_one_split"] = bool((df.groupby("dup_group")["split"].nunique() == 1).all())
    evalsets = ["test_main", "test_skew", "validation", "few_shot_pool"]
    sub = df[df["split"].isin(evalsets)]
    res["text_norm_disjoint"] = bool((sub.groupby("text_norm")["split"].nunique() == 1).all())
    key = sub["review"].map(unaccent_key)
    res["text_no_accent_disjoint"] = bool((sub.assign(k=key).groupby("k")["split"].nunique() == 1).all())
    res["customer_single_tier"] = bool((df.groupby("customer_id")["customer_tier"].nunique() == 1).all())
    res["lot_single_product"] = bool((df.groupby("lot_id")["product_id"].nunique() == 1).all())
    res["no_nulls_in_synthetic"] = bool(df[["customer_id", "customer_tier", "product_id", "lot_id", "created_at"]].notna().all().all())
    tm = set(df.loc[df["split"] == "test_main", "id"])
    res["unaccented_ids_subset_of_test_main"] = bool(set(tu["id"]) <= tm)
    res["unaccented_ids_not_in_other_splits"] = bool(not (set(tu["id"]) & set(df.loc[df["split"] != "test_main", "id"])))
    failed = [k for k, v in res.items() if not v]
    assert not failed, f"KIỂM TRA THẤT BẠI: {failed}"
    return res


def main(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rep_dir = Path(a.report_dir) if a.report_dir else out
    rep_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(a.clean, dtype={"id": str}).sort_values("id").reset_index(drop=True)
    df = add_synthetic(df, a)
    df = split(df, a)

    # Test không dấu: bản không dấu sinh tự động từ chính các dòng Test chính
    tu = df[df["split"] == "test_main"][["id", "review", "label"]].copy()
    tu["review_unaccented"] = tu["review"].map(unaccent)
    tu = tu[tu["review_unaccented"].str.strip() != ""][["id", "review_unaccented"]]
    # đối chiếu hàm bỏ dấu với file aug gốc (chỉ để ghi nhận độ tin cậy của phép biến đổi)
    check = {}
    if a.aug:
        aug = pd.DataFrame([json.loads(l) for l in open(a.aug, encoding="utf-8") if l.strip()])
        aug["id"] = aug["id"].astype(str)
        n = lambda s: s.str.split().str.join(" ")
        j = aug.merge(df[["id", "review"]], on="id", suffixes=("_aug", "_main"))
        check = {"aug_rows_with_matching_id": int(len(j)),
                 "unaccent_fn_reproduces_aug": int((n(j["review_main"].map(unaccent)) == n(j["review_aug"])).sum())}

    res = verify(df, tu)

    master = df[["id", "review", "rating", "customer_id", "customer_tier", "product_id", "lot_id", "created_at"]]
    master = master.rename(columns={"id": "review_id", "review": "review_text"})
    gold = df[["id", "label", "rating_label_flag", "split", "skew_group", "dup_group"]].rename(
        columns={"id": "review_id", "label": "label_original"})
    master.to_csv(out / "reviews.csv", index=False, encoding="utf-8")
    gold.to_csv(out / "review_gold.csv", index=False, encoding="utf-8")
    tu.rename(columns={"id": "review_id"}).to_csv(out / "test_unaccented.csv", index=False, encoding="utf-8")

    rep = {
        "script_version": SCRIPT_VERSION,
        "params": {k: v for k, v in vars(a).items() if k not in ("clean", "aug", "out")},
        "input_sha256": sha256_file(a.clean),
        "rows_total": int(len(df)),
        "split_counts": df["split"].value_counts().to_dict(),
        "label_by_split": {s: g["label"].value_counts().to_dict() for s, g in df.groupby("split")},
        "rating_by_split": {s: {int(k): int(v) for k, v in g["rating"].value_counts().sort_index().items()} for s, g in df.groupby("split")},
        "skew_subgroups": df[df["split"] == "test_skew"]["skew_group"].value_counts().to_dict(),
        "vip_ratio_by_split": {s: round(float((g["customer_tier"] == "VIP").mean()), 3) for s, g in df.groupby("split")},
        "n_customers_used": int(df["customer_id"].nunique()), "n_lots_used": int(df["lot_id"].nunique()),
        "created_at_min": df["created_at"].min(), "created_at_max": df["created_at"].max(),
        "test_unaccented_rows": int(len(tu)),
        "unaccent_function_vs_aug_file": check,
        "verification": res,
    }
    (rep_dir / "split_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", required=True)
    ap.add_argument("--aug", default=None, help="file aug gốc, chỉ dùng để đối chiếu hàm bỏ dấu")
    ap.add_argument("--out", default="out")
    ap.add_argument("--report-dir", dest="report_dir", default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-test-main", dest="n_test_main", type=int, default=300)
    ap.add_argument("--n-val", dest="n_val", type=int, default=150)
    ap.add_argument("--n-fewshot", dest="n_fewshot", type=int, default=60)
    ap.add_argument("--n-customers", dest="n_customers", type=int, default=5000)
    ap.add_argument("--vip-ratio", dest="vip_ratio", type=float, default=0.20)
    ap.add_argument("--n-products", dest="n_products", type=int, default=10)
    ap.add_argument("--lots-per-product", dest="lots_per_product", type=int, default=3)
    ap.add_argument("--start-date", dest="start_date", default="2026-10-01")
    ap.add_argument("--days", type=int, default=30)
    main(ap.parse_args())
