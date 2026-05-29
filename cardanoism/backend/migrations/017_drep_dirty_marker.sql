-- ============================================================
-- 017_drep_dirty_marker.sql
--
-- DRep 委任変動マーカー。
-- Ogmios listener が vote_delegation / stake_and_vote_delegation cert を
-- 検知したときに、旧 drep_id と新 drep_id を marked_at と共に記録する。
--
-- notify_worker.py の drep_sync (--event drep_sync) が直近 1 時間以内に
-- marked_at が更新された DRep だけを「リアルタイム live amount 同期対象」
-- として /drep_delegators で集計する。それ以外の DRep は /drep_info.amount
-- (epoch-boundary 値) で十分とみなす。
--
-- これにより 1 起動あたり 1700 reqs (全 active DRep に /drep_delegators)
-- → 数十 reqs (dirty な DRep のみ) に削減され、Koios の 50,000 req/day
-- 制限内に収まる。
--
-- listener が落ちている間にデータが取りこぼされないよう、cron に日 1 回の
-- fallback として `drep_sync --full` を残し、全 active DRep を強制再集計する。
-- ============================================================
CREATE TABLE IF NOT EXISTS drep_dirty_marker (
    drep_id    VARCHAR(128) PRIMARY KEY,
    marked_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_marked_at (marked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
