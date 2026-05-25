-- ============================================================
-- 021_match_v2_cleanup.sql
-- DRepマッチング診断 v2 (7 axis / AI 主導) のスキーマを冪等に確立する。
--
-- このマイグレーションは下記のいずれの状態からでも v2 スキーマに揃う:
--   - 018 / 019 / 020 を流していない環境 (テーブル無し)
--   - 018 だけ流した環境 (v1 スキーマ)
--   - 018 + 020 を流した環境 (v1 + collation 修正済み)
--
-- 内容:
--   1. 旧 gov_action_tags を drop (v2 では不要)
--   2. drep_profiles を drop + 再作成 (v2 スキーマ + summary 列)
--   3. user_drep_compass_answers を drop + 再作成
--
-- 注意: 旧データは全て失われる (v2 では再生成される設計)
-- ============================================================

-- 1. v1 の GA タグテーブルは廃止
DROP TABLE IF EXISTS gov_action_tags;

-- 2. drep_profiles を v2 スキーマで再作成
DROP TABLE IF EXISTS drep_profiles;
CREATE TABLE drep_profiles (
  drep_id                    VARCHAR(128) PRIMARY KEY,
  profile_json               LONGTEXT DEFAULT NULL
                             COMMENT '7 axis スコア 0.0〜1.0 (JSON)',
  confidence_json            LONGTEXT DEFAULT NULL
                             COMMENT '7 axis 信頼度 0.0〜1.0 (JSON)',
  raw_score_json             LONGTEXT DEFAULT NULL
                             COMMENT '互換用、v2 では NULL',
  summary                    TEXT DEFAULT NULL
                             COMMENT 'AI 生成の 1 行サマリ (日本語)',
  participation_rate         DECIMAL(5,4) NOT NULL DEFAULT 1.0000
                             COMMENT 'v2 では 1.0 固定 (実投票のみが母数)',
  reasoning_disclosure_rate  DECIMAL(5,4) NOT NULL DEFAULT 0.0000
                             COMMENT '投票理由公開率 0.0〜1.0',
  analyzed_vote_count        INT NOT NULL DEFAULT 0
                             COMMENT '分析した Yes+No+Abstain 票数',
  eligible_action_count      INT NOT NULL DEFAULT 0
                             COMMENT 'v2 では analyzed_vote_count と同値',
  analysis_version           VARCHAR(32) NOT NULL DEFAULT 'match-v2'
                             COMMENT 'アルゴリズム version',
  evidence_json              LONGTEXT DEFAULT NULL
                             COMMENT 'axis ごとの根拠 (AI 出力、JSON)',
  calculated_at              DATETIME DEFAULT NULL,
  updated_at                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP
) DEFAULT CHARSET=utf8mb4;

-- 3. user_drep_compass_answers を v2 スキーマで再作成
DROP TABLE IF EXISTS user_drep_compass_answers;
CREATE TABLE user_drep_compass_answers (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id         INT DEFAULT NULL,
  session_id      VARCHAR(64)  DEFAULT NULL,
  answer_json     LONGTEXT NOT NULL
                  COMMENT '10 問の 1/2/3 回答 JSON ({q_id: 1-3, ...})',
  importance_json LONGTEXT NOT NULL DEFAULT (JSON_ARRAY())
                  COMMENT '重要マーク q_id リスト (最大 3)',
  questionnaire_version VARCHAR(32) NOT NULL DEFAULT 'match-v2',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_match_user    (user_id),
  INDEX ix_match_session (session_id)
) DEFAULT CHARSET=utf8mb4;
