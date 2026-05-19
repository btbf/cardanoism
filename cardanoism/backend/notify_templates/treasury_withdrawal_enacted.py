"""treasury_withdrawal_enacted: トレジャリー引き出し施行通知 (User スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "treasury_withdrawal_enacted"


def context(
    *,
    proposal_title: str = "",
    enacted_epoch: int,
    proposal_url: str,
    proposal_count: int = 1,
) -> dict:
    """単一通知 (proposal_count=1) と、同一エポックの集約通知 (>=2) の両方をサポート。

    集約モードでは proposal_title は無視され、proposal_url は一覧ページ (/governance)
    を渡すこと。
    """
    return {
        "proposal_title":  proposal_title or "-",
        "enacted_epoch":   int(enacted_epoch),
        "proposal_url":    proposal_url,
        "proposal_count":  int(proposal_count),
    }


def alt_text(ctx: dict, lang: str) -> str:
    count = ctx.get("proposal_count", 1)
    if count > 1:
        if lang == "ja":
            return f"【Cardanoism】Epoch {ctx['enacted_epoch']} で {count} 件のトレジャリー引き出しが施行"
        return f"[Cardanoism] {count} treasury withdrawals enacted in Epoch {ctx['enacted_epoch']}"
    if lang == "ja":
        return f"【Cardanoism】トレジャリー引き出しが施行: {ctx['proposal_title']}"
    return f"[Cardanoism] Treasury withdrawal enacted: {ctx['proposal_title']}"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.treasury_withdrawal_enacted(
        ctx["proposal_title"], ctx["enacted_epoch"], ctx["proposal_url"], lang=lang,
        proposal_count=ctx.get("proposal_count", 1),
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    count = ctx.get("proposal_count", 1)
    if count > 1:
        if lang == "ja":
            subj = f"Epoch {ctx['enacted_epoch']} でトレジャリー引き出しが {count} 件施行"
            lines = [
                f"件数: {count} 件",
                f"施行エポック: Epoch {ctx['enacted_epoch']}",
            ]
            cta_label = "ガバナンス一覧を開く"
        else:
            subj = f"{count} Treasury Withdrawals Enacted in Epoch {ctx['enacted_epoch']}"
            lines = [
                f"Count: {count}",
                f"Enacted Epoch: {ctx['enacted_epoch']}",
            ]
            cta_label = "Open Governance List"
        return subj, lines, ctx["proposal_url"], cta_label

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
    count = ctx.get("proposal_count", 1)
    if count > 1:
        if lang == "ja":
            return (
                "<b>🏛️ Cardanoism — トレジャリー引き出し施行通知</b>\n"
                "\n"
                f"📊 件数: {count} 件\n"
                f"📅 施行エポック: Epoch {ctx['enacted_epoch']}\n"
                "\n"
                "同一エポックで複数のトレジャリー引き出しが施行されました。\n"
                "\n"
                f'→ <a href="{ctx["proposal_url"]}">ガバナンス一覧を確認する</a>'
            )
        return (
            "<b>🏛️ Cardanoism — Treasury Withdrawals Enacted</b>\n"
            "\n"
            f"📊 Count: {count}\n"
            f"📅 Enacted Epoch: {ctx['enacted_epoch']}\n"
            "\n"
            "Multiple treasury withdrawals enacted in the same epoch.\n"
            "\n"
            f'→ <a href="{ctx["proposal_url"]}">Open governance list</a>'
        )

    if lang == "ja":
        return (
            "<b>🏛️ Cardanoism — トレジャリー引き出し施行通知</b>\n"
            "\n"
            f"📋 提案タイトル: {ctx['proposal_title']}\n"
            f"📅 施行エポック: Epoch {ctx['enacted_epoch']}\n"
            "\n"
            "トレジャリー引き出しが施行されました。\n"
            "\n"
            f'→ <a href="{ctx["proposal_url"]}">提案を確認する</a>'
        )
    return (
        "<b>🏛️ Cardanoism — Treasury Withdrawal Enacted</b>\n"
        "\n"
        f"📋 Proposal Title: {ctx['proposal_title']}\n"
        f"📅 Enacted Epoch: {ctx['enacted_epoch']}\n"
        "\n"
        "A treasury withdrawal has been enacted.\n"
        "\n"
        f'→ <a href="{ctx["proposal_url"]}">View proposal</a>'
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
