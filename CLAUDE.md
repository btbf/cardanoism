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
| 通知 | LINE Messaging API / メール / Telegram Bot API |

---

## 実装スコープ：ソーシャルログイン＆マイページ機能

### ブランチ：`login-mypage`

---

## 1. ソーシャルログイン

### 1-1. 対応プロバイダ

| プロバイダ | 今回 | 備考 |
|-----------|------|------|
| LINE | ✅ 実装 | ログイン＋通知チャンネル連携 |
| Google | 次フェーズ | 海外スケール時に対応 |
| X（Twitter） | 次フェーズ | 海外スケール時に対応 |

### 1-2. 認証実装

- **ライブラリ：** [Authlib](https://authlib.org/)（Python OAuth2ライブラリ）
- ReflexのベースであるFastAPIのルートとしてLINE OAuth2フローを実装
- セッション管理はReflex State + サーバーサイドセッション
- ウォレット接続は**対象外**

### 1-3. ログインUI

- **専用ログインページ：** `/login`
- **ログインモーダル：** サイト全体のどこからでも表示可能
- 未ログインユーザーがマイページにアクセスした場合 → ログインモーダルを表示
- ナビバー：
  - 未ログイン時：「ログイン」ボタンを表示
  - ログイン後：ユーザーアバターアイコンを表示 → クリックでマイページへ遷移

---

## 2. マイページ

### 2-1. URL・ルーティング

- `/mypage` にまとめてタブ切り替え
- タブ構成：**お気に入り / プロフィール / ステークアドレス / 通知管理**

### 2-2. お気に入りタブ

#### カタリスト提案

- カタリスト提案とガバナンス提案を**別タブ**で表示
- ガバナンス提案お気に入りは**スコープ外（将来対応）**

#### カタリスト提案の絞り込み・並び替え

| 機能 | 項目 |
|------|------|
| 絞り込み | Fund別、ステータス別（採択/未採択） |
| 並び替え | 要求金額順 |

### 2-3. プロフィール編集タブ

編集可能な項目：

- ユーザー名（表示名）
- アバター画像
- メールアドレス

### 2-4. ステークアドレスタブ

- 登録上限：**1ユーザーあたり最大3件**
- 各アドレスにニックネームをつけられる
- 登録・削除が可能
- 所有確認：**自己申告制（確認なし）**
- ※サブスクリプションによる上限拡張は**次フェーズ**

### 2-5. 通知管理タブ

#### LINE連携

- LINE連携（Messaging API）の接続・切断をここで行う

#### 通知チャンネル

連携済みのチャンネル全体に一括送信する（チャンネルごとの個別設定なし）

| チャンネル | 実装 |
|-----------|------|
| LINE | LINE Messaging API |
| メール | メール送信 |
| Telegram | Telegram Bot API |

#### 通知イベント

イベントごとに **ON/OFF** を設定できる。

**ステークプール通知**

| イベント | 説明 |
|---------|------|
| プールの引退 | 委任先プールが引退予告を出した場合 |
| 手数料変更 | 固定費・変動手数料が変更された場合 |
| 飽和状態超過 | プールが飽和状態を超えた場合 |
| 次エポック報酬予測 | 翌エポックの報酬予測額を通知 |
| 報酬受け取り | 報酬が受け取れる状態になった場合 |
| 長期委任リマインダー | 3ヶ月ごとに委任先を再確認するリマインダー |

**DRep通知**

| イベント | 説明 |
|---------|------|
| 新提案通知 | 新しいガバナンス提案が作成された場合 |
| 委任先DRep投票通知 | 委任先DRepが投票した場合（投票内容・理由を含む） |
| 長期委任リマインダー | 3ヶ月ごとに委任先DRepを再確認するリマインダー |

#### 通知の配信頻度設定

ユーザーが以下から選択できる：

- **即時通知**：イベント発生時にすぐ送信
- **日次まとめ通知**：1日1回まとめて送信

#### 通知履歴

- 通知管理タブ内に通知履歴セクションを設ける（**将来対応**）

---

## 3. LINEミニアプリ（仕様のみ・実装は次フェーズ）

- LINEミニアプリをベースとしたCardanoismの専用アプリを提供予定
- ステークアドレスの所有確認はLINEミニアプリ経由で行う想定
- 詳細仕様は次フェーズで策定

---

## 4. データモデル（追加・変更）

### DB構成

- **DB：** MariaDB（既存）
- **接続方法：** `mariadb` Pythonライブラリ + コネクションプール（`db_connect.py` の既存パターンに従う）
- SQLModel（rx.Model）は**使わない**。生SQLでテーブル操作する

### 追加テーブル（MariaDB DDL）

```sql
-- ユーザーテーブル
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    avatar_url TEXT,
    google_id VARCHAR(255),
    twitter_id VARCHAR(255),
    line_id VARCHAR(255),
    telegram_chat_id VARCHAR(255),
    notification_frequency ENUM('instant', 'daily') DEFAULT 'instant',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ステークアドレステーブル（1ユーザー最大3件）
CREATE TABLE stake_addresses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    address VARCHAR(255) NOT NULL,
    nickname VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- お気に入りテーブル
CREATE TABLE favorites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    proposal_id INT NOT NULL,
    type ENUM('catalyst', 'governance') NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 通知設定テーブル（イベントごとON/OFF）
CREATE TABLE notification_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    -- イベント種別例: pool_retire, pool_fee_change, pool_saturation,
    --                 pool_reward_estimate, pool_reward_received, pool_delegation_reminder,
    --                 drep_new_proposal, drep_vote, drep_delegation_reminder
    enabled TINYINT(1) DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_event (user_id, event_type)
);
```

---

## 5. ページ構成

| ページ | ルート | 説明 |
|-------|--------|------|
| ログインページ | `/login` | LINEログインボタン |
| マイページ | `/mypage` | タブ切り替え（お気に入り/プロフィール/ステークアドレス/通知管理） |

---

## 6. 次フェーズのスコープ（今回対象外）

- Google・Xログイン（海外スケール時に対応）
- サブスクリプション機能（有料プラン・ステークアドレス上限拡張）
- LINEミニアプリ実装
- ガバナンス提案お気に入り
- アカウント削除機能
- 通知履歴ページ
- 複数ソーシャルアカウントの同一アカウントへの連携
