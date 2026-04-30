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

## 3. 通知バックエンド

通知系は2系統で構成される。両系統とも同じ MariaDB を共有し、`notification_log.dedup_key` で重複送信を防ぐ。

### 3-1. リアルタイム通知（`ogmios_listener.py`）

cardano-node + Ogmios + WebSocket で、ブロック確定の瞬間にイベントを発火する常駐デーモン。

**担当**: `epoch_start` / `pool_epoch_performance` / `pool_retire` / `pool_fee_change` / `drep_new_governance_action` / `drep_vote`

セットアップ詳細: [`docs/realtime-notification-backend.md`](docs/realtime-notification-backend.md)

### 3-2. Koios ポーリング（`notify_worker.py`）

cron で定期実行する独立スクリプト。計算値・履歴値・キャッシュ同期を担当する。

**担当通知**: `pool_saturation` / `pool_pledge_shortage` / `pool_reward_received` / `pool_delegation_reminder` / `drep_delegation_reminder` / `drep_status_change` / `treasury_withdrawal_enacted`

**担当キャッシュ同期**: `treasury_sync` / `fiat_sync` / `drep_sync` / `vote_sync` / `summary_sync` / `params_sync` / `vote_rationale_sync`

セットアップ詳細: [`docs/koios-polling-backend.md`](docs/koios-polling-backend.md)

### 3-3. GA AI 分析（`ga_ai_worker.py`）

OpenAI gpt-5.4-mini で GA の**ファクト整理**をする常駐ワーカー。スコアや判定は出さず、提案の中立的な要約と主要ファクト（label_ja/en + value_ja/en）を JSON 出力し `governance_ai_analysis` に保存。TreasuryWithdrawals の場合は機械計算による NCL 上限内チェックも追加表示する。

> **設計方針**: AI には判定をさせない。情報整理だけ任せて判断はユーザーに委ねる。
> 過去の憲法準拠スコア / VISION 2030 KPI レーダー実装は AI 判定のブレが大きく信頼性が低いため廃止し、A 方針（ファクト整理）に転換した。

**自動 trigger**: `governance.py` の Koios sync が新規 GA を `governance_actions` に INSERT したタイミングで `bulk_enqueue` → ワーカーが pending を拾って処理。

**CLI コマンド**:
- `python notify_worker.py --event ga_ai_initial_sync` — 初回投入（Active / Ratified / Enacted / 直近 6 エポック）
- `python notify_worker.py --event ga_ai_reanalyze --proposal-id <id>` — 単一 GA を再分析（status 不問）
- `python notify_worker.py --event ga_ai_reanalyze --all` — Active な analyzed 全件を再分析

セットアップ詳細: [`docs/ga-ai-analysis-backend.md`](docs/ga-ai-analysis-backend.md)

### 3-4. 共通実装

- 状態管理: `notification_check_state` テーブル
- 重複送信防止: `notification_log` テーブル（`dedup_key` で判定）
- 送信ヘルパー: `flex_and_log()` / `email_and_log()` / `telegram_and_log()`（`notify_worker.py` に定義、`ogmios_listener.py` は import して再利用）
- 送信チャンネル取得: `notification_channels WHERE channel_type IN ('line', 'email', 'telegram')` を JOIN し `_merge_stake_channels()` でマージ

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
| `CARDANOISM_URL` | サイトの URL（通知メール内リンク等に使用） | `https://cardanoism.com` |
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

- **DB：** MariaDB
- **接続：** `mariadb` Pythonライブラリ + コネクションプール（`db_connect.py` の既存パターンに従う）
- SQLModel（rx.Model）は**使わない**。生 SQL でテーブル操作する
- **マイグレーション：** `cardanoism/backend/migrations/` 配下に統合済みスキーマ（001〜007）。すべて `CREATE TABLE IF NOT EXISTS` で冪等。詳細は同ディレクトリの `README.md`

### テーブル一覧

#### 認証・ユーザー（001_users_auth.sql / 002_user_data.sql）
| テーブル | 説明 |
|---------|------|
| `users` | ユーザー基本情報（username, email, avatar_url, language, notification_frequency） |
| `user_sessions` | セッショントークン管理 |
| `user_providers` | ソーシャルログインプロバイダ（line / google / twitter） |
| `notification_channels` | 通知チャンネル（line / email / telegram）と enabled フラグ |
| `telegram_connect_tokens` | Telegram Bot 連携時の一時トークン |
| `stake_addresses` | ステークアドレス（最大3件/ユーザー）+ 委任先 pool/drep 情報 |
| `favorites` | お気に入り提案（catalyst / governance） |

#### 通知（003_notifications.sql）
| テーブル | 説明 |
|---------|------|
| `notification_settings` | ユーザー全体の通知設定（epoch_start 等） |
| `stake_notification_settings` | ステークアドレスごとの通知設定 |
| `notification_check_state` | リアルタイム / バッチワーカーの状態管理（前回チェック値・カーソル） |
| `notification_log` | 送信ログ・重複防止（dedup_key） |

#### ガバナンス（004_governance.sql）
| テーブル | 説明 |
|---------|------|
| `governance_actions` | GA 本体（CIP-100/108 メタデータ含む） |
| `proposal_votes` | GA への投票（DRep / SPO / CC） |
| `proposal_voting_summary` | GA ごとの投票集計 |
| `protocol_params` | プロトコルパラメータ（id=1 固定） |
| `cc_members` | 憲法委員会メンバー |

#### キャッシュ（005〜007）
| テーブル | 説明 |
|---------|------|
| `dreps` | DRep 一覧 + CIP-119 メタデータ |
| `treasury_snapshot` | 最新トレジャリー残高（id=1 固定） |
| `treasury_withdrawal` | トレジャリー引き出し履歴 |
| `ncl_active` | 採用中の Net Change Limit（id=1 固定） |
| `fiat_rate` | ADA 法定通貨レート（id=1 固定） |

---

## 7. ページ構成

| ページ | ルート | 説明 |
|-------|--------|------|
| ログインページ | `/login` | LINE / Google ログインボタン |
| マイページ | `/mypage` | タブ切り替え（お気に入り/プロフィール/ステークアドレス/通知管理） |

---

## 8. 次フェーズのスコープ（現在対象外）

- X（Twitter）ログイン
- サブスクリプション機能（有料プラン・ステークアドレス上限拡張）
- LINEミニアプリ実装
- アカウント削除機能
- 通知履歴ページ
- 複数ソーシャルアカウントの同一アカウントへの連携
