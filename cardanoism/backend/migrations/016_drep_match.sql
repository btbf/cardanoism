-- ============================================================
-- 016_drep_match.sql
-- DRep マッチング診断 v2 (最終形)
--
-- - 9 問の二者択一+迷うアンケート (questionnaire-version='match-v2') で
--   ユーザーの 7 axis 価値観ベクトルを取得
-- - drep_profiles に AI 生成の 7 axis スコア + 信頼度 + サマリ (JA/EN) を保存
-- - 同期: notify_worker.py --event compass_profile_all (daily cron)
--
-- 7 axes: treasury / priority / org / protocol / transparency / risk / marketing
--
-- 関連ドキュメント: docs/drep-match.md
--
-- 過去の経緯 (削除済みマイグレーション):
--   旧 016/017: 9 topic + 5 axis モデル (廃止、19 で drop)
--   旧 018:     11 axis 価値観 + gov_action_tags (廃止、21 で drop)
--   旧 019:     016/017 ALTER 列の drop (fresh deploy では不要)
--   旧 020:     018 テーブルの collation 修正 (fresh deploy では不要)
--   旧 021:     11 axis → 7 axis 移行 cleanup (fresh deploy では不要)
--   旧 022:     summary 列追加 (本ファイルに統合)
--   旧 023:     dreps.meta_fetched_hash (005_dreps.sql に統合)
--   旧 024:     summary_en 列追加 (本ファイルに統合)
-- ============================================================

-- ── DRep プロファイル (AI 生成、7 axis + サマリ) ──────────────
CREATE TABLE IF NOT EXISTS drep_profiles (
  drep_id                    VARCHAR(128) PRIMARY KEY,
  profile_json               LONGTEXT DEFAULT NULL
                             COMMENT '7 axis スコア 0.0〜1.0 (JSON)',
  confidence_json            LONGTEXT DEFAULT NULL
                             COMMENT '7 axis 信頼度 0.0〜1.0 (JSON)',
  raw_score_json             LONGTEXT DEFAULT NULL
                             COMMENT '互換用、v2 では NULL',
  summary                    TEXT DEFAULT NULL
                             COMMENT 'AI 生成サマリ (日本語、1 行)',
  summary_en                 TEXT DEFAULT NULL
                             COMMENT 'AI 生成サマリ (英語、1 行)',
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

-- ── ユーザーアンケート回答 (9 問 × 1-3 値、最大 3 項目の重要マーク付き) ──
CREATE TABLE IF NOT EXISTS user_drep_compass_answers (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id         INT DEFAULT NULL,
  session_id      VARCHAR(64)  DEFAULT NULL,
  answer_json     LONGTEXT NOT NULL
                  COMMENT '9 問の 1/2/3 回答 JSON ({q_id: 1-3, ...})',
  importance_json LONGTEXT NOT NULL DEFAULT (JSON_ARRAY())
                  COMMENT '重要マーク q_id リスト (最大 3)',
  questionnaire_version VARCHAR(32) NOT NULL DEFAULT 'match-v2',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_match_user    (user_id),
  INDEX ix_match_session (session_id)
) DEFAULT CHARSET=utf8mb4;
