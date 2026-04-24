-- 024_proposal_votes.sql
-- GA 詳細ページ用: ガバナンスアクションに対する投票キャッシュ
-- Koios /proposal_votes のレスポンスをキャッシュし、ページは DB を読むだけにする。
-- 同期は notify_worker.py --event vote_sync

CREATE TABLE IF NOT EXISTS proposal_votes (
  id            INT            AUTO_INCREMENT PRIMARY KEY,
  proposal_id   VARCHAR(128)   NOT NULL,
  voter_role    VARCHAR(32)    NOT NULL,          -- DRep / ConstitutionalCommittee / SPO
  voter_id      VARCHAR(128)   NOT NULL,
  voter_hex     VARCHAR(128)   DEFAULT NULL,
  voter_has_script TINYINT(1)  NOT NULL DEFAULT 0,
  vote          VARCHAR(16)    NOT NULL,           -- Yes / No / Abstain
  block_time    DATETIME       DEFAULT NULL,
  meta_url      TEXT           DEFAULT NULL,
  meta_hash     VARCHAR(64)    DEFAULT NULL,
  rationale     MEDIUMTEXT     DEFAULT NULL,       -- メタデータから抽出した投票理由（原文）
  rationale_ja  MEDIUMTEXT     DEFAULT NULL,       -- 日本語翻訳（Phase 4 で埋める）
  meta_fetched_at DATETIME     DEFAULT NULL,       -- 投票メタデータ取得日時（未取得判定用）
  fetched_at    DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_vote (proposal_id, voter_role, voter_id),
  KEY idx_proposal (proposal_id),
  KEY idx_role     (voter_role)
);
