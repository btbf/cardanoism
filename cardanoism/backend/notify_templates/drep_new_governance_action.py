"""drep_new_governance_action: 新ガバナンスアクション提出通知 (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "drep_new_governance_action"


def context(*, action_label: str, base_url: str) -> dict:
    """action_label は表示用 (国庫引き出し / Treasury Withdrawals 等の lang 別文字列)。
    呼出側で _GA_TYPE_MAP_JA / _EN を使って解決済みの値を渡す前提。
    """
    return {
        "action_label": action_label,
        "base_url":     base_url,
        "gov_url":      f"{base_url}/governance",
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】新しいガバナンスアクションが提出されました: {ctx['action_label']}"
    return f"[Cardanoism] New governance action submitted: {ctx['action_label']}"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.drep_new_governance_action(ctx["action_label"], ctx["gov_url"], lang=lang)


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"新しいガバナンスアクションが提出されました: {ctx['action_label']}"
        lines = [
            f"新しいガバナンスアクション（{ctx['action_label']}）が提出されました。",
            "Cardanoism でアクションの詳細を確認できます。",
        ]
        cta_label = "ガバナンスを確認"
    else:
        subj = f"New governance action submitted: {ctx['action_label']}"
        lines = [
            f"A new governance action ({ctx['action_label']}) has been submitted.",
            "Check the details on Cardanoism.",
        ]
        cta_label = "Check Governance"
    return subj, lines, ctx["gov_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return (
            f"🗳️ <b>新ガバナンスアクション</b>\n"
            f"種類: {ctx['action_label']}\n"
            f"{ctx['gov_url']}"
        )
    return (
        f"🗳️ <b>New Governance Action</b>\n"
        f"Type: {ctx['action_label']}\n"
        f"{ctx['gov_url']}"
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
