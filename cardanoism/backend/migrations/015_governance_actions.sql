-- 015_governance_actions.sql
-- ガバナンスアクション（オンチェーンガバナンス提案）テーブル

CREATE TABLE IF NOT EXISTS governance_actions (
    id                INT AUTO_INCREMENT PRIMARY KEY,

    -- Koios 識別子
    proposal_id       VARCHAR(255) NOT NULL UNIQUE,  -- gov_action1...
    proposal_tx_hash  VARCHAR(64)  NOT NULL,
    proposal_index    TINYINT      NOT NULL DEFAULT 0,

    -- 種別・ステータス
    proposal_type     VARCHAR(50)  NOT NULL,
    -- TreasuryWithdrawals / InfoAction / ParameterChange /
    -- NewConstitution / NewCommittee / HardForkInitiation

    proposed_epoch    INT,
    ratified_epoch    INT,
    enacted_epoch     INT,
    dropped_epoch     INT,
    expired_epoch     INT,
    expiration        INT,          -- 失効予定エポック
    block_time        DATETIME,

    -- 財務
    deposit           BIGINT,
    return_address    VARCHAR(255),

    -- オンチェーンメタデータ
    meta_url          TEXT,
    meta_hash         VARCHAR(64),
    meta_is_valid     TINYINT(1),

    -- meta_json.body（生データ）
    title             TEXT,
    abstract          MEDIUMTEXT,
    motivation        MEDIUMTEXT,
    rationale         MEDIUMTEXT,
    references_json   JSON,         -- [{uri, label, @type}, ...]

    -- 日本語翻訳（NULL = 未翻訳）
    title_ja          TEXT,
    abstract_ja       MEDIUMTEXT,
    motivation_ja     MEDIUMTEXT,
    rationale_ja      MEDIUMTEXT,

    -- 管理
    fetched_at        DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_type        (proposal_type),
    INDEX idx_epoch       (proposed_epoch),
    INDEX idx_block_time  (block_time),
    INDEX idx_expiration  (expiration)
);
