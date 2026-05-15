"""pool_fee_change: プール手数料/誓約変更通知 (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "pool_fee_change"


def context(*, pool_name: str,
            old_margin_pct: float, new_margin_pct: float,
            old_fixed_ada: float, new_fixed_ada: float,
            old_pledge_ada: float | None, new_pledge_ada: float,
            apy: float | None, nickname: str, base_url: str,
            effective_epoch: int | None = None) -> dict:
    return {
        "pool_name":      pool_name,
        "old_margin_pct": float(old_margin_pct),
        "new_margin_pct": float(new_margin_pct),
        "old_fixed_ada":  float(old_fixed_ada),
        "new_fixed_ada":  float(new_fixed_ada),
        "old_pledge_ada": old_pledge_ada,
        "new_pledge_ada": float(new_pledge_ada),
        "apy":            apy,
        "nickname":       nickname,
        "base_url":       base_url,
        "effective_epoch": int(effective_epoch) if effective_epoch is not None else None,
        "fee_changed":    (old_margin_pct != new_margin_pct) or (old_fixed_ada != new_fixed_ada),
        "pledge_changed": old_pledge_ada != new_pledge_ada,
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】委任先プール「{ctx['pool_name']}」の手数料が変更されました"
    return f"[Cardanoism] Pool '{ctx['pool_name']}' fee has changed"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.pool_fee_change(
        pool_name=ctx["pool_name"],
        old_margin_pct=ctx["old_margin_pct"], new_margin_pct=ctx["new_margin_pct"],
        old_fixed_ada=ctx["old_fixed_ada"],   new_fixed_ada=ctx["new_fixed_ada"],
        apy=ctx["apy"],
        nickname=ctx["nickname"], url=ctx["base_url"], lang=lang,
        old_pledge_ada=ctx["old_pledge_ada"], new_pledge_ada=ctx["new_pledge_ada"],
        effective_epoch=ctx.get("effective_epoch"),
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    ee = ctx.get("effective_epoch")
    if lang == "ja":
        subj = f"委任先プール「{ctx['pool_name']}」の手数料が変更されました"
        lines = [f"ウォレット: {ctx['nickname']}"]
        if ctx["fee_changed"]:
            lines += [
                f"変動手数料: {ctx['old_margin_pct']:.2f}% → {ctx['new_margin_pct']:.2f}%",
                f"固定手数料: {ctx['old_fixed_ada']:.0f} ADA → {ctx['new_fixed_ada']:.0f} ADA",
            ]
        if ctx["pledge_changed"]:
            if ctx["old_pledge_ada"] is not None:
                lines.append(f"誓約: {ctx['old_pledge_ada']:.0f} ADA → {ctx['new_pledge_ada']:.0f} ADA")
            else:
                lines.append(f"誓約: {ctx['new_pledge_ada']:.0f} ADA")
        if ee is not None:
            lines.append("")
            lines.append(f"※ 新しいパラメータは次エポック (Epoch {ee}) から反映されます。")
        cta_label = "マイページを開く"
    else:
        subj = f"Pool '{ctx['pool_name']}' fee has changed"
        lines = [f"Wallet: {ctx['nickname']}"]
        if ctx["fee_changed"]:
            lines += [
                f"Margin: {ctx['old_margin_pct']:.2f}% → {ctx['new_margin_pct']:.2f}%",
                f"Fixed cost: {ctx['old_fixed_ada']:.0f} ADA → {ctx['new_fixed_ada']:.0f} ADA",
            ]
        if ctx["pledge_changed"]:
            if ctx["old_pledge_ada"] is not None:
                lines.append(f"Pledge: {ctx['old_pledge_ada']:.0f} ADA → {ctx['new_pledge_ada']:.0f} ADA")
            else:
                lines.append(f"Pledge: {ctx['new_pledge_ada']:.0f} ADA")
        if ee is not None:
            lines.append("")
            lines.append(f"Note: new parameters take effect at the next epoch (Epoch {ee}).")
        cta_label = "Open MyPage"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    mypage_url = f"{ctx['base_url']}/mypage?tab=stake"
    ee = ctx.get("effective_epoch")
    if lang == "ja":
        lines = ["<b>💱 Cardanoism — プール手数料変更通知</b>", "", f"🏊 {ctx['pool_name']}"]
        if ctx["fee_changed"]:
            lines += [
                f"📊 変動手数料: {ctx['old_margin_pct']:.2f}% → {ctx['new_margin_pct']:.2f}%",
                f"💰 固定手数料: {ctx['old_fixed_ada']:,.0f} ADA → {ctx['new_fixed_ada']:,.0f} ADA",
            ]
        if ctx["pledge_changed"]:
            if ctx["old_pledge_ada"] is not None:
                lines.append(f"🔒 誓約: {ctx['old_pledge_ada']:,.0f} ADA → {ctx['new_pledge_ada']:,.0f} ADA")
            else:
                lines.append(f"🔒 誓約: {ctx['new_pledge_ada']:,.0f} ADA")
        if ee is not None:
            lines.append(f"⏭️ 反映エポック: Epoch {ee} (次エポックから)")
        lines += [
            f"💼 {ctx['nickname']}で委任中",
            "",
            f'→ <a href="{mypage_url}">マイページで委任先を確認</a>',
        ]
    else:
        lines = ["<b>💱 Cardanoism — Pool Fee Changed</b>", "", f"🏊 {ctx['pool_name']}"]
        if ctx["fee_changed"]:
            lines += [
                f"📊 Margin: {ctx['old_margin_pct']:.2f}% → {ctx['new_margin_pct']:.2f}%",
                f"💰 Fixed cost: {ctx['old_fixed_ada']:,.0f} ADA → {ctx['new_fixed_ada']:,.0f} ADA",
            ]
        if ctx["pledge_changed"]:
            if ctx["old_pledge_ada"] is not None:
                lines.append(f"🔒 Pledge: {ctx['old_pledge_ada']:,.0f} ADA → {ctx['new_pledge_ada']:,.0f} ADA")
            else:
                lines.append(f"🔒 Pledge: {ctx['new_pledge_ada']:,.0f} ADA")
        if ee is not None:
            lines.append(f"⏭️ Effective: Epoch {ee} (next epoch)")
        lines += [
            f"💼 Delegated from {ctx['nickname']}",
            "",
            f'→ <a href="{mypage_url}">Check delegation on MyPage</a>',
        ]
    return "\n".join(lines)


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
