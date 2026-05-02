-- ============================================================
-- 017_governance_ai_analysis.sql
-- GA AI 分析結果のキャッシュ + ジョブステート管理
--
-- ステート遷移:
--   pending → analyzing → analyzed
--                       ↘ failed (再試行可能)
--
-- 同期は Ogmios リスナーが GA 提出を検知して enqueue (status='pending') し、
-- Semaphore(3) のジョブワーカーが atomic claim で processing する設計。
-- ============================================================

CREATE TABLE IF NOT EXISTS governance_ai_analysis (
    proposal_id               VARCHAR(255) NOT NULL PRIMARY KEY,
    status                    VARCHAR(16)  NOT NULL DEFAULT 'pending',
    worker_id                 VARCHAR(64)  DEFAULT NULL,
    started_at                DATETIME     DEFAULT NULL,
    completed_at              DATETIME     DEFAULT NULL,
    attempts                  INT          NOT NULL DEFAULT 0,
    last_error                TEXT         DEFAULT NULL,
    constitution_score        TINYINT      DEFAULT NULL,
    constitution_verdict_ja   VARCHAR(64)  DEFAULT NULL,
    constitution_verdict_en   VARCHAR(64)  DEFAULT NULL,
    constitution_summary_ja   TEXT         DEFAULT NULL,
    constitution_summary_en   TEXT         DEFAULT NULL,
    articles_json             TEXT         DEFAULT NULL,
    concerns_ja_json          TEXT         DEFAULT NULL,
    concerns_en_json          TEXT         DEFAULT NULL,
    pillars_json              TEXT         DEFAULT NULL,
    related_kpis_json         TEXT         DEFAULT NULL,
    model_id                  VARCHAR(64)  DEFAULT NULL,
    constitution_meta_url     TEXT         DEFAULT NULL,
    tokens_input              INT          DEFAULT NULL,
    tokens_output             INT          DEFAULT NULL,
    cost_usd                  DECIMAL(10,6) DEFAULT NULL,
    enqueued_at               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_status        (status),
    KEY idx_started_at    (started_at),
    KEY idx_completed_at  (completed_at)
);
