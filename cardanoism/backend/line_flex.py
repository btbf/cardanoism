"""
line_flex.py
LINE Flex Message コンテンツビルダー

各通知イベントの Flex Message contents（bubble）を生成する。
"""

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


def _wallet_row(nickname: str) -> dict:
    return {
        "type": "box",
        "layout": "horizontal",
        "margin": "md",
        "contents": [
            {"type": "text", "text": "ウォレット", "size": "xs", "color": TEXT_SECONDARY, "flex": 3},
            {"type": "text", "text": nickname, "size": "xs", "color": TEXT_SECONDARY, "align": "end", "flex": 4},
        ],
    }


def _footer(url: str, label: str = "Cardanoism を開く") -> dict:
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


def _bubble(header: dict, body_contents: list, url: str, footer_label: str = "Cardanoism を開く") -> dict:
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

def epoch_start(epoch: int, url: str) -> dict:
    return _bubble(
        _header("新エポック開始", f"Epoch {epoch} が始まりました"),
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
                "text": "新しいエポックが始まりました",
                "size": "sm",
                "align": "center",
                "color": TEXT_SECONDARY,
                "margin": "sm",
            },
        ],
        url,
    )


# ============================================================
# pool_retire
# ============================================================

def pool_retire(
    pool_name: str,
    retiring_epoch: int,
    nickname: str,
    url: str,
) -> dict:
    return _bubble(
        _header("プールリタイア通知", "委任先プールが引退予告を出しました"),
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
                    _row("リタイア予定エポック", f"Epoch {retiring_epoch}", TEXT_UP),
                ],
            },
            {
                "type": "text",
                "text": "新しいプールへの委任をご検討ください",
                "size": "xs",
                "color": TEXT_SECONDARY,
                "wrap": True,
                "margin": "md",
            },
            _wallet_row(nickname),
        ],
        url,
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
) -> dict:
    margin_color = TEXT_UP if new_margin_pct > old_margin_pct else TEXT_DOWN
    fixed_color = TEXT_UP if new_fixed_ada > old_fixed_ada else TEXT_DOWN

    rows = [
        _row("変動手数料", f"{old_margin_pct:.1f}% → {new_margin_pct:.1f}%", margin_color),
        _row("固定費", f"{old_fixed_ada:.0f} → {new_fixed_ada:.0f} ADA", fixed_color),
    ]
    if apy is not None:
        rows.append(_row("APY", f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header("手数料変更通知", "委任先プールの手数料が変更されました"),
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
            _wallet_row(nickname),
        ],
        url,
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
) -> dict:
    rows = [
        _row("飽和度", f"{sat_pct:.1f}%", TEXT_UP),
    ]
    if apy is not None:
        rows.append(_row("APY", f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header("飽和ライン超過", "委任先プールが飽和ラインを超えました"),
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
                "text": "報酬効率が下がる可能性があります",
                "size": "xs",
                "color": TEXT_SECONDARY,
                "wrap": True,
                "margin": "md",
            },
            _wallet_row(nickname),
        ],
        url,
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
) -> dict:
    rows = [
        _row("誓約額", f"{pledged_ada:,.0f} ADA", TEXT_PRIMARY),
        _row("実績", f"{live_ada:,.0f} ADA", TEXT_UP),
    ]
    if apy is not None:
        rows.append(_row("APY", f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header("誓約不足", "委任先プールの誓約が不足しています"),
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
            _wallet_row(nickname),
        ],
        url,
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
) -> dict:
    rows = [
        _row("対象エポック", f"Epoch {reward_epoch}", TEXT_PRIMARY),
        _row("報酬額", f"{amount_ada:,.4f} ADA", TEXT_DOWN),
    ]
    if apy is not None:
        rows.append(_row("APY", f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header("報酬受取", f"Epoch {reward_epoch} 分の報酬が入金されました"),
        [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": rows,
            },
            _wallet_row(nickname),
        ],
        url,
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
) -> dict:
    rows = [
        _row("委任先プール", pool_name, TEXT_PRIMARY),
        _row("委任からの経過", f"{days}日", TEXT_WARN),
    ]
    if apy is not None:
        rows.append(_row("APY", f"{apy:.2f}%", TEXT_APY))

    return _bubble(
        _header("委任先リマインダー", "委任先プールを確認しましょう"),
        [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": rows,
            },
            _wallet_row(nickname),
        ],
        url,
    )


# ============================================================
# drep_new_governance_action
# ============================================================

def drep_new_governance_action(
    proposal_type: str,
    url: str,
) -> dict:
    return _bubble(
        _header("新しいガバナンスアクション", "新しい提案が提出されました"),
        [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    _row("種類", proposal_type, TEXT_PRIMARY),
                ],
            },
            {
                "type": "text",
                "text": "ガバナンスページで詳細を確認できます",
                "size": "xs",
                "color": TEXT_SECONDARY,
                "wrap": True,
                "margin": "md",
            },
        ],
        url,
        "ガバナンスを確認する",
    )


# ============================================================
# drep_vote
# ============================================================

def drep_vote(
    drep_name: str,
    vote_label: str,
    proposal_title: str | None,
    nickname: str,
    url: str,
) -> dict:
    vote_colors = {"賛成": TEXT_DOWN, "反対": TEXT_UP, "棄権": TEXT_SECONDARY}
    vote_color = vote_colors.get(vote_label, TEXT_PRIMARY)

    rows = []
    if proposal_title:
        rows.append(_row("ガバナンスアクション", proposal_title, TEXT_PRIMARY))
    rows.append(_row("投票", vote_label, vote_color))

    return _bubble(
        _header("DRep投票通知", "委任先DRepが投票しました"),
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
            _wallet_row(nickname),
        ],
        url,
        "ガバナンスを確認する",
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
) -> dict:
    return _bubble(
        _header("DRepステータス変更", "委任先DRepのステータスが変わりました"),
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
                    _row("ステータス", f"{old_status} → {new_status}", TEXT_WARN),
                ],
            },
            _wallet_row(nickname),
        ],
        url,
    )


# ============================================================
# drep_delegation_reminder
# ============================================================

def drep_delegation_reminder(
    drep_name: str,
    days: int,
    nickname: str,
    url: str,
) -> dict:
    return _bubble(
        _header("DRep委任リマインダー", "委任先DRepを確認しましょう"),
        [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    _row("委任先DRep", drep_name, TEXT_PRIMARY),
                    _row("委任からの経過", f"{days}日", TEXT_WARN),
                ],
            },
            _wallet_row(nickname),
        ],
        url,
        "ガバナンスを確認する",
    )
