"""
line_flex.py
LINE Flex Message コンテンツビルダー

各通知イベントの Flex Message contents（bubble）を生成する。
lang="ja"（デフォルト）または lang="en" で言語切り替え。
"""
from cardanoism.backend.i18n import get_flex

ACCENT = "#ffcf00"
HEADER_BG = "#1a1a2e"
TEXT_PRIMARY = "#1a1a2e"
TEXT_SECONDARY = "#888888"
TEXT_UP = "#e74c3c"    # 値が上がった（手数料増など）
TEXT_DOWN = "#27ae60"  # 値が下がった
TEXT_APY = "#2980b9"
TEXT_WARN = "#e67e22"  # 警告


def _header(title: str, subtitle: str) -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": HEADER_BG,
        "paddingAll": "16px",
        "contents": [
            {
                "type": "text",
                "text": "Cardanoism",
                "color": ACCENT,
                "size": "xs",
                "weight": "bold",
            },
            {
                "type": "text",
                "text": title,
                "color": "#ffffff",
                "size": "md",
                "weight": "bold",
                "margin": "sm",
                "wrap": True,
            },
            {
                "type": "text",
                "text": subtitle,
                "color": "#ffffff99",
                "size": "xs",
                "margin": "xs",
                "wrap": True,
            },
        ],
    }


def _row(label: str, value: str, value_color: str = TEXT_PRIMARY) -> dict:
    return {
        "type": "box",
        "layout": "horizontal",
        "contents": [
            {
                "type": "text",
                "text": label,
                "size": "sm",
                "color": TEXT_SECONDARY,
                "flex": 3,
            },
            {
                "type": "text",
                "text": value,
                "size": "sm",
                "color": value_color,
                "weight": "bold",
                "align": "end",
                "flex": 4,
                "wrap": True,
            },
        ],
    }


def _wallet_row(nickname: str, lang: str = "ja") -> dict:
    t = get_flex(lang)
    return {
        "type": "box",
        "layout": "horizontal",
        "margin": "md",
        "contents": [
            {"type": "text", "text": t["wallet"], "size": "xs", "color": TEXT_SECONDARY, "flex": 3},
            {"type": "text", "text": nickname, "size": "xs", "color": TEXT_SECONDARY, "align": "end", "flex": 4},
        ],
    }


def _footer(url: str, label: str) -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "paddingAll": "12px",
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": ACCENT,
                "cornerRadius": "4px",
                "paddingAll": "10px",
                "action": {
                    "type": "uri",
                    "uri": url,
                },
                "contents": [
                    {
                        "type": "text",
                        "text": label,
                        "color": HEADER_BG,
                        "align": "center",
                        "weight": "bold",
                        "size": "sm",
                    }
                ],
            }
        ],
    }


def _bubble(header: dict, body_contents: list, url: str, footer_label: str) -> dict:
    return {
        "type": "bubble",
        "header": header,
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "contents": body_contents,
        },
        "footer": _footer(url, footer_label),
    }


# ============================================================
# epoch_start
# ============================================================

def epoch_start(epoch: int, url: str, lang: str = "ja") -> dict:
    t = get_flex(lang)
    return _bubble(
        _header(t["epoch_start_title"], t["epoch_start_subtitle"].format(epoch=epoch)),
        [
            {
                "type": "text",
                "text": f"Epoch {epoch}",
                "weight": "bold",
                "size": "xxl",
                "align": "center",
                "color": TEXT_PRIMARY,
                "margin": "md",
            },
            {
                "type": "text",
                "text": t["epoch_start_body"],
                "size": "sm",
                "align": "center",
                "color": TEXT_SECONDARY,
                "margin": "sm",
            },
        ],
        url,
        t["footer_open"],
    )


# ============================================================
# pool_retire
# ============================================================

def pool_retire(
    pool_name: str,
    retiring_epoch: int,
    nickname: str,
    url: str,
    lang: str = "ja",
) -> dict:
    t = get_flex(lang)
    return _bubble(
        _header(t["pool_retire_title"], t["pool_retire_subtitle"]),
        [
            {
                "type": "text",
                "text": pool_name,
                "weight": "bold",
                "size": "md",
                "wrap": True,
                "color": TEXT_PRIMARY,
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "box",
                "layout": "vertical",
                "margin": "md",
                "spacing": "sm",
                "contents": [
                    _row(t["pool_retire_epoch_label"], f"Epoch {retiring_epoch}", TEXT_UP),
                ],
            },
            {
                "type": "text",
                "text": t["pool_retire_hint"],
                "size": "xs",
                "color": TEXT_SECONDARY,
                "wrap": True,
                "margin": "md",
            },
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_open"],
    )


# ============================================================
# pool_fee_change
# ============================================================

def pool_fee_change(
    pool_name: str,
    old_margin_pct: float,
    new_margin_pct: float,
    old_fixed_ada: float,
    new_fixed_ada: float,
    apy: float | None,
    nickname: str,
    url: str,
    lang: str = "ja",
    old_pledge_ada: float | None = None,
    new_pledge_ada: float | None = None,
    effective_epoch: int | None = None,
) -> dict:
    t = get_flex(lang)
    margin_color = TEXT_UP if new_margin_pct > old_margin_pct else TEXT_DOWN
    fixed_color = TEXT_UP if new_fixed_ada > old_fixed_ada else TEXT_DOWN

    rows = [
        _row(t["pool_fee_variable_label"], f"{old_margin_pct:.1f}% → {new_margin_pct:.1f}%", margin_color),
        _row(t["pool_fee_fixed_label"], f"{old_fixed_ada:.0f} → {new_fixed_ada:.0f} {t['pool_fee_fixed_unit']}", fixed_color),
    ]
    if new_pledge_ada is not None and old_pledge_ada != new_pledge_ada:
        pledge_color = TEXT_DOWN if (old_pledge_ada is None or new_pledge_ada > old_pledge_ada) else TEXT_UP
        if old_pledge_ada is not None:
            pledge_text = f"{old_pledge_ada:.0f} → {new_pledge_ada:.0f} ADA"
        else:
            pledge_text = f"{new_pledge_ada:.0f} ADA"
        rows.append(_row(t["pool_fee_pledge_label"], pledge_text, pledge_color))
    if apy is not None:
        rows.append(_row(t["apy_label"], f"{apy:.2f}%", TEXT_APY))

    body = [
        {
            "type": "text",
            "text": pool_name,
            "weight": "bold",
            "size": "md",
            "wrap": True,
            "color": TEXT_PRIMARY,
        },
        {"type": "separator", "margin": "md"},
        {
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "spacing": "sm",
            "contents": rows,
        },
    ]
    if effective_epoch is not None:
        notice_text = (
            f"次エポック (Epoch {effective_epoch}) から反映されます"
            if lang == "ja" else
            f"Effective at next epoch (Epoch {effective_epoch})"
        )
        body.append({
            "type": "text",
            "text": notice_text,
            "size": "xs",
            "color": TEXT_SECONDARY,
            "wrap": True,
            "margin": "md",
        })
    body.append(_wallet_row(nickname, lang))

    return _bubble(
        _header(t["pool_fee_change_title"], t["pool_fee_change_subtitle"]),
        body,
        url,
        t["footer_open"],
    )


# ============================================================
# pool_saturation
# ============================================================

def pool_saturation(
    pool_name: str,
    sat_pct: float,
    apy: float | None,
    nickname: str,
    url: str,
    lang: str = "ja",
) -> dict:
    t = get_flex(lang)
    rows = [
        _row(t["pool_saturation_label"], f"{sat_pct:.1f}%", TEXT_UP),
    ]
    if apy is not None:
        rows.append(_row(t["apy_label"], f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header(t["pool_saturation_title"], t["pool_saturation_subtitle"]),
        [
            {
                "type": "text",
                "text": pool_name,
                "weight": "bold",
                "size": "md",
                "wrap": True,
                "color": TEXT_PRIMARY,
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "box",
                "layout": "vertical",
                "margin": "md",
                "spacing": "sm",
                "contents": rows,
            },
            {
                "type": "text",
                "text": t["pool_saturation_hint"],
                "size": "xs",
                "color": TEXT_SECONDARY,
                "wrap": True,
                "margin": "md",
            },
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_open"],
    )


# ============================================================
# pool_pledge_shortage
# ============================================================

def pool_pledge_shortage(
    pool_name: str,
    pledged_ada: float,
    live_ada: float,
    apy: float | None,
    nickname: str,
    url: str,
    lang: str = "ja",
) -> dict:
    t = get_flex(lang)
    rows = [
        _row(t["pool_pledge_label"], f"{pledged_ada:,.0f} {t['pool_pledge_unit']}", TEXT_PRIMARY),
        _row(t["pool_pledge_live_label"], f"{live_ada:,.0f} {t['pool_pledge_unit']}", TEXT_UP),
    ]
    if apy is not None:
        rows.append(_row(t["apy_label"], f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header(t["pool_pledge_shortage_title"], t["pool_pledge_shortage_subtitle"]),
        [
            {
                "type": "text",
                "text": pool_name,
                "weight": "bold",
                "size": "md",
                "wrap": True,
                "color": TEXT_PRIMARY,
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "box",
                "layout": "vertical",
                "margin": "md",
                "spacing": "sm",
                "contents": rows,
            },
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_open"],
    )


# ============================================================
# pool_reward_received
# ============================================================

def pool_reward_received(
    reward_epoch: int,
    amount_ada: float,
    apy: float | None,
    nickname: str,
    url: str,
    lang: str = "ja",
    is_leader: bool = False,
) -> dict:
    """報酬入金通知。

    Args:
        is_leader: True の場合は SPO の Leader 報酬として表示。amount_ada は leader 分。
    """
    t = get_flex(lang)
    if is_leader:
        title = "SPO 報酬 (Leader)" if lang == "ja" else "SPO Reward (Leader)"
        subtitle = (
            f"Epoch {reward_epoch} のオペレーター報酬が入金されました"
            if lang == "ja" else
            f"Epoch {reward_epoch} operator rewards have arrived"
        )
        amount_label = "SPO 報酬 (Leader)" if lang == "ja" else "SPO reward (leader)"
    else:
        title = t["pool_reward_title"]
        subtitle = t["pool_reward_subtitle"].format(epoch=reward_epoch)
        amount_label = t["pool_reward_amount_label"]

    rows = [
        _row(t["pool_reward_epoch_label"], f"Epoch {reward_epoch}", TEXT_PRIMARY),
        _row(amount_label, f"{amount_ada:,.4f} ADA", TEXT_DOWN),
    ]
    if apy is not None:
        rows.append(_row(t["apy_label"], f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header(title, subtitle),
        [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": rows,
            },
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_open"],
    )


# ============================================================
# pool_delegation_reminder
# ============================================================

def pool_delegation_reminder(
    pool_name: str,
    days: int,
    apy: float | None,
    nickname: str,
    url: str,
    lang: str = "ja",
) -> dict:
    t = get_flex(lang)
    rows = [
        _row(t["pool_remind_pool_label"], pool_name, TEXT_PRIMARY),
        _row(t["pool_remind_days_label"], t["pool_remind_days_value"].format(days=days), TEXT_WARN),
    ]
    if apy is not None:
        rows.append(_row(t["apy_label"], f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header(t["pool_remind_title"], t["pool_remind_subtitle"]),
        [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": rows,
            },
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_open"],
    )


# ============================================================
# drep_new_governance_action
# ============================================================

def drep_new_governance_action(
    proposal_type: str,
    url: str,
    lang: str = "ja",
    proposal_title: str | None = None,
    proposal_count: int = 1,
) -> dict:
    """新ガバナンスアクション通知。

    proposal_count >= 2 のときは Tx 単位の集約表示 (件数のみ + governance ページリンク)。
    proposal_count == 1 のときは proposal_title (あれば) と action_type を表示。
    """
    t = get_flex(lang)

    body_contents: list[dict] = []

    if int(proposal_count) > 1:
        # 集約モード: 件数のみ
        if lang == "ja":
            count_text = f"{proposal_count} 件の新しいガバナンスアクションが提出されました"
        else:
            count_text = f"{proposal_count} new governance actions submitted"
        body_contents.append({
            "type": "text",
            "text": count_text,
            "weight": "bold",
            "size": "md",
            "wrap": True,
            "color": TEXT_PRIMARY,
        })
    else:
        # 個別モード: タイトル (あれば) + 提案タイプ
        if proposal_title:
            body_contents.append({
                "type": "text",
                "text": proposal_title,
                "weight": "bold",
                "size": "md",
                "wrap": True,
                "color": TEXT_PRIMARY,
            })
            body_contents.append({"type": "separator", "margin": "md"})
        body_contents.append({
            "type": "box",
            "layout": "vertical",
            "margin": "md" if proposal_title else "none",
            "spacing": "sm",
            "contents": [
                _row(t["drep_new_gov_type_label"], proposal_type, TEXT_PRIMARY),
            ],
        })

    body_contents.append({
        "type": "text",
        "text": t["drep_new_gov_hint"],
        "size": "xs",
        "color": TEXT_SECONDARY,
        "wrap": True,
        "margin": "md",
    })

    return _bubble(
        _header(t["drep_new_gov_title"], t["drep_new_gov_subtitle"]),
        body_contents,
        url,
        t["footer_governance"],
    )


# ============================================================
# drep_vote
# ============================================================

def drep_vote(
    drep_name: str,
    vote: str,
    proposal_title: str | None,
    nickname: str,
    url: str,
    lang: str = "ja",
    vote_count: int = 1,
    cta_label: str | None = None,
) -> dict:
    """
    vote: "yes" / "no" / "abstain"（Koios からの raw 値）
    または後方互換のため "賛成" / "反対" / "棄権" も受け付ける。

    vote_count >= 2 のときは Tx 単位の集約表示（「N 件の GA に投票」+ DRep ページリンク）。
    """
    t = get_flex(lang)

    rows: list[dict] = []

    def _plain(text: str, color: str = TEXT_PRIMARY, weight: str | None = None,
               size: str = "sm") -> dict:
        node: dict = {
            "type": "text",
            "text": text,
            "size": size,
            "color": color,
            "wrap": True,
        }
        if weight:
            node["weight"] = weight
        return node

    if int(vote_count) > 1:
        # 集約モード: 件数だけ表示 (見出し無し)
        if lang == "ja":
            count_text = f"{vote_count} 件のガバナンス提案に投票"
        else:
            count_text = f"Voted on {vote_count} governance actions"
        rows.append(_plain(count_text, TEXT_PRIMARY, weight="bold"))
    else:
        # 個別モード: タイトル + 投票内容 (見出し無し)
        vote_key_map = {
            "yes": "vote_yes", "no": "vote_no", "abstain": "vote_abstain",
            "賛成": "vote_yes", "反対": "vote_no", "棄権": "vote_abstain",
        }
        vote_label = t.get(vote_key_map.get(vote.lower(), ""), vote)
        vote_colors = {
            t.get("vote_yes", "賛成"): TEXT_DOWN,
            t.get("vote_no", "反対"): TEXT_UP,
            t.get("vote_abstain", "棄権"): TEXT_SECONDARY,
        }
        vote_color = vote_colors.get(vote_label, TEXT_PRIMARY)
        if proposal_title:
            rows.append(_plain(proposal_title, TEXT_PRIMARY, weight="bold"))
        rows.append(_plain(vote_label, vote_color, weight="bold"))

    # ニックネームも見出し無しで小さめに表示
    rows.append(_plain(nickname, TEXT_SECONDARY, size="xs"))

    disclaimer = (
        "投票内容がご自身の意思と異なる場合は、いつでも委任先 DRep を変更できます。"
        if lang == "ja" else
        "If the vote does not align with your intent, you can change your delegated DRep at any time."
    )

    return _bubble(
        _header(t["drep_vote_title"], t["drep_vote_subtitle"]),
        [
            {
                "type": "text",
                "text": drep_name,
                "weight": "bold",
                "size": "md",
                "wrap": True,
                "color": TEXT_PRIMARY,
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "box",
                "layout": "vertical",
                "margin": "md",
                "spacing": "sm",
                "contents": rows,
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "text",
                "text": disclaimer,
                "size": "xs",
                "color": TEXT_SECONDARY,
                "wrap": True,
                "margin": "md",
            },
        ],
        url,
        cta_label if cta_label else t["footer_governance"],
    )


# ============================================================
# drep_status_change
# ============================================================

def drep_status_change(
    drep_name: str,
    old_status: str,
    new_status: str,
    nickname: str,
    url: str,
    lang: str = "ja",
) -> dict:
    t = get_flex(lang)
    return _bubble(
        _header(t["drep_status_title"], t["drep_status_subtitle"]),
        [
            {
                "type": "text",
                "text": drep_name,
                "weight": "bold",
                "size": "md",
                "wrap": True,
                "color": TEXT_PRIMARY,
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "box",
                "layout": "vertical",
                "margin": "md",
                "spacing": "sm",
                "contents": [
                    _row(t["drep_status_label"], f"{old_status} → {new_status}", TEXT_WARN),
                ],
            },
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_open"],
    )


# ============================================================
# drep_delegation_reminder
# ============================================================

def pool_epoch_performance(
    pool_name: str,
    epoch_no: int,
    active_stake_ada: float | None,
    saturation_pct: float | None,
    block_cnt: int | None,
    apy: float | None,
    nickname: str,
    url: str,
    lang: str = "ja",
    apy_epoch_no: int | None = None,
) -> dict:
    t = get_flex(lang)
    rows = [_row(t["pool_epoch_perf_epoch_label"], str(epoch_no), TEXT_PRIMARY)]
    if active_stake_ada is not None:
        ada_m = active_stake_ada / 1_000_000
        rows.append(_row(t["pool_epoch_perf_active_stake_label"], f"{ada_m:,.1f}M ADA", TEXT_PRIMARY))
    if saturation_pct is not None:
        color = TEXT_UP if saturation_pct >= 100 else TEXT_PRIMARY
        rows.append(_row(t["pool_epoch_perf_saturation_label"], f"{saturation_pct:.1f}%", color))
    if block_cnt is not None:
        rows.append(_row(t["pool_epoch_perf_blocks_label"], str(block_cnt), TEXT_PRIMARY))
    if apy is not None:
        apy_label = f"{t['pool_epoch_perf_apy_label']}（Epoch {apy_epoch_no}）" if apy_epoch_no else t["pool_epoch_perf_apy_label"]
        rows.append(_row(apy_label, f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header(t["pool_epoch_perf_title"], t["pool_epoch_perf_subtitle"]),
        [
            {
                "type": "text",
                "text": pool_name,
                "weight": "bold",
                "size": "md",
                "wrap": True,
                "color": TEXT_PRIMARY,
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "box",
                "layout": "vertical",
                "margin": "md",
                "spacing": "sm",
                "contents": rows,
            },
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_open"],
    )


# ============================================================
# drep_delegation_reminder
# ============================================================

def drep_delegation_reminder(
    drep_name: str,
    days: int,
    nickname: str,
    url: str,
    lang: str = "ja",
) -> dict:
    t = get_flex(lang)
    return _bubble(
        _header(t["drep_remind_title"], t["drep_remind_subtitle"]),
        [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    _row(t["drep_remind_drep_label"], drep_name, TEXT_PRIMARY),
                    _row(t["drep_remind_days_label"], t["drep_remind_days_value"].format(days=days), TEXT_WARN),
                ],
            },
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_governance"],
    )


# ============================================================
# treasury_withdrawal_enacted
# ============================================================

def treasury_withdrawal_enacted(
    title: str,
    enacted_epoch: int,
    url: str,
    lang: str = "ja",
) -> dict:
    """トレジャリー引き出し提案が enacted (施行) されたときの全ユーザー向け通知。"""
    t = get_flex(lang)
    return _bubble(
        _header(t["treasury_enacted_title"], t["treasury_enacted_subtitle"]),
        [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    _row(t["treasury_enacted_proposal_label"], title or "-", TEXT_PRIMARY),
                    _row(t["treasury_enacted_epoch_label"], f"Epoch {enacted_epoch}", TEXT_DOWN),
                ],
            },
        ],
        url,
        t["footer_governance"],
    )


# ============================================================
# spo_pending_vote
# ============================================================

def spo_pending_vote(
    proposal_type_label: str,
    url: str,
    lang: str = "ja",
    proposal_title: str | None = None,
    proposal_count: int = 1,
) -> dict:
    """SPO 投票対象の新ガバナンスアクション提出通知。drep_new_governance_action と
    類似のレイアウトだが SPO 文脈を強調する。

    proposal_count >= 2 のときは Tx 単位の集約表示。
    """
    t = get_flex(lang)

    body_contents: list[dict] = []

    if int(proposal_count) > 1:
        if lang == "ja":
            count_text = f"{proposal_count} 件の SPO 投票対象 GA が提出されました"
        else:
            count_text = f"{proposal_count} new SPO-eligible governance actions"
        body_contents.append({
            "type": "text",
            "text": count_text,
            "weight": "bold",
            "size": "md",
            "wrap": True,
            "color": TEXT_PRIMARY,
        })
    else:
        if proposal_title:
            body_contents.append({
                "type": "text",
                "text": proposal_title,
                "weight": "bold",
                "size": "md",
                "wrap": True,
                "color": TEXT_PRIMARY,
            })
            body_contents.append({"type": "separator", "margin": "md"})
        body_contents.append({
            "type": "box",
            "layout": "vertical",
            "margin": "md" if proposal_title else "none",
            "spacing": "sm",
            "contents": [
                _row(t["drep_new_gov_type_label"], proposal_type_label, TEXT_PRIMARY),
            ],
        })

    body_contents.append({
        "type": "text",
        "text": t["spo_pending_vote_hint"],
        "size": "xs",
        "color": TEXT_SECONDARY,
        "wrap": True,
        "margin": "md",
    })

    return _bubble(
        _header(t["spo_pending_vote_title"], t["spo_pending_vote_subtitle"]),
        body_contents,
        url,
        t["footer_governance"],
    )


# ============================================================
# drep_unvoted_ga
# ============================================================

def drep_unvoted_ga(
    title: str,
    proposal_type_label: str,
    trigger_label: str,
    nickname: str,
    url: str,
    lang: str = "ja",
) -> dict:
    """DRep 本人向けの未投票 GA リマインダー。
    7日経過 / 14日経過 / DRep yes pct が批准閾値の 50% 到達のいずれか先勝ちで発火。
    """
    t = get_flex(lang)
    return _bubble(
        _header(t["drep_unvoted_title"], t["drep_unvoted_subtitle"]),
        [
            {
                "type": "text",
                "text": title or "-",
                "weight": "bold",
                "size": "md",
                "wrap": True,
                "color": TEXT_PRIMARY,
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "box",
                "layout": "vertical",
                "margin": "md",
                "spacing": "sm",
                "contents": [
                    _row(t["drep_unvoted_type_label"], proposal_type_label, TEXT_PRIMARY),
                    _row(t["drep_unvoted_trigger_label"], trigger_label, TEXT_WARN),
                ],
            },
            {
                "type": "text",
                "text": t["drep_unvoted_hint"],
                "size": "xs",
                "color": TEXT_SECONDARY,
                "wrap": True,
                "margin": "md",
            },
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_governance"],
    )
