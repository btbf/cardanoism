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
    "treasury_withdrawal_enacted": "トレジャリー引き出し実行",
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
    "treasury_withdrawal_enacted": "Treasury Withdrawal Enacted",
}


# ============================================================
# UI テキスト
# ============================================================

UI_JA: dict[str, str] = {
    # ナビバー
    "nav_home": "ホーム",
    "nav_catalyst": "カタリスト",
    "nav_proposals_list": "提案一覧",
    "nav_funds_list": "ファンド一覧",
    "nav_governance": "ガバナンス",
    "nav_mypage": "マイページ",
    "nav_logout": "ログアウト",
    "nav_login": "ログイン",

    # カタリストページ
    "catalyst_search_placeholder": "キーワードを入力...(タイトル、タグ、提案者名など)",
    "catalyst_filter_expand": "さらに絞り込む",
    "catalyst_filter_fund": "対象ファンドを選択してください",
    "catalyst_filter_challenge": "チャレンジを選択",
    "catalyst_filter_funding_status": "資金調達ステータス",
    "catalyst_filter_project_status": "プロジェクト進捗",
    "catalyst_search_results": "検索結果",
    "catalyst_results_unit": "件",
    "catalyst_no_proposals": "提案が見つかりませんでした",

    # 提案ステータスバッジ
    "badge_in_progress": "進行中",
    "badge_complete": "完了",
    "badge_funded_label": "採択",
    "badge_not_approved": "不採択",
    "badge_over_budget": "申請不備",
    "badge_pending_vote": "投票期間中",

    # 提案カード・モーダル
    "funding_rate_label": "資金調達率",
    "view_milestones": "進捗状況を見る",
    "proposal_view_raw": "英語原文",
    "proposal_view_ja": "日本語翻訳",
    "proposal_view_ai": "AI要約",
    "proposal_section_problem": "課題",
    "proposal_section_solution": "解決策",
    "proposal_close": "閉じる",
    "proposal_share": "シェア",
    "proposal_copy_url": "URLコピー",
    "proposal_url_copied": "提案リンクをコピーしました",
    "score_alignment": "提案整合性",
    "score_feasibility": "実現可能性",
    "score_auditability": "監査可能性",
    "votes_wallet_tooltip": "投票ウォレット数",
    "votes_yes_tooltip": "賛成票数",
    "votes_abstain_tooltip": "棄権票数",
    "votes_wallet_label": "投票",
    "votes_yes_label": "賛成",
    "votes_abstain_label": "棄権",

    # ガバナンスページ
    "gov_breadcrumb_detail": "詳細",
    "gov_filter_type_placeholder": "アクションタイプ",
    "gov_filter_status_placeholder": "批准ステータス",
    "gov_filter_search_placeholder": "キーワードを検索...(タイトル、概要)",
    "gov_filter_expand": "さらに絞り込む",
    "gov_search_results": "検索結果",
    "gov_results_unit": "件",
    "gov_no_results": "ガバナンスアクションが見つかりませんでした",
    "gov_type_parameter_change": "プロトコル変更",
    "gov_type_treasury_withdrawals": "国庫引き出し",
    "gov_type_hard_fork": "ハードフォーク",
    "gov_type_info_action": "情報提案",
    "gov_type_new_committee": "委員会変更",
    "gov_type_new_constitution": "新憲法",
    "gov_type_no_confidence": "不信任",
    "gov_status_active": "アクティブ",
    "gov_status_ratified": "批准済み",
    "gov_status_enacted": "施行済み",
    "gov_status_dropped": "廃止",
    "gov_status_expired": "失効",
    "gov_title_none": "（タイトルなし）",
    "gov_proposed_epoch_label": "提案: ",
    "gov_expiration_label": "期限: ",
    "gov_deposit_label": "デポジット: ",
    "gov_section_abstract": "概要",
    "gov_section_motivation": "動機",
    "gov_section_rationale": "根拠",
    "gov_section_refs": "参考リンク",
    "gov_current_constitution":    "現行憲法",
    "gov_constitution_in_force":   "施行中",
    "gov_constitution_enacted_label": "施行エポック:",
    "gov_constitution_view_detail": "詳細を見る",
    "gov_constitution_open_source": "原文を開く",
    "gov_section_withdrawal": "国庫引き出し額",
    "gov_withdrawal_total_label": "合計",
    "gov_withdrawal_breakdown": "内訳",
    "gov_section_votes": "投票状況",
    "gov_anchor_votes":  "投票状況へ",
    "gov_section_voting_summary": "投票集計",
    "gov_voter_drep":    "DRep",
    "gov_voter_cc":      "憲法委員会 (CC)",
    "gov_voter_spo":     "SPO",
    "gov_vote_threshold_label": "批准閾値:",
    "gov_vote_no_threshold":    "閾値なし",
    "gov_vote_passed":   "達成",
    "gov_vote_failed":   "未達",
    "gov_vote_not_applicable": "投票対象外",
    "gov_vote_conditional":    "セキュリティ関連のみ",
    "gov_vote_no_members":     "投票メンバーがいません",
    "gov_vote_not_voted":      "未投票",
    "gov_vote_col_role":      "ロール",
    "gov_vote_col_voter":     "投票者",
    "gov_vote_col_vote":      "投票",
    "gov_vote_col_time":      "日時",
    "gov_vote_col_rationale": "理由",
    "gov_vote_rationale_title":    "投票理由",
    "gov_vote_rationale_view":     "投票理由",
    "gov_vote_rationale_ja_label": "日本語訳",
    "gov_vote_rationale_en_label": "原文",
    "gov_vote_rationale_close":    "閉じる",
    "gov_modal_load_error": "詳細を読み込めませんでした",
    "gov_url_copied": "GAリンクをコピーしました",
    "gov_ref_no_label": "（ラベルなし）",

    # ガバナンス サブナビゲーション
    "gov_subnav_actions": "アクション一覧",
    "gov_subnav_drep": "DRep",
    "gov_subnav_treasury": "トレジャリー",

    # DRepページ
    "drep_search_placeholder": "DRep名または DRep ID を検索...",
    "drep_sort_amount_desc": "委任量（多い順）",
    "drep_sort_amount_asc":  "委任量（少ない順）",
    "drep_sort_name_asc":    "名前順",
    "drep_sort_active":      "アクティブ優先",
    "drep_status_active":    "アクティブ",
    "drep_status_inactive":  "非アクティブ",
    "drep_no_name":          "（名前未設定）",
    "drep_delegated_label":  "委任量:",
    "drep_total_delegation_label": "総委任量:",
    "drep_influence_label":  "影響力",
    "drep_id_copied":        "DRep ID をコピーしました",
    "drep_empty":            "DRep が見つかりませんでした",
    "drep_detail_breadcrumb": "詳細",
    "drep_not_found":        "指定された DRep が見つかりません",
    "drep_vote_total_label": "投票数",
    "drep_vote_history_title": "投票履歴",
    "drep_no_votes":         "投票履歴がありません",

    # トレジャリーページ
    "treasury_balance_title": "現在のトレジャリー残高",
    "treasury_epoch_label": "基準エポック:",
    "ncl_title": "Net Change Limit 消化状況",
    "ncl_period_label": "期間:",
    "ncl_spent_label": "引き出し済み",
    "ncl_remaining_label": "残り",
    "ncl_limit_label": "上限",
    "ncl_description": "Net Change Limit は憲法で定められたトレジャリーからの引き出し上限。DRep のアクティブ投票力の 50% 超の賛成で可決され、超過するガバナンスアクションは憲法委員会（CC）によって否決される。上記値は Koios から直近で過半数賛成を得た NCL 提案を自動採用。",
    "treasury_history_title": "引き出し履歴（直近100件）",
    "treasury_history_empty": "トレジャリー引き出しの履歴はありません",
    "treasury_col_earned_epoch": "獲得エポック",
    "treasury_col_spendable_epoch": "使用可能エポック",
    "treasury_col_amount": "金額",
    "treasury_col_stake_addr": "受取ステークアドレス",
    "treasury_load_error": "トレジャリー情報の取得に失敗しました",
    "ncl_not_available": "現在、DRep過半数賛成のNCL提案が存在しません。提案が可決され次第、自動で表示されます。",
    "ncl_pending_label": "引き出し確定",
    "ncl_simulation_label": "シミュレーション",
    "ncl_remaining_and_limit_label": "NCL枠残り / 上限",
    "ncl_simulation_hint": "下のアクティブ提案にチェックを入れると、バーに加算されます。",
    "ncl_simulation_select_all": "全選択",
    "ncl_simulation_clear": "選択解除",
    "ncl_legend_spent": "引き出し済み",
    "ncl_legend_pending": "引き出し確定",
    "ncl_legend_simulation": "シミュレーション",
    "ncl_legend_remaining": "残り",
    "ncl_proposal_proposed_label": "提案:",
    "ncl_proposal_enacted_label": "施行:",
    "ncl_proposals_empty": "NCL期間内のトレジャリー引き出し提案はありません。",
    "treasury_tab_proposals": "提案",
    "treasury_tab_history": "引き出し履歴",

    # インデックスページ
    "hero_daily_update": "提案データを毎日更新",
    "hero_governance_mgmt": "ガバナンス管理",
    "hero_staking_mgmt": "ステーキング管理",
    "hero_heading": "カルダノガバナンスを日本語でナビゲート",
    "hero_subtitle": "Catalyst提案検索からCardanoの意思決定を日本語でキャッチアップし、ガバナンス・ステーキングの管理をワンストップで扱えるプラットフォームへ進化させます。",
    "hero_cta_catalyst": "Catalyst提案を探す",
    "hero_cta_funds": "Fundの動きを見る",

    # フィーチャーセクション
    "feature_section_title": "Cardanoismのコア機能",
    "feature_section_subtitle": "プロダクトの進化軸を3つの視点で整理しました",
    "feature_catalyst_title": "カタリスト管理",
    "feature_catalyst_desc": "投票に必要なデータを集め、気になる提案をまとめて管理。",
    "feature_governance_title": "ガバナンス管理",
    "feature_governance_desc": "カルダノガバナンスを日本語で見える化し、委任先DRepの投票状況も通知。",
    "feature_staking_title": "ステーキング管理",
    "feature_staking_desc": "委任先ステークプールの運用状況をモニタし、異変をすぐ把握。",

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
    "notification_channel_telegram": "Telegram通知",

    # 通知管理タブ
    "notification_tab_line_title": "LINE通知連携",
    "notification_tab_line_connected": "LINE通知連携済みです。",
    "notification_tab_line_friend_hint": "通知を受け取るには、Cardanoism公式LINEアカウントを友だち追加してください。",
    "notification_tab_line_connect_button": "LINEと連携する",
    "notification_tab_line_disconnect_button": "連携を解除する",
    "notification_tab_line_not_connected": "LINEと連携すると、イベント発生時にLINEで通知を受け取れます。",
    "notification_tab_telegram_title": "Telegram通知連携",
    "notification_tab_telegram_connected": "Telegram通知連携済みです。",
    "notification_tab_telegram_connect_button": "Telegramで連携する",
    "notification_tab_telegram_reload_button": "連携済み！ページを更新",
    "notification_tab_telegram_disconnect_button": "連携を解除する",
    "notification_tab_telegram_not_connected": "Telegramと連携すると、イベント発生時にTelegramで通知を受け取れます。",
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

    # ログインページ・モーダル
    "login_page_title": "ログイン",
    "login_page_desc": "マイページ・お気に入り・通知機能を利用するにはログインが必要です。",
    "login_modal_desc": "ログインしてマイページ・お気に入り・通知機能を利用できます。",
    "login_line": "LINEでログイン",
    "login_google": "Googleでログイン",
    "login_x": "Xでログイン",
    "login_back_to_top": "← トップページに戻る",
    "login_close": "閉じる",
}

UI_EN: dict[str, str] = {
    # Navbar
    "nav_home": "Home",
    "nav_catalyst": "Catalyst",
    "nav_proposals_list": "Proposals",
    "nav_funds_list": "Funds",
    "nav_governance": "Governance",
    "nav_mypage": "My Page",
    "nav_logout": "Logout",
    "nav_login": "Login",

    # Catalyst page
    "catalyst_search_placeholder": "Search... (title, tag, proposer name, etc.)",
    "catalyst_filter_expand": "More filters",
    "catalyst_filter_fund": "Select fund",
    "catalyst_filter_challenge": "Select challenge",
    "catalyst_filter_funding_status": "Funding status",
    "catalyst_filter_project_status": "Project status",
    "catalyst_search_results": "Results",
    "catalyst_results_unit": "",
    "catalyst_no_proposals": "No proposals found",

    # Proposal status badges
    "badge_in_progress": "In Progress",
    "badge_complete": "Complete",
    "badge_funded_label": "Funded",
    "badge_not_approved": "Not Approved",
    "badge_over_budget": "Over Budget",
    "badge_pending_vote": "Pending Vote",

    # Proposal card / modal
    "funding_rate_label": "Funding Rate",
    "view_milestones": "View Progress",
    "proposal_view_raw": "Original (EN)",
    "proposal_view_ja": "Japanese (JA)",
    "proposal_view_ai": "AI Summary",
    "proposal_section_problem": "Problem",
    "proposal_section_solution": "Solution",
    "proposal_close": "Close",
    "proposal_share": "Share",
    "proposal_copy_url": "Copy URL",
    "proposal_url_copied": "Link copied",
    "score_alignment": "Alignment",
    "score_feasibility": "Feasibility",
    "score_auditability": "Auditability",
    "votes_wallet_tooltip": "Voting wallets",
    "votes_yes_tooltip": "Yes votes",
    "votes_abstain_tooltip": "Abstain votes",
    "votes_wallet_label": "Votes",
    "votes_yes_label": "Yes",
    "votes_abstain_label": "Abstain",

    # Governance page
    "gov_breadcrumb_detail": "Detail",
    "gov_filter_type_placeholder": "Action Type",
    "gov_filter_status_placeholder": "Ratification Status",
    "gov_filter_search_placeholder": "Search keywords... (title, abstract)",
    "gov_filter_expand": "More filters",
    "gov_search_results": "Results",
    "gov_results_unit": "",
    "gov_no_results": "No governance actions found",
    "gov_type_parameter_change": "Protocol Change",
    "gov_type_treasury_withdrawals": "Treasury Withdrawals",
    "gov_type_hard_fork": "Hard Fork",
    "gov_type_info_action": "Info Action",
    "gov_type_new_committee": "Committee Change",
    "gov_type_new_constitution": "New Constitution",
    "gov_type_no_confidence": "No Confidence",
    "gov_status_active": "Active",
    "gov_status_ratified": "Ratified",
    "gov_status_enacted": "Enacted",
    "gov_status_dropped": "Dropped",
    "gov_status_expired": "Expired",
    "gov_title_none": "(No title)",
    "gov_proposed_epoch_label": "Proposed: ",
    "gov_expiration_label": "Expires: ",
    "gov_deposit_label": "Deposit: ",
    "gov_section_abstract": "Abstract",
    "gov_section_motivation": "Motivation",
    "gov_section_rationale": "Rationale",
    "gov_section_refs": "References",
    "gov_current_constitution":    "Current Constitution",
    "gov_constitution_in_force":   "In force",
    "gov_constitution_enacted_label": "Enacted epoch:",
    "gov_constitution_view_detail": "View details",
    "gov_constitution_open_source": "Open source",
    "gov_section_withdrawal": "Treasury Withdrawal",
    "gov_withdrawal_total_label": "Total",
    "gov_withdrawal_breakdown": "Breakdown",
    "gov_section_votes": "Votes",
    "gov_anchor_votes":  "Jump to Votes",
    "gov_section_voting_summary": "Voting Summary",
    "gov_voter_drep":    "DRep",
    "gov_voter_cc":      "Constitutional Committee",
    "gov_voter_spo":     "SPO",
    "gov_vote_threshold_label": "Threshold:",
    "gov_vote_no_threshold":    "No threshold",
    "gov_vote_passed":   "Passed",
    "gov_vote_failed":   "Failed",
    "gov_vote_not_applicable": "Not applicable",
    "gov_vote_conditional":    "Security only",
    "gov_vote_no_members":     "No voting members",
    "gov_vote_not_voted":      "Not voted",
    "gov_vote_col_role":      "Role",
    "gov_vote_col_voter":     "Voter",
    "gov_vote_col_vote":      "Vote",
    "gov_vote_col_time":      "Time",
    "gov_vote_col_rationale": "Rationale",
    "gov_vote_rationale_title":    "Vote Rationale",
    "gov_vote_rationale_view":     "Rationale",
    "gov_vote_rationale_ja_label": "Japanese",
    "gov_vote_rationale_en_label": "Original",
    "gov_vote_rationale_close":    "Close",
    "gov_modal_load_error": "Failed to load details",
    "gov_url_copied": "Link copied",
    "gov_ref_no_label": "(No label)",

    # Governance subnav
    "gov_subnav_actions": "Actions",
    "gov_subnav_drep": "DReps",
    "gov_subnav_treasury": "Treasury",

    # DRep page
    "drep_search_placeholder": "Search by DRep name or DRep ID...",
    "drep_sort_amount_desc": "Delegation (desc)",
    "drep_sort_amount_asc":  "Delegation (asc)",
    "drep_sort_name_asc":    "Name",
    "drep_sort_active":      "Active first",
    "drep_status_active":    "Active",
    "drep_status_inactive":  "Inactive",
    "drep_no_name":          "(No name)",
    "drep_delegated_label":  "Delegated:",
    "drep_total_delegation_label": "Total Delegation:",
    "drep_influence_label":  "Influence",
    "drep_id_copied":        "DRep ID copied",
    "drep_empty":            "No DReps found",
    "drep_detail_breadcrumb": "Detail",
    "drep_not_found":        "DRep not found",
    "drep_vote_total_label": "Votes",
    "drep_vote_history_title": "Voting History",
    "drep_no_votes":         "No voting history",

    # Treasury page
    "treasury_balance_title": "Current Treasury Balance",
    "treasury_epoch_label": "Reference Epoch:",
    "ncl_title": "Net Change Limit Usage",
    "ncl_period_label": "Period:",
    "ncl_spent_label": "Withdrawn",
    "ncl_remaining_label": "Remaining",
    "ncl_limit_label": "Limit",
    "ncl_description": "The Net Change Limit is the treasury withdrawal cap defined by the constitution. It is ratified when the DRep active voting stake votes >50% in favor. Governance actions exceeding it are voted down by the Constitutional Committee. The value above is sourced automatically from the most recent NCL proposal ratified by DRep majority on Koios.",
    "treasury_history_title": "Withdrawal History (latest 100)",
    "treasury_history_empty": "No treasury withdrawals yet",
    "treasury_col_earned_epoch": "Earned Epoch",
    "treasury_col_spendable_epoch": "Spendable Epoch",
    "treasury_col_amount": "Amount",
    "treasury_col_stake_addr": "Receiving Stake Address",
    "treasury_load_error": "Failed to load treasury data",
    "ncl_not_available": "No NCL proposal currently has DRep majority support. The page will auto-update once one is ratified.",
    "ncl_pending_label": "Confirmed",
    "ncl_simulation_label": "Simulation",
    "ncl_remaining_and_limit_label": "NCL Remaining / Limit",
    "ncl_simulation_hint": "Check active proposals below to add them to the bar.",
    "ncl_simulation_select_all": "Select all",
    "ncl_simulation_clear": "Clear selection",
    "ncl_legend_spent": "Withdrawn",
    "ncl_legend_pending": "Confirmed",
    "ncl_legend_simulation": "Simulation",
    "ncl_legend_remaining": "Remaining",
    "ncl_proposal_proposed_label": "Proposed:",
    "ncl_proposal_enacted_label": "Enacted:",
    "ncl_proposals_empty": "No treasury withdrawal proposals within the NCL period.",
    "treasury_tab_proposals": "Proposals",
    "treasury_tab_history": "Withdrawal History",

    # Index page
    "hero_daily_update": "Daily proposal updates",
    "hero_governance_mgmt": "Governance management",
    "hero_staking_mgmt": "Staking management",
    "hero_heading": "Navigate Cardano Governance",
    "hero_subtitle": "Catch up on Cardano's decision-making through Catalyst proposal search, and evolve into a one-stop platform for managing governance and staking.",
    "hero_cta_catalyst": "Browse Catalyst",
    "hero_cta_funds": "View Fund Activity",

    # Feature section
    "feature_section_title": "Core Features",
    "feature_section_subtitle": "Three pillars driving the product evolution",
    "feature_catalyst_title": "Catalyst Management",
    "feature_catalyst_desc": "Collect data needed for voting and manage your favorite proposals.",
    "feature_governance_title": "Governance Management",
    "feature_governance_desc": "Visualize Cardano governance and get notified of your delegated DRep's voting activity.",
    "feature_staking_title": "Staking Management",
    "feature_staking_desc": "Monitor your delegated stake pool's performance and catch anomalies early.",

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
    "notification_channel_telegram": "Telegram Notifications",

    # Notification tab
    "notification_tab_line_title": "LINE Notifications",
    "notification_tab_line_connected": "LINE notifications connected.",
    "notification_tab_line_friend_hint": "Add the Cardanoism official LINE account as a friend to receive notifications.",
    "notification_tab_line_connect_button": "Connect with LINE",
    "notification_tab_line_disconnect_button": "Disconnect",
    "notification_tab_line_not_connected": "Connect with LINE to receive event notifications via LINE.",
    "notification_tab_telegram_title": "Telegram Notifications",
    "notification_tab_telegram_connected": "Telegram notifications connected.",
    "notification_tab_telegram_connect_button": "Connect with Telegram",
    "notification_tab_telegram_reload_button": "Connected! Reload status",
    "notification_tab_telegram_disconnect_button": "Disconnect",
    "notification_tab_telegram_not_connected": "Connect with Telegram to receive event notifications via Telegram.",
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

    # Login page / modal
    "login_page_title": "Login",
    "login_page_desc": "Login is required to use My Page, favorites, and notification features.",
    "login_modal_desc": "Log in to access My Page, favorites, and notification features.",
    "login_line": "Log in with LINE",
    "login_google": "Sign in with Google",
    "login_x": "Log in with X",
    "login_back_to_top": "← Back to top",
    "login_close": "Close",
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
