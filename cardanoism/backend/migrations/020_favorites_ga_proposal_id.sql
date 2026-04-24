-- 020_favorites_ga_proposal_id.sql
-- ガバナンスお気に入りのキーを proposal_tx_hash → proposal_id に移行する。
-- 1 Tx に複数 GA を含められる仕様のため proposal_tx_hash はユニークでない。
-- 複数 GA が紐付く tx は proposal_index が最小（通常 0）の GA の proposal_id に寄せる。

UPDATE favorites f
JOIN (
    SELECT proposal_tx_hash, MIN(proposal_index) AS min_idx
    FROM governance_actions
    GROUP BY proposal_tx_hash
) m ON m.proposal_tx_hash = f.proposal_uuid
JOIN governance_actions g
    ON g.proposal_tx_hash = m.proposal_tx_hash
   AND g.proposal_index  = m.min_idx
SET f.proposal_uuid = g.proposal_id
WHERE f.type = 'governance'
  AND f.proposal_uuid <> g.proposal_id;
