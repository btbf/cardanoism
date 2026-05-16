"""drep_delegation_reminder: DRep 委任長期リマインダー (Stake address スコープ)。

milestone == 365 は「365 日以上委任しています」表記、それ未満は「N 日経過」表記。
"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "drep_delegation_reminder"


def context(*, drep_name: str, milestone: int, nickname: str,
            base_url: str) -> dict:
    return {
        "drep_name": drep_name,
        "milestone": int(milestone),
        "nickname":  nickname,
        "base_url":  base_url,
        "gov_url":   f"{base_url}/governance",
    }


def _phrase(milestone: int, lang: str) -> str:
    if milestone >= 365:
        return f"{milestone} 日以上" if lang == "ja" else f"{milestone}+ days"
    return f"{milestone} 日" if lang == "ja" else f"{milestone} days"


def alt_text(ctx: dict, lang: str) -> str:
    phrase = _phrase(ctx["milestone"], lang)
    if lang == "ja":
        if ctx["milestone"] >= 365:
            return f"【Cardanoism】{phrase}委任しています。委任先DRepを確認しましょう"
        return f"【Cardanoism】委任から{phrase}が経過しました。委任先DRepを確認しましょう"
    if ctx["milestone"] >= 365:
        return f"[Cardanoism] You've been delegated for {phrase}. Please check your DRep."
    return f"[Cardanoism] {phrase} since delegation. Please check your DRep."


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.drep_delegation_reminder(
        ctx["drep_name"], ctx["milestone"], ctx["nickname"], ctx["gov_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    phrase = _phrase(ctx["milestone"], lang)
    if lang == "ja":
        if ctx["milestone"] >= 365:
            subj = f"{phrase}委任しています。委任先DRepを確認しましょう"
            body_line = f"{phrase}委任が継続しています。委任先DRepの活動を確認することをお勧めします。"
        else:
            subj = f"委任から{phrase}が経過しました。委任先DRepを確認しましょう"
            body_line = f"委任から {phrase}が経過しました。委任先DRepの活動を確認することをお勧めします。"
        lines = [
            f"ウォレット: {ctx['nickname']}",
            f"委任先DRep: {ctx['drep_name']}",
            body_line,
        ]
        cta_label = "ガバナンスを確認"
    else:
        if ctx["milestone"] >= 365:
            subj = f"You've been delegated for {phrase}. Please check your DRep."
            body_line = f"You have been delegated for {phrase}. We recommend reviewing your DRep's activity."
        else:
            subj = f"{phrase} since delegation. Please check your DRep."
            body_line = f"{phrase} have passed since delegation. We recommend reviewing your DRep's activity."
        lines = [
            f"Wallet: {ctx['nickname']}",
            f"DRep: {ctx['drep_name']}",
            body_line,
        ]
        cta_label = "Check Governance"
    return subj, lines, ctx["gov_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    mypage_url = f"{ctx['base_url']}/mypage?tab=stake"
    phrase = _phrase(ctx["milestone"], lang)
    if lang == "ja":
        elapsed_line = (
            f"📅 {phrase}委任継続中" if ctx["milestone"] >= 365 else f"📅 委任から {phrase}経過"
        )
        return (
            "<b>🔔 Cardanoism — DRep委任リマインダー</b>\n"
            "\n"
            f"👤 {ctx['drep_name']}\n"
            f"{elapsed_line}\n"
            f"💼 {ctx['nickname']}で委任中\n"
            "\n"
            "委任先DRepの活動を確認しましょう。\n"
            "\n"
            f'→ <a href="{mypage_url}">マイページで委任先を確認</a>'
        )
    elapsed_line = (
        f"📅 Delegated for {phrase}" if ctx["milestone"] >= 365 else f"📅 {phrase} since delegation"
    )
    return (
        "<b>🔔 Cardanoism — DRep Delegation Reminder</b>\n"
        "\n"
        f"👤 {ctx['drep_name']}\n"
        f"{elapsed_line}\n"
        f"💼 Delegated from {ctx['nickname']}\n"
        "\n"
        "Please review your DRep's activity.\n"
        "\n"
        f'→ <a href="{mypage_url}">Check delegation on MyPage</a>'
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
