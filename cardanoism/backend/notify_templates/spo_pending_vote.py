"""spo_pending_vote: SPO 投票対象 GA 提出通知 (Stake address スコープ、SPO のみ)。

Tx 単位で集約する:
  proposal_count == 1 : 個別通知 (タイトル + action_type + GA リンク)
  proposal_count >= 2 : 集約通知 (N 件の SPO 対象 GA + governance ページリンク)
"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "spo_pending_vote"


def context(*, action_label: str, base_url: str,
            proposal_id: str | None = None,
            proposal_title: str | None = None,
            proposal_count: int = 1) -> dict:
    pid = proposal_id or ""
    return {
        "action_label":   action_label,
        "base_url":       base_url,
        "gov_url":        f"{base_url}/governance",
        "proposal_id":    pid,
        "proposal_url":   f"{base_url}/governance/{pid}" if pid else f"{base_url}/governance",
        "proposal_title": proposal_title or "",
        "proposal_count": int(proposal_count),
    }


def alt_text(ctx: dict, lang: str) -> str:
    count = int(ctx.get("proposal_count", 1))
    if count > 1:
        if lang == "ja":
            return f"【Cardanoism】SPO 投票対象の新ガバナンスアクション {count} 件"
        return f"[Cardanoism] {count} new SPO-eligible governance actions"
    if lang == "ja":
        return f"【Cardanoism】SPO 投票対象の新ガバナンスアクション: {ctx['action_label']}"
    return f"[Cardanoism] New SPO-eligible governance action: {ctx['action_label']}"


def render_flex(ctx: dict, lang: str) -> dict:
    count = int(ctx.get("proposal_count", 1))
    url = ctx["proposal_url"] if count == 1 and ctx.get("proposal_id") else ctx["gov_url"]
    return line_flex.spo_pending_vote(
        ctx["action_label"], url, lang=lang,
        proposal_title=ctx.get("proposal_title") or None,
        proposal_count=count,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    count = int(ctx.get("proposal_count", 1))
    if count > 1:
        if lang == "ja":
            subj = f"SPO 投票対象の新ガバナンスアクション {count} 件"
            lines = [
                f"SPO が投票可能な新しいガバナンスアクションが {count} 件提出されました。",
                "あなたのプールに代わって投票することを検討してください。",
            ]
            cta_label = "ガバナンスを確認"
        else:
            subj = f"{count} new SPO-eligible governance actions"
            lines = [
                f"{count} new governance actions eligible for SPO voting have been submitted.",
                "Consider casting a vote on behalf of your pool.",
            ]
            cta_label = "Check Governance"
        cta_url = ctx["gov_url"]
    else:
        title = (ctx.get("proposal_title") or "").strip()
        if lang == "ja":
            subj = f"SPO 投票対象の新ガバナンスアクション: {ctx['action_label']}"
            lines = [
                f"SPO が投票可能な新しいガバナンスアクション（{ctx['action_label']}）が提出されました。",
            ]
            if title:
                lines.append(f"タイトル: {title}")
            lines.append("あなたのプールに代わって投票することを検討してください。")
            cta_label = "ガバナンス提案を確認"
        else:
            subj = f"New SPO-eligible governance action: {ctx['action_label']}"
            lines = [
                f"A new governance action ({ctx['action_label']}) eligible for SPO voting has been submitted.",
            ]
            if title:
                lines.append(f"Title: {title}")
            lines.append("Consider casting a vote on behalf of your pool.")
            cta_label = "View proposal"
        cta_url = ctx["proposal_url"]
    return subj, lines, cta_url, cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    count = int(ctx.get("proposal_count", 1))
    if count > 1:
        if lang == "ja":
            out = [
                "<b>👑 Cardanoism — SPO 投票対象 GA 通知</b>", "",
                f"📋 SPO が投票可能な新しいガバナンスアクションが {count} 件提出されました。",
                "プールに代わって投票を検討してください。",
                "",
                f"→ ガバナンスを確認: {ctx['gov_url']}",
            ]
        else:
            out = [
                "<b>👑 Cardanoism — SPO-eligible Governance Actions</b>", "",
                f"📋 {count} new SPO-eligible governance actions have been submitted.",
                "Consider casting a vote on behalf of your pool.",
                "",
                f"→ Check Governance: {ctx['gov_url']}",
            ]
        return "\n".join(out)

    title = (ctx.get("proposal_title") or "").strip()
    if lang == "ja":
        out = [
            "<b>👑 Cardanoism — SPO 投票対象 GA 通知</b>", "",
            f"📋 提案タイプ: {ctx['action_label']}",
        ]
        if title:
            out.append(f"📝 タイトル: {title}")
        out.extend([
            "",
            "SPO が投票可能な新しいガバナンスアクションが提出されました。",
            "プールに代わって投票を検討してください。",
            "",
            f"→ 提案を確認する: {ctx['proposal_url']}",
        ])
    else:
        out = [
            "<b>👑 Cardanoism — SPO-eligible Governance Action</b>", "",
            f"📋 Proposal Type: {ctx['action_label']}",
        ]
        if title:
            out.append(f"📝 Title: {title}")
        out.extend([
            "",
            "A new governance action eligible for SPO voting has been submitted.",
            "Consider casting a vote on behalf of your pool.",
            "",
            f"→ View proposal: {ctx['proposal_url']}",
        ])
    return "\n".join(out)


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
