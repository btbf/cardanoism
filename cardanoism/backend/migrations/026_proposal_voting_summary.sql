-- 026_proposal_voting_summary.sql
-- 各ガバナンスアクションの投票集計キャッシュ。Koios /proposal_voting_summary のレスポンスを格納。
-- proposal_id を PRIMARY KEY にして、GA ごとに 1 行保持する。
-- 同期は notify_worker.py --event vote_sync と同時に更新する想定。

CREATE TABLE IF NOT EXISTS proposal_voting_summary (
  proposal_id                       VARCHAR(128) PRIMARY KEY,
  proposal_type                     VARCHAR(50)   DEFAULT NULL,
  epoch_no                          INT           DEFAULT NULL,
  -- DRep
  drep_yes_votes_cast               INT           DEFAULT 0,
  drep_no_votes_cast                INT           DEFAULT 0,
  drep_abstain_votes_cast           INT           DEFAULT 0,
  drep_yes_pct                      DECIMAL(6,2)  DEFAULT 0,
  drep_no_pct                       DECIMAL(6,2)  DEFAULT 0,
  -- Pool (SPO)
  pool_yes_votes_cast               INT           DEFAULT 0,
  pool_no_votes_cast                INT           DEFAULT 0,
  pool_abstain_votes_cast           INT           DEFAULT 0,
  pool_yes_pct                      DECIMAL(6,2)  DEFAULT 0,
  pool_no_pct                       DECIMAL(6,2)  DEFAULT 0,
  -- Committee
  committee_yes_votes_cast          INT           DEFAULT 0,
  committee_no_votes_cast           INT           DEFAULT 0,
  committee_abstain_votes_cast      INT           DEFAULT 0,
  committee_yes_pct                 DECIMAL(6,2)  DEFAULT 0,
  committee_no_pct                  DECIMAL(6,2)  DEFAULT 0,
  updated_at                        DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
