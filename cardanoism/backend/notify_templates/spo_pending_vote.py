"""spo_pending_vote: SPO 投票対象 GA 提出通知 (Stake address スコープ、SPO のみ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "spo_pending_vote"


def context(*, action_label: str, base_url: str) -> dict:
    return {
        "action_label": action_label,
        "base_url":     base_url,
        "gov_url":      f"{base_url}/governance",
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】SPO 投票対象の新ガバナンスアクション: {ctx['action_label']}"
    return f"[Cardanoism] New SPO-eligible governance action: {ctx['action_label']}"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.spo_pending_vote(ctx["action_label"], ctx["gov_url"], lang=lang)


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"SPO 投票対象の新ガバナンスアクション: {ctx['action_label']}"
        lines = [
            f"SPO が投票可能な新しいガバナンスアクション（{ctx['action_label']}）が提出されました。",
            "あなたのプールに代わって投票することを検討してください。",
        ]
        cta_label = "ガバナンスを確認"
    else:
        subj = f"New SPO-eligible governance action: {ctx['action_label']}"
        lines = [
            f"A new governance action ({ctx['action_label']}) eligible for SPO voting has been submitted.",
            "Consider casting a vote on behalf of your pool.",
        ]
        cta_label = "Check Governance"
    return subj, lines, ctx["gov_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return (
            f"👑 <b>SPO 投票対象 GA</b>\n"
            f"種類: {ctx['action_label']}\n"
            f"プールに代わって投票を検討してください。\n"
            f"{ctx['gov_url']}"
        )
    return (
        f"👑 <b>SPO-eligible GA</b>\n"
        f"Type: {ctx['action_label']}\n"
        f"Consider casting a vote on behalf of your pool.\n"
        f"{ctx['gov_url']}"
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
