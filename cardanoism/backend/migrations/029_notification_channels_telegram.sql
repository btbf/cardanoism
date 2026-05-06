-- ============================================================
-- 029_notification_channels_telegram.sql
-- notification_channels.channel_type ENUM に 'telegram' を追加。
--
-- 001_users_auth.sql で初めから 'telegram' を含めて定義済みだが、
-- 過去に 'line' / 'email' のみで作成された既存環境では ENUM が古いまま
-- 残ってしまい、Telegram 連携時の UPSERT が
--   "Data truncated for column 'channel_type' at row 1"
-- で失敗する。この ALTER で確実に最新の ENUM 定義へ揃える。
--
-- 既に 'telegram' を含む環境では何も変わらない (冪等)。
-- ============================================================

ALTER TABLE notification_channels
    MODIFY COLUMN channel_type ENUM('line', 'email', 'telegram') NOT NULL;
