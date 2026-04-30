-- ============================================================
-- 019_constitution_cache.sql
-- Cardano 憲法本文の原文 + 日本語訳キャッシュ（id=1 固定の単一行）
--
-- 最新 enacted NewConstitution の本文を IPFS から取得し、Catalyst でも使われる
-- Translator (cardanoism/translate/engine.py) で翻訳して保存する。
-- 同期は notify_worker.py --event constitution_sync で行う。
-- ============================================================

CREATE TABLE IF NOT EXISTS constitution_cache (
    id              INT          NOT NULL DEFAULT 1 PRIMARY KEY,
    proposal_id     VARCHAR(255) DEFAULT NULL,
    enacted_epoch   INT          DEFAULT NULL,
    source_url      TEXT         DEFAULT NULL,
    original_text   MEDIUMTEXT   DEFAULT NULL,
    translated_text MEDIUMTEXT   DEFAULT NULL,
    fetched_at      DATETIME     DEFAULT NULL,
    translated_at   DATETIME     DEFAULT NULL,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
