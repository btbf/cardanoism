-- 006_stake_address_drep_info.sql
-- 委任先DRep情報を stake_addresses に追加

ALTER TABLE stake_addresses
  ADD COLUMN delegated_drep_id VARCHAR(255) DEFAULT NULL AFTER role_checked_at,
  ADD COLUMN delegated_drep_name VARCHAR(255) DEFAULT NULL AFTER delegated_drep_id;
