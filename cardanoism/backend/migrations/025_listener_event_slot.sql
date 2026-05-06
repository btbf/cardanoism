-- ============================================================
-- 025_listener_event_slot.sql
-- Ogmios listener が DB を直接更新する設計 (Phase 1〜4) の前提:
-- 各 listener-managed 行に「最後にイベントが発生した slot」を記録する。
--
-- chain rollback (re-org) 通知時に listener はこのカラムを使って
--   DELETE FROM <table> WHERE last_event_slot > <rollback_slot>
-- を実行し、無効化されたチェーン情報を巻き戻す。
--
-- カラム名は `last_event_slot` 統一。NULL は「listener 経由で書かれていない (Koios sync 由来)」
-- ことを意味し、rollback 対象から外れる。
-- ============================================================

-- Phase 1: 新規 GA / 投票
ALTER TABLE governance_actions
    ADD COLUMN IF NOT EXISTS last_event_slot BIGINT DEFAULT NULL;

ALTER TABLE proposal_votes
    ADD COLUMN IF NOT EXISTS last_event_slot BIGINT DEFAULT NULL;

-- Phase 2: DRep cert
ALTER TABLE dreps
    ADD COLUMN IF NOT EXISTS last_event_slot BIGINT DEFAULT NULL;

-- Phase 3: Pool cert
ALTER TABLE pools
    ADD COLUMN IF NOT EXISTS last_event_slot BIGINT DEFAULT NULL;

-- Phase 4: 委任 cert (StakeDelegCert / VoteDelegCert)
ALTER TABLE stake_addresses
    ADD COLUMN IF NOT EXISTS last_event_slot BIGINT DEFAULT NULL;

-- 補助インデックス (rollback DELETE が高速に走るため)
CREATE INDEX IF NOT EXISTS idx_ga_event_slot     ON governance_actions(last_event_slot);
CREATE INDEX IF NOT EXISTS idx_votes_event_slot  ON proposal_votes(last_event_slot);
CREATE INDEX IF NOT EXISTS idx_dreps_event_slot  ON dreps(last_event_slot);
CREATE INDEX IF NOT EXISTS idx_pools_event_slot  ON pools(last_event_slot);
