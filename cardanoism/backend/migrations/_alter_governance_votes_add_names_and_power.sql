-- ============================================================
-- _alter_governance_votes_add_names_and_power.sql
--
-- 既存の本番 / preview DB に対して以下を追加する「一時マイグレーション」。
-- 新規環境では 004_governance.sql の CREATE TABLE に含まれているため不要。
--
-- 1) proposal_votes.voter_name
--    投票メタデータ (CIP-100) の authors[0].name。
--    CC / SPO は dreps のような名前テーブルが無く、さらに CC は hot key を
--    ローテーションするため cc_members との突き合わせが将来壊れる。投票行そのものに
--    名前を持たせることで、鍵が変わっても過去の投票に名前が残る。
--    埋めるバッチ: notify_worker.py --event vote_rationale_sync
--
-- 2) proposal_voting_summary.*_vote_power
--    Koios の *_yes_pct / *_no_pct は批准判定ベース (棄権を分母から除外) のため
--    常に yes+no=100 になり、棄権の割合を再現できない。棄権率を出すために
--    投票力の実数を保持する。
--    埋めるバッチ: notify_worker.py --event summary_sync
--
-- 適用例:
--   mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < _alter_governance_votes_add_names_and_power.sql
-- ============================================================

ALTER TABLE proposal_votes
  ADD COLUMN IF NOT EXISTS voter_name VARCHAR(255) DEFAULT NULL
  COMMENT '投票メタデータ (CIP-100) authors[0].name'
  AFTER meta_hash;

ALTER TABLE proposal_voting_summary
  ADD COLUMN IF NOT EXISTS drep_yes_vote_power            BIGINT DEFAULT NULL AFTER drep_no_pct,
  ADD COLUMN IF NOT EXISTS drep_no_vote_power             BIGINT DEFAULT NULL AFTER drep_yes_vote_power,
  ADD COLUMN IF NOT EXISTS drep_active_abstain_vote_power BIGINT DEFAULT NULL AFTER drep_no_vote_power,
  ADD COLUMN IF NOT EXISTS drep_always_abstain_vote_power BIGINT DEFAULT NULL AFTER drep_active_abstain_vote_power,
  ADD COLUMN IF NOT EXISTS pool_yes_vote_power            BIGINT DEFAULT NULL AFTER pool_no_pct,
  ADD COLUMN IF NOT EXISTS pool_no_vote_power             BIGINT DEFAULT NULL AFTER pool_yes_vote_power,
  ADD COLUMN IF NOT EXISTS pool_active_abstain_vote_power BIGINT DEFAULT NULL AFTER pool_no_vote_power,
  ADD COLUMN IF NOT EXISTS pool_passive_always_abstain_vote_power BIGINT DEFAULT NULL AFTER pool_active_abstain_vote_power;
