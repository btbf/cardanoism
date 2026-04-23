-- ============================================================
-- 001_auth_tables.sql
-- ソーシャルログイン・マイページ機能用テーブル
-- ============================================================

-- ユーザーテーブル
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    avatar_url TEXT,
    line_id VARCHAR(255) UNIQUE,
    google_id VARCHAR(255) UNIQUE,
    twitter_id VARCHAR(255) UNIQUE,
    telegram_chat_id VARCHAR(255),
    notification_frequency ENUM('instant', 'daily') DEFAULT 'instant',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- セッションテーブル
CREATE TABLE IF NOT EXISTS user_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_token (session_token),
    INDEX idx_user_id (user_id)
);

-- ステークアドレステーブル（1ユーザー最大3件）
CREATE TABLE IF NOT EXISTS stake_addresses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    address VARCHAR(255) NOT NULL,
    nickname VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- お気に入りテーブル
CREATE TABLE IF NOT EXISTS favorites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    proposal_id INT NOT NULL,
    type ENUM('catalyst', 'governance') NOT NULL DEFAULT 'catalyst',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_proposal (user_id, proposal_id, type)
);

-- 通知設定テーブル（イベントごとON/OFF）
-- event_type の値:
--   pool_retire, pool_fee_change, pool_saturation,
--   pool_reward_estimate, pool_reward_received, pool_delegation_reminder,
--   drep_new_proposal, drep_vote, drep_delegation_reminder
CREATE TABLE IF NOT EXISTS notification_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    enabled TINYINT(1) DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_event (user_id, event_type)
);
