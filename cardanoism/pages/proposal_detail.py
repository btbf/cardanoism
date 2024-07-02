"""The dashboard page."""

from cardanoism.templates import template

import reflex as rx

# class proposal_detail_State(rx.State):
#     @rx.var
#     def ideascale_id(self) -> str:
#         return self.router.page.params.get("ideascale_id", False)

# @template(route="/catalyst/[ideascale_id]", title="カタリストファンド")
# def proposal_detail() -> rx.Component:
#     return rx.vstack(
#         proposal_detail_State.ideascale_id,
#         rx.heading("カタリスト", size="8"),
#         rx.text("Welcome to Reflex!"),
#         rx.text(
#             "You can edit this page in ",
#             rx.code("{your_app}/pages/fund.py"),
#         ),
#     )