-- ============================================================
-- 021_match_v2_cleanup.sql
-- DRepマッチング診断 v2 (7 axis AI 主導) への移行に伴う旧データ撤去
--
-- v1 (gov_action_tags ベース) から v2 (AI 直接分析) に切り替える際に、
-- 旧テーブル / 旧データを drop / 初期化する。
--
-- 1. gov_action_tags テーブル: 廃止 (AI が DRep を直接読むため不要)
-- 2. drep_profiles: v1 のデータは互換性なし → 全 row truncate
--    (analysis_version で v2 か判定できるが、明示的に空にして再生成を強制)
-- 3. user_drep_compass_answers: questionnaire_version 互換性なし → truncate
-- ============================================================

DROP TABLE IF EXISTS gov_action_tags;

-- v1 で計算した row は v2 と axis 体系が違うので全削除して再生成
TRUNCATE TABLE drep_profiles;

-- v1 questionnaire の回答は v2 設問と互換性なし
TRUNCATE TABLE user_drep_compass_answers;
