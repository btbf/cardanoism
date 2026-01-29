# ようこそ！カルダノイズムへ

このサイトはカルダノブロックチェーンの総合ガバナンス日本語ポータルサイトです。

## セットアップ手順

このプロジェクトは `uv` を使った環境構築を前提にしています。

前提:
- PowerShell（Windows）または bash（macOS / Linux）
- MariaDB をローカルで起動できること

### 1) uv のインストール

Windows（winget）
```powershell
winget install --id AstralSoftware.UV -e
```

macOS（Homebrew）
```bash
brew install uv
```

Linux
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

確認:
```bash
uv --version
```

### 2) Python のインストール（uv経由）

`pyproject.toml` の指定に合わせて Python 3.11 を入れます。

```bash
uv python install 3.11
```

### 3) venv 環境構築（uv）

```bash
uv venv .venv
```

### 4) venv の有効化

Windows（PowerShell）
```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux（bash）
```bash
source .venv/bin/activate
```

### 5) 依存関係インストール

`pyproject.toml` ベース（推奨）:
```bash
uv sync
```

`requirements.txt` ベース:
```bash
uv pip install -r requirements.txt
```

Playwright のブラウザもインストール:
```bash
playwright install
```

## cardanoism起動手順

venv を有効化し、環境変数（DB_* など）を設定した状態で実行します。

```bash
uv run reflex run
```

開発モードを明示したい場合:
```bash
uv run reflex run --env dev
```

## MariaDB セットアップ

このアプリは起動時に次の環境変数を参照します。
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASS`

### 1) MariaDB のインストール

Windows（winget）
```powershell
winget install --id MariaDB.Server -e
```

macOS（Homebrew）
```bash
brew install mariadb
```

Linux（Ubuntu / Debian）
```bash
sudo apt-get update
sudo apt-get install mariadb-server
```

### 2) MariaDB の起動

Windows（サービス起動の例）
```powershell
net start MariaDB
```

macOS（Homebrew services）
```bash
brew services start mariadb
```

Linux（systemd）
```bash
sudo systemctl enable mariadb
sudo systemctl start mariadb
```

### 3) データベース／ユーザー作成（例）

```sql
CREATE DATABASE cardanoism CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'cardanoism'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON cardanoism.* TO 'cardanoism'@'localhost';
FLUSH PRIVILEGES;
```

### 4) 環境変数の設定（PowerShell例）

```powershell
$env:DB_HOST = "localhost"
$env:DB_PORT = "3306"
$env:DB_NAME = "cardanoism"
$env:DB_USER = "cardanoism"
$env:DB_PASS = "your_password"
```

### 5) マイグレーション適用

```bash
mariadb -u cardanoism -p cardanoism < migrations/funds_new.sql
mariadb -u cardanoism -p cardanoism < migrations/campaigns_new.sql
mariadb -u cardanoism -p cardanoism < migrations/proposals_new.sql
mariadb -u cardanoism -p cardanoism < migrations/proposal_detail_new.sql
```


## 4) カタリストデータ取得

以下は「Fundを指定して取り込む」前提の基本手順です。

### 1) Catalyst Explorer API インポート

Fund一覧:
```bash
uv run python cardanoism/backend/funds_update_new.py
```

Campaigns:
```bash
uv run python cardanoism/backend/campaigns_new.py
```

Proposals（Fund指定）:
```bash
uv run python cardanoism/backend/proposals_update_new.py --fund 14
```

### 2) Project Catalyst スクレイピング（Fund指定）

```bash
uv run python cardanoism/backend/proposal_scraping.py --fund 14
```

必要に応じて件数制限:
```bash
uv run python cardanoism/backend/proposal_scraping.py --fund 14 --limit 300
```

### 3) 翻訳（Fund指定、limit=300）

```bash
uv run python cardanoism/backend/translate_proposals_new.py --fund 14 --limit 300
```

### 4) 日次バッチ（例）

Linux（cron登録例）:

1) 実行権限を付与
```bash
chmod +x cardanoism/backend/daily_bat.sh
```

2) cronに登録（毎日03:00に実行）※パスは環境に合わせて変更してください
```bash
(crontab -l 2>/dev/null; echo "0 3 * * * cd /path/to/cardanoism && ./cardanoism/backend/daily_bat.sh >> /path/to/cardanoism/cron.log 2>&1") | crontab -
```
