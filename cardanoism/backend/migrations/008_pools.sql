-- ============================================================
-- 008_pools.sql
-- ステークプール（SPO）キャッシュ
--
-- - Koios /pool_list + /pool_info の結果をマージしてキャッシュ
-- - 同期は notify_worker.py --event pool_sync
-- - DRep キャッシュ (005_dreps.sql) と同じ戦略：DB だけ読めばリスト/ダッシュボードを描画できる
-- ============================================================

CREATE TABLE IF NOT EXISTS pools (
    pool_id_bech32   VARCHAR(64)  PRIMARY KEY,
    pool_id_hex      VARCHAR(64)  DEFAULT NULL,
    pool_status      VARCHAR(32)  DEFAULT NULL,
    active_epoch_no  INT          DEFAULT NULL,
    retiring_epoch   INT          DEFAULT NULL,
    op_cert          VARCHAR(128) DEFAULT NULL,
    op_cert_counter  INT          DEFAULT NULL,
    vrf_key_hash     VARCHAR(128) DEFAULT NULL,
    pledge           BIGINT       DEFAULT 0,
    margin           DECIMAL(7,6) DEFAULT NULL,
    fixed_cost       BIGINT       DEFAULT 0,
    active_stake     BIGINT       DEFAULT 0,
    live_stake       BIGINT       DEFAULT 0,
    live_pledge      BIGINT       DEFAULT 0,
    live_delegators  INT          DEFAULT 0,
    live_saturation  DECIMAL(7,4) DEFAULT NULL,
    sigma            DECIMAL(12,10) DEFAULT NULL,
    block_count      INT          DEFAULT 0,
    reward_addr      VARCHAR(255) DEFAULT NULL,
    owners           LONGTEXT     DEFAULT NULL,
    relays           LONGTEXT     DEFAULT NULL,
    meta_url         TEXT         DEFAULT NULL,
    meta_hash        VARCHAR(128) DEFAULT NULL,
    ticker           VARCHAR(64)  DEFAULT NULL,
    pool_name        VARCHAR(255) DEFAULT NULL,
    description      TEXT         DEFAULT NULL,
    homepage         TEXT         DEFAULT NULL,
    pool_icon_url    TEXT         DEFAULT NULL,
    pool_logo_url    TEXT         DEFAULT NULL,
    extended_about   TEXT         DEFAULT NULL,
    twitter_handle   VARCHAR(128) DEFAULT NULL,
    telegram_handle  VARCHAR(128) DEFAULT NULL,
    youtube_handle   VARCHAR(255) DEFAULT NULL,
    github_handle    VARCHAR(128) DEFAULT NULL,
    relay_alive      TINYINT(1)   DEFAULT NULL,
    relay_checked_at DATETIME     DEFAULT NULL,
    fetched_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_live_stake (live_stake),
    KEY idx_active_stake (active_stake),
    KEY idx_status (pool_status),
    KEY idx_ticker (ticker),
    KEY idx_saturation (live_saturation),
    KEY idx_block_count (block_count),
    KEY idx_delegators (live_delegators)
);
