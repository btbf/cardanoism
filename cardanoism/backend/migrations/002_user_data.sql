-- ============================================================
-- 002_user_data.sql
-- ユーザーが操作するデータ:
--   stake_addresses             登録ステークアドレス
--   favorites                   カタリスト / ガバナンスお気に入り
--   wallet_verification_nonces  CIP-8 signData 検証用の一時 nonce
--
-- - ステークアドレスは1ユーザー最大3件 (アプリ層で制御)
-- - お気に入りは catalyst (CIDP id) と governance (proposal_id) を共通テーブルで管理
-- ============================================================

-- 登録ステークアドレス (マイページで管理)
-- role / delegated_* / spo_pool_id は Koios 取得時 + Ogmios listener で自動更新。
-- wallet_address は登録時の addr1... を保存 (受信用に表示)。
-- verified / verified_at は CIP-8 signData によるウォレット所有証明結果。
-- last_event_slot は Ogmios listener が委任 cert を反映した slot (rollback 対応)。
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
    spo_pool_id         VARCHAR(64)  DEFAULT NULL,           -- 値あり = この stake address が pools.reward_addr / owners
    verified            TINYINT(1)   NOT NULL DEFAULT 0,     -- CIP-8 signData 検証済みフラグ
    verified_at         DATETIME     DEFAULT NULL,
    last_event_slot     BIGINT       DEFAULT NULL,           -- Ogmios listener が反映した最終 slot
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    KEY idx_stake_addr_spo (spo_pool_id)
);

-- お気に入り
-- proposal_uuid:
--   - catalyst   : CIDP の UUID
--   - governance : GA の proposal_id
--   - drep       : DRep の drep_id (bech32 / cip-129)
--   - pool       : Pool の pool_id_bech32
-- (1 Tx に複数 GA を含められる仕様のため tx_hash ではなく proposal_id をキーに使う)
CREATE TABLE IF NOT EXISTS favorites (
    id            INT          AUTO_INCREMENT PRIMARY KEY,
    user_id       INT          NOT NULL,
    proposal_uuid VARCHAR(255) NOT NULL DEFAULT '',
    type          ENUM('catalyst', 'governance', 'drep', 'pool') NOT NULL DEFAULT 'catalyst',
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_proposal_type (user_id, proposal_uuid, type)
);

-- ウォレット検証 nonce (5 分 TTL、1 nonce 1 回限り)
-- 検証フロー:
--   1. ユーザがマイページの「ウォレットで検証」ボタンを押す
--   2. サーバが nonce を発行し DB に保存 (expires_at = NOW + 5min)
--   3. ブラウザ側で CIP-30 signData(stake_addr_hex, "Cardanoism: verify ownership / nonce=...")
--   4. サーバが COSE_Sign1 を検証 + nonce 一致を確認 → stake_addresses.verified=1
CREATE TABLE IF NOT EXISTS wallet_verification_nonces (
    id            INT          AUTO_INCREMENT PRIMARY KEY,
    user_id       INT          NOT NULL,
    stake_address VARCHAR(255) NOT NULL,
    nonce         VARCHAR(64)  NOT NULL,
    expires_at    DATETIME     NOT NULL,
    used          TINYINT(1)   NOT NULL DEFAULT 0,
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    KEY idx_nonce     (nonce),
    KEY idx_user_addr (user_id, stake_address),
    KEY idx_expires   (expires_at)
);
