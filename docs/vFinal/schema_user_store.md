# User Store Schema / ユーザーデータ格納スキーマ

**Language / 言語:** [English](#english) ・ [日本語](#日本語)

An inventory of the data Cardanoism holds about users — where it is stored, the fields, their purpose, whether they are personal data, and retention/deletion rules. For both compliance (personal-data inventory) and engineering reference.
Cardanoism がユーザーについて保持するデータの一覧。格納先・項目・目的・個人データ該当性・保持/削除ルールを整理する。コンプライアンス（保有個人データ棚卸し）と開発の双方の参照用。

- **DB:** MariaDB (no ORM / raw SQL)
- **Source:** [`cardanoism/backend/migrations/001_users_auth.sql`](../../cardanoism/backend/migrations/001_users_auth.sql) · [`002_user_data.sql`](../../cardanoism/backend/migrations/002_user_data.sql)
- All tables use `CREATE TABLE IF NOT EXISTS` (idempotent).

---

## English

> "Personal data" legend: ●=personal information / identifier · ○=user-linked but not identifying on its own · −=non-personal

### Overview

```
users (1) ──┬─< user_sessions          sessions
            ├─< user_providers         social login IDs
            ├─< notification_channels   delivery targets (LINE/Email/Telegram)
            ├─< telegram_connect_tokens temporary linking tokens
            ├─< stake_addresses         registered stake addresses (max 3)
            ├─< favorites               favorites
            └─< wallet_verification_nonces  ownership-check nonces (ephemeral)
```

Every child table references `users` via a `user_id` foreign key with **`ON DELETE CASCADE`**. Deleting a `users` row automatically removes all linked user data.

### 1. Auth core (001_users_auth.sql)

#### `users` — basic user info

| Column | Type | NULL | Personal | Description |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | ○ | Internal user ID |
| `username` | VARCHAR(255) | no | ● | Display name (from provider or user-edited) |
| `email` | VARCHAR(255) | yes | ● | Email. Auto-upserts into `notification_channels` when set |
| `avatar_url` | TEXT | yes | ● | Avatar image URL |
| `external_uuid` | CHAR(36) UNIQUE | yes | ○ | UUID v4 to identify the user in external systems (feedback form, etc.). **Identifier only, not for auth**; decoupled from OAuth identity |
| `notification_frequency` | ENUM('instant','daily') | def. instant | − | Notification frequency |
| `language` | ENUM('ja','en') | def. ja | − | Display language |
| `created_at` / `updated_at` | DATETIME | − | − | Created / updated timestamps |

Auth IDs are normalized into `user_providers`; delivery targets into `notification_channels` (not held here).

#### `user_sessions` — sessions

| Column | Type | NULL | Personal | Description |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | no | ○ | → users.id |
| `session_token` | VARCHAR(255) UNIQUE | no | ● | Cookie-stored token (auth credential) |
| `expires_at` | DATETIME | no | − | Expiry |
| `created_at` | DATETIME | − | − | |

> `session_token` is an auth credential; leakage allows impersonation. Cleanup after expiry is handled at the app/batch layer.

#### `user_providers` — social login providers

| Column | Type | NULL | Personal | Description |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | no | ○ | → users.id |
| `provider` | ENUM('line','google','twitter') | no | − | Provider type |
| `provider_id` | VARCHAR(255) | no | ● | User ID on the provider side (external identifier) |
| `created_at` | DATETIME | − | − | |

`UNIQUE(provider, provider_id)`. Designed so one user can hold multiple providers (currently single in practice).

#### `notification_channels` — delivery targets

| Column | Type | NULL | Personal | Description |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | no | ○ | → users.id |
| `channel_type` | ENUM('line','email','telegram') | no | − | Channel type |
| `channel_value` | VARCHAR(255) | no | ● | Destination (LINE userId / email / Telegram chat_id) |
| `enabled` | TINYINT(1) | def. 1 | − | On/off |
| `created_at` | DATETIME | − | − | |

`UNIQUE(user_id, channel_type)`. The email channel is upserted in sync with `users.email`.

#### `telegram_connect_tokens` — temporary Telegram linking token

| Column | Type | NULL | Personal | Description |
|---|---|---|:---:|---|
| `token` | VARCHAR(64) PK | − | ● | One-time linking token |
| `user_id` | INT FK | no | ○ | → users.id |
| `expires_at` | DATETIME | no | − | Expiry (short-lived) |

### 2. User-operated data (002_user_data.sql)

#### `stake_addresses` — registered stake addresses (My Page, max 3)

| Column | Type | NULL | Personal | Description |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | no | ○ | → users.id |
| `address` | VARCHAR(255) | no | ● | Stake address (stake1...). On-chain identifier |
| `wallet_address` | VARCHAR(255) | yes | ● | addr1... at registration (shown for receiving) |
| `nickname` | VARCHAR(100) | no | ○ | User-assigned nickname |
| `role` | ENUM('delegator','drep','abstain') | def. delegator | − | Auto-updated via Koios/Ogmios |
| `role_checked_at` | DATETIME | yes | − | Last role check |
| `delegated_drep_id` / `_name` | VARCHAR(255) | yes | ○ | Delegated DRep (auto-updated) |
| `delegated_pool_id` / `_name` | VARCHAR(255) | yes | ○ | Delegated pool (auto-updated) |
| `spo_pool_id` | VARCHAR(64) | yes | ○ | Set when this stake addr is a pool's reward_addr/owner |
| `verified` | TINYINT(1) | def. 0 | − | Ownership-proven flag (CIP-8 signData) |
| `verified_at` | DATETIME | yes | − | Ownership-proof timestamp |
| `last_event_slot` | BIGINT | yes | − | Last slot reflected by the Ogmios listener (rollback handling) |
| `created_at` | DATETIME | − | − | |

The 3-item cap is enforced at the app layer. Ownership is self-declared + optional CIP-8 verification.

#### `favorites` — favorites

| Column | Type | NULL | Personal | Description |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | no | ○ | → users.id |
| `proposal_uuid` | VARCHAR(255) | def. '' | − | Target ID (per type below) |
| `type` | ENUM('catalyst','governance','drep','pool') | def. catalyst | − | Target type |
| `created_at` | DATETIME | − | − | Favorited timestamp |

`UNIQUE(user_id, proposal_uuid, type)`. Meaning of `proposal_uuid` depends on type:
- `catalyst` → CIDP UUID · `governance` → GA proposal_id · `drep` → drep_id (bech32, CIP-129) · `pool` → pool_id (bech32)

> The favorited entities (proposals, DReps, pools) are public on-chain/Catalyst data. The personal aspect is the linkage of "who favorited what" (preferences).

#### `wallet_verification_nonces` — ownership-check nonce (ephemeral / 5-min TTL)

| Column | Type | NULL | Personal | Description |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | no | ○ | → users.id |
| `stake_address` | VARCHAR(255) | no | ● | Address being verified |
| `nonce` | VARCHAR(64) | no | − | One-time value |
| `expires_at` | DATETIME | no | − | NOW+5min |
| `used` | TINYINT(1) | def. 0 | − | One-time-use flag |
| `created_at` | DATETIME | − | − | |

Short-lived data for the CIP-30 `signData` verification flow.

### 3. Personal-data summary

| Aspect | Content |
|---|---|
| **Identifiers / contact** | `users.email`, `notification_channels.channel_value` (email/LINE/Telegram), `user_providers.provider_id`, `stake_addresses.address`/`wallet_address` |
| **Auth credentials** | `user_sessions.session_token`, `telegram_connect_tokens.token` |
| **Preferences / behavior** | `favorites` (targets and timestamps), `stake_addresses` (delegation targets, nickname) |
| **Deletion (cascade)** | Every child table has an FK to `users` with `ON DELETE CASCADE`; a user delete purges everything. **However, the account-deletion feature itself is not yet implemented (next phase)** |
| **Ephemeral data** | `wallet_verification_nonces` (5 min), `telegram_connect_tokens` (short-lived), `user_sessions` (expires_at) |
| **Export** | Favorites can be exported as CSV (see [`export_spec.md`](export_spec.md)) |

### Appendix: related user-linked tables (outside this doc's core "user store" scope)

User settings / logs that link to `user_id` but fall outside this doc's primary scope (identity + user-operated data). See each migration for details.

| Table | Migration | Content |
|---|---|---|
| `notification_settings` | 003 | Account-wide notification on/off (epoch_start, etc.) |
| `stake_notification_settings` | 003 | Per-stake-address notification on/off (pool/DRep events) |
| `notification_log` | 003 | Send log / dedup (dedup_key). May contain destinations and content fragments |
| `subscriptions` | 014 | Subscription state (implementation in next phase) |

> Whether to include these in the personal-data inventory is a legal judgment. Fold them in here if needed.

---

## 日本語

> 「個人データ」列の凡例: ●=個人情報・識別子に該当 / ○=ユーザー紐付けだが単体では非識別 / −=非個人データ

### 全体像

```
users (1) ──┬─< user_sessions          セッション
            ├─< user_providers         ソーシャルログイン ID
            ├─< notification_channels   通知送信先（LINE/Email/Telegram）
            ├─< telegram_connect_tokens 一時連携トークン
            ├─< stake_addresses         登録ステークアドレス（最大3）
            ├─< favorites               お気に入り
            └─< wallet_verification_nonces  所有確認 nonce（一時）
```

すべての子テーブルは `user_id` 外部キーで `users` を参照し、**`ON DELETE CASCADE`**。`users` を削除すれば紐付くユーザーデータは全て自動削除される。

### 1. 認証コア（001_users_auth.sql）

#### `users` — ユーザー基本情報

| カラム | 型 | NULL | 個人データ | 説明 |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | ○ | 内部ユーザー ID |
| `username` | VARCHAR(255) | 不可 | ● | 表示名（プロバイダ由来 or ユーザー編集） |
| `email` | VARCHAR(255) | 可 | ● | メールアドレス。設定時 `notification_channels` に自動 upsert |
| `avatar_url` | TEXT | 可 | ● | アバター画像 URL |
| `external_uuid` | CHAR(36) UNIQUE | 可 | ○ | 外部システム（フィードバックフォーム等）用の識別子 UUID v4。**認証用ではなく識別子のみ**。OAuth アイデンティティとは切り離す |
| `notification_frequency` | ENUM('instant','daily') | 既定 instant | − | 通知頻度設定 |
| `language` | ENUM('ja','en') | 既定 ja | − | 表示言語 |
| `created_at` / `updated_at` | DATETIME | − | − | 作成 / 更新時刻 |

認証 ID は `user_providers` に、通知送信先は `notification_channels` に正規化済み（このテーブルには持たない）。

#### `user_sessions` — セッション

| カラム | 型 | NULL | 個人データ | 説明 |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | 不可 | ○ | → users.id |
| `session_token` | VARCHAR(255) UNIQUE | 不可 | ● | Cookie 保存トークン（認証クレデンシャル相当） |
| `expires_at` | DATETIME | 不可 | − | 失効時刻 |
| `created_at` | DATETIME | − | − | |

> `session_token` は認証情報。漏洩でなりすまし可。失効後の掃除はアプリ層/バッチで実施。

#### `user_providers` — ソーシャルログインプロバイダ

| カラム | 型 | NULL | 個人データ | 説明 |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | 不可 | ○ | → users.id |
| `provider` | ENUM('line','google','twitter') | 不可 | − | プロバイダ種別 |
| `provider_id` | VARCHAR(255) | 不可 | ● | プロバイダ側のユーザー ID（外部識別子） |
| `created_at` | DATETIME | − | − | |

`UNIQUE(provider, provider_id)`。1 ユーザーが複数プロバイダを持てる設計（現状は単一運用）。

#### `notification_channels` — 通知送信先

| カラム | 型 | NULL | 個人データ | 説明 |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | 不可 | ○ | → users.id |
| `channel_type` | ENUM('line','email','telegram') | 不可 | − | チャンネル種別 |
| `channel_value` | VARCHAR(255) | 不可 | ● | 送信先（LINE userId / メールアドレス / Telegram chat_id） |
| `enabled` | TINYINT(1) | 既定 1 | − | ON/OFF |
| `created_at` | DATETIME | − | − | |

`UNIQUE(user_id, channel_type)`。メールチャンネルは `users.email` と連動 upsert。

#### `telegram_connect_tokens` — Telegram 連携一時トークン

| カラム | 型 | NULL | 個人データ | 説明 |
|---|---|---|:---:|---|
| `token` | VARCHAR(64) PK | − | ● | 連携用ワンタイムトークン |
| `user_id` | INT FK | 不可 | ○ | → users.id |
| `expires_at` | DATETIME | 不可 | − | 失効時刻（短命） |

### 2. ユーザー操作データ（002_user_data.sql）

#### `stake_addresses` — 登録ステークアドレス（マイページ管理 / 最大3件）

| カラム | 型 | NULL | 個人データ | 説明 |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | 不可 | ○ | → users.id |
| `address` | VARCHAR(255) | 不可 | ● | ステークアドレス（stake1...）。オンチェーン識別子 |
| `wallet_address` | VARCHAR(255) | 可 | ● | 登録時の addr1...（受信表示用） |
| `nickname` | VARCHAR(100) | 不可 | ○ | ユーザー付与のニックネーム |
| `role` | ENUM('delegator','drep','abstain') | 既定 delegator | − | Koios/Ogmios で自動更新 |
| `role_checked_at` | DATETIME | 可 | − | role 最終確認時刻 |
| `delegated_drep_id` / `_name` | VARCHAR(255) | 可 | ○ | 委任先 DRep（自動更新） |
| `delegated_pool_id` / `_name` | VARCHAR(255) | 可 | ○ | 委任先プール（自動更新） |
| `spo_pool_id` | VARCHAR(64) | 可 | ○ | この stake addr が pools の reward_addr/owners の場合に値あり |
| `verified` | TINYINT(1) | 既定 0 | − | CIP-8 signData による所有証明済みフラグ |
| `verified_at` | DATETIME | 可 | − | 所有証明時刻 |
| `last_event_slot` | BIGINT | 可 | − | Ogmios listener が反映した最終 slot（rollback 対応） |
| `created_at` | DATETIME | − | − | |

上限 3 件はアプリ層で制御。所有確認は自己申告 + 任意の CIP-8 検証。

#### `favorites` — お気に入り

| カラム | 型 | NULL | 個人データ | 説明 |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | 不可 | ○ | → users.id |
| `proposal_uuid` | VARCHAR(255) | 既定 '' | − | 対象 ID（下記 type 別） |
| `type` | ENUM('catalyst','governance','drep','pool') | 既定 catalyst | − | 対象種別 |
| `created_at` | DATETIME | − | − | お気に入り登録時刻 |

`UNIQUE(user_id, proposal_uuid, type)`。`proposal_uuid` の意味は type 依存:
- `catalyst` → CIDP の UUID / `governance` → GA の proposal_id / `drep` → drep_id(bech32, CIP-129) / `pool` → pool_id(bech32)

> お気に入り対象（提案・DRep・プール）自体は公開オンチェーン/カタリストデータ。個人データは「誰が何をお気に入りにしたか（嗜好）」の紐付けの方。

#### `wallet_verification_nonces` — 所有確認 nonce（一時 / 5分 TTL）

| カラム | 型 | NULL | 個人データ | 説明 |
|---|---|---|:---:|---|
| `id` | INT PK AI | − | − | |
| `user_id` | INT FK | 不可 | ○ | → users.id |
| `stake_address` | VARCHAR(255) | 不可 | ● | 検証対象アドレス |
| `nonce` | VARCHAR(64) | 不可 | − | ワンタイム値 |
| `expires_at` | DATETIME | 不可 | − | NOW+5min |
| `used` | TINYINT(1) | 既定 0 | − | 1 回限り使用フラグ |
| `created_at` | DATETIME | − | − | |

CIP-30 `signData` 検証フロー用の短命データ。

### 3. 個人データ観点まとめ

| 観点 | 内容 |
|---|---|
| **識別子・連絡先** | `users.email`、`notification_channels.channel_value`（メール/LINE/Telegram）、`user_providers.provider_id`、`stake_addresses.address`/`wallet_address` |
| **認証クレデンシャル** | `user_sessions.session_token`、`telegram_connect_tokens.token` |
| **嗜好・行動** | `favorites`（お気に入り対象と時刻）、`stake_addresses`（委任先・ニックネーム） |
| **削除（カスケード）** | 全子テーブルが `users` への FK + `ON DELETE CASCADE`。ユーザー削除で一括消去可能。**ただしアカウント削除機能自体は現状未実装（次フェーズ）** |
| **短命データ** | `wallet_verification_nonces`（5分）、`telegram_connect_tokens`（短命）、`user_sessions`（expires_at 失効） |
| **エクスポート** | お気に入りは CSV 出力対応（[`export_spec.md`](export_spec.md) 参照） |

### 付録: 関連する user_id 紐付けテーブル（本書のコア「ユーザーストア」範囲外）

ユーザー設定・ログとして `user_id` に紐付くが、本書の主対象（identity + ユーザー操作データ）からは外れるもの。詳細は各マイグレーション参照。

| テーブル | マイグレーション | 内容 |
|---|---|---|
| `notification_settings` | 003 | ユーザー全体の通知 ON/OFF（epoch_start 等） |
| `stake_notification_settings` | 003 | ステークアドレス別の通知 ON/OFF（プール/DRep 系） |
| `notification_log` | 003 | 送信ログ・重複防止（dedup_key）。送信先・本文断片を含み得る |
| `subscriptions` | 014 | サブスクリプション状態（実装は次フェーズ） |

> これらを保有個人データ棚卸しに含めるかは法務判断。必要なら本書に取り込む。
