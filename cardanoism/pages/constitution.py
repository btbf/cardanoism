"""
constitution.py
/constitution ページ。最新 enacted Cardano 憲法の原文 + 日本語訳を表示する。

データソース: constitution_cache (id=1)
言語: AuthState.language で切り替え（手動トグルもあり）
"""
from __future__ import annotations

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.constitution_db import get_constitution
from cardanoism.components.governance_nav import governance_subnav
from cardanoism.components.login_modal import login_modal


# ─── 状態 ──────────────────────────────────────────────────────────────────────

class ConstitutionState(rx.State):
    """憲法ページ専用の State。AuthState.language とは独立に
    手動トグル (lang_mode) で原文/翻訳を切り替えできるようにする。
    lang_mode = "auto" / "ja" / "en"

    Note: フィールド名は動的ルート引数 (例: /catalyst/proposals/[proposal_id]) と
    衝突しないようにプレフィクス "constitution_" を付けている。
    """
    constitution_proposal_id: str = ""
    constitution_enacted_epoch: int = 0
    constitution_source_url: str = ""
    constitution_original_text: str = ""
    constitution_translated_text: str = ""
    constitution_fetched_at: str = ""
    constitution_translated_at: str = ""
    constitution_loaded: bool = False

    lang_mode: str = "auto"

    def on_load(self):
        self.constitution_loaded = False
        self.constitution_proposal_id = ""
        self.constitution_enacted_epoch = 0
        self.constitution_source_url = ""
        self.constitution_original_text = ""
        self.constitution_translated_text = ""
        self.constitution_fetched_at = ""
        self.constitution_translated_at = ""
        try:
            row = get_constitution()
        except Exception:
            row = None
        if row:
            self.constitution_proposal_id = str(row.get("proposal_id") or "")
            try:
                self.constitution_enacted_epoch = int(row.get("enacted_epoch") or 0)
            except (TypeError, ValueError):
                self.constitution_enacted_epoch = 0
            self.constitution_source_url = str(row.get("source_url") or "")
            # Vision OCR で生成済みの Markdown を State に格納（追加整形は不要）
            self.constitution_original_text = str(row.get("original_text") or "")
            self.constitution_translated_text = str(row.get("translated_text") or "")
            ft = row.get("fetched_at")
            tt = row.get("translated_at")
            self.constitution_fetched_at = ft.strftime("%Y-%m-%d %H:%M") if ft else ""
            self.constitution_translated_at = tt.strftime("%Y-%m-%d %H:%M") if tt else ""
        self.constitution_loaded = True

    def set_lang_ja(self):
        self.lang_mode = "ja"

    def set_lang_en(self):
        self.lang_mode = "en"

    @rx.var
    def has_translation(self) -> bool:
        return bool(self.constitution_translated_text)

    @rx.var
    def has_constitution(self) -> bool:
        return bool(self.constitution_original_text) or bool(self.constitution_translated_text)


# ─── パンくず ──────────────────────────────────────────────────────────────────

def _breadcrumb() -> rx.Component:
    # /governance がそのまま憲法ページなので、中間に「ガバナンス」を入れず 2 階層構成にする
    return rx.hstack(
        rx.link(rx.icon("home", size=16), href="/", underline="none", color_scheme="gray"),
        rx.icon("chevron-right", size=14, color="gray"),
        rx.text(AuthState.t["constitution_breadcrumb"], size="2", weight="medium"),
        spacing="2", align="center", width="100%",
        padding_top="15px", padding_bottom="0px",
    )


# ─── ヘッダー ──────────────────────────────────────────────────────────────────

def _header() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("scroll-text", size=22, color="var(--amber-11)"),
                rx.text(
                    AuthState.t["constitution_page_title"],
                    size="6", weight="bold", color="var(--gray-12)",
                ),
                rx.badge(
                    AuthState.t["gov_constitution_in_force"],
                    color_scheme="violet", variant="soft",
                ),
                spacing="2", align="center", wrap="wrap",
            ),
            rx.hstack(
                rx.cond(
                    ConstitutionState.constitution_enacted_epoch > 0,
                    rx.hstack(
                        rx.text(
                            AuthState.t["constitution_enacted_label"],
                            size="2", color="var(--gray-10)",
                        ),
                        rx.text(
                            "Ep." + ConstitutionState.constitution_enacted_epoch.to_string(),
                            size="2", weight="medium", color="var(--gray-12)",
                        ),
                        spacing="1", align="baseline",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    ConstitutionState.constitution_source_url != "",
                    rx.link(
                        rx.button(
                            rx.icon("external-link", size=14),
                            rx.text(AuthState.t["constitution_source_link"], size="2"),
                            variant="outline", size="2", cursor="pointer",
                        ),
                        href=rx.cond(
                            ConstitutionState.constitution_source_url.startswith("ipfs://"),
                            "https://ipfs.io/ipfs/" + ConstitutionState.constitution_source_url.replace("ipfs://", ""),
                            ConstitutionState.constitution_source_url,
                        ),
                        is_external=True,
                        underline="none",
                    ),
                    rx.fragment(),
                ),
                spacing="3", align="center", wrap="wrap",
            ),
            spacing="2", align="start", width="100%",
        ),
        padding="16px 20px",
        border=f"1px solid {rx.color('amber', 6)}",
        border_radius="12px",
        background="var(--amber-2)",
        width="100%",
    )


# ─── 言語トグル ────────────────────────────────────────────────────────────────

def _lang_toggle() -> rx.Component:
    """日本語訳 / 原文 (English) のトグルボタン。"""
    ja_active = ConstitutionState.lang_mode == "ja"
    en_active = ConstitutionState.lang_mode == "en"
    auto = ConstitutionState.lang_mode == "auto"

    # auto モードでは AuthState.language を尊重して active 表示する
    ja_visual_active = rx.cond(auto, AuthState.language != "en", ja_active)
    en_visual_active = rx.cond(auto, AuthState.language == "en", en_active)

    return rx.hstack(
        rx.button(
            rx.icon("languages", size=14),
            rx.text(AuthState.t["constitution_lang_toggle_ja"], size="2"),
            variant=rx.cond(ja_visual_active, "solid", "soft"),
            color_scheme="amber",
            on_click=ConstitutionState.set_lang_ja,
            cursor="pointer",
            disabled=~ConstitutionState.has_translation,
        ),
        rx.button(
            rx.icon("globe", size=14),
            rx.text(AuthState.t["constitution_lang_toggle_en"], size="2"),
            variant=rx.cond(en_visual_active, "solid", "soft"),
            color_scheme="amber",
            on_click=ConstitutionState.set_lang_en,
            cursor="pointer",
        ),
        spacing="2", align="center", wrap="wrap",
    )


# ─── 本文表示 ──────────────────────────────────────────────────────────────────

def _body() -> rx.Component:
    """選択言語の本文を表示。pre-wrap で改行とインデントを保持。"""
    # lang_mode == "auto" → AuthState.language で切替
    # lang_mode == "ja"   → 翻訳テキスト（無ければ原文）
    # lang_mode == "en"   → 原文
    auto_text = rx.cond(
        AuthState.language == "en",
        ConstitutionState.constitution_original_text,
        rx.cond(
            ConstitutionState.has_translation,
            ConstitutionState.constitution_translated_text,
            ConstitutionState.constitution_original_text,
        ),
    )
    text = rx.match(
        ConstitutionState.lang_mode,
        ("ja", rx.cond(
            ConstitutionState.has_translation,
            ConstitutionState.constitution_translated_text,
            ConstitutionState.constitution_original_text,
        )),
        ("en", ConstitutionState.constitution_original_text),
        auto_text,
    )

    return rx.box(
        rx.box(
            rx.markdown(text),
            class_name=(
                "prose max-w-none dark:prose-invert "
                "prose-headings:text-[var(--gray-12)] dark:prose-headings:text-[var(--gray-12)] "
                "prose-h2:mt-8 prose-h2:mb-3 prose-h2:pb-2 prose-h2:border-b "
                "prose-h2:border-[var(--amber-7)] prose-h2:text-[20px] "
                "prose-h3:mt-6 prose-h3:mb-2 prose-h3:text-[16px] "
                "prose-p:text-[var(--gray-12)] dark:prose-p:text-[var(--gray-12)] "
                "prose-p:leading-7 "
                "prose-li:text-[var(--gray-12)] dark:prose-li:text-[var(--gray-12)] "
                "prose-strong:text-[var(--gray-12)] dark:prose-strong:text-[var(--gray-12)] "
                "prose-a:text-[var(--amber-11)] dark:prose-a:text-[var(--amber-11)] "
                "prose-blockquote:border-[var(--amber-7)] "
                "prose-blockquote:text-[var(--gray-11)] "
                "prose-code:text-[var(--gray-12)] dark:prose-code:bg-[var(--gray-4)]"
            ),
            color="var(--gray-12)",
        ),
        padding="20px 24px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="10px",
        background="var(--gray-2)",
        width="100%",
        max_height="80vh",
        overflow_y="auto",
    )


def _disclaimer() -> rx.Component:
    return rx.hstack(
        rx.icon("info", size=14, color="var(--gray-9)"),
        rx.text(
            AuthState.t["constitution_translation_disclaimer"],
            size="1", color="var(--gray-9)",
        ),
        spacing="2", align="start", width="100%",
    )


def _empty_state() -> rx.Component:
    return rx.callout(
        AuthState.t["constitution_no_constitution"],
        icon="info",
        color_scheme="gray",
    )


# ─── ページ本体 ────────────────────────────────────────────────────────────────

@template(
    route="/governance",
    title="Cardano 憲法 | Cardanoism",
    on_load=ConstitutionState.on_load,
)
def constitution_page() -> rx.Component:
    return rx.cond(
        ConstitutionState.constitution_loaded,
        rx.box(
            login_modal(),
            rx.vstack(
                _breadcrumb(),
                governance_subnav("constitution"),
                rx.cond(
                    ConstitutionState.has_constitution,
                    rx.vstack(
                        _header(),
                        _lang_toggle(),
                        _body(),
                        _disclaimer(),
                        spacing="4",
                        width="100%",
                    ),
                    _empty_state(),
                ),
                spacing="4",
                width="100%",
            ),
            width="100%",
            max_width="1130px",
        ),
        rx.flex(rx.spinner(size="3"), justify="center", align="center", width="100%", padding_y="20px"),
    )
