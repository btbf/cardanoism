# リアルタイム通知バックエンド 設定方法

Cardano チェーン上のイベント（エポック切替・プール証明書・ガバナンスアクション提出・DRep 投票）を **ブロック確定の瞬間** に検知して通知する常駐デーモンの本番セットアップ手順。

```
cardano-node ─IPC ── Ogmios ─WebSocket── ogmios_listener.py ── 通知送信
                                                  │
                                              MariaDB（カーソル / 重複防止）
```

`notify_worker.py`（Koios ポーリング）の送信関数（`flex_and_log` / `email_and_log` / `telegram_and_log`）をそのまま再利用する。新規送信ロジックは持たない。

---

## 1. 担当イベント

リアルタイムバックエンドが担当するのはオンチェーン即時検知が可能なイベントのみ。計算値・集計値・履歴系は Koios ポーリングバックエンドが担当する（`docs/koios-polling-backend.md`）。

| イベント | トリガー（Ogmios） |
|---------|-------------------|
| `epoch_start` | block.slot からエポック番号変化を検知 |
| `pool_epoch_performance` | エポック切替と同時にプール実績を Koios で取得して通知 |
| `pool_retire` | `stakePoolRetirement` 証明書 |
| `pool_fee_change` | `stakePoolRegistration` 証明書（手数料・誓約変化） |
| `drep_new_governance_action` | `proposals` |
| `drep_vote` | `votes`（`voter.role == "delegateRepresentative"` のみ） |

---

## 2. インフラ要件

| コンポーネント | 役割 | 必要リソース目安（mainnet） |
|--------------|------|---------------------------|
| cardano-node | チェーン同期（フルノード） | RAM 24GB / SSD 350GB / 安定回線 |
| Ogmios | cardano-node ↔ WebSocket ブリッジ | 軽量（同居可） |
| ogmios_listener.py | イベント検知 + 通知発火 | 軽量（同居可） |
| MariaDB | カーソル・重複防止・通知ログ | 共通 DB |

mainnet 初回同期は **数日〜1週間**。同期完了（`syncProgress: "100.00"`）まで `ogmios_listener.py` は起動しない。

---

## 3. cardano-node セットアップ

### 3-1. バイナリ取得

```bash
# https://github.com/IntersectMBO/cardano-node/releases
wget https://github.com/IntersectMBO/cardano-node/releases/download/10.4.1/cardano-node-10.4.1-linux.tar.gz
tar -xzf cardano-node-10.4.1-linux.tar.gz
sudo mv cardano-node cardano-cli /usr/local/bin/
```

### 3-2. 設定ファイル取得

```bash
sudo mkdir -p /opt/cardano/{config,db,socket}
sudo chown -R cardanoism:cardanoism /opt/cardano

cd /opt/cardano/config
# mainnet の場合（preprod / preview は environments の URL を変更）
wget https://book.play.dev.cardano.org/environments/mainnet/config.json
wget https://book.play.dev.cardano.org/environments/mainnet/topology.json
wget https://book.play.dev.cardano.org/environments/mainnet/byron-genesis.json
wget https://book.play.dev.cardano.org/environments/mainnet/shelley-genesis.json
wget https://book.play.dev.cardano.org/environments/mainnet/alonzo-genesis.json
wget https://book.play.dev.cardano.org/environments/mainnet/conway-genesis.json
```

### 3-3. systemd サービス

`/etc/systemd/system/cardano-node.service`:

```ini
[Unit]
Description=Cardano Node
After=network.target

[Service]
Type=simple
User=cardanoism
ExecStart=/usr/local/bin/cardano-node run \
  --config        /opt/cardano/config/config.json \
  --topology      /opt/cardano/config/topology.json \
  --database-path /opt/cardano/db \
  --socket-path   /opt/cardano/socket/node.socket \
  --port          3001
Restart=always
RestartSec=10
LimitNOFILE=65535
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cardano-node
journalctl -u cardano-node -f
```

### 3-4. 同期確認

```bash
cardano-cli query tip --mainnet --socket-path /opt/cardano/socket/node.socket
# syncProgress が "100.00" になるまで待機
```

---

## 4. Ogmios セットアップ

### 4-1. バイナリ取得

```bash
# https://github.com/CardanoSolutions/ogmios/releases
wget https://github.com/CardanoSolutions/ogmios/releases/download/v6.14.0/ogmios-v6.14.0-x86_64-linux.zip
unzip ogmios-v6.14.0-x86_64-linux.zip
sudo mv bin/ogmios /usr/local/bin/
sudo chmod +x /usr/local/bin/ogmios
ogmios --version
```

### 4-2. systemd サービス

`/etc/systemd/system/ogmios.service`:

```ini
[Unit]
Description=Ogmios WebSocket Bridge
After=network.target cardano-node.service
Requires=cardano-node.service

[Service]
Type=simple
User=cardanoism
ExecStart=/usr/local/bin/ogmios \
  --node-socket /opt/cardano/socket/node.socket \
  --node-config /opt/cardano/config/config.json \
  --host 127.0.0.1 \
  --port 1337
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ogmios
```

### 4-3. ヘルスチェック

```bash
curl http://127.0.0.1:1337/health | jq .
# 出力例:
# {
#   "currentEpoch": 537,
#   "syncProgress": "100.00",
#   "networkSynchronization": "1.000",
#   "lastKnownTip": { "slot": ..., "id": ... }
# }
```

`syncProgress: "100.00"` を確認してから次のステップに進む。

### 4-4. ポート

| ポート | 用途 |
|--------|------|
| 3001 | cardano-node P2P（外部公開） |
| 1337 | Ogmios（**127.0.0.1 のみ。外部公開しない**） |

---

## 5. ogmios_listener.py セットアップ

### 5-1. リポジトリ配置

```bash
sudo mkdir -p /opt/cardanoism
sudo chown cardanoism:cardanoism /opt/cardanoism
cd /opt/cardanoism
git clone <REPO_URL> .
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# `websockets>=12.0` が必要
```

### 5-2. 環境変数（`/opt/cardanoism/.env`）

| 変数 | 必須 | 説明 |
|------|:---:|------|
| `OGMIOS_URL` | ✅ | Ogmios WebSocket URL（同居なら `ws://127.0.0.1:1337`） |
| `KOIOS_NETWORK` | ✅ | `mainnet` / `preprod` / `preview`（Ogmios `/health` から自動検出可） |
| `CARDANOISM_URL` | ✅ | サイト URL（通知メッセージ内のリンク用） |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASS` / `DB_NAME` | ✅ | MariaDB 接続情報 |
| `LINE_CHANNEL_ACCESS_TOKEN` | ⚠️ | LINE 通知を使う場合 |
| `MAIL_SMTP_HOST` / `MAIL_SMTP_PORT` / `MAIL_SMTP_USER` / `MAIL_SMTP_PASSWORD` / `MAIL_FROM_NAME` | ⚠️ | メール通知を使う場合 |
| `TELEGRAM_BOT_TOKEN` | ⚠️ | Telegram 通知を使う場合 |
| `KOIOS_API_KEY` | 任意 | Koios の認証キー（DRep 投票時のタイトル補完・プール実績取得に使用） |

### 5-3. 起動方法

```bash
cd /opt/cardanoism
.venv/bin/python ogmios_listener.py
# または引数指定
.venv/bin/python ogmios_listener.py --ogmios-url ws://127.0.0.1:1337

# 既存DBがありgenesisから再生したくない場合（推奨: 初回起動時）
.venv/bin/python ogmios_listener.py --from-tip
```

`--from-tip` は **初回起動時のみ** に使う。tip からカーソルを設定し、ジェネシスからの再生をスキップする。2回目以降は `notification_check_state` の `ogmios_last_slot` から自動再開するため不要。

### 5-4. systemd サービス

`/etc/systemd/system/ogmios-listener.service`:

```ini
[Unit]
Description=Cardanoism Ogmios Chain Listener
After=network.target ogmios.service
Requires=ogmios.service

[Service]
Type=simple
User=cardanoism
WorkingDirectory=/opt/cardanoism
EnvironmentFile=/opt/cardanoism/.env
ExecStart=/opt/cardanoism/.venv/bin/python ogmios_listener.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ogmios-listener
journalctl -u ogmios-listener -f
```

---

## 6. ロールバック対応

Ogmios `nextBlock` は `direction: "backward"` で網羅的にロールバックを通知する。本実装では:

- **通知はスキップ**（送り過ぎより送らない方を優先）
- カーソルを `point.slot` / `point.id` に巻き戻す
- `prev_epoch` も巻き戻し後のスロットから再計算

通常の mainnet 運用では rollback 深さは数ブロック程度。深い rollback が頻発する場合はネットワーク状況（ピアの接続性等）を確認する。

---

## 7. ネットワーク切替（preprod / preview）

`OGMIOS_URL` を切り替えれば `ogmios_listener.py` は `/health` の `network` フィールドから自動検出する。`KOIOS_NETWORK` 環境変数を明示する場合はそちらが優先される。

cardano-node / Ogmios 側はネットワークごとに別の config 一式が必要。preprod の場合は `environments/preprod/config.json` を使い、別 systemd ユニットを立てる構成を推奨。

---

## 8. 運用コマンド

### 状態確認

```bash
# サービス状態
systemctl status cardano-node ogmios ogmios-listener

# ログ追跡
journalctl -u ogmios-listener -f

# 最終処理スロット（DB）
mysql -e "SELECT key_name, last_value, checked_at
          FROM notification_check_state
          WHERE scope_type='global' AND key_name LIKE 'ogmios_%'"
```

### 通知履歴

```bash
mysql -e "SELECT event_type, channel, dedup_key, sent_at
          FROM notification_log
          ORDER BY sent_at DESC LIMIT 50"
```

### カーソル巻き戻し（深いロールバック復旧時など）

```sql
-- ogmios_last_slot を削除すると次回起動で genesis から再開する
DELETE FROM notification_check_state
WHERE scope_type='global' AND key_name IN ('ogmios_last_slot', 'ogmios_last_id');
```

または `--from-tip` で起動して tip から再開する。

---

## 9. トラブルシューティング

| 症状 | 原因と対処 |
|------|----------|
| `ogmios-listener` が `Connection refused` | Ogmios が未起動。`systemctl status ogmios` を確認 |
| `findIntersection 失敗` | DB に保存されたカーソルとチェーンが乖離。`--from-tip` で再起動するか、`notification_check_state` の `ogmios_*` 行を削除 |
| `syncProgress` が 100 にならない | cardano-node の同期が未完了。`journalctl -u cardano-node` を確認、回線とディスク I/O をチェック |
| 同じ通知が繰り返される | `notification_log.dedup_key` が空または不一致。`ogmios_listener.py` の dedup_key 生成ロジックを確認 |
| 通知が来ない（ログには検知記録あり） | `notification_settings` / `stake_notification_settings` の `enabled = 0`、または `notification_channels` 未登録 |
| エポック切替時に重複通知 | `notification_check_state` の `current_epoch` 値が破損。手動で当該エポック番号に修正 |

---

## 10. notify_worker.py との関係

リアルタイムバックエンドが担当するイベントは notify_worker.py の cron からは **完全に除外** されている（`notify_worker.py` のヘッダーコメント参照）。両方を稼働させても重複は起きないが、Ogmios 側を必ず単一プロセスで運用すること（複数立てると同じブロックを重複処理する）。

Koios 必須のイベント（saturation / pledge / reward / reminder / drep_status_change）と、各キャッシュテーブルの sync 系は引き続き notify_worker.py が担当する。詳細は `docs/koios-polling-backend.md`。

---

## 11. 参考リンク

- [Ogmios 公式ドキュメント](https://ogmios.dev/)
- [Ogmios リリース](https://github.com/CardanoSolutions/ogmios/releases)
- [Ogmios chain sync プロトコル](https://ogmios.dev/mini-protocols/local-chain-sync/)
- [cardano-node リリース](https://github.com/IntersectMBO/cardano-node/releases)
- [Cardano 設定ファイル（environments）](https://book.play.dev.cardano.org/environments.html)
