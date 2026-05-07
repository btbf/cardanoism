"""drep_delegation_reminder: DRep 委任長期リマインダー (Stake address スコープ)。"""
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


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】委任から{ctx['milestone']}日が経過しました。委任先DRepを確認しましょう"
    return f"[Cardanoism] {ctx['milestone']} days since delegation. Please check your DRep."


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.drep_delegation_reminder(
        ctx["drep_name"], ctx["milestone"], ctx["nickname"], ctx["gov_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"委任から{ctx['milestone']}日が経過しました。委任先DRepを確認しましょう"
        lines = [
            f"ウォレット: {ctx['nickname']}",
            f"委任先DRep: {ctx['drep_name']}",
            f"委任から {ctx['milestone']} 日が経過しました。委任先DRepの活動を確認することをお勧めします。",
        ]
        cta_label = "ガバナンスを確認"
    else:
        subj = f"{ctx['milestone']} days since delegation. Please check your DRep."
        lines = [
            f"Wallet: {ctx['nickname']}",
            f"DRep: {ctx['drep_name']}",
            f"{ctx['milestone']} days have passed since delegation. We recommend reviewing your DRep's activity.",
        ]
        cta_label = "Check Governance"
    return subj, lines, ctx["gov_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    mypage_url = f"{ctx['base_url']}/mypage?tab=stake"
    if lang == "ja":
        return (
            "<b>🔔 Cardanoism — DRep委任リマインダー</b>\n"
            "\n"
            f"👤 {ctx['drep_name']}\n"
            f"📅 委任から {ctx['milestone']} 日経過\n"
            f"💼 {ctx['nickname']}で委任中\n"
            "\n"
            "委任先DRepの活動を確認しましょう。\n"
            "\n"
            f'→ <a href="{mypage_url}">マイページで委任先を確認</a>'
        )
    return (
        "<b>🔔 Cardanoism — DRep Delegation Reminder</b>\n"
        "\n"
        f"👤 {ctx['drep_name']}\n"
        f"📅 {ctx['milestone']} days since delegation\n"
        f"💼 Delegated from {ctx['nickname']}\n"
        "\n"
        "Please review your DRep's activity.\n"
        "\n"
        f'→ <a href="{mypage_url}">Check delegation on MyPage</a>'
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
