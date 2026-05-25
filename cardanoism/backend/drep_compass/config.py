"""drep_compass.config
DRepマッチング診断の設定値。
"""
from __future__ import annotations

# プロファイルアルゴリズム識別子
ANALYSIS_VERSION = "match-v2"

# アンケート定義識別子
QUESTIONNAIRE_VERSION = "match-v2"

# ── マッチング (match.py) ──────────────────────────────────
# 重要マーク済みの問の axis の重み倍率
WEIGHT_IMPORTANT = 1.5
WEIGHT_NORMAL    = 1.0

# ユーザーが「重要」として選べる最大 axis 数
MAX_IMPORTANT_AXES = 3

# マッチ結果の TOP N (default)
DEFAULT_MATCH_LIMIT = 5

# DRep をマッチング対象に残す最低 analyzed_vote_count
# (これより少ない投票履歴の DRep は AI でも傾向が読みづらいため除外)
MIN_ANALYZED_VOTE_COUNT = 3
