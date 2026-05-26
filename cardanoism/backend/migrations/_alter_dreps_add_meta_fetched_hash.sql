-- ============================================================
-- _alter_dreps_add_meta_fetched_hash.sql
--
-- 既存の本番 / preview DB に対して dreps.meta_fetched_hash 列を追加する
-- 「一時マイグレーション」。新規環境では 005_dreps.sql の CREATE TABLE
-- に既に meta_fetched_hash VARCHAR(64) が含まれているため不要。
--
-- 用途:
--   check_drep_sync が CIP-119 metadata を実際に取り込んだ時点の meta_hash を
--   保持し、Ogmios listener が drep_update cert で meta_hash を書き換えた直後でも
--   「metadata 本体未取得」を次の sync で検出できるようにする。
--   比較: /drep_info.meta_hash != dreps.meta_fetched_hash → /drep_metadata 取得対象
--
-- 適用後、このファイルはリポジトリに残してよい (冪等)。番号付きの統合スキーマ
-- には追加しない (移行用 ALTER は migrations 番号付きには載せない方針)。
--
-- 適用例:
--   mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < _alter_dreps_add_meta_fetched_hash.sql
--
-- 適用後の挙動:
--   - 全行 meta_fetched_hash IS NULL の状態でスタート
--   - 初回 drep_sync で全 registered DRep が「metadata 取得対象」扱いになり
--     /drep_metadata batch が 1 回だけ重い (~70 batch reqs)
--   - 以降は差分のみ (meta_hash 変動行 + 新規 DRep) で軽量
-- ============================================================

ALTER TABLE dreps
  ADD COLUMN IF NOT EXISTS meta_fetched_hash VARCHAR(64) DEFAULT NULL
  COMMENT 'check_drep_sync が CIP-119 metadata を取り込んだ時点の meta_hash (差分判定用)'
  AFTER meta_is_valid;
