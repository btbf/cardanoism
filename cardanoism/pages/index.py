"""
index.py
TOP ページ (/) — Cardanoism の主要機能をモダンに紹介する。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.templates import template
from cardanoism import styles
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.home_state import HomeState
from cardanoism.backend.plan_config import BETA_MODE


# ─── ブランドカラー ──────────────────────────────────────────────────────────
ACCENT = "#ffcf00"
ACCENT_DARK = "#c7a300"
TEXT_MUTED = "var(--gray-10)"

# 機能ごとのアクセントカラー
F_AI     = "#7c5cff"   # 紫: AI 提案要約 + 投票マトリクス
F_WALLET = "#10b981"   # エメラルド: ウォレット連携
F_CAT    = "#eab308"   # 黄: Catalyst
F_CONST  = "#0ea5e9"   # 水色: 憲法
F_TRES   = "#16a34a"   # 緑: トレジャリー
F_NOTI   = "#f97316"   # オレンジ: ステーキング通知
# 旧カード用 (mock 関数で参照され続けている)
F_DREP   = "#3b82f6"   # 青: DRep
F_GA     = "#ec4899"   # ピンク: GA 日本語化
F_BLK   = "#e11d48"   # 赤: ライブブロック

LINE_BRAND = "#06C755"
TG_BRAND = "#2AABEE"
MAIL_BRAND = "#7c5cff"


HOME_CSS = f"""
<style>
h1, h2, h3, h4, h5, h6 {{ font-family: {styles.font_family}; }}

@keyframes cdn_float {{
  0%, 100% {{ transform: translateY(0); }}
  50%      {{ transform: translateY(-7px); }}
}}
@keyframes cdn_pulse {{
  0%, 100% {{ opacity: 0.55; transform: scale(1); }}
  50%      {{ opacity: 1; transform: scale(1.25); }}
}}
@keyframes cdn_block_drop {{
  0%   {{ transform: translateY(-12px); opacity: 0; }}
  60%  {{ transform: translateY(2px);  opacity: 1; }}
  100% {{ transform: translateY(0);    opacity: 1; }}
}}
@keyframes cdn_aurora {{
  0%   {{ transform: translate(0, 0) rotate(0deg); }}
  50%  {{ transform: translate(40px, -30px) rotate(180deg); }}
  100% {{ transform: translate(0, 0) rotate(360deg); }}
}}

/* hero 背景の動的グラデーション */
.cdn-hero-aurora {{
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}}
.cdn-hero-aurora::before,
.cdn-hero-aurora::after {{
  content: "";
  position: absolute;
  width: 720px;
  height: 720px;
  border-radius: 50%;
  filter: blur(110px);
  opacity: 0.45;
  animation: cdn_aurora 22s ease-in-out infinite;
}}
.cdn-hero-aurora::before {{
  top: -240px; right: -120px;
  background: radial-gradient(circle, rgba(255,207,0,0.55) 0%, transparent 70%);
}}
.cdn-hero-aurora::after {{
  bottom: -260px; left: -180px;
  background: radial-gradient(circle, rgba(124,92,255,0.40) 0%, transparent 70%);
  animation-delay: -11s;
}}

/* hero タイトルのグラデーション */
.cdn-gradient-text {{
  background: linear-gradient(135deg, #ffcf00 0%, #ff7e5f 50%, #7c5cff 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  -webkit-text-fill-color: transparent;
}}

.cdn-soft-card {{
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}}
.cdn-soft-card:hover {{ transform: translateY(-4px); }}

/* feature card のホバー時グロー */
.cdn-feature-card {{
  position: relative;
  overflow: hidden;
}}
.cdn-feature-card::before {{
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at top right, var(--cdn-feature-color, transparent), transparent 60%);
  opacity: 0;
  transition: opacity 0.25s ease;
  pointer-events: none;
}}
.cdn-feature-card:hover::before {{ opacity: 0.18; }}

/* mini live block animation */
.cdn-mini-block {{
  animation: cdn_block_drop 0.9s ease-out;
}}

/* スマホ mock スクリーンショット 3 枚クロスフェード (9s で 1 ループ、各 3s 表示) */
@keyframes cdn_slide_fade_3 {{
  0%, 100%       {{ opacity: 0; }}
  5.55%, 33.33%  {{ opacity: 1; }}
  38.88%         {{ opacity: 0; }}
}}
.cdn-slide-img {{
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  object-fit: contain;
  opacity: 0;
  animation: cdn_slide_fade_3 9s ease-in-out infinite;
}}
.cdn-slide-img-1 {{ animation-delay: -0.5s; }}
.cdn-slide-img-2 {{ animation-delay: 2.5s; }}
.cdn-slide-img-3 {{ animation-delay: 5.5s; }}
</style>
"""


def _shell(*children, **kw) -> rx.Component:
    # TOP の各セクションは width:100vw で背景を全幅に伸ばすため、template の
    # 1em パディングが効かない。スマホは _shell 側で 16px (template と同等) を
    # 持たせて、他ページと左右余白を揃える。
    base = dict(
        max_width="1180px",
        width="100%",
        margin_x="auto",
        padding_x=["16px", "28px", "40px"],
    )
    base.update(kw)
    return rx.box(*children, **base)


# ─── LINE スマホ mock ───────────────────────────────────────────────────────

def _line_msg_bubble(title_key: str, body_key: str, time_key: str) -> rx.Component:
    """LINE 風のメッセージバブル（公式アカウントからの受信）。"""
    return rx.hstack(
        # 公式アカウントのアバター
        rx.box(
            rx.text("C", size="2", weight="bold", color=ACCENT_DARK,
                    style={"lineHeight": "1"}),
            width="32px", height="32px",
            border_radius="999px",
            background="white",
            display="flex",
            align_items="center",
            justify_content="center",
            flex_shrink="0",
            box_shadow="0 1px 2px rgba(0,0,0,0.15)",
        ),
        rx.vstack(
            rx.text(
                "Cardanoism",
                size="1",
                color="rgba(255,255,255,0.92)",
                weight="medium",
                style={"fontSize": "10px",
                       "textShadow": "0 1px 2px rgba(0,0,0,0.25)"},
            ),
            rx.hstack(
                rx.box(
                    rx.vstack(
                        rx.text(AuthState.t[title_key], size="1",
                                weight="bold", color="#222",
                                style={"fontSize": "11px",
                                       "lineHeight": "1.4"}),
                        rx.text(AuthState.t[body_key], size="1",
                                color="#444",
                                style={"fontSize": "10.5px",
                                       "lineHeight": "1.45"}),
                        spacing="1",
                        align_items="start",
                    ),
                    padding="8px 12px",
                    border_radius="14px 14px 14px 4px",
                    background="white",
                    box_shadow="0 1px 2px rgba(0,0,0,0.08)",
                    max_width="180px",
                ),
                rx.text(
                    AuthState.t[time_key],
                    size="1",
                    color="rgba(255,255,255,0.85)",
                    style={"fontSize": "9px",
                           "textShadow": "0 1px 2px rgba(0,0,0,0.2)",
                           "whiteSpace": "nowrap"},
                ),
                spacing="1",
                align="end",
            ),
            spacing="1",
            align_items="start",
            min_width="0",
        ),
        spacing="2",
        align="start",
        width="100%",
    )


def _line_phone_screenshots() -> rx.Component:
    """JA 用: assets/moc/line_*.jpg を 3 秒間隔でクロスフェード表示。

    アニメーションは HOME_CSS の cdn_slide_fade_3 keyframes に集約。
    各画像は cdn-slide-img-{1,2,3} クラスで delay が異なる。
    """
    images = [
        "/moc/line_Screenshot_staking.jpg",
        "/moc/line_Screenshot_drepvote.jpg",
        "/moc/line_Screenshot_drepremind.jpg",
    ]
    return rx.box(
        *[
            rx.image(
                src=src,
                alt="Cardanoism LINE notification",
                class_name=f"cdn-slide-img cdn-slide-img-{i + 1}",
            )
            for i, src in enumerate(images)
        ],
        position="relative",
        width="100%",
        height="100%",
        background="black",
    )


def _line_phone_mock() -> rx.Component:
    """LINE 公式アカウントの通知画面を模したスマホ mock。"""
    chat_mock = rx.vstack(
        # ── ステータスバー（時刻 / 電波 / バッテリー）
        rx.hstack(
            rx.text("9:41", size="1", weight="bold", color="#000",
                    style={"fontSize": "11px"}),
            rx.spacer(),
            rx.icon("signal", size=10, color="#000"),
            rx.icon("wifi", size=10, color="#000"),
            rx.icon("battery-full", size=12, color="#000"),
            spacing="1", align="center", width="100%",
            padding="6px 22px 4px 18px",
            background="white",
        ),
        # ── LINE チャットヘッダー（緑）
        rx.hstack(
            rx.icon("chevron-left", size=18, color="white"),
            rx.box(
                rx.text("C", size="2", weight="bold", color=ACCENT_DARK,
                        style={"lineHeight": "1"}),
                width="34px", height="34px",
                border_radius="999px",
                background="white",
                display="flex",
                align_items="center",
                justify_content="center",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text("Cardanoism", size="2", weight="bold", color="white",
                        style={"fontSize": "13px", "lineHeight": "1.1"}),
                rx.text(AuthState.t["home_line_mock_official"], size="1",
                        color="rgba(255,255,255,0.85)",
                        style={"fontSize": "10px", "lineHeight": "1.1"}),
                spacing="0", align_items="start",
            ),
            rx.spacer(),
            rx.icon("phone", size=15, color="white"),
            rx.icon("more-vertical", size=15, color="white"),
            spacing="2", align="center", width="100%",
            padding="10px 14px",
            background=LINE_BRAND,
        ),
        # ── チャット領域（LINE 風の青グレー背景）
        rx.vstack(
            # 日付チップ
            rx.box(
                rx.text(AuthState.t["home_line_mock_today"], size="1",
                        color="white", weight="medium",
                        style={"fontSize": "10px"}),
                padding="3px 12px",
                border_radius="999px",
                background="rgba(0,0,0,0.18)",
                align_self="center",
            ),
            _line_msg_bubble(
                "home_line_mock_msg1_title",
                "home_line_mock_msg1_body",
                "home_line_mock_msg1_time",
            ),
            _line_msg_bubble(
                "home_line_mock_msg2_title",
                "home_line_mock_msg2_body",
                "home_line_mock_msg2_time",
            ),
            _line_msg_bubble(
                "home_line_mock_msg3_title",
                "home_line_mock_msg3_body",
                "home_line_mock_msg3_time",
            ),
            spacing="3",
            width="100%",
            padding="12px 12px 18px 12px",
            background="#7B98B7",
            flex="1",
            align_items="stretch",
            overflow="hidden",
        ),
        spacing="0",
        width="100%",
        height="100%",
        align_items="stretch",
    )

    # JA: 実機 LINE のスクリーンショットを 3 秒間隔フェードで表示
    # EN: 既存の chat 風 mock を維持 (画像が JA 仕様なので)
    screen = rx.cond(
        AuthState.language == "en",
        chat_mock,
        _line_phone_screenshots(),
    )
    return rx.box(
        # 内側の画面（ベゼルのパディングで囲む）
        rx.box(
            screen,
            position="relative",
            width="100%",
            height="100%",
            border_radius="22px",
            overflow="hidden",
            background="white",
        ),
        # パンチホール（前面カメラ）
        rx.box(
            width="10px",
            height="10px",
            border_radius="50%",
            background="#0a0a0a",
            position="absolute",
            top="14px",
            left="50%",
            style={"transform": "translateX(-50%)",
                   "zIndex": "10",
                   "boxShadow": "inset 0 0 0 1px rgba(255,255,255,0.08)"},
        ),
        position="relative",
        # 内側 528px 高さ × 画像アスペクト (1172/2748) ≒ 225.2px 幅 → 外形 238×540
        width="238px",
        height="540px",
        border_radius="28px",
        background="linear-gradient(145deg, #1a1a1a 0%, #2c2c30 100%)",
        padding="6px",
        box_shadow=("0 32px 80px -22px rgba(0,0,0,0.45), "
                    "0 16px 36px -12px rgba(6,199,85,0.30), "
                    "inset 0 0 0 1px rgba(255,255,255,0.06)"),
        style={"animation": "cdn_float 6s ease-in-out infinite"},
    )


# ─── Hero ────────────────────────────────────────────────────────────────────

def _beta_badge() -> rx.Component:
    """非推奨: 旧 hero 内バッジ。ヘッダー直下の _beta_announcement() に移管済み。"""
    return rx.fragment()


def _beta_announcement() -> rx.Component:
    """ヘッダー直下のベータ告知行。画面全幅で枠なし。/feedback への導線。"""
    if not BETA_MODE:
        return rx.fragment()
    return rx.link(
        rx.flex(
            rx.box(
                rx.text(
                    AuthState.t["hero_beta_badge_label"],
                    size="1",
                    weight="bold",
                    style={"letterSpacing": "0.12em", "color": "#1a1a1a"},
                ),
                padding="3px 10px",
                border_radius="999px",
                background="linear-gradient(135deg, #ffcf00, #ff9500)",
                style={"flexShrink": "0"},
            ),
            rx.text(
                AuthState.t["hero_beta_badge_text"],
                size="2",
                weight="medium",
                color=rx.color_mode_cond("var(--amber-12)", "var(--amber-11)"),
            ),
            rx.hstack(
                rx.text(
                    AuthState.t["hero_beta_badge_cta"],
                    size="2",
                    weight="bold",
                    color="var(--amber-11)",
                ),
                rx.icon("arrow-right", size=14, color="var(--amber-11)"),
                spacing="1",
                align="center",
                style={"flexShrink": "0"},
            ),
            spacing="2",
            align="center",
            justify="center",
            wrap="wrap",
            width="100%",
            max_width="1180px",
            margin_x="auto",
            padding_x=["16px", "28px", "40px"],
            padding_y="10px",
        ),
        href="/feedback",
        underline="none",
        # ヘッダーとの間に少しだけ呼吸を残しつつ、画面全幅で配置。
        # 親 box の padding-top (2em) を半分だけ打ち消して 1em の隙間を残す。
        style={
            "display":     "block",
            "width":       "100vw",
            "marginLeft":  "calc(-50vw + 50%)",
            "marginRight": "calc(-50vw + 50%)",
            "marginTop":   "-1em",
            "textAlign":   "center",
            "background":  rx.color_mode_cond(
                "rgba(255,243,199,0.55)",
                "rgba(120,80,0,0.16)",
            ),
            "borderBottom": rx.color_mode_cond(
                "1px solid rgba(0,0,0,0.05)",
                "1px solid rgba(255,255,255,0.06)",
            ),
            "transition":   "background 0.15s",
            "_hover": {
                "background": rx.color_mode_cond(
                    "rgba(255,237,170,0.75)",
                    "rgba(140,95,5,0.22)",
                ),
            },
        },
    )


def hero_section() -> rx.Component:
    headline = rx.heading(
        rx.text(AuthState.t["hero_heading"], class_name="cdn-gradient-text"),
        as_="h1",
        size="9",
        weight="bold",
        line_height="1.05",
        letter_spacing="-0.02em",
        # i18n の \n を意図的に改行として描画するため white-space: pre-line。
        # 上下余白を加えてヘッドラインに呼吸を与える。
        margin_y=["16px", "20px", "24px"],
        style={
            "whiteSpace": "pre-line",
            "@media (max-width: 640px)": {
                "fontSize":   "36px",
                "lineHeight": "1.25",
                "wordBreak":  "keep-all",
                "lineBreak":  "strict",
                "overflowWrap": "break-word",
            },
        },
    )
    subtitle = rx.text(
        AuthState.t["hero_subtitle"],
        size={"base": "3", "md": "4"},
        color=rx.color_mode_cond("rgba(20,20,20,0.74)", "rgba(245,245,245,0.78)"),
        line_height="1.75",
        max_width="600px",
    )
    # CTA はスマホで full-width にして親指タップしやすく。
    # ログイン状態 + アドレス登録状況で文言と遷移先を切り替える。
    #   未ログイン           : 無料で始める → /login
    #   ログイン済み・アドレス未登録 : アドレスを登録する → /mypage?tab=stake
    #   ログイン済み・アドレス登録済 : ダッシュボードへ → /mypage
    cta_label = rx.cond(
        AuthState.is_logged_in,
        rx.cond(
            AuthState.is_stake_addresses_empty,
            AuthState.t["hero_cta_register_address"],
            AuthState.t["hero_cta_dashboard"],
        ),
        AuthState.t["hero_cta_primary"],
    )
    cta_href = rx.cond(
        AuthState.is_logged_in,
        rx.cond(
            AuthState.is_stake_addresses_empty,
            "/mypage?tab=stake",
            "/mypage",
        ),
        "/login",
    )
    primary_cta = rx.link(
        rx.button(
            rx.icon("rocket", size=18),
            rx.text(cta_label, weight="bold"),
            size="4",
            background="linear-gradient(135deg, #ffcf00, #ff9500)",
            color="#111",
            border="1px solid rgba(199,163,0,0.5)",
            cursor="pointer",
            padding="0 28px",
            _hover={"background": "linear-gradient(135deg, #ff9500, #ffcf00)"},
            style={
                "boxShadow": "0 10px 30px -8px rgba(255,154,0,0.55)",
                "width": "100%",
            },
        ),
        href=cta_href,
        underline="none",
        width=["100%", "100%", "auto"],
        # PC は max 360px くらいで詰めて中央寄せ感を出す
        max_width=["100%", "100%", "360px"],
    )
    help_cta = rx.link(
        rx.button(
            rx.icon("book-open", size=16),
            rx.text(AuthState.t["nav_help"], weight="medium"),
            size="4",
            variant="outline",
            color_scheme="gray",
            cursor="pointer",
            padding="0 24px",
            style={"width": "100%"},
        ),
        href="/help",
        underline="none",
        width=["100%", "100%", "auto"],
        max_width=["100%", "100%", "240px"],
    )
    cta = rx.flex(
        primary_cta,
        help_cta,
        flex_direction=["column", "column", "row"],
        spacing="3",
        align="stretch",
        width=["100%", "100%", "auto"],
        # サブタイトルとの間に呼吸を入れる
        margin_top=["16px", "20px", "24px"],
    )

    return rx.box(
        rx.box(class_name="cdn-hero-aurora"),
        _shell(
            rx.flex(
                rx.vstack(
                    _beta_badge(),
                    headline,
                    subtitle,
                    cta,
                    # スマホは余白控えめ、デスクトップは広めに
                    spacing={"base": "4", "md": "6"},
                    align_items="start",
                    flex="1 1 auto",
                    min_width="0",
                    max_width="820px",
                    width="100%",
                ),
                rx.box(
                    _line_phone_mock(),
                    flex="0 0 auto",
                    display=["none", "none", "flex"],  # スマホでは非表示
                    align_items="center",
                    justify_content="center",
                ),
                direction={"base": "column", "md": "row"},
                align="center",
                justify={"base": "center", "md": "between"},
                spacing="6",
                width="100%",
            ),
            padding_y=["20px", "60px", "80px"],
            position="relative",
            z_index="1",
        ),
        position="relative",
        background=rx.color_mode_cond(
            "linear-gradient(180deg, #fefcf2 0%, #f8f9fc 100%)",
            "linear-gradient(180deg, #0a0b10 0%, #0f1018 100%)",
        ),
        width="100vw",
        margin_left="calc(-50vw + 50%)",
        margin_right="calc(-50vw + 50%)",
        overflow="hidden",
        border_bottom=f"1px solid {rx.color('gray', 4)}",
    )


# ─── Section Heading 共通 ────────────────────────────────────────────────────

def _section_heading(kicker, title, subtitle, kicker_color: str = ACCENT_DARK) -> rx.Component:
    return rx.vstack(
        rx.text(kicker, size="2", weight="bold", color=kicker_color, letter_spacing="0.14em"),
        rx.heading(title, as_="h2", size="7", weight="bold", line_height="1.2", max_width="720px"),
        rx.text(subtitle, size="3", color=TEXT_MUTED, line_height="1.7", max_width="720px"),
        spacing="3",
        align_items="start",
        width="100%",
    )


# ─── Feature Showcase ────────────────────────────────────────────────────────

def _feature_card(
    icon: str, color: str, title, desc,
    href: str, mock: rx.Component | None = None,
) -> rx.Component:
    return rx.link(
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.box(
                        rx.icon(icon, size=22, color=color),
                        width="48px",
                        height="48px",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        border_radius="14px",
                        background=f"{color}1f",
                        border=f"1px solid {color}33",
                        flex_shrink="0",
                    ),
                    rx.spacer(),
                    rx.icon("arrow-up-right", size=16, color=TEXT_MUTED),
                    spacing="2", align="center", width="100%",
                ),
                rx.heading(title, size="4", as_="h3", weight="bold",
                           color="var(--gray-12)"),
                rx.text(desc, size="2", color=TEXT_MUTED, line_height="1.7"),
                rx.cond(
                    mock is not None,
                    mock if mock is not None else rx.fragment(),
                    rx.fragment(),
                ),
                spacing="3",
                align_items="start",
                width="100%",
            ),
            class_name="cdn-soft-card cdn-feature-card",
            padding="24px",
            border=f"1px solid {rx.color('gray', 5)}",
            border_radius="18px",
            background=rx.color_mode_cond("rgba(255,255,255,0.78)", "rgba(255,255,255,0.03)"),
            height="100%",
            style={"--cdn-feature-color": color},
            _hover={
                "border_color": color,
                "box_shadow": f"0 22px 48px -32px {color}80",
            },
        ),
        href=href,
        underline="none",
        width="100%",
        height="100%",
    )


def _mock_chip(text, color: str) -> rx.Component:
    return rx.box(
        rx.text(text, size="1", weight="medium", color=color),
        padding="3px 10px",
        border_radius="999px",
        background=f"{color}1a",
        border=f"1px solid {color}33",
        display="inline-flex",
        align_items="center",
        style={"whiteSpace": "nowrap"},
    )


def _mock_ai() -> rx.Component:
    """AI 要約を模した小チップ。"""
    return rx.vstack(
        rx.hstack(
            _mock_chip("引き出し額: 50K ADA", F_AI),
            _mock_chip("用途: 教育", F_AI),
            spacing="1", wrap="wrap",
        ),
        rx.box(
            rx.text(
                "本提案は教育プログラムの運営費として 50,000 ADA を…",
                size="1", color=TEXT_MUTED, line_height="1.5",
                style={
                    "display": "-webkit-box",
                    "WebkitLineClamp": "2",
                    "WebkitBoxOrient": "vertical",
                    "overflow": "hidden",
                },
            ),
            padding="8px 12px",
            border_radius="10px",
            background=f"{F_AI}0d",
            border=f"1px solid {F_AI}22",
        ),
        spacing="2", width="100%",
    )


def _mock_drep() -> rx.Component:
    return rx.hstack(
        rx.icon("user-check", size=14, color=F_DREP),
        rx.text("Cardano Foundation", size="1", weight="medium", color="var(--gray-12)"),
        rx.spacer(),
        rx.box(
            rx.hstack(
                rx.icon("check", size=12, color="white"),
                rx.text("Yes", size="1", weight="bold", color="white"),
                spacing="1", align="center",
            ),
            padding="2px 8px",
            border_radius="999px",
            background="var(--green-9)",
        ),
        spacing="2", align="center", width="100%",
        padding="10px 12px",
        border_radius="10px",
        background=f"{F_DREP}0d",
        border=f"1px solid {F_DREP}22",
    )


def _mock_constitution() -> rx.Component:
    version = rx.cond(
        HomeState.constitution_version_label != "",
        HomeState.constitution_version_label,
        "v1.0",
    )
    return rx.hstack(
        rx.icon("scroll-text", size=16, color=F_CONST),
        rx.text("Cardano Constitution", size="2", weight="medium", color="var(--gray-12)"),
        rx.box(
            rx.text(version, size="1", weight="bold", color="white"),
            padding="2px 8px",
            border_radius="999px",
            background=F_CONST,
        ),
        spacing="2", align="center", width="100%",
        padding="10px 12px",
        border_radius="10px",
        background=f"{F_CONST}0d",
        border=f"1px solid {F_CONST}22",
    )


def _mock_treasury() -> rx.Component:
    return rx.box(
        rx.html(
            f'''
            <svg width="100%" height="42" viewBox="0 0 240 42" preserveAspectRatio="none"
                 xmlns="http://www.w3.org/2000/svg" style="display:block">
              <path d="M0,32 L40,28 L80,30 L120,22 L160,18 L200,12 L240,6"
                    fill="none" stroke="{F_TRES}" stroke-width="2.5" stroke-linejoin="round"/>
              <path d="M0,32 L40,28 L80,30 L120,22 L160,18 L200,12 L240,6 L240,42 L0,42 Z"
                    fill="{F_TRES}" fill-opacity="0.18"/>
            </svg>
            '''
        ),
        padding="8px 12px",
        border_radius="10px",
        background=f"{F_TRES}0d",
        border=f"1px solid {F_TRES}22",
    )


def _mock_notify() -> rx.Component:
    return rx.hstack(
        _mock_chip("LINE", LINE_BRAND),
        _mock_chip("Telegram", TG_BRAND),
        _mock_chip("Email", MAIL_BRAND),
        spacing="1", wrap="wrap",
    )


def _mock_wallet() -> rx.Component:
    """ウォレット連携 mock。主要 Cardano ウォレット名のチップ。"""
    return rx.hstack(
        _mock_chip("Eternl", F_WALLET),
        _mock_chip("Lace",   F_WALLET),
        _mock_chip("Typhon", F_WALLET),
        _mock_chip("Yoroi",  F_WALLET),
        spacing="1", wrap="wrap",
    )


def _mock_catalyst() -> rx.Component:
    """Catalyst 管理 mock。Fund 番号とステータスのチップ。"""
    return rx.hstack(
        _mock_chip("Fund 12", F_CAT),
        _mock_chip("Fund 13", F_CAT),
        _mock_chip("Fund 14", F_CAT),
        spacing="1", wrap="wrap",
    )


def _mock_ga_ja() -> rx.Component:
    """GA 日本語化を表すミニ mock。EN→JA バッジ + サンプルタイトル。"""
    return rx.vstack(
        rx.hstack(
            _mock_chip("EN", F_GA),
            rx.icon("arrow-right", size=12, color=F_GA),
            _mock_chip("日本語", F_GA),
            spacing="2", align="center",
        ),
        rx.box(
            rx.text(
                "Treasury Withdrawal — 教育プログラム運営費 50K ADA",
                size="1", color=TEXT_MUTED, line_height="1.5",
                style={
                    "display": "-webkit-box",
                    "WebkitLineClamp": "2",
                    "WebkitBoxOrient": "vertical",
                    "overflow": "hidden",
                },
            ),
            padding="8px 12px",
            border_radius="10px",
            background=f"{F_GA}0d",
            border=f"1px solid {F_GA}22",
        ),
        spacing="2", width="100%",
    )


def features_section() -> rx.Component:
    return _shell(
        rx.vstack(
            _section_heading(
                AuthState.t["home_features_kicker"],
                AuthState.t["home_features_title"],
                AuthState.t["home_features_subtitle"],
            ),
            rx.grid(
                # 1. ステーキング報酬・プール状態の即時通知
                _feature_card(
                    "bell", F_NOTI,
                    AuthState.t["home_f_notify_title"],
                    AuthState.t["home_f_notify_desc"],
                    href="/mypage?tab=notification",
                    mock=_mock_notify(),
                ),
                # 2. ウォレット連携で委任完結
                _feature_card(
                    "wallet", F_WALLET,
                    AuthState.t["home_f_wallet_title"],
                    AuthState.t["home_f_wallet_desc"],
                    href="/staking",
                    mock=_mock_wallet(),
                ),
                # 3. AI 提案要約 + 投票マトリクス
                _feature_card(
                    "sparkles", F_AI,
                    AuthState.t["home_f_ai_title"],
                    AuthState.t["home_f_ai_desc"],
                    href="/governance/matrix",
                    mock=_mock_ai(),
                ),
                # 4. Catalyst 提案管理
                _feature_card(
                    "list-checks", F_CAT,
                    AuthState.t["home_f_catalyst_title"],
                    AuthState.t["home_f_catalyst_desc"],
                    href="/catalyst",
                    mock=_mock_catalyst(),
                ),
                # 5. トレジャリー残高グラフ
                _feature_card(
                    "trending-up", F_TRES,
                    AuthState.t["home_f_treasury_title"],
                    AuthState.t["home_f_treasury_desc"],
                    href="/governance/treasury",
                    mock=_mock_treasury(),
                ),
                # 6. Cardano 憲法完全日本語化
                _feature_card(
                    "scroll-text", F_CONST,
                    AuthState.t["home_f_constitution_title"],
                    AuthState.t["home_f_constitution_desc"],
                    href="/governance/constitution",
                    mock=_mock_constitution(),
                ),
                columns={"base": "1", "sm": "2", "lg": "3"},
                spacing="4",
                width="100%",
            ),
            spacing="7",
            width="100%",
        ),
        padding_y=["48px", "60px", "72px"],
    )


# ─── Constitution Highlight ──────────────────────────────────────────────────

def constitution_highlight_section() -> rx.Component:
    def _version_badge() -> rx.Component:
        return rx.cond(
            HomeState.constitution_version_label != "",
            rx.box(
                rx.text(
                    HomeState.constitution_version_label,
                    size="1", weight="bold", color="white",
                    style={"whiteSpace": "nowrap"},
                ),
                padding="4px 12px",
                border_radius="999px",
                background=F_CONST,
                style={"flexShrink": "0"},
            ),
            rx.fragment(),
        )

    # 左カラム: 啓発コンテンツ
    left_col = rx.vstack(
        rx.text(
            AuthState.t["home_constitution_kicker"],
            size="1", weight="bold", color=F_CONST, letter_spacing="0.18em",
        ),
        rx.heading(
            AuthState.t["home_constitution_title"],
            as_="h2",
            size={"base": "5", "sm": "6", "md": "7"},
            weight="bold",
            line_height="1.25",
            style={"wordBreak": "break-word", "overflowWrap": "anywhere", "maxWidth": "100%"},
        ),
        rx.text(
            AuthState.t["home_constitution_subtitle"],
            size={"base": "2", "md": "3"},
            color=TEXT_MUTED, line_height="1.75",
            style={"wordBreak": "break-word", "maxWidth": "100%"},
        ),
        rx.flex(
            rx.text(
                AuthState.t["home_constitution_version_label"],
                size="2", color=TEXT_MUTED,
            ),
            _version_badge(),
            spacing="2",
            align="center",
            wrap="wrap",
        ),
        rx.link(
            rx.button(
                rx.icon("scroll-text", size=16),
                AuthState.t["home_constitution_cta"],
                rx.icon("arrow-right", size=16),
                size="3",
                background=F_CONST,
                color="white",
                cursor="pointer",
                padding="0 22px",
                _hover={"background": "#0284c7"},
                style={"boxShadow": f"0 12px 32px -10px {F_CONST}"},
            ),
            href="/governance/constitution",
            underline="none",
        ),
        spacing="4",
        align_items="start",
        width="100%",
        style={"minWidth": "0", "flex": "1 1 50%"},
    )

    # 右カラム: 憲法プレビューカード
    preview_card = rx.box(
        rx.vstack(
            rx.flex(
                rx.icon("scroll-text", size=18, color=F_CONST),
                rx.text(
                    AuthState.t["home_constitution_preview_doc_title"],
                    size="2", weight="bold", color="var(--gray-12)",
                    style={"flex": "1 1 auto", "minWidth": "0"},
                ),
                _version_badge(),
                spacing="2",
                align="center",
                width="100%",
                wrap="wrap",
            ),
            rx.divider(),
            rx.text(
                AuthState.t["home_constitution_preview_article_en"],
                size="2", weight="bold", color="var(--gray-12)",
            ),
            rx.text(
                AuthState.t["home_constitution_preview_quote_en"],
                size="1", color=TEXT_MUTED, line_height="1.6",
                style={"fontStyle": "italic", "wordBreak": "break-word"},
            ),
            rx.text(
                AuthState.t["home_constitution_preview_article_ja"],
                size="2", weight="bold", color="var(--gray-12)",
                style={"marginTop": "8px"},
            ),
            rx.text(
                AuthState.t["home_constitution_preview_quote_ja"],
                size="1", color=TEXT_MUTED, line_height="1.6",
                style={"wordBreak": "break-word"},
            ),
            spacing="2",
            align_items="start",
            width="100%",
        ),
        padding=["18px", "20px", "22px"],
        border=f"1px solid {F_CONST}33",
        border_radius="16px",
        background=rx.color_mode_cond(
            "rgba(255,255,255,0.95)", "rgba(255,255,255,0.04)",
        ),
        backdrop_filter="blur(10px)",
        box_shadow=f"0 22px 60px -28px {F_CONST}55",
        width="100%",
        style={
            "minWidth": "0",
            "flex": "1 1 50%",
            "boxSizing": "border-box",
        },
    )

    return rx.box(
        _shell(
            rx.flex(
                left_col,
                # プレビューカードは tablet/desktop のみ表示 (モバイルでは非表示)
                rx.tablet_and_desktop(preview_card),
                direction={"base": "column", "md": "row"},
                align={"base": "stretch", "md": "center"},
                spacing={"base": "5", "md": "8"},
                width="100%",
                style={"minWidth": "0"},
            ),
            padding_y=["40px", "52px", "72px"],
        ),
        background=rx.color_mode_cond(
            "linear-gradient(135deg, #f0f9ff 0%, #ecfeff 100%)",
            "linear-gradient(135deg, #0c1422 0%, #0a1820 100%)",
        ),
        width="100%",
        border_top=f"1px solid {rx.color('gray', 4)}",
        border_bottom=f"1px solid {rx.color('gray', 4)}",
        style={"overflow": "hidden"},
    )


# ─── 3-step Setup ────────────────────────────────────────────────────────────

def _step(num: int, title, body) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text(
                f"0{num}",
                size="6",
                weight="bold",
                color=ACCENT_DARK,
                letter_spacing="-0.02em",
                line_height="1",
            ),
            rx.box(width="32px", height="2px", background=ACCENT, align_self="center"),
            spacing="3",
            align="center",
        ),
        rx.heading(title, size="4", as_="h3", weight="bold"),
        rx.text(body, size="2", color=TEXT_MUTED, line_height="1.7"),
        spacing="3",
        align_items="start",
        padding="24px",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="18px",
        background=rx.color_mode_cond("rgba(255,255,255,0.78)", "rgba(255,255,255,0.03)"),
        height="100%",
    )


def setup_section() -> rx.Component:
    return _shell(
        rx.vstack(
            _section_heading(
                "GET STARTED",
                AuthState.t["home_setup_title"],
                AuthState.t["home_setup_subtitle"],
            ),
            rx.grid(
                _step(1, AuthState.t["home_step_account_title"], AuthState.t["home_step_account_body"]),
                _step(2, AuthState.t["home_step_stake_title"], AuthState.t["home_step_stake_body"]),
                _step(3, AuthState.t["home_step_channel_title"], AuthState.t["home_step_channel_body"]),
                columns={"base": "1", "md": "3"},
                spacing="4",
                width="100%",
            ),
            spacing="6",
            width="100%",
            align_items="start",
        ),
        padding_y=["44px", "56px", "68px"],
    )


# ─── Final CTA ──────────────────────────────────────────────────────────────

def final_cta_section() -> rx.Component:
    # ログイン状態に応じてラベルと遷移先を切替 (hero CTA と同じロジック)
    cta_label = rx.cond(
        AuthState.is_logged_in,
        rx.cond(
            AuthState.is_stake_addresses_empty,
            AuthState.t["hero_cta_register_address"],
            AuthState.t["hero_cta_dashboard"],
        ),
        AuthState.t["home_final_cta_button"],
    )
    cta_href = rx.cond(
        AuthState.is_logged_in,
        rx.cond(
            AuthState.is_stake_addresses_empty,
            "/mypage?tab=stake",
            "/mypage",
        ),
        "/login",
    )
    return rx.box(
        _shell(
            rx.vstack(
                rx.heading(
                    AuthState.t["home_final_cta_title"],
                    as_="h2", size="8", weight="bold", text_align="center",
                    line_height="1.15",
                ),
                rx.text(
                    AuthState.t["home_final_cta_subtitle"],
                    size="3", color=TEXT_MUTED, text_align="center",
                    max_width="560px",
                ),
                rx.link(
                    rx.button(
                        rx.icon("rocket", size=16),
                        cta_label,
                        rx.icon("arrow-right", size=16),
                        size="4",
                        background="linear-gradient(135deg, #ffcf00, #ff7e5f)",
                        color="#111",
                        border="1px solid rgba(199,163,0,0.5)",
                        cursor="pointer",
                        padding="0 28px",
                        _hover={"background": "linear-gradient(135deg, #ff7e5f, #ffcf00)"},
                        style={"boxShadow": "0 14px 36px -10px rgba(255,154,0,0.6)"},
                    ),
                    href=cta_href,
                    underline="none",
                ),
                spacing="5",
                align="center",
                width="100%",
            ),
            padding_y=["56px", "72px", "88px"],
        ),
        background=rx.color_mode_cond(
            "linear-gradient(180deg, #fefcf2 0%, #fff8e7 100%)",
            "linear-gradient(180deg, #0c0d12 0%, #1a1410 100%)",
        ),
        position="relative",
        overflow="hidden",
        width="100vw",
        margin_left="calc(-50vw + 50%)",
        margin_right="calc(-50vw + 50%)",
        border_top=f"1px solid {rx.color('gray', 4)}",
    )


# ─── ページエントリ ────────────────────────────────────────────────────────

@template(
    route="/",
    title="Cardanoism | カルダノをもっと身近に",
    on_load=HomeState.warm_up,
)
def index() -> rx.Component:
    return rx.box(
        rx.html(HOME_CSS),
        _beta_announcement(),
        hero_section(),
        features_section(),
        constitution_highlight_section(),
        setup_section(),
        final_cta_section(),
        width="100%",
        max_width="100%",
    )
