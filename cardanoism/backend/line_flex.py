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
) -> dict:
    t = get_flex(lang)
    margin_color = TEXT_UP if new_margin_pct > old_margin_pct else TEXT_DOWN
    fixed_color = TEXT_UP if new_fixed_ada > old_fixed_ada else TEXT_DOWN

    rows = [
        _row(t["pool_fee_variable_label"], f"{old_margin_pct:.1f}% → {new_margin_pct:.1f}%", margin_color),
        _row(t["pool_fee_fixed_label"], f"{old_fixed_ada:.0f} → {new_fixed_ada:.0f} {t['pool_fee_fixed_unit']}", fixed_color),
    ]
    if apy is not None:
        rows.append(_row(t["apy_label"], f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header(t["pool_fee_change_title"], t["pool_fee_change_subtitle"]),
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
) -> dict:
    t = get_flex(lang)
    rows = [
        _row(t["pool_reward_epoch_label"], f"Epoch {reward_epoch}", TEXT_PRIMARY),
        _row(t["pool_reward_amount_label"], f"{amount_ada:,.4f} ADA", TEXT_DOWN),
    ]
    if apy is not None:
        rows.append(_row(t["apy_label"], f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header(t["pool_reward_title"], t["pool_reward_subtitle"].format(epoch=reward_epoch)),
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
) -> dict:
    t = get_flex(lang)
    return _bubble(
        _header(t["drep_new_gov_title"], t["drep_new_gov_subtitle"]),
        [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    _row(t["drep_new_gov_type_label"], proposal_type, TEXT_PRIMARY),
                ],
            },
            {
                "type": "text",
                "text": t["drep_new_gov_hint"],
                "size": "xs",
                "color": TEXT_SECONDARY,
                "wrap": True,
                "margin": "md",
            },
        ],
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
) -> dict:
    """
    vote: "yes" / "no" / "abstain"（Koios からの raw 値）
    または後方互換のため "賛成" / "反対" / "棄権" も受け付ける。
    """
    t = get_flex(lang)

    # raw vote key → 言語別ラベルに変換
    vote_key_map = {
        "yes": "vote_yes", "no": "vote_no", "abstain": "vote_abstain",
        # 後方互換（日本語で渡された場合）
        "賛成": "vote_yes", "反対": "vote_no", "棄権": "vote_abstain",
    }
    vote_label = t.get(vote_key_map.get(vote.lower(), ""), vote)
    vote_colors = {
        t.get("vote_yes", "賛成"): TEXT_DOWN,
        t.get("vote_no", "反対"): TEXT_UP,
        t.get("vote_abstain", "棄権"): TEXT_SECONDARY,
    }
    vote_color = vote_colors.get(vote_label, TEXT_PRIMARY)

    rows = []
    if proposal_title:
        rows.append(_row(t["drep_vote_action_label"], proposal_title, TEXT_PRIMARY))
    rows.append(_row(t["drep_vote_label"], vote_label, vote_color))

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
            _wallet_row(nickname, lang),
        ],
        url,
        t["footer_governance"],
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
