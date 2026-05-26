"""drep_compass.questionnaire
DRepマッチング診断 (新設計): 9 問の二者択一 + 「迷う」アンケート。

各設問は 1〜2 axis に紐づき、回答は:
  1 (左)   → 0.0  (左端寄り)
  2 (迷う) → 0.5  (中立)
  3 (右)   → 1.0  (右端寄り)

同じ axis に複数問が紐づく場合は平均を取る。
重要 (importance) として最大 3 問選択でき、その axis は重み 1.5。
"""
from __future__ import annotations

from dataclasses import dataclass

from cardanoism.backend.drep_compass import config


@dataclass(frozen=True)
class Question:
    q_id: str             # 内部 ID (q1..q9)
    i18n_key: str         # 質問本文 i18n キー (drep_match_q_<key>)
    axes: tuple[str, ...] # この問が影響する axis 群
    # 補助情報 i18n キー (質問の論点解説)
    context_i18n_key: str  # 📖 論点の背景
    left_i18n_key:    str  # 左ボタン (絵文字 + 短文)
    right_i18n_key:   str  # 右ボタン (絵文字 + 短文)


def _q(q_id: str, key_base: str, axes: tuple[str, ...]) -> Question:
    return Question(
        q_id=q_id,
        i18n_key=f"drep_match_q_{key_base}",
        axes=axes,
        context_i18n_key=f"drep_match_q_{key_base}_context",
        left_i18n_key=f"drep_match_q_{key_base}_left",
        right_i18n_key=f"drep_match_q_{key_base}_right",
    )


# 9 問。各設問は 1〜2 axis に紐づく。
QUESTIONS: tuple[Question, ...] = (
    _q("q1",  "money_use",         ("treasury",)),
    _q("q2",  "investment_target", ("priority",)),
    _q("q3",  "trust_target",      ("org",)),
    _q("q4",  "protocol_change",   ("protocol",)),
    _q("q5",  "accountability",    ("transparency",)),
    _q("q6",  "risk_appetite",     ("risk",)),
    _q("q7",  "marketing_stance",  ("marketing",)),
    _q("q8",  "drep_selection",    ("org",)),         # org の補完問
    _q("q9",  "rationale_value",   ("transparency",)), # transparency の補完問
)

QUESTION_BY_ID: dict[str, Question] = {q.q_id: q for q in QUESTIONS}
QUESTION_TOTAL: int = len(QUESTIONS)


def answer_to_value(answer: int) -> float:
    """1〜3 の二者択一+迷う回答を 0.0〜1.0 のスコアに変換。

    1 = 左 (例: 🚀 攻め)        → 0.0
    2 = 迷う                    → 0.5
    3 = 右 (例: 🛡 守り)        → 1.0
    """
    try:
        a = int(answer)
    except (TypeError, ValueError):
        return 0.5
    if a == 1:
        return 0.0
    if a == 3:
        return 1.0
    return 0.5  # 2 / 不正値 / 未回答 は中立


def build_user_vector(
    answers: dict[str, int],
    importance: list[str] | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """ユーザー回答から (axis -> value, axis -> weight) を生成。

    - 同じ axis に複数問が紐づく場合は value の平均。
    - importance に含まれる q_id の axis は weight=1.5、その他 1.0。
    """
    important_set = set(importance or [])
    if len(important_set) > config.MAX_IMPORTANT_AXES:
        important_set = set((importance or [])[:config.MAX_IMPORTANT_AXES])

    axis_values: dict[str, list[float]] = {}
    axis_weights: dict[str, float] = {}

    for q in QUESTIONS:
        if q.q_id not in answers:
            continue
        v = answer_to_value(answers[q.q_id])
        is_important = q.q_id in important_set
        weight = (config.WEIGHT_IMPORTANT
                  if is_important else config.WEIGHT_NORMAL)
        for axis in q.axes:
            axis_values.setdefault(axis, []).append(v)
            cur = axis_weights.get(axis, config.WEIGHT_NORMAL)
            axis_weights[axis] = max(cur, weight)

    user_vector = {a: (sum(vs) / len(vs)) for a, vs in axis_values.items()}
    return user_vector, axis_weights
