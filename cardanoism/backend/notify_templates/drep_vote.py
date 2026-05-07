"""drep_vote: 委任先 DRep 投票通知 (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "drep_vote"


_VOTE_LABEL_JA = {"yes": "賛成", "no": "反対", "abstain": "棄権"}
_VOTE_LABEL_EN = {"yes": "Yes", "no": "No", "abstain": "Abstain"}

_GA_TYPE_MAP_JA = {
    "treasuryWithdrawals": "国庫引き出し",
    "parameterChange":     "プロトコル変更",
    "hardForkInitiation":  "ハードフォーク",
    "noConfidence":        "不信任",
    "updateCommittee":     "委員会変更",
    "newConstitution":     "新憲法",
    "information":         "情報提案",
}
_GA_TYPE_MAP_EN = {
    "treasuryWithdrawals": "Treasury Withdrawals",
    "parameterChange":     "Protocol Parameter Change",
    "hardForkInitiation":  "Hard Fork Initiation",
    "noConfidence":        "No Confidence",
    "updateCommittee":     "Update Committee",
    "newConstitution":     "New Constitution",
    "information":         "Information",
}


def _label(vote: str, lang: str) -> str:
    v = (vote or "").lower()
    return (_VOTE_LABEL_JA if lang == "ja" else _VOTE_LABEL_EN).get(v, vote)


def _action_label(action_type: str, lang: str) -> str:
    if not action_type:
        return ""
    table = _GA_TYPE_MAP_JA if lang == "ja" else _GA_TYPE_MAP_EN
    return table.get(action_type, action_type)


def context(*, drep_name: str, vote: str, proposal_title: str | None,
            nickname: str, base_url: str,
            action_type: str | None = None,
            proposal_id: str | None = None) -> dict:
    pid = proposal_id or ""
    return {
        "drep_name":      drep_name,
        "vote":           (vote or "").lower(),
        "proposal_title": proposal_title or "",
        "action_type":    action_type or "",
        "proposal_id":    pid,
        "nickname":       nickname,
        "base_url":       base_url,
        "gov_url":        f"{base_url}/governance",
        "proposal_url":   f"{base_url}/governance/{pid}" if pid else f"{base_url}/governance",
    }


def alt_text(ctx: dict, lang: str) -> str:
    label = _label(ctx["vote"], lang)
    if lang == "ja":
        return f"【Cardanoism】委任先DRep「{ctx['drep_name']}」が投票しました（{label}）"
    return f"[Cardanoism] Delegated DRep '{ctx['drep_name']}' voted ({label})"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.drep_vote(
        ctx["drep_name"], ctx["vote"], ctx["proposal_title"] or None,
        ctx["nickname"], ctx["gov_url"], lang=lang,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    label = _label(ctx["vote"], lang)
    if lang == "ja":
        subj = f"委任先DRep「{ctx['drep_name']}」が投票しました（{label}）"
        lines = [
            f"ウォレット: {ctx['nickname']}",
            f"DRep: {ctx['drep_name']}",
            f"投票結果: {label}",
        ]
        if ctx["proposal_title"]:
            lines.append(f"対象: {ctx['proposal_title']}")
        cta_label = "ガバナンスを確認"
    else:
        subj = f"Delegated DRep '{ctx['drep_name']}' voted ({label})"
        lines = [
            f"Wallet: {ctx['nickname']}",
            f"DRep: {ctx['drep_name']}",
            f"Vote: {label}",
        ]
        if ctx["proposal_title"]:
            lines.append(f"Proposal: {ctx['proposal_title']}")
        cta_label = "Check Governance"
    return subj, lines, ctx["gov_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    label = _label(ctx["vote"], lang)
    vote_icon = {"yes": "✅", "no": "❌", "abstain": "⚪"}.get(ctx["vote"], "🔘")
    action_label = _action_label(ctx.get("action_type", ""), lang)
    mypage_url = f"{ctx['base_url']}/mypage?tab=stake"
    if lang == "ja":
        out = ["<b>🗳️ Cardanoism — DRep投票通知</b>", ""]
        if ctx["proposal_title"]:
            out.append(f"📋 提案タイトル: {ctx['proposal_title']}")
        if action_label:
            out.append(f"📋 提案タイプ: {action_label}")
        out.extend([
            "",
            f"👤 {ctx['drep_name']}",
            f"{vote_icon} {label}",
            f"💼 {ctx['nickname']}で委任中",
            "",
            "投票内容がご自身の意思と異なる場合は、",
            "いつでも委任先 DRep を変更できます。",
            "",
            f'→ <a href="{ctx["proposal_url"]}">ガバナンス提案を確認する</a>',
            f'→ <a href="{mypage_url}">マイページで委任先を変更</a>',
        ])
    else:
        out = ["<b>🗳️ Cardanoism — DRep Vote</b>", ""]
        if ctx["proposal_title"]:
            out.append(f"📋 Proposal Title: {ctx['proposal_title']}")
        if action_label:
            out.append(f"📋 Proposal Type: {action_label}")
        out.extend([
            "",
            f"👤 {ctx['drep_name']}",
            f"{vote_icon} {label}",
            f"💼 Delegated from {ctx['nickname']}",
            "",
            "If the vote does not align with your intent,",
            "you can change your delegated DRep at any time.",
            "",
            f'→ <a href="{ctx["proposal_url"]}">View proposal</a>',
            f'→ <a href="{mypage_url}">Change delegation on MyPage</a>',
        ])
    return "\n".join(out)


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
