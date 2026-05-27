# DRep マッチング診断

ユーザーが 8 問の Likert (強く反対〜強く賛成) に答えるだけで、自分の価値観に
合う Cardano DRep を提案する診断機能。Cardano に詳しくない委任者でも
直感的に DRep を選べることを目的とする。

> **設計方針 (v4: outcome-first)**: ユーザー回答 / DRep プロファイル共に
> **8 axis を 0.0〜1.0** の同じスケールで表現し、axis 距離 + 信頼度重み付けで
> 類似度を出す。1 axis = 1 つの観察可能な DRep の振る舞い に対応し、
> 全 axis が独立 (直交) になるよう設計。
>
> DRep プロファイルは **GA pre-classification** (`governance_ai_analysis.axis_tags_json`)
> を集計して算出。AI は GA 単位でファクトと軸タグ付けを行い、DRep 単位の判定はしない。

---

## 1. 8 axis モデル (v4)

各 axis は「DRep の観察可能な 1 つの振る舞い」と 1:1 対応する。

| axis                     | 値 0.0 (賛成度低) ↔ 値 1.0 (賛成度高)                             | 集計ソース                                              |
|--------------------------|--------------------------------------------------------------|--------------------------------------------------------|
| `large_treasury`         | 大型 Treasury (≥1000 万 ADA) 支出への Yes 率                    | GA tag: `treasury_size = large`                        |
| `incumbent_org`          | IO / CF / Emurgo / Intersect / Midnight 関連提案への Yes 率      | GA tag: `orgs ∋ {IO, CF, Emurgo, Intersect, Midnight}` |
| `new_team`               | 新興チーム / 個人開発者への配分提案への Yes 率                   | GA tag: `orgs` が空 or `recipient_type = new`          |
| `technical`              | コア技術 / 基盤レベル提案 (ノード / プロトコル / 言語) への Yes 率 | GA tag: `priority = technical` (内容軸、作り手は不問)   |
| `adoption`               | dApp / DeFi / Wallet など実用層への Yes 率                       | GA tag: `priority = adoption`                          |
| `marketing`              | マーケ / PR / イベント予算への Yes 率                            | GA tag: `priority = marketing`                         |
| `protocol_change`        | HF / プロトコルパラメータ変更への Yes 率                         | GA `action_type` HardForkInitiation / ParameterChange  |
| `rationale_disclosure`   | DRep が投票理由を公開する頻度                                    | DRep プロパティ `reasoning_disclosure_rate` を直接利用 |

定義: [taxonomy.py](../cardanoism/backend/drep_compass/taxonomy.py)

**v3 からの変更点 (outcome-first 再設計)**:
- 旧 `treasury` (攻め/守り) → `large_treasury` (Yes 率に統一)
- 旧 `priority` (技術/採用 1 軸) → `technical` / `adoption` / `marketing` の 3 独立軸に分解
- 旧 `tech_origin` / `org` / `risk` の重複・対立構造を解消 → `incumbent_org` / `new_team` に再構成
- `protocol_change` 軸を復活 (action_type ベースで判定容易)
- `rationale_disclosure` (旧 `rationale`) は DRep プロパティ直接参照に固定 (集計不要)

---

## 2. ユーザー側フロー

1. `/governance/drep` の「マッチング診断」セクションで開始
2. 8 問 5 段階 Likert (強く反対=0.0 / やや反対=0.25 / 中立=0.5 / やや賛成=0.75 / 強く賛成=1.0)
3. q_id = axis 名で 1:1 マッピング (回答値がそのまま axis 値)
4. 最大 3 つまで「重要マーク」を付与可（該当 axis の重み × 1.5）
5. 回答送信 → `build_user_vector` で 8 axis ベクトル化
6. `list_matches` が quality filter を通った DRep プロファイルとの類似度（axis 重み付き）でソート
7. 上位 10 件をカード表示 + 1 行サマリ + 透明性モーダル (axis chip クリックで evidence 表示)

**質問カードの構成 (v4)**:
- 質問本文 (「○○すべきだ」の価値観表明スタイル)
- 論点 (賛否の対立構造の解説)
- 5 段階 Likert ボタン (全質問共通ラベル: 強く反対 / やや反対 / 中立 / やや賛成 / 強く賛成)
- 賛成派の主張 / 反対派の主張 (両論併記)
- 重要マーク toggle

**quality filter** ([config.py](../cardanoism/backend/drep_compass/config.py)):
- `analyzed_vote_count >= MIN_ANALYZED_VOTE_COUNT` (default 5) — 投票実績がある程度ある
- `reasoning_disclosure_rate >= MIN_REASONING_DISCLOSURE_RATE` (default 0.30) — 投票理由を公開している
- `REQUIRE_GIVEN_NAME=True` — CIP-119 自己紹介がある

委任量 (amount) はソート / フィルタには **使わない**。influence power に依存せず
liquid democracy 的に「質」で並べる設計。

質問定義: [questionnaire.py](../cardanoism/backend/drep_compass/questionnaire.py)
類似度計算: [match.py](../cardanoism/backend/drep_compass/match.py)

---

## 3. DRep プロファイル生成 (集計のみ、AI 不要)

`compass_profile_all` cron が active DRep 全件について
`governance_ai_analysis.axis_tags_json` を集計し、
`drep_profiles` テーブルに 8 axis スコア + 信頼度 + evidence を保存する。

```
   cron (daily 06:45)
        ↓
   notify_worker.py --event compass_profile_all
        ↓
   recalculate_all_drep_profiles
        │
        └─ for each active DRep:
              ├─ _fetch_drep_votes_with_tags
              │     (proposal_votes JOIN governance_ai_analysis.axis_tags_json)
              ├─ compute_axis_scores (純粋ロジック、AI 不要)
              │     - profile     : 8 axis × 0.0〜1.0
              │     - confidence  : 寄与投票数 / 10 で 0.0〜1.0 にクリップ
              │     - evidence    : axis ごとの寄与投票リスト
              │     ※ rationale_disclosure は dreps.reasoning_disclosure_rate を直接代入
              └─ _upsert drep_profiles
```

集計は決定論的 (同じデータからは必ず同じスコア)。
GA 単位のタグ付けは `ga_ai_worker.py` で既に処理済 ([ga-ai-analysis-backend.md](ga-ai-analysis-backend.md))。

集計ロジック: [profile.py:compute_axis_scores](../cardanoism/backend/drep_compass/profile.py)

**コスト**: drep_compass 自体は AI 呼び出しなし。GA 側の AI コストは [ga-ai-analysis-backend.md](ga-ai-analysis-backend.md) 参照。

---

## 4. データモデル

### drep_profiles ([021_match_v2_cleanup.sql](../cardanoism/backend/migrations/021_match_v2_cleanup.sql))

| 列                          | 説明                                              |
|----------------------------|---------------------------------------------------|
| `drep_id`                  | PRIMARY KEY                                       |
| `profile_json`             | 8 axis スコア (JSON, 0.0〜1.0)                    |
| `confidence_json`          | 8 axis 信頼度 (JSON, 0.0〜1.0)                    |
| `summary` / `summary_en`   | 任意のナラティブサマリ (v4 では空でも可)          |
| `evidence_json`            | axis ごとの根拠投票 (JSON)                        |
| `participation_rate`       | 常に 1.0 (実投票のみが母数)                       |
| `reasoning_disclosure_rate`| 投票理由公開率 0.0〜1.0 (= rationale_disclosure 軸) |
| `analyzed_vote_count`      | 分析した Yes/No 票数                              |
| `analysis_version`         | `'match-v3'` (config の `ANALYSIS_VERSION`)       |
| `calculated_at`            | 集計実行時刻                                      |

### user_drep_compass_answers

| 列                      | 説明                                       |
|------------------------|--------------------------------------------|
| `answer_json`          | 8 問の 1〜5 回答 (JSON)                    |
| `importance_json`      | 重要マーク q_id リスト (最大 3)            |
| `questionnaire_version`| `'match-v4'` — 旧バージョン回答は pre-fill されない |

ログイン中なら `user_id`、未ログインなら `session_id` で保存。

---

## 5. 運用コマンド

### 全 active DRep 再集計 (AI コストなし)

```bash
infisical run --env=mainnet -- python notify_worker.py --event compass_profile_all
```

cron 自動: `45 6 * * *` (daily) — [deploy/cron.d-cardanoism-notify](../deploy/cron.d-cardanoism-notify)

### 1 DRep のみ単体集計

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
- `drep_status = 'active'`: 集計対象母数
- `JOIN 一致 DRep 数`: 投票実績ある active DRep
- `analyzed_vote_count >= 5`: マッチング候補として表示可能な DRep 数

### v3.x → v4 への移行

`QUESTIONNAIRE_VERSION = "match-v4"` に bump 済。旧 v2/v3 で保存された回答は
pre-fill されないため、ユーザーは再回答が必要。drep_profiles の `analysis_version`
も v4 axis 構成で再生成するため、初回デプロイ後に `compass_profile_all` を 1 回手動実行。

---

## 6. 設定定数 ([config.py](../cardanoism/backend/drep_compass/config.py))

| 定数                            | 値           | 説明                              |
|--------------------------------|--------------|-----------------------------------|
| `ANALYSIS_VERSION`             | `match-v3`   | profile スキーマ識別子            |
| `QUESTIONNAIRE_VERSION`        | `match-v4`   | 質問セット識別子                  |
| `MIN_ANALYZED_VOTE_COUNT`      | `5`          | quality filter: 最小投票実績数    |
| `MIN_REASONING_DISCLOSURE_RATE`| `0.30`       | quality filter: 投票理由公開率の下限 |
| `REQUIRE_GIVEN_NAME`           | `True`       | quality filter: CIP-119 自己紹介必須 |
| `WEIGHT_IMPORTANT`             | `1.5`        | 重要マーク axis の重み倍率        |
| `MAX_IMPORTANT_AXES`           | `3`          | 1 ユーザーが付けられる重要マーク数 |
| `DEFAULT_MATCH_LIMIT`          | `10`         | 結果表示件数                      |

---

## 7. 関連ドキュメント

- 通常の Koios 同期: [koios-polling-backend.md](koios-polling-backend.md)
- GA 自体の AI 分析（マッチング診断の前段、axis_tags_json 生成）: [ga-ai-analysis-backend.md](ga-ai-analysis-backend.md)
- 初期セットアップ: [initial-setup.md](initial-setup.md)
