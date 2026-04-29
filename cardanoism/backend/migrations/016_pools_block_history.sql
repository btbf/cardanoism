-- ============================================================
-- 016_pools_block_history.sql
-- pools に直近5エポックのブロック生成数を保持するカラムを追加
--
-- - block_history_5ep: 直近5エポック分のブロック数を JSON 配列で保存
--   例: "[12, 8, 15, 11, 9]" (newest 順)
-- - 同期は notify_worker.py --event pool_block_history_sync (Koios /pool_history)
-- ============================================================

ALTER TABLE pools
    ADD COLUMN IF NOT EXISTS block_history_5ep TEXT DEFAULT NULL;
