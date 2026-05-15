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

> 新規 VPS への一括デプロイ手順は [`docs/initial-setup.md`](docs/initial-setup.md) を参照。3 系統を 1 ホストで立ち上げる流れがまとまっている。

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

### 3-4. 投票理由ワーカー（`vote_rationale_worker.py`）

`ogmios_listener.py` が DRep 投票を検知して `proposal_votes` に即時書き込みするが、`rationale` 本文は IPFS fetch + OpenAI 翻訳が必要なので listener では行わない。代わりにこの常駐ワーカーが短間隔（デフォルト 10 秒）で polling して、`rationale IS NULL AND meta_url IS NOT NULL` の行を見つけて埋める。

**設計方針**: listener は「チェーン検知 + DB 書き込み」に専念し、重い I/O（IPFS / OpenAI）はこのワーカーに切り出す責務分離。

**CLI コマンド**:
- `python vote_rationale_worker.py` — 常駐起動
- `python vote_rationale_worker.py --poll-interval 10 --fetch-limit 20 --translate-limit 10` — パラメータ指定

`notify_worker.py --event vote_rationale_sync` の 4h cron はバックアップとして残す（このワーカーが止まっていても遅延付きで処理される）。

セットアップ詳細: [`docs/realtime-notification-backend.md`](docs/realtime-notification-backend.md) の systemd セクションを参照。

### 3-5. 共通実装

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

## 5. シークレット管理 (Infisical)

`.env` は廃止し、**Infisical** で集中管理する。`.infisical.json` (workspaceId / defaultEnvironment) はリポジトリにコミット、secret 本体は Infisical 側のみ。

**environment スコープ**:
- `local`  : Windows ローカル開発用 (default)
- `mainnet`: 本番 VPS (mainnet)
- `preview`: テストネット VPS (preview)

**ローカル開発の起動コマンド**:

```bash
# Reflex 起動
infisical run -- reflex run

# 別 environment を使う場合
infisical run --env=preview -- reflex run

# notify_worker / ga_ai_worker 等の単発実行
infisical run -- python notify_worker.py --event vote_sync
```

> 素の `reflex run` だと `os.getenv` が空を返して起動失敗する。必ず `infisical run --` でラップする。

**VPS (systemd / cron) の運用**:

VPS では Machine Identity (Service Token) で非対話認証する。詳細は `docs/realtime-notification-backend.md` 5-2。

**管理対象 secret**:

| 変数 | 説明 | デフォルト |
|------|------|----------|
| `KOIOS_NETWORK` | Koios ネットワーク（mainnet / preprod / preview） | `mainnet` |
| `KOIOS_API_KEY` | Koios 認証キー（rate limit 緩和、任意） | - |
| `OGMIOS_URL` | Ogmios WebSocket URL（リアルタイム通知用） | `ws://109.123.231.103:1337` |
| `CARDANOISM_URL` | サイトの URL（通知メール内リンク等に使用） | `https://cardanoism.com` |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASS` / `DB_NAME` | MariaDB 接続情報 | - |
| `LINE_CLIENT_ID` / `LINE_CLIENT_SECRET` / `LINE_REDIRECT_URI` | LINE OAuth | - |
| `LINE_MESSAGING_TOKEN` | LINE Messaging API（通知用） | - |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Google OAuth | - |
| `MAIL_SMTP_HOST` / `MAIL_SMTP_PORT` / `MAIL_SMTP_USER` / `MAIL_SMTP_PASSWORD` / `MAIL_FROM_NAME` | SMTP メール | - |
| `TELEGRAM_BOT_TOKEN` | Telegram 通知 | - |
| `ADMIN_USER_ID` | 管理者用通知疎通テスト（`notify_worker.py --event notify_test`）の対象ユーザー。このユーザーの `notification_channels` に登録済みの全チャンネルへ送信 | - |
| `GPT_API_KEY` | OpenAI API キー（GA AI 分析・投票理由翻訳） | - |
| `OPENAI_MODEL` | OpenAI モデル名 | `gpt-4o-mini` |
| `EPOCH_CHECK_WINDOW_MIN` | エポック切り替わりウィンドウ（分）。0=常に実行 | `0` |
| `FEEDBACK_FORM_URL` | ベータ版フィードバック用 Google Form の viewform URL | - |
| `FEEDBACK_FORM_USER_ID_ENTRY` | Google Form の user_id 短答フィールドの entry ID（例: `entry.123456`） | - |
| `FEEDBACK_FORM_USERNAME_ENTRY` | Google Form の username 短答フィールドの entry ID（任意） | - |

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
- 複数ソーシャルアカウントの同一ソーシャルアカウントへの連携

---

## 9. Reflex フレームワーク制約・知見

実装中に判明した Reflex の特性と回避策。次セッション以降の自分が同じ罠にハマらないため。

### 9-1. レンダリング: SPA のみ

| モード | サポート |
|---|---|
| SPA (default) | ✅ |
| SSG / 静的プリレンダー | ❌ (`prerender_routes` API なし) |
| SSR (リクエスト毎サーバ生成) | ❌ |

→ ユーザー固有ページ（マイページ、お気に入り）の静的化は不可。SEO 重要ページは tag メタを動的更新で対応。

### 9-2. Google Analytics は手動 page_view 追跡が必須

SPA なので URL 変更で自動 page_view が発火しない。`cardanoism.py` の `_GA_INLINE_SCRIPT` で `history.pushState` / `replaceState` / `popstate` をフックして、各遷移時に手動で `gtag('event', 'page_view', ...)` を発火させる。`requestAnimationFrame` で 1 frame 遅延させて React の `document.title` 更新を待つのがポイント。

### 9-3. WASM 系 npm ライブラリ取り込み

Reflex 公式は WASM をサポートしていない。Cardano lib (Lucid Evolution / MeshSDK) のような WASM 依存パッケージは Vite/Rolldown と相性が悪い:

- `libsodium-wrappers-sumo@0.7.16` のパッケージング不具合（[issue #360](https://github.com/jedisct1/libsodium.js/issues/360)、0.8.0+ で修正済）
- ESM 統合 (`import.wasm`) のサポートに `vite-plugin-wasm` + `vite-plugin-top-level-await` が必要
- Node API polyfill (`global` / `Buffer` / `process`) も別途必要

**回避策**:
- `reflex-vite-config-plugin` で `optimizeDeps.exclude` 等を注入できる
- ただしネスト依存（`@cardano-sdk/...` 配下の独自 `node_modules`）まで完全制御は難しい
- 確実な解は **esbuild で self-host bundle 化して assets で配信**

→ **Phase 3（委任 tx 構築）はペンディング**。実装は別ブランチで esbuild bundle 方式で再挑戦予定。

### 9-4. カスタム React コンポーネント wrap の正規 API

`rx.Component` を継承して以下を提供する:

| メソッド | 役割 |
|---|---|
| `library = "<npm-name>"` / `tag = "<Component>"` | npm からの import |
| `add_imports() -> dict` | 追加 import 文（モジュールトップ） |
| `add_hooks() -> list[str]` | コンポーネント render 内 hooks |
| `add_custom_code() -> list[str]` | render 関数の外側に注入する JS |

`rx.Fragment` ベースで `add_custom_code` 単独でも使えるが、ローカル component を `library = None` で書くのは非サポート。

### 9-5. 推奨される browser-side scripting

| ニーズ | 推奨 API |
|---|---|
| 一度だけインジェクト | `rx.script(content)` (head_components 等で) |
| Python event から JS 実行 + 結果受け取り | `rx.call_script(js, callback=event)` (async OK) |
| state 変化に応じて JS 反応 | カスタム `rx.Component` で hooks 化 |

`rx.call_script` の引数 JS は async IIFE でラップして `try/catch` を被せると Python 側の `__error` 規約と合わせやすい（`wallet_state.py` の `_js_call` ヘルパー参照）。

### 9-6. バージョン情報

- **現在**: 0.8.22 (`pyproject.toml` / `requirements.txt`)
- **最新**: 0.9.1（2026-04-27 リリース）
- **0.9.x 破壊的変更**:
  - ビルド出力先: `.web/_static/*` → `.web/build/client/*`
  - DB スタック (`pydantic` / `sqlmodel` / `alembic`) は `reflex[db]` extra に分離
  - イベントキュー実装変更（`yield` 挙動の差異あり）
- アップグレードは別ブランチで慎重に検証すること
