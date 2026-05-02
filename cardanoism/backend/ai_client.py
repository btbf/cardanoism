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
  ]
}

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
