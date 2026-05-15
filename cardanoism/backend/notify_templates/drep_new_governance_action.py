"""drep_new_governance_action: 新ガバナンスアクション提出通知 (Stake address スコープ)。

Tx 単位で集約する:
  proposal_count == 1 : 個別通知 (タイトル + action_type + GA リンク)
  proposal_count >= 2 : 集約通知 (N 件の新 GA + governance ページリンク)
"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "drep_new_governance_action"


def context(*, action_label: str, base_url: str,
            proposal_id: str | None = None,
            proposal_title: str | None = None,
            proposal_count: int = 1) -> dict:
    """action_label は表示用 (国庫引き出し / Treasury Withdrawals 等の lang 別文字列)。
    呼出側で _GA_TYPE_MAP_JA / _EN を使って解決済みの値を渡す前提。
    """
    pid = proposal_id or ""
    return {
        "action_label":    action_label,
        "base_url":        base_url,
        "gov_url":         f"{base_url}/governance",
        "proposal_id":     pid,
        "proposal_url":    f"{base_url}/governance/{pid}" if pid else f"{base_url}/governance",
        "proposal_title":  proposal_title or "",
        "proposal_count":  int(proposal_count),
    }


def alt_text(ctx: dict, lang: str) -> str:
    count = int(ctx.get("proposal_count", 1))
    if count > 1:
        if lang == "ja":
            return f"【Cardanoism】{count} 件の新しいガバナンスアクションが提出されました"
        return f"[Cardanoism] {count} new governance actions submitted"
    if lang == "ja":
        return f"【Cardanoism】新しいガバナンスアクションが提出されました: {ctx['action_label']}"
    return f"[Cardanoism] New governance action submitted: {ctx['action_label']}"


def render_flex(ctx: dict, lang: str) -> dict:
    count = int(ctx.get("proposal_count", 1))
    # 集約のときは governance 一覧へ、個別のときは GA 詳細ページへ
    url = ctx["proposal_url"] if count == 1 and ctx.get("proposal_id") else ctx["gov_url"]
    return line_flex.drep_new_governance_action(
        ctx["action_label"], url, lang=lang,
        proposal_title=ctx.get("proposal_title") or None,
        proposal_count=count,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    count = int(ctx.get("proposal_count", 1))
    if count > 1:
        if lang == "ja":
            subj = f"{count} 件の新しいガバナンスアクションが提出されました"
            lines = [
                f"{count} 件の新しいガバナンスアクションが提出されました。",
                "Cardanoism のガバナンスページでアクションの詳細を確認できます。",
            ]
            cta_label = "ガバナンスを確認"
        else:
            subj = f"{count} new governance actions submitted"
            lines = [
                f"{count} new governance actions have been submitted.",
                "Check the details on the Cardanoism governance page.",
            ]
            cta_label = "Check Governance"
        cta_url = ctx["gov_url"]
    else:
        title = (ctx.get("proposal_title") or "").strip()
        if lang == "ja":
            subj = f"新しいガバナンスアクションが提出されました: {ctx['action_label']}"
            lines = [
                f"新しいガバナンスアクション（{ctx['action_label']}）が提出されました。",
            ]
            if title:
                lines.append(f"タイトル: {title}")
            lines.append("Cardanoism でアクションの詳細を確認できます。")
            cta_label = "ガバナンス提案を確認"
        else:
            subj = f"New governance action submitted: {ctx['action_label']}"
            lines = [
                f"A new governance action ({ctx['action_label']}) has been submitted.",
            ]
            if title:
                lines.append(f"Title: {title}")
            lines.append("Check the details on Cardanoism.")
            cta_label = "View proposal"
        cta_url = ctx["proposal_url"]
    return subj, lines, cta_url, cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    count = int(ctx.get("proposal_count", 1))
    if count > 1:
        if lang == "ja":
            out = [
                "<b>🗳️ Cardanoism — 新ガバナンスアクション通知</b>", "",
                f"📋 {count} 件の新しいガバナンスアクションが提出されました。",
                "",
                f"→ ガバナンスを確認: {ctx['gov_url']}",
            ]
        else:
            out = [
                "<b>🗳️ Cardanoism — New Governance Actions</b>", "",
                f"📋 {count} new governance actions have been submitted.",
                "",
                f"→ Check Governance: {ctx['gov_url']}",
            ]
        return "\n".join(out)

    title = (ctx.get("proposal_title") or "").strip()
    if lang == "ja":
        out = [
            "<b>🗳️ Cardanoism — 新ガバナンスアクション通知</b>", "",
            f"📋 提案タイプ: {ctx['action_label']}",
        ]
        if title:
            out.append(f"📝 タイトル: {title}")
        out.extend([
            "",
            "新しいガバナンスアクションが提出されました。",
            "",
            f"→ 提案を確認する: {ctx['proposal_url']}",
        ])
    else:
        out = [
            "<b>🗳️ Cardanoism — New Governance Action</b>", "",
            f"📋 Proposal Type: {ctx['action_label']}",
        ]
        if title:
            out.append(f"📝 Title: {title}")
        out.extend([
            "",
            "A new governance action has been submitted.",
            "",
            f"→ View proposal: {ctx['proposal_url']}",
        ])
    return "\n".join(out)


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
