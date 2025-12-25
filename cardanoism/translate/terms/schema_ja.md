# Translation Control Dictionary Schema

---

## Schema Definition (YAML)

```yaml
version: <string>

terms:
  - id: <string>
    source: <string>
    keep: <string>
    prefer:
      - <string>
    avoid:
      - <string>
    note: <string>
```

---

## 日本語仕様（Japanese Specification）

### 概要

本ドキュメントは、翻訳時に AI の語彙選択を制御するための  
**翻訳制御辞書（Translation Control Dictionary）**の正式スキーマ仕様を定義します。

本辞書は運用上、`keep_terms.yaml` と `guidance_terms.yaml` の2ファイルに分割して管理します。

本辞書の目的は以下のとおりです。

- 英語表現を起点として翻訳方針を制御する
- 用語の一貫性と安定性を保つ
- 不自然な訳語を避ける
- 固有名詞は固定して翻訳しない

本スキーマは **翻訳結果の検査やエラー判定を目的としません**。  
翻訳結果は常に確定値として保存されることを前提とします。

---

### ルート要素

#### `version`（必須）

```yaml
version: 0.1
```

- スキーマバージョン
- 破壊的変更が入る場合は更新する

---

#### `terms`（必須）

- 翻訳制御定義の配列
- **1エントリ = 1つの英語トリガー語（または概念）**

---

### Term オブジェクト

#### `id`（必須）

```yaml
id: insight
```

- 辞書内で一意な識別子
- DB・API・ログ用途
- 表示目的では使用しない

---

#### `keep`（任意）

```yaml
keep: ステーキング
```

- 翻訳前に該当英語を `__TERM_xxx__` に置換する
- 翻訳後に必ず `keep` の文字列に復元される
- AI に意味解釈や言い換えをさせない

---

#### `prefer`（任意）

```yaml
prefer:
  - ガバナンス
```

- 翻訳時に **優先して使いたい日本語表現**
- 自動置換・検査は行わない

---

#### `avoid`（任意）

```yaml
avoid:
  - 洞察
```

- 翻訳時に **避けたい日本語表現**
- 自動置換・検査は行わない

#### `source`（必須）

```yaml
source: insight
```

- 翻訳制御の起点となる英語表現
- すべての制御は英語ベースで行う

---

#### `note`（任意）

```yaml
note: >
  Translate naturally depending on context.
  Avoid academic tone.
```

- 翻訳時に AI に渡される補足ガイド
- 文体・トーン・語彙選択の方向性を自然言語で記述
- プロンプト内の「Notes」として使用される

---

### 設計思想

- 用語は人間が制御する
- AI は文脈に合わせて自然な表現を選ぶ
- 翻訳は常に成功し、結果は保存される

> 用語は固定する  
> 表現は文脈に合わせる

---
