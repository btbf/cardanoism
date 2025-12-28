import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.db_connect import AppState
from cardanoism.components.proposal_detail import detail_foreach_dict


@template(route="/catalyst/proposals/[proposal_id]", title="提案詳細 | Cardanoism", on_load=AppState.load_detail_page)
def proposal_detail_page() -> rx.Component:
    return rx.box(
        rx.el.title(
            rx.cond(
                AppState.modal_proposal.get("title_ja"),
                AppState.modal_proposal.get("title_ja").to(str) + " | Cardanoism",
                "提案詳細 | Cardanoism",
            )
        ),
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
