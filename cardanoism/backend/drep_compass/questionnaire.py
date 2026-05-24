"""drep_compass.questionnaire
DRep委任コンパス 10 問アンケート定義 (5-Likert)。

spec 第 5 節「ユーザーアンケート」を厳守。
i18n キーは UI 側で参照。本モジュールは axis マッピングと変換ロジックのみ。
"""
from __future__ import annotations

from dataclasses import dataclass

from cardanoism.backend.drep_compass import config


@dataclass(frozen=True)
class Question:
    q_id: str             # 内部 ID (q1..q10)
    i18n_key: str         # AuthState.t[i18n_key] で取れる質問文キー
    axes: tuple[str, ...] # この問が影響する axis 群
    # 補助情報 i18n キー (質問本文の下に常時表示する論点解説)
    context_i18n_key: str  # 📖 論点の背景
    pros_i18n_key: str     # ✅ 支持する根拠 (改行区切り bullet)
    cons_i18n_key: str     # ⚠️ 慎重な根拠 (改行区切り bullet)
    # value = (answer - 1) / 4 で 0.0〜1.0 にスケール。
    # 同じ axis に複数問が紐づく場合は平均を取る (questionnaire 側の責任)。


def _q(q_id: str, key_base: str, axes: tuple[str, ...]) -> Question:
    return Question(
        q_id=q_id,
        i18n_key=f"drep_match_q_{key_base}",
        axes=axes,
        context_i18n_key=f"drep_match_q_{key_base}_context",
        pros_i18n_key=f"drep_match_q_{key_base}_pros",
        cons_i18n_key=f"drep_match_q_{key_base}_cons",
    )


QUESTIONS: tuple[Question, ...] = (
    _q("q1",  "treasury_kpi",             ("treasury_discipline", "transparency_focus")),
    _q("q2",  "growth_investment",        ("growth_investment",)),
    _q("q3",  "technical_priority",       ("technical_foundation",)),
    _q("q4",  "ecosystem_expansion",      ("ecosystem_expansion", "growth_investment")),
    _q("q5",  "marketing_support",        ("marketing_support",)),
    _q("q6",  "institutional_continuity", ("institutional_continuity",)),
    _q("q7",  "decentralized_allocation", ("decentralized_allocation",)),
    _q("q8",  "protocol_conservatism",    ("protocol_conservatism",)),
    _q("q9",  "protocol_innovation",      ("protocol_innovation",)),
    _q("q10", "reasoning_disclosure",     ("reasoning_disclosure",)),
)

QUESTION_BY_ID: dict[str, Question] = {q.q_id: q for q in QUESTIONS}
QUESTION_TOTAL: int = len(QUESTIONS)


def answer_to_value(answer: int) -> float:
    """1〜5 のリッカート回答を 0.0〜1.0 のスコアに変換。

    1 = 全くそう思わない → 0.0
    5 = 強くそう思う     → 1.0
    """
    try:
        a = int(answer)
    except (TypeError, ValueError):
        return 0.5  # 不正値は中立扱い
    if a < 1:
        a = 1
    elif a > 5:
        a = 5
    return (a - 1) / 4.0


def build_user_vector(
    answers: dict[str, int],
    importance: list[str] | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """ユーザー回答から (axis -> value, axis -> weight) を生成。

    - 同じ axis に複数問が紐づく場合は value の平均。
    - importance に含まれる q_id の axis は weight=1.5、その他 1.0。
      ただし 1 axis が複数問にまたがる場合、importance に含まれる問が
      1 つでもあれば WEIGHT_IMPORTANT を採用。

    importance は最大 config.MAX_IMPORTANT_AXES 個まで (それ以上は無視)。
    """
    important_set = set(importance or [])
    if len(important_set) > config.MAX_IMPORTANT_AXES:
        # 多すぎる場合は順序を保って前から N 個まで
        important_set = set((importance or [])[:config.MAX_IMPORTANT_AXES])

    axis_values: dict[str, list[float]] = {}
    axis_weights: dict[str, float] = {}

    for q in QUESTIONS:
        if q.q_id not in answers:
            continue  # 未回答はスキップ
        v = answer_to_value(answers[q.q_id])
        is_important = q.q_id in important_set
        weight = (config.WEIGHT_IMPORTANT
                  if is_important else config.WEIGHT_NORMAL)
        for axis in q.axes:
            axis_values.setdefault(axis, []).append(v)
            # 重要扱いの問が 1 つでもあれば axis weight も重要に
            cur = axis_weights.get(axis, config.WEIGHT_NORMAL)
            axis_weights[axis] = max(cur, weight)

    user_vector = {a: (sum(vs) / len(vs)) for a, vs in axis_values.items()}
    return user_vector, axis_weights
