"""drep_status_change: 委任先 DRep ステータス変更通知 (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "drep_status_change"


def context(*, drep_name: str, old_status: str, new_status: str,
            nickname: str, base_url: str) -> dict:
    return {
        "drep_name":  drep_name,
        "old_status": old_status,
        "new_status": new_status,
        "nickname":   nickname,
        "base_url":   base_url,
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】委任先DRep「{ctx['drep_name']}」のステータスが変わりました"
    return f"[Cardanoism] Delegated DRep '{ctx['drep_name']}' status changed"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.drep_status_change(
        ctx["drep_name"], ctx["old_status"], ctx["new_status"],
        ctx["nickname"], ctx["base_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"委任先DRep「{ctx['drep_name']}」のステータスが変わりました"
        lines = [
            f"ウォレット: {ctx['nickname']}",
            f"DRep: {ctx['drep_name']}",
            f"ステータス: {ctx['old_status']} → {ctx['new_status']}",
        ]
        cta_label = "ガバナンスを確認"
    else:
        subj = f"Delegated DRep '{ctx['drep_name']}' status changed"
        lines = [
            f"Wallet: {ctx['nickname']}",
            f"DRep: {ctx['drep_name']}",
            f"Status: {ctx['old_status']} → {ctx['new_status']}",
        ]
        cta_label = "Check Governance"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return (
            f"📋 <b>DRepステータス変更</b>\n"
            f"ウォレット: {ctx['nickname']}\n"
            f"DRep: {ctx['drep_name']}\n"
            f"ステータス: {ctx['old_status']} → {ctx['new_status']}"
        )
    return (
        f"📋 <b>DRep Status Changed</b>\n"
        f"Wallet: {ctx['nickname']}\n"
        f"DRep: {ctx['drep_name']}\n"
        f"Status: {ctx['old_status']} → {ctx['new_status']}"
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
