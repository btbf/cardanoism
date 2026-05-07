"""pool_delegation_reminder: プール委任長期リマインダー (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "pool_delegation_reminder"


def context(*, pool_name: str, milestone: int, apy: float | None,
            nickname: str, base_url: str) -> dict:
    return {
        "pool_name": pool_name,
        "milestone": int(milestone),
        "apy":       apy,
        "nickname":  nickname,
        "base_url":  base_url,
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】委任から{ctx['milestone']}日が経過しました。委任先プールを確認しましょう"
    return f"[Cardanoism] {ctx['milestone']} days since delegation. Please check your pool."


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.pool_delegation_reminder(
        ctx["pool_name"], ctx["milestone"], ctx["apy"],
        ctx["nickname"], ctx["base_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"委任から{ctx['milestone']}日が経過しました。委任先プールを確認しましょう"
        lines = [
            f"ウォレット: {ctx['nickname']}",
            f"委任先プール: {ctx['pool_name']}",
            f"委任から {ctx['milestone']} 日が経過しました。委任先プールの状態を確認することをお勧めします。",
        ]
        cta_label = "マイページを開く"
    else:
        subj = f"{ctx['milestone']} days since delegation. Please check your pool."
        lines = [
            f"Wallet: {ctx['nickname']}",
            f"Pool: {ctx['pool_name']}",
            f"{ctx['milestone']} days have passed since delegation. We recommend reviewing your pool.",
        ]
        cta_label = "Open MyPage"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    mypage_url = f"{ctx['base_url']}/mypage?tab=stake"
    if lang == "ja":
        return (
            "<b>🔔 Cardanoism — プール委任リマインダー</b>\n"
            "\n"
            f"🏊 {ctx['pool_name']}\n"
            f"📅 委任から {ctx['milestone']} 日経過\n"
            f"💼 {ctx['nickname']}で委任中\n"
            "\n"
            "委任先プールの状態を確認しましょう。\n"
            "\n"
            f'→ <a href="{mypage_url}">マイページで委任先を確認</a>'
        )
    return (
        "<b>🔔 Cardanoism — Pool Delegation Reminder</b>\n"
        "\n"
        f"🏊 {ctx['pool_name']}\n"
        f"📅 {ctx['milestone']} days since delegation\n"
        f"💼 Delegated from {ctx['nickname']}\n"
        "\n"
        "Please review the status of your pool.\n"
        "\n"
        f'→ <a href="{mypage_url}">Check delegation on MyPage</a>'
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
