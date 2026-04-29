"""
governance_ai_analysis.py
GA 詳細ページに表示する AI 分析セクション（フロントエンド プロトタイプ）。

- Feature A: 憲法準拠スコア
- Feature B: VISION 2030 KPI レーダーチャート

5 状態（対象外 / pending / analyzing / analyzed / failed）をデモ表示するため、
GAAIDemoState で状態を切り替えられるようにしてある。
バックエンド実装後、サンプルデータと state 切り替え UI は本番データに置き換える。
"""
from __future__ import annotations

import math
from typing import Dict, List

import reflex as rx

from cardanoism.backend.auth_state import AuthState


# ─── サンプルデータ ────────────────────────────────────────────────────────────

_SAMPLE_CONSTITUTION_SCORE: int = 78
_SAMPLE_CONSTITUTION_VERDICT_JA: str = "概ね準拠"
_SAMPLE_CONSTITUTION_VERDICT_EN: str = "Mostly Compliant"
_SAMPLE_CONSTITUTION_SUMMARY_JA: str = (
    "本提案は Cardano 憲法の主要な原則（コミュニティ主導の意思決定、委任者の権利保護、"
    "プロトコルパラメータ変更の妥当性）を概ね満たしている。"
    "ただし結果評価の透明性に関する記述が不十分で、第 V 条の予算執行の説明責任に懸念が残る。"
)
_SAMPLE_CONSTITUTION_SUMMARY_EN: str = (
    "The proposal generally aligns with the core principles of the Cardano Constitution "
    "(community-led decision making, protection of delegator rights, sound parameter changes). "
    "However, the description of post-enactment transparency is insufficient, "
    "leaving accountability concerns under Article V."
)

_SAMPLE_ARTICLE_ROWS: List[Dict[str, str]] = [
    {
        "key": "art2",
        "label_ja": "第 II 条 — Cardano のミッション",
        "label_en": "Article II — Cardano's Mission",
        "score": "9",
        "comment_ja": "ネイティブステーキング体験の向上に直接寄与し、ミッションに合致。",
        "comment_en": "Directly contributes to native staking UX, aligned with the mission.",
        "color": "green",
    },
    {
        "key": "art3",
        "label_ja": "第 III 条 — 基本原則",
        "label_en": "Article III — Principles",
        "score": "7",
        "comment_ja": "コミュニティ主導の原則は満たすが、分散性への中期的影響の評価が不足。",
        "comment_en": "Meets community-led principle, but mid-term decentralization impact is unclear.",
        "color": "amber",
    },
    {
        "key": "art4",
        "label_ja": "第 IV 条 — 権利",
        "label_en": "Article IV — Rights",
        "score": "8",
        "comment_ja": "委任者・DRep の投票権を侵害しない設計になっている。",
        "comment_en": "Design preserves delegator and DRep voting rights.",
        "color": "green",
    },
    {
        "key": "art5",
        "label_ja": "第 V 条 — ガバナンス",
        "label_en": "Article V — Governance",
        "score": "6",
        "comment_ja": "予算執行後の進捗開示・KPI 報告義務についての記述が不足。",
        "comment_en": "Missing post-enactment progress disclosure and KPI reporting commitments.",
        "color": "ruby",
    },
]

_SAMPLE_CONCERNS_JA: List[str] = [
    "予算配分の使途の透明性レポーティング義務が明記されていない",
    "成功 / 失敗を判定する具体的な KPI と測定方法が曖昧",
    "実行主体の説明責任（ガバナンスへの定期報告）の頻度が定義されていない",
]
_SAMPLE_CONCERNS_EN: List[str] = [
    "No explicit transparency reporting requirements for budget allocation",
    "Specific KPIs and measurement methods for success / failure are vague",
    "Accountability cadence (regular governance reports) is not defined",
]

# VISION 2030 KPI 6 軸 (0–100)
_SAMPLE_KPI_AXES_JA: List[str] = ["採用", "エコシステム", "分散性", "技術革新", "持続可能性", "コミュニティ"]
_SAMPLE_KPI_AXES_EN: List[str] = ["Adoption", "Ecosystem", "Decentralization", "Innovation", "Sustainability", "Community"]
_SAMPLE_KPI_SCORES: List[int] = [75, 65, 50, 80, 70, 85]
_SAMPLE_KPI_COMMENTS_JA: List[str] = [
    "新規ユーザーのオンランプ改善が採用拡大を後押し",
    "既存 dApp との直接的な連携は限定的",
    "ステークプール集中度に中立。長期的影響は未知数",
    "新しい委任 UX を提示し、技術的なベンチマークを更新",
    "予算執行は 1 回限りで運用負担は軽い",
    "コミュニティへの透明性の高いコミュニケーションを継続",
]
_SAMPLE_KPI_COMMENTS_EN: List[str] = [
    "Improved onramp boosts new-user adoption",
    "Direct integration with existing dApps is limited",
    "Neutral on stake-pool concentration; long-term impact unclear",
    "Introduces new delegation UX, advancing technical benchmarks",
    "One-shot budget execution implies low ongoing operational burden",
    "Maintains transparent communication with the community",
]


# ─── レーダーチャート用座標計算 ────────────────────────────────────────────────

_RADAR_CX = 175
_RADAR_CY = 175
_RADAR_R = 120
_RADAR_LABEL_R = 150  # 軸ラベル位置


def _polar(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def _build_radar_geometry(scores: List[int]) -> Dict[str, object]:
    """SVG 描画用の座標群を一括計算する。"""
    n = len(scores)
    # 各軸の角度: 上 (-90°) を基点に時計回り
    angles = [-90 + (360 / n) * i for i in range(n)]

    # グリッド (4 リング)
    grids: list[str] = []
    for ring_pct in (25, 50, 75, 100):
        pts = [_polar(_RADAR_CX, _RADAR_CY, _RADAR_R * ring_pct / 100, a) for a in angles]
        grids.append(" ".join(f"{x:.1f},{y:.1f}" for x, y in pts))

    # 軸線 + ラベル位置
    axis_lines: list[Dict[str, str]] = []
    label_positions: list[Dict[str, str]] = []
    for a in angles:
        ex, ey = _polar(_RADAR_CX, _RADAR_CY, _RADAR_R, a)
        lx, ly = _polar(_RADAR_CX, _RADAR_CY, _RADAR_LABEL_R, a)
        axis_lines.append({"x2": f"{ex:.1f}", "y2": f"{ey:.1f}"})
        # text-anchor をラベルの位置に応じて切り替え
        if abs(lx - _RADAR_CX) < 1:
            anchor = "middle"
        elif lx > _RADAR_CX:
            anchor = "start"
        else:
            anchor = "end"
        label_positions.append({"x": f"{lx:.1f}", "y": f"{ly:.1f}", "anchor": anchor})

    # データポリゴン
    data_pts = [
        _polar(_RADAR_CX, _RADAR_CY, _RADAR_R * (s / 100), a)
        for s, a in zip(scores, angles)
    ]
    polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in data_pts)
    points = [{"cx": f"{x:.1f}", "cy": f"{y:.1f}"} for x, y in data_pts]

    return {
        "grids": grids,
        "axis_lines": axis_lines,
        "label_positions": label_positions,
        "polygon": polygon,
        "points": points,
    }


_RADAR = _build_radar_geometry(_SAMPLE_KPI_SCORES)


# ─── デモ State ────────────────────────────────────────────────────────────────

class GAAIDemoState(rx.State):
    """サンプル表示用の状態切り替え。バックエンド実装後は不要になる。"""

    # one of: "none", "pending", "analyzing", "analyzed", "failed"
    demo_state: str = "analyzed"

    # pending 状態で表示する経過秒数（デモなので静止）
    pending_seconds: int = 12

    # failed 状態のエラー文言
    error_message: str = "Anthropic API rate limit exceeded (429)"

    @rx.event
    def set_state(self, value: str):
        self.demo_state = value


# ─── 共通レイアウト ────────────────────────────────────────────────────────────

_AI_SECTION_PADDING = "20px 22px"


def _ai_heading() -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon("sparkles", size=18, color="white"),
            background="linear-gradient(135deg, var(--violet-9), var(--indigo-9))",
            border_radius="8px",
            padding="6px",
            display="inline-flex",
            align_items="center",
            justify_content="center",
        ),
        rx.vstack(
            rx.text(AuthState.t["ga_ai_section_title"], size="3", weight="bold", color="var(--gray-12)"),
            rx.text(AuthState.t["ga_ai_section_subtitle"], size="1", color="var(--gray-10)"),
            spacing="0",
            align="start",
        ),
        rx.spacer(),
        rx.badge(
            rx.hstack(
                rx.icon("flask-conical", size=12),
                rx.text("Beta", weight="medium"),
                spacing="1",
                align="center",
            ),
            color_scheme="violet",
            variant="soft",
            size="1",
            radius="full",
        ),
        spacing="3",
        align="center",
        width="100%",
    )


def _ai_card(content: rx.Component) -> rx.Component:
    return rx.box(
        rx.vstack(
            _ai_heading(),
            rx.divider(),
            content,
            spacing="3",
            width="100%",
            align_items="stretch",
        ),
        padding=_AI_SECTION_PADDING,
        border=f"1px solid {rx.color('violet', 5)}",
        border_radius="14px",
        background=rx.color_mode_cond(
            light="linear-gradient(180deg, var(--violet-2), var(--gray-1))",
            dark="linear-gradient(180deg, var(--violet-3), var(--gray-2))",
        ),
        width="100%",
    )


# ─── 状態 1: 対象外 ────────────────────────────────────────────────────────────

def _state_none() -> rx.Component:
    return rx.hstack(
        rx.icon("info", size=16, color="var(--gray-9)"),
        rx.text(
            AuthState.t["ga_ai_state_none"],
            size="2",
            color="var(--gray-10)",
        ),
        spacing="2",
        align="center",
        padding="12px 4px",
    )


# ─── 状態 2: pending ───────────────────────────────────────────────────────────

def _state_pending() -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.box(
                width="10px",
                height="10px",
                border_radius="50%",
                background="var(--amber-9)",
                animation="ai-pulse 1.4s ease-in-out infinite",
            ),
            rx.html(
                """
                <style>
                @keyframes ai-pulse {
                  0%, 100% { transform: scale(1); opacity: 1; }
                  50% { transform: scale(1.6); opacity: 0.4; }
                }
                </style>
                """
            ),
        ),
        rx.vstack(
            rx.text(
                AuthState.t["ga_ai_state_pending_title"],
                size="2", weight="bold", color="var(--gray-12)",
            ),
            rx.hstack(
                rx.text(
                    AuthState.t["ga_ai_state_pending_desc_prefix"],
                    size="1", color="var(--gray-10)",
                ),
                rx.text(
                    GAAIDemoState.pending_seconds.to_string(),
                    size="1", color="var(--gray-12)", weight="medium",
                ),
                rx.text(
                    AuthState.t["ga_ai_state_pending_desc_suffix"],
                    size="1", color="var(--gray-10)",
                ),
                spacing="1",
                align="baseline",
            ),
            spacing="0",
            align="start",
        ),
        spacing="3",
        align="center",
        padding="14px 4px",
    )


# ─── 状態 3: analyzing ─────────────────────────────────────────────────────────

def _state_analyzing() -> rx.Component:
    return rx.hstack(
        rx.spinner(size="3", color="violet"),
        rx.vstack(
            rx.hstack(
                rx.text(
                    AuthState.t["ga_ai_state_analyzing_title"],
                    size="2", weight="bold", color="var(--gray-12)",
                ),
                rx.badge("Claude Sonnet 4.6", color_scheme="violet", variant="soft", size="1"),
                spacing="2", align="center",
            ),
            rx.text(
                AuthState.t["ga_ai_state_analyzing_desc"],
                size="1", color="var(--gray-10)",
            ),
            spacing="1",
            align="start",
        ),
        spacing="3",
        align="center",
        padding="14px 4px",
    )


# ─── 状態 5: failed ────────────────────────────────────────────────────────────

def _state_failed() -> rx.Component:
    return rx.hstack(
        rx.icon("triangle-alert", size=20, color="var(--red-10)"),
        rx.vstack(
            rx.text(
                AuthState.t["ga_ai_state_failed_title"],
                size="2", weight="bold", color="var(--red-11)",
            ),
            rx.text(
                GAAIDemoState.error_message,
                size="1",
                color="var(--gray-10)",
                style={"fontFamily": "var(--code-font-family, ui-monospace, monospace)"},
            ),
            spacing="0", align="start",
        ),
        rx.spacer(),
        rx.button(
            rx.icon("rotate-ccw", size=14),
            rx.text(AuthState.t["ga_ai_retry"], size="2"),
            color_scheme="red",
            variant="soft",
            size="2",
            cursor="pointer",
        ),
        spacing="3",
        align="center",
        padding="10px 4px",
        width="100%",
    )


# ─── 状態 4: analyzed — Feature A: 憲法準拠 ────────────────────────────────────

def _score_color(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 60:
        return "amber"
    if score >= 40:
        return "orange"
    return "ruby"


def _gauge_arc(score: int) -> rx.Component:
    """半円ゲージ。SVG のストロークオフセットで進捗を描画。"""
    # 半円の弧長 = π * r (半円なので)
    r = 70
    circumference = math.pi * r  # 半円の長さ
    progress = circumference * (score / 100)
    color = _score_color(score)

    return rx.box(
        rx.html(
            f"""
            <svg width="180" height="100" viewBox="0 0 180 100" xmlns="http://www.w3.org/2000/svg">
              <path d="M 20 90 A 70 70 0 0 1 160 90"
                    fill="none" stroke="var(--gray-4)" stroke-width="10" stroke-linecap="round"/>
              <path d="M 20 90 A 70 70 0 0 1 160 90"
                    fill="none" stroke="var(--{color}-9)" stroke-width="10"
                    stroke-linecap="round"
                    stroke-dasharray="{progress:.1f} {circumference:.1f}"/>
              <text x="90" y="78" text-anchor="middle"
                    font-size="34" font-weight="700" fill="var(--gray-12)">{score}</text>
              <text x="90" y="94" text-anchor="middle"
                    font-size="11" fill="var(--gray-10)">/ 100</text>
            </svg>
            """
        ),
        flex_shrink="0",
    )


def _article_row(row: Dict[str, str]) -> rx.Component:
    label = rx.cond(AuthState.language == "en", row["label_en"], row["label_ja"])
    comment = rx.cond(AuthState.language == "en", row["comment_en"], row["comment_ja"])
    color = row["color"]
    score_int = int(row["score"])
    bar_pct = f"{score_int * 10}%"

    return rx.vstack(
        rx.hstack(
            rx.text(label, size="2", weight="medium", color="var(--gray-12)"),
            rx.spacer(),
            rx.hstack(
                rx.text(str(score_int), size="3", weight="bold", color=f"var(--{color}-11)"),
                rx.text("/ 10", size="1", color="var(--gray-9)"),
                spacing="1", align="baseline",
            ),
            spacing="2", align="center", width="100%",
        ),
        rx.box(
            rx.box(
                width=bar_pct,
                height="100%",
                background=f"var(--{color}-9)",
                border_radius="3px",
                transition="width 0.6s ease",
            ),
            width="100%",
            height="6px",
            background="var(--gray-4)",
            border_radius="3px",
            overflow="hidden",
        ),
        rx.text(comment, size="1", color="var(--gray-10)", line_height="1.5"),
        spacing="1",
        align="start",
        width="100%",
    )


def _concern_row(text: str) -> rx.Component:
    return rx.hstack(
        rx.icon("circle-alert", size=14, color="var(--ruby-10)", flex_shrink="0"),
        rx.text(text, size="2", color="var(--gray-12)", line_height="1.5"),
        spacing="2",
        align="start",
        width="100%",
    )


def _constitution_card() -> rx.Component:
    verdict = rx.cond(
        AuthState.language == "en",
        _SAMPLE_CONSTITUTION_VERDICT_EN,
        _SAMPLE_CONSTITUTION_VERDICT_JA,
    )
    summary = rx.cond(
        AuthState.language == "en",
        _SAMPLE_CONSTITUTION_SUMMARY_EN,
        _SAMPLE_CONSTITUTION_SUMMARY_JA,
    )

    score = _SAMPLE_CONSTITUTION_SCORE
    color = _score_color(score)

    head = rx.hstack(
        rx.icon("scroll-text", size=18, color="var(--violet-11)"),
        rx.text(AuthState.t["ga_ai_const_title"], size="3", weight="bold", color="var(--gray-12)"),
        rx.spacer(),
        rx.badge(
            verdict,
            color_scheme=color,
            variant="soft",
            size="2",
        ),
        spacing="2", align="center", width="100%",
    )

    top_block = rx.flex(
        _gauge_arc(score),
        rx.vstack(
            rx.text(AuthState.t["ga_ai_const_summary_label"], size="1", weight="medium", color="var(--gray-10)"),
            rx.text(summary, size="2", color="var(--gray-12)", line_height="1.6"),
            spacing="1",
            align="start",
            flex="1",
            min_width="240px",
        ),
        spacing="4",
        align="center",
        wrap="wrap",
        width="100%",
    )

    articles_block = rx.vstack(
        rx.text(AuthState.t["ga_ai_const_articles_label"], size="2", weight="medium", color="var(--gray-11)"),
        *[_article_row(r) for r in _SAMPLE_ARTICLE_ROWS],
        spacing="3",
        width="100%",
        align="start",
    )

    concerns_block = rx.vstack(
        rx.hstack(
            rx.icon("circle-alert", size=14, color="var(--ruby-10)"),
            rx.text(AuthState.t["ga_ai_const_concerns_label"], size="2", weight="medium", color="var(--ruby-11)"),
            spacing="1", align="center",
        ),
        rx.cond(
            AuthState.language == "en",
            rx.vstack(
                *[_concern_row(c) for c in _SAMPLE_CONCERNS_EN],
                spacing="2", width="100%", align="start",
            ),
            rx.vstack(
                *[_concern_row(c) for c in _SAMPLE_CONCERNS_JA],
                spacing="2", width="100%", align="start",
            ),
        ),
        spacing="2",
        width="100%",
        align="start",
        padding="12px",
        background="var(--ruby-2)",
        border=f"1px solid {rx.color('ruby', 4)}",
        border_radius="8px",
    )

    return rx.box(
        rx.vstack(
            head,
            top_block,
            articles_block,
            concerns_block,
            spacing="4",
            width="100%",
            align_items="stretch",
        ),
        padding="18px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


# ─── 状態 4: analyzed — Feature B: VISION 2030 KPI ─────────────────────────────

def _radar_grid_polygon(points_str: str) -> rx.Component:
    return rx.html(
        f'<polygon points="{points_str}" fill="none" stroke="var(--gray-5)" stroke-width="1"/>'
    )


def _radar_chart() -> rx.Component:
    grids = _RADAR["grids"]  # 4 rings
    axis_lines = _RADAR["axis_lines"]
    labels = _RADAR["label_positions"]
    polygon = _RADAR["polygon"]
    points = _RADAR["points"]

    axes_ja = _SAMPLE_KPI_AXES_JA
    axes_en = _SAMPLE_KPI_AXES_EN

    # 1 つの大きな <svg> に組み立てる（rx.html で一発描画）
    svg_parts: list[str] = [
        '<svg width="350" height="350" viewBox="0 0 350 350" xmlns="http://www.w3.org/2000/svg" '
        'style="max-width:100%;height:auto;display:block;margin:0 auto;">'
    ]

    # 4 リング (内側→外側)
    ring_opacities = [0.35, 0.5, 0.7, 1.0]
    for ring_pts, op in zip(grids, ring_opacities):
        svg_parts.append(
            f'<polygon points="{ring_pts}" fill="var(--gray-3)" '
            f'stroke="var(--gray-5)" stroke-width="1" opacity="{op}"/>'
        )

    # 軸線
    for axis in axis_lines:
        svg_parts.append(
            f'<line x1="{_RADAR_CX}" y1="{_RADAR_CY}" '
            f'x2="{axis["x2"]}" y2="{axis["y2"]}" '
            f'stroke="var(--gray-5)" stroke-width="1"/>'
        )

    # データポリゴン
    svg_parts.append(
        f'<polygon points="{polygon}" '
        'fill="var(--violet-9)" fill-opacity="0.25" '
        'stroke="var(--violet-10)" stroke-width="2"/>'
    )

    # データポイント
    for p in points:
        svg_parts.append(
            f'<circle cx="{p["cx"]}" cy="{p["cy"]}" r="4" '
            'fill="var(--violet-11)" stroke="var(--gray-1)" stroke-width="2"/>'
        )

    svg_parts.append("</svg>")
    svg_ja = "".join(svg_parts[:1] + [
        # ラベル（JA）
        *svg_parts[1:-1],
        *[
            f'<text x="{labels[i]["x"]}" y="{labels[i]["y"]}" '
            f'text-anchor="{labels[i]["anchor"]}" dominant-baseline="middle" '
            f'font-size="12" font-weight="600" fill="var(--gray-12)">{axes_ja[i]}</text>'
            for i in range(len(axes_ja))
        ],
        svg_parts[-1],
    ])
    svg_en = "".join(svg_parts[:1] + [
        *svg_parts[1:-1],
        *[
            f'<text x="{labels[i]["x"]}" y="{labels[i]["y"]}" '
            f'text-anchor="{labels[i]["anchor"]}" dominant-baseline="middle" '
            f'font-size="11" font-weight="600" fill="var(--gray-12)">{axes_en[i]}</text>'
            for i in range(len(axes_en))
        ],
        svg_parts[-1],
    ])

    return rx.cond(
        AuthState.language == "en",
        rx.html(svg_en),
        rx.html(svg_ja),
    )


def _kpi_legend() -> rx.Component:
    """各軸の数値とコメントをリスト表示。"""
    rows: list[rx.Component] = []
    for i, score in enumerate(_SAMPLE_KPI_SCORES):
        label = rx.cond(
            AuthState.language == "en",
            _SAMPLE_KPI_AXES_EN[i],
            _SAMPLE_KPI_AXES_JA[i],
        )
        comment = rx.cond(
            AuthState.language == "en",
            _SAMPLE_KPI_COMMENTS_EN[i],
            _SAMPLE_KPI_COMMENTS_JA[i],
        )
        color = _score_color(score)
        rows.append(
            rx.hstack(
                rx.box(
                    width="8px",
                    height="40px",
                    background=f"var(--{color}-9)",
                    border_radius="2px",
                    flex_shrink="0",
                ),
                rx.vstack(
                    rx.hstack(
                        rx.text(label, size="2", weight="medium", color="var(--gray-12)"),
                        rx.spacer(),
                        rx.text(str(score), size="3", weight="bold", color=f"var(--{color}-11)"),
                        rx.text("/ 100", size="1", color="var(--gray-9)"),
                        spacing="1", align="baseline", width="100%",
                    ),
                    rx.text(comment, size="1", color="var(--gray-10)", line_height="1.4"),
                    spacing="0",
                    align="start",
                    flex="1",
                    min_width="0",
                ),
                spacing="2",
                align="center",
                width="100%",
            )
        )
    return rx.vstack(*rows, spacing="3", width="100%", align="start")


def _kpi_card() -> rx.Component:
    head = rx.hstack(
        rx.icon("radar", size=18, color="var(--indigo-11)"),
        rx.text(AuthState.t["ga_ai_kpi_title"], size="3", weight="bold", color="var(--gray-12)"),
        rx.spacer(),
        rx.badge(AuthState.t["ga_ai_kpi_vision_label"], color_scheme="indigo", variant="soft", size="1"),
        spacing="2", align="center", width="100%",
    )

    body = rx.flex(
        rx.box(
            _radar_chart(),
            flex="0 0 auto",
            width=["100%", "100%", "350px"],
        ),
        rx.box(
            _kpi_legend(),
            flex="1",
            min_width="240px",
        ),
        spacing="4",
        wrap="wrap",
        width="100%",
        align="start",
    )

    return rx.box(
        rx.vstack(
            head,
            body,
            spacing="4",
            width="100%",
            align_items="stretch",
        ),
        padding="18px",
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="12px",
        background="var(--gray-2)",
        width="100%",
    )


def _state_analyzed() -> rx.Component:
    return rx.vstack(
        _constitution_card(),
        _kpi_card(),
        rx.hstack(
            rx.icon("info", size=12, color="var(--gray-9)"),
            rx.text(
                AuthState.t["ga_ai_disclaimer"],
                size="1", color="var(--gray-9)", line_height="1.5",
            ),
            spacing="1",
            align="start",
            width="100%",
        ),
        spacing="4",
        width="100%",
        align_items="stretch",
    )


# ─── デモ用: 状態切り替えボタン ────────────────────────────────────────────────

_DEMO_STATES = [
    ("none",      "対象外",   "ban"),
    ("pending",   "Pending",   "clock"),
    ("analyzing", "Analyzing", "loader"),
    ("analyzed",  "Analyzed",  "sparkles"),
    ("failed",    "Failed",    "triangle-alert"),
]


def _demo_switcher() -> rx.Component:
    buttons = [
        rx.button(
            rx.icon(icon, size=12),
            rx.text(label, size="1"),
            size="1",
            variant=rx.cond(GAAIDemoState.demo_state == key, "solid", "soft"),
            color_scheme=rx.cond(GAAIDemoState.demo_state == key, "violet", "gray"),
            on_click=GAAIDemoState.set_state(key),
            cursor="pointer",
        )
        for key, label, icon in _DEMO_STATES
    ]
    return rx.box(
        rx.hstack(
            rx.icon("flask-conical", size=12, color="var(--amber-10)"),
            rx.text("DEMO: 状態切替", size="1", weight="medium", color="var(--amber-11)"),
            *buttons,
            spacing="2",
            align="center",
            wrap="wrap",
        ),
        padding="8px 12px",
        border=f"1px dashed {rx.color('amber', 7)}",
        border_radius="8px",
        background="var(--amber-2)",
        width="100%",
    )


# ─── 公開エントリポイント ──────────────────────────────────────────────────────

def ai_analysis_section() -> rx.Component:
    """GA 詳細ページの voting summary 直後に配置するセクション。"""
    body = rx.match(
        GAAIDemoState.demo_state,
        ("none",      _state_none()),
        ("pending",   _state_pending()),
        ("analyzing", _state_analyzing()),
        ("analyzed",  _state_analyzed()),
        ("failed",    _state_failed()),
        _state_analyzed(),
    )
    return rx.vstack(
        _demo_switcher(),
        _ai_card(body),
        spacing="3",
        width="100%",
        align_items="stretch",
    )
