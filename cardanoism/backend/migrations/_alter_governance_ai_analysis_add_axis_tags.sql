-- ============================================================
-- _alter_governance_ai_analysis_add_axis_tags.sql
--
-- 既存の本番 / preview DB に対して governance_ai_analysis.axis_tags_json
-- 列を追加する「一時マイグレーション」。新規環境では
-- 011_governance_ai_analysis.sql の CREATE TABLE に既に含まれているため不要。
--
-- 用途:
--   drep-match v3 で GA per-axis 分類タグを保存する。
--   ga_ai_worker.py が GA 分析時に AI 抽出した axis_tags を JSON で書き込む。
--   drep_compass/profile.py がこれを集計してユーザー側 axis スコアを算出する。
--
--   axis_tags_json 構造例:
--     {
--       "treasury_size":     "large",
--       "priority":          "technical",
--       "org_recipient":     ["IO", "other"],
--       "protocol_change":   "n_a",
--       "marketing_purpose": "no",
--       "kpi_clarity":       "clear",
--       "risk_level":        "low",
--       "summary_ja":        "...",
--       "reasoning": { ... 各 axis ごとの判定理由 ... }
--     }
--
-- 適用後、このファイルはリポジトリに残してよい (冪等)。番号付きの統合スキーマ
-- には追加しない (移行用 ALTER は migrations 番号付きには載せない方針)。
--
-- 適用例:
--   mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < _alter_governance_ai_analysis_add_axis_tags.sql
--
-- 適用後の挙動:
--   - 全行 axis_tags_json IS NULL の状態でスタート
--   - 既存 GA の backfill: ga_ai_worker.py --reanalyze --all を 1 回流す
--     (全 600 GA 程度 × $0.01 ≒ $6-10)
--   - 以降は新規 GA の AI 分析時に自動付与
-- ============================================================

ALTER TABLE governance_ai_analysis
  ADD COLUMN IF NOT EXISTS axis_tags_json TEXT DEFAULT NULL
  COMMENT 'drep-match v3: 7 axis 分類タグ (JSON)'
  AFTER rule_checks_json;
