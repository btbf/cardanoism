-- ============================================================
-- 021_governance_ai_analysis_facts.sql
-- governance_ai_analysis をスコアベース → ファクト整理ベースに変更
--
-- 廃止カラム:
--   constitution_score           (スコア廃止)
--   constitution_verdict_ja/en   (verdict 廃止)
--   concerns_ja_json / concerns_en_json (主観的判定廃止)
--   pillars_json                 (VISION 2030 レーダー廃止)
--   related_kpis_json            (KPI 表示廃止)
--
-- 流用カラム:
--   constitution_summary_ja/en   → 提案概要 (proposal_summary)
--   articles_json                → 関連条文（スコア無し、引用と理由のみ）
--
-- 追加カラム:
--   proposal_facts_json          AI が抽出した提案の主要ファクト
--   rule_checks_json             ルールベースの自動チェック結果
--
-- 既存データは互換性なし。デプロイ後に
--   TRUNCATE TABLE governance_ai_analysis;
-- を手動で実行して再分析することを推奨。
-- ============================================================

ALTER TABLE governance_ai_analysis
    DROP COLUMN IF EXISTS constitution_score,
    DROP COLUMN IF EXISTS constitution_verdict_ja,
    DROP COLUMN IF EXISTS constitution_verdict_en,
    DROP COLUMN IF EXISTS concerns_ja_json,
    DROP COLUMN IF EXISTS concerns_en_json,
    DROP COLUMN IF EXISTS pillars_json,
    DROP COLUMN IF EXISTS related_kpis_json,
    ADD COLUMN IF NOT EXISTS proposal_facts_json TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS rule_checks_json    TEXT DEFAULT NULL;
