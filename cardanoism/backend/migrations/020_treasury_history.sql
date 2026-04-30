-- ============================================================
-- 020_treasury_history.sql
-- エポックごとのトレジャリー残高履歴。
--
-- treasury_snapshot は最新値だけを id=1 で保持する単一行だが、
-- 直近 N エポック分の流入/流出を可視化するためエポック別履歴が必要。
--
-- notify_worker.py --event treasury_sync が /totals?_epoch_no=N を
-- 直近 6 エポック分呼び出して UPSERT する。
-- ============================================================

CREATE TABLE IF NOT EXISTS treasury_history (
    epoch_no    INT      NOT NULL PRIMARY KEY,
    treasury    BIGINT   DEFAULT NULL,
    reserves    BIGINT   DEFAULT NULL,
    supply      BIGINT   DEFAULT NULL,
    fetched_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
