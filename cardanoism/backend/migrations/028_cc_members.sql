-- 028_cc_members.sql
-- Constitutional Committee メンバーのキャッシュ。
-- Koios /committee_info から同期する。
-- CC メンバーには公式なメタデータ規格がなく、Koios からは表示名が取れないため、
-- display_name は運用で手動設定できるようにする（空なら UI 側で ID を使う）。

CREATE TABLE IF NOT EXISTS cc_members (
  cc_cold_id        VARCHAR(128) PRIMARY KEY,
  cc_cold_hex       VARCHAR(128) DEFAULT NULL,
  cc_hot_id         VARCHAR(128) DEFAULT NULL,
  cc_hot_hex        VARCHAR(128) DEFAULT NULL,
  status            VARCHAR(32)  DEFAULT NULL,  -- authorized / resigned / expired / unrecognized 等
  expiration_epoch  INT          DEFAULT NULL,
  cc_hot_has_script TINYINT(1)   DEFAULT 0,
  cc_cold_has_script TINYINT(1)  DEFAULT 0,
  display_name      VARCHAR(255) DEFAULT NULL,  -- 運用で手動編集可
  updated_at        DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
