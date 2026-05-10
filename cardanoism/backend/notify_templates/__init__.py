"""notify_templates: 統合通知テンプレートシステム

各イベント 1 モジュールで以下を提供する。

  context(...)               → 共通の ctx (dict) を構築
  alt_text(ctx, lang)        → LINE alt / Telegram 冒頭タイトルに使う短文
  render_flex(ctx, lang)     → LINE Flex Bubble (dict)
  render_email(ctx, lang)    → (subject, lines, cta_url, cta_label) のタプル
  render_telegram(ctx, lang) → Telegram HTML 本文 (str)

ディスパッチャ (_dispatcher.deliver) が ctx と template を受け取り、
addr の channel 設定に応じて 3 チャンネルへ送信。

データは 1 回 build → 3 チャンネルで再利用、文言変更は 1 ファイルで完結。
"""
from cardanoism.backend.notify_templates._dispatcher import (
    deliver,
    register,
    merge_user_channels,
    EVENT_TEMPLATES,
)

# テンプレート一覧 (import 時点で各モジュールが register() を呼ぶ)
from cardanoism.backend.notify_templates import epoch_start                  # noqa: F401
from cardanoism.backend.notify_templates import pool_retire                  # noqa: F401
from cardanoism.backend.notify_templates import pool_fee_change              # noqa: F401
from cardanoism.backend.notify_templates import pool_saturation              # noqa: F401
from cardanoism.backend.notify_templates import pool_pledge_shortage         # noqa: F401
from cardanoism.backend.notify_templates import pool_reward_received         # noqa: F401
from cardanoism.backend.notify_templates import pool_epoch_performance       # noqa: F401
from cardanoism.backend.notify_templates import pool_delegation_reminder     # noqa: F401
from cardanoism.backend.notify_templates import drep_new_governance_action   # noqa: F401
from cardanoism.backend.notify_templates import drep_vote                    # noqa: F401
from cardanoism.backend.notify_templates import drep_status_change           # noqa: F401
from cardanoism.backend.notify_templates import drep_delegation_reminder     # noqa: F401
from cardanoism.backend.notify_templates import treasury_withdrawal_enacted  # noqa: F401
from cardanoism.backend.notify_templates import spo_pending_vote             # noqa: F401
from cardanoism.backend.notify_templates import drep_unvoted_ga              # noqa: F401

__all__ = ["deliver", "register", "merge_user_channels", "EVENT_TEMPLATES"]
