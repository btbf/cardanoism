-- ============================================================
-- 020_drep_compass_collation_fix.sql
-- migration 018 で作った compass テーブル群の collation を、既存テーブル
-- (dreps / governance_actions / proposal_votes) と一致させる。
--
-- 問題:
--   018 は `DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci` と
--   明示してテーブルを作ったが、本番 / staging DB のデフォルト collation
--   は MariaDB 10.10+ の `utf8mb4_uca1400_ai_ci`。
--   JOIN drep_profiles ↔ dreps の VARCHAR 比較で
--     Illegal mix of collations
--   が発生する。
--
-- 修正:
--   3 テーブルを CHARACTER SET utf8mb4 のまま CONVERT TO で
--   DB デフォルト collation に揃える (CONVERT TO CHARACTER SET utf8mb4
--   は collation 句を省略すれば DB デフォルトを使う)。
-- ============================================================

ALTER TABLE gov_action_tags          CONVERT TO CHARACTER SET utf8mb4;
ALTER TABLE drep_profiles            CONVERT TO CHARACTER SET utf8mb4;
ALTER TABLE user_drep_compass_answers CONVERT TO CHARACTER SET utf8mb4;
