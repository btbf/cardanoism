-- ============================================================
-- 016_drep_topic_match.sql
-- DRep マッチング診断（/governance/drep の「マッチング診断」タブ）用カラム追加
--
-- - governance_ai_analysis.topic_tags_json
--     AI が GA を 8 トピック（core_dev / research / education / community /
--     defi / enterprise / product / governance、該当なしは other）に分類した結果。
--     JSON 配列。例: ["education","community"]
--
-- - dreps.topic_profile_json
--     DRep × トピックの Yes 率を集計したベクトル。JSON。
--     例: {"core_dev":0.85,"research":0.60,"education":1.0,...}
--     母数 = Yes + No 票 (Abstain は除外)
--
-- - dreps.topic_vote_count
--     profile 算出に使った投票件数（Yes + No）。< 5 はデータ不足としてマッチング
--     対象外に振り分ける UI 用。
-- ============================================================

ALTER TABLE governance_ai_analysis
  ADD COLUMN IF NOT EXISTS topic_tags_json TEXT DEFAULT NULL
  COMMENT 'AI 分類トピック (JSON 配列、例: ["core_dev","research"])';

ALTER TABLE dreps
  ADD COLUMN IF NOT EXISTS topic_profile_json TEXT DEFAULT NULL
  COMMENT 'DRep × トピックの Yes 率 (JSON、例: {"core_dev":0.85,...})';

ALTER TABLE dreps
  ADD COLUMN IF NOT EXISTS topic_vote_count INT NOT NULL DEFAULT 0
  COMMENT 'topic_profile 算出に使った投票件数 (Yes+No)。< 5 はデータ不足';
