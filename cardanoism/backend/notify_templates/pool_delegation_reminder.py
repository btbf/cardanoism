"""pool_delegation_reminder: プール委任長期リマインダー (Stake address スコープ)。

milestone == 365 は「365 日以上委任しています」表記、それ未満は「N 日経過」表記。
"""
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


def _phrase(milestone: int, lang: str) -> str:
    """milestone に応じた経過表現を返す。365 のときは「以上」表記。"""
    if milestone >= 365:
        return f"{milestone} 日以上" if lang == "ja" else f"{milestone}+ days"
    return f"{milestone} 日" if lang == "ja" else f"{milestone} days"


def alt_text(ctx: dict, lang: str) -> str:
    phrase = _phrase(ctx["milestone"], lang)
    if lang == "ja":
        if ctx["milestone"] >= 365:
            return f"【Cardanoism】{phrase}委任しています。委任先プールを確認しましょう"
        return f"【Cardanoism】委任から{phrase}が経過しました。委任先プールを確認しましょう"
    if ctx["milestone"] >= 365:
        return f"[Cardanoism] You've been delegated for {phrase}. Please check your pool."
    return f"[Cardanoism] {phrase} since delegation. Please check your pool."


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.pool_delegation_reminder(
        ctx["pool_name"], ctx["milestone"], ctx["apy"],
        ctx["nickname"], ctx["base_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    phrase = _phrase(ctx["milestone"], lang)
    if lang == "ja":
        if ctx["milestone"] >= 365:
            subj = f"{phrase}委任しています。委任先プールを確認しましょう"
            body_line = f"{phrase}委任が継続しています。委任先プールの状態を確認することをお勧めします。"
        else:
            subj = f"委任から{phrase}が経過しました。委任先プールを確認しましょう"
            body_line = f"委任から {phrase}が経過しました。委任先プールの状態を確認することをお勧めします。"
        lines = [
            f"ウォレット: {ctx['nickname']}",
            f"委任先プール: {ctx['pool_name']}",
            body_line,
        ]
        cta_label = "マイページを開く"
    else:
        if ctx["milestone"] >= 365:
            subj = f"You've been delegated for {phrase}. Please check your pool."
            body_line = f"You have been delegated for {phrase}. We recommend reviewing your pool."
        else:
            subj = f"{phrase} since delegation. Please check your pool."
            body_line = f"{phrase} have passed since delegation. We recommend reviewing your pool."
        lines = [
            f"Wallet: {ctx['nickname']}",
            f"Pool: {ctx['pool_name']}",
            body_line,
        ]
        cta_label = "Open MyPage"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    mypage_url = f"{ctx['base_url']}/mypage?tab=stake"
    phrase = _phrase(ctx["milestone"], lang)
    if lang == "ja":
        elapsed_line = (
            f"📅 {phrase}委任継続中" if ctx["milestone"] >= 365 else f"📅 委任から {phrase}経過"
        )
        return (
            "<b>🔔 Cardanoism — プール委任リマインダー</b>\n"
            "\n"
            f"🏊 {ctx['pool_name']}\n"
            f"{elapsed_line}\n"
            f"💼 {ctx['nickname']}で委任中\n"
            "\n"
            "委任先プールの状態を確認しましょう。\n"
            "\n"
            f'→ <a href="{mypage_url}">マイページで委任先を確認</a>'
        )
    elapsed_line = (
        f"📅 Delegated for {phrase}" if ctx["milestone"] >= 365 else f"📅 {phrase} since delegation"
    )
    return (
        "<b>🔔 Cardanoism — Pool Delegation Reminder</b>\n"
        "\n"
        f"🏊 {ctx['pool_name']}\n"
        f"{elapsed_line}\n"
        f"💼 Delegated from {ctx['nickname']}\n"
        "\n"
        "Please review the status of your pool.\n"
        "\n"
        f'→ <a href="{mypage_url}">Check delegation on MyPage</a>'
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
