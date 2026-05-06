"""pool_reward_received: 報酬入金通知 (Stake address スコープ)。

SPO の場合は leader 報酬として表示。非 SPO は member ベース合算。
"""
from __future__ import annotations

from cardanoism.backend import line_flex
from cardanoism.backend.notify_templates._dispatcher import register

EVENT_TYPE = "pool_reward_received"


def context(
    *,
    reward_epoch: int,
    primary_ada: float,
    apy: float | None,
    nickname: str,
    is_leader: bool,
    base_url: str,
) -> dict:
    return {
        "reward_epoch": int(reward_epoch),
        "primary_ada":  float(primary_ada),
        "apy":          apy,
        "nickname":     nickname,
        "is_leader":    bool(is_leader),
        "base_url":     base_url,
    }


def alt_text(ctx: dict, lang: str) -> str:
    if ctx["is_leader"]:
        if lang == "ja":
            return f"【Cardanoism】Epoch {ctx['reward_epoch']} の SPO 報酬 (Leader) が入金されました"
        return f"[Cardanoism] SPO leader rewards for Epoch {ctx['reward_epoch']} have arrived"
    if lang == "ja":
        return f"【Cardanoism】Epoch {ctx['reward_epoch']} 分の報酬が入金されました"
    return f"[Cardanoism] Rewards for Epoch {ctx['reward_epoch']} have arrived"


def render_flex(ctx: dict, lang: str) -> dict:
    return line_flex.pool_reward_received(
        ctx["reward_epoch"], ctx["primary_ada"], ctx["apy"],
        ctx["nickname"], ctx["base_url"],
        lang=lang, is_leader=ctx["is_leader"],
    )


def render_email(ctx: dict, lang: str) -> tuple[str, list[str], str, str]:
    if ctx["is_leader"]:
        if lang == "ja":
            subj = f"Epoch {ctx['reward_epoch']} の SPO 報酬 (Leader) が入金されました"
            lines = [
                f"ウォレット: {ctx['nickname']}",
                f"Epoch {ctx['reward_epoch']} の SPO 報酬 (Leader): {ctx['primary_ada']:.6f} ADA",
            ]
        else:
            subj = f"SPO leader rewards for Epoch {ctx['reward_epoch']} have arrived"
            lines = [
                f"Wallet: {ctx['nickname']}",
                f"Epoch {ctx['reward_epoch']} SPO reward (leader): {ctx['primary_ada']:.6f} ADA",
            ]
    else:
        if lang == "ja":
            subj = f"Epoch {ctx['reward_epoch']} 分の報酬が入金されました"
            lines = [
                f"ウォレット: {ctx['nickname']}",
                f"Epoch {ctx['reward_epoch']} の報酬: {ctx['primary_ada']:.6f} ADA",
            ]
        else:
            subj = f"Rewards for Epoch {ctx['reward_epoch']} have arrived"
            lines = [
                f"Wallet: {ctx['nickname']}",
                f"Epoch {ctx['reward_epoch']} reward: {ctx['primary_ada']:.6f} ADA",
            ]
    cta_label = "マイページを開く" if lang == "ja" else "Open MyPage"
    return subj, lines, ctx["base_url"], cta_label


def render_telegram(ctx: dict, lang: str) -> str:
    if ctx["is_leader"]:
        if lang == "ja":
            return (
                f"👑 <b>SPO 報酬 (Leader) 入金</b>\n"
                f"ウォレット: {ctx['nickname']}\n"
                f"Epoch {ctx['reward_epoch']} SPO 報酬: {ctx['primary_ada']:.6f} ADA"
            )
        return (
            f"👑 <b>SPO Leader Reward Received</b>\n"
            f"Wallet: {ctx['nickname']}\n"
            f"Epoch {ctx['reward_epoch']} SPO reward: {ctx['primary_ada']:.6f} ADA"
        )
    if lang == "ja":
        return (
            f"💰 <b>ステーキング報酬入金</b>\n"
            f"ウォレット: {ctx['nickname']}\n"
            f"Epoch {ctx['reward_epoch']} 報酬: {ctx['primary_ada']:.6f} ADA"
        )
    return (
        f"💰 <b>Staking Reward Received</b>\n"
        f"Wallet: {ctx['nickname']}\n"
        f"Epoch {ctx['reward_epoch']} reward: {ctx['primary_ada']:.6f} ADA"
    )


register(EVENT_TYPE, __import__(__name__, fromlist=["_"]))
