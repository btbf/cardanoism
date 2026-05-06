"""pool_retire: プールリタイア通知 (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "pool_retire"


def context(*, pool_name: str, retiring_epoch: int, nickname: str,
            base_url: str) -> dict:
    return {
        "pool_name":      pool_name,
        "retiring_epoch": int(retiring_epoch),
        "nickname":       nickname,
        "base_url":       base_url,
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】委任先プール「{ctx['pool_name']}」が Epoch {ctx['retiring_epoch']} にリタイアします"
    return f"[Cardanoism] Pool '{ctx['pool_name']}' will retire at Epoch {ctx['retiring_epoch']}"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.pool_retire(
        ctx["pool_name"], ctx["retiring_epoch"], ctx["nickname"], ctx["base_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"委任先プール「{ctx['pool_name']}」が Epoch {ctx['retiring_epoch']} にリタイアします"
        lines = [
            f"ウォレット: {ctx['nickname']}",
            f"プール「{ctx['pool_name']}」は Epoch {ctx['retiring_epoch']} にリタイアする予定です。",
            "委任先の変更をご検討ください。",
        ]
        cta_label = "マイページを開く"
    else:
        subj = f"Pool '{ctx['pool_name']}' will retire at Epoch {ctx['retiring_epoch']}"
        lines = [
            f"Wallet: {ctx['nickname']}",
            f"Pool '{ctx['pool_name']}' is scheduled to retire at Epoch {ctx['retiring_epoch']}.",
            "Please consider changing your delegation.",
        ]
        cta_label = "Open MyPage"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return (
            f"⚠️ <b>プールリタイア通知</b>\n"
            f"ウォレット: {ctx['nickname']}\n"
            f"プール: {ctx['pool_name']}\n"
            f"リタイア予定: Epoch {ctx['retiring_epoch']}"
        )
    return (
        f"⚠️ <b>Pool Retirement</b>\n"
        f"Wallet: {ctx['nickname']}\n"
        f"Pool: {ctx['pool_name']}\n"
        f"Retiring at Epoch {ctx['retiring_epoch']}"
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
