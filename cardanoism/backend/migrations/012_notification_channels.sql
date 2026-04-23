-- migration 012: 通知チャンネル選択カラムを追加
-- email_notify: メール通知を有効にするか（メールアドレスが登録されている場合）
-- line_notify:  LINE通知を有効にするか（line_idが連携されている場合）
ALTER TABLE users
  ADD COLUMN email_notify TINYINT(1) NOT NULL DEFAULT 1
    AFTER language,
  ADD COLUMN line_notify TINYINT(1) NOT NULL DEFAULT 1
    AFTER email_notify;
