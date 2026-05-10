"""drep_unvoted_ga: DRep 本人向け未投票 GA リマインダー (Stake address スコープ)。

4 トリガー（先勝ち、1 GA につき 1 通）:
  - "7d"          : block_time から 7 日経過し未投票
  - "14d"         : block_time から 14 日経過し未投票
  - "pre_ratify"  : drep_yes_pct が批准閾値の 10pt 手前に到達し未投票
  - "near_expire" : expiration まで残り 2 epoch 以下で未投票
"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.i18n import get_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "drep_unvoted_ga"

# trigger key → flex 文言キー
_TRIGGER_LABEL_KEY = {
    "7d":          "drep_unvoted_trigger_7d",
    "14d":         "drep_unvoted_trigger_14d",
    "pre_ratify":  "drep_unvoted_trigger_pre_ratify",
    "near_expire": "drep_unvoted_trigger_near_expire",
}


def _trigger_label(trigger: str, lang: str) -> str:
    return get_flex(lang).get(_TRIGGER_LABEL_KEY.get(trigger, ""), trigger)


def context(*, title: str, proposal_type_label: str, trigger: str,
            nickname: str, proposal_id: str, base_url: str) -> dict:
    return {
        "title":               title,
        "proposal_type_label": proposal_type_label,
        "trigger":             trigger,             # "7d" / "14d" / "50pct"
        "nickname":            nickname,
        "proposal_id":         proposal_id,
        "base_url":            base_url,
        "proposal_url":        f"{base_url}/governance/{proposal_id}" if proposal_id else f"{base_url}/governance",
    }


def alt_text(ctx: dict, lang: str) -> str:
    label = _trigger_label(ctx["trigger"], lang)
    if lang == "ja":
        return f"【Cardanoism】DRep 未投票リマインダー: {ctx['title'] or '-'}（{label}）"
    return f"[Cardanoism] DRep unvoted reminder: {ctx['title'] or '-'} ({label})"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.drep_unvoted_ga(
        title=ctx["title"],
        proposal_type_label=ctx["proposal_type_label"],
        trigger_label=_trigger_label(ctx["trigger"], lang),
        nickname=ctx["nickname"],
        url=ctx["proposal_url"],
        lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    label = _trigger_label(ctx["trigger"], lang)
    title = ctx["title"] or "-"
    if lang == "ja":
        subj = f"DRep 未投票リマインダー: {title}（{label}）"
        lines = [
            f"提案タイトル: {title}",
            f"提案タイプ:  {ctx['proposal_type_label']}",
            f"状況:        {label}",
            f"ウォレット:  {ctx['nickname']}",
            "DRep として、Yes / No / Abstain のいずれかを投票してください。",
        ]
        cta_label = "提案を確認する"
    else:
        subj = f"DRep unvoted reminder: {title} ({label})"
        lines = [
            f"Proposal: {title}",
            f"Type: {ctx['proposal_type_label']}",
            f"Status: {label}",
            f"Wallet: {ctx['nickname']}",
            "As a DRep, please cast your vote (Yes / No / Abstain).",
        ]
        cta_label = "View proposal"
    return subj, lines, ctx["proposal_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    label = _trigger_label(ctx["trigger"], lang)
    title = ctx["title"] or "-"
    if lang == "ja":
        return (
            "<b>🗳️ Cardanoism — DRep 未投票リマインダー</b>\n"
            "\n"
            f"📋 {title}\n"
            f"🏷️ 提案タイプ: {ctx['proposal_type_label']}\n"
            f"⏰ 状況: {label}\n"
            f"💼 {ctx['nickname']}\n"
            "\n"
            "DRep として投票判断を表明しましょう。\n"
            "\n"
            f'→ <a href="{ctx["proposal_url"]}">提案を確認する</a>'
        )
    return (
        "<b>🗳️ Cardanoism — DRep Unvoted Reminder</b>\n"
        "\n"
        f"📋 {title}\n"
        f"🏷️ Type: {ctx['proposal_type_label']}\n"
        f"⏰ Status: {label}\n"
        f"💼 {ctx['nickname']}\n"
        "\n"
        "As a DRep, please cast your vote.\n"
        "\n"
        f'→ <a href="{ctx["proposal_url"]}">View proposal</a>'
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
