-- ============================================================
-- 024_drep_profiles_summary_en.sql
--
-- drep_profiles.summary_en 列を追加 (AI 生成サマリの英語版)。
--
-- 既存の `summary` は日本語サマリのまま (旧設計の名残でカラム名は無印だが
-- 実体は JA)。今後はユーザー言語に応じて summary (JA) / summary_en を切替表示。
--
-- 既存行の summary_en は NULL。次の compass_profile_all 実行で全件 backfill 必要。
-- フォールバック: UI 側で summary_en が空なら summary (JA) を表示する。
-- ============================================================

ALTER TABLE drep_profiles
  ADD COLUMN IF NOT EXISTS summary_en TEXT DEFAULT NULL
  COMMENT 'AI 生成サマリ (英語、1 行)';
