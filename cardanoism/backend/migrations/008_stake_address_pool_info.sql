-- 008_stake_address_pool_info.sql
-- 委任先ステークプール情報を保存するカラムを追加

ALTER TABLE stake_addresses
  ADD COLUMN delegated_pool_id VARCHAR(255) DEFAULT NULL AFTER delegated_drep_name,
  ADD COLUMN delegated_pool_name VARCHAR(255) DEFAULT NULL AFTER delegated_pool_id;
