-- ============================================================
-- 009_pools_icon.sql
-- pools テーブルに extended metadata 由来のアイコン URL を追加
--
-- - CIP-6 / Pool Operator Metadata (POM) の extended メタデータに含まれる
--   info.url_png_icon_64x64 (なければ info.url_png_logo) を保存する
-- - 同期は notify_worker.py --event pool_sync が並列でフェッチする
-- ============================================================

ALTER TABLE pools ADD COLUMN IF NOT EXISTS pool_icon_url TEXT DEFAULT NULL;
