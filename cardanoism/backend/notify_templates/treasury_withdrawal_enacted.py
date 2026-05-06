"""treasury_withdrawal_enacted: トレジャリー引き出し施行通知 (User スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "treasury_withdrawal_enacted"


def context(
    *,
    proposal_title: str,
    enacted_epoch: int,
    proposal_url: str,
) -> dict:
    return {
        "proposal_title": proposal_title or "-",
        "enacted_epoch":  int(enacted_epoch),
        "proposal_url":   proposal_url,
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】トレジャリー引き出しが施行: {ctx['proposal_title']}"
    return f"[Cardanoism] Treasury withdrawal enacted: {ctx['proposal_title']}"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.treasury_withdrawal_enacted(
        ctx["proposal_title"], ctx["enacted_epoch"], ctx["proposal_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = "トレジャリー引き出しが施行されました"
        lines = [
            f"タイトル: {ctx['proposal_title']}",
            f"施行エポック: Epoch {ctx['enacted_epoch']}",
        ]
        cta_label = "提案を開く"
    else:
        subj = "Treasury Withdrawal Enacted"
        lines = [
            f"Title: {ctx['proposal_title']}",
            f"Enacted Epoch: {ctx['enacted_epoch']}",
        ]
        cta_label = "Open Proposal"
    return subj, lines, ctx["proposal_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return (
            f"🏛️ <b>トレジャリー引き出しが施行</b>\n"
            f"タイトル: {ctx['proposal_title']}\n"
            f"施行エポック: Epoch {ctx['enacted_epoch']}\n"
            f"{ctx['proposal_url']}"
        )
    return (
        f"🏛️ <b>Treasury Withdrawal Enacted</b>\n"
        f"Title: {ctx['proposal_title']}\n"
        f"Enacted Epoch: {ctx['enacted_epoch']}\n"
        f"{ctx['proposal_url']}"
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
