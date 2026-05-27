"""drep_compass.questionnaire
DRepマッチング診断 v4: 8 問 5 段階 Likert (8 axis 1:1 マッピング)。

設計方針 (outcome-first):
- 1 質問 = 1 axis = 1 つの観察可能な振る舞い
- 質問は「価値観表明」スタイル (例: 「○○すべきだ」)
- 回答は Likert 5 段階 (強く反対 〜 強く賛成)
- 値マッピング: 1→0.0 / 2→0.25 / 3→0.5 / 4→0.75 / 5→1.0
  (0.0=「その振る舞いに反対」 = DRep の Yes 率低い と一致)

旧 v3.x の「対立構造の左右」「補完問」「重複軸」を全廃。
全 axis が独立。
"""
from __future__ import annotations

from dataclasses import dataclass

from cardanoism.backend.drep_compass import config


@dataclass(frozen=True)
class Question:
    q_id: str             # 内部 ID (axis 名と同じ。1:1 マッピング)
    i18n_key: str         # 質問本文 i18n キー (drep_match_q_<key>)
    axes: tuple[str, ...] # この問が影響する axis 群 (v4 では常に 1 つ)
    # 補助情報 i18n キー (質問カードに表示)
    context_i18n_key: str  # 論点 (賛否の対立構造の解説)
    pros_i18n_key:    str  # 賛成派の主張 (改行区切りの bullet 群)
    cons_i18n_key:    str  # 反対派の主張 (同上)


def _q(q_id: str, axis: str) -> Question:
    """q_id = axis 名で 1:1 マッピング (v4)。"""
    return Question(
        q_id=q_id,
        i18n_key=f"drep_match_q_{q_id}",
        axes=(axis,),
        context_i18n_key=f"drep_match_q_{q_id}_context",
        pros_i18n_key=f"drep_match_q_{q_id}_pros",
        cons_i18n_key=f"drep_match_q_{q_id}_cons",
    )


# 8 問 / 8 axis。q_id = axis 名で 1:1。
QUESTIONS: tuple[Question, ...] = (
    _q("large_treasury",       "large_treasury"),
    _q("incumbent_org",        "incumbent_org"),
    _q("new_team",             "new_team"),
    _q("technical",            "technical"),
    _q("adoption",             "adoption"),
    _q("marketing",            "marketing"),
    _q("protocol_change",      "protocol_change"),
    _q("rationale_disclosure", "rationale_disclosure"),
)

QUESTION_BY_ID: dict[str, Question] = {q.q_id: q for q in QUESTIONS}
QUESTION_TOTAL: int = len(QUESTIONS)


def answer_to_value(answer: int) -> float:
    """5 段階 Likert 回答を 0.0〜1.0 のスコアに変換。

    1 = 強く反対     → 0.0
    2 = やや反対     → 0.25
    3 = 中立 / 迷う  → 0.5
    4 = やや賛成     → 0.75
    5 = 強く賛成     → 1.0

    マッピング根拠:
    - 「賛成」= その振る舞いに価値を見いだす = DRep の Yes 率高い (1.0) と一致
    - 「反対」= その振る舞いを望まない = DRep の Yes 率低い (0.0) と一致
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

    v4 では q_id = axis 名なので、答えがそのまま axis 値に対応。
    重要 (importance) に含まれる q_id の axis は重み 1.5、その他 1.0。
    """
    important_set = set(importance or [])
    if len(important_set) > config.MAX_IMPORTANT_AXES:
        important_set = set((importance or [])[:config.MAX_IMPORTANT_AXES])

    user_vector: dict[str, float] = {}
    axis_weights: dict[str, float] = {}

    for q in QUESTIONS:
        if q.q_id not in answers:
            continue
        v = answer_to_value(answers[q.q_id])
        is_important = q.q_id in important_set
        weight = (config.WEIGHT_IMPORTANT
                  if is_important else config.WEIGHT_NORMAL)
        for axis in q.axes:
            user_vector[axis] = v
            axis_weights[axis] = weight

    return user_vector, axis_weights
