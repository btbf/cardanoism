-- 023_dreps_image_url_expand.sql
-- image_url に data URI（base64 画像）が入るケースがあり TEXT の 65,535 byte 制限を超える。
-- MEDIUMTEXT に拡張する。既に 022 を適用済みの環境で実行する。

ALTER TABLE dreps
  MODIFY COLUMN image_url MEDIUMTEXT DEFAULT NULL;
