-- ============================================================
-- _alter_governance_add_meta_fetch_retry.sql
--
-- 既存の本番 / preview DB に、Ogmios が検知した Governance Action の
-- CIP-100/108 メタデータ取得状態を追加する冪等マイグレーション。
-- 新規環境では 004_governance.sql に含まれているため不要。
--
-- 適用例:
--   mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME \
--     < cardanoism/backend/migrations/_alter_governance_add_meta_fetch_retry.sql
-- ============================================================

ALTER TABLE governance_actions
  ADD COLUMN IF NOT EXISTS meta_fetch_attempts INT NOT NULL DEFAULT 0
    COMMENT 'CIP-100/108 metadata の取得試行回数' AFTER meta_is_valid,
  ADD COLUMN IF NOT EXISTS meta_fetch_next_at DATETIME DEFAULT NULL
    COMMENT '指数バックオフ後の次回取得可能時刻 (UTC)' AFTER meta_fetch_attempts,
  ADD COLUMN IF NOT EXISTS meta_fetched_at DATETIME DEFAULT NULL
    COMMENT 'metadata JSON の取得成功時刻 (UTC)' AFTER meta_fetch_next_at,
  ADD COLUMN IF NOT EXISTS meta_fetch_error VARCHAR(500) DEFAULT NULL
    COMMENT '直近の metadata 取得エラー' AFTER meta_fetched_at;

CREATE INDEX IF NOT EXISTS idx_ga_meta_retry
  ON governance_actions (meta_fetched_at, meta_fetch_next_at, meta_fetch_attempts);
