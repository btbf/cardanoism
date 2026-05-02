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
.venv/bin/pip install -r requirements.txt
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

VPS への CLI / Service Token セットアップは `docs/realtime-notification-backend.md` 5-2 と共通。cron では `infisical run --env=mainnet --token="$(cat /etc/cardanoism/infisical.token)" -- python notify_worker.py ...` の形でラップする。

---

## 4. cron 設定

### 4-1. 推奨スケジュール

```cron
# /etc/cron.d/cardanoism-notify
SHELL=/bin/bash
WORKDIR=/opt/cardanoism
PY=/opt/cardanoism/.venv/bin/python
INF=/usr/local/bin/infisical
TOKEN_FILE=/etc/cardanoism/infisical.token
# Infisical の env スコープを切り替えるなら ENV=preview に変更
ENV=mainnet
RUN="$INF run --env=$ENV --token=$(cat $TOKEN_FILE) --"

# ── 通知 ─────────────────────────────────────────────
# プール系（saturation / pledge / reward）
*/30 * * * *  cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event pool         >> /var/log/cardanoism/notify.log 2>&1

# DRep 系（status_change）
*/30 * * * *  cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event drep         >> /var/log/cardanoism/notify.log 2>&1

# 委任リマインダー（pool / drep）
0    * * * *  cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event reminder     >> /var/log/cardanoism/notify.log 2>&1

# トレジャリー引き出し提案の enacted 検知
0    * * * *  cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event treasury     >> /var/log/cardanoism/notify.log 2>&1

# ── キャッシュ同期 ───────────────────────────────────
# トレジャリー残高・履歴・NCL
*/15 * * * *  cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event treasury_sync >> /var/log/cardanoism/sync.log 2>&1

# 法定通貨レート（CoinGecko）
*/10 * * * *  cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event fiat_sync     >> /var/log/cardanoism/sync.log 2>&1

# DRep 一覧・メタデータ
0    */2 * * * cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event drep_sync    >> /var/log/cardanoism/sync.log 2>&1

# 投票履歴（GA 詳細用）
*/30 * * * *  cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event vote_sync     >> /var/log/cardanoism/sync.log 2>&1

# 投票集計
*/30 * * * *  cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event summary_sync  >> /var/log/cardanoism/sync.log 2>&1

# プロトコルパラメータ・CC メンバー
0    */6 * * * cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event params_sync  >> /var/log/cardanoism/sync.log 2>&1

# 投票理由の翻訳（OpenAI、無料枠の上限注意）
0    */4 * * * cardanoism cd $WORKDIR && $RUN $PY notify_worker.py --event vote_rationale_sync >> /var/log/cardanoism/sync.log 2>&1
```

cron は `$()` を直接展開できないため、`$RUN` 変数を組み立てる際に `$(cat ...)` を頭に出している点に注意。動かない場合は `--token-file=$TOKEN_FILE` 指定に切替えるか、wrapper script を用意する。

```bash
sudo mkdir -p /var/log/cardanoism
sudo chown cardanoism:cardanoism /var/log/cardanoism
sudo install -m 0644 cron.d-cardanoism-notify /etc/cron.d/cardanoism-notify
```

### 4-2. cron スケジュールの考え方

| 種類 | 頻度 | 理由 |
|------|------|------|
| 通知（`pool` / `drep`） | 30分 | チェーン更新は数十秒〜数分単位だが、Koios 側の rate limit と通知の即時性のバランス |
| `reminder` | 1時間 | 日次集計の差分処理。1時間で十分 |
| `treasury` | 1時間 | エポック単位で更新されるため十分 |
| `fiat_sync` | 10分 | UI で常時表示されるため短め |
| `treasury_sync` / `vote_sync` / `summary_sync` | 15-30分 | UI 表示の最新性とサーバー負荷のバランス |
| `params_sync` | 6時間 | プロトコルパラメータはエポックでしか変化しない |
| `drep_sync` | 2時間 | DRep 数が多くフェッチが重い。低頻度で運用 |
| `vote_rationale_sync` | 4時間 | OpenAI コスト抑制 |

---

## 5. 運用コマンド

### 5-1. 全イベント手動実行

```bash
cd /opt/cardanoism
.venv/bin/python notify_worker.py
# = 全 --event を順次実行
```

### 5-2. 個別実行

```bash
# 通知だけ
.venv/bin/python notify_worker.py --event pool
.venv/bin/python notify_worker.py --event drep
.venv/bin/python notify_worker.py --event reminder

# 同期だけ
.venv/bin/python notify_worker.py --event drep_sync
.venv/bin/python notify_worker.py --event vote_sync
.venv/bin/python notify_worker.py --event summary_sync
.venv/bin/python notify_worker.py --event params_sync
.venv/bin/python notify_worker.py --event treasury_sync
.venv/bin/python notify_worker.py --event fiat_sync
```

### 5-3. テスト送信

```bash
# 対象ユーザー一覧
.venv/bin/python notify_worker.py --list-users

# ユーザーへ実データでテスト
.venv/bin/python notify_worker.py --test 1

# 特定イベントのダミーデータでテスト
.venv/bin/python notify_worker.py --test 1 --test-event pool_saturation

# ユーザーが ON にしているイベントだけダミーテスト
.venv/bin/python notify_worker.py --test 1 --test-enabled
```

### 5-4. エポック切替時刻の確認

```bash
.venv/bin/python notify_worker.py --epoch-schedule
```

直近 10 エポックの切替時刻と推奨 cron 行を出力する。

> リアルタイムバックエンドが稼働している場合、`epoch_start` 通知は Ogmios 側が担当するため、ここで提示された cron 行は **登録不要**。

### 5-5. 投票理由翻訳の制限

```bash
# メタデータ取得は最大 100 件、OpenAI 翻訳は最大 30 件で実行（コスト抑制）
.venv/bin/python notify_worker.py --event vote_rationale_sync \
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
| ログが急増 | `--list-users` でユーザー数を確認、`MAX_WORKERS = 10`（並列 Koios コール数）を絞ると軽減 |
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
