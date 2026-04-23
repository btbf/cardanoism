-- ============================================================
-- 003_stake_address_role.sql
-- ステークアドレスにDRep/委任者ロールを追加
-- ============================================================

ALTER TABLE stake_addresses
ADD COLUMN role ENUM('delegator', 'drep') NOT NULL DEFAULT 'delegator' AFTER nickname,
ADD COLUMN role_checked_at DATETIME AFTER role;
