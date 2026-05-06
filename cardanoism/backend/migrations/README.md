# Migrations

Cardanoism の MariaDB スキーマ定義。

## 適用方針

すべて `CREATE TABLE IF NOT EXISTS` で構成された **冪等** な統合スキーマ。番号順に1回流せばよい。
再実行しても既存テーブルには影響しない（既存テーブルが先勝ち）。

## 適用順

| # | ファイル | 内容 |
|---|---------|------|
| 001 | `001_users_auth.sql` | users / user_sessions / user_providers / notification_channels / telegram_connect_tokens |
| 002 | `002_user_data.sql` | stake_addresses / favorites |
| 003 | `003_notifications.sql` | notification_settings / stake_notification_settings / notification_check_state / notification_log |
| 004 | `004_governance.sql` | governance_actions / proposal_votes / proposal_voting_summary / protocol_params / cc_members |
| 005 | `005_dreps.sql` | dreps |
| 006 | `006_treasury.sql` | treasury_snapshot / treasury_withdrawal / ncl_active |
| 007 | `007_fiat_rate.sql` | fiat_rate |
| 008 | `008_pools.sql` | pools |
| 009 | `009_pools_icon.sql` | pools.pool_icon_url 追加 (ALTER) |
| 010 | `010_pools_meta_hash.sql` | pools.meta_hash を VARCHAR(128) に拡張 (ALTER) |
| 011 | `011_pools_extended.sql` | pools に extended metadata 由来カラムを追加 (logo / about / social) |
| 012 | `012_pools_relay_check.sql` | pools にリレー疎通結果カラムを追加 (relay_alive / relay_checked_at) |
| 013 | `013_recent_blocks.sql` | recent_blocks（直近100件のブロック履歴） |
| 014 | `014_mempool_state.sql` | mempool_state（id=1 固定の Ogmios mempool スナップショット） |
| 015 | `015_recent_blocks_size.sql` | recent_blocks に block_size (bytes) を追加 (ALTER) |
| 016 | `016_pools_block_history.sql` | pools に block_history_5ep (直近5エポックのブロック数) を追加 (ALTER) |
| 017 | `017_governance_ai_analysis.sql` | governance_ai_analysis（GA AI 分析結果 + ジョブステート） |
| 018 | `018_governance_actions_action_anchor.sql` | governance_actions に action_anchor_url / action_anchor_hash 追加 (ALTER) |
| 019 | `019_constitution_cache.sql` | constitution_cache（憲法本文 + 日本語訳キャッシュ、id=1 固定） |
| 020 | `020_treasury_history.sql` | treasury_history（エポックごとのトレジャリー残高履歴） |
| 021 | `021_governance_ai_analysis_facts.sql` | governance_ai_analysis をファクト整理ベースに変更（スコア / verdict / KPI 等を廃止、proposal_facts_json / rule_checks_json 追加） |
| 022 | `022_stake_address_verification.sql` | stake_addresses に verified / verified_at + wallet_verification_nonces |
| 023 | `023_pools_apy.sql` | pools.apy_history_7ep |
| 024 | `024_stake_rewards.sql` | stake_rewards（ステークアドレスごとのエポック別報酬） |
| 025 | `025_listener_event_slot.sql` | governance_actions / proposal_votes / dreps / pools / stake_addresses に last_event_slot を追加（Ogmios listener の rollback 対応） |
| 026 | `026_stake_addresses_spo.sql` | stake_addresses.spo_pool_id (SPO 識別) |
| 027 | `027_stake_rewards_type.sql` | stake_rewards.reward_type (member / leader / other 分離) + UNIQUE KEY 変更 |
| 028 | `028_governance_actions_spo_target.sql` | governance_actions.spo_target (SPO 投票対象判定) |
| 029 | `029_notification_channels_telegram.sql` | notification_channels.channel_type ENUM に 'telegram' を追加（既存 DB の古い ENUM 補完用、冪等） |

## 適用例

```bash
DB_HOST=...; DB_USER=...; DB_PASS=...; DB_NAME=...

for f in cardanoism/backend/migrations/*.sql; do
  echo "--- applying $f"
  mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$f"
done
```

## デフォルトデータの扱い

`notification_settings` / `stake_notification_settings` の初期イベント挿入は
**マイグレーション側では行わない**。アプリケーション側（`auth_db.py`）が以下のタイミングで挿入する:

- ユーザー新規作成時 (`_create_user`)
- ステークアドレス追加時 (`add_stake_address`)

## 設計上の留意点

- ENUM の値は変更頻度が低い（`role`、`channel_type`、`provider` など）。値を増やす場合は追加マイグレーションで `MODIFY COLUMN` する
- `protocol_params`、`treasury_snapshot`、`ncl_active`、`fiat_rate` は **id=1 固定の単一行** で運用する（`INSERT ... ON DUPLICATE KEY UPDATE` で上書き）
- 投票理由 (`proposal_votes.rationale_ja`) は OpenAI 翻訳で埋める想定。バッチは `notify_worker.py --event vote_rationale_sync`
