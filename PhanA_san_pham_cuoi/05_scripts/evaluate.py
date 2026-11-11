#!/usr/bin/env python3
"""Đánh giá phân loại Positive/Negative trên các tập, so với hai baseline theo số sao.

Chạy chỉ baseline:   python evaluate.py --out ../06_reports
Chạy kèm dự đoán:     python evaluate.py --pred ../06_reports/predictions/pred_*.csv --out ../06_reports
Test lệch cần nhãn người:  thêm --human human_labels_final.csv  (cột review_id, label_human)

Quy ước đã cố định TRƯỚC khi có kết quả Test:
- Lớp dương tính khi tính Recall Negative là 'negative'. Macro F1 = trung bình F1 hai lớp.
- Ca dự đoán lỗi (status != ok) mặc định tính là SAI (--invalid-policy wrong); --invalid-policy drop để loại khỏi mẫu. Luôn báo cáo số ca lỗi.
- Baseline: rating <= 2 là negative, và rating <= 3 là negative (báo cáo cả hai).
- Test chính/Validation chấm theo nhãn gốc; Test lệch chấm theo NHÃN NGƯỜI (không chấm theo nhãn gốc).
- Kết quả MOCK bị từ chối trừ khi có --allow-mock, và file xuất mang tiền tố MOCK_.
"""
import argparse, glob, json, math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parent.parent
NEG, POS = "negative", "positive"


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(c - h, 4), round(c + h, 4)


def metrics(gold, pred):
    """gold, pred: Series nhãn (pred có thể là '' = không có dự đoán hợp lệ, đã xử lý trước)."""
    g, p = np.array(gold), np.array(pred)
    n = len(g)
    cm = {(a, b): int(((g == a) & (p == b)).sum()) for a in (NEG, POS) for b in (NEG, POS)}
    out = {"n": n, "n_negative": int((g == NEG).sum()), "n_positive": int((g == POS).sum())}
    out["accuracy"] = round((cm[(NEG, NEG)] + cm[(POS, POS)]) / n, 4) if n else float("nan")
    f1s = []
    for c, o in ((NEG, POS), (POS, NEG)):
        tp, fp, fn = cm[(c, c)], cm[(o, c)], cm[(c, o)]
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        out[f"precision_{c}"], out[f"recall_{c}"], out[f"f1_{c}"] = round(pr, 4), round(rc, 4), round(f1, 4)
        f1s.append(f1)
    out["macro_f1"] = round(sum(f1s) / 2, 4)
    lo, hi = wilson(cm[(NEG, NEG)], cm[(NEG, NEG)] + cm[(NEG, POS)])
    out["recall_negative_ci95_lo"], out["recall_negative_ci95_hi"] = lo, hi
    out.update({"TN_neg_as_neg": cm[(NEG, NEG)], "FN_neg_as_pos": cm[(NEG, POS)],
                "FP_pos_as_neg": cm[(POS, NEG)], "TP_pos_as_pos": cm[(POS, POS)]})
    return out, cm


def plot_cm(cm, title, path):
    arr = np.array([[cm[(NEG, NEG)], cm[(NEG, POS)]], [cm[(POS, NEG)], cm[(POS, POS)]]])
    fig, ax = plt.subplots(figsize=(4.2, 3.6), dpi=150)
    ax.imshow(arr, cmap="Blues")
    for i in range(2):
        for j in range(2):
            row = arr[i].sum()
            pct = f"\n({arr[i, j] / row:.0%} hàng)" if row else ""
            ax.text(j, i, f"{arr[i, j]}{pct}", ha="center", va="center", fontsize=12,
                    color="white" if arr[i, j] > arr.max() / 2 else "black")
    ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
    ax.set_xticklabels(["Dự đoán\nnegative", "Dự đoán\npositive"]); ax.set_yticklabels(["Thực tế\nnegative", "Thực tế\npositive"])
    ax.set_title(title, fontsize=9)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def mcnemar_p(correct_a, correct_b):
    b = int((correct_a & ~correct_b).sum()); c = int((~correct_a & correct_b).sum())
    return round(binomtest(b, b + c, 0.5).pvalue, 4) if b + c else 1.0


def main(a):
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rv = pd.read_csv(a.reviews, dtype={"review_id": str})
    gd = pd.read_csv(a.gold, dtype={"review_id": str})
    d = rv.merge(gd, on="review_id")
    if a.human:
        h = pd.read_csv(a.human, dtype={"review_id": str})[["review_id", "label_human"]]
        d = d.merge(h, on="review_id", how="left")
    else:
        d["label_human"] = np.nan
    # tập và nhãn chuẩn dùng để chấm
    sets = {"validation": d[d["split"] == "validation"].assign(gold=lambda x: x["label_original"]),
            "test_main": d[d["split"] == "test_main"].assign(gold=lambda x: x["label_original"]),
            "test_unaccented": None,
            "test_skew": d[(d["split"] == "test_skew") & d["label_human"].notna()].assign(gold=lambda x: x["label_human"])}
    tm = sets["test_main"]
    tu = pd.read_csv(a.unaccented, dtype={"review_id": str})
    sets["test_unaccented"] = tm[tm["review_id"].isin(tu["review_id"])]
    notes = []
    if len(sets["test_skew"]) == 0:
        notes.append("test_skew: CHƯA có nhãn người (--human) nên chưa chấm. Không dùng nhãn gốc để chấm Test lệch.")

    preds = []
    for pattern in a.pred or []:
        for f in sorted(glob.glob(pattern)):
            p = pd.read_csv(f, dtype={"review_id": str}).fillna({"label_pred": "", "status": ""})
            if (p["model"] == "MOCK-HEURISTIC").any() and not a.allow_mock:
                raise SystemExit(f"{f} là kết quả MOCK; chỉ chạy với --allow-mock để thử pipeline.")
            preds.append(p)
    rows, err_files = [], []
    for sname, sd in sets.items():
        if sd is None or len(sd) == 0:
            continue
        systems = {}
        if sname != "test_unaccented":  # baseline dùng số sao nên không áp dụng cho bản không dấu
            systems["baseline_rating<=2"] = sd.assign(pred=np.where(sd["rating"] <= 2, NEG, POS), status="ok")
            systems["baseline_rating<=3"] = sd.assign(pred=np.where(sd["rating"] <= 3, NEG, POS), status="ok")
        for p in preds:
            pp = p[p["split"] == sname]
            if pp.empty:
                continue
            key = f"{pp['model'].iat[0]}|{pp['prompt_version'].iat[0]}|{pp['run_id'].iat[0]}"
            m = sd.merge(pp[["review_id", "label_pred", "status", "reason", "issue_type"]], on="review_id", how="left")
            m["status"] = m["status"].fillna("missing")
            m["pred"] = m["label_pred"].fillna("")
            systems[key] = m
        correct = {}
        for sysname, m in systems.items():
            bad = m["status"] != "ok"
            if a.invalid_policy == "drop":
                mm = m[~bad]
                p_ = mm["pred"]
            else:
                mm = m
                p_ = np.where(bad | ~mm["pred"].isin([NEG, POS]), np.where(mm["gold"] == NEG, POS, NEG), mm["pred"])
            res, cm = metrics(mm["gold"], p_)
            res.update({"split": sname, "system": ("MOCK_" if "MOCK" in sysname else "") + sysname,
                        "invalid_or_missing": int(bad.sum()), "invalid_policy": a.invalid_policy})
            correct[sysname] = pd.Series(np.array(mm["gold"]) == np.array(p_), index=mm["review_id"].to_numpy())
            rows.append(res)
            safe = (sysname.replace("|", "_").replace("<=", "le").replace("/", "-"))
            plot_cm(cm, f"{sname} - {res['system']}\n(n={res['n']})", out / f"confusion_{sname}__{safe}.png")
            e = mm.assign(pred_used=p_)
            e = e[e["gold"].to_numpy() != np.array(p_)]
            cols = [c for c in ["review_id", "review_text", "rating", "gold", "pred_used", "status", "issue_type", "reason"] if c in e.columns]
            e = e[cols].copy(); e["error_category"] = ""; e["notes"] = ""
            e.to_csv(out / f"errors_{sname}__{safe}.csv", index=False, encoding="utf-8")
        # McNemar giữa từng hệ thống dự đoán và hai baseline (cùng các mẫu)
        for r in rows:
            if r["split"] != sname or r["system"].startswith("baseline"):
                continue
            k = [s for s in correct if ("MOCK_" if "MOCK" in s else "") + s == r["system"]][0]
            for bl in ("baseline_rating<=2", "baseline_rating<=3"):
                if bl in correct:
                    idx = correct[k].index.intersection(correct[bl].index)
                    r[f"mcnemar_p_vs_{bl.split('_')[1]}"] = mcnemar_p(correct[k][idx], correct[bl][idx])
    df = pd.DataFrame(rows)
    front = ["split", "system", "n", "n_negative", "n_positive", "accuracy", "macro_f1", "recall_negative", "recall_negative_ci95_lo",
             "recall_negative_ci95_hi", "precision_negative", "f1_negative", "precision_positive", "recall_positive", "f1_positive",
             "TN_neg_as_neg", "FN_neg_as_pos", "FP_pos_as_neg", "TP_pos_as_pos", "invalid_or_missing", "invalid_policy"]
    df = df[[c for c in front if c in df.columns] + [c for c in df.columns if c not in front]]
    prefix = "MOCK_" if (df["system"].str.startswith("MOCK_").any()) else ""
    df.to_csv(out / f"{prefix}metrics.csv", index=False, encoding="utf-8")
    # độ nhất quán giữa các lần chạy cùng cấu hình
    cons = []
    if preds:
        allp = pd.concat(preds)
        for (mdl, pv, sp), g in allp.groupby(["model", "prompt_version", "split"]):
            runs = sorted(g["run_id"].unique())
            for i in range(len(runs)):
                for j in range(i + 1, len(runs)):
                    x = g[g["run_id"] == runs[i]].set_index("review_id")["label_pred"]
                    y = g[g["run_id"] == runs[j]].set_index("review_id")["label_pred"]
                    ids = x.index.intersection(y.index)
                    ag = float((x[ids] == y[ids]).mean()) if len(ids) else float("nan")
                    cons.append({"model": mdl, "prompt_version": pv, "split": sp, "run_a": runs[i], "run_b": runs[j],
                                 "n_common": len(ids), "label_agreement": round(ag, 4)})
    if cons:
        pd.DataFrame(cons).to_csv(out / f"{prefix}consistency.csv", index=False, encoding="utf-8")
    (out / f"{prefix}evaluate_notes.json").write_text(json.dumps({"notes": notes, "invalid_policy": a.invalid_policy}, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.set_option("display.width", 220)
    print(df[["split", "system", "n", "accuracy", "macro_f1", "recall_negative", "recall_negative_ci95_lo", "recall_negative_ci95_hi", "precision_negative"]].to_string(index=False))
    for n in notes:
        print("LƯU Ý:", n)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviews", default=str(ROOT / "01_data" / "reviews.csv"))
    ap.add_argument("--gold", default=str(ROOT / "01_data" / "review_gold.csv"))
    ap.add_argument("--unaccented", default=str(ROOT / "01_data" / "test_unaccented.csv"))
    ap.add_argument("--pred", nargs="*", default=None)
    ap.add_argument("--human", default=None)
    ap.add_argument("--invalid-policy", dest="invalid_policy", choices=["wrong", "drop"], default="wrong")
    ap.add_argument("--allow-mock", dest="allow_mock", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "06_reports"))
    main(ap.parse_args())
