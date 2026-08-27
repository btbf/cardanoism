# リアルタイム通知バックエンド 設定方法

Cardano チェーン上のイベント（エポック切替・プール証明書・ガバナンスアクション提出・DRep 投票）を **ブロック確定の瞬間** に検知して通知する常駐デーモンの本番セットアップ手順。

```
cardano-node ─IPC ── Ogmios ─WebSocket── ogmios_listener.py ── 通知送信
                                                  │
                                              MariaDB（カーソル / 重複防止）
```

`notify_worker.py`（Koios ポーリング）の送信関数（`flex_and_log` / `email_and_log` / `telegram_and_log`）をそのまま再利用する。新規送信ロジックは持たない。

> 新規 VPS への一括デプロイは [`initial-setup.md`](initial-setup.md) に全体手順をまとめている。本ドキュメントはリアルタイム通知個別の詳細。

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
sudo mkdir -p /home/btism/cardanoism_tmp
sudo chown cardanoism:cardanoism /home/btism/cardanoism_tmp
cd /home/btism/cardanoism_tmp
git clone <REPO_URL> .
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# `websockets>=12.0` が必要
```

### 5-2. シークレット管理 (Infisical)

`.env` ではなく **Infisical** で集中管理する。本番 (mainnet) / テストネット (preview) を environment スコープで分離。

必要な secret 一覧:

| 変数 | 必須 | 説明 |
|------|:---:|------|
| `OGMIOS_URL` | ✅ | Ogmios WebSocket URL（同居なら `ws://127.0.0.1:1337`） |
| `KOIOS_NETWORK` | ✅ | `mainnet` / `preprod` / `preview`（Ogmios `/health` から自動検出可） |
| `CARDANOISM_URL` | ✅ | サイト URL（通知メッセージ内のリンク用） |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASS` / `DB_NAME` | ✅ | MariaDB 接続情報 |
| `LINE_MESSAGING_TOKEN` | ⚠️ | LINE 通知を使う場合（Messaging API チャンネルアクセストークン） |
| `MAIL_SMTP_HOST` / `MAIL_SMTP_PORT` / `MAIL_SMTP_USER` / `MAIL_SMTP_PASSWORD` / `MAIL_FROM_NAME` | ⚠️ | メール通知を使う場合 |
| `TELEGRAM_BOT_TOKEN` | ⚠️ | Telegram 通知を使う場合 |
| `KOIOS_API_KEY` | 任意 | Koios の認証キー（DRep 投票時のタイトル補完・プール実績取得に使用） |
| `NOTIFICATION_REALTIME_MAX_LAG_SLOTS` | 任意 | 通常chainイベントの通知期限（既定: `1800` slots） |
| `NOTIFICATION_EPOCH_MAX_LAG_SLOTS` | 任意 | epoch境界通知の期限（既定: `7200` slots） |

VPS 側で Infisical CLIをインストールし、Infisical Agentとcron / systemd / tmux共通ラッパーを配置する:

```bash
# CLI インストール
curl -1sLf https://artifacts-cli.infisical.com/setup.deb.sh | sudo -E bash
sudo apt install -y infisical

# Agent / Universal Auth / project ID / environment の配置は deploy/README.md を参照
sudo -u btism /usr/local/bin/cardanoism-infisical env | grep DB_HOST
```

> 詳細な配置手順と権限設定は [`deploy/README.md`](../deploy/README.md) を参照。

### 5-3. 起動方法

```bash
cd /home/btism/cardanoism_tmp
/usr/local/bin/cardanoism-infisical \
    .venv/bin/python ogmios_listener.py

# 初回起動時のみ tip から再開
/usr/local/bin/cardanoism-infisical \
    .venv/bin/python ogmios_listener.py --from-tip
```

`--from-tip` は **初回起動時のみ** に使う。tip からカーソルを設定し、ジェネシスからの再生をスキップする。2回目以降は `notification_check_state` の `ogmios_last_slot` から自動再開するため不要。

### 5-4. systemd サービス

`/etc/systemd/system/ogmios-listener.service`:

```ini
[Unit]
Description=Cardanoism Ogmios Chain Listener
After=network-online.target infisical-agent.service
Wants=network-online.target infisical-agent.service

[Service]
Type=simple
User=btism
WorkingDirectory=/home/btism/cardanoism_tmp
# 共通ラッパーがInfisical Agentのtoken sinkを読み込む
ExecStart=/usr/local/bin/cardanoism-infisical /home/btism/cardanoism_tmp/.venv/bin/python ogmios_listener.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

> **Ogmios が同一ホストにある場合** は `[Unit]` に `After=network-online.target ogmios.service` /
> `Requires=ogmios.service` を加えると起動順を保証できる。**Ogmios を別サーバで動かす構成**
> (`OGMIOS_URL` がリモートを指す) では `ogmios.service` がこのホストに存在しないため、
> これらを書くと `Unit ogmios.service not found` で起動失敗する。上記例はリモート Ogmios
> 構成向け。`ogmios_listener.py` は WebSocket 接続失敗時に自動再接続するため、起動順を
> systemd で縛る必要はない。

> preview テストネット用の listener を別途立てるときは `--env=preview` に変更し、別 unit (`ogmios-listener-preview.service`) として登録する。

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

## 7. Catch-up 時の通知鮮度

listener が停止中のブロックへ追いつく場合も、GA・vote・certificate のDB同期は
最後まで行う。ただし古いイベント通知は送らない。

`nextBlock.result.tip.slot - block.slot` で遅延を判定し、既定では以下のwindowを使う。

| 対象 | 既定window | 環境変数 |
|---|---:|---|
| GA / DRep vote / SPO pending / pool retire / pool fee | 1,800 slots（30分） | `NOTIFICATION_REALTIME_MAX_LAG_SLOTS` |
| epoch_start / pool epoch performance / epoch sync trigger | 7,200 slots（2時間） | `NOTIFICATION_EPOCH_MAX_LAG_SLOTS` |

期限切れでも `governance_actions`、`proposal_votes`、pool等のデータ更新、GA metadata、
投票理由の取得は継続する。抑止されるのはユーザーへの通知と、古いepoch境界からの
重いsync triggerだけ。GA metadataや投票理由のバックグラウンド処理が長引いた場合も、
配送直前に残りwindowを再確認する。

たとえば現在epoch 651で、listenerがepoch 649のブロックから再開しても、649のGAは
DBへ登録されるが「新規GA」としては通知されない。

## 8. ネットワーク切替（preprod / preview）

Infisical で `mainnet` / `preview` environment を分けているので、systemd unit の `--env=` フラグだけ書き換えれば network 別の secret に切り替わる。`ogmios_listener.py` 自体は Ogmios `/health` の `network` フィールドから自動検出するため、コード側に変更は不要。

cardano-node / Ogmios 側はネットワークごとに別の config 一式が必要。preprod の場合は `environments/preprod/config.json` を使い、別 systemd ユニット (`cardano-node-preprod.service`) を立てる構成を推奨。

---

## 9. 運用コマンド

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

## 10. トラブルシューティング

| 症状 | 原因と対処 |
|------|----------|
| `ogmios-listener` が `Connection refused` | Ogmios が未起動。`systemctl status ogmios` を確認 |
| `findIntersection 失敗` | DB に保存されたカーソルとチェーンが乖離。`--from-tip` で再起動するか、`notification_check_state` の `ogmios_*` 行を削除 |
| `syncProgress` が 100 にならない | cardano-node の同期が未完了。`journalctl -u cardano-node` を確認、回線とディスク I/O をチェック |
| 同じ通知が繰り返される | `notification_log.dedup_key` が空または不一致。`ogmios_listener.py` の dedup_key 生成ロジックを確認 |
| 通知が来ない（ログには検知記録あり） | `notification_settings` / `stake_notification_settings` の `enabled = 0`、または `notification_channels` 未登録 |
| エポック切替時に重複通知 | `notification_check_state` の `current_epoch` 値が破損。手動で当該エポック番号に修正 |

---

## 11. notify_worker.py との関係

リアルタイムバックエンドが担当するイベントは notify_worker.py の cron からは **完全に除外** されている（`notify_worker.py` のヘッダーコメント参照）。両方を稼働させても重複は起きないが、Ogmios 側を必ず単一プロセスで運用すること（複数立てると同じブロックを重複処理する）。

Koios 必須のイベント（saturation / pledge / reward / reminder / drep_status_change）と、各キャッシュテーブルの sync 系は引き続き notify_worker.py が担当する。詳細は `docs/koios-polling-backend.md`。

---

## 12. 参考リンク

- [Ogmios 公式ドキュメント](https://ogmios.dev/)
- [Ogmios リリース](https://github.com/CardanoSolutions/ogmios/releases)
- [Ogmios chain sync プロトコル](https://ogmios.dev/mini-protocols/local-chain-sync/)
- [cardano-node リリース](https://github.com/IntersectMBO/cardano-node/releases)
- [Cardano 設定ファイル（environments）](https://book.play.dev.cardano.org/environments.html)
