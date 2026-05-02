-- ============================================================
-- 010_pools_meta_hash.sql
-- pools.meta_hash の長さ拡張
--
-- Koios (PostgREST) が一部プールで 64 文字を超える meta_hash を返す
-- ケースがあるため安全に VARCHAR(128) へ拡張する。
-- ============================================================

ALTER TABLE pools MODIFY COLUMN meta_hash VARCHAR(128) DEFAULT NULL;
