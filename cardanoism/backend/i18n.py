"""
i18n.py
多言語対応翻訳辞書（日本語 / 英語）

使用方法:
  from cardanoism.backend.i18n import UI_JA, UI_EN, NOTIFICATION_LABELS_JA, NOTIFICATION_LABELS_EN
"""

# ============================================================
# 通知イベントラベル
# ============================================================

NOTIFICATION_LABELS_JA: dict[str, str] = {
    "pool_retire": "プールリタイア",
    "pool_fee_change": "手数料変更",
    "pool_saturation": "飽和ライン超過",
    "pool_pledge_shortage": "誓約不足",
    "pool_reward_received": "報酬受取",
    "pool_epoch_performance": "エポック実績",
    "pool_delegation_reminder": "長期委任リマインダー（90/120/365日）",
    "drep_vote": "委任先DRepの投票通知",
    "drep_status_change": "委任先DRepのステータス変化",
    "drep_delegation_reminder": "長期委任リマインダー（90/120/365日）",
    "drep_new_governance_action": "新しいガバナンスアクション",
    "drep_unvoted_1week": "未投票リマインダー（1週間経過）",
    "drep_unvoted_2weeks": "未投票リマインダー（2週間経過）",
    "epoch_start": "エポックスタート",
}

NOTIFICATION_LABELS_EN: dict[str, str] = {
    "pool_retire": "Pool Retirement",
    "pool_fee_change": "Fee Change",
    "pool_saturation": "Saturation Exceeded",
    "pool_pledge_shortage": "Pledge Shortage",
    "pool_reward_received": "Reward Received",
    "pool_epoch_performance": "Epoch Performance",
    "pool_delegation_reminder": "Delegation Reminder (90/120/365 days)",
    "drep_vote": "Delegated DRep Vote",
    "drep_status_change": "Delegated DRep Status Change",
    "drep_delegation_reminder": "Delegation Reminder (90/120/365 days)",
    "drep_new_governance_action": "New Governance Action",
    "drep_unvoted_1week": "Unvoted Reminder (1 week)",
    "drep_unvoted_2weeks": "Unvoted Reminder (2 weeks)",
    "epoch_start": "Epoch Start",
}


# ============================================================
# UI テキスト
# ============================================================

UI_JA: dict[str, str] = {
    # タブ
    "tab_favorites": "お気に入り",
    "tab_profile": "プロフィール",
    "tab_stake": "アドレス",
    "tab_notification": "通知管理",

    # お気に入りタブ
    "filter_fund_placeholder": "Fund で絞り込み",
    "filter_status_placeholder": "ステータスで絞り込み",
    "filter_all": "すべて",
    "status_funded": "採択",
    "status_not_funded": "未採択",
    "status_over_budget": "予算超過",
    "sort_amount_desc": "要求金額（高い順）",
    "sort_amount_asc": "要求金額（低い順）",
    "favorites_empty": "お気に入りはありません",

    # プロフィールタブ
    "display_name": "表示名",
    "email_address": "メールアドレス",
    "save": "保存",
    "saved": "保存しました",
    "language": "言語",
    "lang_ja": "日本語",
    "lang_en": "English",

    # ステークアドレスタブ
    "stake_tab_desc": "登録したアドレスのイベントを通知します。最大3件まで登録できます。",
    "stake_empty": "登録されたステークアドレスはありません",
    "stake_role_loading": "委任先情報を確認中...",
    "stake_new_title": "新規登録",
    "stake_nickname_label": "ニックネーム",
    "stake_nickname_placeholder": "メインウォレット",
    "stake_address_label": "受信アドレス",
    "stake_address_hint": "ウォレットの受信アドレスを入力するとステークアドレスを自動取得します",
    "stake_add_button": "追加",
    "stake_limit_message": "ステークアドレスの登録上限（3件）に達しています。",

    # エラーメッセージ
    "err_addr_required": "アドレスとニックネームを入力してください",
    "err_invalid_addr": "有効な受信アドレス（addr1...）を入力してください",
    "err_stake_not_found": "ステークアドレスを取得できませんでした（エンタープライズアドレスは非対応）",
    "err_duplicate": "このステークアドレスはすでに登録されています",
    "err_limit": "登録できるステークアドレスは最大3件です",

    # 通知チャンネル選択
    "notification_channel_title": "通知チャンネル",
    "notification_channel_desc": "通知を受け取るチャンネルをON/OFFで選択してください。",
    "notification_channel_email": "メール通知",
    "notification_channel_line": "LINE通知",

    # 通知管理タブ
    "notification_tab_line_title": "LINE通知連携",
    "notification_tab_line_connected": "LINE通知連携済みです。",
    "notification_tab_line_friend_hint": "通知を受け取るには、Cardanoism公式LINEアカウントを友だち追加してください。",
    "notification_tab_line_connect_button": "LINEと連携する",
    "notification_tab_line_disconnect_button": "連携を解除する",
    "notification_tab_line_not_connected": "LINEと連携すると、イベント発生時にLINEで通知を受け取れます。",
    "notification_tab_no_stake": "ステークアドレスを登録すると、アドレスごとに通知を設定できます。",
    "notification_tab_per_addr_title": "アドレスごとの通知設定",
    "notification_pool_label": "委任プール",
    "notification_drep_label": "委任DRep",
    "notification_pool_section": "ステークプール通知",
    "notification_pool_undelegated": "ステークプールに委任していないため、プール関連の通知はありません",
    "notification_governance_section": "ガバナンス通知",
    "badge_drep": "DRep",
    "badge_abstain": "棄権",
    "badge_delegator": "委任者",
    "drep_abstain_notice": "ガバナンス投票を棄権中のため、DRep関連の通知はありません",
    "drep_abstain_explanation": "Cardanoは分散型ガバナンスへ移行しており、トレジャリーの使途や各種提案はDRepの投票によって決まります。あなたのADAも、1ADA＝1票としてその意思決定に活かすことができます。まだ委任していない方は、ぜひDRepへの委任をご検討ください。",
    "drep_undelegated_notice": "DRepに委任していないため、DRep関連の通知はありません",
    "notification_general_title": "一般通知",

    # 未ログイン
    "login_required": "マイページを利用するにはログインが必要です",
    "login_button": "ログインする",
}

UI_EN: dict[str, str] = {
    # Tabs
    "tab_favorites": "Favorites",
    "tab_profile": "Profile",
    "tab_stake": "Addresses",
    "tab_notification": "Notifications",

    # Favorites tab
    "filter_fund_placeholder": "Filter by Fund",
    "filter_status_placeholder": "Filter by Status",
    "filter_all": "All",
    "status_funded": "Funded",
    "status_not_funded": "Not Funded",
    "status_over_budget": "Over Budget",
    "sort_amount_desc": "Amount (High to Low)",
    "sort_amount_asc": "Amount (Low to High)",
    "favorites_empty": "No favorites yet",

    # Profile tab
    "display_name": "Display Name",
    "email_address": "Email Address",
    "save": "Save",
    "saved": "Saved",
    "language": "Language",
    "lang_ja": "日本語",
    "lang_en": "English",

    # Stake tab
    "stake_tab_desc": "Receive notifications for registered addresses. Up to 3 addresses can be registered.",
    "stake_empty": "No stake addresses registered",
    "stake_role_loading": "Checking delegation info...",
    "stake_new_title": "Add New",
    "stake_nickname_label": "Nickname",
    "stake_nickname_placeholder": "Main Wallet",
    "stake_address_label": "Receive Address",
    "stake_address_hint": "Enter your wallet's receive address to automatically detect the stake address",
    "stake_add_button": "Add",
    "stake_limit_message": "Maximum stake address limit (3) reached.",

    # Error messages
    "err_addr_required": "Please enter an address and nickname",
    "err_invalid_addr": "Please enter a valid receive address (addr1...)",
    "err_stake_not_found": "Could not retrieve stake address (enterprise addresses are not supported)",
    "err_duplicate": "This stake address is already registered",
    "err_limit": "You can register up to 3 stake addresses",

    # Notification channels
    "notification_channel_title": "Notification Channels",
    "notification_channel_desc": "Select which channels you want to receive notifications through.",
    "notification_channel_email": "Email Notifications",
    "notification_channel_line": "LINE Notifications",

    # Notification tab
    "notification_tab_line_title": "LINE Notifications",
    "notification_tab_line_connected": "LINE notifications connected.",
    "notification_tab_line_friend_hint": "Add the Cardanoism official LINE account as a friend to receive notifications.",
    "notification_tab_line_connect_button": "Connect with LINE",
    "notification_tab_line_disconnect_button": "Disconnect",
    "notification_tab_line_not_connected": "Connect with LINE to receive event notifications via LINE.",
    "notification_tab_no_stake": "Register a stake address to configure notifications per address.",
    "notification_tab_per_addr_title": "Notification Settings per Address",
    "notification_pool_label": "Pool",
    "notification_drep_label": "DRep",
    "notification_pool_section": "Stake Pool Notifications",
    "notification_pool_undelegated": "Not delegated to a pool; no pool notifications available",
    "notification_governance_section": "Governance Notifications",
    "badge_drep": "DRep",
    "badge_abstain": "Abstain",
    "badge_delegator": "Delegator",
    "drep_abstain_notice": "Abstaining from governance voting; no DRep notifications available",
    "drep_abstain_explanation": "Cardano has transitioned to decentralized governance. Treasury spending and protocol changes are decided by DRep votes. Your ADA counts as 1 vote. If you haven't delegated yet, consider delegating to a DRep.",
    "drep_undelegated_notice": "Not delegated to a DRep; no DRep notifications available",
    "notification_general_title": "General Notifications",

    # Not logged in
    "login_required": "Login required to use My Page",
    "login_button": "Log In",
}


def get_ui(lang: str) -> dict[str, str]:
    return UI_EN if lang == "en" else UI_JA


def get_notification_labels(lang: str) -> dict[str, str]:
    return NOTIFICATION_LABELS_EN if lang == "en" else NOTIFICATION_LABELS_JA


# ============================================================
# LINE Flex Message テキスト
# ============================================================

FLEX_JA: dict[str, str] = {
    "footer_open": "Cardanoism を開く",
    "footer_governance": "ガバナンスを確認する",
    "wallet": "ウォレット",

    # epoch_start
    "epoch_start_title": "新エポック開始",
    "epoch_start_subtitle": "Epoch {epoch} が始まりました",
    "epoch_start_body": "新しいエポックが始まりました",

    # pool_retire
    "pool_retire_title": "プールリタイア通知",
    "pool_retire_subtitle": "委任先プールが引退予告を出しました",
    "pool_retire_epoch_label": "リタイア予定エポック",
    "pool_retire_hint": "新しいプールへの委任をご検討ください",

    # pool_fee_change
    "pool_fee_change_title": "手数料変更通知",
    "pool_fee_change_subtitle": "委任先プールの手数料が変更されました",
    "pool_fee_variable_label": "変動手数料",
    "pool_fee_fixed_label": "固定費",
    "pool_fee_fixed_unit": "ADA",
    "pool_fee_pledge_label": "誓約",

    # pool_saturation
    "pool_saturation_title": "飽和ライン超過",
    "pool_saturation_subtitle": "委任先プールが飽和ラインを超えました",
    "pool_saturation_label": "飽和度",
    "pool_saturation_hint": "報酬効率が下がる可能性があります",

    # pool_epoch_performance
    "pool_epoch_perf_title": "エポック実績通知",
    "pool_epoch_perf_subtitle": "前エポックのプール実績です",
    "pool_epoch_perf_epoch_label": "エポック",
    "pool_epoch_perf_active_stake_label": "有効ステーク",
    "pool_epoch_perf_saturation_label": "飽和度",
    "pool_epoch_perf_blocks_label": "ブロック生成数",
    "pool_epoch_perf_apy_label": "APY（実績）",

    # pool_pledge_shortage
    "pool_pledge_shortage_title": "誓約不足",
    "pool_pledge_shortage_subtitle": "委任先プールの誓約が不足しています",
    "pool_pledge_label": "誓約額",
    "pool_pledge_live_label": "実績",
    "pool_pledge_unit": "ADA",

    # pool_reward_received
    "pool_reward_title": "報酬受取",
    "pool_reward_subtitle": "Epoch {epoch} 分の報酬が入金されました",
    "pool_reward_epoch_label": "対象エポック",
    "pool_reward_amount_label": "報酬額",

    # pool_delegation_reminder
    "pool_remind_title": "委任先リマインダー",
    "pool_remind_subtitle": "委任先プールを確認しましょう",
    "pool_remind_pool_label": "委任先プール",
    "pool_remind_days_label": "委任からの経過",
    "pool_remind_days_value": "{days}日",

    # drep_new_governance_action
    "drep_new_gov_title": "新しいガバナンスアクション",
    "drep_new_gov_subtitle": "新しい提案が提出されました",
    "drep_new_gov_type_label": "種類",
    "drep_new_gov_hint": "ガバナンスページで詳細を確認できます",

    # drep_vote
    "drep_vote_title": "DRep投票通知",
    "drep_vote_subtitle": "委任先DRepが投票しました",
    "drep_vote_action_label": "ガバナンスアクション",
    "drep_vote_label": "投票",
    "vote_yes": "賛成",
    "vote_no": "反対",
    "vote_abstain": "棄権",

    # drep_status_change
    "drep_status_title": "DRepステータス変更",
    "drep_status_subtitle": "委任先DRepのステータスが変わりました",
    "drep_status_label": "ステータス",

    # drep_delegation_reminder
    "drep_remind_title": "DRep委任リマインダー",
    "drep_remind_subtitle": "委任先DRepを確認しましょう",
    "drep_remind_drep_label": "委任先DRep",
    "drep_remind_days_label": "委任からの経過",
    "drep_remind_days_value": "{days}日",

    # APY
    "apy_label": "APY",
}

FLEX_EN: dict[str, str] = {
    "footer_open": "Open Cardanoism",
    "footer_governance": "Check Governance",
    "wallet": "Wallet",

    # epoch_start
    "epoch_start_title": "New Epoch Started",
    "epoch_start_subtitle": "Epoch {epoch} has started",
    "epoch_start_body": "A new epoch has started",

    # pool_retire
    "pool_retire_title": "Pool Retirement Notice",
    "pool_retire_subtitle": "Your delegated pool has announced retirement",
    "pool_retire_epoch_label": "Retirement Epoch",
    "pool_retire_hint": "Please consider delegating to a new pool",

    # pool_fee_change
    "pool_fee_change_title": "Fee Change Notice",
    "pool_fee_change_subtitle": "Your delegated pool's fee has changed",
    "pool_fee_variable_label": "Variable Fee",
    "pool_fee_fixed_label": "Fixed Fee",
    "pool_fee_fixed_unit": "ADA",
    "pool_fee_pledge_label": "Pledge",

    # pool_epoch_performance
    "pool_epoch_perf_title": "Epoch Performance",
    "pool_epoch_perf_subtitle": "Previous epoch pool performance",
    "pool_epoch_perf_epoch_label": "Epoch",
    "pool_epoch_perf_active_stake_label": "Active Stake",
    "pool_epoch_perf_saturation_label": "Saturation",
    "pool_epoch_perf_blocks_label": "Blocks Minted",
    "pool_epoch_perf_apy_label": "APY (actual)",

    # pool_saturation
    "pool_saturation_title": "Saturation Exceeded",
    "pool_saturation_subtitle": "Your delegated pool has exceeded saturation",
    "pool_saturation_label": "Saturation",
    "pool_saturation_hint": "Reward efficiency may decrease",

    # pool_pledge_shortage
    "pool_pledge_shortage_title": "Pledge Shortage",
    "pool_pledge_shortage_subtitle": "Your delegated pool has insufficient pledge",
    "pool_pledge_label": "Pledge",
    "pool_pledge_live_label": "Actual",
    "pool_pledge_unit": "ADA",

    # pool_reward_received
    "pool_reward_title": "Reward Received",
    "pool_reward_subtitle": "Rewards for Epoch {epoch} have arrived",
    "pool_reward_epoch_label": "Epoch",
    "pool_reward_amount_label": "Reward",

    # pool_delegation_reminder
    "pool_remind_title": "Delegation Reminder",
    "pool_remind_subtitle": "Please check your delegated pool",
    "pool_remind_pool_label": "Delegated Pool",
    "pool_remind_days_label": "Days Since Delegation",
    "pool_remind_days_value": "{days} days",

    # drep_new_governance_action
    "drep_new_gov_title": "New Governance Action",
    "drep_new_gov_subtitle": "A new proposal has been submitted",
    "drep_new_gov_type_label": "Type",
    "drep_new_gov_hint": "Check details on the Governance page",

    # drep_vote
    "drep_vote_title": "DRep Vote Notification",
    "drep_vote_subtitle": "Your delegated DRep has voted",
    "drep_vote_action_label": "Governance Action",
    "drep_vote_label": "Vote",
    "vote_yes": "Yes",
    "vote_no": "No",
    "vote_abstain": "Abstain",

    # drep_status_change
    "drep_status_title": "DRep Status Change",
    "drep_status_subtitle": "Your delegated DRep's status has changed",
    "drep_status_label": "Status",

    # drep_delegation_reminder
    "drep_remind_title": "DRep Delegation Reminder",
    "drep_remind_subtitle": "Please check your delegated DRep",
    "drep_remind_drep_label": "Delegated DRep",
    "drep_remind_days_label": "Days Since Delegation",
    "drep_remind_days_value": "{days} days",

    # APY
    "apy_label": "APY",
}


def get_flex(lang: str) -> dict[str, str]:
    return FLEX_EN if lang == "en" else FLEX_JA
