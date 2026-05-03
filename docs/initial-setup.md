# 初期セットアップガイド

新規 VPS / クリーン環境への一括デプロイ手順。3 つのバックエンド (Koios ポーリング / リアルタイム通知 / GA AI 分析) を 1 ホストで立ち上げる流れに沿ってまとめる。

各セクションは **必要最小限のコマンド + 詳細 docs へのリンク** で構成する。深掘りは個別 docs を参照。

```
┌─────────────────────────────────────────┐
│  Reflex (Web UI)                        │  ← infisical run -- reflex run
├─────────────────────────────────────────┤
│  ogmios_listener.py    (常駐 systemd)   │  ← リアルタイム通知
│  notify_worker.py      (cron / 定期)    │  ← Koios ポーリング
│  ga_ai_worker.py       (常駐 systemd)   │  ← GA AI 分析
├─────────────────────────────────────────┤
│  MariaDB / cardano-node + Ogmios        │
└─────────────────────────────────────────┘
```

---

## 0. 前提

| 項目 | 推奨 |
|------|------|
| OS | Ubuntu 22.04+ |
| Python | 3.11+ (`pyenv` 経由推奨) |
| MariaDB | 10.6+ |
| Infisical CLI | 0.43+ (シークレット注入) |
| cardano-node + Ogmios | リアルタイム通知を使う場合のみ。`docs/realtime-notification-backend.md` § 3-4 |

---

## 1. リポジトリ配置 + venv

```bash
sudo mkdir -p /opt/cardanoism
sudo chown <user>:<user> /opt/cardanoism
cd /opt/cardanoism
git clone <REPO_URL> .

python3 -m venv .venv
source .venv/bin/activate
```

---

## 2. 依存パッケージ

```bash
# 通常依存
pip install -r requirements.txt

# editable: ローカルの custom component (CIP-30 ウォレットコネクタ)
pip install -e cardanoism/custom_components/cardanoism_wallet
```

> `cardanoism-wallet` は `pyproject.toml` の `[tool.uv.sources]` で path 指定の editable パッケージ。`requirements.txt` には書けないので別途必要。

---

## 3. シークレット管理 (Infisical)

`.infisical.json` (workspaceId / defaultEnvironment) は repo にコミット済み。シークレット本体は Infisical Web UI で管理。

### 3-1. CLI インストール

```bash
curl -1sLf https://artifacts-cli.infisical.com/setup.deb.sh | sudo -E bash
sudo apt install -y infisical
infisical --version
```

### 3-2. Service Token (非対話認証)

VPS では Machine Identity から発行した Service Token をファイル経由で読み込む。詳細手順は `docs/realtime-notification-backend.md` § 5-2。

```bash
sudo install -m 0600 /dev/stdin /etc/cardanoism/infisical.token <<< "<TOKEN>"
sudo chown <user>:<user> /etc/cardanoism/infisical.token
```

### 3-3. environment スコープ

| environment | 用途 |
|---|---|
| `local` | ローカル開発 (Windows / Mac) |
| `mainnet` | 本番 VPS |
| `preview` | テストネット VPS |

注入確認:

```bash
infisical run --env=mainnet --token="$(cat /etc/cardanoism/infisical.token)" -- \
  bash -c 'echo "DB=$DB_HOST/$DB_NAME, KOIOS=$KOIOS_NETWORK"'
```

必須 secret 一覧は `docs/koios-polling-backend.md` § 3-3 / `docs/realtime-notification-backend.md` § 5-2。

---

## 4. DB スキーマセットアップ

`cardanoism/backend/migrations/` 配下の SQL を番号順に流す。すべて `CREATE TABLE IF NOT EXISTS` で冪等。

```bash
infisical run --env=mainnet --token="$(cat /etc/cardanoism/infisical.token)" -- bash -c '
for f in cardanoism/backend/migrations/*.sql; do
  echo "--- applying $f"
  mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$f"
done
'
```

詳細は `cardanoism/backend/migrations/README.md`。

---

## 5. 初回データ同期

順序が重要。GA 本体が無いと AI 分析の enqueue 対象が無く、NCL 計算も `protocol_params` が前提。

```bash
INF="infisical run --env=mainnet --token=$(cat /etc/cardanoism/infisical.token) --"
PY="/opt/cardanoism/.venv/bin/python"

# (1) GA 本体を governance_actions に取り込む (新規ぶんは AI 分析キューへ自動 enqueue)
$INF $PY cardanoism/backend/governance.py --no-translate

# (2) プロトコルパラメータ + CC メンバー
$INF $PY notify_worker.py --event params_sync

# (3) トレジャリー残高 + 履歴 + NCL
$INF $PY notify_worker.py --event treasury_sync

# (4) 法定通貨レート
$INF $PY notify_worker.py --event fiat_sync

# (5) DRep 一覧
$INF $PY notify_worker.py --event drep_sync

# (6) 投票履歴 + 集計
$INF $PY notify_worker.py --event vote_sync
$INF $PY notify_worker.py --event summary_sync

# (7) 投票理由メタ + OpenAI 翻訳
$INF $PY notify_worker.py --event vote_rationale_sync

# (8) SPO
$INF $PY notify_worker.py --event pool_sync
$INF $PY notify_worker.py --event pool_block_history_sync

# (9) 既存 GA を AI 分析キューに bulk enqueue (空 DB で全件処理する用)
$INF $PY notify_worker.py --event ga_ai_initial_sync

# (10) 憲法本文 + 翻訳
$INF $PY notify_worker.py --event constitution_sync
```

詳細: `docs/koios-polling-backend.md` § 5-4。

DB を再リセットする運用が発生したら同じ順序で叩き直す。

---

## 6. 定期 polling 設定 (cron)

`notify_worker.py` を cron で定期実行する。テンプレート全体は `docs/koios-polling-backend.md` § 4-1。

```bash
sudo install -m 0644 cron.d-cardanoism-notify /etc/cron.d/cardanoism-notify
sudo mkdir -p /var/log/cardanoism
sudo chown <user>:<user> /var/log/cardanoism
```

スケジュールの考え方は `docs/koios-polling-backend.md` § 4-2。

---

## 7. 通知用常駐サービス (systemd)

### 7-1. Ogmios listener (リアルタイム通知)

cardano-node + Ogmios が `syncProgress: 100.00` まで同期完了してから起動する。**初回起動は `--from-tip` 必須** (DB のカーソルが空な状態でジェネシスから再生するのを防ぐ)。

```bash
# 初回 (フォアグラウンドで動作確認)
infisical run --env=mainnet --token="$(cat /etc/cardanoism/infisical.token)" -- \
  /opt/cardanoism/.venv/bin/python ogmios_listener.py --from-tip
```

systemd unit 例は `docs/realtime-notification-backend.md` § 5-4。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ogmios-listener
journalctl -u ogmios-listener -f
```

### 7-2. GA AI worker

`governance_ai_analysis.status = 'pending'` を消化する常駐ワーカー。

```bash
# 初回 (フォアグラウンドで動作確認)
infisical run --env=mainnet --token="$(cat /etc/cardanoism/infisical.token)" -- \
  /opt/cardanoism/.venv/bin/python ga_ai_worker.py
```

systemd unit 例は `docs/ga-ai-analysis-backend.md` § 3-4。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ga-ai-worker
journalctl -u ga-ai-worker -f
```

### 7-3. Reflex (Web UI)

開発モード:

```bash
infisical run --env=mainnet --token="$(cat /etc/cardanoism/infisical.token)" -- reflex run
```

本番は `reflex export` + nginx + プロセスマネージャ (例: pm2 / systemd) で `.web/_static` を配信。詳細は Reflex 公式参照。

---

## 8. 動作確認

### 8-1. キャッシュテーブルの件数

```sql
SELECT 'governance_actions' AS t, COUNT(*) FROM governance_actions
UNION ALL SELECT 'proposal_voting_summary', COUNT(*) FROM proposal_voting_summary
UNION ALL SELECT 'proposal_votes',          COUNT(*) FROM proposal_votes
UNION ALL SELECT 'dreps',                   COUNT(*) FROM dreps
UNION ALL SELECT 'treasury_snapshot',       COUNT(*) FROM treasury_snapshot
UNION ALL SELECT 'ncl_active',              COUNT(*) FROM ncl_active
UNION ALL SELECT 'pools',                   COUNT(*) FROM pools
UNION ALL SELECT 'fiat_rate',               COUNT(*) FROM fiat_rate
UNION ALL SELECT 'governance_ai_analysis',  COUNT(*) FROM governance_ai_analysis;
```

### 8-2. Ogmios カーソル

```sql
SELECT key_name, last_value, checked_at
FROM notification_check_state
WHERE scope_type = 'global' AND key_name LIKE 'ogmios_%';
```

### 8-3. 通知ログ

```sql
SELECT event_type, channel, dedup_key, sent_at
FROM notification_log
ORDER BY sent_at DESC LIMIT 20;
```

### 8-4. systemd サービス

```bash
systemctl status ogmios-listener ga-ai-worker
journalctl -u ogmios-listener --since "10 min ago"
journalctl -u ga-ai-worker     --since "10 min ago"
```

---

## 9. ネットワーク切替 (mainnet ↔ preview)

`--env` フラグだけ切り替える。ただし mainnet と preview は **物理的に別 DB / 別 Ogmios** を使うべき (同居すると mainnet データを破壊する)。systemd unit を `*-preview.service` として複製し、`--env=preview` に書き換えて並行稼働させる構成が推奨。

DB を空にしてから初回データ同期 (§ 5) を流せば、preview ネットワークのデータが入る。

---

## 10. 関連ドキュメント

| 系統 | ドキュメント |
|------|------------|
| Koios ポーリング (notify_worker / cron / 同期) | [`koios-polling-backend.md`](koios-polling-backend.md) |
| リアルタイム通知 (cardano-node / Ogmios / listener) | [`realtime-notification-backend.md`](realtime-notification-backend.md) |
| GA AI 分析 (ga_ai_worker / OpenAI) | [`ga-ai-analysis-backend.md`](ga-ai-analysis-backend.md) |
| マイグレーション一覧 | [`../cardanoism/backend/migrations/README.md`](../cardanoism/backend/migrations/README.md) |
