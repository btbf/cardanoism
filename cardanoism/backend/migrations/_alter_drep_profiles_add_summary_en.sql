-- ============================================================
-- _alter_drep_profiles_add_summary_en.sql
--
-- 既存の本番 / preview DB に対して drep_profiles.summary_en 列を追加する
-- 「一時マイグレーション」。新規環境では 016_drep_match.sql の CREATE TABLE
-- に既に summary_en TEXT が含まれているため不要。
--
-- 用途:
--   AI 生成サマリの英語版を保存。EN UI でマッチング診断結果カードに表示する
--   ためのデータソース。
--   既存の summary 列は日本語サマリのまま (旧設計の名残でカラム名は無印だが
--   実体は JA)。
--
-- 適用後、このファイルはリポジトリに残してよい (冪等)。番号付きの統合スキーマ
-- には追加しない (移行用 ALTER は migrations 番号付きには載せない方針)。
--
-- 適用例:
--   mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < _alter_drep_profiles_add_summary_en.sql
--
-- 適用後の挙動:
--   - 全行 summary_en IS NULL の状態でスタート
--   - 次回 compass_profile_all 実行 (45 6 * * * の daily cron) で全件 backfill
--   - 過渡期 (backfill 前) は EN UI でも JA サマリにフォールバック表示
--     (governance_drep.py の rx.cond で summary_en 空なら summary を使う)
-- ============================================================

ALTER TABLE drep_profiles
  ADD COLUMN IF NOT EXISTS summary_en TEXT DEFAULT NULL
  COMMENT 'AI 生成サマリ (英語、1 行)'
  AFTER summary;
