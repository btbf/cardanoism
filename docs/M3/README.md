# Welcome to Cardanoism

This site is a Japanese governance portal for the Cardano blockchain.

## Setup steps

This project assumes environment setup with `uv`.

Prerequisites:
- PowerShell (Windows) or bash (macOS / Linux)
- MariaDB can run locally

### 1) Install uv

Windows (winget)
```powershell
winget install --id AstralSoftware.UV -e
```

macOS (Homebrew)
```bash
brew install uv
```

Linux
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify:
```bash
uv --version
```

### 2) Install Python (via uv)

Install Python 3.11 per `pyproject.toml`.

```bash
uv python install 3.11
```

### 3) Create venv (uv)

```bash
uv venv .venv
```

### 4) Activate venv

Windows (PowerShell)
```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux (bash)
```bash
source .venv/bin/activate
```

### 5) Install dependencies

From `requirements.txt`:
```bash
uv pip install -r requirements.txt
```

Also install Playwright browsers:
```bash
playwright install
```


## MariaDB setup

This app reads the following environment variables at startup.
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASS`

### 1) Install MariaDB

Windows (winget)
```powershell
winget install --id MariaDB.Server -e
```

macOS (Homebrew)
```bash
brew install mariadb
```

Linux (Ubuntu / Debian)
```bash
sudo apt-get update
sudo apt-get install mariadb-server
```

### 2) Start MariaDB

Windows (service example)
```powershell
net start MariaDB
```

macOS (Homebrew services)
```bash
brew services start mariadb
```

Linux (systemd)
```bash
sudo systemctl enable mariadb
sudo systemctl start mariadb
```

### 3) Create database / user (example)

```sql
CREATE DATABASE cardanoism CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'cardanoism'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON cardanoism.* TO 'cardanoism'@'localhost';
FLUSH PRIVILEGES;
```

### 4) Set environment variables (PowerShell example)

```powershell
$env:DB_HOST = "localhost"
$env:DB_PORT = "3306"
$env:DB_NAME = "cardanoism"
$env:DB_USER = "cardanoism"
$env:DB_PASS = "your_password"
```

### 5) Apply migrations

```bash
mariadb -u cardanoism -p cardanoism < migrations/funds_new.sql
mariadb -u cardanoism -p cardanoism < migrations/campaigns_new.sql
mariadb -u cardanoism -p cardanoism < migrations/proposals_new.sql
mariadb -u cardanoism -p cardanoism < migrations/proposal_detail_new.sql
```


## 4) Catalyst data import

The following steps assume importing by specifying a Fund.

### 1) Catalyst Explorer API import

Fund list:
```bash
uv run python cardanoism/backend/funds_update_new.py
```

Campaigns:
```bash
uv run python cardanoism/backend/campaigns_new.py
```

Proposals (by Fund):
```bash
uv run python cardanoism/backend/proposals_update_new.py --fund 14
```

### 2) Project Catalyst scraping (by Fund)

```bash
uv run python cardanoism/backend/proposal_scraping.py --fund 14
```

Limit count as needed:
```bash
uv run python cardanoism/backend/proposal_scraping.py --fund 14 --limit 300
```

### 3) Translation (by Fund, limit=300)

```bash
uv run python cardanoism/backend/translate_proposals_new.py --fund 14 --limit 300
```

### 4) Daily batch (example)

Linux (cron example):

1) Grant execute permission
```bash
chmod +x cardanoism/backend/daily_bat.sh
```

2) Register with cron (runs daily at 03:00). Adjust paths for your environment.
```bash
(crontab -l 2>/dev/null; echo "0 3 * * * cd /path/to/cardanoism && ./cardanoism/backend/daily_bat.sh >> /path/to/cardanoism/cron.log 2>&1") | crontab -
```

## 5) Run cardanoism

Run with venv activated and environment variables (DB_* etc.) set.

```bash
uv run reflex run
```

If you want to explicitly use dev mode:
```bash
uv run reflex run --env dev
```

### Status check
```
https://yourdomain.com/_health
```

## Nginx reverse proxy assumed (health check)

- Assumes Nginx reverse proxy forwards `/`, `/_event`, `/_next/webpack-hmr`, and `/_health` to the app.
- Upstream port is assumed to be `3000` or `8000` (choose based on your environment).
- Health check path: `/_health`.
