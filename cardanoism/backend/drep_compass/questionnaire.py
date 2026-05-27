"""drep_compass.questionnaire
DRepマッチング診断 v3 (Likert): 8 問 5 段階評価アンケート (7 axis 対応)。

各設問は 1〜2 axis に紐づき、回答は 5 段階 Likert:
  1 (強く左) → 0.0
  2 (やや左) → 0.25
  3 (迷う)   → 0.5
  4 (やや右) → 0.75
  5 (強く右) → 1.0

「やや」が入って解像度が倍に。強い意見と弱い意見を区別できる。

同じ axis に複数問が紐づく場合は平均を取る。
重要 (importance) として最大 3 問選択でき、その axis は重み 1.5。
"""
from __future__ import annotations

from dataclasses import dataclass

from cardanoism.backend.drep_compass import config


@dataclass(frozen=True)
class Question:
    q_id: str             # 内部 ID
    i18n_key: str         # 質問本文 i18n キー (drep_match_q_<key>)
    axes: tuple[str, ...] # この問が影響する axis 群
    # 補助情報 i18n キー (質問の論点解説)
    context_i18n_key: str  # 📖 論点の背景
    left_i18n_key:    str  # 左端ラベル (例: 🚀 大胆)
    right_i18n_key:   str  # 右端ラベル (例: 🛡 慎重)


def _q(q_id: str, key_base: str, axes: tuple[str, ...]) -> Question:
    return Question(
        q_id=q_id,
        i18n_key=f"drep_match_q_{key_base}",
        axes=axes,
        context_i18n_key=f"drep_match_q_{key_base}_context",
        left_i18n_key=f"drep_match_q_{key_base}_left",
        right_i18n_key=f"drep_match_q_{key_base}_right",
    )


# 8 問 / 7 axis。v3 Likert (5 段階) で再構成。
# Q2 を Q2a (priority) と Q2b (tech_origin) に分割して 8 問に。
# q_id は v3 初版から番号維持 (gap あり) — 保存済み回答との互換性のため。
QUESTIONS: tuple[Question, ...] = (
    _q("q1",  "money_use",          ("treasury",)),
    _q("q2a", "investment_target",  ("priority",)),     # Q2 分割: 使途
    _q("q2b", "tech_source",        ("tech_origin",)),  # Q2 分割: 新興企業 tech 採用
    _q("q3",  "trust_target",       ("org",)),
    _q("q6",  "risk_appetite",      ("risk",)),
    _q("q7",  "marketing_stance",   ("marketing",)),
    _q("q8",  "drep_selection",     ("org",)),          # org の補完問
    _q("q9",  "rationale_value",    ("rationale",)),    # rationale 単独軸
)

QUESTION_BY_ID: dict[str, Question] = {q.q_id: q for q in QUESTIONS}
QUESTION_TOTAL: int = len(QUESTIONS)


def answer_to_value(answer: int) -> float:
    """1〜5 の Likert 回答を 0.0〜1.0 のスコアに変換。

    1 = 強く左 (例: 🚀 強く 大胆)  → 0.0
    2 = やや左 (例: 🚀 やや 大胆)  → 0.25
    3 = 迷う / 中立                 → 0.5
    4 = やや右 (例: 🛡 やや 慎重)  → 0.75
    5 = 強く右 (例: 🛡 強く 慎重)  → 1.0

    旧 3 段階 (1=左 / 2=迷う / 3=右) の保存済み回答は match-v3.1 で
    別 questionnaire_version になるので混在しない (config 参照)。
    """
    try:
        a = int(answer)
    except (TypeError, ValueError):
        return 0.5
    return {1: 0.0, 2: 0.25, 3: 0.5, 4: 0.75, 5: 1.0}.get(a, 0.5)


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
