-- ============================================================
-- 027_stake_rewards_type.sql
-- stake_rewards に reward_type カラムを追加。
--
-- Koios /account_reward_history のレスポンスには各エポック行に type フィールドがあり:
--   member  : 委任先プールからのステーク報酬
--   leader  : SPO のオペレーション報酬 (margin + fixed_cost)
--   treasury: トレジャリー由来 (NCL 引き出し時)
--   reserves: リザーブ由来 (Genesis 時等)
--   refund  : pool deposit 返還
--
-- これまでは type を区別せず全合算して 1 行にしていたため、SPO の reward_addr では
-- ステーキング報酬とプール報酬が混在していた。type 別に保存することで分離表示可能。
--
-- "other" には treasury / reserves / refund を集約して保存する (UI で個別表示する優先度低)。
--
-- UNIQUE KEY を (stake_address, epoch_no) → (stake_address, epoch_no, reward_type) に変更。
-- 既存データは default 'member' で初期化される。SPO アドレスについては次回 backfill で再取得時に
-- member / leader に正確化される。
-- ============================================================

ALTER TABLE stake_rewards
    ADD COLUMN IF NOT EXISTS reward_type ENUM('member', 'leader', 'other')
        NOT NULL DEFAULT 'member';

-- 既存 UNIQUE KEY を破棄して type を含む新しい KEY に差し替え
ALTER TABLE stake_rewards DROP INDEX uq_stake_epoch;
ALTER TABLE stake_rewards
    ADD UNIQUE KEY uq_stake_epoch_type (stake_address, epoch_no, reward_type);
