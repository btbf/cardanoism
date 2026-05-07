"""pool_pledge_shortage: プール誓約不足通知 (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "pool_pledge_shortage"


def context(*, pool_name: str, pledged_ada: float, live_ada: float,
            apy: float | None, nickname: str, base_url: str) -> dict:
    return {
        "pool_name":   pool_name,
        "pledged_ada": float(pledged_ada),
        "live_ada":    float(live_ada),
        "apy":         apy,
        "nickname":    nickname,
        "base_url":    base_url,
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】委任先プール「{ctx['pool_name']}」の誓約が不足しています"
    return f"[Cardanoism] Pool '{ctx['pool_name']}' has insufficient pledge"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.pool_pledge_shortage(
        ctx["pool_name"], ctx["pledged_ada"], ctx["live_ada"], ctx["apy"],
        ctx["nickname"], ctx["base_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"委任先プール「{ctx['pool_name']}」の誓約が不足しています"
        lines = [
            f"ウォレット: {ctx['nickname']}",
            f"誓約金額: {ctx['pledged_ada']:,.0f} ADA",
            f"現在の実績: {ctx['live_ada']:,.0f} ADA",
            "誓約不足のプールは報酬が減少する場合があります。",
        ]
        cta_label = "マイページを開く"
    else:
        subj = f"Pool '{ctx['pool_name']}' has insufficient pledge"
        lines = [
            f"Wallet: {ctx['nickname']}",
            f"Pledge: {ctx['pledged_ada']:,.0f} ADA",
            f"Live pledge: {ctx['live_ada']:,.0f} ADA",
            "Pools with insufficient pledge may have reduced rewards.",
        ]
        cta_label = "Open MyPage"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    mypage_url = f"{ctx['base_url']}/mypage?tab=stake"
    if lang == "ja":
        return (
            "<b>⚠️ Cardanoism — 誓約不足通知</b>\n"
            "\n"
            f"🏊 {ctx['pool_name']}\n"
            f"🔒 誓約: {ctx['pledged_ada']:,.0f} ADA\n"
            f"📊 実績: {ctx['live_ada']:,.0f} ADA\n"
            f"💼 {ctx['nickname']}で委任中\n"
            "\n"
            "誓約不足のプールは報酬が減少する場合があります。\n"
            "\n"
            f'→ <a href="{mypage_url}">マイページで委任先を確認</a>'
        )
    return (
        "<b>⚠️ Cardanoism — Pledge Shortage Alert</b>\n"
        "\n"
        f"🏊 {ctx['pool_name']}\n"
        f"🔒 Pledge: {ctx['pledged_ada']:,.0f} ADA\n"
        f"📊 Live: {ctx['live_ada']:,.0f} ADA\n"
        f"💼 Delegated from {ctx['nickname']}\n"
        "\n"
        "Pools with insufficient pledge may have reduced rewards.\n"
        "\n"
        f'→ <a href="{mypage_url}">Check delegation on MyPage</a>'
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
