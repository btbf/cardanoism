-- migration 014: ログインプロバイダと通知チャンネルを正規化

-- ============================================================
-- 新テーブル作成
-- ============================================================

CREATE TABLE IF NOT EXISTS user_providers (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  user_id     INT NOT NULL,
  provider    ENUM('line', 'google', 'twitter') NOT NULL,
  provider_id VARCHAR(255) NOT NULL,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_provider (provider, provider_id),
  INDEX idx_user_id (user_id)
);

CREATE TABLE IF NOT EXISTS notification_channels (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  user_id      INT NOT NULL,
  channel_type ENUM('line', 'email') NOT NULL,
  channel_value VARCHAR(255) NOT NULL,
  enabled      TINYINT(1) NOT NULL DEFAULT 1,
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_user_channel (user_id, channel_type)
);

-- ============================================================
-- 既存データ移行
-- ============================================================

-- LINEログイン → user_providers
INSERT IGNORE INTO user_providers (user_id, provider, provider_id)
SELECT id, 'line', line_id FROM users WHERE line_id IS NOT NULL AND line_id != '';

-- Googleログイン → user_providers
INSERT IGNORE INTO user_providers (user_id, provider, provider_id)
SELECT id, 'google', google_id FROM users WHERE google_id IS NOT NULL AND google_id != '';

-- Twitterログイン → user_providers
INSERT IGNORE INTO user_providers (user_id, provider, provider_id)
SELECT id, 'twitter', twitter_id FROM users WHERE twitter_id IS NOT NULL AND twitter_id != '';

-- LINE通知チャンネル（line_notify_id があればそちらを、なければ line_id を使用）
INSERT IGNORE INTO notification_channels (user_id, channel_type, channel_value, enabled)
SELECT id, 'line',
  COALESCE(line_notify_id, line_id),
  COALESCE(line_notify, 1)
FROM users
WHERE COALESCE(line_notify_id, line_id) IS NOT NULL
  AND COALESCE(line_notify_id, line_id) != '';

-- メール通知チャンネル
INSERT IGNORE INTO notification_channels (user_id, channel_type, channel_value, enabled)
SELECT id, 'email', email, COALESCE(email_notify, 1)
FROM users
WHERE email IS NOT NULL AND email != '';

-- ============================================================
-- 旧カラム削除
-- ============================================================

ALTER TABLE users
  DROP COLUMN IF EXISTS line_id,
  DROP COLUMN IF EXISTS line_notify_id,
  DROP COLUMN IF EXISTS google_id,
  DROP COLUMN IF EXISTS twitter_id,
  DROP COLUMN IF EXISTS telegram_chat_id,
  DROP COLUMN IF EXISTS email_notify,
  DROP COLUMN IF EXISTS line_notify;
