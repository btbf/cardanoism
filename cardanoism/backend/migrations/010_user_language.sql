-- migration 010: ユーザーテーブルに言語設定カラムを追加
ALTER TABLE users
  ADD COLUMN language ENUM('ja', 'en') NOT NULL DEFAULT 'ja'
  AFTER notification_frequency;
