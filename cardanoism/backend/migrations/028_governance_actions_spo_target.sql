-- ============================================================
-- 028_governance_actions_spo_target.sql
-- governance_actions に SPO 投票対象判定カラムを追加。
--
-- spo_target:
--   NULL = 未判定 (legacy データ)
--   0    = SPO は投票対象外 (TreasuryWithdrawals / NewConstitution / security group 以外の ParameterChange)
--   1    = SPO 投票対象 (HardForkInitiation / NoConfidence / UpdateCommittee / InfoAction /
--           security group 関連の ParameterChange)
--
-- CIP-1694 の SPO 投票対象規定に基づく判定:
--   - HardForkInitiation : 必須
--   - NoConfidence       : 必須
--   - UpdateCommittee    : 必須
--   - ParameterChange    : security group のサブグループのみ条件付き
--   - InfoAction         : 任意 (意見表明)
--   - TreasuryWithdrawals: 対象外
--   - NewConstitution    : 対象外
-- ============================================================

ALTER TABLE governance_actions
    ADD COLUMN IF NOT EXISTS spo_target TINYINT(1) DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_ga_spo_target ON governance_actions(spo_target);
