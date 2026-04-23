# リアルタイム通知設計書

## 概要

現在 Koios API のポーリングで実装している通知を、Dolos（軽量 Cardano データノード）+ UTxORPC Python SDK を使ったブロックストリームに移行する設計。

---

## アーキテクチャ

```
Dolos（軽量ノード, Mithril でブートストラップ）
    ↓ gRPC follow_tip（UTxORPC Sync module）
oura_listener.py（常駐デーモン）
    ├── 各ブロックの tx → cert / proposal / vote を解析
    ├── DB のステークアドレス・委任先と照合
    └── 該当ユーザーに通知（notify_worker.py の送信ロジックを直接呼び出し）
```

`notify_worker.py` の送信関数（`flex_and_log`、`email_and_log` 等）はそのまま再利用し、検知ロジックのみ置き換える。

---

## 全通知イベント分類

### Dolos（ブロックストリーム）で置き換え可能

| イベント | 検知方法 |
|---------|---------|
| `epoch_start` | ブロックの slot 番号からエポック変化を検知 |
| `pool_retire` | `PoolRetirementCert` |
| `pool_fee_change` | `PoolRegistrationCert`（再登録） |
| `drep_new_governance_action` | `ProposalProcedure` |
| `drep_vote` | `VotingProcedure` |

### Koios 必須（計算値・集計値）

| イベント | 理由 |
|---------|------|
| `pool_saturation` | `live_saturation` は「委任総量 ÷ 飽和閾値」の計算値。オンチェーンに存在しない |
| `pool_pledge_shortage` | `live_pledge` はオーナー残高の集計値。Koios が計算 |
| `pool_reward_received` | 報酬額は ledger state の計算値。tx として表現されない |
| `pool_delegation_reminder` | 過去の委任日時の初回取得に Koios が必要 |
| `drep_delegation_reminder` | 同上 |

### 部分的に Dolos 可能

| イベント | 状況 |
|---------|------|
| `drep_status_change` | `RegDRepCert` / `UnRegDRepCert`（登録・解除）は Dolos で検知可能。ただし activity 期間超過による自動 inactive 化は ledger state 判定のため Koios 必須 |

---

## 各イベントの実装仕様

### epoch_start

**現状（Koios）**
cron 毎日 21:44 → `/tip` の `epoch_slot` < window なら処理

**Dolos 実装**
ブロックストリームの各ブロックに `slot` が含まれる。`epoch_no = slot // 432000`（mainnet）を計算し、前ブロックの epoch_no と比較して変化したら発火。

```
受信ブロック → slot 番号から epoch_no 算出 → 前回 epoch_no と比較
→ 変化あり → check_epoch_start() の送信ロジックを呼ぶ
```

cron が不要になる。

---

### pool_retire

**現状（Koios）**
`/pool_info` → `retiring_epoch` をポーリング、値があれば通知

**Dolos 実装**
ブロック内 tx の `PoolRetirementCert` を検知。

Cert に含まれるもの:
- `operator`（pool key hash）
- `epoch`（引退エポック）

```
PoolRetirementCert 検知
    → operator（raw bytes）を bech32 変換 → pool1xxx
    → DB: SELECT users WHERE delegated_pool_id = pool1xxx
    → 対象ユーザーに通知
```

---

### pool_fee_change

**現状（Koios）**
`/pool_info` → `margin` / `fixed_cost` をポーリング、前回値と比較

**Dolos 実装**
ブロック内 tx の `PoolRegistrationCert`（再登録 = 手数料変更時に発生）を検知。

Cert に含まれるもの:
- `operator`（pool key hash）
- `cost`（固定費、lovelace）
- `margin`（分数 numerator / denominator）

```
PoolRegistrationCert 検知
    → pool1xxx に変換
    → notification_check_state から前回の fee 値を取得（pool 単位で管理）
    → 変化あり → DB: SELECT users WHERE delegated_pool_id = pool1xxx
    → 対象ユーザーに通知 + state 更新
```

現在は stake_address ごとに state を持つが、Dolos 版は **pool 単位**で持つ方が自然（同じプールに複数人が委任していても 1 回の Cert 検知で済む）。

---

### drep_new_governance_action

**現状（Koios）**
`/proposal_list` → 最新 `proposal_tx_hash` をポーリング、変化したら通知

**Dolos 実装**
ブロック内 tx の `ProposalProcedure` を検知。

Proposal に含まれるもの:
- `gov_action`（種別: ParameterChange / TreasuryWithdrawals / HardForkInitiation 等）
- `anchor`（URL / hash）
- `deposit`
- `reward_account`

```
ProposalProcedure 検知
    → gov_action の種別を取得
    → tx_hash を dedup_key に使用
    → DB: SELECT users WITH drep_new_governance_action enabled
    → 全対象ユーザーに通知
```

提案提出の瞬間（ブロック確定後）に通知。現在の 5 分ポーリングが不要。

---

### drep_vote

**現状（Koios）**
`/drep_votes` を委任 DRep ごとに並列ポーリング → 最新 tx_hash が変わったら通知

**Dolos 実装**
ブロック内 tx の `VotingProcedure` を検知。

VotingProcedure に含まれるもの:
- `voter`（DRep key hash）
- `gov_action_id`
- `vote`（YES / NO / ABSTAIN）

```
VotingProcedure 検知
    → voter が DRep 型かチェック
    → drep key hash を bech32 変換 → drep1xxx
    → DB: SELECT users WHERE delegated_drep_id = drep1xxx
    → 対象ユーザーに通知
    ※ proposal_title の取得は従来通り Koios（ハイブリッド）
```

---

## 共通の技術課題

### key hash → bech32 変換

Cert の operator は raw bytes。`bech32` Python ライブラリで変換する。

```python
import bech32

def keyhash_to_pool_id(raw_bytes: bytes) -> str:
    return bech32.encode("pool", bech32.convertbits(raw_bytes, 8, 5))

def keyhash_to_drep_id(raw_bytes: bytes) -> str:
    return bech32.encode("drep", bech32.convertbits(raw_bytes, 8, 5))
```

### ロールバック対応

Dolos の `follow_tip` は `apply` / `undo` / `reset` を返す。
**`undo` イベントは通知処理をスキップ**（通知は送り過ぎより送らない方がよい）。

確定ブロックのみ処理したい場合は Dolos 接続時に `RollbackBuffer min_depth=10` 相当の設定を行う。

### カーソル管理（再起動耐性）

- 最後に処理した slot を DB（`notification_check_state`）に保存
- 再起動時にそのスロットから `intersect` で再開

---

## Koios との役割分担（最終形）

| 処理 | Dolos | Koios |
|-----|:-----:|:-----:|
| `epoch_start` 検知 | ✅ | |
| `pool_retire` 検知 | ✅ | |
| `pool_fee_change` 検知 | ✅ | |
| `drep_new_governance_action` 検知 | ✅ | |
| `drep_vote` 検知 | ✅ | |
| `drep_vote` の proposal_title 取得 | | ✅ |
| `pool_saturation` | | ✅ |
| `pool_pledge_shortage` | | ✅ |
| `pool_reward_received` | | ✅ |
| `pool/drep_delegation_reminder` | | ✅ |
| `drep_status_change` | | ✅ |
| `refresh_stake_delegations` | | ✅ |
| `get_pool_apy` | | ✅ |

---

## 技術スタック

| 項目 | 内容 |
|-----|------|
| データノード | [Dolos](https://docs.txpipe.io/dolos)（TxPipe 製軽量ノード） |
| ブートストラップ | Mithril スナップショット |
| gRPC 仕様 | [UTxORPC](https://utxorpc.org)（Sync module） |
| Python SDK | `utxorpc`（`pip install utxorpc`） |
| bech32 変換 | `bech32` Python ライブラリ |
| ブロック解析基盤 | Pallas（Rust、Dolos の内部ライブラリ） |

---

## 参考リンク

- [Dolos ドキュメント](https://docs.txpipe.io/dolos)
- [UTxORPC 仕様](https://utxorpc.org)
- [UTxORPC Python SDK](https://github.com/utxorpc/python-sdk)
- [UTxORPC spec (proto)](https://github.com/utxorpc/spec)
- [Pallas](https://github.com/txpipe/pallas)
