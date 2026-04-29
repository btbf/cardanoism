-- ============================================================
-- 014_mempool_state.sql
-- Ogmios Mempool Monitoring の最新スナップショット (id=1 固定の単一行)
--
-- - tx_count       : mempool 内の待機中 tx 数
-- - byte_size      : mempool 内の合計バイト数
-- - capacity_bytes : mempool 容量上限 (bytes)
-- - 更新は ogmios_listener.py の mempool poller (10秒間隔)
-- ============================================================

CREATE TABLE IF NOT EXISTS mempool_state (
    id              INT      PRIMARY KEY,
    tx_count        INT      NOT NULL DEFAULT 0,
    byte_size       BIGINT   NOT NULL DEFAULT 0,
    capacity_bytes  BIGINT   DEFAULT NULL,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT IGNORE INTO mempool_state (id, tx_count, byte_size, capacity_bytes) VALUES (1, 0, 0, NULL);
