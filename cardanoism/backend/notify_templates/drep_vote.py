"""drep_vote: 委任先 DRep 投票通知 (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "drep_vote"


_VOTE_LABEL_JA = {"yes": "賛成", "no": "反対", "abstain": "棄権"}
_VOTE_LABEL_EN = {"yes": "Yes", "no": "No", "abstain": "Abstain"}


def _label(vote: str, lang: str) -> str:
    v = (vote or "").lower()
    return (_VOTE_LABEL_JA if lang == "ja" else _VOTE_LABEL_EN).get(v, vote)


def context(*, drep_name: str, vote: str, proposal_title: str | None,
            nickname: str, base_url: str) -> dict:
    return {
        "drep_name":      drep_name,
        "vote":           (vote or "").lower(),
        "proposal_title": proposal_title or "",
        "nickname":       nickname,
        "base_url":       base_url,
        "gov_url":        f"{base_url}/governance",
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
    if lang == "ja":
        out = [
            "🗳️ <b>DRep投票</b>",
            f"ウォレット: {ctx['nickname']}",
            f"DRep: {ctx['drep_name']}",
            f"投票: {label}",
        ]
        if ctx["proposal_title"]:
            out.append(f"対象: {ctx['proposal_title']}")
    else:
        out = [
            "🗳️ <b>DRep Vote</b>",
            f"Wallet: {ctx['nickname']}",
            f"DRep: {ctx['drep_name']}",
            f"Vote: {label}",
        ]
        if ctx["proposal_title"]:
            out.append(f"Proposal: {ctx['proposal_title']}")
    return "\n".join(out)


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
