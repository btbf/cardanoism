"""
ai_client.py
OpenAI Chat Completions API のラッパー。GA AI 分析（憲法準拠 + VISION 2030）の
LLM 呼び出しと JSON 出力パースを担当する。

公開関数:
    analyze_proposal(proposal, constitution_text) -> AnalysisResult
        1 つの GA を分析し、JSON 結果と使用 token / コストを返す。

設計方針:
- model 固定 (gpt-5.4-mini) で運用。
- 憲法本文 + システム指示を system role に配置。OpenAI の自動プロンプトキャッシュ
  に乗せて複数 GA で再利用される。
- 429 / 5xx は exponential backoff (5/10/20/40s) で 4 回リトライ。
- response_format={"type":"json_object"} で JSON 出力を強制。
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ─── 定数 ──────────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "gpt-5.4-mini"

# gpt-5.4-mini の料金 (USD per 1M tokens) — OpenAI 公式 pricing
_PRICE_INPUT_PER_MTOK = 0.75
_PRICE_CACHED_INPUT_PER_MTOK = 0.075
_PRICE_OUTPUT_PER_MTOK = 4.50

# リトライ設定
_RETRY_BACKOFFS_SEC: tuple[int, ...] = (5, 10, 20, 40)
_MAX_OUTPUT_TOKENS = 4096


# ─── 結果型 ────────────────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    """analyze_proposal の戻り値。LLM 出力 JSON とメタデータを保持する。"""

    payload: dict[str, Any]            # JSON でパース済みの分析結果
    model_id: str                      # 実際に使ったモデル ID
    tokens_input: int                  # 入力トークン (cached を含む合計)
    tokens_cached_input: int           # うちキャッシュヒットしたトークン数
    tokens_output: int                 # 出力トークン
    cost_usd: float                    # 合算コスト（USD）
    raw_text: str = field(repr=False)  # 生のレスポンス本文（デバッグ用）


# ─── 内部: SDK クライアント ────────────────────────────────────────────────────

_client = None  # 遅延初期化


def _get_client():
    """openai.OpenAI を遅延初期化。SDK 未インストール時はわかりやすく落とす。"""
    global _client
    if _client is not None:
        return _client
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "openai SDK is not installed. Run: pip install openai"
        ) from e

    api_key = os.getenv("GPT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GPT_API_KEY (or OPENAI_API_KEY) is not set")
    _client = OpenAI(api_key=api_key)
    return _client


# ─── 内部: コスト計算 ──────────────────────────────────────────────────────────

def _compute_cost(
    tokens_input: int,
    tokens_cached_input: int,
    tokens_output: int,
) -> float:
    non_cached = max(0, tokens_input - tokens_cached_input)
    return (
        non_cached * _PRICE_INPUT_PER_MTOK
        + tokens_cached_input * _PRICE_CACHED_INPUT_PER_MTOK
        + tokens_output * _PRICE_OUTPUT_PER_MTOK
    ) / 1_000_000


# ─── 内部: メッセージ送信 + リトライ ───────────────────────────────────────────

def _send_with_retry(
    client,
    *,
    model: str,
    system_text: str,
    user_text: str,
    max_tokens: int,
):
    """rate limit / 5xx を exponential backoff でリトライ。"""
    last_error: Exception | None = None
    for attempt in range(len(_RETRY_BACKOFFS_SEC) + 1):
        try:
            return client.chat.completions.create(
                model=model,
                max_completion_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user_text},
                ],
            )
        except Exception as e:
            last_error = e
            status_code = getattr(e, "status_code", None) or getattr(e, "status", None)
            retryable = False
            if status_code in (429, 500, 502, 503, 504):
                retryable = True
            elif "rate" in str(e).lower() or "overloaded" in str(e).lower() or "timeout" in str(e).lower():
                retryable = True

            if not retryable or attempt >= len(_RETRY_BACKOFFS_SEC):
                raise
            wait = _RETRY_BACKOFFS_SEC[attempt]
            logger.warning(
                "OpenAI API retryable error (attempt %d/%d, wait %ds): %s",
                attempt + 1, len(_RETRY_BACKOFFS_SEC), wait, e,
            )
            time.sleep(wait)
    if last_error:
        raise last_error
    raise RuntimeError("unreachable")


# ─── 内部: プロンプト組み立て ──────────────────────────────────────────────────

# 憲法本文より前に置く固定の指示。OpenAI の自動キャッシュは長めのプレフィクスが
# 共通な時にヒットするので、システムメッセージの先頭で固定文を流し込む構成に揃える。
_SYSTEM_INSTRUCTIONS = """\
You are a research assistant for Cardano governance proposals.
Your job is to produce a structured JSON output that helps Japanese-speaking
voters understand a proposal — NOT to score or judge it.

You MUST NOT output any score, verdict, compliance rating, KPI assessment, or
constitution analysis. Your only outputs are:
1. A neutral plain-text summary of the proposal (Japanese + English).
2. A bullet-list of factual key information extracted from the proposal.
3. A `axis_tags` block that classifies the proposal along 7 intrinsic axes
   (drep-match v3). This is structured TAG classification, not scoring —
   you tag what the proposal IS, you do NOT judge if it's good or bad.

## Per-Type Fact Extraction

`proposal_facts` is a list of {label_ja, label_en, value_ja, value_en} entries
summarizing the most important quantitative or structural facts:

- **TreasuryWithdrawals**: amount, recipient (stake address), purpose,
  duration / period, reporting commitments if any.
- **ParameterChange**: parameter name, current value (if known), proposed value,
  effective epoch.
- **HardForkInitiation**: target protocol version, breaking changes, target epoch.
- **NewCommittee**: member changes (added / removed / replaced), term length,
  effective epoch.
- **NewConstitution**: high-level summary of changes vs current constitution,
  ratification path.
- **InfoAction**: stated goal / topic, intended audience, action requested.
- **NoConfidence**: target body, stated grounds, transition plan if any.

### value_ja / value_en (REQUIRED, both must be filled)

Each fact MUST have BOTH `value_ja` (Japanese) and `value_en` (English).
For numerical / address values that are language-agnostic (e.g., "50,000 ADA",
"stake1xxx..."), set both fields to the same string.
For text values like 用途 / Purpose, write each version naturally in its own
language. Do NOT mix languages in a single field.

Examples:
- {"label_ja": "引き出し額", "label_en": "Amount",
   "value_ja": "50,000 ADA", "value_en": "50,000 ADA"}
- {"label_ja": "用途", "label_en": "Purpose",
   "value_ja": "教育プログラムの運営", "value_en": "Operating educational programs"}
- {"label_ja": "受取先", "label_en": "Recipient",
   "value_ja": "stake1xxx... (Cardanoism 財団)",
   "value_en": "stake1xxx... (Cardanoism Foundation)"}

Use clean Japanese labels in label_ja (e.g., "引き出し額", "受取先", "用途").

## Output Schema (STRICT)

Output ONLY this JSON object with no extra text:

{
  "proposal_summary_ja": "提案の背景 / 目的 / 主な内容 / 期待される効果 / 関係者 を含む詳細な中立要約。300〜500 文字、6〜10 文。",
  "proposal_summary_en": "A detailed neutral summary covering background, purpose, main content, expected outcomes, and stakeholders. 6-10 sentences (~250-450 words).",
  "proposal_facts": [
    {"label_ja": "引き出し額", "label_en": "Amount",
     "value_ja": "50,000 ADA", "value_en": "50,000 ADA"},
    {"label_ja": "受取先", "label_en": "Recipient",
     "value_ja": "stake1xxx... (Cardanoism 財団)",
     "value_en": "stake1xxx... (Cardanoism Foundation)"}
  ],
  "axis_tags": {
    "treasury_size":     "large" | "small" | "n_a",
    "priority":          "technical" | "adoption" | "both" | "n_a",
    "org_recipient":     [array of org tags, possibly empty],
    "protocol_change":   "hard_fork" | "param_change" | "n_a",
    "marketing_purpose": "yes" | "no",
    "kpi_clarity":       "clear" | "unclear" | "n_a",
    "risk_level":        "high" | "low" | "n_a",
    "reasoning": {
      "treasury_size":     "なぜそう判定したか (≤80 chars)",
      "priority":          "...",
      "org_recipient":     "...",
      "protocol_change":   "...",
      "marketing_purpose": "...",
      "kpi_clarity":       "...",
      "risk_level":        "..."
    }
  }
}

## axis_tags Classification Rules (drep-match v3)

### treasury_size
- "large" : Treasury withdrawal で総額 >= 10,000,000 ADA (1000 万 ADA 以上)
- "small" : Treasury withdrawal で総額 < 10,000,000 ADA
- "n_a"   : Treasury 系ではない (ParameterChange / HardFork / InfoAction 等)

### priority (提案の目的軸)
**technical の定義は厳しく**。Input Output (IO / IOG / IOHK) が主導する
コア・プロトコル研究 / 合意層 / 暗号 / Hydra・Mithril・Leios 等の
プロトコル仕様策定・実装、Cardano ノード本体の保守。
IO 公式委託先 (例: Tweag が Peras を契約で実装する) も含む。

- "technical" : 上記の「IO 主導 / 公式委託 のコア R&D / プロトコル / ノード保守」のみ。
                例:
                - Plomin / Chang HardFork (IO リードのプロトコル更新)
                - Leios / Hydra プロトコル仕様策定 (IO)
                - IO+Ensurable Cardano コア保守
                - Tweag による Peras R&D (IO 委託)
                - Mithril / Catalyst Voting プロトコル
- "adoption"  : 上記以外の全ての開発 ・ 実装。例:
                - dApp / DeFi / ウォレット (IO 系列以外の独立チーム)
                - 外部スマートコントラクト言語 (例: Pebble by Harmonic Labs)
                - Hydra を「使う」 dApp (例: DeltaDeFi の DEX)
                - 教育 / トレーニング (実用スキル向上)
                - ユーザー獲得 / 採用拡大 系
                - 開発者向けライブラリ (IO 以外が作るもの)
- "both"      : ほぼ使わない。本当に IO 主導コア R&D + dApp 実用が 50:50 なケースのみ。
- "n_a"       : 以下は priority 軸の対象外 (marketing 軸で扱うため重複を避ける)。
                - イベント / サミット / カンファレンス / スポンサーシップ
                - 啓蒙 / 認知拡大 / 広告 / PR キャンペーン
                - コミュニティ拡大 (一般認知向上目的)
                その他 procedure-only / 抽象的 InfoAction なども n_a。

**判定の鍵**: 「IO 主導 (または公式委託) のコア R&D か」が技術判定。
それ以外の開発はすべて adoption。**外部チームによる独立開発は技術寄りでも adoption** に分類する。

### org_recipient (受益組織を多重 array で。author ではなく実際に予算を受け取る組織)
- "IO"       : Input Output (IOG / IOHK)
- "CF"       : Cardano Foundation
- "Intersect": **実際に予算を Intersect 自身が受領して内部運営に使う場合のみ**。
               以下は "Intersect" に含めない:
                 - Intersect が代理で他組織のために提出している
                 - Intersect が管理 / 取りまとめ / オーケストレーション役割
                 - Intersect が事務局的に予算を流して別組織が実行
               迷ったら "Intersect" は **含めない**。
               (例: 「IO と Ensurable の保守予算を Intersect が管理」→ ["IO", "other"]
                のみ。Intersect は含めない)
- "Emurgo"   : Emurgo
- "Midnight" : Midnight (IO 系列だが別組織扱い)
- "new_team" : Cardano エコシステム内の新興 / 個別開発チーム。
               例: DeFi の DEX チーム、独立 dApp 開発、オープンソース貢献団体
                   (Harmonic Labs / DeltaDeFi / Andamio / Aiken team 等)。
               規模感: Cardano コミュニティ発で、上記 5 大組織よりも小さい。
- "individual": 個人開発者 / フリーランス
- "other"    : Cardano エコシステム外の **既存の大企業** (例: Tweag, Fireblocks,
               Chainlink 等)、または上記 6 区分に明確に当てはまらない既存団体。
               **Cardano 発の新興チームには使わない (それは new_team)**。
- []         : 組織受益が無い (InfoAction、ParameterChange 等)
- 複数該当する場合は ["IO", "CF"] のように複数指定。

### protocol_change
- "hard_fork"   : HardForkInitiation
- "param_change": ParameterChange
- "n_a"         : それ以外

### marketing_purpose
- "yes" : PR / イベント / カンファレンス / 認知拡大 / スポンサーシップが主目的
- "no"  : 開発・運営・研究等の主目的、マーケは副次的または無し

### kpi_clarity
- "clear"  : 明確な KPI、マイルストーン、成果検証手順が記述されている
- "unclear": KPI が抽象的、達成基準不明、報告義務不明
- "n_a"    : 性質上 KPI が適用されない (InfoAction、ParameterChange、HardFork)

### risk_level
- "high" : 実験的 / 未検証技術 / 単一エンティティへの大型出資 / 不確実性大
- "low"  : 既存技術 / 実績ある運営 / 分散実行 / 既存契約継続
- "n_a"  : 評価困難 (InfoAction 等)

### axis_tags 共通原則
- 提案の中身 (title + abstract) から判定する。author 情報には依存しない。
- 表面的なキーワードマッチではなく、提案の意図を理解する。
- 不確かな場合は "n_a" / "unclear" を使うことを恐れない。
- 全フィールド必須。reasoning も全項目必須 (各 ≤80 chars)。

## Summary Writing Guidelines

The proposal_summary should be substantive enough that a Japanese-speaking voter
can understand the proposal WITHOUT reading the full document. Include:

1. 背景 / コンテキスト（なぜこの提案が出されたか）
2. 提案の主旨（何を実行・変更するのか）
3. 主要な数字や条件（期間 / 金額 / 範囲など）
4. 期待される効果や恩恵を受ける関係者
5. 提案文中で言及されている前提条件や制約（あれば）

Aim for 300-500 Japanese characters / 6-10 sentences. Avoid value judgments.

## Hard Rules

- DO NOT include any score, verdict, compliance rating, "concerns", KPI, or
  constitution-article fields. Your role is purely to organize information.
- DO NOT output anything other than the JSON object (no markdown fences, no commentary).
- DO NOT fabricate facts. Only extract what is directly stated in the proposal.
- All Japanese fields must read as natural Japanese, not machine translation.
- proposal_facts entries should be SHORT (each value ≤ ~80 chars). Use 3-7 entries.
  Both value_ja and value_en MUST be present for every entry.
- The proposal_summary should be neutral and descriptive — no positive or
  negative judgment.
- DO NOT include topic_tags or faction labels.
- axis_tags MUST be included exactly as specified in the "axis_tags
  Classification Rules" section above. All 7 axes are required plus reasoning
  for each. No additional axes, no missing axes.
"""


def _build_system_text(constitution_text: str, constitution_ja: str | None = None) -> str:
    """システムメッセージ: 固定指示 + 憲法本文（英語原文 + 任意で日本語訳）。
    プレフィクス（指示部分）が安定していれば OpenAI の自動キャッシュが効く。

    日本語訳が渡された場合、AI は両方を参照し:
      - label_ja / quote_ja → 日本語訳から取得
      - label_en / quote_en → 英語原文から取得
    することで日本人ユーザー向けに自然な表記が出せる。
    """
    parts = [
        _SYSTEM_INSTRUCTIONS,
        "\n\n# Cardano Constitution — Original (English, authoritative)\n\n",
        constitution_text,
    ]
    if constitution_ja and constitution_ja.strip():
        parts.append(
            "\n\n# Cardano Constitution — Japanese Translation (reference)\n\n"
            "The following is a Japanese translation provided for label_ja / quote_ja "
            "field generation. Use it for natural Japanese phrasing, but the English "
            "version above is the authoritative source for evaluation.\n\n"
        )
        parts.append(constitution_ja)
    return "".join(parts)


def _build_proposal_excerpt(proposal: dict[str, Any], max_chars: int = 8000) -> str:
    """proposal dict から AI に渡すテキストを組み立てる。長すぎる場合は切り詰める。"""
    parts: list[str] = []

    title = proposal.get("title") or proposal.get("title_ja") or ""
    parts.append(f"# Title\n{title}")

    ptype = proposal.get("proposal_type", "")
    parts.append(f"# Type\n{ptype}")

    abstract = proposal.get("abstract") or proposal.get("abstract_ja") or ""
    if abstract:
        parts.append(f"# Abstract\n{abstract}")

    motivation = proposal.get("motivation") or proposal.get("motivation_ja") or ""
    if motivation:
        parts.append(f"# Motivation\n{motivation}")

    rationale = proposal.get("rationale") or proposal.get("rationale_ja") or ""
    if rationale:
        parts.append(f"# Rationale\n{rationale}")

    if proposal.get("withdrawal_total_lovelace"):
        ada = int(proposal["withdrawal_total_lovelace"]) // 1_000_000
        parts.append(f"# Withdrawal\n{ada:,} ADA")

    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n... [truncated for length]"
    return text


# ─── 公開エントリポイント ──────────────────────────────────────────────────────

def analyze_proposal(
    proposal: dict[str, Any],
    constitution_text: str,
    *,
    constitution_ja: str | None = None,
    model: str = DEFAULT_MODEL,
) -> AnalysisResult:
    """1 つの GA を分析する。

    proposal:
        governance_actions テーブルから取得した dict。
        最低限 title / proposal_type / abstract のいずれかが必要。
    constitution_text:
        Cardano 憲法本文（プレーンテキスト or Markdown）。
        system message に埋め込み、OpenAI 自動プロンプトキャッシュを期待する。
    model:
        OpenAI モデル ID。デフォルトは gpt-4.1。

    Returns:
        AnalysisResult: 分析結果 JSON + 使用トークン + コスト。

    Raises:
        ValueError: モデル出力から JSON が抽出できない場合。
        RuntimeError: API キー未設定 / SDK 未インストール時。
        openai.APIError: リトライしても回復しない場合。
    """
    client = _get_client()

    system_text = _build_system_text(constitution_text, constitution_ja)
    user_text = _build_proposal_excerpt(proposal)

    response = _send_with_retry(
        client,
        model=model,
        system_text=system_text,
        user_text=user_text,
        max_tokens=_MAX_OUTPUT_TOKENS,
    )

    raw = response.choices[0].message.content or ""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"failed to parse JSON: {e}") from e

    usage = response.usage
    tokens_input = getattr(usage, "prompt_tokens", 0) or 0
    tokens_output = getattr(usage, "completion_tokens", 0) or 0
    # キャッシュヒット token は prompt_tokens_details.cached_tokens に入る
    details = getattr(usage, "prompt_tokens_details", None)
    tokens_cached_input = 0
    if details is not None:
        tokens_cached_input = getattr(details, "cached_tokens", 0) or 0

    cost = _compute_cost(tokens_input, tokens_cached_input, tokens_output)

    return AnalysisResult(
        payload=payload,
        model_id=model,
        tokens_input=tokens_input,
        tokens_cached_input=tokens_cached_input,
        tokens_output=tokens_output,
        cost_usd=cost,
        raw_text=raw,
    )


# ─── DRep委任コンパス用: GA タグ分類 ──────────────────────────────────────────

_COMPASS_TAG_SYSTEM = """\
You are a classification assistant for Cardano governance proposals.

Your job is to assign Cardanoism's proprietary tags to a single Governance
Action (GA) based on its type, title, abstract, motivation and rationale.

Tags are grouped into three families. Pick ONLY from the lists below — do
NOT invent new tags. Multiple tags may apply.

## category (broad topic — what the proposal is about)
- treasury, protocol, governance, constitution, core_development,
  infrastructure, ecosystem, marketing, community, education, event,
  dapp, wallet, defi, other

## attribute (the proposal's properties — scale, target, type of work)
- large_budget, recurring_budget, operational_budget,
  existing_entity, new_team, individual_contributor,
  regional_focus, global_focus, open_source, closed_source,
  public_goods, commercial_product,
  developer_experience, user_adoption, awareness,
  long_term_research, security_related,
  parameter_change, hard_fork, urgent, high_risk

## quality (proposal quality / governance hygiene)
- kpi_defined, kpi_unclear,
  milestone_based, milestone_unclear,
  budget_reasonable, budget_unclear, budget_excessive,
  track_record_strong, track_record_unknown,
  transparency_high, transparency_low,
  accountability_defined, accountability_unclear,
  conflict_of_interest_possible

## Selection rules
- Always include at least one category tag. Use "other" only if no
  category truly applies.
- For TreasuryWithdrawals: always include "treasury". Pick the most
  specific category (marketing / event / education / defi / wallet /
  dapp / infrastructure / community / core_development / ecosystem etc.)
  based on the stated spending purpose.
- For ParameterChange: include "protocol" + "parameter_change".
- For HardForkInitiation: include "protocol" + "hard_fork".
- For NewConstitution / ConstitutionUpdate: include "governance" +
  "constitution".
- For InfoAction / NewCommittee / NoConfidence: include "governance".
- attribute tags: add ones whose conditions are clearly evidenced in the
  text. Skip ambiguous ones. (For example, "open_source" only if a
  GitHub / GitLab / "open source" reference exists.)
- quality tags: pair up — if KPI is clearly defined add "kpi_defined",
  if KPI is mentioned but not actually measurable add "kpi_unclear".
  Likewise for milestone / accountability / transparency / budget.
- Do NOT add value-judgmental tags. The taxonomy explicitly forbids
  labels like "bad_proposal" / "wasteful" / "centralized_bad".

## Output format (STRICT JSON)
Return ONLY this object:

{
  "tags": [
    {"tag": "<one of the lists above>",
     "confidence": 0.0..1.0,
     "rationale": "<short reason in English, ≤120 chars>"},
    ...
  ]
}

- Up to 8 tags total.
- confidence is YOUR own probability of correctness (0.5 = uncertain,
  0.9 = clear evidence in text, 1.0 = derived directly from
  proposal_type).
- Output English-only rationale; no Markdown, no extra prose.
"""


def _build_compass_user_text(proposal: dict[str, Any], max_chars: int = 8000) -> str:
    """compass tag 分類用の user message を組み立てる。"""
    parts: list[str] = []

    title = proposal.get("title") or proposal.get("title_ja") or ""
    parts.append(f"# Title\n{title}")

    ptype = proposal.get("proposal_type", "")
    parts.append(f"# Type\n{ptype}")

    abstract = proposal.get("abstract") or proposal.get("abstract_ja") or ""
    if abstract:
        parts.append(f"# Abstract\n{abstract}")

    motivation = proposal.get("motivation") or proposal.get("motivation_ja") or ""
    if motivation:
        parts.append(f"# Motivation\n{motivation}")

    rationale = proposal.get("rationale") or proposal.get("rationale_ja") or ""
    if rationale:
        parts.append(f"# Rationale\n{rationale}")

    if proposal.get("withdrawal_total_lovelace"):
        ada = int(proposal["withdrawal_total_lovelace"]) // 1_000_000
        parts.append(f"# Withdrawal\n{ada:,} ADA")

    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n... [truncated for length]"
    return text


@dataclass
class CompassTagResult:
    """classify_proposal_tags の戻り値。"""
    tags: list[dict[str, Any]]    # [{tag, confidence, rationale}]
    model_id: str
    tokens_input: int
    tokens_cached_input: int
    tokens_output: int
    cost_usd: float
    raw_text: str = field(repr=False)


def classify_proposal_tags(
    proposal: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 800,
) -> CompassTagResult:
    """1 つの GA に対する Cardanoism独自タグ群を OpenAI で生成する。

    決定性向上のため:
      - response_format=json_object で構造化出力を強制
      - system プロンプトは固定 → OpenAI 自動キャッシュに乗る

    Args:
      proposal: governance_actions row (proposal_type / title / abstract /
                motivation / rationale / withdrawal_total_lovelace を含む dict)

    Returns:
      CompassTagResult。tags は [{tag, confidence, rationale}] の list。
      呼び出し側で taxonomy.is_valid_tag() による検証必須。
    """
    client = _get_client()
    user_text = _build_compass_user_text(proposal)

    response = _send_with_retry(
        client,
        model=model,
        system_text=_COMPASS_TAG_SYSTEM,
        user_text=user_text,
        max_tokens=max_output_tokens,
    )
    raw = response.choices[0].message.content or ""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"compass classify: failed to parse JSON: {e}") from e

    tags_raw = payload.get("tags") or []
    if not isinstance(tags_raw, list):
        tags_raw = []

    # tag フィールドだけは必ず正規化 (空白・小文字)。validation は呼び出し側。
    tags: list[dict[str, Any]] = []
    for t in tags_raw:
        if not isinstance(t, dict):
            continue
        tag = str(t.get("tag") or "").strip().lower()
        if not tag:
            continue
        try:
            conf = float(t.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        rationale = str(t.get("rationale") or "").strip()
        tags.append({"tag": tag, "confidence": conf, "rationale": rationale})

    usage = response.usage
    tokens_input = getattr(usage, "prompt_tokens", 0) or 0
    tokens_output = getattr(usage, "completion_tokens", 0) or 0
    details = getattr(usage, "prompt_tokens_details", None)
    tokens_cached_input = 0
    if details is not None:
        tokens_cached_input = getattr(details, "cached_tokens", 0) or 0
    cost = _compute_cost(tokens_input, tokens_cached_input, tokens_output)

    return CompassTagResult(
        tags=tags,
        model_id=model,
        tokens_input=tokens_input,
        tokens_cached_input=tokens_cached_input,
        tokens_output=tokens_output,
        cost_usd=cost,
        raw_text=raw,
    )


_DREP_PROFILE_SYSTEM = """\
You analyze a Cardano DRep's voting behavior for Cardanoism's "DRep Matching
Diagnostic". You receive the DRep's past votes (Yes/No/Abstain), the
corresponding Governance Action title and abstract, and any voter rationale
the DRep published (CIP-100/108 metadata).

Your job: infer the DRep's tendencies along 7 axes, each scored 0.0..1.0,
and write a neutral one-line summary for delegators.

Do NOT use faction labels (anti-IO, centralized, wasteful, giveaway, etc.).
Use neutral "tends to..." tendency language only.

# 7 axes (all 0.0..1.0, 0.5 = neutral / mixed / no evidence)

- treasury     (0=Aggressive Treasury use / 1=Cautious Treasury use)
  Higher when the DRep votes No on large lump-sum proposals and prefers
  small targeted grants. Lower when they support large bold investments.

- priority     (0=Technical foundation / 1=Real-world usage)
  Lower when DRep supports protocol R&D, security, infrastructure,
  developer tooling. Higher when they support dApps, DeFi, wallets,
  user-adoption and commercial product growth.

- org          (0=Established orgs / 1=Distributed allocation)
  Lower when DRep supports continuing budgets for IO / CF / Intersect /
  Emurgo. Higher when they prefer funding new teams, regions, individual
  contributors and community DAOs.

- protocol     (0=Progressive protocol change / 1=Conservative stability)
  Lower when DRep supports hard forks and parameter changes for new
  features. Higher when they vote No on consensus-affecting changes
  for stability.

- transparency (0=Lenient on disclosure / 1=Strict on disclosure)
  Higher when DRep votes No on proposals lacking KPIs, milestones,
  budget transparency or accountability. Lower when they accept
  proposals based on trust without strict reporting.

- risk         (0=Aggressive risk taking / 1=Cautious risk management)
  Lower when DRep supports experimental, unproven or high-risk
  proposals. Higher when they vote No on speculative or unclear-ROI
  proposals.

- marketing    (0=Pro marketing / 1=Marketing-cautious)
  Lower when DRep supports PR, events, awareness, conferences.
  Higher when they prefer product/dev funding over marketing spend.

# Scoring rules
- 0.5 means neutral, mixed evidence, or no relevant votes.
- Abstain is participation but a weak signal. Move axes only slightly.
- A No vote may signal multiple axes. Use the GA content and rationale
  text to infer which axis the No is really about.
- confidence is per-axis 0.0..1.0. Low confidence when evidence is sparse
  or ambiguous, high confidence when many clear votes + rationale text.

# Output (STRICT JSON only)
{
  "profile":    {"<axis>": 0.0..1.0, ...},   // all 7 axes required
  "confidence": {"<axis>": 0.0..1.0, ...},   // all 7 axes required
  "summary":    "neutral one-sentence description in Japanese",
  "summary_en": "the same description in English (same meaning, single sentence)",
  "evidence":   {"<axis>": [{"proposal_id": "...", "vote": "Yes|No|Abstain",
                              "reason": "..."}], ...}   // optional, may be empty
}

# Output size limits
- evidence: MAX 3 items per axis (pick the strongest signals). Do NOT exceed this cap.
- evidence.reason: MAX 120 chars per item, in Japanese.
- summary    (JA): MAX 80 Japanese characters, single sentence.
- summary_en (EN): MAX 160 ASCII characters, single sentence, same meaning as `summary`.

`summary` and `summary_en` MUST express the same content in the two languages
(e.g., JA: "新興プロジェクトを積極支援し、KPI を厳しく問う傾向" /
 EN: "Tends to back emerging projects while demanding strict KPIs.").
"""


def _build_drep_profile_user_text(payload: dict[str, Any], max_chars: int = 18000) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated for length]"
    return text


@dataclass
class DrepCompassProfileResult:
    profile: dict[str, float]
    confidence: dict[str, float]
    summary: str                            # 1-line neutral description (Japanese)
    summary_en: str                         # 1-line English version of summary
    rationale: dict[str, str]               # 旧 11 axis 用、後方互換のため残置
    evidence: dict[str, list[dict[str, Any]]]
    model_id: str
    tokens_input: int
    tokens_cached_input: int
    tokens_output: int
    cost_usd: float
    raw_text: str = field(repr=False)


def analyze_drep_compass_profile(
    payload: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 4000,
) -> DrepCompassProfileResult:
    """Infer an 11-axis DRep compass profile with AI."""
    client = _get_client()
    user_text = _build_drep_profile_user_text(payload)
    response = _send_with_retry(
        client,
        model=model,
        system_text=_DREP_PROFILE_SYSTEM,
        user_text=user_text,
        max_tokens=max_output_tokens,
    )
    raw = response.choices[0].message.content or ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"drep compass profile: failed to parse JSON: {e}") from e

    def clamp_map(value: Any) -> dict[str, float]:
        out: dict[str, float] = {}
        if not isinstance(value, dict):
            return out
        for k, v in value.items():
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            out[str(k)] = max(0.0, min(1.0, f))
        return out

    profile = clamp_map(parsed.get("profile"))
    confidence = clamp_map(parsed.get("confidence"))
    summary = str(parsed.get("summary") or "")[:500]
    summary_en = str(parsed.get("summary_en") or "")[:500]
    rationale_raw = parsed.get("rationale") if isinstance(parsed.get("rationale"), dict) else {}
    rationale = {str(k): str(v or "")[:1000] for k, v in rationale_raw.items()}
    evidence_raw = parsed.get("evidence") if isinstance(parsed.get("evidence"), dict) else {}
    evidence: dict[str, list[dict[str, Any]]] = {}
    for axis, items in evidence_raw.items():
        if not isinstance(items, list):
            continue
        cleaned: list[dict[str, Any]] = []
        for item in items[:10]:
            if isinstance(item, dict):
                cleaned.append({
                    "proposal_id": str(item.get("proposal_id") or ""),
                    "vote": str(item.get("vote") or ""),
                    "reason": str(item.get("reason") or "")[:500],
                    "source": "ai",
                })
        evidence[str(axis)] = cleaned

    usage = response.usage
    tokens_input = getattr(usage, "prompt_tokens", 0) or 0
    tokens_output = getattr(usage, "completion_tokens", 0) or 0
    details = getattr(usage, "prompt_tokens_details", None)
    tokens_cached_input = getattr(details, "cached_tokens", 0) if details is not None else 0
    cost = _compute_cost(tokens_input, tokens_cached_input, tokens_output)

    return DrepCompassProfileResult(
        profile=profile,
        confidence=confidence,
        summary=summary,
        summary_en=summary_en,
        rationale=rationale,
        evidence=evidence,
        model_id=model,
        tokens_input=tokens_input,
        tokens_cached_input=tokens_cached_input,
        tokens_output=tokens_output,
        cost_usd=cost,
        raw_text=raw,
    )


# ─── DRep v3 サマリ生成 (集計結果から AI が 1 文ナラティブを書く) ─────────────

_DREP_V3_SUMMARY_SYSTEM = """\
あなたは Cardano DRep の投票傾向を 1 文で要約するアシスタントです。
DRep の 7 axis スコア (drep_compass v3 で集計済み) を受け取り、自然な
日本語と英語で「この DRep はどんな投票傾向か」を要約します。

# 7 axis 定義 (score 0.0〜1.0、0.5 = 中立 / 判断材料不足)

- treasury     : 0.0 = 大型 Treasury 支出に積極 (攻め) /
                 1.0 = 大型支出に慎重 (守り)
- priority     : 0.0 = 技術基盤・プロトコル R&D / セキュリティ / 開発者ツール /
                 1.0 = 実利用・dApp / DeFi / 採用拡大
- org          : 0.0 = 既存大組織 (IO / CF / Emurgo / Intersect / Midnight) 支持 /
                 1.0 = 新興チーム / 個別開発者 / 分散的配分支持
- protocol     : 0.0 = 革新 (HardFork / パラメータ変更を歓迎) /
                 1.0 = 安定 (合意層変更に慎重)
- transparency : 0.0 = ゆるめ (信頼ベース) /
                 1.0 = KPI / マイルストーン / 報告義務を厳格に要求
- risk         : 0.0 = 実験的 / 未検証 / 単一エンティティ大型出資 OK /
                 1.0 = 慎重 (既存実績・分散実行優先)
- marketing    : 0.0 = マーケティング / PR / イベント / スポンサーシップ推進 /
                 1.0 = マーケ抑制 (開発・運営優先)

# ルール
- **confidence < 0.3 の axis は無視** (判断材料不足、サマリに含めない)
- score の極端さで言葉の強弱を変える:
    0.0-0.15 or 0.85-1.0 → 「強く X 寄り」
    0.15-0.30 or 0.70-0.85 → 「やや X 寄り」
    0.30-0.40 or 0.60-0.70 → 「X 寄りの傾向」
- 中立 (0.40-0.60) の axis はスキップ
- 信頼度の高い、極端な axis を 2-3 個 選んで自然に統合
- 派閥ラベル (例: anti-IO, 集権派) は使わない。「〜する傾向」「〜寄り」のみ
- JA: 80 文字以内、1 文
- EN: 160 文字以内、1 文 (JA と同じ意味)

# 出力 (STRICT JSON only)

{
  "summary_ja": "新興プロジェクトと革新的なプロトコル変更を支援し、マーケティング支出には慎重な傾向",
  "summary_en": "Tends to back emerging projects and progressive protocol changes while being cautious about marketing spend"
}

# 注意
- 渡されない axis、confidence ゼロの axis は無いものとして扱う
- 全 axis が低信頼の場合は「判断材料が不足しています」と返す:
    {"summary_ja": "投票実績が少なく、傾向の判断材料が不足しています",
     "summary_en": "Limited voting record — insufficient data to determine tendencies"}
"""


@dataclass
class DrepV3SummaryResult:
    """drep-match v3: AI が集計結果から生成した 1 文サマリ。"""
    summary_ja: str
    summary_en: str
    model_id: str
    tokens_input: int
    tokens_cached_input: int
    tokens_output: int
    cost_usd: float


def analyze_drep_v3_summary(
    axes: dict[str, dict[str, float]],
    *,
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 400,
) -> DrepV3SummaryResult:
    """v3 集計結果から 1 文サマリを AI で生成する (axis 定義は system prompt)。

    axes: {axis_name: {"score": 0.0-1.0, "conf": 0.0-1.0}, ...}
          全 7 axis を渡す前提 (中立 / 低信頼は AI 側で除外)。
    """
    client = _get_client()
    user_text = json.dumps({"axes": axes}, ensure_ascii=False)
    response = _send_with_retry(
        client,
        model=model,
        system_text=_DREP_V3_SUMMARY_SYSTEM,
        user_text=user_text,
        max_tokens=max_output_tokens,
    )
    raw = response.choices[0].message.content or ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"drep v3 summary: failed to parse JSON: {e}") from e

    summary_ja = str(parsed.get("summary_ja") or "")[:200]
    summary_en = str(parsed.get("summary_en") or "")[:300]

    usage = response.usage
    tokens_input = getattr(usage, "prompt_tokens", 0) or 0
    tokens_output = getattr(usage, "completion_tokens", 0) or 0
    details = getattr(usage, "prompt_tokens_details", None)
    tokens_cached_input = getattr(details, "cached_tokens", 0) if details is not None else 0
    cost = _compute_cost(tokens_input, tokens_cached_input, tokens_output)

    return DrepV3SummaryResult(
        summary_ja=summary_ja,
        summary_en=summary_en,
        model_id=model,
        tokens_input=tokens_input,
        tokens_cached_input=tokens_cached_input,
        tokens_output=tokens_output,
        cost_usd=cost,
    )
