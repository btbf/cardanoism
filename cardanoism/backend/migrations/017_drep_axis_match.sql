-- ============================================================
-- 017_drep_axis_match.sql
-- DRep マッチング診断: 5 軸モデルに再設計したことに伴うカラム追加
--
-- 旧設計 (016) は 9 トピックのフラットなタグ付け + Yes 率ベクトルだった。
-- 新設計は「派閥モデル」: 5 軸 × 2 派閥スペクトラム
--   A. axis_treasury  : "discipline"  ⟷ "investment"
--   B. axis_protocol  : "conservative" ⟷ "progressive"
--   C. axis_org       : "centralized" ⟷ "decentralized"
--   D. axis_ecosystem : "technical"   ⟷ "expansion"
--   E. axis_marketing : "promotion"   ⟷ "restraint"
--
-- - governance_ai_analysis.axis_tags_json
--     AI が GA に付与した軸ラベル。JSON オブジェクト。
--     例: {"axis_treasury":"discipline","axis_org":"centralized"}
--     該当しない軸は欠落 OK (= AI が判定不能とした)
--
-- - dreps.axis_profile_json
--     DRep の各軸の派閥スコア (-1.0 〜 +1.0)。
--     +1.0 = 完全に先頭派閥 (discipline/conservative/centralized/technical/promotion)
--     -1.0 = 完全に後尾派閥 (investment/progressive/decentralized/expansion/restraint)
--     例: {"axis_treasury":0.7,"axis_protocol":-0.3,"axis_org":0.9}
--
-- - dreps.axis_vote_count
--     軸プロファイル算出に使った Yes+No 票総数 (axis タグが付いた GA への投票)。
--     5 票未満はデータ不足としてマッチング対象外。
--
-- 旧カラム (topic_tags_json / topic_profile_json / topic_vote_count) は残置。
-- 後方互換のため削除しない。次フェーズで運用が安定したら別 PR で drop 予定。
-- ============================================================

ALTER TABLE governance_ai_analysis
  ADD COLUMN IF NOT EXISTS axis_tags_json TEXT DEFAULT NULL
  COMMENT 'AI 軸ラベル (JSON、例: {"axis_treasury":"discipline","axis_org":"centralized"})';

ALTER TABLE dreps
  ADD COLUMN IF NOT EXISTS axis_profile_json TEXT DEFAULT NULL
  COMMENT 'DRep 軸派閥スコア (-1.0〜+1.0、JSON、例: {"axis_treasury":0.7,...})';

ALTER TABLE dreps
  ADD COLUMN IF NOT EXISTS axis_vote_count INT NOT NULL DEFAULT 0
  COMMENT '軸プロファイル算出に使った投票件数 (Yes+No)。< 5 はデータ不足';
