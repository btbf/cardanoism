-- ============================================================
-- 015_ga_withdrawal_payout.sql
-- GA (TreasuryWithdrawals) の受取先ごとの出金状況
--
-- ratified_epoch を持つ TreasuryWithdrawals GA の withdrawal_json を
-- 受取先 (stake_address) 単位に展開して登録し、Koios
-- /account_reward_history の type=treasury 報酬と照合して
-- 「実際に出金されたか」を追跡する。
--
-- 既存の treasury_withdrawal テーブル (Koios /treasury_withdrawals の
-- キャッシュ) とは別物。あちらは GA に紐付かない出金記録のみ。
--
-- 同期は notify_worker.py --event treasury_sync に相乗り。
-- ============================================================

CREATE TABLE IF NOT EXISTS ga_withdrawal_payout (
    id              INT          AUTO_INCREMENT PRIMARY KEY,
    proposal_id     VARCHAR(255) NOT NULL,                  -- どの GA か
    stake_address   VARCHAR(128) NOT NULL,                  -- 受取先
    amount_lovelace BIGINT       NOT NULL,                  -- withdrawal_json の amount
    paid            TINYINT(1)   NOT NULL DEFAULT 0,        -- 出金確認できたか
    paid_epoch      INT          DEFAULT NULL,              -- 照合できた earned_epoch
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payout (proposal_id, stake_address, amount_lovelace),
    KEY idx_payout_proposal (proposal_id),
    KEY idx_payout_paid     (paid)
);
