# Cardanoism 仕様書

## Claude Code 開発ルール

- 難しいタスクの前に `/effort high` を実行して思考予算を上げること
- `showThinkingSummaries: true` を有効にして思考過程を可視化すること
- **読んでいないコードは変更するな。** 必ずファイルを読んでから変更すること

---

## プロジェクト概要

CardanoガバナンスをナビゲートするReflexベースの日本語ポータルサイト。

| 項目 | 内容 |
|------|------|
| フレームワーク | **Reflex**（Python + FastAPI） |
| DB | **MariaDB**（`mariadb` Pythonライブラリ + コネクションプール） |
| DB接続 | `cardanoism/backend/db_connect.py` の既存パターンに従う |
| ORM | 使用しない（生SQLで操作） |
| 認証 | **Authlib**（OAuth2） |
| 通知 | LINE Messaging API / SMTP メール |
| オンチェーンデータ | **Koios API**（`cardanoism/backend/koios.py`） |

---

## 実装済みスコープ

### ブランチ：`login-mypage`

---

## 1. ソーシャルログイン

### 1-1. 対応プロバイダ

| プロバイダ | 状態 | 備考 |
|-----------|------|------|
| LINE | ✅ 実装済み | ログイン＋通知チャンネル連携 |
| Google | ✅ 実装済み | ログインのみ（通知チャンネルはメール経由） |
| X（Twitter） | 次フェーズ | 海外スケール時に対応 |

### 1-2. 認証実装

- **ライブラリ：** [Authlib](https://authlib.org/)（Python OAuth2ライブラリ）
- ReflexのベースであるFastAPIのルートとしてLINE / Google OAuth2フローを実装
- セッション管理はReflex State（`AuthState`）+ サーバーサイドセッション（`user_sessions` テーブル）
- ログインプロバイダは `user_providers` テーブルで管理（1ユーザーが複数プロバイダを持てる設計だが、現状は単一）
- ウォレット接続は**対象外**（手動入力のみ）

### 1-3. ログインUI

- **専用ログインページ：** `/login`
- **ログインモーダル：** サイト全体のどこからでも表示可能（`login_modal.py`）
- 未ログインユーザーがマイページにアクセスした場合 → ログインモーダルを表示
- ナビバー：
  - 未ログイン時：「ログイン」ボタンを表示
  - ログイン後：ユーザーアバターアイコンを表示 → クリックでマイページへ遷移
- Googleボタンは標準デザイン仕様（ピル形状・Roboto Medium・`rx.color_mode_cond` でライト/ダークテーマ対応）

---

## 2. マイページ（`/mypage`）

タブ切り替え構成。URL クエリパラメータ `?tab=` でタブを指定できる。

### タブ構成

| タブ | `?tab=` | 説明 |
|------|---------|------|
| お気に入り | `favorites` | カタリスト提案のブックマーク一覧 |
| プロフィール | `profile` | 表示名・メールアドレスの編集 |
| ステークアドレス | `stake` | アドレスの登録・削除（最大3件） |
| 通知管理 | `notification` | チャンネル・イベント ON/OFF 設定 |

### 2-1. お気に入りタブ

- カタリスト提案のブックマーク一覧
- 絞り込み：Fund 別・ステータス別（採択/未採択）
- 並び替え：要求金額順
- ガバナンス提案お気に入りは**次フェーズ**

### 2-2. プロフィール編集タブ

- 編集可能：ユーザー名・メールアドレス・アバター画像
- Googleログインユーザーはメールアドレス変更不可（Google アカウントのメールを使用）
- **メール保存時の挙動：** `notification_channels` テーブルのメールチャンネルを自動 upsert する。メール削除時は自動削除。これにより通知管理タブのメール ON/OFF が連動して表示・非表示される。

### 2-3. ステークアドレスタブ

- 登録上限：**1ユーザーあたり最大3件**
- 各アドレスにニックネームをつけられる
- 所有確認：自己申告制（確認なし）
- 登録時に Koios API でステークアドレスとロール（delegator / drep / abstain）を自動取得
- ※サブスクリプションによる上限拡張は次フェーズ

### 2-4. 通知管理タブ

#### 通知チャンネル

`notification_channels` テーブルで管理。ユーザーが持つチャンネルのみ表示される。

| チャンネル | 表示条件 | ON/OFF |
|-----------|---------|--------|
| メール | `users.email` が登録済み（自動 upsert） | ✅ |
| LINE | LINE 通知連携済み（Messaging API） | ✅ |
| Telegram | 次フェーズ | - |

#### LINE連携

- 通知管理タブ内で接続・切断
- LINE ログインとは別フロー（`/auth/line/connect`）

#### 通知イベント設定

イベントは 2 層で管理する。

| 層 | テーブル | 対象イベント |
|----|---------|------------|
| ユーザー全体 | `notification_settings` | `epoch_start` |
| ステークアドレスごと | `stake_notification_settings` | プール・DRep 系全イベント |

**ステークプール通知**（`stake_notification_settings`）

| event_type | 説明 |
|-----------|------|
| `pool_retire` | 委任先プールが引退予告 |
| `pool_fee_change` | 固定費・変動手数料の変更 |
| `pool_saturation` | 飽和状態超過 |
| `pool_pledge_shortage` | 誓約不足 |
| `pool_reward_received` | エポック報酬の入金 |
| `pool_delegation_reminder` | 長期委任リマインダー（90/120/365日） |

**DRep通知**（`stake_notification_settings`）

| event_type | 説明 |
|-----------|------|
| `drep_new_governance_action` | 新しいガバナンスアクションの提出 |
| `drep_vote` | 委任先 DRep の投票 |
| `drep_status_change` | 委任先 DRep のステータス変化 |
| `drep_delegation_reminder` | 長期委任リマインダー（90/120/365日） |

---

## 3. 通知バッチワーカー（`notify_worker.py`）

cron で定期実行する独立スクリプト。Reflex アプリとは独立して動作する。

### アーキテクチャ

```
notify_worker.py
├── 状態管理        : notification_check_state テーブル（前回値との差分検出）
├── 重複送信防止    : notification_log テーブル（dedup_key で管理）
├── LINE 送信       : cardanoism/backend/line_notify.py（Messaging API）
└── メール送信      : cardanoism/backend/mail_notify.py（SMTP）
```

### 送信チャンネルの取得方法

- LINE：`notification_channels WHERE channel_type='line'` を JOIN
- メール：`notification_channels WHERE channel_type='email'` を JOIN
- 両チャンネルをマージして送信（`_merge_stake_channels()` ヘルパー）

### エポック時刻チェック（`EPOCH_CHECK_WINDOW_MIN`）

`--event epoch_start` 実行時に時間外スキップを行う機能。

- Koios `/tip` の `epoch_slot`（エポック内経過秒数）で判定
- `EPOCH_CHECK_WINDOW_MIN=60` のとき、エポック開始から 60 分以内のみ処理
- ネットワーク別エポック長：mainnet/preprod = 432,000秒（5日）、preview = 86,400秒（1日）

```cron
# 推奨 cron 設定（毎日 21:44 UTC に実行、mainnet の場合）
44 21 * * *  EPOCH_CHECK_WINDOW_MIN=60 python notify_worker.py --event epoch_start
44 21 * * *  は実際には 5 日に 1 回だけ処理が走る

# エポック切り替わり時刻確認
python notify_worker.py --epoch-schedule
```

### 推奨 cron 設定

```cron
44 21 * * *   EPOCH_CHECK_WINDOW_MIN=60 python /path/to/notify_worker.py --event epoch_start
*/30 * * * *  python /path/to/notify_worker.py --event pool
*/30 * * * *  python /path/to/notify_worker.py --event drep
0 * * * *     python /path/to/notify_worker.py --event reminder
```

---

## 4. メール送信（`cardanoism/backend/mail_notify.py`）

SMTP 経由でメールを送信するヘルパー。

| 関数 | 説明 |
|------|------|
| `send_email(to, subject, html, text)` | SMTP 送信（STARTTLS/SSL 両対応） |
| `build_html(subject, lines, cta_url, ...)` | Cardanoism ブランドの HTML メール生成 |
| `build_text(subject, lines, cta_url, ...)` | プレーンテキスト生成 |

---

## 5. 環境変数

| 変数 | 説明 | デフォルト |
|------|------|----------|
| `KOIOS_NETWORK` | Koios ネットワーク（mainnet / preprod / preview） | `mainnet` |
| `CARDANOISM_URL` | サイトの URL（通知メール内リンク等に使用） | `https://cardanoism.app` |
| `LINE_CLIENT_ID` | LINE OAuth クライアント ID | - |
| `LINE_CLIENT_SECRET` | LINE OAuth クライアントシークレット | - |
| `LINE_REDIRECT_URI` | LINE OAuth コールバック URI | - |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API チャンネルアクセストークン | - |
| `GOOGLE_CLIENT_ID` | Google OAuth クライアント ID | - |
| `GOOGLE_CLIENT_SECRET` | Google OAuth クライアントシークレット | - |
| `GOOGLE_REDIRECT_URI` | Google OAuth コールバック URI | - |
| `MAIL_SMTP_HOST` | SMTP サーバーホスト | - |
| `MAIL_SMTP_PORT` | SMTP ポート（587=STARTTLS, 465=SSL） | `587` |
| `MAIL_SMTP_USER` | SMTP ユーザー（送信元アドレス） | - |
| `MAIL_SMTP_PASSWORD` | SMTP パスワード | - |
| `MAIL_FROM_NAME` | 送信者表示名 | `Cardanoism` |
| `EPOCH_CHECK_WINDOW_MIN` | エポック切り替わりウィンドウ（分）。0=常に実行 | `0` |

---

## 6. データモデル

- **DB：** MariaDB（既存）
- **接続：** `mariadb` Pythonライブラリ + コネクションプール（`db_connect.py` の既存パターンに従う）
- SQLModel（rx.Model）は**使わない**。生 SQL でテーブル操作する

### テーブル一覧

| テーブル | 説明 |
|---------|------|
| `users` | ユーザー基本情報（email, username, avatar_url 等） |
| `user_sessions` | セッショントークン管理 |
| `user_providers` | ソーシャルログインプロバイダ（line / google / twitter） |
| `notification_channels` | 通知チャンネル（line / email）と enabled フラグ |
| `stake_addresses` | ステークアドレス（最大3件/ユーザー） |
| `favorites` | お気に入り提案（catalyst / governance） |
| `notification_settings` | ユーザー全体の通知設定（epoch_start 等） |
| `stake_notification_settings` | ステークアドレスごとの通知設定 |
| `notification_check_state` | バッチワーカーの状態管理（前回チェック値） |
| `notification_log` | 送信ログ・重複防止（dedup_key） |

### `notification_channels` テーブル

```sql
CREATE TABLE IF NOT EXISTS notification_channels (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  user_id      INT NOT NULL,
  channel_type ENUM('line', 'email') NOT NULL,
  channel_value VARCHAR(255) NOT NULL,   -- LINE user ID / メールアドレス
  enabled      TINYINT(1) NOT NULL DEFAULT 1,
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_user_channel (user_id, channel_type)
);
```

---

## 7. ページ構成

| ページ | ルート | 説明 |
|-------|--------|------|
| ログインページ | `/login` | LINE / Google ログインボタン |
| マイページ | `/mypage` | タブ切り替え（お気に入り/プロフィール/ステークアドレス/通知管理） |

---

## 8. 次フェーズのスコープ（現在対象外）

- X（Twitter）ログイン
- Telegram 通知チャンネル
- サブスクリプション機能（有料プラン・ステークアドレス上限拡張）
- LINEミニアプリ実装
- ガバナンス提案お気に入り
- アカウント削除機能
- 通知履歴ページ
- 複数ソーシャルアカウントの同一アカウントへの連携
