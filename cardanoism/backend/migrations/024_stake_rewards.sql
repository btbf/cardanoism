-- ============================================================
-- 024_stake_rewards.sql
-- ステーキング報酬キャッシュ:
--   stake_rewards   ステークアドレスごとのエポック別報酬
--
-- データソース:
--   notify_worker.py の _check_pool_reward_received_batch が
--   /account_reward_history を叩いた結果をここに upsert する。
--   現状は通知 ON のステークアドレスのみキャッシュされる。
--
-- ダッシュボードでの利用:
--   DashboardState が直近 5 エポック分の報酬と累積報酬を
--   ここから SELECT で取り出す（Koios リアルタイムを叩かない）。
-- ============================================================

CREATE TABLE IF NOT EXISTS stake_rewards (
    id              INT          AUTO_INCREMENT PRIMARY KEY,
    stake_address   VARCHAR(255) NOT NULL,
    epoch_no        INT          NOT NULL,
    amount_lovelace BIGINT       NOT NULL DEFAULT 0,
    pool_id         VARCHAR(128) DEFAULT NULL,
    fetched_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_stake_epoch (stake_address, epoch_no),
    KEY idx_stake (stake_address),
    KEY idx_epoch (epoch_no)
);
