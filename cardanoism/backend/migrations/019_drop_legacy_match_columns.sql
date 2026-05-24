-- ============================================================
-- 019_drop_legacy_match_columns.sql
-- 旧 DRep マッチング診断 (016/017) で追加されたカラムを drop する。
--
-- 旧モデル:
--   - 016: 9 topic_tags_json (governance_ai_analysis) +
--          topic_profile_json / topic_vote_count (dreps)
--   - 017: 5 axis_tags_json (governance_ai_analysis) +
--          axis_profile_json / axis_vote_count (dreps)
--
-- これらは 018_drep_compass.sql で導入された 11 axis モデル (gov_action_tags
-- + drep_profiles) に完全置換されたため不要。
-- ============================================================

ALTER TABLE governance_ai_analysis
  DROP COLUMN IF EXISTS topic_tags_json;

ALTER TABLE governance_ai_analysis
  DROP COLUMN IF EXISTS axis_tags_json;

ALTER TABLE dreps
  DROP COLUMN IF EXISTS topic_profile_json;

ALTER TABLE dreps
  DROP COLUMN IF EXISTS topic_vote_count;

ALTER TABLE dreps
  DROP COLUMN IF EXISTS axis_profile_json;

ALTER TABLE dreps
  DROP COLUMN IF EXISTS axis_vote_count;
