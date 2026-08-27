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
| `pool_delegation_reminder` | アドレス | 長期委任リマインダー（90 / 120 / 365 日）。**到達済み最高マイルストーン 1 件のみ**送信 (新規登録時に 3 通同時発火を防止) |
| `drep_delegation_reminder` | アドレス | 長期 DRep 委任リマインダー（90 / 120 / 365 日）。同上の 1 件発火仕様 |
| `drep_status_change` | アドレス | DRep ステータス変化（activity 期間超過は ledger state 判定） |
| `treasury_withdrawal_enacted` | ユーザー | トレジャリー引き出し提案の Enacted 検知 |

### 1-2. キャッシュ同期イベント

ページの応答性向上のため、Koios のレスポンスを DB にキャッシュする。

| イベント | 対象テーブル | 内容 |
|---------|------------|------|
| `treasury_sync` | `treasury_snapshot` / `treasury_withdrawal` / `ncl_active` | トレジャリー残高・履歴・NCL |
| `fiat_sync` | `fiat_rate` | ADA/JPY、ADA/USD レート（CoinGecko） |
| `drep_dirty_sync` | `dreps.amount` | listener が dirty mark した active DRep の委任量だけ差分更新 |
| `drep_sync` | `dreps` | DRep 一覧 + 状態 + メタデータ。epoch / 日次 fallback 用 |
| `vote_sync` | `proposal_votes` | 投票履歴 |
| `summary_sync` | `proposal_voting_summary` | 投票集計 |
| `params_sync` | `protocol_params` / `cc_members` | プロトコルパラメータ・憲法委員会 |
| `vote_rationale_sync` | `proposal_votes.rationale` / `rationale_ja` | **backup**: listener bg task が主で 4h cron は fallback (§ 1-3 参照) |
| `pool_sync` | `pools` (active + pending) | SPO 一覧 + 拡張メタ。`/pool_updates.active_epoch_no` で「現在 active な値」と「未来エポック反映予定の pending 値」を分離書込み (§ 1-5 参照) |
| `pool_block_history_sync` | `pools.block_history_5ep` / `apy_history_7ep` | プール別エポック作成ブロック数とAPYの履歴。通知もこのAPYキャッシュを参照する |
| `relay_check` | `pools.relay_alive` | リレー疎通チェック |
| `constitution_sync` | `constitution_cache` | Cardano 憲法本文の取得 + 翻訳 |
| `governance.py --retry-metadata` | `governance_actions` | Ogmios 登録後にIPFSメタデータ取得へ失敗したGAだけを指数バックオフで再試行（Koios不使用） |
| `ga_ai_initial_sync` | `governance_ai_analysis` (pending) | 既存 GA を AI 分析キューに一括投入 (空 DB の再投入用、通常は governance.py が自動 enqueue) |
| `ga_ai_reanalyze` | `governance_ai_analysis` | 単一 GA の再分析。`--proposal-id <id>` か `--all` (Active かつ analyzed) を併用 |
| `spo_role_initial_sync` | `stake_addresses.spo_pool_id` | 全 stake_address の SPO 判定を一括再計算 (新規 VPS の初回投入向け) |
| `notify_test` | (送信のみ、DB 変更なし) | `ADMIN_USER_ID` の登録チャンネル全て (LINE / メール / Telegram) に管理者用疎通テスト通知を 1 通ずつ送信 |

> リアルタイムバックエンド（Ogmios）が担当するイベント（`epoch_start` / `pool_retire` / `pool_fee_change` / `pool_epoch_performance` / `drep_new_governance_action` / `drep_vote` / `spo_pending_vote`）は notify_worker.py からは送信されない。Ogmios デーモンが必須。

### 1-3. vote_rationale_sync の責務移行

DRep 投票検知時の rationale 取得 + 翻訳は **`ogmios_listener.py` 内バックグラウンドタスク** が主体で行う:

1. listener が DRep 投票を検知 → `record_vote_from_event` で `proposal_votes` に即時書き込み (rationale 空、meta_url 入り)
2. 同じ Tx 内の DRep を集約 → `asyncio.create_task(_process_drep_vote_post(...))` で bg 起動
3. bg 内で IPFS fetch + OpenAI 翻訳 → DB UPDATE → `_notify_drep_vote` 発火
4. IPFS / OpenAI 失敗時でも通知は必ず飛ぶ (UX 優先)
5. `_rationale_lock` (asyncio.Lock) で bg タスクを順次実行し OpenAI レートバーストを回避

cron の `vote_rationale_sync` (4h) は **listener が落ちている間に Koios sync 経由で proposal_votes に書かれた古い行** をフォローするバックアップ。

### 1-4. Governance Action 本文の取得と再試行

新規 GA は Ogmios listener が `governance_actions` に即時登録し、同じバックグラウンドタスクで anchor のIPFS/HTTPSメタデータを取得する。失敗時は `meta_fetch_attempts` と `meta_fetch_next_at` を保存し、15分cronの `governance.py --retry-metadata` が期限到来分だけを再試行する。

- 再試行間隔: 15分 → 30分 → 1時間 → 2時間 → 4時間 → 8時間 → 16時間 → 24時間
- 最大8回。JSONを取得できたが任意フィールドが欠ける文書は成功扱いにし、無期限再試行を防ぐ
- 復旧した行だけ翻訳・AI分析キュー投入を行う
- Koios `/proposal_list` の全件取得はepoch開始時と日次fallbackに限定する
- DRep投票通知の提案名・種別も `governance_actions` を参照し、通知ごとのKoios全件取得は行わない

### 1-5. pool_sync の active / pending 分離

`/pool_info` は最新 cert の pledge/margin/fixed_cost をそのまま返してしまうため、ledger 上で未来エポック反映予定の値も「現在の値」として書き込まれてしまう問題があった。

修正後の `check_pool_sync`:
- **`/pool_info`** ... live 系 (active_stake / live_stake / saturation / blocks / メタ) のみ採用
- **`/pool_updates`** ... 直近 2 エポックぶんを `active_epoch_no=gte.<current-1>` で全プール 1 リクエスト取得し:
  - `active_epoch_no <= current_epoch` の最新 → `pools.pledge / margin / fixed_cost` (現在 active な値)
  - `active_epoch_no >  current_epoch` の最新 → `pools.pending_pledge / pending_margin / pending_fixed_cost / pending_effective_epoch` (次エポック反映予定)
- 直近で更新が無いプールは `/pool_info` の値を active 値として採用 (= 長らく変化が無い静かなプール)
- APYは`pool_block_history_sync`が`apy_history_7ep`へ保存し、10分ごとのプール通知と15分ごとの委任リマインダーはDBから最新値を一括取得する。キャッシュ欠損時は表示を省略し、Koiosへフォールバックしない

これに連動して UI には「次エポックで変更」バッジを表示 (`pending_effective_epoch IS NOT NULL` で判定)。listener 側 (`record_pool_registration`) も新規プール以外は pending_* 列に書く設計に変更済み。

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
| `GPT_API_KEY` | 任意 | OpenAI API キー（GA AI 分析 / 投票理由翻訳 / GA 翻訳で使用） |
| `OPENAI_MODEL` | 任意 | OpenAI モデル名（既定: `gpt-4o-mini`） |
| `NOTIFICATION_REWARD_WINDOW_SECONDS` | 任意 | 報酬通知を許可するepoch開始後の秒数（既定: `43200`） |
| `NOTIFICATION_TREASURY_WINDOW_SECONDS` | 任意 | Treasury施行通知を許可するepoch開始後の秒数（既定: `43200`） |
| `NOTIFICATION_STATE_RECOVERY_GAP_SECONDS` | 任意 | 状態通知を復旧baseline扱いにする停止時間（既定: `1800`） |
| `ADMIN_USER_ID` | 任意 | `notify_test` イベントの送信先ユーザー ID。この user の `notification_channels` に登録済みのチャンネル全て (LINE / メール / Telegram) に管理者用テスト通知が飛ぶ |
| `FEEDBACK_FORM_URL` / `FEEDBACK_FORM_USER_ID_ENTRY` / `FEEDBACK_FORM_USERNAME_ENTRY` | 任意 | ベータ版フィードバックフォーム連携 (UI 側) |

⚠️ は通知チャンネルを使う場合のみ必須。最低 1 つは設定。

Infisical AgentがUniversal Authの短期tokenを `/run/cardanoism/infisical-token` へ自動更新し、共通ラッパー `/usr/local/bin/cardanoism-infisical` がそのtokenを使用する。project ID / environmentは `/etc/cardanoism/infisical.env` から読む。cron定義自体には認証情報を置かない。配置手順は [`deploy/README.md`](../deploy/README.md) を参照。

---

## 4. cron 設定

cron 定義は [`deploy/cron.d-cardanoism-notify`](../deploy/cron.d-cardanoism-notify) 1 ファイルで完結する形式。VPS への install 手順は [`deploy/README.md`](../deploy/README.md) を参照。本セクションは設計意図と運用上の補足のみ。

### 4-1. cron file の構造

ファイル冒頭で 3 つの変数 (`INFISICAL_RUN` / `WORKDIR` / `PY`) をデプロイ時に書き換え、各 cron 行は以下の形:

```cron
*/30 * * * *  cardanoism cd $WORKDIR && $INFISICAL_RUN $PY notify_worker.py --event pool >> $LOG/notify-pool.log 2>&1
```

- 認証と接続先は共通ラッパーが解決する (cron file には token / project ID を含めない)
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
| `drep_dirty_sync` | 15 分 | listener が直近1時間に dirty mark した active DRep のみ `/drep_delegators` で再集計。全件一覧・infoは取得しない |
| `governance.py --retry-metadata --limit 20` | 15 分 | Ogmios後のメタデータ取得失敗分のみ。DBの次回時刻・最大試行回数で対象を限定し、Koiosは呼ばない |
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
| `drep_sync --full` | 04:30 | listener: epoch_start。常時の委任量差分は `drep_dirty_sync` |
| `pool_sync` | 05:00 | listener: epoch_start + Pool cert 検知 |
| `pool_block_history_sync` | 05:30 | listener: epoch_start |
| `vote_sync` | 06:00 | listener: 投票即時反映 |
| `constitution_sync` | 07:00 | listener: epoch_start |

> cron・epoch listener・手動実行は同じ MariaDB advisory lock を使用する。同じイベントが既に実行中なら後発は処理せず終了する。
> 平時の DRep 更新は dirty 対象だけなので、全DRepを15分ごとに取得する旧構成よりKoiosコール量を大幅に抑えられる。
> `governance.py` の全件同期は途中ページが失敗・不正応答になった場合、取得済みの部分結果も破棄してDB更新を中止する。

#### API 復旧時の古い通知抑止

チェーン履歴や定期syncのcatch-upと通知配送は分離する。Koiosが復旧しても、
以下のwindowを過ぎた通知は送らない。

| 対象 | 既定window | 環境変数 |
|---|---:|---|
| 報酬入金 | 入金epoch開始から12時間 | `NOTIFICATION_REWARD_WINDOW_SECONDS` |
| Treasury施行 | 施行epoch開始から12時間 | `NOTIFICATION_TREASURY_WINDOW_SECONDS` |
| saturation / pledge不足 / DRep状態 | 最終成功から30分超なら復旧直後はbaseline更新のみ | `NOTIFICATION_STATE_RECOVERY_GAP_SECONDS` |

Cardanoの報酬epoch Nはepoch N+2開始時に入金される。そのため現在epoch 651では
reward epoch 649が「今回の入金」だが、651開始から12時間を過ぎてAPIが復旧した場合は
通知専用のreward API取得も抑止する。これにより古い通知だけでなく、Free枠で意味のない
再取得が繰り返されることも防ぐ。GA・vote等のチェーン履歴と各 `*_sync` は通常どおり
catch-upを継続する。

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
infisical run --env=preview -- python notify_worker.py --event drep           # status_change + drep_unvoted_ga
infisical run --env=preview -- python notify_worker.py --event drep_unvoted   # drep_unvoted_ga のみ (status_change スキップ)
infisical run --env=preview -- python notify_worker.py --event reminder
infisical run --env=preview -- python notify_worker.py --event treasury

# 同期だけ
infisical run --env=preview -- python notify_worker.py --event drep_dirty_sync  # dirty DRep の委任量だけ
infisical run --env=preview -- python notify_worker.py --event drep_sync
infisical run --env=preview -- python notify_worker.py --event vote_sync
infisical run --env=preview -- python notify_worker.py --event summary_sync
infisical run --env=preview -- python notify_worker.py --event params_sync
infisical run --env=preview -- python notify_worker.py --event treasury_sync
infisical run --env=preview -- python notify_worker.py --event fiat_sync
infisical run --env=preview -- python notify_worker.py --event vote_rationale_sync   # listener bg の backup

# SPO 系
infisical run --env=preview -- python notify_worker.py --event pool_sync
infisical run --env=preview -- python notify_worker.py --event pool_block_history_sync
infisical run --env=preview -- python notify_worker.py --event relay_check

# 単発系 (--event "all" には含まれず、明示指定でのみ実行)
infisical run --env=preview -- python notify_worker.py --event constitution_sync         # 憲法本文取得 + 翻訳
infisical run --env=preview -- python notify_worker.py --event ga_ai_initial_sync        # GA AI 分析キューに既存 GA を一括 enqueue (空 DB 再投入用)
infisical run --env=preview -- python notify_worker.py --event ga_ai_reanalyze --proposal-id <gov_action_id>  # 単一 GA 再分析
infisical run --env=preview -- python notify_worker.py --event ga_ai_reanalyze --all     # Active analyzed 全件を再分析
infisical run --env=preview -- python notify_worker.py --event spo_role_initial_sync     # 全 stake_address の spo_pool_id を再判定
infisical run --env=preview -- python notify_worker.py --event notify_test               # ADMIN_USER_ID へ管理者用 疎通テスト通知
```

### 5-3. 初回投入 / DB リセット時の同期手順

新規環境にデプロイした直後、またはネットワーク切替（mainnet ↔ preview）でガバナンス系・SPO 系のキャッシュテーブルを TRUNCATE した直後に **1 回だけ** 実行する。順序が重要（GA 本体が無いと AI 分析の enqueue 対象が無いため）。

```bash
INF="infisical run --env=preview --"

# (1) GA 本体を governance_actions に取り込む
#     Koios /proposal_list を全件フェッチ → upsert → 新規 GA は AI 分析キューに自動 enqueue
$INF python cardanoism/backend/governance.py --no-translate
# 翻訳まで一気にやる場合は --no-translate を外す

# Ogmios後の metadata 失敗分だけを手動再試行する場合（通常は15分cron）
$INF python cardanoism/backend/governance.py --retry-metadata --limit 20

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

> `notification_check_state.scope_id` は **`NOT NULL DEFAULT 0`** で運用 (global scope は `scope_id = 0`)。MySQL/MariaDB の UNIQUE は NULL を毎回別物として扱うため、NULL 許容にすると ON DUPLICATE KEY UPDATE が動かず行が増殖するバグがあったため修正済み。
>
> 既存 DB のクリーンアップ:
>
> ```sql
> -- 重複削除 (最新 id を残す)
> DELETE n1 FROM notification_check_state n1
> INNER JOIN notification_check_state n2
>   ON n1.scope_type = n2.scope_type
>  AND COALESCE(n1.scope_id, -1) = COALESCE(n2.scope_id, -1)
>  AND n1.key_name = n2.key_name
>  AND n1.id < n2.id;
> -- NULL → 0
> UPDATE notification_check_state SET scope_id = 0 WHERE scope_id IS NULL;
> -- NOT NULL DEFAULT 0 に変更
> ALTER TABLE notification_check_state MODIFY COLUMN scope_id INT NOT NULL DEFAULT 0;
> -- 既に廃止された pool_fee:* 行の掃除
> DELETE FROM notification_check_state WHERE key_name LIKE 'pool_fee:%';
> ```

#### 現在使われている key_name 一覧

| scope_type | key_name | 用途 |
|---|---|---|
| `global` (id=0) | `ogmios_last_slot` / `ogmios_last_id` | Ogmios ChainSync **カーソル** (listener が書込み) |
| `global` (id=0) | `current_epoch` | epoch_start 通知の多重発火防止 (listener) |
| `stake_address` | `pool_saturated` | 飽和フラグ (連続通知抑止) |
| `stake_address` | `pool_pledge_short` | 誓約不足フラグ |
| `stake_address` | `pool_delegation_date` | プール委任日 (90 / 120 / 365 日リマインダー起算) |
| `stake_address` | `drep_delegation_date` | DRep 委任日 (同上) |
| `stake_address` | `drep_status` | DRep ステータス前回値 (変化検知) |

`pool_fee:<pool_id>` は廃止 (比較ベースラインは `pools` テーブルから直接読む方式に変更)。

---

## 7. トラブルシューティング

| 症状 | 原因と対処 |
|------|----------|
| Koios `429 Too Many Requests` | rate limit。`KOIOS_API_KEY` を設定するか、cron 頻度を下げる |
| 通知が来ない | `notification_settings` / `stake_notification_settings` の `enabled = 0` を確認、`notification_channels` 登録の有無を確認 |
| 同じ通知が繰り返される | `notification_log` に該当 dedup_key の行があるか確認、`notification_check_state` の前回値を確認 |
| `vote_rationale_sync` が遅い／高額 | `--fetch-limit` / `--translate-limit` で制限。listener bg が主体なので通常コストは listener 側で発生 (バーストは `_rationale_lock` で抑止) |
| `treasury_sync` で残高が更新されない | Koios 側の同期遅延。1〜2エポック分は遅延するのが正常 |
| ログが急増 | DB 上で `SELECT COUNT(*) FROM notification_channels WHERE channel_type='line'` を確認、`MAX_WORKERS = 10`（並列 Koios コール数）を絞ると軽減 |
| エポック開始通知が重複 | リアルタイムバックエンドが担当しているため、`notify_worker.py --event epoch_start` は cron に登録しない |
| 「次エポックで変更」バッジが消えない / 出るべきタイミングで出ない | `pools.pending_*` と active 値が `/pool_updates.active_epoch_no` の判定に基づいて反映されているか確認。次回の `pool_sync` で正される。手動で再判定するなら `--event pool_sync` を直接実行 |
| `notification_check_state` が急増する | scope_id NULL バグの旧 DB。§ 6-3 のクリーンアップ SQL で重複削除 + NOT NULL DEFAULT 0 に ALTER |
| `notify_test` 通知が届かない | `ADMIN_USER_ID` の設定確認、対象ユーザーが `notification_channels` (line / email / telegram) を登録済みかチェック |

---

## 8. リアルタイムバックエンドとの責務分担

| イベント | リアルタイム（Ogmios） | Koios ポーリング |
|---------|:--------------------:|:---------------:|
| epoch_start | ✅ | — |
| pool_epoch_performance | ✅ | — |
| pool_retire | ✅ | — |
| pool_fee_change | ✅ (pending_* に書込み) | — |
| drep_new_governance_action | ✅ (listener bg で IPFS fetch + 翻訳 → 通知) | — |
| drep_vote | ✅ (listener bg で IPFS fetch + 翻訳 → 通知) | — |
| spo_pending_vote | ✅ (drep_new_governance_action と同じ bg タスクで発火) | — |
| pool_saturation | — | ✅ |
| pool_pledge_shortage | — | ✅ |
| pool_reward_received | — | ✅ |
| pool / drep_delegation_reminder | — | ✅ |
| drep_status_change | — | ✅ |
| DRep live 委任量 | dirty mark ✅ | dirty 対象だけ再集計 (`drep_dirty_sync`) |
| treasury_withdrawal_enacted | (listener も拾うが軽量な safety net 用) | ✅ |
| vote_rationale_sync | ✅ (listener bg = primary) | ✅ (4h cron = backup) |
| 全 *_sync（キャッシュ） | (一部 listener が epoch_start で chain 起動) | ✅ |

リアルタイムバックエンドが停止しても Koios ポーリング側で多くは代替できるが、検知遅延が発生する（最大 cron 周期分）。本番運用は両系統 + 監視を強く推奨。

---

## 9. 参考リンク

- [Koios API ドキュメント](https://api.koios.rest/)
- [CoinGecko API](https://www.coingecko.com/api/documentation)
- [OpenAI API](https://platform.openai.com/docs/)
- [リアルタイム通知バックエンド設定](realtime-notification-backend.md)
