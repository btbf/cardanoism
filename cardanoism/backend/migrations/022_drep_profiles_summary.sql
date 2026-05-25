-- ============================================================
-- 022_drep_profiles_summary.sql
-- 旧設計の名残。021 で drep_profiles を再作成する際に summary 列を
-- 含めるよう変更したため、本ファイルは no-op になった。
--
-- 既に 021 を流していれば drep_profiles に summary 列がある状態。
-- ALTER TABLE ... ADD COLUMN IF NOT EXISTS は MariaDB 10.0.2+ で動作。
-- ============================================================

ALTER TABLE drep_profiles
  ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT NULL
  COMMENT 'AI 生成の 1 行サマリ (日本語)';
