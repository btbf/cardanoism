-- ============================================================
-- 001_users_auth.sql
-- 認証コア: users / user_sessions / user_providers /
-- notification_channels / telegram_connect_tokens
--
-- すべて CREATE TABLE IF NOT EXISTS で冪等。フレッシュ DB でも
-- 既存 DB でも安全に再実行できる。
-- ============================================================

-- ユーザー基本情報
-- 認証 ID（line_id / google_id 等）は user_providers に正規化済み。
-- 通知チャンネル（メール・LINE・Telegram）は notification_channels に正規化済み。
-- external_uuid: 外部システム（フィードバックフォーム / サポートチケット等）で
--                ユーザーを識別するための、OAuth アイデンティティと切り離された UUID v4。
--                認証用ではなく、識別子としてのみ使用する。
CREATE TABLE IF NOT EXISTS users (
    id                     INT          AUTO_INCREMENT PRIMARY KEY,
    username               VARCHAR(255) NOT NULL,
    email                  VARCHAR(255) DEFAULT NULL,
    avatar_url             TEXT         DEFAULT NULL,
    external_uuid          CHAR(36)     DEFAULT NULL UNIQUE,
    notification_frequency ENUM('instant', 'daily') DEFAULT 'instant',
    language               ENUM('ja', 'en')          NOT NULL DEFAULT 'ja',
    created_at             DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at             DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- セッション（Cookie 保存トークン）
CREATE TABLE IF NOT EXISTS user_sessions (
    id            INT          AUTO_INCREMENT PRIMARY KEY,
    user_id       INT          NOT NULL,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    expires_at    DATETIME     NOT NULL,
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_token (session_token),
    INDEX idx_user_id       (user_id)
);

-- ソーシャルログインプロバイダ（1ユーザーが複数持てる設計）
CREATE TABLE IF NOT EXISTS user_providers (
    id          INT          AUTO_INCREMENT PRIMARY KEY,
    user_id     INT          NOT NULL,
    provider    ENUM('line', 'google', 'twitter') NOT NULL,
    provider_id VARCHAR(255) NOT NULL,
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_provider (provider, provider_id),
    INDEX idx_user_id (user_id)
);

-- 通知送信先（LINE userId / Email / Telegram chat_id）
CREATE TABLE IF NOT EXISTS notification_channels (
    id            INT          AUTO_INCREMENT PRIMARY KEY,
    user_id       INT          NOT NULL,
    channel_type  ENUM('line', 'email', 'telegram') NOT NULL,
    channel_value VARCHAR(255) NOT NULL,
    enabled       TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_channel (user_id, channel_type)
);

-- Telegram Bot 連携時の一時トークン
CREATE TABLE IF NOT EXISTS telegram_connect_tokens (
    token      VARCHAR(64) PRIMARY KEY,
    user_id    INT         NOT NULL,
    expires_at DATETIME    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
