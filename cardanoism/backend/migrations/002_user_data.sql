-- ============================================================
-- 002_user_data.sql
-- ユーザーが操作するデータ: stake_addresses / favorites
--
-- - ステークアドレスは1ユーザー最大3件（アプリ層で制御）
-- - お気に入りは catalyst（CIDP id）と governance（proposal_id）を共通テーブルで管理
-- ============================================================

-- 登録ステークアドレス（マイページで管理）
-- role / delegated_* は Koios 取得時に自動で埋められる。
-- wallet_address は登録時の addr1... を保存（受信用に表示）。
CREATE TABLE IF NOT EXISTS stake_addresses (
    id                  INT          AUTO_INCREMENT PRIMARY KEY,
    user_id             INT          NOT NULL,
    address             VARCHAR(255) NOT NULL,
    wallet_address      VARCHAR(255) DEFAULT NULL,
    nickname            VARCHAR(100) NOT NULL,
    role                ENUM('delegator', 'drep', 'abstain') NOT NULL DEFAULT 'delegator',
    role_checked_at     DATETIME     DEFAULT NULL,
    delegated_drep_id   VARCHAR(255) DEFAULT NULL,
    delegated_drep_name VARCHAR(255) DEFAULT NULL,
    delegated_pool_id   VARCHAR(255) DEFAULT NULL,
    delegated_pool_name VARCHAR(255) DEFAULT NULL,
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- お気に入り
-- proposal_uuid: catalyst は CIDP の UUID、governance は GA の proposal_id
-- （1 Tx に複数 GA を含められる仕様のため tx_hash ではなく proposal_id をキーに使う）
CREATE TABLE IF NOT EXISTS favorites (
    id            INT          AUTO_INCREMENT PRIMARY KEY,
    user_id       INT          NOT NULL,
    proposal_uuid VARCHAR(255) NOT NULL DEFAULT '',
    type          ENUM('catalyst', 'governance') NOT NULL DEFAULT 'catalyst',
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_proposal_type (user_id, proposal_uuid, type)
);
