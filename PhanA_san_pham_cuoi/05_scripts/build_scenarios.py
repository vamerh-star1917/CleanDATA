#!/usr/bin/env python3
"""Dựng bộ dữ liệu kịch bản cho WF2 (cảnh báo cụm lỗi theo lô) - hai bộ riêng: tune và eval.

Chạy: python build_scenarios.py --master reviews_master.csv --gold review_gold.csv \
        --fewshot ../03_prompt/fewshot_examples.json --out ../02_scenarios/
Nguồn review: CHỈ lấy từ tập `reserve` (tách biệt với Validation/Test/few-shot), mỗi review dùng tối đa một lần.
Quy ước tham chiếu (giả định, V3 có thể đổi): cửa sổ 4 giờ, ngưỡng >= 5 ca cùng (lô, nhóm lỗi) trong một cửa sổ.
expected_alert được TÍNH từ dữ liệu sinh ra (không viết tay) và được assert với thiết kế.
"""
import argparse, hashlib, json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

TZ = timezone(timedelta(hours=7))
TPL = re.compile(r"[A-Za-zÀ-ỹ/\s]{2,35}:[^\s]*")  # trường mẫu Shopee, ví dụ "Bao bì/Mẫu mã:đẹp"

DMG = re.compile(r"(móp|méo|rách|vỡ|bể|nát|dập|hở|rò rỉ|chảy|trầy|bẹp|thủng|toác|bục|xẹp|tràn)")
CONT = re.compile(r"(hộp|bao bì|túi|gói|chai|lọ|nắp|vỏ|thùng|đóng gói|tuýp|bịch|lon|tem|bọc|seal|vòi)")
NEG = re.compile(r"(không|ko|k|chưa|chẳng|hok|hông|đâu có)\s+(bị\s+|có\s+|hề\s+|thấy\s+|hư\s+)?$")
SUB = {  # nhóm cách diễn đạt của lỗi bao bì (để K1 dùng một kiểu, K2 dùng nhiều kiểu)
    "mop": re.compile(r"(móp|méo|bẹp|xẹp|dập)"),
    "rach": re.compile(r"(rách|toác|thủng|bục|hở)"),
    "vo": re.compile(r"(vỡ|bể|nát)"),
    "chay": re.compile(r"(chảy|tràn|rò rỉ)"),
}
ISSUE_RULES = [  # THỨ TỰ ƯU TIÊN; quy tắc từ khóa, chỉ là ước lượng
    ("wrong_or_missing_item", r"(thiếu|giao sai|gửi sai|nhầm (hàng|sản phẩm|màu|size)|không (có )?quà|không được tặng|ko (có )?quà|không tặng|ko tặng|không kèm|ko kèm)"),
    ("delivery_issue", r"(giao (hàng )?(chậm|lâu|trễ)|ship (chậm|lâu)|chờ (lâu|mãi)|chưa (nhận|giao)|shipper)"),
    ("not_as_described", r"(không giống|ko giống|khác (với )?(hình|mô tả|quảng cáo|ảnh)|không đúng (mô tả|hình)|sai (mô tả|size|màu)|hàng (giả|fake)|hàng cũ|đã qua sử dụng)"),
    ("service_issue", r"(thái độ|không (trả lời|phản hồi)|ko (trả lời|rep|phản hồi)|cskh|chăm sóc khách|bảo hành|hoàn (tiền|đơn))"),
    ("product_defect", r"(hỏng|lỗi|không (dùng|xài) được|ko (dùng|xài) được|gãy|không hoạt động)"),
    ("poor_quality", r"(kém|tệ|dở|không tốt|ko tốt|mỏng|hôi|thối|mùi (lạ|khó)|phai|nhăn|rít|ngứa|dị ứng|không hiệu quả|hết hạn|cận date)"),
]
ISSUE_RULES = [(k, re.compile(v)) for k, v in ISSUE_RULES]


def u(key, seed):
    h = hashlib.sha256(f"{seed}|{key}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def body(t):
    return re.sub(r"\s+", " ", TPL.sub(" ", str(t).replace("\n", " "))).strip()


def is_packaging(b):
    b = b.lower()
    for mm in DMG.finditer(b):
        if NEG.search(b[max(0, mm.start() - 14):mm.start()]):
            continue
        if CONT.search(b[max(0, mm.start() - 45):mm.end() + 45]):
            return True
    return False


def rule_issue(b):
    b = b.lower()
    for k, rx in ISSUE_RULES:
        if rx.search(b):
            return k
    return "other"


def lot_to_product(lot):
    return "P" + lot[1:3]


def build(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    m = pd.read_csv(a.master, dtype={"review_id": str})
    g = pd.read_csv(a.gold, dtype={"review_id": str})
    d = m.merge(g, on="review_id")
    fewshot_ids = {e["review_id"] for e in json.load(open(a.fewshot, encoding="utf-8"))["examples"]}
    res = d[(d["split"] == "reserve") & (~d["review_id"].isin(fewshot_ids))].copy()
    res["b"] = res["review_text"].map(body)
    res = res[res["b"].str.len().between(25, 220)].copy()
    res["pk"] = res["b"].map(is_packaging)
    lots = sorted(m["lot_id"].unique())
    assert len(lots) >= 30

    # kho nguồn (loại trừ nhau giữa các nhóm sử dụng)
    pk_pool = res[res["pk"] & (res["label_original"] == "negative") & ~res["b"].str.contains("thiếu", case=False)].copy()
    pk_pool["sub"] = pk_pool["b"].map(lambda b: [k for k, rx in SUB.items() if rx.search(b.lower())])
    neg_pool = res[(~res["pk"]) & (res["label_original"] == "negative")].copy()
    neg_pool["issue_type"] = neg_pool["b"].map(rule_issue)
    pos_pool = res[(res["label_original"] == "positive") & (~res["pk"])].copy()
    used = set()
    rng = np.random.default_rng(a.seed)

    def take(pool, n, cond=None):
        c = pool[~pool["review_id"].isin(used)]
        if cond is not None:
            c = c[c.apply(cond, axis=1)]
        assert len(c) >= n, f"không đủ nguồn: cần {n}, có {len(c)}"
        ids = list(rng.choice(c["review_id"].to_numpy(), size=n, replace=False))
        used.update(ids)
        return pool.set_index("review_id").loc[ids].reset_index()

    all_events, checkpoints = [], []
    sets = {"tune": ("T", datetime(2026, 10, 1, tzinfo=TZ), lots[:15]),
            "eval": ("E", datetime(2026, 10, 8, tzinfo=TZ), lots[15:30])}
    W = a.window_hours
    T = a.ref_threshold

    for sname, (tag, start, lot_pool) in sets.items():
        def wstart(day, w):
            return start + timedelta(days=day, hours=w * W)

        def rand_time(ws):
            return ws + timedelta(seconds=int(rng.integers(0, W * 3600 - 1)))

        ev = []  # mỗi phần tử: dict một sự kiện

        def add(row, lot, ws, scenario, issue_type, source):
            ev.append(dict(set=sname, scenario_id=scenario, source_review_id=row["review_id"], review_text=row["review_text"],
                           rating=int(row["rating"]), label=row["label_original"], issue_type=issue_type,
                           issue_type_source=source, lot_id=lot, window_start=ws, created_at=rand_time(ws)))

        focus = list(rng.choice(lot_pool, size=6, replace=False))
        lotK1, lotK2, lotK3, lotK5a, lotK5b, lotK7 = focus
        lotsK4 = list(rng.choice(lot_pool, size=8, replace=False))
        # vị trí cửa sổ kiểm tra (sau 3 ngày lịch sử): (ngày, chỉ số cửa sổ)
        pos = {"K0a": (3, 2), "K1": (3, 4), "K2": (4, 1), "K3": (4, 3), "K0b": (4, 5),
               "K4": (5, 1), "K5a": (5, 3), "K5b": (5, 5), "K7": (6, 2)}
        cp_windows = {wstart(*v) for v in pos.values()}

        # K1: lỗi bao bì tập trung, cách diễn đạt GIỐNG nhau (kiểu móp), n = 7
        for _, r in take(pk_pool, 7, lambda r: r["sub"] == ["mop"]).iterrows():
            add(r, lotK1, wstart(*pos["K1"]), "K1", "packaging_damage", "rule_packaging")
        # K2: cùng loại lỗi, cách diễn đạt KHÁC nhau (lấy luân phiên 4 nhóm), n = 8
        for i in range(8):
            key = list(SUB)[i % 4]
            r = take(pk_pool, 1, lambda r, key=key: r["sub"] == [key]).iloc[0]
            add(r, lotK2, wstart(*pos["K2"]), "K2", "packaging_damage", "rule_packaging")
        # K3: cụm nhỏ dưới ngưỡng, n = T-2
        for _, r in take(pk_pool, T - 2).iterrows():
            add(r, lotK3, wstart(*pos["K3"]), "K3", "packaging_damage", "rule_packaging")
        # K4: lỗi bao bì rải đều 8 lô, mỗi lô 1 ca
        for lot, (_, r) in zip(lotsK4, take(pk_pool, 8).iterrows()):
            add(r, lot, wstart(*pos["K4"]), "K4", "packaging_damage", "rule_packaging")
        # K5a: đúng ngưỡng (n = T); K5b: sát dưới ngưỡng (n = T-1)
        for _, r in take(pk_pool, T).iterrows():
            add(r, lotK5a, wstart(*pos["K5a"]), "K5a", "packaging_damage", "rule_packaging")
        for _, r in take(pk_pool, T - 1).iterrows():
            add(r, lotK5b, wstart(*pos["K5b"]), "K5b", "packaging_damage", "rule_packaging")
        # K0b: một ca lẻ (một ca duy nhất không được báo)
        lone_lot = [l for l in lot_pool if l not in focus][0]
        r = take(pk_pool, 1).iloc[0]
        add(r, lone_lot, wstart(*pos["K0b"]), "K0b", "packaging_damage", "rule_packaging")
        # K7: nhiều loại lỗi cùng một lô, mỗi loại dưới ngưỡng (3 + 2 + 2)
        for itype, n in (("delivery_issue", 3), ("product_defect", 2), ("poor_quality", 2)):
            for _, r in take(neg_pool, n, lambda r, it=itype: r["issue_type"] == it).iterrows():
                add(r, lotK7, wstart(*pos["K7"]), "K7", itype, "rule")
        # ca lẻ bao bì rải rác ở các cửa sổ KHÔNG phải cửa sổ kiểm tra (tạo mức nền > 0 cho baseline)
        n_single = 0
        while n_single < a.n_singles:
            day, w, lot = int(rng.integers(0, 7)), int(rng.integers(0, 6)), str(rng.choice(lot_pool))
            if wstart(day, w) in cp_windows:
                continue
            r = take(pk_pool, 1).iloc[0]
            add(r, lot, wstart(day, w), "BG_single", "packaging_damage", "rule_packaging")
            n_single += 1
        # nền: Poisson theo (lô, cửa sổ); 25% negative không bao bì, 75% positive
        for day in range(7):
            for w in range(6):
                for lot in lots:
                    for _ in range(int(rng.poisson(a.bg_rate))):
                        if rng.random() < a.bg_neg_share:
                            r = take(neg_pool, 1).iloc[0]
                            add(r, lot, wstart(day, w), "BG", r["issue_type"], "rule")
                        else:
                            r = take(pos_pool, 1).iloc[0]
                            add(r, lot, wstart(day, w), "BG", "none", "none_positive")
        df = pd.DataFrame(ev).sort_values(["created_at", "source_review_id"]).reset_index(drop=True)
        df["scenario_review_id"] = [f"S-{tag}-{i + 1:05d}" for i in range(len(df))]
        df["product_id"] = df["lot_id"].map(lot_to_product)
        df["customer_id"] = [f"C{int(u(i + '|cust', a.seed) * 5000):05d}" for i in df["scenario_review_id"]]
        df["customer_tier"] = ["VIP" if u(c + "|tier", a.seed) < 0.2 else "Regular" for c in df["customer_id"]]
        all_events.append(df)

        # --- bảng kỳ vọng: TÍNH từ dữ liệu
        neg = df[df["issue_type"].ne("none")]

        def cluster(ws):
            x = neg[neg["window_start"] == ws]
            if x.empty:
                return 0, "-", "-"
            c = x.groupby(["lot_id", "issue_type"]).size().sort_values(ascending=False)
            (lot, it), n = c.index[0], int(c.iloc[0])
            return n, lot, it

        desc = {
            "K0a": "Không có lỗi: chỉ có review nền, không cụm", "K1": f"Lỗi bao bì tập trung một lô (7 ca, cùng cách diễn đạt), trên ngưỡng",
            "K2": "Lỗi bao bì tập trung một lô (8 ca), cách diễn đạt khác nhau (móp/rách/vỡ/chảy)",
            "K3": f"Cụm nhỏ dưới ngưỡng ({T - 2} ca một lô)", "K0b": "Một ca lỗi bao bì lẻ ở một lô, không phải cụm",
            "K4": "Lỗi bao bì rải đều 8 lô khác nhau (1 ca mỗi lô), không lô nào có cụm",
            "K5a": f"Đúng ngưỡng ({T} ca một lô)", "K5b": f"Sát dưới ngưỡng ({T - 1} ca một lô)",
            "K7": "Nhiều loại lỗi khác nhau trong cùng một lô, mỗi loại dưới ngưỡng"}
        design_lot = {"K1": lotK1, "K2": lotK2, "K3": lotK3, "K5a": lotK5a, "K5b": lotK5b, "K7": lotK7, "K0b": lone_lot}
        order = ["K0a", "K1", "K2", "K3", "K0b", "K4", "K5a", "K5b", "K7"]
        for sc in order:
            ws = wstart(*pos[sc])
            n, lot, it = cluster(ws)
            checkpoints.append(dict(
                checkpoint_id=f"{tag}-{sc}", set=sname, scenario_id=sc, description=desc[sc],
                sim_now=(ws + timedelta(hours=W)).isoformat(), window_start=ws.isoformat(), window_hours=W,
                focus_lot_id=design_lot.get(sc, "MULTI" if sc == "K4" else "-"),
                focus_issue_type=("-" if sc == "K0a" else "MIXED" if sc == "K7" else "packaging_damage"), max_cluster_size=n,
                reference_threshold=T, expected_alert=bool(n >= T), rerun_of=""))
        k1 = next(c for c in checkpoints if c["checkpoint_id"] == f"{tag}-K1")
        for suffix, mins, text in (("K6a", 0, "Chạy lại ngay cùng thời điểm sau khi đã báo K1"),
                                   ("K6b", 30, "Chạy lại 30 phút sau (trong thời gian chờ) khi cụm vẫn còn")):
            checkpoints.append(dict(
                checkpoint_id=f"{tag}-{suffix}", set=sname, scenario_id=suffix, description=text,
                sim_now=(datetime.fromisoformat(k1["sim_now"]) + timedelta(minutes=mins)).isoformat(),
                window_start=k1["window_start"], window_hours=W, focus_lot_id=k1["focus_lot_id"],
                focus_issue_type=k1["focus_issue_type"], max_cluster_size=k1["max_cluster_size"],
                reference_threshold=T, expected_alert=False, rerun_of=k1["checkpoint_id"]))

    ev = pd.concat(all_events, ignore_index=True)
    cp = pd.DataFrame(checkpoints)
    # --- assert với thiết kế
    exp = cp.set_index("checkpoint_id")["expected_alert"]
    for tag in ("T", "E"):
        for sc, want in {"K0a": False, "K1": True, "K2": True, "K3": False, "K0b": False, "K4": False,
                         "K5a": True, "K5b": False, "K6a": False, "K6b": False, "K7": False}.items():
            assert bool(exp[f"{tag}-{sc}"]) == want, f"kỳ vọng sai ở {tag}-{sc}"
    assert ev["source_review_id"].is_unique, "một review nguồn bị dùng hai lần"
    assert set(ev["source_review_id"]) <= set(res["review_id"]), "nguồn nằm ngoài reserve"
    assert not (set(ev["source_review_id"]) & fewshot_ids)
    real = ~cp["focus_lot_id"].isin(["MULTI", "-"])
    t_lots = set(cp[(cp["set"] == "tune") & real]["focus_lot_id"])
    e_lots = set(cp[(cp["set"] == "eval") & real]["focus_lot_id"])
    assert not (t_lots & e_lots), "lô trọng tâm của hai bộ bị trùng"
    ev["window_start"] = ev["window_start"].map(lambda x: x.isoformat())
    ev["created_at"] = ev["created_at"].map(lambda x: x.isoformat())
    cols = ["scenario_review_id", "set", "scenario_id", "source_review_id", "review_text", "rating", "label",
            "issue_type", "issue_type_source", "lot_id", "product_id", "customer_id", "customer_tier", "window_start", "created_at"]
    ev[cols].rename(columns={"set": "scenario_set"}).to_csv(out / "scenario_reviews.csv", index=False, encoding="utf-8")
    cp.rename(columns={"set": "scenario_set"}).to_csv(out / "scenario_checkpoints.csv", index=False, encoding="utf-8")
    rep = {"params": {k: v for k, v in vars(a).items() if k not in ("master", "gold", "fewshot", "out")},
           "rows_by_set": ev["set"].value_counts().to_dict(),
           "rows_by_set_scenario": {s: g["scenario_id"].value_counts().to_dict() for s, g in ev.groupby("set")},
           "issue_type_by_set": {s: g["issue_type"].value_counts().to_dict() for s, g in ev.groupby("set")},
           "label_by_set": {s: g["label"].value_counts().to_dict() for s, g in ev.groupby("set")},
           "checkpoints": int(len(cp)), "expected_alert_true": cp[cp["expected_alert"]]["checkpoint_id"].tolist(),
           "focus_lots": {"tune": sorted(t_lots), "eval": sorted(e_lots)},
           "source_reviews_unique": int(ev["source_review_id"].nunique()),
           "packaging_pool_size": int(len(pk_pool)), "checks": "pass (nguồn duy nhất, trong reserve, kỳ vọng khớp thiết kế, lô trọng tâm không trùng)"}
    (out / "scenario_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--fewshot", required=True)
    ap.add_argument("--out", default="out")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--window-hours", dest="window_hours", type=int, default=4)
    ap.add_argument("--ref-threshold", dest="ref_threshold", type=int, default=5)
    ap.add_argument("--bg-rate", dest="bg_rate", type=float, default=0.35)
    ap.add_argument("--bg-neg-share", dest="bg_neg_share", type=float, default=0.25)
    ap.add_argument("--n-singles", dest="n_singles", type=int, default=8)
    build(ap.parse_args())
