-- ============================================================
-- 011_pools_extended.sql
-- pools テーブルに POM (Pool Operator Metadata) extended 由来の追加情報
--
-- - info.url_png_logo            → pool_logo_url
-- - info.about.me                → extended_about
-- - info.social.twitter_handle   → twitter_handle
-- - info.social.telegram_handle  → telegram_handle
-- - info.social.youtube_handle   → youtube_handle
-- - info.social.github_handle    → github_handle
-- - 同期は notify_worker.py --event pool_sync
-- ============================================================

ALTER TABLE pools
    ADD COLUMN IF NOT EXISTS pool_logo_url   TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS extended_about  TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS twitter_handle  VARCHAR(128) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS telegram_handle VARCHAR(128) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS youtube_handle  VARCHAR(255) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS github_handle   VARCHAR(128) DEFAULT NULL;
