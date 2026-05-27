"""drep_compass.config
DRepマッチング診断の設定値。
"""
from __future__ import annotations

# プロファイルアルゴリズム識別子
# v3: AI 推論を廃止し、GA per-axis tags (governance_ai_analysis.axis_tags_json)
#     を集計してスコアを算出する。透明性と再現性を確保。
ANALYSIS_VERSION = "match-v3"

# アンケート定義識別子
# v3: 7 問 / 6 axis (Q4 protocol, Q5 transparency 削除、rationale 軸追加)。
# match-v2 の保存済み回答とは互換性が無いため、bump して pre-fill を抑止する。
QUESTIONNAIRE_VERSION = "match-v4"

# ── マッチング (match.py) ──────────────────────────────────
# 重要マーク済みの問の axis の重み倍率
WEIGHT_IMPORTANT = 1.5
WEIGHT_NORMAL    = 1.0

# ユーザーが「重要」として選べる最大 axis 数
MAX_IMPORTANT_AXES = 3

# マッチ結果の TOP N (default)
DEFAULT_MATCH_LIMIT = 10

# DRep をマッチング対象に残す最低 analyzed_vote_count
# (これより少ない投票履歴の DRep は AI でも傾向が読みづらいため除外)
MIN_ANALYZED_VOTE_COUNT = 5

# ── マッチング品質フィルタ (quality filter) ────────────────
# amount (委任量) ではなく以下の品質シグナルで母集団を絞る:
#   - 投票実績がそれなりにある
#   - 投票理由を一定割合で公開している (説明責任)
#   - CIP-119 自己紹介がある (本人確認情報がある)
# 影響力 (amount) に依存せず、liquid democracy 的に「質」で並べる。
MIN_REASONING_DISCLOSURE_RATE = 0.30   # 投票理由公開率の下限
REQUIRE_GIVEN_NAME            = True   # True なら CIP-119 given_name 必須
