-- 018_treasury_tables.sql
-- ガバナンス > トレジャリーページ用のキャッシュテーブル
-- Koios API を毎回叩かず、バッチ（notify_worker.py --event treasury_sync）で同期する

-- 最新のトレジャリー残高（id=1 固定の単一行、ネットワーク切り替え時も常に上書き）
CREATE TABLE IF NOT EXISTS treasury_snapshot (
  id         INT      PRIMARY KEY,
  epoch_no   INT      NOT NULL,
  treasury   BIGINT   NOT NULL,    -- lovelace
  reserves   BIGINT   NULL,
  supply     BIGINT   NULL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- トレジャリー引き出し履歴（Koios /treasury_withdrawals のキャッシュ）
CREATE TABLE IF NOT EXISTS treasury_withdrawal (
  id              INT          AUTO_INCREMENT PRIMARY KEY,
  stake_address   VARCHAR(128) NOT NULL,
  amount_lovelace BIGINT       NOT NULL,
  earned_epoch    INT          NOT NULL,
  spendable_epoch INT          NOT NULL,
  UNIQUE KEY uq_wd (stake_address, earned_epoch, amount_lovelace),
  INDEX idx_earned (earned_epoch DESC)
);

-- 採用中の Net Change Limit（直近で DRep 過半数賛成のもの）
-- id=1 の1行のみを使う
CREATE TABLE IF NOT EXISTS ncl_active (
  id               INT           PRIMARY KEY,
  limit_ada        BIGINT        NOT NULL,
  start_epoch      INT           NOT NULL,
  end_epoch        INT           NOT NULL,
  title            VARCHAR(500)  NOT NULL,
  proposal_tx_hash VARCHAR(64)   NOT NULL,
  proposal_id      VARCHAR(128)  NOT NULL,
  drep_yes_pct     DECIMAL(5,2)  NOT NULL,
  updated_at       DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
