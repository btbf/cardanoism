-- ============================================================
-- 023_pools_apy.sql
-- pools テーブルに APY (epoch_ros) 履歴を追加
--
-- /pool_history は pool_block_history_sync で既に全 active プールを叩いている。
-- 同じレスポンス内の epoch_ros を拾えば API コール数ゼロ追加で APY をキャッシュできる。
--
-- block_history_5ep と同じ流儀で「直近 7 エポックの epoch_ros 配列」を JSON 文字列で 1 カラムに保存。
-- 平均は表示時に Python 側で計算する (block_history_5ep の sum() と同じパターン)。
-- ============================================================

ALTER TABLE pools
    ADD COLUMN IF NOT EXISTS apy_history_7ep TEXT DEFAULT NULL;
