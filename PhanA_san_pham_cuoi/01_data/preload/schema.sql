-- Schema phần A (đề xuất; thống nhất với CH01). Các cột giả lập được ghi rõ trong data_dictionary.xlsx
CREATE TABLE IF NOT EXISTS issue_types (
  issue_type   TEXT PRIMARY KEY,
  description  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
  review_id      TEXT PRIMARY KEY,                 -- id gốc Kaggle (khóa idempotent cho WF1)
  review_text    TEXT NOT NULL,                    -- GỐC
  rating         SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),   -- GỐC
  customer_id    TEXT NOT NULL,                    -- GIẢ LẬP
  customer_tier  TEXT NOT NULL CHECK (customer_tier IN ('VIP','Regular')),  -- GIẢ LẬP (20% VIP)
  product_id     TEXT NOT NULL,                    -- GIẢ LẬP
  lot_id         TEXT NOT NULL,                    -- GIẢ LẬP
  created_at     TIMESTAMPTZ NOT NULL              -- GIẢ LẬP
);

-- Nhãn và thông tin chia tập tách riêng để workflow không vô tình đọc nhãn gốc
CREATE TABLE IF NOT EXISTS review_gold (
  review_id          TEXT PRIMARY KEY REFERENCES reviews(review_id),
  label_original     TEXT NOT NULL CHECK (label_original IN ('positive','negative')),  -- GỐC (suy ra từ số sao, chưa kiểm chứng)
  rating_label_flag  TEXT NOT NULL,
  split              TEXT NOT NULL CHECK (split IN ('few_shot_pool','validation','test_main','test_skew','reserve')),
  skew_group         TEXT,
  dup_group          INTEGER NOT NULL,
  label_human        TEXT CHECK (label_human IN ('positive','negative'))   -- điền sau khi gán nhãn Test lệch
);

CREATE TABLE IF NOT EXISTS scenario_reviews (
  scenario_review_id TEXT PRIMARY KEY,
  scenario_set       TEXT NOT NULL CHECK (scenario_set IN ('tune','eval')),
  scenario_id        TEXT NOT NULL,
  source_review_id   TEXT NOT NULL,
  review_text        TEXT NOT NULL,
  rating             SMALLINT NOT NULL,
  label              TEXT NOT NULL,
  issue_type         TEXT NOT NULL REFERENCES issue_types(issue_type),
  issue_type_source  TEXT NOT NULL,                -- rule_packaging | rule | none_positive (KHÔNG phải nhãn người)
  lot_id             TEXT NOT NULL,
  product_id         TEXT NOT NULL,
  customer_id        TEXT NOT NULL,
  customer_tier      TEXT NOT NULL,
  window_start       TIMESTAMPTZ NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS scenario_checkpoints (
  checkpoint_id        TEXT PRIMARY KEY,
  scenario_set         TEXT NOT NULL,
  scenario_id          TEXT NOT NULL,
  description          TEXT NOT NULL,
  sim_now              TIMESTAMPTZ NOT NULL,
  window_start         TIMESTAMPTZ NOT NULL,
  window_hours         INTEGER NOT NULL,
  focus_lot_id         TEXT NOT NULL,
  focus_issue_type     TEXT NOT NULL,
  max_cluster_size     INTEGER NOT NULL,
  reference_threshold  INTEGER NOT NULL,
  expected_alert       BOOLEAN NOT NULL,
  rerun_of             TEXT
);
