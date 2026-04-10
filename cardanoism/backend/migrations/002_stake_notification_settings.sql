-- ============================================================
-- 002_stake_notification_settings.sql
-- ステークアドレスごとの通知設定テーブル追加
-- プール・DRep イベントをアドレス単位で管理する
-- ============================================================

-- ステークアドレスごとの通知設定
-- event_type: pool_retire, pool_fee_change, pool_saturation, pool_pledge_shortage,
--             pool_reward_estimate, pool_reward_received, pool_delegation_reminder, pool_status_active,
--             drep_new_governance_action, drep_governance_action_deadline,
--             drep_vote, drep_delegation_reminder, drep_status_active
CREATE TABLE IF NOT EXISTS stake_notification_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stake_address_id INT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    enabled TINYINT(1) DEFAULT 1,
    FOREIGN KEY (stake_address_id) REFERENCES stake_addresses(id) ON DELETE CASCADE,
    UNIQUE KEY uq_stake_event (stake_address_id, event_type)
);

-- 既存の notification_settings からプール・DRep イベントを削除
-- （epoch_start など汎用イベントのみ残す）
DELETE FROM notification_settings
WHERE event_type IN (
    'pool_retire', 'pool_fee_change', 'pool_saturation', 'pool_pledge_shortage',
    'pool_reward_estimate', 'pool_reward_received', 'pool_delegation_reminder', 'pool_status_active',
    'drep_new_proposal', 'drep_new_governance_action', 'drep_governance_action_deadline',
    'drep_vote', 'drep_delegation_reminder', 'drep_status_active'
);

-- 既存のステークアドレスにデフォルト通知設定を挿入
INSERT IGNORE INTO stake_notification_settings (stake_address_id, event_type, enabled)
SELECT sa.id, et.event_type, 1
FROM stake_addresses sa
CROSS JOIN (
    SELECT 'pool_retire'                    AS event_type UNION ALL
    SELECT 'pool_fee_change'                UNION ALL
    SELECT 'pool_saturation'                UNION ALL
    SELECT 'pool_pledge_shortage'           UNION ALL
    SELECT 'pool_reward_estimate'           UNION ALL
    SELECT 'pool_reward_received'           UNION ALL
    SELECT 'pool_delegation_reminder'       UNION ALL
    SELECT 'pool_status_active'             UNION ALL
    SELECT 'drep_new_governance_action'     UNION ALL
    SELECT 'drep_governance_action_deadline' UNION ALL
    SELECT 'drep_vote'                      UNION ALL
    SELECT 'drep_delegation_reminder'       UNION ALL
    SELECT 'drep_status_active'
) et;
