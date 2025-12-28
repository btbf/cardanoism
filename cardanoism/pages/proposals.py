import reflex as rx

from cardanoism.templates.template import render_page
from cardanoism.backend.db_connect import AppState
from cardanoism.components.proposal_detail import detail_foreach_dict


OGP_IMAGE_PATH = "./cardanoism-ogp.jpg"


def _proposal_title() -> rx.Var:
    return rx.cond(
        AppState.modal_proposal.get("title_ja"),
        AppState.modal_proposal.get("title_ja").to(str) + " | Cardanoism",
        rx.cond(
            AppState.modal_proposal.get("title"),
            AppState.modal_proposal.get("title").to(str) + " | Cardanoism",
            "提案詳細 | Cardanoism",
        ),
    )


def _proposal_description() -> rx.Var:
    return rx.cond(
        AppState.modal_proposal.get("headline_problem_ja"),
        AppState.modal_proposal.get("headline_problem_ja").to(str),
        rx.cond(
            AppState.modal_proposal.get("problem_ja"),
            AppState.modal_proposal.get("problem_ja").to(str),
            rx.cond(
                AppState.modal_proposal.get("problem"),
                AppState.modal_proposal.get("problem").to(str),
                "Cardanoismの提案詳細ページです。",
            ),
        ),
    )


def proposal_detail_page() -> rx.Component:
    return render_page(
        rx.box(
        rx.el.meta(name="description", content=_proposal_description()),
        rx.el.meta(property="og:type", content="article"),
        rx.el.meta(property="og:title", content=_proposal_title()),
        rx.el.meta(property="og:description", content=_proposal_description()),
        rx.el.meta(property="og:url", content=AppState.router.page.full_path),
        rx.el.meta(property="og:image", content=OGP_IMAGE_PATH),
        rx.el.meta(name="twitter:card", content="summary_large_image"),
        rx.el.meta(name="twitter:title", content=_proposal_title()),
        rx.el.meta(name="twitter:description", content=_proposal_description()),
        rx.el.meta(name="twitter:url", content=AppState.router.page.full_path),
        rx.el.meta(name="twitter:image", content=OGP_IMAGE_PATH),
        rx.cond(
            AppState.selected_proposal_uuid,
            detail_foreach_dict(),
            rx.flex(
                rx.spinner(size="3"),
                justify="center",
                align="center",
                width="100%",
                flex="1",
                padding_y="20px",
            ),
        ),
        width="100%",
        max_width="1130px",
        )
    )
