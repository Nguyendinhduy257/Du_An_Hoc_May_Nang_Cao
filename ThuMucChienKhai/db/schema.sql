-- ==================================================================
-- Đường dẫn: Du_An_Hoc_May_Nang_Cao\ThuMucChienKhai\db\schema.sql
-- Mục đích : Tạo toàn bộ bảng cho đồ án Fake Review Detection.
-- Ghi chú  : Mọi lệnh đều có IF NOT EXISTS nên chạy lại nhiều lần vẫn an toàn.
--            File này được Docker chạy tự động ở lần khởi tạo đầu tiên,
--            và cũng được MaNguon/db.py đọc để bảo đảm schema luôn đủ.
--
-- GLOSSARY:
--   JSONB      : kiểu JSON nhị phân của PostgreSQL, truy vấn được bên trong.
--   BIGSERIAL  : số nguyên tự tăng 64-bit.
--   TIMESTAMPTZ: thời gian có múi giờ.
--   CHECK      : ràng buộc giá trị hợp lệ.
-- ==================================================================

-- Mỗi lần huấn luyện tạo một dòng: lưu ngưỡng, chỉ số, cấu hình.
CREATE TABLE IF NOT EXISTS model_runs (
    id          BIGSERIAL PRIMARY KEY,
    model_name  TEXT        NOT NULL,
    threshold   NUMERIC(6, 4) NOT NULL,
    metrics     JSONB       NOT NULL,
    config      JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mỗi lần người dùng tải file CSV lên: lưu thông tin lô phân tích.
CREATE TABLE IF NOT EXISTS upload_batches (
    id                 BIGSERIAL PRIMARY KEY,
    file_name          TEXT        NOT NULL,
    rows_total         INTEGER     NOT NULL,
    rows_analyzed      INTEGER     NOT NULL,
    translate_requested BOOLEAN    NOT NULL,
    elapsed_seconds    NUMERIC(8, 2) NOT NULL,
    summary            JSONB       NOT NULL,
    warnings           JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bảng trung tâm: một dòng cho mỗi review đã được chấm điểm.
-- dataset_split: 'test' (dữ liệu demo), 'val' (để vẽ đường ngưỡng),
--                'upload' (file người dùng tải lên).
CREATE TABLE IF NOT EXISTS reviews (
    id               BIGSERIAL PRIMARY KEY,
    model_run_id     BIGINT      REFERENCES model_runs(id) ON DELETE SET NULL,
    batch_id         BIGINT      REFERENCES upload_batches(id) ON DELETE CASCADE,
    dataset_split    TEXT        NOT NULL CHECK (dataset_split IN ('test', 'val', 'upload')),
    row_index        INTEGER     NOT NULL,
    text             TEXT        NOT NULL,
    translated_text  TEXT        NOT NULL DEFAULT '',
    used_translation BOOLEAN     NOT NULL DEFAULT FALSE,
    rating           NUMERIC(3, 1),
    product_category TEXT        NOT NULL DEFAULT '',
    true_label       SMALLINT    CHECK (true_label IN (0, 1) OR true_label IS NULL),
    prob_fake        NUMERIC(7, 6) NOT NULL CHECK (prob_fake >= 0 AND prob_fake <= 1),
    predicted_label  SMALLINT    NOT NULL CHECK (predicted_label IN (0, 1)),
    category         TEXT        NOT NULL,
    flags            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    reasons          JSONB       NOT NULL DEFAULT '[]'::jsonb,
    is_useful        BOOLEAN     NOT NULL,
    is_reliable      BOOLEAN     NOT NULL,
    word_count       INTEGER     NOT NULL,
    known_token_ratio NUMERIC(6, 5) NOT NULL DEFAULT 1.0,
    content_hash     CHAR(64)    NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bổ sung cột cho database đã tạo từ phiên bản trước.
-- Vì sao cần: lý do "không đáng tin" trên web cần đúng tỷ lệ token quen thuộc.
ALTER TABLE reviews
    ADD COLUMN IF NOT EXISTS known_token_ratio NUMERIC(6, 5) NOT NULL DEFAULT 1.0;

-- Vì sao có index: bảng có thể lên tới hàng trăm nghìn dòng khi nạp nhiều file.
CREATE INDEX IF NOT EXISTS reviews_split_idx    ON reviews (dataset_split);
CREATE INDEX IF NOT EXISTS reviews_category_idx ON reviews (category);
CREATE INDEX IF NOT EXISTS reviews_useful_idx   ON reviews (is_useful);
CREATE INDEX IF NOT EXISTS reviews_rating_idx   ON reviews (rating);
CREATE INDEX IF NOT EXISTS reviews_batch_idx    ON reviews (batch_id);
CREATE INDEX IF NOT EXISTS reviews_hash_idx     ON reviews (content_hash);

-- Chống nạp trùng dữ liệu demo: mỗi (lần chạy model, tập, vị trí dòng) là duy nhất.
-- Vì sao dùng partial index: dòng upload có batch_id khác NULL nên không bị ràng buộc.
CREATE UNIQUE INDEX IF NOT EXISTS reviews_demo_unique
    ON reviews (model_run_id, dataset_split, row_index)
    WHERE batch_id IS NULL;

-- Cache bản dịch: giúp lần tải file thứ hai nhanh và ổn định, kể cả khi
-- dịch vụ dịch bên ngoài tạm thời không truy cập được.
CREATE TABLE IF NOT EXISTS translation_cache (
    source_hash       CHAR(64) PRIMARY KEY,
    source_text       TEXT        NOT NULL,
    translated_text   TEXT        NOT NULL,
    provider          TEXT        NOT NULL DEFAULT 'google-unofficial',
    detected_language TEXT        NOT NULL DEFAULT '',
    hit_count         INTEGER     NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bổ sung cột cho database đã tạo từ phiên bản trước.
-- Vì sao cần: CREATE TABLE IF NOT EXISTS không thêm cột vào bảng đã tồn tại.
ALTER TABLE translation_cache
    ADD COLUMN IF NOT EXISTS detected_language TEXT NOT NULL DEFAULT '';
