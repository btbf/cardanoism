"""pool_saturation: プール飽和ライン超過通知 (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "pool_saturation"


def context(*, pool_name: str, sat_pct: float, apy: float | None,
            nickname: str, base_url: str) -> dict:
    return {
        "pool_name": pool_name,
        "sat_pct":   float(sat_pct),
        "apy":       apy,
        "nickname":  nickname,
        "base_url":  base_url,
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】委任先プール「{ctx['pool_name']}」が飽和ラインを超えました（{ctx['sat_pct']:.1f}%）"
    return f"[Cardanoism] Pool '{ctx['pool_name']}' exceeded saturation ({ctx['sat_pct']:.1f}%)"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.pool_saturation(
        ctx["pool_name"], ctx["sat_pct"], ctx["apy"],
        ctx["nickname"], ctx["base_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"委任先プール「{ctx['pool_name']}」が飽和ラインを超えました（{ctx['sat_pct']:.1f}%）"
        lines = [
            f"ウォレット: {ctx['nickname']}",
            f"プール「{ctx['pool_name']}」の飽和度が {ctx['sat_pct']:.1f}% になっています。",
            "委任先の変更をご検討ください。",
        ]
        cta_label = "マイページを開く"
    else:
        subj = f"Pool '{ctx['pool_name']}' exceeded saturation ({ctx['sat_pct']:.1f}%)"
        lines = [
            f"Wallet: {ctx['nickname']}",
            f"Pool '{ctx['pool_name']}' saturation is {ctx['sat_pct']:.1f}%.",
            "Please consider changing your delegation.",
        ]
        cta_label = "Open MyPage"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    mypage_url = f"{ctx['base_url']}/mypage?tab=stake"
    if lang == "ja":
        return (
            "<b>⚠️ Cardanoism — プール飽和通知</b>\n"
            "\n"
            f"🏊 {ctx['pool_name']}\n"
            f"📈 飽和度: {ctx['sat_pct']:.1f}%\n"
            f"💼 {ctx['nickname']}で委任中\n"
            "\n"
            "委任先の変更をご検討ください。\n"
            "\n"
            f'→ <a href="{mypage_url}">マイページで委任先を変更</a>'
        )
    return (
        "<b>⚠️ Cardanoism — Pool Saturation Alert</b>\n"
        "\n"
        f"🏊 {ctx['pool_name']}\n"
        f"📈 Saturation: {ctx['sat_pct']:.1f}%\n"
        f"💼 Delegated from {ctx['nickname']}\n"
        "\n"
        "Please consider changing your delegation.\n"
        "\n"
        f'→ <a href="{mypage_url}">Change delegation on MyPage</a>'
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
