-- 027_cc_quorum.sql
-- 憲法委員会（CC）の quorum 閾値を protocol_params に追加。
-- CIP-1694 では CC の投票閾値は committee_info.quorum_numerator / quorum_denominator で決まる。
-- 現在 mainnet は 2/3。

ALTER TABLE protocol_params
  ADD COLUMN cc_quorum_numerator   INT DEFAULT NULL,
  ADD COLUMN cc_quorum_denominator INT DEFAULT NULL;
