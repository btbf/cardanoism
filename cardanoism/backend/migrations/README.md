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
