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

    -- 基本ステータス
    pool_status      VARCHAR(32)  DEFAULT NULL,             -- registered / retiring / retired
    active_epoch_no  INT          DEFAULT NULL,
    retiring_epoch   INT          DEFAULT NULL,
    op_cert          VARCHAR(128) DEFAULT NULL,
    op_cert_counter  INT          DEFAULT NULL,
    vrf_key_hash     VARCHAR(128) DEFAULT NULL,

    -- 経済パラメータ
    pledge           BIGINT       DEFAULT 0,                -- 約定ステーク (lovelace)
    margin           DECIMAL(7,6) DEFAULT NULL,             -- 変動手数料 (0.0 - 1.0)
    fixed_cost       BIGINT       DEFAULT 0,                -- 固定手数料 (lovelace)

    -- ステーク状態
    active_stake     BIGINT       DEFAULT 0,                -- アクティブステーク (lovelace)
    live_stake       BIGINT       DEFAULT 0,                -- 現在のステーク (lovelace)
    live_pledge      BIGINT       DEFAULT 0,                -- 現在のプレッジ (lovelace)
    live_delegators  INT          DEFAULT 0,                -- 委任者数
    live_saturation  DECIMAL(7,4) DEFAULT NULL,             -- 飽和率 (0.0 - 1.0+, > 1 で過飽和)
    sigma            DECIMAL(12,10) DEFAULT NULL,           -- 当該プールのアクティブステーク比率

    -- ブロック生成
    block_count      INT          DEFAULT 0,                -- 累計ブロック生成数

    -- アドレス情報
    reward_addr      VARCHAR(255) DEFAULT NULL,
    owners           LONGTEXT     DEFAULT NULL,             -- JSON 配列
    relays           LONGTEXT     DEFAULT NULL,             -- JSON 配列

    -- メタデータ (CIP-6)
    meta_url         TEXT         DEFAULT NULL,
    meta_hash        VARCHAR(64)  DEFAULT NULL,
    ticker           VARCHAR(64)  DEFAULT NULL,
    pool_name        VARCHAR(255) DEFAULT NULL,
    description      TEXT         DEFAULT NULL,
    homepage         TEXT         DEFAULT NULL,

    fetched_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    KEY idx_live_stake     (live_stake DESC),
    KEY idx_active_stake   (active_stake DESC),
    KEY idx_status         (pool_status),
    KEY idx_ticker         (ticker),
    KEY idx_saturation     (live_saturation),
    KEY idx_block_count    (block_count DESC),
    KEY idx_delegators     (live_delegators DESC)
);
