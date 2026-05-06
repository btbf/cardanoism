-- ============================================================
-- 026_stake_addresses_spo.sql
-- stake_addresses に SPO 判定用カラムを追加。
--
-- spo_pool_id:
--   - NULL = 通常ユーザー (delegator / drep / abstain)
--   - 値あり = SPO (この stake address が pools.reward_addr または pools.owners に含まれる)
--
-- 判定タイミング:
--   1. ステークアドレス登録時 (auth_state.add_stake_address_handler)
--   2. Ogmios listener が PoolRegistration cert を受信した時
--   3. 24h fallback として pool_sync の末尾で全件再判定 (notify_worker)
--   4. 初期投入時 spo_role_initial_sync で全件 sync (新環境セットアップ手順)
--
-- 複数プールに該当するケース (multi-pool 運営者) は最初に見つかった 1 件のみ記録する。
-- 将来必要になれば別テーブル化 (stake_address_pools) で拡張可能。
-- ============================================================

ALTER TABLE stake_addresses
    ADD COLUMN IF NOT EXISTS spo_pool_id VARCHAR(64) DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_stake_addr_spo ON stake_addresses(spo_pool_id);
