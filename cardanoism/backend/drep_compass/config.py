"""drep_compass.config
GA 分類・DRep プロファイル計算・マッチング計算のしきい値を集約する設定モジュール。

しきい値はここに集約して、後から検証ベースで調整できるようにする。
DB 化したい場合は config テーブルに切り出すこと。
"""
from __future__ import annotations

# プロファイルアルゴリズム識別子。compute ロジックを変えたら bump する。
ANALYSIS_VERSION = "compass-mvp-v1"

# アンケート定義識別子。問の入れ替え / wording 変更で bump する。
QUESTIONNAIRE_VERSION = "compass-mvp-v1"

# ── 1. GA 分類 (classifier) ─────────────────────────────────
# large_budget / high_risk 判定の lovelace しきい値
LARGE_BUDGET_LOVELACE = 5_000_000 * 1_000_000      # 5M ADA
HIGH_RISK_LOVELACE    = 20_000_000 * 1_000_000     # 20M ADA

# ── 2. DRep プロファイル (profile.py) ───────────────────────
# axis あたり confidence = min(1.0, related_vote_count / 5)
CONFIDENCE_VOTE_TARGET = 5

# rationale が付いた投票が 1 件以上あれば axis confidence +0.1 (キャップ 1.0)
RATIONALE_CONFIDENCE_BONUS = 0.10

# 1 投票が 1 axis に与える raw score の基本増分 (Yes=+, No=-)
# (タグごとに係数が乗る — profile.py 内で定義)
BASE_STEP = 1.0

# normalized_score = (raw_score + 1) / 2 を [0,1] にクランプ後、
# final_score = 0.5 * (1 - confidence) + normalized * confidence
NEUTRAL_MIDPOINT = 0.5

# ── 3. マッチング (match.py) ────────────────────────────────
# 重要項目に選ばれた axis の重み (1.0 = 通常、1.5 = 重要)
WEIGHT_IMPORTANT = 1.5
WEIGHT_NORMAL    = 1.0

# confidence がこれ未満の axis は除外
LOW_CONFIDENCE_THRESHOLD = 0.20

# 表示用: confidence が低い軸を「低信頼」と表示するしきい値 (除外より緩い)
LOW_CONFIDENCE_DISPLAY = 0.40

# ユーザーが「重要」として選べる最大数
MAX_IMPORTANT_AXES = 3

# マッチ結果の TOP N (default)
DEFAULT_MATCH_LIMIT = 5

# DRep をマッチング対象に残す最低 analyzed_vote_count
# Cardano governance は GA 数が少ないため、当面は緩く 3 に設定。
# 投票実績が増えてきたら 5 に戻す。
MIN_ANALYZED_VOTE_COUNT = 3
