-- 017_telegram_channel.sql
-- notification_channels に telegram チャンネルタイプを追加
-- Telegram 連携トークンテーブルを追加

ALTER TABLE notification_channels
MODIFY COLUMN channel_type ENUM('line', 'email', 'telegram') NOT NULL;

CREATE TABLE IF NOT EXISTS telegram_connect_tokens (
  token      VARCHAR(64)  PRIMARY KEY,
  user_id    INT          NOT NULL,
  expires_at DATETIME     NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
