# GA AI 分析バックエンド 設定方法

ガバナンスアクション（GA）に対して **OpenAI gpt-5.4-mini** で「Cardano 憲法準拠スコア」と「VISION 2030 評価」を自動生成する常駐ワーカー `ga_ai_worker.py` のセットアップと CLI コマンド。

```
        cron / 自動 trigger
             ↓
    governance.py (Koios sync)
             │
             ├─ governance_actions に新規 INSERT
             └─ governance_ai_db.bulk_enqueue で pending 投入
                          ↓
              governance_ai_analysis (status=pending)
                          ↓
                  ga_ai_worker.py (常駐)
                          │
                          ├─ claim_next で atomic 取得 (status=analyzing)
                          ├─ 憲法本文を IPFS から取得 (PDF/JSON/Markdown 自動判定)
                          ├─ OpenAI gpt-5.4-mini で分析
                          └─ save_result で結果保存 (status=analyzed)
                          ↓
              GA 詳細ページ (/governance/<id>)
                  - GovernanceState.modal_ai_* に展開
                  - pending/analyzing 中は poll_ai_status が 5 秒ごとに再ロード
```

リアルタイムバックエンド（Ogmios）と Koios ポーリングバックエンドとは独立した第 3 のデーモン。

---

## 1. インフラ要件

| コンポーネント | 用途 |
|--------------|------|
| Linux ホスト | systemd で常駐 |
| Python 3.10+ | 実行環境 |
| MariaDB | `governance_ai_analysis` + 既存テーブル |
| OpenAI API | gpt-5.4-mini |
| pypdf | 憲法 PDF のテキスト抽出 |
| IPFS gateway | 憲法本文取得（複数 gateway フォールバック） |

---

## 2. 環境変数

| 変数 | 説明 | デフォルト |
|------|------|----------|
| `GPT_API_KEY` | OpenAI API キー（`OPENAI_API_KEY` でも可） | - |
| `KOIOS_NETWORK` | mainnet / preprod / preview | `mainnet` |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME` | MariaDB 接続情報 | - |

---

## 3. セットアップ手順

### 3-1. マイグレーション

```bash
mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < cardanoism/backend/migrations/017_governance_ai_analysis.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < cardanoism/backend/migrations/018_governance_actions_action_anchor.sql
```

### 3-2. 依存パッケージ

```bash
pip install -r requirements.txt   # openai と pypdf を含む
```

### 3-3. 既存 GA を sync して action_anchor_url を埋める

`action_anchor_url` カラムは 018 で追加されたため、既存の GA では NULL のまま。以下を 1 度実行して全 GA を再 sync する：

```bash
python -m cardanoism.backend.governance --no-translate
```

確認：

```sql
SELECT proposal_id, enacted_epoch, action_anchor_url
FROM governance_actions
WHERE proposal_type='NewConstitution' AND enacted_epoch IS NOT NULL
ORDER BY enacted_epoch DESC LIMIT 1;
```

`action_anchor_url` に IPFS URL が入っていれば成功。

### 3-4. 初回バッチ

既存の Active / 直近 6 エポック以内の GA を一括で AI 分析キューに投入：

```bash
python notify_worker.py --event ga_ai_initial_sync
```

### 3-5. 常駐ワーカー起動

```bash
# テスト起動（フォアグラウンド）
python ga_ai_worker.py --poll-interval 20 --concurrency 3

# systemd 例（/etc/systemd/system/ga-ai-worker.service）
```

```ini
[Unit]
Description=Cardanoism GA AI Worker
After=mysql.service network.target

[Service]
Type=simple
User=cardanoism
WorkingDirectory=/path/to/cardanoism
EnvironmentFile=/path/to/cardanoism/.env
ExecStart=/usr/bin/python /path/to/cardanoism/ga_ai_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ga-ai-worker
sudo systemctl start ga-ai-worker
sudo journalctl -u ga-ai-worker -f
```

---

## 4. 通常運用

新規 GA は cron で動く `governance.py` （Koios sync）が検知して自動的に enqueue → ga_ai_worker が処理 → GA 詳細ページに `analyzed` 状態で表示。

`governance.py` を実行する cron 例（既存の通知 cron に相乗り想定）：

```
*/5 * * * *  python /path/to/cardanoism/cardanoism/backend/governance.py --no-translate
```

---

## 5. CLI コマンド

### 5-1. 初回同期（デプロイ時 1 回だけ）

```bash
python notify_worker.py --event ga_ai_initial_sync
```

対象（OR 条件）：
- Active（ratified/enacted/dropped/expired すべて NULL）
- Ratified（`ratified_epoch IS NOT NULL`）
- Enacted（`enacted_epoch IS NOT NULL`）
- `expiration >= 現在エポック - 6`（直近 Expired / Dropped を含める）

`INSERT IGNORE` なので何度実行しても安全。既に行があるものはスキップ。

### 5-2. 再分析

#### 単一 GA を再分析

```bash
python notify_worker.py --event ga_ai_reanalyze \
  --proposal-id gov_action1xxx...
```

`status` 不問で `pending` に戻す。Active 判定もしない（過去の決着済み GA も狙い撃ちで再分析できる）。

#### Active な analyzed 全件を再分析

```bash
python notify_worker.py --event ga_ai_reanalyze --all
```

対象は `status='analyzed' かつ Active な GA` のみ。Ratified / Enacted / Dropped / Expired は対象外（既決着分は再分析しない）。

憲法改訂やプロンプト改善で評価をやり直したいときに使う。

### 5-3. ワーカー起動

```bash
python ga_ai_worker.py [--poll-interval 20] [--concurrency 3]
```

| オプション | デフォルト | 説明 |
|---|---|---|
| `--poll-interval` | 20 秒 | キュー再走査の間隔 |
| `--concurrency` | 3 | 並列分析数（OpenAI rate limit と相談） |

SIGINT / SIGTERM で graceful shutdown（drain 中のジョブを完了してから停止）。

---

## 6. データモデル

### 6-1. `governance_ai_analysis`（migration 017）

| カラム | 型 | 説明 |
|---|---|---|
| `proposal_id` | VARCHAR(255) PK | GA の proposal_id（governance_actions と同じ） |
| `status` | VARCHAR(16) | pending / analyzing / analyzed / failed |
| `worker_id` | VARCHAR(64) | claim 中ワーカーの識別子 |
| `started_at` | DATETIME | analyzing 遷移時刻（タイムアウト判定用） |
| `completed_at` | DATETIME | analyzed/failed 遷移時刻 |
| `attempts` | INT | 試行回数 |
| `last_error` | TEXT | 失敗時のエラー文 |
| `constitution_score` | TINYINT | 憲法準拠スコア (0-100) |
| `constitution_verdict_*` | VARCHAR(64) | 短評（JA/EN） |
| `constitution_summary_*` | TEXT | 総評（JA/EN） |
| `articles_json` | TEXT | 条文ごとの整合性 JSON |
| `concerns_*_json` | TEXT | 懸念点リスト JSON（JA/EN） |
| `pillars_json` | TEXT | 5 pillar 評価 JSON |
| `related_kpis_json` | TEXT | 関連 KPI JSON |
| `model_id` | VARCHAR(64) | 使用モデル ID |
| `constitution_meta_url` | TEXT | 分析時に使った憲法 URL |
| `tokens_input` / `tokens_output` | INT | トークン使用量 |
| `cost_usd` | DECIMAL(10,6) | 概算コスト |

### 6-2. `governance_actions.action_anchor_url`（migration 018）

NewConstitution 提案で、実際の憲法本文ドキュメントの URL を保存する。`meta_url`（提案メタデータ JSON）とは別物。

---

## 7. ステートマシン

```
        ┌─────────┐
        │ pending │ ←──── enqueue (governance.py / initial_sync / reanalyze)
        └────┬────┘
             │ claim_next (atomic UPDATE)
             ↓
       ┌─────────────┐  ┌──── reclaim_stale (10 分タイムアウト)
       │  analyzing  │ ←┘
       └─────┬───────┘
             │
       ┌─────┴──────┐
       ↓            ↓
  ┌─────────┐  ┌─────────┐
  │analyzed │  │ failed  │ ←── 再分析時はこれも pending に戻す
  └─────────┘  └─────────┘
```

- **pending → analyzing**: `claim_next` が atomic UPDATE で取得（同時実行で 1 ワーカーだけ成功）
- **analyzing → analyzed**: `save_result` 成功
- **analyzing → failed**: `save_failure`（IPFS 取得失敗 / OpenAI API エラー / 等）
- **analyzing → pending（自動）**: 10 分以上 analyzing が続いた行を `reclaim_stale` がリセット（クラッシュ復旧）
- **failed / analyzed → pending**: 手動再分析（CLI または UI の再試行ボタン）

---

## 8. 憲法ソース

`constitution_fetcher.py` が DB から最新 enacted NewConstitution を引き、本文を取得する。

優先順：
1. `action_anchor_url`（実際の憲法本文 PDF / Markdown）
2. `meta_url`（提案メタデータ JSON、フォールバック）
3. JSON 内 `body.references[]` で "constitution" ラベル

取得した bytes は Content-Type / マジックバイトで判定して以下のいずれかでテキスト化：
- PDF: pypdf で抽出
- JSON: `body.title / abstract / motivation / rationale` を連結、不足時は references を 1 段辿る
- Markdown / プレーンテキスト: そのまま

同一プロセス内では URL をキーに in-process キャッシュ。新憲法 enact で URL が変われば自動的にキャッシュ無効化。

IPFS gateway フォールバック: `ipfs.io` / `dweb.link` / `gateway.pinata.cloud` / `cloudflare-ipfs.com` の順。

---

## 9. プロンプト構造

OpenAI Chat Completions API:

```
[system]
固定指示 (5 Pillars 説明 / 9 KPIs リスト / JSON スキーマ / ガイドライン)

# Cardano Constitution (reference)
<憲法全文> ← cache_control 相当（OpenAI 自動キャッシュ）

[user]
# Title / Type / Abstract / Motivation / Rationale / Withdrawal
<提案本文>
```

`response_format={"type":"json_object"}` で JSON 出力を強制。

---

## 10. コスト目安（gpt-5.4-mini）

| 項目 | 単価（USD per 1M tokens） |
|---|---|
| Input | $0.75 |
| Cached input | $0.075 |
| Output | $4.50 |

1 GA あたり想定（入力 ~5K tok / 4K キャッシュ + 出力 ~1K tok）：

```
非キャッシュ入力 1K × $0.75 / 1M = $0.00075
キャッシュヒット 4K × $0.075 / 1M = $0.0003
出力          1K × $4.50  / 1M = $0.0045
                             合計  $0.0056 ≒ 0.85 円
```

50 件初回バックフィル → 約 $0.28（≒ 42 円）。

---

## 11. ログとモニタリング

- ワーカーログ: `journalctl -u ga-ai-worker -f`
- DB クエリで監視：

```sql
-- 現在のキュー状況
SELECT status, COUNT(*) FROM governance_ai_analysis GROUP BY status;

-- 直近の失敗
SELECT proposal_id, last_error, completed_at
FROM governance_ai_analysis
WHERE status='failed'
ORDER BY completed_at DESC LIMIT 10;

-- 累積コスト
SELECT SUM(cost_usd) AS total_usd, SUM(tokens_input) AS in_tok, SUM(tokens_output) AS out_tok
FROM governance_ai_analysis WHERE status='analyzed';
```

---

## 12. トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `failed` が連発 | `GPT_API_KEY` 未設定 / quota 超過 | API キー / Billing を確認、`--event ga_ai_reanalyze --all` で再キュー |
| `failed` で `last_error: 憲法本文の取得に失敗` | IPFS gateway 全滅 / `action_anchor_url` 空 | governance.py 再 sync で URL を埋め直す。pypdf 未インストールなら `pip install pypdf` |
| pending が処理されない | ga_ai_worker が落ちている | `systemctl status ga-ai-worker` で確認 |
| analyzing が長時間残っている | プロセスがクラッシュ | 10 分後に reclaim_stale が自動 pending に戻す |
| 憲法のバージョンが古い | 新しい NewConstitution が enacted した直後 | ga_ai_worker を再起動するか、しばらく待てば in-process キャッシュも自動更新（meta_url が変わるため） |
