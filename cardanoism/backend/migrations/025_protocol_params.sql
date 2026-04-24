-- 025_protocol_params.sql
-- プロトコルパラメータ（投票閾値・デポジット等）のキャッシュ。id=1 固定の単一行。
-- 同期は notify_worker.py --event params_sync で行う。

CREATE TABLE IF NOT EXISTS protocol_params (
  id                              INT            PRIMARY KEY,
  epoch_no                        INT            DEFAULT NULL,
  -- DRep voting thresholds
  dvt_motion_no_confidence        DECIMAL(10,8)  DEFAULT NULL,
  dvt_committee_normal            DECIMAL(10,8)  DEFAULT NULL,
  dvt_committee_no_confidence     DECIMAL(10,8)  DEFAULT NULL,
  dvt_update_to_constitution      DECIMAL(10,8)  DEFAULT NULL,
  dvt_hard_fork_initiation        DECIMAL(10,8)  DEFAULT NULL,
  dvt_p_p_network_group           DECIMAL(10,8)  DEFAULT NULL,
  dvt_p_p_economic_group          DECIMAL(10,8)  DEFAULT NULL,
  dvt_p_p_technical_group         DECIMAL(10,8)  DEFAULT NULL,
  dvt_p_p_gov_group               DECIMAL(10,8)  DEFAULT NULL,
  dvt_treasury_withdrawal         DECIMAL(10,8)  DEFAULT NULL,
  -- SPO voting thresholds
  pvt_motion_no_confidence        DECIMAL(10,8)  DEFAULT NULL,
  pvt_committee_normal            DECIMAL(10,8)  DEFAULT NULL,
  pvt_committee_no_confidence     DECIMAL(10,8)  DEFAULT NULL,
  pvt_hard_fork_initiation        DECIMAL(10,8)  DEFAULT NULL,
  pvtpp_security_group            DECIMAL(10,8)  DEFAULT NULL,
  -- Committee / deposit 関連
  committee_min_size              INT            DEFAULT NULL,
  committee_max_term_length       INT            DEFAULT NULL,
  gov_action_lifetime             INT            DEFAULT NULL,
  gov_action_deposit              BIGINT         DEFAULT NULL,
  drep_deposit                    BIGINT         DEFAULT NULL,
  drep_activity                   INT            DEFAULT NULL,
  updated_at                      DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
