-- 005_stake_address_role_abstain.sql
-- stake_addresses.role に 'abstain'（棄権）を追加

ALTER TABLE stake_addresses
  MODIFY COLUMN role ENUM('delegator', 'drep', 'abstain') NOT NULL DEFAULT 'delegator';
