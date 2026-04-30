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
You are an expert analyst evaluating Cardano governance proposals.
Your task is to produce a structured JSON evaluation in the exact schema below.

Evaluate the proposal against:
1. The Cardano Constitution (provided below in this same system message)
2. The Cardano VISION 2030 strategy (5 Pillars):
   - I: Infrastructure & Research Excellence
   - A: Adoption & Utility
   - G: Governance
   - C: Community & Ecosystem Growth
   - E: Ecosystem Sustainability & Resilience
3. The 9 numerical KPIs defined in VISION 2030 (3 Core + 6 Additional Primary).
   For "related_kpis", pick 1-3 most relevant to this proposal and rate impact
   (+ / 0 / -). Use the exact KPI name from the list below; for "target",
   use the exact 2030 target value shown.

   Core KPIs:
     - "Total Value Locked (TVL)" (current: $200M, target: $3B)
     - "Monthly transactions" (current: 800k, target: ≥27M)
     - "Monthly Active Users (MAU)" (current: 100k–300k, target: 1M)

   Additional Primary core KPIs:
     - "Monthly (6 epochs) UpTime" (current: 99.98%, target: 99.98%)
     - "Voting Power distribution of controlling stake" (current: 35 DReps, target: >22 DReps)
     - "Alternative full node clients" (current: 1, target: ≥2)
     - "Annual Protocol Revenue" (current: 3.5M ada, target: ≥16M ada)
     - "DRep participation rate" (target: >70%)
     - "Throughput capacity per day" (current: 300k, target: 3x current)

Output STRICT JSON with this exact schema (no markdown, no extra text):

{
  "constitution": {
    "score": 0-100 integer,
    "verdict_ja": "短い判定（例: 概ね準拠）",
    "verdict_en": "Short verdict (e.g., Mostly Compliant)",
    "summary_ja": "総評（2-3 文）",
    "summary_en": "Overall verdict (2-3 sentences)",
    "articles": [
      {"key": "art2", "label_ja": "第 II 条 — ミッション", "label_en": "Article II — Mission", "score": 0-10 integer, "comment_ja": "...", "comment_en": "..."}
    ],
    "concerns_ja": ["懸念点 1", "懸念点 2"],
    "concerns_en": ["Concern 1", "Concern 2"]
  },
  "pillars": [
    {"key": "I", "score": 0-100, "comment_ja": "...", "comment_en": "..."},
    {"key": "A", "score": 0-100, "comment_ja": "...", "comment_en": "..."},
    {"key": "G", "score": 0-100, "comment_ja": "...", "comment_en": "..."},
    {"key": "C", "score": 0-100, "comment_ja": "...", "comment_en": "..."},
    {"key": "E", "score": 0-100, "comment_ja": "...", "comment_en": "..."}
  ],
  "related_kpis": [
    {"name_ja": "...", "name_en": "...", "target": "...", "impact": "+|0|-", "comment_ja": "...", "comment_en": "..."}
  ]
}

Guidelines:
- Evaluate fairly and conservatively. Do not give high scores without evidence.
- All Japanese fields must be in natural Japanese, not machine translation.
- Concerns should be concrete and actionable, not generic boilerplate.
- related_kpis must contain 1-3 entries (the most relevant KPIs only).
- For "articles": pick 3-6 articles from the constitution that are most relevant to
  this proposal. Use the EXACT topic title from the constitution text, formatted as
  "第 N 条 — トピック名" / "Article N — Topic Name" (e.g., "第 II 条 — ミッション" /
  "Article II — Mission"). Do NOT make up article numbers or titles — use what
  appears verbatim in the constitution provided.
- "key" should be a short slug (e.g., "art2", "art3") matching the article number.
- Output ONLY the JSON object. No markdown fences, no commentary.
"""


def _build_system_text(constitution_text: str) -> str:
    """システムメッセージ: 固定指示 + 憲法本文。
    プレフィクス（指示部分）が安定していれば OpenAI の自動キャッシュが効く。
    """
    return (
        _SYSTEM_INSTRUCTIONS
        + "\n\n# Cardano Constitution (reference)\n\n"
        + constitution_text
    )


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

    system_text = _build_system_text(constitution_text)
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
