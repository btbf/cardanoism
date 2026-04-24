-- 021_governance_withdrawal.sql
-- TreasuryWithdrawals タイプの GA に引き出し情報を保持するカラムを追加
-- Koios /proposal_list.withdrawal は [{amount, stake_address}, ...] の配列
-- 合計 lovelace は集計済みで保持（表示・フィルタ・ソート用）
-- 内訳（配列）は JSON 文字列で保持（複数受取先の場合の表示用）

ALTER TABLE governance_actions
  ADD COLUMN withdrawal_total_lovelace BIGINT DEFAULT NULL AFTER deposit,
  ADD COLUMN withdrawal_json           TEXT   DEFAULT NULL AFTER withdrawal_total_lovelace;
