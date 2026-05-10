# Koios API ポーリングバックエンド 設定方法

`notify_worker.py` の本番セットアップ手順。Cardano チェーンの **計算値・履歴値** を Koios API でポーリング取得し、通知発火やキャッシュテーブル同期を行う独立スクリプト。

```
              cron
               ↓
        notify_worker.py ── Koios API ── (HTTPS)
               │
               ├─ 通知発火（LINE / Email / Telegram）
               └─ キャッシュテーブル同期（DB UPSERT）
```

リアルタイムバックエンド（`docs/realtime-notification-backend.md`）と並行稼働する独立プロセス。

> **Phase 1〜5 (Ogmios listener DB 直書き) 適用後の運用**
>
> Ogmios listener が GA / 投票 / DRep cert / Pool cert / 委任 cert を即時 DB 反映し、
> エポック境界で各種 `*_sync` を自動発火するようになりました。
>
> このため `notify_worker.py` の各 `*_sync` cron は **listener が落ちている間のフォールバック**
> として低頻度 (24 時間に 1 回深夜) で動かす運用に変わります。詳細は § 4-1。

> 新規 VPS への一括デプロイは [`initial-setup.md`](initial-setup.md) に全体手順をまとめている。本ドキュメントは Koios ポーリング個別の詳細。

---

## 1. 担当イベント

### 1-1. 通知イベント

| イベント | スコープ | 説明 |
|---------|---------|------|
| `pool_saturation` | アドレス | プール飽和度の超過（`live_saturation` は計算値） |
| `pool_pledge_shortage` | アドレス | プール誓約不足（`live_pledge` は集計値） |
| `pool_reward_received` | アドレス | エポック報酬の入金（ledger state 計算値） |
| `pool_delegation_reminder` | アドレス | 長期委任リマインダー（90/120/365日） |
| `drep_delegation_reminder` | アドレス | 長期 DRep 委任リマインダー |
| `drep_status_change` | アドレス | DRep ステータス変化（activity 期間超過は ledger state 判定） |
| `treasury_withdrawal_enacted` | ユーザー | トレジャリー引き出し提案の Enacted 検知 |

### 1-2. キャッシュ同期イベント

ページの応答性向上のため、Koios のレスポンスを DB にキャッシュする。

| イベント | 対象テーブル | 内容 |
|---------|------------|------|
| `treasury_sync` | `treasury_snapshot` / `treasury_withdrawal` / `ncl_active` | トレジャリー残高・履歴・NCL |
| `fiat_sync` | `fiat_rate` | ADA/JPY、ADA/USD レート（CoinGecko） |
| `drep_sync` | `dreps` | DRep 一覧 + メタデータ |
| `vote_sync` | `proposal_votes` | 投票履歴 |
| `summary_sync` | `proposal_voting_summary` | 投票集計 |
| `params_sync` | `protocol_params` / `cc_members` | プロトコルパラメータ・憲法委員会 |
| `vote_rationale_sync` | `proposal_votes.rationale_ja` | OpenAI で投票理由を翻訳 |
| `pool_sync` | `pools` | SPO 一覧 + 拡張メタ |
| `pool_block_history_sync` | `pools_block_history` | プール別エポック作成ブロック数の履歴 |
| `relay_check` | `pools.relay_alive` | リレー疎通チェック |
| `constitution_sync` | `constitution_cache` | Cardano 憲法本文の取得 + 翻訳 |
| `ga_ai_initial_sync` | `governance_ai_analysis` (pending) | 既存 GA を AI 分析キューに一括投入 |

> リアルタイムバックエンド（Ogmios）が担当するイベント（`epoch_start` / `pool_retire` / `pool_fee_change` / `pool_epoch_performance` / `drep_new_governance_action` / `drep_vote`）は notify_worker.py からは送信されない。Ogmios デーモンが必須。

---

## 2. インフラ要件

| コンポーネント | 用途 |
|--------------|------|
| Linux ホスト | cron で定期実行 |
| Python 3.10+ | 実行環境 |
| MariaDB | キャッシュ・通知ログ（リアルタイム側と共通） |
| Koios API | 公開 API（無料、必要なら API key で rate limit 緩和） |
| CoinGecko API | 法定通貨レート（無料） |
| OpenAI API | 投票理由翻訳（任意、`vote_rationale_sync` のみ） |

---

## 3. セットアップ

### 3-1. リポジトリ配置

```bash
sudo mkdir -p /opt/cardanoism
sudo chown cardanoism:cardanoism /opt/cardanoism
cd /opt/cardanoism
git clone <REPO_URL> .
python3 -m venv .venv
infisical run --env=preview -- pip install -r requirements.txt
```

### 3-2. DB マイグレーション適用

```bash
for f in cardanoism/backend/migrations/*.sql; do
  echo "--- applying $f"
  mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$f"
done
```

詳細は `cardanoism/backend/migrations/README.md`。

### 3-3. シークレット管理 (Infisical)

`.env` ではなく **Infisical** で集中管理する。`mainnet` / `preview` environment ごとに secret を分離し、cron / systemd 起動時に CLI が `os.environ` に注入する。

必要な secret 一覧:

| 変数 | 必須 | 説明 |
|------|:---:|------|
| `KOIOS_NETWORK` | ✅ | `mainnet` / `preprod` / `preview` |
| `CARDANOISM_URL` | ✅ | サイト URL（通知メッセージ内のリンク） |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASS` / `DB_NAME` | ✅ | MariaDB 接続情報 |
| `KOIOS_API_KEY` | 任意 | Koios 認証キー（rate limit 緩和） |
| `LINE_MESSAGING_TOKEN` | ⚠️ | LINE 通知（Messaging API チャンネルアクセストークン） |
| `MAIL_SMTP_HOST` / `MAIL_SMTP_PORT` / `MAIL_SMTP_USER` / `MAIL_SMTP_PASSWORD` | ⚠️ | メール通知 |
| `MAIL_FROM_NAME` | 任意 | 送信者表示名（既定: `Cardanoism`） |
| `TELEGRAM_BOT_TOKEN` | ⚠️ | Telegram 通知 |
| `GPT_API_KEY` | 任意 | OpenAI API キー（投票理由翻訳 `vote_rationale_sync` で使用） |

⚠️ は通知チャンネルを使う場合のみ必須。最低 1 つは設定。

Infisical 認証は cron 実行ユーザー (`cardanoism`) で `infisical login` を一度実行しておく前提 (`~/.infisical/` に credentials が保存され、以降の `infisical run` がそれを読む)。cron 行に token を渡す必要はない。

---

## 4. cron 設定

cron 定義は [`deploy/cron.d-cardanoism-notify`](../deploy/cron.d-cardanoism-notify) 1 ファイルで完結する形式。VPS への install 手順は [`deploy/README.md`](../deploy/README.md) を参照。本セクションは設計意図と運用上の補足のみ。

### 4-1. cron file の構造

ファイル冒頭で 3 つの変数 (`ENV` / `WORKDIR` / `PY`) をデプロイ時に書き換え、各 cron 行は以下の素直な形:

```cron
*/30 * * * *  cardanoism cd $WORKDIR && infisical run --env=$ENV -- $PY notify_worker.py --event pool >> $LOG/notify-pool.log 2>&1
```

- 認証は `cardanoism` user の `~/.infisical/` 経由で自動解決 (cron file には token を含めない)
- ログはイベント別ファイル `notify-<event>.log` に分離 (logrotate と障害切り分けが楽)
- ファイル権限は通常の `0644 root:root` でよい (機密情報を含まないため)

> Ogmios listener が GA / 投票 / DRep cert / Pool cert / 委任 cert の各イベントを即時 DB 反映するため、従来の `*_sync` 系 cron は **listener 停止時のフォールバック** として 24 時間に 1 回だけ走らせる構成。

### 4-2. cron スケジュールの考え方

#### 常時 cron (listener 状態に関係なく走る)

| 種類 | 頻度 | 理由 |
|------|------|------|
| `drep` | 5 分 | drep_unvoted_ga (DB only) を高頻度で。drep_status_change の `/drep_info` も bulk 1 回で軽量 |
| `fiat_sync` | 5 分 | UI で常時表示されるため短め (CoinGecko 無料枠 30 req/min 内) |
| `pool` | 10 分 | saturation / pledge / reward 検知。エポック計算値なので cron 不可避 |
| `summary_sync` | **15 分** | **Active GA 限定**で投票集計を最新化。`pre_ratify` トリガー (drep_yes_pct ≥ 批准値 -10pt) のリアルタイム判定の前提 |
| `reminder` | 15 分 | 委任長期リマインダー + `refresh_stake_delegations` |
| `treasury` | 15 分 | enacted 検知。listener も拾えるが軽量な safety net |
| `relay_check` | 6 時間 | TCP 疎通テスト (オフチェーン) |
| `vote_rationale_sync` | 4 時間 | OpenAI 翻訳。コスト抑制のため低頻度 |

> `summary_sync` は元々全 GA 対象で重かったが、Active GA 限定 (通常 10–30 件) に絞って 15 min cron に格上げした。これにより `pre_ratify` トリガーが最大でも 15 分遅延に収まる。

#### フォールバック cron (24 時間に 1 回、深夜に集中)

通常は Ogmios listener が epoch_start を検知したときに `*_sync` チェーンを起動する。
listener が長時間停止していてもデータが完全停止しないよう、**1 日 1 回だけ深夜にバックアップ実行**する。
`summary_sync` は常時 15 min で回っているためフォールバックには含めない。

| 種類 | 起動時刻 | 通常駆動 |
|------|---------|---------|
| `governance.py --no-translate` | 03:00 | listener 経由で逐次反映 + epoch_start でステータス確定 |
| `params_sync` | 03:30 | listener: epoch_start |
| `treasury_sync` | 04:00 | listener: epoch_start |
| `drep_sync` | 04:30 | listener: epoch_start + DRep cert 検知 |
| `pool_sync` | 05:00 | listener: epoch_start + Pool cert 検知 |
| `pool_block_history_sync` | 05:30 | listener: epoch_start |
| `vote_sync` | 06:00 | listener: 投票即時反映 |
| `constitution_sync` | 07:00 | listener: epoch_start |

> **listener が動いている限り**、これらの cron 実行はほぼ「no-op (= 既に最新)」になる。
> Koios コール量は通常時とフォールバック時で大きく差がついて、平時は 1/10 程度に抑えられる。

### 4-3. listener の状態監視

Phase 1〜5 によりデータの新鮮度は **Ogmios listener が動いているか** に依存するようになりました。
fallback cron が 24 時間に 1 回しか走らないため、listener 停止を早期検知することが重要です。

#### journalctl で稼働確認

```bash
# 直近 5 分間でブロック処理ログが出ていれば正常
sudo journalctl -u cardanoism-ogmios-listener --since "5 minutes ago" | grep "ブロック受信"
```

#### DB 経由の鮮度チェック

```sql
-- listener が直近に書いた slot を見る (各テーブル)
SELECT 'governance_actions' AS tbl, MAX(last_event_slot) AS last_slot FROM governance_actions
UNION ALL
SELECT 'proposal_votes',                MAX(last_event_slot) FROM proposal_votes
UNION ALL
SELECT 'dreps',                         MAX(last_event_slot) FROM dreps
UNION ALL
SELECT 'pools',                         MAX(last_event_slot) FROM pools
UNION ALL
SELECT 'stake_addresses',               MAX(last_event_slot) FROM stake_addresses;
```

最新の slot が **数十分以上更新されていない** 場合、listener が詰まっている / 落ちている可能性が高い。

#### 推奨アラート

systemd の `OnFailure=` や外部監視 (Healthchecks.io / UptimeRobot 等) で:

- `cardanoism-ogmios-listener.service` の状態 `active (running)` を 5 分間隔で確認
- もしくは `cat /var/lib/cardanoism/ogmios.cursor` の `mtime` が 10 分以上古ければアラート

---

## 5. 運用コマンド

### 5-1. 全イベント手動実行

```bash
cd /opt/cardanoism
infisical run --env=preview -- python notify_worker.py
# = 全 --event を順次実行
```

### 5-2. 個別実行

```bash
# 通知だけ
infisical run --env=preview -- python notify_worker.py --event pool
infisical run --env=preview -- python notify_worker.py --event drep
infisical run --env=preview -- python notify_worker.py --event reminder

# 同期だけ
infisical run --env=preview -- python notify_worker.py --event drep_sync
infisical run --env=preview -- python notify_worker.py --event vote_sync
infisical run --env=preview -- python notify_worker.py --event summary_sync
infisical run --env=preview -- python notify_worker.py --event params_sync
infisical run --env=preview -- python notify_worker.py --event treasury_sync
infisical run --env=preview -- python notify_worker.py --event fiat_sync

# SPO 系
infisical run --env=preview -- python notify_worker.py --event pool_sync
infisical run --env=preview -- python notify_worker.py --event pool_block_history_sync
infisical run --env=preview -- python notify_worker.py --event relay_check
```

### 5-3. 初回投入 / DB リセット時の同期手順

新規環境にデプロイした直後、またはネットワーク切替（mainnet ↔ preview）でガバナンス系・SPO 系のキャッシュテーブルを TRUNCATE した直後に **1 回だけ** 実行する。順序が重要（GA 本体が無いと AI 分析の enqueue 対象が無いため）。

```bash
INF="infisical run --env=preview --"

# (1) GA 本体を governance_actions に取り込む
#     Koios /proposal_list を全件フェッチ → upsert → 新規 GA は AI 分析キューに自動 enqueue
$INF python cardanoism/backend/governance.py --no-translate
# 翻訳まで一気にやる場合は --no-translate を外す

# (2) プロトコルパラメータ + CC メンバー（NCL 計算の前提）
$INF python notify_worker.py --event params_sync

# (3) トレジャリー残高 + 履歴 + NCL
$INF python notify_worker.py --event treasury_sync

# (4) 法定通貨レート
$INF python notify_worker.py --event fiat_sync

# (5) DRep 一覧
$INF python notify_worker.py --event drep_sync

# (6) 投票履歴 + 集計
$INF python notify_worker.py --event vote_sync
$INF python notify_worker.py --event summary_sync

# (7) 投票理由メタ + 翻訳
$INF python notify_worker.py --event vote_rationale_sync

# (8) SPO
$INF python notify_worker.py --event pool_sync
$INF python notify_worker.py --event pool_block_history_sync

# (9) GA AI 分析の pending を bulk enqueue
#     (1) で新規ぶんは自動 enqueue 済み。空 DB から再投入する時のみ必要
$INF python notify_worker.py --event ga_ai_initial_sync

# (10) 憲法本文 + 翻訳
$INF python notify_worker.py --event constitution_sync
```

(9) の pending を消化する常駐ワーカーは別プロセス:

```bash
$INF python ga_ai_worker.py
```

DB リセット後の Ogmios listener は `--from-tip` 必須（`docs/realtime-notification-backend.md` 5-3）。

### 5-4. エポック切替時刻の確認

```bash
infisical run --env=preview -- python notify_worker.py --epoch-schedule
```

直近 10 エポックの切替時刻と推奨 cron 行を出力する。

> リアルタイムバックエンドが稼働している場合、`epoch_start` 通知は Ogmios 側が担当するため、ここで提示された cron 行は **登録不要**。

### 5-5. 投票理由翻訳の制限

```bash
# メタデータ取得は最大 100 件、OpenAI 翻訳は最大 30 件で実行（コスト抑制）
infisical run --env=preview -- python notify_worker.py --event vote_rationale_sync \
  --fetch-limit 100 --translate-limit 30
```

`0` を指定すると無制限。

---

## 6. ログとモニタリング

### 6-1. ログ

`/var/log/cardanoism/notify.log` と `sync.log` に出力。`logrotate` の設定例:

```
# /etc/logrotate.d/cardanoism
/var/log/cardanoism/*.log {
  daily
  rotate 14
  compress
  missingok
  notifempty
  create 0644 cardanoism cardanoism
}
```

### 6-2. 通知履歴

```sql
-- 直近 50 件の送信履歴
SELECT event_type, channel, dedup_key, sent_at
FROM notification_log
ORDER BY sent_at DESC LIMIT 50;

-- イベント別の日次集計
SELECT DATE(sent_at) AS d, event_type, channel, COUNT(*) AS n
FROM notification_log
WHERE sent_at > NOW() - INTERVAL 7 DAY
GROUP BY d, event_type, channel
ORDER BY d DESC, n DESC;
```

### 6-3. ステート確認

```sql
-- 各通知の前回値
SELECT scope_type, scope_id, key_name, last_value, checked_at
FROM notification_check_state
ORDER BY checked_at DESC LIMIT 50;
```

---

## 7. トラブルシューティング

| 症状 | 原因と対処 |
|------|----------|
| Koios `429 Too Many Requests` | rate limit。`KOIOS_API_KEY` を設定するか、cron 頻度を下げる |
| 通知が来ない | `notification_settings` / `stake_notification_settings` の `enabled = 0` を確認、`notification_channels` 登録の有無を確認 |
| 同じ通知が繰り返される | `notification_log` に該当 dedup_key の行があるか確認、`notification_check_state` の前回値を確認 |
| `vote_rationale_sync` が遅い／高額 | `--fetch-limit` / `--translate-limit` で制限。OpenAI コスト次第で間引く |
| `treasury_sync` で残高が更新されない | Koios 側の同期遅延。1〜2エポック分は遅延するのが正常 |
| ログが急増 | DB 上で `SELECT COUNT(*) FROM notification_channels WHERE channel_type='line'` を確認、`MAX_WORKERS = 10`（並列 Koios コール数）を絞ると軽減 |
| エポック開始通知が重複 | リアルタイムバックエンドが担当しているため、`notify_worker.py --event epoch_start` は cron に登録しない |

---

## 8. リアルタイムバックエンドとの責務分担

| イベント | リアルタイム（Ogmios） | Koios ポーリング |
|---------|:--------------------:|:---------------:|
| epoch_start | ✅ | — |
| pool_epoch_performance | ✅ | — |
| pool_retire | ✅ | — |
| pool_fee_change | ✅ | — |
| drep_new_governance_action | ✅ | — |
| drep_vote | ✅ | — |
| pool_saturation | — | ✅ |
| pool_pledge_shortage | — | ✅ |
| pool_reward_received | — | ✅ |
| pool/drep_delegation_reminder | — | ✅ |
| drep_status_change | — | ✅ |
| treasury_withdrawal_enacted | — | ✅ |
| 全 *_sync（キャッシュ） | — | ✅ |

リアルタイムバックエンドが停止しても Koios ポーリング側で多くは代替できるが、検知遅延が発生する（最大 cron 周期分）。本番運用は両系統 + 監視を強く推奨。

---

## 9. 参考リンク

- [Koios API ドキュメント](https://api.koios.rest/)
- [CoinGecko API](https://www.coingecko.com/api/documentation)
- [OpenAI API](https://platform.openai.com/docs/)
- [リアルタイム通知バックエンド設定](realtime-notification-backend.md)
