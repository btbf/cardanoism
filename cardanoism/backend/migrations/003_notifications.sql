-- ============================================================
-- 003_notifications.sql
-- 通知設定 + バッチ実行ステート
--
-- ・notification_settings        : ユーザー全体イベント (epoch_start 等)
-- ・stake_notification_settings  : ステークアドレス単位イベント (pool_*, drep_*)
-- ・notification_check_state     : ogmios_listener / notify_worker の前回値
-- ・notification_log             : 送信履歴 (dedup_key で重複送信防止)
--
-- 既存ユーザー / アドレスへのデフォルトイベント挿入は
-- アプリケーションコード (auth_db.py の _create_user / add_stake_address) が担当する。
-- ============================================================

-- ユーザー全体の通知設定
-- event_type 例: epoch_start, treasury_withdrawal_enacted
CREATE TABLE IF NOT EXISTS notification_settings (
    id         INT          AUTO_INCREMENT PRIMARY KEY,
    user_id    INT          NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    enabled    TINYINT(1)   DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_event (user_id, event_type)
);

-- ステークアドレス単位の通知設定
-- event_type 例:
--   pool_retire / pool_fee_change / pool_saturation / pool_pledge_shortage /
--   pool_reward_received / pool_epoch_performance / pool_delegation_reminder /
--   spo_pending_vote /
--   drep_new_governance_action / drep_vote / drep_status_change /
--   drep_delegation_reminder / drep_unvoted_ga
CREATE TABLE IF NOT EXISTS stake_notification_settings (
    id               INT          AUTO_INCREMENT PRIMARY KEY,
    stake_address_id INT          NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    enabled          TINYINT(1)   DEFAULT 1,
    FOREIGN KEY (stake_address_id) REFERENCES stake_addresses(id) ON DELETE CASCADE,
    UNIQUE KEY uq_stake_event (stake_address_id, event_type)
);

-- バッチ実行ステート (前回値の保持)
-- scope_type:
--   global         : ユーザー横断 (current_epoch, ogmios_last_slot 等)。scope_id = 0
--   stake_address  : ステークアドレス単位 (scope_id = stake_addresses.id)
--
-- 重要: scope_id を NULL 許容にすると MySQL/MariaDB の UNIQUE は NULL を毎回
-- 別物として扱うため ON DUPLICATE KEY UPDATE が機能せず、global scope の
-- set_state が呼ばれるたびに新規行が INSERT され、テーブルが急速に肥大化する。
-- そのため NOT NULL DEFAULT 0 とし、global scope は scope_id = 0 を使う。
CREATE TABLE IF NOT EXISTS notification_check_state (
    id         INT          AUTO_INCREMENT PRIMARY KEY,
    scope_type ENUM('global', 'stake_address') NOT NULL DEFAULT 'global',
    scope_id   INT          NOT NULL DEFAULT 0,
    key_name   VARCHAR(100) NOT NULL,
    last_value TEXT,
    checked_at DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scope_key (scope_type, scope_id, key_name)
);

-- 送信履歴 + 重複送信防止
-- dedup_key は (user_id, event_type) と組み合わせて一意性を判定する
CREATE TABLE IF NOT EXISTS notification_log (
    id         INT          AUTO_INCREMENT PRIMARY KEY,
    user_id    INT          NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    channel    VARCHAR(50)  NOT NULL DEFAULT 'line',
    dedup_key  VARCHAR(255) NOT NULL DEFAULT '',
    payload    TEXT,
    sent_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    KEY idx_dedup (user_id, event_type, dedup_key)
);
