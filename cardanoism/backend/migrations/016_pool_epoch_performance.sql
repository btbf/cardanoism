-- ============================================================
-- 016_pool_epoch_performance.sql
-- pool_epoch_performance 通知イベントを既存ステークアドレスに追加
-- ============================================================

INSERT IGNORE INTO stake_notification_settings (stake_address_id, event_type, enabled)
SELECT id, 'pool_epoch_performance', 1
FROM stake_addresses;
