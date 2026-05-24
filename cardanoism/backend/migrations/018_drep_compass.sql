-- ============================================================
-- 018_drep_compass.sql
-- DRep委任コンパス (MVP) 用テーブル
--
-- 既存マッチング診断 (016/017) とは独立した新機能。
-- - axis_profile_json (017) は 5 軸の派閥モデル
-- - drep_profiles (本 migration) は 11 axis の価値観モデル
-- 両者は並走可能で、本 PR では UI には公開しない (内部実装のみ)。
--
-- 設計詳細は spec を参照。Cardanoism独自タグ (gov_action_tags) は
-- 公式オンチェーンデータと分離して保存する。
-- ============================================================

-- ── 1. Cardanoism独自タグ (Governance Action × tag) ─────────
-- 1 GA に対して複数行 (1 tag = 1 row)。tag_type は 3 系統:
--   category  : treasury / protocol / ecosystem / marketing / ...
--   attribute : large_budget / existing_entity / open_source / ...
--   quality   : kpi_defined / budget_unclear / track_record_strong / ...
-- source = "rule" (rule-based classifier) / "ai" / "manual" を区別する。
CREATE TABLE IF NOT EXISTS gov_action_tags (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  gov_action_id   VARCHAR(128) NOT NULL
                  COMMENT 'governance_actions.proposal_id への参照',
  tag             VARCHAR(64)  NOT NULL
                  COMMENT 'taxonomy 定義済みのタグキー',
  tag_type        ENUM('category','attribute','quality') NOT NULL,
  confidence      DECIMAL(4,3) NOT NULL DEFAULT 1.000
                  COMMENT '分類の確信度 0.0〜1.0 (rule は通常 1.0、ai は 0.5〜0.9)',
  source          ENUM('rule','ai','manual') NOT NULL DEFAULT 'rule',
  rationale       TEXT DEFAULT NULL
                  COMMENT '分類理由 (どのキーワードがヒットしたか等)',
  reviewed_by     VARCHAR(128) DEFAULT NULL
                  COMMENT 'manual の場合のレビュー担当者 ID',
  reviewed_at     DATETIME DEFAULT NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ga_tag_source (gov_action_id, tag, source),
  INDEX ix_gat_ga    (gov_action_id),
  INDEX ix_gat_tag   (tag),
  INDEX ix_gat_type  (tag_type)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 2. DRep プロファイル (11 axis 価値観モデル) ─────────────
-- 1 DRep につき 1 行。calculate_drep_profile() が定期的に再計算する。
CREATE TABLE IF NOT EXISTS drep_profiles (
  drep_id                    VARCHAR(128) PRIMARY KEY,
  profile_json               LONGTEXT DEFAULT NULL
                             COMMENT '11 axis の final_score 0.0〜1.0 (JSON)',
  confidence_json            LONGTEXT DEFAULT NULL
                             COMMENT '11 axis の confidence 0.0〜1.0 (JSON)',
  raw_score_json             LONGTEXT DEFAULT NULL
                             COMMENT '11 axis の生 raw score -1.0〜+1.0 (JSON、debug 用)',
  participation_rate         DECIMAL(5,4) NOT NULL DEFAULT 0.0000
                             COMMENT '投票参加率 0.0〜1.0 (Abstain 含む)',
  reasoning_disclosure_rate  DECIMAL(5,4) NOT NULL DEFAULT 0.0000
                             COMMENT '投票理由 (rationale / meta_url) 公開率 0.0〜1.0',
  analyzed_vote_count        INT NOT NULL DEFAULT 0
                             COMMENT '分析対象になった投票件数 (Yes+No+Abstain)',
  eligible_action_count      INT NOT NULL DEFAULT 0
                             COMMENT '対象となった GA 件数 (参加率の母数)',
  analysis_version           VARCHAR(32) NOT NULL DEFAULT 'compass-mvp-v1'
                             COMMENT 'プロファイルアルゴリズムのバージョン',
  evidence_json              LONGTEXT DEFAULT NULL
                             COMMENT 'axis ごとの根拠サマリ (axis: [{gov_action_id, tag, vote}])',
  calculated_at              DATETIME DEFAULT NULL,
  updated_at                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 3. ユーザーアンケート回答保存 ──────────────────────────
-- ログイン済みなら user_id、未ログインなら session_id を使う (どちらか必須)
CREATE TABLE IF NOT EXISTS user_drep_compass_answers (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id         INT DEFAULT NULL,
  session_id      VARCHAR(64)  DEFAULT NULL,
  answer_json     LONGTEXT NOT NULL
                  COMMENT '10 問の 1-5 Likert 回答 JSON ({q_id: 1-5, ...})',
  importance_json LONGTEXT NOT NULL DEFAULT '[]'
                  COMMENT 'ユーザーが重要視した質問 ID リスト (最大 3 個)',
  questionnaire_version VARCHAR(32) NOT NULL DEFAULT 'compass-mvp-v1',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_compass_user    (user_id),
  INDEX ix_compass_session (session_id)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
