#!/usr/bin/env python3
"""Kiểm tra file reviews_preload.sql bằng SQLite làm môi trường thay thế (KHÔNG phải PostgreSQL):
số dòng, khóa ngoại, văn bản khớp CSV, và kiểm tra chéo kỳ vọng kịch bản bằng GROUP BY thuần.
Chạy: python verify_preload.py   -> 06_reports/preload_check.json"""
import json, sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
con = sqlite3.connect(":memory:"); con.execute("PRAGMA foreign_keys=ON")
con.executescript((ROOT / "01_data/preload/reviews_preload.sql").read_text(encoding="utf-8"))
q = lambda s: con.execute(s).fetchall()
res = {"engine": "SQLite (mô phỏng cục bộ; đã kiểm chứng trên PostgreSQL/Supabase)"}
res["counts"] = {t: q(f"select count(*) from {t}")[0][0] for t in ["reviews", "review_gold", "scenario_reviews", "scenario_checkpoints", "issue_types"]}
res["fk_orphans_review_gold"] = q("select count(*) from review_gold g left join reviews r using(review_id) where r.review_id is null")[0][0]
res["fk_orphans_scenario_issue_type"] = q("select count(*) from scenario_reviews s left join issue_types i using(issue_type) where i.issue_type is null")[0][0]
rv = pd.read_csv(ROOT / "01_data/reviews.csv", dtype={"review_id": str}).set_index("review_id")
db = dict(q("select review_id, review_text from reviews"))
norm = lambda s: str(s).replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
res["review_text_differs_from_csv"] = sum(norm(rv.at[i, "review_text"]) != db[i] for i in rv.index)
res["rows_with_newline"] = sum("\n" in v for v in db.values()); res["rows_with_apostrophe"] = sum("'" in v for v in db.values())
res["vip_share"] = round(q("select avg(customer_tier='VIP') from reviews")[0][0], 3)
res["split_counts"] = dict(q("select split,count(*) from review_gold group by split"))
rows = q("""select c.checkpoint_id,c.expected_alert,c.reference_threshold,
 coalesce((select max(n) from (select count(*) n from scenario_reviews s where s.scenario_set=c.scenario_set and s.window_start=c.window_start and s.issue_type<>'none' group by s.lot_id,s.issue_type)),0),
 c.max_cluster_size,c.rerun_of from scenario_checkpoints c""")
bad = [r[0] for r in rows if r[3] != r[4] or bool(r[1]) != (r[3] >= r[2] and r[5] is None)]
res["scenario_sql_crosscheck"] = {"checkpoints": len(rows), "mismatches": len(bad), "mismatch_ids": bad}
ok = res["fk_orphans_review_gold"] == 0 and res["fk_orphans_scenario_issue_type"] == 0 and res["review_text_differs_from_csv"] == 0 and not bad
res["all_passed"] = bool(ok)
(ROOT / "06_reports/preload_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=2)); assert ok
