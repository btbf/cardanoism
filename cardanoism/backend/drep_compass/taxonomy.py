"""drep_compass.taxonomy
DRepマッチング診断 (新設計) の 7 axis 定義のみを保持する。

旧 11 axis / gov_action_tags ベースは廃止。GA タグ付け作業も廃止し、
DRep のプロファイルは AI が rationale を直接読んで生成する形に統一。

7 axis:
  1. treasury   : お財布の使い方     (0=攻め / 1=守り)
  2. priority   : 重視領域           (0=技術基盤 / 1=実利用)
  3. org        : 組織のあり方       (0=既存組織 / 1=分散)
  4. protocol   : プロトコル変更     (0=革新 / 1=安定)
  5. transparency: 説明責任          (0=ゆるめ / 1=厳しめ)
  6. risk       : リスク許容         (0=大胆 / 1=慎重)
  7. marketing  : マーケティング      (0=推進 / 1=抑制)

全 axis は 0.0〜1.0 (中央 0.5)。
ユーザー回答も DRep プロファイルも同じスケール。
"""
from __future__ import annotations


# ── 7 axis 定義 ───────────────────────────────────────────────
AXES: tuple[str, ...] = (
    "treasury",
    "priority",
    "org",
    "protocol",
    "transparency",
    "risk",
    "marketing",
)
AXES_SET: frozenset[str] = frozenset(AXES)


def is_valid_axis(axis: str) -> bool:
    return axis in AXES_SET


# ── 各 axis の両端ラベル (i18n キー suffix と対応) ──────────
# UI で 0.0 (左) / 1.0 (右) の絵文字とテキストを引くときに使う
# i18n キー形式:
#   drep_match_axis_<axis>_left   ← 0.0 寄りラベル (例: 攻め)
#   drep_match_axis_<axis>_right  ← 1.0 寄りラベル (例: 守り)
#   drep_match_axis_<axis>        ← 軸名 (例: お財布の使い方)
AXIS_KEYS: tuple[str, ...] = AXES
