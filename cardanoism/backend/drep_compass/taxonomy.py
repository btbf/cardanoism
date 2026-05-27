"""drep_compass.taxonomy
DRepマッチング診断 v3 の 6 axis 定義のみを保持する。

v2 (7 axis: protocol / transparency 含む) は廃止。
- protocol: 「内容を吟味した上での Yes/No」と「機械的賛成」を区別できず除外
- transparency: 提案側の KPI 厳格度を測る軸として識別困難で除外
代わりに rationale axis を追加し、DRep の投票理由公開率を独立軸として測る。

6 axis:
  1. treasury  : トレジャリ姿勢     (0=攻め / 1=守り)
  2. priority  : 重視領域           (0=技術基盤 / 1=実利用)
  3. org       : 組織のあり方       (0=既存組織 / 1=分散)
  4. risk      : リスク許容         (0=大胆 / 1=慎重)
  5. marketing : マーケティング      (0=推進 / 1=抑制)
  6. rationale : 投票理由の公開      (0=非公開 OK / 1=必ず公開、新軸)

全 axis は 0.0〜1.0 (中央 0.5)。
ユーザー回答も DRep プロファイルも同じスケール。

axis のスコア算出方法は 2 種類:
  - GA tag 集計型 (treasury / priority / org / risk / marketing):
      GA に AI が付けた axis_tags × DRep の Yes/No 投票を集計
  - DRep プロパティ直接型 (rationale):
      DRep の reasoning_disclosure_rate (rationale 文を書いた投票 / 全投票) をそのまま score
"""
from __future__ import annotations


# ── 6 axis 定義 ───────────────────────────────────────────────
AXES: tuple[str, ...] = (
    "treasury",
    "priority",
    "org",
    "risk",
    "marketing",
    "rationale",
)
AXES_SET: frozenset[str] = frozenset(AXES)


def is_valid_axis(axis: str) -> bool:
    return axis in AXES_SET


# ── 各 axis の両端ラベル (i18n キー suffix と対応) ──────────
# UI で 0.0 (左) / 1.0 (右) の絵文字とテキストを引くときに使う
# i18n キー形式:
#   drep_match_axis_<axis>_left   ← 0.0 寄りラベル (例: 攻め)
#   drep_match_axis_<axis>_right  ← 1.0 寄りラベル (例: 守り)
#   drep_match_axis_<axis>        ← 軸名 (例: トレジャリ姿勢)
AXIS_KEYS: tuple[str, ...] = AXES
