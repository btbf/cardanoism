# Backend Scripts

このREADMEは `cardanoism/backend` 配下の主要スクリプトの使い方と更新挙動をまとめたものです。
This README summarizes how to run the main scripts under `cardanoism/backend` and how they update data.

---

## 日本語

### campaigns_new.py

- 目的: Catalyst ExplorerのCampaigns APIから取得し、`campaigns_new` に取り込む
- オプション: なし
- 更新挙動:
  - 既存がなければ INSERT
  - 既存があれば差分のみ UPDATE（`id` と内部キーは除外）
  - タイトル/要約の日本語訳をOpenAIで生成・更新（タイトル/要約が変わった場合）
  - fund番号をタイトルから推測して `fund_uuid` を補完
- 依存: ネットワーク、`GPT_API_KEY`（OpenAI翻訳）

### funds_update_new.py

- 目的: Catalyst ExplorerのFunds APIから取得し、`funds_new` に取り込む
- オプション: なし
- 更新挙動:
  - 既存がなければ INSERT
  - 既存があれば差分のみ UPDATE（`id` を除外、数値/日時は正規化比較）

### proposals_update_new.py

- 目的: Catalyst ExplorerのProposals APIから取得し、`proposals_new` に取り込む
- オプション:
  - `--fund` Fund識別子（UUID or 番号）。未指定なら全Fund
- 更新挙動:
  - 既存がなければ INSERT（`COLUMN_ORDER` 全項目）
  - 既存があれば差分のみ UPDATE
  - UPDATE対象は以下8項目のみ（`None` は更新しない）
    - `amount_received`, `funding_status`, `yes_votes_count`, `abstain_votes_count`
    - `unique_wallets`, `alignment_score`, `feasibility_score`, `auditability_score`
  - `projectcatalyst_link` を解決（API提供URLの生存確認 → 生成URLの検証）

### proposal_scraping.py

- 目的: `proposals_new.projectcatalyst_link` の詳細ページをPlaywrightでスクレイプし、詳細カラムを更新
- オプション:
  - `--fund` fund_id で絞り込み（整数）
  - `--limit` 件数上限
  - `--id` `uuid` / `catalyst_id` をカンマ区切り指定
  - `--bat` バッチモード（`project_status` のみ更新）
  - `--force` 上書きモード（`idea_raw_html` の空条件を外す）
  - `--debug` デバッグ出力
- 更新挙動:
  - 対象抽出: `projectcatalyst_link` が空でないもの
  - 通常モード（`--bat`/`--force` なし）:
    - `idea_raw_html` が空のものだけ対象
    - 更新カラム: `idea_raw_html`, `idea_semantic_blocks`, `catalyst_id`,
      `project_status`, `project_country`, `currency`, `currency_symbol`, `milestones_link`
  - `--bat`:
    - `idea_raw_html` 条件は外れる
    - 更新カラム: `project_status` のみ
  - `--force`:
    - `idea_raw_html` 条件は外れる
    - 更新内容は通常モードと同じ

### translate_proposals_new.py

- 目的: `proposals_new` の翻訳カラム（日本語）を生成・更新
- オプション:
  - `--fund` Fund識別子（UUID or 番号）
  - `--id` 対象提案（`uuid` or `catalyst_id`）
  - `--limit` 1回の処理件数（既定 50）
  - `--sleep` 翻訳間の待機秒数
  - `--force` 既存値があっても再翻訳
  - `--workers` 並列翻訳数
  - `--debug` 詳細ログ
- 更新挙動:
  - `title_ja`, `problem_ja`, `solution_ja` を翻訳
  - `idea_semantic_blocks_ja` / `idea_semantic_blocks_ai` が存在する場合は翻訳
  - 通常は未翻訳のみ対象、`--force` で再翻訳
- 依存: `GPT_API_KEY`（OpenAI）

---

## English

### campaigns_new.py

- Purpose: Fetch campaigns from Catalyst Explorer API and load into `campaigns_new`
- Options: none
- Update behavior:
  - INSERT when missing
  - UPDATE only changed columns (excluding `id` and internal keys)
  - Translate title/excerpt to Japanese via OpenAI when changed
  - Infer `fund_uuid` from the title’s fund number
- Requires: network access, `GPT_API_KEY` (OpenAI)

### funds_update_new.py

- Purpose: Fetch funds from Catalyst Explorer API and load into `funds_new`
- Options: none
- Update behavior:
  - INSERT when missing
  - UPDATE only changed columns (excluding `id`, with normalized numeric/datetime comparison)

### proposals_update_new.py

- Purpose: Fetch proposals from Catalyst Explorer API and load into `proposals_new`
- Options:
  - `--fund` Fund identifier (UUID or number). Blank = all funds
- Update behavior:
  - INSERT when missing (all `COLUMN_ORDER` fields)
  - UPDATE only changed fields
  - Only these 8 fields are eligible for UPDATE (skip `None`)
    - `amount_received`, `funding_status`, `yes_votes_count`, `abstain_votes_count`
    - `unique_wallets`, `alignment_score`, `feasibility_score`, `auditability_score`
  - Resolve `projectcatalyst_link` by validating API URL and generated URL

### proposal_scraping.py

- Purpose: Scrape proposal detail pages via Playwright and update `proposals_new` details
- Options:
  - `--fund` filter by fund_id (int)
  - `--limit` max number of records
  - `--id` comma-separated `uuid` / `catalyst_id`
  - `--bat` batch mode (update `project_status` only)
  - `--force` overwrite mode (skip the `idea_raw_html` empty filter)
  - `--debug` debug logs
- Update behavior:
  - Target filter: `projectcatalyst_link` must be present
  - Normal mode (no `--bat`/`--force`):
    - Only rows with empty `idea_raw_html`
    - Update: `idea_raw_html`, `idea_semantic_blocks`, `catalyst_id`,
      `project_status`, `project_country`, `currency`, `currency_symbol`, `milestones_link`
  - `--bat`:
    - Skip the `idea_raw_html` empty filter
    - Update `project_status` only
  - `--force`:
    - Skip the `idea_raw_html` empty filter
    - Same update fields as normal mode

### translate_proposals_new.py

- Purpose: Translate `proposals_new` text fields into Japanese
- Options:
  - `--fund` Fund identifier (UUID or number)
  - `--id` proposal filter (`uuid` or `catalyst_id`)
  - `--limit` max records per run (default 50)
  - `--sleep` seconds between translations
  - `--force` re-translate even if already populated
  - `--workers` number of parallel workers
  - `--debug` verbose logs
- Update behavior:
  - Translates `title_ja`, `problem_ja`, `solution_ja`
  - Also handles `idea_semantic_blocks_ja` / `idea_semantic_blocks_ai` when present
  - By default, only rows with empty target fields; `--force` re-translates
- Requires: `GPT_API_KEY` (OpenAI)
