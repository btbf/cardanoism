"""epoch_start: 新エポック開始通知 (User スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "epoch_start"


def context(epoch: int, base_url: str) -> dict:
    return {"epoch": int(epoch), "base_url": base_url}


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】Epoch {ctx['epoch']} が始まりました"
    return f"[Cardanoism] Epoch {ctx['epoch']} has started"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.epoch_start(ctx["epoch"], ctx["base_url"], lang=lang)


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"Epoch {ctx['epoch']} が始まりました"
        lines = [f"新しいエポック (Epoch {ctx['epoch']}) が始まりました。",
                 "Cardanoism のダッシュボードで前エポックの実績を確認できます。"]
        cta_label = "ダッシュボードを開く"
    else:
        subj = f"Epoch {ctx['epoch']} has started"
        lines = [f"A new epoch (Epoch {ctx['epoch']}) has started.",
                 "Check last epoch's performance on the Cardanoism dashboard."]
        cta_label = "Open Dashboard"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return (
            "<b>⏰ Cardanoism — 新エポック開始</b>\n"
            "\n"
            f"🆕 Epoch {ctx['epoch']} が始まりました\n"
            "\n"
            f'→ <a href="{ctx["base_url"]}">ダッシュボードを開く</a>'
        )
    return (
        "<b>⏰ Cardanoism — New Epoch Started</b>\n"
        "\n"
        f"🆕 Epoch {ctx['epoch']} has started\n"
        "\n"
        f'→ <a href="{ctx["base_url"]}">Open Dashboard</a>'
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
