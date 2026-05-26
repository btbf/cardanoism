-- ============================================================
-- 023_drep_meta_fetched_hash.sql
--
-- dreps.meta_fetched_hash 列を追加。
--
-- 目的:
--   check_drep_sync が CIP-119 metadata を実際に取り込んだ時の meta_hash を
--   meta_hash とは別に保持する。これにより listener_dreps.py が drep_update cert
--   を検出して meta_hash を書き換えた直後でも、metadata 本体 (given_name 等)
--   未取り込みであることを次の sync で検出できる。
--
-- 比較ロジック:
--   /drep_info.meta_hash != dreps.meta_fetched_hash  → /drep_metadata 取得対象
--   一致するなら CIP-119 本体は既に最新 → skip
--
-- ALTER TABLE ... ADD COLUMN IF NOT EXISTS は MariaDB 10.0.2+ で動作。
-- ============================================================

ALTER TABLE dreps
  ADD COLUMN IF NOT EXISTS meta_fetched_hash VARCHAR(64) DEFAULT NULL
  COMMENT 'check_drep_sync が CIP-119 metadata を取り込んだ時点の meta_hash';
