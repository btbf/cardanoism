-- migration 013: LINE通知用IDを認証用IDから分離
-- line_id        : LINEログイン認証専用（UNIQUE制約維持）
-- line_notify_id : LINE通知送信先（制約なし、複数アカウントで共有可能）
ALTER TABLE users
  ADD COLUMN line_notify_id VARCHAR(255) NULL
    AFTER line_id;

-- 既存データ: LINEログインユーザーは line_id を line_notify_id にコピー
UPDATE users SET line_notify_id = line_id WHERE line_id IS NOT NULL;
