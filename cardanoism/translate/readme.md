# Translation Control Rules for Cardano Catalyst (JA)

## 目的

この翻訳システムは、カルダノカタリスト提案の日本語化で起きる
誤訳と表現揺れを最小化するための **用語制御ルール** です。

対象は専門用語が多い領域です。

- Cardano blockchain
- Midnight
- ガバナンス（Catalyst, DRep, treasury, proposals など）
- クリプト/プロトコル設計

AI翻訳だけでは、専門用語の誤解釈や不自然な日本語が起きやすいため、
人間が定義した辞書で翻訳の振る舞いを制御します。

## 基本方針

- 人間がルールを定義する
- AIは自然な文の構成を担う
- 辞書の意図がAIの判断より優先される
- 回避は「禁止」だが、翻訳は必ず出す
- 英語の言い回しやジョークはAIに任せるが、辞書と矛盾する場合は辞書優先
- 翻訳タスクは拒否しない（教育関連の語彙も許容する）

## 用語分類

### 固定 (keep)

- 固有名詞や技術名を原文のまま保持する
- AIの判断を挟まない

主な対象:

- チーム名
- プロトコル名
- プロジェクト名

### 推奨 (prefer)

- もっとも使いたい訳語を指定する
- 文脈上自然な範囲で優先適用する
- 迷った場合は辞書の推奨を使う

### 回避 (avoid)

- 日本語として不自然、または誤解を招く訳語を禁止する
- 代わりに文脈に合った類義語をAIが選ぶ
- 禁止語があっても翻訳を止めない

例:

- “insight” は 「洞察」 を禁止
- 代替は文脈次第で 「見解」「知見」「理解」 など

## 優先度

1. 固定 (keep): 必ず原文保持
2. 回避 (avoid): 禁止語は出さない
3. 推奨 (prefer): 自然なら優先して採用

英語の言い回しやジョークはAIの裁量で処理しますが、
辞書の意図とズレる場合は辞書を優先します。

## 翻訳フロー（検証なし）

1. keep 用語をプレースホルダに置換
3. AI翻訳（keep / prefer / avoid を指示）
4. プレースホルダを復元

結果の自動検証や再翻訳は行いません。
制御は翻訳時のプロンプトと前処理で完結させます。

## title 辞書（完全一致）

title は AI で翻訳せず、**専用辞書の完全一致**で統一します。

- 一致: 辞書の target を採用
- 不一致: 原文のまま残す

title のタグ（例: `[GENERAL]`）もこの辞書で日本語化します。

## 辞書ファイル構成

- `keep_terms.yaml`: keep（固定）専用
- `guidance_terms.yaml`: prefer / avoid / note 専用
``terms.yaml`` は旧フォーマットのため使用しません。

## terms スキーマ（案）

```
terms:
  - id: cardano
    source: Cardano
    keep: カルダノ
    note: >
      固有名詞。翻訳しない。

  - id: governance
    source: governance
    prefer:
      - ガバナンス
    note: >
      文脈上自然な範囲で優先使用する。

  - id: insight
    source: insight
    avoid:
      - 洞察
    note: >
      文脈に応じて自然な表現を選ぶ。
```

## 非目的

- 汎用翻訳エンジンの開発
- 既存AI翻訳の置き換え
- すべての誤訳を機械的に排除する検証システム

## まとめ

この辞書は「翻訳ガバナンス」のためのルールセットです。
人間が定義した用語制御を優先しつつ、AIの自然な表現力を活かします。

---

# Translation Control Rules for Cardano Catalyst (EN)

## Objective

This translation system is a **terminology control ruleset** designed to
minimize mistranslations and wording drift in Japanese translations of
Cardano Catalyst proposals.

The target domains are highly specialized:

- Cardano blockchain
- Midnight
- Governance (Catalyst, DRep, treasury, proposals, etc.)
- Crypto / protocol design

Because AI translation alone often produces incorrect terminology or
unnatural Japanese, we apply a human-defined dictionary to control behavior.

## Core Principles

- Humans define the rules
- AI is responsible for natural sentence construction
- Dictionary intent overrides AI judgment
- Avoid means "prohibited," but translation must always be produced
- English phrasing and jokes are handled by AI, unless they conflict with the dictionary
- Translation tasks must not be refused (educational vocabulary is allowed)

## Term Categories

### Lock (keep)

- Preserve proper nouns and technical names as-is
- No AI discretion

Primary use:

- Team names
- Protocol names
- Project names

### Prefer (prefer)

- Define the preferred Japanese wording
- Apply when natural in context
- If in doubt, follow the dictionary preference

### Avoid (avoid)

- Prohibit unnatural or misleading Japanese translations
- AI selects context-appropriate alternatives
- Do not block translation even if a forbidden term appears in the source

Example:

- "insight" must not become "洞察"
- Alternatives depend on context (e.g., "見解", "知見", "理解")

## Priority

1. Lock: always preserve original text
2. Avoid: do not output forbidden terms
3. Prefer: use preferred wording when natural

English phrasing and jokes are handled by AI, but dictionary intent wins on conflict.

## Translation Flow (No Validation)

1. Replace keep terms with placeholders
3. AI translation with keep / prefer / avoid instructions
4. Restore placeholders

No automatic validation or re-translation is performed.
Control is enforced during preprocessing and prompting.

## Title Dictionary (Exact Match)

Titles are not translated by AI. They are normalized by an **exact-match title dictionary**.

- Match: use the dictionary target
- No match: keep the original text

Title tags (e.g., `[GENERAL]`) are also translated via this dictionary.

## Dictionary File Layout

- `keep_terms.yaml`: keep-only terms
- `guidance_terms.yaml`: prefer / avoid / note terms
``terms.yaml`` is deprecated and no longer used.

## Terms Schema (Draft)

```
terms:
  - id: cardano
    source: Cardano
    keep: カルダノ
    note: >
      Proper noun. Do not translate.

  - id: governance
    source: governance
    prefer:
      - ガバナンス
    note: >
      Use the preferred term when natural.

  - id: insight
    source: insight
    avoid:
      - 洞察
    note: >
      Choose a natural expression based on context.
```

## Non-Goals

- Building a general-purpose translation engine
- Replacing existing AI translation
- A validation system that mechanically rejects translations

## Summary

This dictionary is a translation governance ruleset.
It prioritizes human-defined terminology control while leveraging AI for fluency.
