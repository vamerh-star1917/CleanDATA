-- ====================================================================
-- CSDL BỔ SUNG CHO WORKFLOW n8n (CRM & CẢNH BÁO RỦI RO)
-- Thực thi trên Supabase SQL Editor
-- ====================================================================

-- 1. Bảng lưu các bản nháp phản hồi do AI sinh ra (chờ duyệt qua Telegram)
CREATE TABLE IF NOT EXISTS response_drafts (
    draft_id SERIAL PRIMARY KEY,
    review_id TEXT REFERENCES reviews(review_id) ON DELETE CASCADE,
    customer_id TEXT,
    customer_tier TEXT CHECK (customer_tier IN ('VIP', 'Regular')),
    issue_type TEXT,
    reason TEXT,
    response_draft TEXT,
    status TEXT DEFAULT 'pending_approval' CHECK (status IN ('pending_approval', 'approved', 'rejected', 'edited')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index để tìm kiếm nhanh theo review và trạng thái
CREATE INDEX IF NOT EXISTS idx_response_drafts_review ON response_drafts(review_id);
CREATE INDEX IF NOT EXISTS idx_response_drafts_status ON response_drafts(status);

-- 2. Bảng lưu trữ kết quả phân loại (cho node Positive - Update DB nếu dùng)
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id SERIAL PRIMARY KEY,
    review_id TEXT REFERENCES reviews(review_id) ON DELETE CASCADE,
    sentiment TEXT CHECK (sentiment IN ('Positive', 'Negative')),
    model_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_predictions_review ON predictions(review_id);
