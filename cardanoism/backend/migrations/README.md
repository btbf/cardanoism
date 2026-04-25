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
