-- ============================================================
-- 022_drep_profiles_summary.sql
-- drep_profiles に summary 列を追加 (AI 生成の 1 行サマリ)
-- ============================================================

ALTER TABLE drep_profiles
  ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT NULL
  COMMENT 'AI 生成の 1 行サマリ (日本語)';
