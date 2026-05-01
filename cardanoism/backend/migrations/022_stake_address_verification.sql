-- ============================================================
-- 022_stake_address_verification.sql
-- ステークアドレスのウォレット署名による所有確認 (CIP-8 / signData)
--
-- - stake_addresses に verified / verified_at を追加 (自己申告 → 暗号証明済み)
-- - wallet_verification_nonces: 一時 nonce (5 分 TTL)。1 nonce 1 回限り (used)
--
-- 検証フロー:
--   1. ユーザがマイページの「ウォレットで検証」ボタンを押す
--   2. サーバが nonce を発行し DB に保存 (expires_at = NOW + 5min)
--   3. ブラウザ側で CIP-30 signData(stake_addr_hex, "Cardanoism: verify ownership / nonce=...")
--   4. サーバが COSE_Sign1 を検証 + nonce 一致を確認 → verified=1
-- ============================================================

ALTER TABLE stake_addresses
    ADD COLUMN IF NOT EXISTS verified    TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS verified_at DATETIME            DEFAULT NULL;

CREATE TABLE IF NOT EXISTS wallet_verification_nonces (
    id            INT          AUTO_INCREMENT PRIMARY KEY,
    user_id       INT          NOT NULL,
    stake_address VARCHAR(255) NOT NULL,
    nonce         VARCHAR(64)  NOT NULL,
    expires_at    DATETIME     NOT NULL,
    used          TINYINT(1)   NOT NULL DEFAULT 0,
    created_at    DATETIME              DEFAULT CURRENT_TIMESTAMP,
    KEY idx_nonce         (nonce),
    KEY idx_user_addr     (user_id, stake_address),
    KEY idx_expires       (expires_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
