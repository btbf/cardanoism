import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.db_connect import ProposalAppState
from cardanoism.components.proposal_detail import detail_foreach_dict


@template(route="/catalyst/proposals/[proposal_id]", title="Proposal | Cardanoism", on_load=ProposalAppState.on_load)
def proposal_detail_page() -> rx.Component:
    return rx.box(
        detail_foreach_dict(),
        width="100%",
        max_width="1130px",
    )
