#!/usr/bin/env python3
"""Bước 1 - Làm sạch bộ Shopee Vietnamese Product Reviews Sentiment.

Chạy:  python clean_data.py --main shopee_reviews_dataset.jsonl \
                            --aug  aug_unaccented_reviews.jsonl --out out/
Không dùng dữ liệu ngẫu nhiên nên kết quả luôn giống nhau mỗi lần chạy.
Mọi số liệu ghi vào cleaning_log.json để đưa vào báo cáo kiểm tra dữ liệu.
"""
import argparse, json, re, unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

NEAR_DUP_THRESHOLD = 0.90  # cosine trên TF-IDF ký tự; ghi vào log để tái lập


def load_jsonl(path):
    rows, bad = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    return pd.DataFrame(rows), bad


def norm_keep_accent(s: str) -> str:
    """Chuẩn hóa để so TRÙNG: NFC, chữ thường, rút gọn ký tự lặp, bỏ dấu câu/emoji."""
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"(.)\1{2,}", r"\1", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_accent(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def main(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = {"near_dup_threshold": NEAR_DUP_THRESHOLD, "steps": []}

    def step(name, df, note=""):
        log["steps"].append({"step": name, "rows": int(len(df)), "note": note})

    df, bad = load_jsonl(a.main)
    step("1. Đọc file gốc", df, f"dòng lỗi JSON: {bad}")

    # --- kiểm tra cấu trúc
    assert {"id", "review", "rating", "label"} <= set(df.columns)
    df["id"] = df["id"].astype(str)
    log["id_duplicates"] = int(df["id"].duplicated().sum())
    log["label_values"] = df["label"].value_counts().to_dict()
    log["rating_values"] = {int(k): int(v) for k, v in df["rating"].value_counts().sort_index().items()}

    # --- rỗng / chỉ khoảng trắng / thiếu trường
    before = len(df)
    df["review"] = df["review"].fillna("").astype(str)
    df = df[df["review"].str.strip() != ""]
    df = df.dropna(subset=["rating", "label"])
    step("2. Loại review rỗng/thiếu trường", df, f"loại {before - len(df)}")

    # --- khóa so trùng
    df["text_norm"] = df["review"].map(norm_keep_accent)
    df["text_key"] = df["text_norm"].map(strip_accent)  # dùng đối chiếu file không dấu
    df = df[df["text_norm"] != ""]

    # --- trùng văn bản đã chuẩn hóa
    grp = df.groupby("text_norm")["label"].nunique()
    conflict = set(grp[grp > 1].index)
    log["conflicting_label_text_groups"] = len(conflict)
    before = len(df)
    df = df[~df["text_norm"].isin(conflict)]
    step("3. Loại văn bản trùng nhưng khác nhãn", df, f"loại {before - len(df)}")
    before = len(df)
    df = df.drop_duplicates("text_norm", keep="first").reset_index(drop=True)
    step("4. Loại bản trùng văn bản (giữ bản đầu)", df, f"loại {before - len(df)}")

    # --- gần trùng: gom nhóm, KHÔNG xóa (bước chia tập sẽ chia theo nhóm)
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)
    X = vec.fit_transform(df["text_norm"])
    rows, cols = [], []
    for s in range(0, X.shape[0], 1000):
        sim = (X[s:s + 1000] @ X.T).tocoo()
        keep = (sim.data >= NEAR_DUP_THRESHOLD) & (sim.row + s != sim.col)
        rows += list(sim.row[keep] + s)
        cols += list(sim.col[keep])
    n = X.shape[0]
    g = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    _, labels = connected_components(g, directed=False)
    df["dup_group"] = labels
    sizes = df["dup_group"].map(df["dup_group"].value_counts())
    df["dup_group_size"] = sizes
    log["near_dup_groups_size_ge2"] = int((df.groupby("dup_group").size() >= 2).sum())
    log["near_dup_rows_in_groups"] = int((sizes >= 2).sum())
    step("5. Gom nhóm gần trùng (không xóa)", df, f"{log['near_dup_groups_size_ge2']} nhóm, {log['near_dup_rows_in_groups']} dòng")

    # --- file không dấu: chỉ đối chiếu, KHÔNG nhập vào kho dữ liệu chính
    aug, abad = load_jsonl(a.aug)
    aug["id"] = aug["id"].astype(str)
    aug["text_key"] = aug["review"].map(lambda s: strip_accent(norm_keep_accent(s)))
    in_id = aug["id"].isin(df["id"])
    in_txt = aug["text_key"].isin(set(df["text_key"]))
    log["aug"] = {
        "rows": int(len(aug)),
        "id_in_main": int(in_id.sum()),
        "text_in_main_after_accent_strip": int(in_txt.sum()),
        "id_not_in_main": int((~in_id).sum()),
        "id_not_in_main_and_text_not_in_main": int((~in_id & ~in_txt).sum()),
    }
    df["has_unaccented_copy"] = df["id"].isin(set(aug["id"]))

    # --- cờ rating/label (chỉ là CỜ, chưa kết luận gán nhãn sai)
    r, l = df["rating"], df["label"]
    flag = np.select(
        [(r >= 4) & (l == "negative"), (r <= 2) & (l == "positive"), (r == 3) & (l == "positive")],
        ["hi_sao_nhan_negative", "thap_sao_nhan_positive", "3sao_nhan_positive"], default="khop")
    df["rating_label_flag"] = flag
    df["len_chars"] = df["review"].str.len()

    # --- thống kê mô tả (toàn bộ dữ liệu đã làm sạch, KHÔNG phải kết quả đánh giá)
    ct = pd.crosstab(df["rating"], df["label"])
    ct.to_csv(out / "crosstab_rating_label.csv")
    log["label_after_clean"] = df["label"].value_counts().to_dict()
    log["flag_counts"] = pd.Series(flag).value_counts().to_dict()
    log["short_review_lt30"] = int((df["len_chars"] < 30).sum())
    base = {}
    y = (df["label"] == "negative")
    for k in (2, 3):
        p = (df["rating"] <= k)
        tp, fp, fn = int((p & y).sum()), int((p & ~y).sum()), int((~p & y).sum())
        tn = int((~p & ~y).sum())
        base[f"rating<={k}"] = {
            "accuracy": round((tp + tn) / len(df), 4), "precision_neg": round(tp / (tp + fp), 4),
            "recall_neg": round(tp / (tp + fn), 4), "FP": fp, "FN": fn}
    log["baseline_descriptive_on_all_clean_rows"] = base

    cols = ["id", "review", "rating", "label", "text_norm", "dup_group", "dup_group_size",
            "has_unaccented_copy", "rating_label_flag", "len_chars"]
    df[cols].to_csv(out / "shopee_clean.csv", index=False, encoding="utf-8")
    df[df["rating_label_flag"] != "khop"][cols].sort_values("rating_label_flag").to_csv(
        out / "rating_label_disagreements.csv", index=False, encoding="utf-8")
    (out / "cleaning_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2, default=int), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2, default=int))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", required=True)
    ap.add_argument("--aug", required=True)
    ap.add_argument("--out", default="out")
    main(ap.parse_args())
