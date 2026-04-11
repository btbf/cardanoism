-- 007_stake_address_wallet_addr.sql
-- 登録時の受信アドレス（addr1...）を保存するカラムを追加

ALTER TABLE stake_addresses
  ADD COLUMN wallet_address VARCHAR(255) DEFAULT NULL AFTER address;
