-- ============================================================
-- 011_governance_ai_analysis.sql
-- GA AI 分析結果のキャッシュ + ジョブステート管理 (ファクト整理ベース)
--
-- ステート遷移:
--   pending → analyzing → analyzed
--                       ↘ failed (再試行可能)
--
-- 同期は Ogmios リスナーが GA 提出を検知して enqueue (status='pending') し、
-- Semaphore(3) のジョブワーカーが atomic claim で processing する設計。
--
-- カラム設計はスコア / verdict / KPI 等の主観判定を排した
-- 「ファクト整理」方針に統一済み (cf. CLAUDE.md GA AI 分析セクション):
--   constitution_summary_*  → 提案概要
--   articles_json           → 関連条文 (引用と理由のみ、スコア無し)
--   proposal_facts_json     → AI が抽出した提案の主要ファクト
--   rule_checks_json        → ルールベースの自動チェック結果
-- ============================================================

CREATE TABLE IF NOT EXISTS governance_ai_analysis (
    proposal_id               VARCHAR(255) NOT NULL PRIMARY KEY,
    status                    VARCHAR(16)  NOT NULL DEFAULT 'pending',
    worker_id                 VARCHAR(64)  DEFAULT NULL,
    started_at                DATETIME     DEFAULT NULL,
    completed_at              DATETIME     DEFAULT NULL,
    attempts                  INT          NOT NULL DEFAULT 0,
    last_error                TEXT         DEFAULT NULL,
    constitution_summary_ja   TEXT         DEFAULT NULL,
    constitution_summary_en   TEXT         DEFAULT NULL,
    articles_json             TEXT         DEFAULT NULL,
    proposal_facts_json       TEXT         DEFAULT NULL,
    rule_checks_json          TEXT         DEFAULT NULL,
    axis_tags_json            TEXT         DEFAULT NULL,               -- drep-match v3: 7 axis 分類タグ (treasury_size / priority / org_recipient / protocol_change / marketing_purpose / kpi_clarity / risk_level + reasoning)
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
