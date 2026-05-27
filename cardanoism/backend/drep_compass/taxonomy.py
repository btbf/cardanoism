"""drep_compass.taxonomy
DRepマッチング診断 v4 の 8 axis 定義。

v4 設計方針 (outcome-first):
- 各 axis = 「観察可能な DRep の振る舞い 1 つ」に 1:1 対応
- 全 axis が独立 (orthogonal) — 重複なし
- ユーザー回答 = Likert 5 段階 (強く反対 〜 強く賛成)
- DRep スコア = 該当する振る舞いの Yes 率 (0.0=低 / 1.0=高)
- ユーザーの「賛成度」と DRep の「Yes 率」が同じスケールで直接比較可能

8 axis:
  1. large_treasury        : 1000万 ADA 超 Treasury 提案への Yes 率
  2. incumbent_org         : 中核 5 組織 (IO/CF/Emurgo/Intersect/Midnight) への Yes 率
  3. new_team              : 新興チーム / 個人開発者への Yes 率
  4. technical             : 技術系 (priority=technical) への Yes 率
  5. adoption              : 採用拡大系 (priority=adoption) への Yes 率
  6. marketing             : マーケ系 (marketing_purpose=yes) への Yes 率
  7. protocol_change       : HF / param 変更への Yes 率
  8. rationale_disclosure  : DRep の rationale 公開率 (直接測定)

全 axis は 0.0〜1.0 (中央 0.5)。
axis のスコア算出方法は 2 種類:
  - GA tag 集計型 (1-7): GA 側 axis_tags × DRep の Yes/No 投票
  - DRep プロパティ直接型 (8): reasoning_disclosure_rate
"""
from __future__ import annotations


# ── 8 axis 定義 (v4) ──────────────────────────────────────────
AXES: tuple[str, ...] = (
    "large_treasury",
    "incumbent_org",
    "new_team",
    "technical",
    "adoption",
    "marketing",
    "protocol_change",
    "rationale_disclosure",
)
AXES_SET: frozenset[str] = frozenset(AXES)


def is_valid_axis(axis: str) -> bool:
    return axis in AXES_SET


# ── 各 axis の両端ラベル (i18n キー suffix と対応) ──────────
# UI で 0.0 (左) / 1.0 (右) のラベルを引くときに使う
# i18n キー形式:
#   drep_match_axis_<axis>_left   ← 0.0 寄りラベル (例: 慎重)
#   drep_match_axis_<axis>_right  ← 1.0 寄りラベル (例: 積極)
#   drep_match_axis_<axis>        ← 軸名 (例: 大型 Treasury 姿勢)
AXIS_KEYS: tuple[str, ...] = AXES
