-- ============================================================
-- 030_subscriptions.sql
-- サブスクリプション基盤テーブル (Phase 0: tier 名は文字列で柔軟に)
--
-- 設計方針:
--   - tier は ENUM ではなく VARCHAR で柔軟性を確保。「light / standard /
--     plus / pro」など名前が変わっても DB は無改修。
--   - status は Stripe 連携を見越した文字列。Phase 0 では "active" 固定。
--   - Stripe 関連カラムは Phase 1 で埋める（現時点は NULL 可）。
--   - ベータ期間中は新規ユーザーを tier="standard" でデフォルト挿入する想定。
-- ============================================================

CREATE TABLE IF NOT EXISTS subscriptions (
    id                       INT          AUTO_INCREMENT PRIMARY KEY,
    user_id                  INT          NOT NULL,
    tier                     VARCHAR(32)  NOT NULL DEFAULT 'free',
    status                   VARCHAR(32)  NOT NULL DEFAULT 'active',
    billing_cycle            VARCHAR(16)  DEFAULT NULL,
    started_at               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    current_period_end       DATETIME     DEFAULT NULL,
    canceled_at              DATETIME     DEFAULT NULL,
    stripe_customer_id       VARCHAR(255) DEFAULT NULL,
    stripe_subscription_id   VARCHAR(255) DEFAULT NULL,
    stripe_price_id          VARCHAR(255) DEFAULT NULL,
    note                     VARCHAR(255) DEFAULT NULL,
    created_at               DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at               DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user (user_id),
    KEY idx_tier   (tier),
    KEY idx_status (status),
    KEY idx_stripe_customer (stripe_customer_id)
);

-- ベータ期間中の既存ユーザー全員に standard 行を backfill。
-- INSERT IGNORE なので既に行があれば何もしない (再実行安全)。
-- 本番リリース時に default tier を 'free' に変える際は別マイグレーションで対応。
INSERT IGNORE INTO subscriptions (user_id, tier, status, note)
SELECT id, 'standard', 'active', 'beta_grandfather' FROM users;
