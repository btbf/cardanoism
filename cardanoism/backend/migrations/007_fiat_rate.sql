-- ============================================================
-- 007_fiat_rate.sql
-- ADA 法定通貨レート（JPY / USD）キャッシュ
--
-- - id=1 固定の単一行で常に上書き
-- - CoinGecko API のレートを抑制するため DB にキャッシュ
-- - 同期は notify_worker.py --event fiat_sync
-- ============================================================

CREATE TABLE IF NOT EXISTS fiat_rate (
    id         INT            PRIMARY KEY,
    ada_jpy    DECIMAL(20, 6) NOT NULL,
    ada_usd    DECIMAL(20, 6) NOT NULL,
    source     VARCHAR(64)    DEFAULT 'coingecko',
    updated_at DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
