-- ============================================================
-- 004_governance.sql
-- ガバナンス関連キャッシュ:
--   governance_actions         GA 本体 (CIP-100/108 メタデータ含む)
--   proposal_votes             GA への投票 (DRep / SPO / CC)
--   proposal_voting_summary    GA ごとの集計
--   protocol_params            投票閾値・デポジット等 (id=1 の単一行)
--   cc_members                 憲法委員会メンバー
--
-- 同期は notify_worker.py の各 sync イベント (vote_sync / params_sync / summary_sync 等)
-- + Ogmios listener が新規 GA / 投票を即時 INSERT。last_event_slot は rollback 対応用。
-- ============================================================

-- ガバナンスアクション本体 (CIP-100/108 メタデータ含む)
-- action_anchor_url/hash は NewConstitution の本文 PDF/Markdown 等の参照先。
-- spo_target は SPO 投票対象判定 (CIP-1694): NULL=未判定 / 0=対象外 / 1=SPO 投票対象。
-- last_event_slot は Ogmios listener が GA を反映した最終 slot (rollback 対応)。
CREATE TABLE IF NOT EXISTS governance_actions (
    id                        INT           NOT NULL AUTO_INCREMENT,
    proposal_id               VARCHAR(255)  NOT NULL,
    proposal_tx_hash          VARCHAR(64)   NOT NULL,
    proposal_index            TINYINT       NOT NULL DEFAULT 0,
    proposal_type             VARCHAR(50)   NOT NULL,
    proposed_epoch            INT           DEFAULT NULL,
    ratified_epoch            INT           DEFAULT NULL,
    enacted_epoch             INT           DEFAULT NULL,
    dropped_epoch             INT           DEFAULT NULL,
    expired_epoch             INT           DEFAULT NULL,
    expiration                INT           DEFAULT NULL,
    block_time                DATETIME      DEFAULT NULL,
    deposit                   BIGINT        DEFAULT NULL,
    withdrawal_total_lovelace BIGINT        DEFAULT NULL,
    withdrawal_json           TEXT          DEFAULT NULL,
    return_address            VARCHAR(255)  DEFAULT NULL,
    meta_url                  TEXT          DEFAULT NULL,
    meta_hash                 VARCHAR(64)   DEFAULT NULL,
    meta_is_valid             TINYINT(1)    DEFAULT NULL,
    title                     TEXT          DEFAULT NULL,
    `abstract`                MEDIUMTEXT    DEFAULT NULL,
    motivation                MEDIUMTEXT    DEFAULT NULL,
    rationale                 MEDIUMTEXT    DEFAULT NULL,
    references_json           LONGTEXT      DEFAULT NULL,
    authors_json              TEXT          DEFAULT NULL,             -- CIP-100/108 authors の name 配列 (JSON)
    title_ja                  TEXT          DEFAULT NULL,
    abstract_ja               MEDIUMTEXT    DEFAULT NULL,
    motivation_ja             MEDIUMTEXT    DEFAULT NULL,
    rationale_ja              MEDIUMTEXT    DEFAULT NULL,
    action_anchor_url         TEXT          DEFAULT NULL,
    action_anchor_hash        VARCHAR(128)  DEFAULT NULL,
    spo_target                TINYINT(1)    DEFAULT NULL,
    last_event_slot           BIGINT        DEFAULT NULL,
    fetched_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_proposal_id (proposal_id),
    KEY idx_type          (proposal_type),
    KEY idx_epoch         (proposed_epoch),
    KEY idx_block_time    (block_time),
    KEY idx_expiration    (expiration),
    KEY idx_ga_spo_target (spo_target),
    KEY idx_ga_event_slot (last_event_slot)
);

-- 投票 (DRep / SPO / CC)
-- rationale_ja は OpenAI 翻訳でフェーズ4で埋める
-- last_event_slot は Ogmios listener が VotingProcedures cert を反映した slot (rollback 対応)
CREATE TABLE IF NOT EXISTS proposal_votes (
    id              INT          AUTO_INCREMENT PRIMARY KEY,
    proposal_id     VARCHAR(128) NOT NULL,
    voter_role      VARCHAR(32)  NOT NULL,                    -- DRep / ConstitutionalCommittee / SPO
    voter_id        VARCHAR(128) NOT NULL,
    voter_hex       VARCHAR(128) DEFAULT NULL,
    voter_has_script TINYINT(1)  NOT NULL DEFAULT 0,
    vote            VARCHAR(16)  NOT NULL,                    -- Yes / No / Abstain
    block_time      DATETIME     DEFAULT NULL,
    meta_url        TEXT         DEFAULT NULL,
    meta_hash       VARCHAR(64)  DEFAULT NULL,
    -- 投票メタデータ (CIP-100) の authors[0].name。CC / SPO は名前解決手段が他に無く、
    -- CC は hot key ローテーションで cc_members と紐付かなくなるため投票行に保持する。
    voter_name      VARCHAR(255) DEFAULT NULL,
    rationale       MEDIUMTEXT   DEFAULT NULL,
    rationale_ja    MEDIUMTEXT   DEFAULT NULL,
    meta_fetched_at DATETIME     DEFAULT NULL,
    last_event_slot BIGINT       DEFAULT NULL,
    fetched_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_vote (proposal_id, voter_role, voter_id),
    KEY idx_proposal        (proposal_id),
    KEY idx_role            (voter_role),
    KEY idx_votes_event_slot(last_event_slot)
);

-- 投票集計 (Koios /proposal_voting_summary のキャッシュ)
--
-- *_yes_pct / *_no_pct は Koios が返す「批准判定ベース」の割合で、必ず yes+no=100 になる
-- (CIP-1694 では棄権票は分母から除外されるため)。棄権の割合を出すには分母に棄権を戻す
-- 必要があり、そのために *_vote_power 系の実数値も保持する。
CREATE TABLE IF NOT EXISTS proposal_voting_summary (
    proposal_id                  VARCHAR(128) PRIMARY KEY,
    proposal_type                VARCHAR(50)   DEFAULT NULL,
    epoch_no                     INT           DEFAULT NULL,
    drep_yes_votes_cast          INT           DEFAULT 0,
    drep_no_votes_cast           INT           DEFAULT 0,
    drep_abstain_votes_cast      INT           DEFAULT 0,
    drep_yes_pct                 DECIMAL(6,2)  DEFAULT 0,
    drep_no_pct                  DECIMAL(6,2)  DEFAULT 0,
    drep_yes_vote_power          BIGINT        DEFAULT NULL,
    drep_no_vote_power           BIGINT        DEFAULT NULL,
    drep_active_abstain_vote_power BIGINT      DEFAULT NULL,
    drep_always_abstain_vote_power BIGINT      DEFAULT NULL,
    pool_yes_votes_cast          INT           DEFAULT 0,
    pool_no_votes_cast           INT           DEFAULT 0,
    pool_abstain_votes_cast      INT           DEFAULT 0,
    pool_yes_pct                 DECIMAL(6,2)  DEFAULT 0,
    pool_no_pct                  DECIMAL(6,2)  DEFAULT 0,
    pool_yes_vote_power          BIGINT        DEFAULT NULL,
    pool_no_vote_power           BIGINT        DEFAULT NULL,
    pool_active_abstain_vote_power BIGINT      DEFAULT NULL,
    pool_passive_always_abstain_vote_power BIGINT DEFAULT NULL,
    committee_yes_votes_cast     INT           DEFAULT 0,
    committee_no_votes_cast      INT           DEFAULT 0,
    committee_abstain_votes_cast INT           DEFAULT 0,
    committee_yes_pct            DECIMAL(6,2)  DEFAULT 0,
    committee_no_pct             DECIMAL(6,2)  DEFAULT 0,
    updated_at                   DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- プロトコルパラメータ (id=1 固定の単一行)
CREATE TABLE IF NOT EXISTS protocol_params (
    id                          INT            PRIMARY KEY,
    epoch_no                    INT            DEFAULT NULL,
    -- DRep voting thresholds
    dvt_motion_no_confidence    DECIMAL(10,8)  DEFAULT NULL,
    dvt_committee_normal        DECIMAL(10,8)  DEFAULT NULL,
    dvt_committee_no_confidence DECIMAL(10,8)  DEFAULT NULL,
    dvt_update_to_constitution  DECIMAL(10,8)  DEFAULT NULL,
    dvt_hard_fork_initiation    DECIMAL(10,8)  DEFAULT NULL,
    dvt_p_p_network_group       DECIMAL(10,8)  DEFAULT NULL,
    dvt_p_p_economic_group      DECIMAL(10,8)  DEFAULT NULL,
    dvt_p_p_technical_group     DECIMAL(10,8)  DEFAULT NULL,
    dvt_p_p_gov_group           DECIMAL(10,8)  DEFAULT NULL,
    dvt_treasury_withdrawal     DECIMAL(10,8)  DEFAULT NULL,
    -- SPO voting thresholds
    pvt_motion_no_confidence    DECIMAL(10,8)  DEFAULT NULL,
    pvt_committee_normal        DECIMAL(10,8)  DEFAULT NULL,
    pvt_committee_no_confidence DECIMAL(10,8)  DEFAULT NULL,
    pvt_hard_fork_initiation    DECIMAL(10,8)  DEFAULT NULL,
    pvtpp_security_group        DECIMAL(10,8)  DEFAULT NULL,
    -- 憲法委員会 quorum (CIP-1694)
    cc_quorum_numerator         INT            DEFAULT NULL,
    cc_quorum_denominator       INT            DEFAULT NULL,
    -- Committee / deposit 関連
    committee_min_size          INT            DEFAULT NULL,
    committee_max_term_length   INT            DEFAULT NULL,
    gov_action_lifetime         INT            DEFAULT NULL,
    gov_action_deposit          BIGINT         DEFAULT NULL,
    drep_deposit                BIGINT         DEFAULT NULL,
    drep_activity               INT            DEFAULT NULL,
    updated_at                  DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 憲法委員会メンバー (display_name は運用で手動編集)
CREATE TABLE IF NOT EXISTS cc_members (
    cc_cold_id         VARCHAR(128) PRIMARY KEY,
    cc_cold_hex        VARCHAR(128) DEFAULT NULL,
    cc_hot_id          VARCHAR(128) DEFAULT NULL,
    cc_hot_hex         VARCHAR(128) DEFAULT NULL,
    status             VARCHAR(32)  DEFAULT NULL,             -- authorized / resigned / expired / unrecognized 等
    expiration_epoch   INT          DEFAULT NULL,
    cc_hot_has_script  TINYINT(1)   DEFAULT 0,
    cc_cold_has_script TINYINT(1)   DEFAULT 0,
    display_name       VARCHAR(255) DEFAULT NULL,
    updated_at         DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
