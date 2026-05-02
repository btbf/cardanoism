-- ============================================================
-- 005_dreps.sql
-- DRep キャッシュ
--
-- - Koios /drep_list + /drep_metadata の結果をマージしてキャッシュ
-- - image_url に data URI（base64 画像）が入るため MEDIUMTEXT
-- - 同期は notify_worker.py --event drep_sync
-- ============================================================

CREATE TABLE IF NOT EXISTS dreps (
    drep_id          VARCHAR(128) PRIMARY KEY,
    hex              VARCHAR(128) DEFAULT NULL,
    has_script       TINYINT(1)   NOT NULL DEFAULT 0,
    registered       TINYINT(1)   NOT NULL DEFAULT 0,
    drep_status      VARCHAR(32)  DEFAULT NULL,             -- active / inactive / deregistered / not_registered 等
    active           TINYINT(1)   NOT NULL DEFAULT 0,
    deposit          BIGINT       DEFAULT NULL,
    expires_epoch_no INT          DEFAULT NULL,
    amount           BIGINT       DEFAULT 0,                 -- 委任量 (lovelace)
    -- CIP-119 メタデータ
    given_name       VARCHAR(255) DEFAULT NULL,
    image_url        MEDIUMTEXT   DEFAULT NULL,
    payment_address  VARCHAR(255) DEFAULT NULL,
    motivations      MEDIUMTEXT   DEFAULT NULL,
    objectives       MEDIUMTEXT   DEFAULT NULL,
    qualifications   MEDIUMTEXT   DEFAULT NULL,
    references_json  LONGTEXT     DEFAULT NULL,
    meta_url         TEXT         DEFAULT NULL,
    meta_hash        VARCHAR(64)  DEFAULT NULL,
    meta_is_valid    TINYINT(1)   DEFAULT NULL,
    fetched_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_amount (amount DESC),
    KEY idx_active (active),
    KEY idx_name   (given_name)
);
