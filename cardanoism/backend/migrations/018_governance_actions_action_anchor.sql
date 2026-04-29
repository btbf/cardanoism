-- ============================================================
-- 018_governance_actions_action_anchor.sql
-- governance_actions に action 内 anchor の URL/hash カラムを追加
--
-- NewConstitution 提案では、提案メタデータ (meta_url) は提案の説明 JSON で、
-- 実際の憲法本文ドキュメント (PDF/Markdown 等) は別 URL に置かれている。
-- Koios /proposal_list の proposed_action.contents または body.references から
-- その URL を抽出し、ここに保存する。
-- ============================================================

ALTER TABLE governance_actions
    ADD COLUMN IF NOT EXISTS action_anchor_url  TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS action_anchor_hash VARCHAR(128) DEFAULT NULL;
