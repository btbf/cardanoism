-- 009_notification_tables.sql
-- 通知チェック状態管理テーブル + 送信ログテーブル

CREATE TABLE notification_check_state (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scope_type ENUM('global', 'stake_address') NOT NULL DEFAULT 'global',
    scope_id INT DEFAULT NULL,          -- stake_address.id / global は NULL
    key_name VARCHAR(100) NOT NULL,     -- "current_epoch", "pool_fee" など
    last_value TEXT,
    checked_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scope_key (scope_type, scope_id, key_name)
);

CREATE TABLE notification_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    channel VARCHAR(50) NOT NULL DEFAULT 'line',
    dedup_key VARCHAR(255) NOT NULL DEFAULT '',  -- 重複送信防止キー
    payload TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_dedup (user_id, event_type, dedup_key)
);
