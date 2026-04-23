-- 004_favorites_uuid.sql
-- favorites.proposal_id (INT) を proposal_uuid (VARCHAR) に変更する
-- 既存データは UUID で特定できないため削除する

-- 既存お気に入りをクリア（IDベースのものはUUIDと対応できないため）
DELETE FROM favorites;

-- 旧カラム削除・新カラム追加
ALTER TABLE favorites
  DROP COLUMN proposal_id,
  ADD COLUMN proposal_uuid VARCHAR(255) NOT NULL DEFAULT '' AFTER user_id;

-- ユニークキー再作成
ALTER TABLE favorites
  ADD UNIQUE KEY uq_user_proposal_type (user_id, proposal_uuid, type);
