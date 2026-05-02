-- ============================================================
-- 012_pools_relay_check.sql
-- pools テーブルにリレー疎通結果のフラグを追加
--
-- - relay_alive       : 1 = 全リレーへTCP疎通OK / 0 = 1つでもNG or 確認不能
-- - relay_checked_at  : 最後に疎通確認した日時
-- - 同期は notify_worker.py --event relay_check
-- ============================================================

ALTER TABLE pools
    ADD COLUMN IF NOT EXISTS relay_alive      TINYINT(1) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS relay_checked_at DATETIME   DEFAULT NULL;
