-- ============================================================
-- 006_treasury.sql
-- トレジャリー関連キャッシュ
--
-- - treasury_snapshot   : 最新残高 (id=1 固定の単一行)
-- - treasury_history    : エポックごとの残高履歴 (チャート用、直近 6 ep を UPSERT)
-- - treasury_withdrawal : 引き出し履歴
-- - ncl_active          : 採用中の Net Change Limit (id=1 固定)
--
-- 同期は notify_worker.py --event treasury_sync
-- ============================================================

-- 最新トレジャリー残高 (id=1 の単一行で常に上書き)
CREATE TABLE IF NOT EXISTS treasury_snapshot (
    id         INT      PRIMARY KEY,
    epoch_no   INT      NOT NULL,
    treasury   BIGINT   NOT NULL,            -- lovelace
    reserves   BIGINT   DEFAULT NULL,
    supply     BIGINT   DEFAULT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- エポック別残高履歴 (treasury_sync が直近 6 ep を /totals?_epoch_no=N で UPSERT)
CREATE TABLE IF NOT EXISTS treasury_history (
    epoch_no    INT      NOT NULL PRIMARY KEY,
    treasury    BIGINT   DEFAULT NULL,
    reserves    BIGINT   DEFAULT NULL,
    supply      BIGINT   DEFAULT NULL,
    fetched_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- トレジャリー引き出し履歴 (Koios /treasury_withdrawals のキャッシュ)
CREATE TABLE IF NOT EXISTS treasury_withdrawal (
    id              INT          AUTO_INCREMENT PRIMARY KEY,
    stake_address   VARCHAR(128) NOT NULL,
    amount_lovelace BIGINT       NOT NULL,
    earned_epoch    INT          NOT NULL,
    spendable_epoch INT          NOT NULL,
    UNIQUE KEY uq_wd       (stake_address, earned_epoch, amount_lovelace),
    INDEX idx_earned (earned_epoch DESC)
);

-- 採用中の Net Change Limit (直近で DRep 過半数賛成のもの、id=1 固定)
CREATE TABLE IF NOT EXISTS ncl_active (
    id               INT          PRIMARY KEY,
    limit_ada        BIGINT       NOT NULL,
    start_epoch      INT          NOT NULL,
    end_epoch        INT          NOT NULL,
    title            VARCHAR(500) NOT NULL,
    proposal_tx_hash VARCHAR(64)  NOT NULL,
    proposal_id      VARCHAR(128) NOT NULL,
    drep_yes_pct     DECIMAL(5,2) NOT NULL,
    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
