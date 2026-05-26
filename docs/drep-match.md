# DRep マッチング診断

ユーザーが 9 問の二者択一（+「迷う」）に答えるだけで、自分の価値観に
合う Cardano DRep を提案する診断機能。Cardano に詳しくない委任者でも
直感的に DRep を選べることを目的とする。

> **設計方針**: ユーザー回答 / DRep プロファイル共に **7 axis を 0.0〜1.0** の
> 同じスケールで表現し、axis 距離 + 信頼度重み付けで類似度を出す。
> DRep プロファイルは **AI が投票履歴 + rationale を直接読んで生成**
> （旧設計の gov_action_tags ルール集計は廃止）。

---

## 1. 7 axis モデル

各 DRep / 各ユーザーは 7 次元のベクトルで表現される。値は全て 0.0〜1.0
（0.5 = 中立）。

| axis           | 0.0 側                                  | 1.0 側                              |
|----------------|----------------------------------------|------------------------------------|
| `treasury`     | 攻め（大胆な Treasury 活用）            | 守り（慎重な Treasury 運用）        |
| `priority`     | 技術基盤（プロトコル R&D / インフラ）   | 実利用（dApp / DeFi / 採用拡大）    |
| `org`          | 既存組織（IO / CF / Intersect / Emurgo）| 分散配分（新興チーム / 個人）       |
| `protocol`     | 革新（HF / パラメータ変更に積極）       | 安定（合意層変更に慎重）            |
| `transparency` | ゆるめ（信頼ベース）                    | 厳しめ（KPI / マイルストーン必須）  |
| `risk`         | 大胆（実験的 / 高リスク許容）           | 慎重（不確実性に No）               |
| `marketing`    | 推進（PR / イベント支援）               | 抑制（プロダクト / 開発優先）       |

定義: [taxonomy.py](../cardanoism/backend/drep_compass/taxonomy.py)

---

## 2. ユーザー側フロー

1. `/governance/drep` の「マッチング診断」セクションで開始
2. 9 問の二者択一 + 「迷う」(answer=1/2/3 → 値 0.0 / 0.5 / 1.0)
3. 最大 3 つまで「重要マーク」を付与可（該当 axis の重み × 1.5）
4. 回答送信 → `build_user_vector` で 7 axis の平均ベクトル化
5. `list_matches` が quality filter を通った DRep プロファイルとの類似度（axis 重み付き）でソート
6. 上位 10 件をカード表示 + AI 生成のサマリ 1 行を併記

**quality filter** (config.py):
- `analyzed_vote_count >= MIN_ANALYZED_VOTE_COUNT` (default 5) — 投票実績がある程度ある
- `reasoning_disclosure_rate >= MIN_REASONING_DISCLOSURE_RATE` (default 0.30) — 投票理由を公開している
- `REQUIRE_GIVEN_NAME=True` — CIP-119 自己紹介がある

委任量 (amount) はソート / フィルタには **使わない**。influence power に依存せず
liquid democracy 的に「質」で並べる設計。

質問定義: [questionnaire.py](../cardanoism/backend/drep_compass/questionnaire.py)
類似度計算: [match.py](../cardanoism/backend/drep_compass/match.py)

---

## 3. DRep プロファイル生成 (AI)

`compass_profile_all` cron が active DRep 全件を OpenAI で分析し、
`drep_profiles` テーブルに 7 axis スコア + 信頼度 + 1 行サマリ + 根拠
を保存する。

```
   cron (daily 06:45)
        ↓
   notify_worker.py --event compass_profile_all
        ↓
   recalculate_all_drep_profiles
        │
        ├─ get_active_drep_ids (registered=1 AND drep_status='active')
        │
        └─ for each DRep:
              ├─ _fetch_drep_votes (proposal_votes JOIN governance_actions)
              ├─ analyze_drep_compass_profile (OpenAI gpt-5.4-mini)
              │     - profile     : 7 axis × 0.0〜1.0
              │     - confidence  : 7 axis × 0.0〜1.0
              │     - summary     : 日本語 1 文 (80 文字以内)
              │     - evidence    : axis あたり最大 3 件の根拠投票
              └─ _upsert drep_profiles
```

AI 呼び出し: [ai_client.py:analyze_drep_compass_profile](../cardanoism/backend/ai_client.py)
DB 書き込み: [profile.py](../cardanoism/backend/drep_compass/profile.py)

**コスト目安**: 1 DRep ≒ 入力 3.5K + 出力 1.8K tokens ≒ $0.01。
active 350〜400 件で 1 回 $3〜$5。日次 fallback として cron 設定。

**JSON truncation 対策**:
- `max_output_tokens = 4000`
- system prompt で `evidence` を axis あたり最大 3 件 / `reason` 120 文字 / `summary` 80 文字に制限

---

## 4. データモデル

### drep_profiles ([021_match_v2_cleanup.sql](../cardanoism/backend/migrations/021_match_v2_cleanup.sql))

| 列                          | 説明                                              |
|----------------------------|---------------------------------------------------|
| `drep_id`                  | PRIMARY KEY                                       |
| `profile_json`             | 7 axis スコア (JSON, 0.0〜1.0)                    |
| `confidence_json`          | 7 axis 信頼度 (JSON, 0.0〜1.0)                    |
| `summary`                  | AI 生成の日本語 1 行サマリ                        |
| `evidence_json`            | axis ごとの根拠投票 (JSON)                        |
| `participation_rate`       | v2 では常に 1.0 (実投票のみが母数)                |
| `reasoning_disclosure_rate`| 投票理由公開率 0.0〜1.0                           |
| `analyzed_vote_count`      | 分析した Yes/No/Abstain 票数                      |
| `analysis_version`         | `'match-v2'`                                      |
| `calculated_at`            | AI 分析実行時刻                                   |

### user_drep_compass_answers

| 列                      | 説明                                       |
|------------------------|--------------------------------------------|
| `answer_json`          | 9 問の 1/2/3 回答 (JSON)                   |
| `importance_json`      | 重要マーク q_id リスト (最大 3)            |
| `questionnaire_version`| `'match-v2'`                               |

ログイン中なら `user_id`、未ログインなら `session_id` で保存。

---

## 5. 運用コマンド

### 全 active DRep 再分析（OpenAI コスト発生）

```bash
infisical run --env=mainnet -- python notify_worker.py --event compass_profile_all
```

cron 自動: `45 6 * * *` (daily) — [deploy/cron.d-cardanoism-notify](../deploy/cron.d-cardanoism-notify)

### 1 DRep のみ単体分析

```bash
infisical run --env=mainnet -- python -c "
from cardanoism.backend.drep_compass.api import calculate_drep_profile
import json
print(json.dumps(calculate_drep_profile('<DREP_ID>'), indent=2, ensure_ascii=False))
"
```

### 診断 (drep_profiles テーブル + dreps + proposal_votes の状態確認)

```bash
infisical run --env=mainnet -- python notify_worker.py --event compass_status
```

主な観点:
- `drep_status = 'active'`: AI 分析の対象母数
- `JOIN 一致 DRep 数`: 投票実績ある active DRep（= 分析可能件数）
- `analyzed_vote_count >= 3`: マッチング候補として表示可能な DRep 数

---

## 6. 設定定数 ([config.py](../cardanoism/backend/drep_compass/config.py))

| 定数                            | 値           | 説明                              |
|--------------------------------|--------------|-----------------------------------|
| `ANALYSIS_VERSION`             | `match-v2`   | profile スキーマ識別子            |
| `QUESTIONNAIRE_VERSION`        | `match-v2`   | 質問セット識別子                  |
| `MIN_ANALYZED_VOTE_COUNT`      | `5`          | quality filter: 最小投票実績数    |
| `MIN_REASONING_DISCLOSURE_RATE`| `0.30`       | quality filter: 投票理由公開率の下限 |
| `REQUIRE_GIVEN_NAME`           | `True`       | quality filter: CIP-119 自己紹介必須 |
| `WEIGHT_IMPORTANT`             | `1.5`        | 重要マーク axis の重み倍率        |
| `MAX_IMPORTANT_AXES`           | `3`          | 1 ユーザーが付けられる重要マーク数 |
| `DEFAULT_MATCH_LIMIT`          | `10`         | 結果表示件数                      |
| `LOW_CONFIDENCE`               | `0.2`        | 「判断材料が少ない」と表示する閾値 |

---

## 7. 関連ドキュメント

- 通常の Koios 同期: [koios-polling-backend.md](koios-polling-backend.md)
- GA 自体の AI 分析（マッチング診断とは別系統）: [ga-ai-analysis-backend.md](ga-ai-analysis-backend.md)
- 初期セットアップ: [initial-setup.md](initial-setup.md)
