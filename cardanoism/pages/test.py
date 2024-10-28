import reflex as rx
from typing import List, Dict
from cardanoism.templates import template


class ForeachState(rx.State):
    user: List[Dict[str,int]] = [
        {"value":1, "max":100},
        {"value":30, "max":200},
        {"value":150, "max":500},
        {"value":600, "max":1000},
    ]

def progress_box(user: Dict[str,int]):
    cul = (user['value'] / user['max']) * 100
    return rx.box(
        rx.text(f"{cul}%"),
        rx._x.progress(value=user['value'], max=user['max'], width='200px')
    )

@template(route="/test",)
def foreach_example() -> rx.Component:
    return rx.box(
        rx.foreach(ForeachState.user, progress_box),
    )