# Ogmios リアルタイム通知設計書

## 概要

Ogmios の WebSocket chain sync（`nextBlock`）を使い、Cardano ブロックが確定した瞬間に
cert / proposal / vote を解析して通知を発火する常駐デーモンの設計。

既存の `notify_worker.py`（Koios ポーリング）と **並行稼働**し、
Ogmios 側が担当するイベントは notify_worker.py の cron から除外していく移行戦略をとる。

---

## アーキテクチャ

```
cardano-node ── IPC socket ── Ogmios (port 1337)
                                   │ WebSocket JSON/RPC
                              ogmios_listener.py（常駐デーモン）
                                   ├── block.slot → epoch 変化 → epoch_start
                                   ├── certificates
                                   │     ├── stakePoolRetirement  → pool_retire
                                   │     └── stakePoolRegistration → pool_fee_change
                                   ├── proposals
                                   │     └── GovernanceAction → drep_new_governance_action
                                   └── votes
                                         └── delegateRepresentative vote → drep_vote
                                              │ (proposal_title のみ Koios で補完)
                                   │
                              notify_worker.py の送信ロジックを直接呼び出し
                              （flex_and_log / email_and_log）
```

### 役割分担（最終形）

| イベント | Ogmios（本設計） | Koios（継続） |
|---------|:--------------:|:------------:|
| `epoch_start` | ✅ slot からエポック変化を検知 | 廃止 |
| `pool_retire` | ✅ `stakePoolRetirement` cert | 廃止 |
| `pool_fee_change` | ✅ `stakePoolRegistration` cert | 廃止 |
| `drep_new_governance_action` | ✅ `proposals` | 廃止 |
| `drep_vote` | ✅ `votes` (DRep role) | 廃止 |
| `pool_saturation` | — | ✅ `live_saturation` は計算値 |
| `pool_pledge_shortage` | — | ✅ `live_pledge` は集計値 |
| `pool_reward_received` | — | ✅ ledger state の計算値 |
| `pool/drep_delegation_reminder` | — | ✅ 過去日時の初回取得 |
| `drep_status_change` | — | ✅ activity 期間超過は ledger state |

---

## インフラ要件

### 必要コンポーネント

| コンポーネント | 用途 |
|--------------|------|
| cardano-node | Cardano チェーンの同期（フルノード） |
| Ogmios | cardano-node と WebSocket をブリッジ |
| ogmios_listener.py | 本設計の常駐デーモン |

### バイナリセットアップ

cardano-node と Ogmios をそれぞれバイナリで導入する。

#### 1. cardano-node のインストール

[cardano-node GitHub Releases](https://github.com/IntersectMBO/cardano-node/releases) から最新バイナリをダウンロードする。

```bash
# バイナリをダウンロード・展開（バージョンは適宜変更）
wget https://github.com/IntersectMBO/cardano-node/releases/download/10.4.1/cardano-node-10.4.1-linux.tar.gz
tar -xzf cardano-node-10.4.1-linux.tar.gz
sudo mv cardano-node cardano-cli /usr/local/bin/

# 設定ファイルを取得（mainnet の場合）
mkdir -p /opt/cardano/config
cd /opt/cardano/config
wget https://book.play.dev.cardano.org/environments/mainnet/config.json
wget https://book.play.dev.cardano.org/environments/mainnet/topology.json
wget https://book.play.dev.cardano.org/environments/mainnet/byron-genesis.json
wget https://book.play.dev.cardano.org/environments/mainnet/shelley-genesis.json
wget https://book.play.dev.cardano.org/environments/mainnet/alonzo-genesis.json
wget https://book.play.dev.cardano.org/environments/mainnet/conway-genesis.json
```

cardano-node を起動する。

```bash
mkdir -p /opt/cardano/db /opt/cardano/socket

cardano-node run \
  --config        /opt/cardano/config/config.json \
  --topology      /opt/cardano/config/topology.json \
  --database-path /opt/cardano/db \
  --socket-path   /opt/cardano/socket/node.socket \
  --port          3001
```

#### 2. Ogmios のインストール

[Ogmios GitHub Releases](https://github.com/CardanoSolutions/ogmios/releases) から最新バイナリをダウンロードする。

```bash
# バイナリをダウンロード・展開（バージョンは適宜変更）
wget https://github.com/CardanoSolutions/ogmios/releases/download/v6.14.0/ogmios-v6.14.0-x86_64-linux.zip
unzip ogmios-v6.14.0-x86_64-linux.zip
sudo mv bin/ogmios /usr/local/bin/
chmod +x /usr/local/bin/ogmios

# バージョン確認
ogmios --version
```

Ogmios を起動する（cardano-node のソケットと設定ファイルを指定）。

```bash
ogmios \
  --node-socket /opt/cardano/socket/node.socket \
  --node-config /opt/cardano/config/config.json \
  --host 127.0.0.1 \
  --port 1337
```

| ポート | 用途 |
|--------|------|
| 1337 | Ogmios WebSocket / HTTP |
| 3001 | cardano-node P2P |

ネットワーク切り替え（preprod / preview）は設定ファイルのパスを変更するだけでよい。

```bash
# preprod の場合
ogmios \
  --node-socket /opt/cardano/socket/node.socket \
  --node-config /opt/cardano/config/preprod/config.json \
  --port 1337
```

#### 3. systemd サービス登録

**cardano-node:**

```ini
# /etc/systemd/system/cardano-node.service
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
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Ogmios:**

```ini
# /etc/systemd/system/ogmios.service
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
systemctl daemon-reload
systemctl enable cardano-node ogmios
systemctl start cardano-node
# ノード起動後（ソケットが生成されてから）Ogmios を起動
systemctl start ogmios
```

#### 4. 同期状態の確認

```bash
# cardano-node の同期進捗を確認
cardano-cli query tip --mainnet

# Ogmios ヘルスエンドポイント（HTTP）
curl http://127.0.0.1:1337/health | jq .

# 出力例: syncProgress が 100.00 になれば同期完了
# {
#   "currentEpoch": 537,
#   "syncProgress": "100.00",
#   ...
# }
```

### 初期同期について

mainnet の初回同期は **数日〜1週間** かかる。
同期完了（`syncProgress: "100.00"`）まで `ogmios_listener.py` は起動しなくてよい。

---

## Ogmios WebSocket プロトコル

### 接続と findIntersection

```python
import websockets
import json

WS_URL = "ws://localhost:1337"

async with websockets.connect(WS_URL) as ws:
    # 前回の続きから再開（カーソルがある場合）
    await ws.send(json.dumps({
        "jsonrpc": "2.0",
        "method": "findIntersection",
        "params": {
            "points": [
                {"slot": 139823921, "id": "abc123..."},
                "origin"   # フォールバック
            ]
        }
    }))
    await ws.recv()  # findIntersection レスポンスを消費

    # ブロックをストリーミング
    while True:
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "nextBlock"}))
        response = json.loads(await ws.recv())
        process_response(response)
```

### レスポンス構造

#### rollForward（新しいブロック）

```json
{
  "jsonrpc": "2.0",
  "method": "nextBlock",
  "result": {
    "direction": "forward",
    "block": {
      "type": "praos",
      "era": "conway",
      "slot": 139823921,
      "id": "abc123...",
      "height": 10500000,
      "transactions": [
        {
          "id": "tx_hash...",
          "certificates": [...],
          "proposals": [...],
          "votes": [...]
        }
      ]
    },
    "tip": {
      "slot": 139823921,
      "id": "abc123...",
      "height": 10500000
    }
  }
}
```

#### rollBackward（ロールバック）

```json
{
  "result": {
    "direction": "backward",
    "point": {"slot": 139823000, "id": "xxx..."},
    "tip": {...}
  }
}
```

---

## 検知対象フィールドの JSON 構造

### certificates: stakePoolRetirement

```json
{
  "type": "stakePoolRetirement",
  "stakePool": {
    "id": "pool1uezllnjtqj99yyu9p8h5cn7uce9f2xkazs4zy4s0mzs8wpnahah",
    "retirementEpoch": 6
  }
}
```

→ `stakePool.id`（bech32、pool1xxx）と `retirementEpoch` を使って `pool_retire` 通知を発火。

### certificates: stakePoolRegistration

```json
{
  "type": "stakePoolRegistration",
  "stakePool": {
    "id": "pool184ccf4skzd0lwhxv5yx87rfjexw2sc6umuzatl0qmc7ds24g9ve",
    "cost": {"ada": {"lovelace": 274001}},
    "margin": "1341749/4000000",
    "pledge": {"ada": {"lovelace": 430827}},
    "rewardAccount": "stake_test1u...",
    "owners": [...],
    "relays": [...],
    "metadata": {"url": "...", "hash": "..."}
  }
}
```

→ `stakePool.id`・`cost`・`margin`（分数文字列）を使って `pool_fee_change` を発火。  
→ `margin` は `"numerator/denominator"` 形式。`eval("1341749/4000000")` または `Fraction` で変換する。

### proposals（ガバナンスアクション提出）

```json
{
  "action": {
    "type": "treasuryWithdrawals",
    "withdrawals": {...},
    "guardrails": null
  },
  "returnAddress": "stake1...",
  "deposit": {"ada": {"lovelace": 100000000}}
}
```

`action.type` の種別一覧:

| type | 日本語表示 |
|------|-----------|
| `treasuryWithdrawals` | 国庫引き出し |
| `parameterChange` | プロトコル変更 |
| `hardForkInitiation` | ハードフォーク |
| `noConfidence` | 不信任 |
| `updateCommittee` | 委員会変更 |
| `newConstitution` | 新憲法 |
| `information` | 情報提案 |

→ tx の `id`（hash）を `dedup_key` として使い `drep_new_governance_action` を発火。

### votes（DRep 投票）

```json
{
  "voter": {
    "role": "delegateRepresentative",
    "id": "drep1xxx..."
  },
  "actionId": {
    "transaction": {"id": "proposal_tx_hash..."},
    "index": 1
  },
  "vote": "no"
}
```

`voter.role` の種別:

| role | 説明 |
|------|------|
| `delegateRepresentative` | DRep（本設計で対象） |
| `stakePoolOperator` | SPO |
| `constitutionalCommittee` | 憲法委員会 |

→ `voter.role == "delegateRepresentative"` のみ処理。  
→ `voter.id`（drep1xxx）で DB の `delegated_drep_id` と照合。  
→ `actionId.transaction.id` + `actionId.index` で Koios の `get_proposal_title()` を呼んでタイトル補完。  
→ `dedup_key = f"drep_vote_{stake_id}_{actionId.transaction.id}_{actionId.index}"`

---

## 実装: ogmios_listener.py

### ファイル配置

```
cardanoism/
├── notify_worker.py        # 既存（Koios ポーリング）
├── ogmios_listener.py      # 本設計（新規）
└── cardanoism/backend/
    ├── db_connect.py
    ├── line_notify.py
    ├── mail_notify.py
    └── line_flex.py
```

### 依存パッケージ

```
# requirements.txt に追記
websockets>=12.0
```

（`bech32`・`utxorpc` は不要。bech32 変換は Ogmios が処理済み文字列で返す）

### 起動方法

```bash
# 環境変数
export OGMIOS_URL=ws://localhost:1337
export KOIOS_NETWORK=mainnet
export CARDANOISM_URL=https://cardanoism.app

python ogmios_listener.py
# または
python ogmios_listener.py --ogmios-url ws://localhost:1337
```

### メインループ設計

```python
async def _run(ogmios_url: str) -> None:
    async with websockets.connect(ogmios_url, ping_interval=30) as ws:
        # カーソル（前回の続き）で findIntersection
        await _find_intersection(ws)

        prev_epoch = _load_prev_epoch()

        while True:
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "nextBlock"}))
            data = json.loads(await ws.recv())
            result = data.get("result", {})

            if result.get("direction") == "forward":
                block = result["block"]
                prev_epoch = _process_block(block, prev_epoch)

            elif result.get("direction") == "backward":
                # ロールバック: 通知スキップ、カーソルを巻き戻す
                point = result.get("point", {})
                logger.info("rollback: slot=%s", point.get("slot"))
                _save_cursor(point.get("slot"), point.get("id", ""))
```

### カーソル管理

`notification_check_state` テーブルを使って最終処理スロットを保存する。

```python
# 保存
set_state("global", None, "ogmios_last_slot", str(slot))
set_state("global", None, "ogmios_last_id",   block_id)

# 読み出し（findIntersection に渡す intersect points）
def _load_cursor() -> list[dict]:
    slot = get_state("global", None, "ogmios_last_slot")
    bid  = get_state("global", None, "ogmios_last_id")
    if slot and bid:
        return [{"slot": int(slot), "id": bid}]
    return ["origin"]
```

### 各イベントの処理フロー

#### epoch_start

```python
def _check_epoch(block: dict, prev_epoch: int) -> int:
    slot = block["slot"]
    EPOCH_LEN = {"mainnet": 432_000, "preprod": 432_000, "preview": 86_400}
    current_epoch = slot // EPOCH_LEN.get(NETWORK, 432_000)

    if prev_epoch >= 0 and current_epoch != prev_epoch:
        last = get_state("global", None, "current_epoch")
        if last != str(current_epoch):
            set_state("global", None, "current_epoch", str(current_epoch))
            if last is not None:
                _notify_epoch_start(current_epoch)

    return current_epoch
```

#### pool_retire

```python
def _handle_cert(cert: dict) -> None:
    if cert["type"] == "stakePoolRetirement":
        pool_id        = cert["stakePool"]["id"]          # pool1xxx
        retiring_epoch = cert["stakePool"]["retirementEpoch"]
        _notify_pool_retire(pool_id, retiring_epoch)
```

#### pool_fee_change

```python
    elif cert["type"] == "stakePoolRegistration":
        pool_id  = cert["stakePool"]["id"]
        cost_ada = cert["stakePool"]["cost"]["ada"]["lovelace"]  # lovelace
        # margin: "1341749/4000000" → float
        num, den = cert["stakePool"]["margin"].split("/")
        margin   = int(num) / int(den)
        _notify_pool_fee_change(pool_id, margin, cost_ada)
```

`pool_fee_change` の state 管理は pool 単位（`key_name = f"pool_fee:{pool_id}"`）で保存する。

#### drep_new_governance_action

```python
def _handle_proposal(tx_id: str, proposal: dict) -> None:
    action_type = proposal.get("action", {}).get("type", "")
    _TYPE_MAP = {
        "treasuryWithdrawals": "国庫引き出し",
        "parameterChange":     "プロトコル変更",
        "hardForkInitiation":  "ハードフォーク",
        "noConfidence":        "不信任",
        "updateCommittee":     "委員会変更",
        "newConstitution":     "新憲法",
        "information":         "情報提案",
    }
    label = _TYPE_MAP.get(action_type, action_type)
    _notify_governance_action(tx_id, label)
```

#### drep_vote

```python
def _handle_vote(vote: dict, tx_id: str) -> None:
    voter = vote.get("voter", {})
    if voter.get("role") != "delegateRepresentative":
        return  # SPO・委員会は対象外

    drep_id     = voter["id"]                            # drep1xxx
    vote_str    = vote["vote"]                           # "yes" | "no" | "abstain"
    action_id   = vote.get("actionId", {})
    gov_tx_hash = action_id.get("transaction", {}).get("id", "")
    gov_index   = action_id.get("index", 0)

    _notify_drep_vote(drep_id, vote_str, gov_tx_hash, gov_index)
```

---

## 既存 notify_worker.py との統合

`ogmios_listener.py` は `notify_worker.py` の送信関数を直接 import して使う。
新たな送信ロジックは書かない。

```python
from notify_worker import (
    get_state, set_state,
    already_sent, flex_and_log, email_and_log,
    get_users_with_event, get_users_with_email_event,
    get_stake_addrs_with_event, get_stake_addrs_with_email_event,
    _merge_stake_channels,
    CARDANOISM_URL,
)
from cardanoism.backend import line_flex
from cardanoism.backend.mail_notify import build_html, build_text
from cardanoism.backend.koios import get_proposal_title  # drep_vote のタイトル補完
```

---

## ロールバック対応

Cardano では ネットワーク分岐によりロールバックが発生する。
`direction: "backward"` の場合:

- **通知はスキップ**（送り過ぎより送らない方がよい）
- カーソルを `point.slot` / `point.id` に巻き戻す
- 前回エポック値 (`prev_epoch`) も対応スロットの値に戻す

```python
elif result.get("direction") == "backward":
    point = result.get("point", {})
    slot  = point.get("slot", 0)
    bid   = point.get("id", "")
    logger.info("rollback: slot=%s", slot)
    _save_cursor(slot, bid)
    prev_epoch = _epoch_from_slot(slot) if slot else prev_epoch
```

---

## notify_worker.py との cron 移行計画

Ogmios デーモン安定稼働確認後、以下の順で cron から削除する。

| フェーズ | 対象 | 内容 |
|---------|------|------|
| 1 | `epoch_start` | cron `44 21 * * *` を削除 |
| 2 | `pool_retire` / `pool_fee_change` | `notify_worker.py --event pool` で対象から除外 |
| 3 | `drep_new_governance_action` / `drep_vote` | `notify_worker.py --event drep` で対象から除外 |

Koios で引き続き担当するイベント（`pool_saturation`・`pool_pledge_shortage`・`pool_reward_received`・`reminder`・`drep_status_change`）は cron を維持する。

---

## systemd サービス設定（ogmios_listener.py）

cardano-node・Ogmios のサービスはバイナリセットアップ手順に記載済み。
ここでは `ogmios_listener.py` のサービスのみ示す。

```ini
# /etc/systemd/system/ogmios-listener.service
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
systemctl daemon-reload
systemctl enable ogmios-listener
systemctl start ogmios-listener
journalctl -u ogmios-listener -f
```

---

## 環境変数

| 変数 | 説明 | デフォルト |
|------|------|----------|
| `OGMIOS_URL` | Ogmios WebSocket URL | `ws://localhost:1337` |
| `KOIOS_NETWORK` | ネットワーク（mainnet / preprod / preview） | `mainnet` |
| `CARDANOISM_URL` | サイト URL（通知リンク） | `https://cardanoism.app` |
| 既存の DB・LINE・MAIL 変数 | `notify_worker.py` と共通 | — |

---

## 参考リンク

- [Ogmios 公式ドキュメント](https://ogmios.dev/)
- [Ogmios バイナリリリース](https://github.com/CardanoSolutions/ogmios/releases)
- [Ogmios chain sync プロトコル](https://ogmios.dev/mini-protocols/local-chain-sync/)
- [Ogmios API リファレンス v6.14](https://ogmios.dev/api/)
- [GitHub: CardanoSolutions/ogmios](https://github.com/CardanoSolutions/ogmios)
- [cardano-node リリース](https://github.com/IntersectMBO/cardano-node/releases)
- [Cardano 設定ファイル（environments）](https://book.play.dev.cardano.org/environments.html)
