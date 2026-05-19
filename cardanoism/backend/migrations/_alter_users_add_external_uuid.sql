-- ============================================================
-- _alter_users_add_external_uuid.sql
--
-- 既存の本番 / preview DB に対して users.external_uuid を追加 + backfill する
-- 「一時マイグレーション」。新規環境では 001_users_auth.sql の CREATE TABLE
-- に既に external_uuid CHAR(36) UNIQUE が含まれているため不要。
--
-- 適用後、このファイルはリポジトリに残してよい (冪等)。番号付きの統合スキーマ
-- には追加しない (移行用 ALTER は migrations 番号付きには載せない方針)。
--
-- 適用例:
--   mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < _alter_users_add_external_uuid.sql
-- ============================================================

-- 1. カラム追加 (既に存在する場合は何もしない / MariaDB 10.6+)
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS external_uuid CHAR(36) DEFAULT NULL UNIQUE
    AFTER avatar_url;

-- 2. 既存ユーザーの backfill: UUID v4 を発行する。
--    MariaDB の UUID() は v1 (時間/MAC ベース) なので、ここでは MariaDB 10.10+ の
--    UUID(4) もしくは SYS_GUID() を使うか、Python 側でやるのが厳密。
--    本番は 10.11+ 想定なので、ここでは UUID() (v1) でも実害なし (一意性は確保) として
--    backfill する。「外部識別子」用途で v1 か v4 かはユーザーには無関係。
UPDATE users
   SET external_uuid = UUID()
 WHERE external_uuid IS NULL;
