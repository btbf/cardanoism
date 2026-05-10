# Migrations

Cardanoism の MariaDB スキーマ定義（最終形）。

## 適用方針

すべて `CREATE TABLE IF NOT EXISTS` で構成された **冪等** な統合スキーマ。
番号順に 1 回流せばよい。再実行しても既存テーブルには影響しない（既存テーブルが先勝ち）。

## 適用順

| # | ファイル | テーブル / 内容 |
|---|---------|----------------|
| 001 | `001_users_auth.sql` | users / user_sessions / user_providers / notification_channels / telegram_connect_tokens |
| 002 | `002_user_data.sql` | stake_addresses / favorites / wallet_verification_nonces |
| 003 | `003_notifications.sql` | notification_settings / stake_notification_settings / notification_check_state / notification_log |
| 004 | `004_governance.sql` | governance_actions / proposal_votes / proposal_voting_summary / protocol_params / cc_members |
| 005 | `005_dreps.sql` | dreps |
| 006 | `006_treasury.sql` | treasury_snapshot / treasury_history / treasury_withdrawal / ncl_active |
| 007 | `007_fiat_rate.sql` | fiat_rate |
| 008 | `008_pools.sql` | pools |
| 009 | `009_recent_blocks.sql` | recent_blocks（直近 100 件のブロック履歴） |
| 010 | `010_mempool_state.sql` | mempool_state（id=1 固定の Ogmios mempool スナップショット） |
| 011 | `011_governance_ai_analysis.sql` | governance_ai_analysis（GA AI 分析結果 + ジョブステート） |
| 012 | `012_constitution_cache.sql` | constitution_cache（憲法本文 + 日本語訳キャッシュ、id=1 固定） |
| 013 | `013_stake_rewards.sql` | stake_rewards（エポック × reward_type 別の報酬キャッシュ） |
| 014 | `014_subscriptions.sql` | subscriptions（サブスク基盤）+ ベータ向け既存ユーザー backfill |

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

- ENUM の値は変更頻度が低い（`role`、`channel_type`、`provider`、`reward_type` など）。値を増やす場合は追加マイグレーションで `MODIFY COLUMN` する
- `protocol_params`、`treasury_snapshot`、`ncl_active`、`fiat_rate`、`mempool_state`、`constitution_cache` は **id=1 固定の単一行** で運用する（`INSERT ... ON DUPLICATE KEY UPDATE` で上書き）
- 投票理由 (`proposal_votes.rationale_ja`) は OpenAI 翻訳で埋める想定。バッチは `notify_worker.py --event vote_rationale_sync`
- `last_event_slot`（governance_actions / proposal_votes / dreps / pools / stake_addresses）は Ogmios listener が rollback 時に `DELETE WHERE last_event_slot > <rollback_slot>` で巻き戻すために使う。NULL は「listener 経由で書かれていない（Koios sync 由来）」を意味し rollback 対象外。

## このファイルの更新方針

新しいテーブル / カラムを追加するときは:

1. **新規テーブル**: 連番で新ファイルを追加（`015_*.sql` など）
2. **既存テーブルへのカラム追加**: 該当 base ファイルの `CREATE TABLE` 本体に追記。本番 DB に対しては別途 `ALTER TABLE` を流すこと（このディレクトリには ALTER 系ファイルを残さない方針）

「最終形」を保ち続けることで、新規 VPS デプロイ時に番号順に流せば常に最新スキーマが構築される状態を維持する。
