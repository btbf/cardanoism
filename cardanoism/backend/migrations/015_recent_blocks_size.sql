-- ============================================================
-- 015_recent_blocks_size.sql
-- recent_blocks に block_size (bytes) を追加
--
-- Ogmios の block.size.bytes を保持。ダッシュボードのキューブで
-- block_size / max_block_body_size を充填率として可視化する。
-- ============================================================

ALTER TABLE recent_blocks
    ADD COLUMN IF NOT EXISTS block_size INT NOT NULL DEFAULT 0;
