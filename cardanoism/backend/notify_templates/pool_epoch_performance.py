"""pool_epoch_performance: プール前エポック実績通知 (Stake address スコープ)。"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "pool_epoch_performance"


def context(*, pool_name: str, prev_epoch: int,
            active_stake_ada: float | None, saturation_pct: float | None,
            block_cnt: int | None, apy: float | None, apy_epoch: int | None,
            nickname: str, base_url: str) -> dict:
    return {
        "pool_name":        pool_name,
        "prev_epoch":       int(prev_epoch),
        "active_stake_ada": active_stake_ada,
        "saturation_pct":   saturation_pct,
        "block_cnt":        block_cnt,
        "apy":              apy,
        "apy_epoch":        apy_epoch,
        "nickname":         nickname,
        "base_url":         base_url,
    }


def alt_text(ctx: dict, lang: str) -> str:
    if lang == "ja":
        return f"【Cardanoism】Epoch {ctx['prev_epoch']} の{ctx['pool_name']}実績が確定しました"
    return f"[Cardanoism] Epoch {ctx['prev_epoch']} performance for {ctx['pool_name']}"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.pool_epoch_performance(
        pool_name=ctx["pool_name"], epoch_no=ctx["prev_epoch"],
        active_stake_ada=ctx["active_stake_ada"],
        saturation_pct=ctx["saturation_pct"],
        block_cnt=ctx["block_cnt"],
        apy=ctx["apy"],
        nickname=ctx["nickname"], url=ctx["base_url"], lang=lang,
        apy_epoch_no=ctx["apy_epoch"] if ctx["apy"] is not None else None,
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if lang == "ja":
        subj = f"Epoch {ctx['prev_epoch']} の{ctx['pool_name']}実績が確定しました"
        lines = [f"ウォレット: {ctx['nickname']}", f"プール: {ctx['pool_name']}",
                 f"エポック: {ctx['prev_epoch']}"]
        if ctx["active_stake_ada"] is not None:
            lines.append(f"有効ステーク: {ctx['active_stake_ada'] / 1_000_000:,.1f}M ADA")
        if ctx["saturation_pct"] is not None:
            lines.append(f"飽和度: {ctx['saturation_pct']:.1f}%")
        if ctx["block_cnt"] is not None:
            lines.append(f"ブロック生成数: {ctx['block_cnt']}")
        if ctx["apy"] is not None:
            lines.append(f"APY（Ep.{ctx['apy_epoch']} 実績）: {ctx['apy']:.2f}%")
        cta_label = "マイページを開く"
    else:
        subj = f"Epoch {ctx['prev_epoch']} performance for {ctx['pool_name']}"
        lines = [f"Wallet: {ctx['nickname']}", f"Pool: {ctx['pool_name']}",
                 f"Epoch: {ctx['prev_epoch']}"]
        if ctx["active_stake_ada"] is not None:
            lines.append(f"Active Stake: {ctx['active_stake_ada'] / 1_000_000:,.1f}M ADA")
        if ctx["saturation_pct"] is not None:
            lines.append(f"Saturation: {ctx['saturation_pct']:.1f}%")
        if ctx["block_cnt"] is not None:
            lines.append(f"Blocks Minted: {ctx['block_cnt']}")
        if ctx["apy"] is not None:
            lines.append(f"APY (Ep.{ctx['apy_epoch']}): {ctx['apy']:.2f}%")
        cta_label = "Open MyPage"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    if lang == "ja":
        lines = [
            "📊 <b>プール実績通知</b>",
            f"ウォレット: {ctx['nickname']}",
            f"プール: {ctx['pool_name']}",
            f"Epoch {ctx['prev_epoch']} 確定",
        ]
        if ctx["block_cnt"] is not None:
            lines.append(f"ブロック生成数: {ctx['block_cnt']}")
        if ctx["saturation_pct"] is not None:
            lines.append(f"飽和度: {ctx['saturation_pct']:.1f}%")
        if ctx["apy"] is not None:
            lines.append(f"APY: {ctx['apy']:.2f}%")
    else:
        lines = [
            "📊 <b>Pool Performance</b>",
            f"Wallet: {ctx['nickname']}",
            f"Pool: {ctx['pool_name']}",
            f"Epoch {ctx['prev_epoch']} confirmed",
        ]
        if ctx["block_cnt"] is not None:
            lines.append(f"Blocks: {ctx['block_cnt']}")
        if ctx["saturation_pct"] is not None:
            lines.append(f"Saturation: {ctx['saturation_pct']:.1f}%")
        if ctx["apy"] is not None:
            lines.append(f"APY: {ctx['apy']:.2f}%")
    return "\n".join(lines)


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
