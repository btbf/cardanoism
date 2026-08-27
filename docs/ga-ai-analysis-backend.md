# GA AI 分析バックエンド 設定方法

ガバナンスアクション（GA）の中身をユーザーが理解するのを助ける**ファクト整理ツール**。
**OpenAI gpt-5.4-mini** を使って提案の中立的な要約とキーファクトを抽出し、
TreasuryWithdrawals の場合は機械計算による NCL 上限内チェックを補足表示する。

> **設計方針**: AI に評価 / スコアリング / 判定をさせない。AI は情報整理だけを担当し、
> 「準拠しているか」「賛成すべきか」といった判断はユーザーに委ねる。
> 過去には憲法準拠スコアや VISION 2030 KPI レーダーを実装していたが、
> AI 判定のブレが大きく信頼性が低いため A 方針（ファクト整理）に転換した。

```
        Ogmios listener / fallback cron
             ↓
    governance_actions 登録 + IPFS metadata取得
             │
             ├─ governance_actions に新規 INSERT
             └─ governance_ai_db.bulk_enqueue で pending 投入
                          ↓
              governance_ai_analysis (status=pending)
                          ↓
                  ga_ai_worker.py (常駐)
                          │
                          ├─ claim_next で atomic 取得 (status=analyzing)
                          ├─ ai_client.analyze_proposal で AI 抽出
                          │   - proposal_summary_ja / _en（300〜500 文字、6〜10 文）
                          │   - proposal_facts (label_ja/en + value_ja/en の配列)
                          ├─ compute_supplemental_facts で機械計算ファクト追加
                          │   - TreasuryWithdrawals の NCL 上限内チェック
                          └─ save_result で結果保存 (status=analyzed)
                          ↓
              GA 詳細ページ (/governance/<id>)
                  - GovernanceState.modal_ai_* に展開
                  - pending/analyzing 中は poll_ai_status が 5 秒ごとに再ロード
                  - ログインユーザーには委任先 DRep 投票カードも表示
                  - 投票期限カウントダウンバッジを header に表示
```

リアルタイムバックエンド（Ogmios）と Koios ポーリングバックエンドとは独立した第 3 のデーモン。

> 新規 VPS への一括デプロイは [`initial-setup.md`](initial-setup.md) に全体手順をまとめている。本ドキュメントは GA AI 分析個別の詳細。

---

## 1. インフラ要件

| コンポーネント | 用途 |
|--------------|------|
| Linux ホスト | systemd で常駐 |
| Python 3.10+ | 実行環境 |
| MariaDB | `governance_ai_analysis` + 既存テーブル |
| OpenAI API | gpt-5.4-mini（憲法本文は読まないので Vision OCR は不要） |

---

## 2. シークレット (Infisical)

`.env` ではなく **Infisical** で管理する。`mainnet` / `preview` environment ごとに切替。詳細セットアップは `docs/realtime-notification-backend.md` 5-2 を参照。

| 変数 | 説明 | デフォルト |
|------|------|----------|
| `GPT_API_KEY` | OpenAI API キー | - |
| `KOIOS_NETWORK` | mainnet / preprod / preview | `mainnet` |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME` | MariaDB 接続情報 | - |

---

## 3. セットアップ手順

### 3-1. マイグレーション

```bash
mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < cardanoism/backend/migrations/017_governance_ai_analysis.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < cardanoism/backend/migrations/018_governance_actions_action_anchor.sql
mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < cardanoism/backend/migrations/021_governance_ai_analysis_facts.sql
```

021 は旧スキーマ（スコア / verdict / pillars / KPI 関連カラム）を撤去し、
新スキーマ（`proposal_facts_json`）を追加する。
021 適用後は既存データに互換性が無いため、`TRUNCATE TABLE governance_ai_analysis;` で初期化推奨。

### 3-2. 依存パッケージ

```bash
pip install -r requirements.txt   # openai を含む
```

### 3-3. 初回バッチ

既存の Active / 直近 6 エポック以内の GA を一括で AI 分析キューに投入：

```bash
python notify_worker.py --event ga_ai_initial_sync
```

### 3-4. 常駐ワーカー起動

```bash
# テスト起動（フォアグラウンド）
python ga_ai_worker.py --poll-interval 20 --concurrency 3

# systemd 例（/etc/systemd/system/ga-ai-worker.service）
```

```ini
[Unit]
Description=Cardanoism GA AI Worker
After=network-online.target infisical-agent.service
Wants=network-online.target infisical-agent.service

[Service]
Type=simple
User=btism
WorkingDirectory=/home/btism/cardanoism_tmp
# 共通ラッパーがInfisical Agentのtoken sinkを読み込む
ExecStart=/usr/local/bin/cardanoism-infisical /home/btism/cardanoism_tmp/.venv/bin/python ga_ai_worker.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

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

新規 GA は Ogmios listener が検知し、IPFSメタデータ取得後に自動的に enqueue → ga_ai_worker が処理 → GA 詳細ページに `analyzed` 状態で表示する。初回取得に失敗した提案だけ、cronの `governance.py --retry-metadata` が指数バックオフ付きで再試行する。

メタデータ再試行cronの例（Koios `/proposal_list` は呼ばない）：

```
7,22,37,52 * * * *  python /path/to/cardanoism/cardanoism/backend/governance.py --retry-metadata --limit 20
```

Koiosの全件同期はステータス整合性確認としてepoch開始時と日次fallbackに限定する。

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

プロンプト改善や仕様変更で評価をやり直したいときに使う。

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

### 6-1. `governance_ai_analysis`（migration 017 + 021）

| カラム | 型 | 説明 |
|---|---|---|
| `proposal_id` | VARCHAR(255) PK | GA の proposal_id（governance_actions と同じ） |
| `status` | VARCHAR(16) | pending / analyzing / analyzed / failed |
| `worker_id` | VARCHAR(64) | claim 中ワーカーの識別子 |
| `started_at` | DATETIME | analyzing 遷移時刻（タイムアウト判定用） |
| `completed_at` | DATETIME | analyzed/failed 遷移時刻 |
| `attempts` | INT | 試行回数 |
| `last_error` | TEXT | 失敗時のエラー文 |
| `constitution_summary_ja` | TEXT | AI 生成の提案要約（300〜500 文字 / 6〜10 文） |
| `constitution_summary_en` | TEXT | 英語版要約 |
| `articles_json` | TEXT | （現状未使用、将来再導入の余地として残置） |
| `proposal_facts_json` | TEXT | AI 抽出のキーファクト + 機械計算ファクト |
| `rule_checks_json` | TEXT | （現状未使用、proposal_facts_json に統合済み） |
| `model_id` | VARCHAR(64) | 使用モデル ID |
| `constitution_meta_url` | TEXT | （現状 NULL、AI は憲法本文を読まないため） |
| `tokens_input` / `tokens_output` | INT | トークン使用量 |
| `cost_usd` | DECIMAL(10,6) | 概算コスト |

### 6-2. `proposal_facts_json` の中身

```json
[
  {
    "label_ja": "引き出し額",
    "label_en": "Amount",
    "value_ja": "50,000 ADA",
    "value_en": "50,000 ADA"
  },
  {
    "label_ja": "受取先",
    "label_en": "Recipient",
    "value_ja": "stake1xxx... (Cardanoism 財団)",
    "value_en": "stake1xxx... (Cardanoism Foundation)"
  },
  {
    "label_ja": "用途",
    "label_en": "Purpose",
    "value_ja": "教育プログラムの運営",
    "value_en": "Operating educational programs"
  },
  {
    "label_ja": "NCL 上限内チェック",
    "label_en": "NCL Limit Check",
    "value_ja": "上限内 — 50,000 / 350,000,000 ADA (0.01%)",
    "value_en": "Within limit — 50,000 / 350,000,000 ADA (0.01%)"
  }
]
```

末尾のエントリ（NCL 上限内チェック）は `compute_supplemental_facts()` が
追加する**機械計算ファクト**で、AI 出力ではない。
TreasuryWithdrawals 提案で `governance_actions.withdrawal_total_lovelace` と
`ncl_active.limit_ada` を比較して算出する。

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
- **analyzing → failed**: `save_failure`（OpenAI API エラー / DB エラー / 等）
- **analyzing → pending（自動）**: 10 分以上 analyzing が続いた行を `reclaim_stale` がリセット（クラッシュ復旧）
- **failed / analyzed → pending**: 手動再分析（CLI または UI の再試行ボタン）

---

## 8. プロンプト構造

OpenAI Chat Completions API:

```
[system]
You are a research assistant for Cardano governance proposals.
Your job is to produce a structured JSON output that helps Japanese-speaking
voters understand a proposal — NOT to score or judge it.

(GA タイプ別のファクト抽出ガイド)
(出力スキーマ: proposal_summary_ja/en + proposal_facts[])
(要約は 300-500 文字 / 6-10 文の中立記述)

[user]
# Title / Type / Abstract / Motivation / Rationale / Withdrawal
<提案本文>
```

`response_format={"type":"json_object"}` で JSON 出力を強制。

### 重要なルール

- AI に憲法本文は渡さない（コスト削減 + ブレ防止）
- スコア / verdict / KPI / 憲法評価は出力させない
- proposal_facts は **value_ja と value_en の両方を必須**で出力させる
- 中立的な記述のみ。賛否の判断は禁止

---

## 9. コスト目安（gpt-5.4-mini）

| 項目 | 単価（USD per 1M tokens） |
|---|---|
| Input | $0.75 |
| Cached input | $0.075 |
| Output | $4.50 |

1 GA あたり想定（入力 ~3K tok（cache 1.5K + 非 cache 1.5K）+ 出力 ~1.5K tok）：

```
非キャッシュ入力 1.5K × $0.75 / 1M = $0.001125
キャッシュヒット 1.5K × $0.075 / 1M = $0.0001125
出力           1.5K × $4.50  / 1M = $0.00675
                              合計  ≒ $0.008 (≒ 1.2 円)
```

50 件初回バックフィル → 約 $0.4（≒ 60 円）。

> 旧仕様（憲法本文 + 5 pillar + KPI 評価）に比べて入力 token が大幅に減ったため
> 1 GA あたりのコストはむしろ若干上がる傾向（出力に要約 + facts を多めに出すため）。
> 全体としては安価で運用できる。

---

## 10. UI への露出（参考）

GA 詳細ページ `/governance/<id>` の AI 分析セクションは：

- **提案の概要（AI 要約）**: `proposal_summary_ja/en` を中立記述で表示
- **提案の中身**: `proposal_facts_json` を表組みでリスト表示
  - 末尾の NCL 上限内チェックは機械計算ファクトとして混在表示
- **AI 補足の免責文**: 「AI による参考情報です」を末尾に小さく表示

可視性: ログインユーザーのみ。未ログインはログイン CTA を出す（`AuthState.is_logged_in` でガード）。

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
| `failed` が連発 | `GPT_API_KEY` 未設定 / quota 超過 / OpenAI API ダウン | API キー / Billing を確認、`--event ga_ai_reanalyze --all` で再キュー |
| pending が処理されない | ga_ai_worker が落ちている | `systemctl status ga-ai-worker` で確認 |
| analyzing が長時間残っている | プロセスがクラッシュ | 10 分後に reclaim_stale が自動 pending に戻す |
| 値が一部空白 | proposal の rationale / abstract が空 / 短すぎ | AI が抽出できる情報が無い。提案者のメタデータ品質に依存 |
| 英語表示時に日本語が混じる | 旧スキーマで生成された行（単一 `value` のみ） | TRUNCATE して再分析すれば新スキーマ（`value_ja` / `value_en`）になる |
| NCL 上限内チェックが出ない | `treasury_sync` 未実行で `ncl_active` が空 / TreasuryWithdrawals 以外の提案 | `python notify_worker.py --event treasury_sync` 実行 |

---

## 13. 関連実装

- `cardanoism/backend/ai_client.py` — OpenAI API ラッパー、プロンプト定義
- `cardanoism/backend/ai_analyze_worker.py` — `analyze_claimed()` 本体ロジック
- `cardanoism/backend/governance_ai_db.py` — DB CRUD + `compute_supplemental_facts()`
- `cardanoism/backend/db_connect.py` — `GovernanceState._load_ai_analysis()` で State に展開
- `cardanoism/components/governance_ai_analysis.py` — UI コンポーネント
- `ga_ai_worker.py` — 常駐ワーカーエントリポイント
- `notify_worker.py --event ga_ai_initial_sync / ga_ai_reanalyze` — CLI コマンド
