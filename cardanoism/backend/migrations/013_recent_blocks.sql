-- ============================================================
-- 013_recent_blocks.sql
-- リアルタイムブロック履歴（直近100件をローリング保持）
--
-- - ogmios_listener.py が新ブロック受信時に INSERT
-- - 100件超えたら古いものを TRIM
-- - ダッシュボードのライブブロック一覧で参照
-- ============================================================

CREATE TABLE IF NOT EXISTS recent_blocks (
    block_height  BIGINT       PRIMARY KEY,
    block_hash    VARCHAR(128) NOT NULL,
    slot_no       BIGINT       NOT NULL,
    epoch_no      INT          NOT NULL,
    pool_id_hex   VARCHAR(64)  DEFAULT NULL,
    block_time    DATETIME     NOT NULL,
    tx_count      INT          DEFAULT 0,
    block_size    INT          NOT NULL DEFAULT 0,
    fetched_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_block_time (block_time),
    KEY idx_pool_hex (pool_id_hex)
);
