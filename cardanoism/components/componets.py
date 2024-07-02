import reflex as rx
from cardanoism import styles

def top_button_component():
    
    return rx.box(
        rx.link(
            rx.icon("circle-chevron-up", size=60, color="var(--indigo-8)"),
            on_click=rx.call_script("window.scrollTo(0, 0)"),
        ),
        id="top-button",
        **styles.top_button,
    )


    

        #     rx.chakra.button(
        # "TOPへ移動",
        # id="top-button",
        # on_click=rx.call_script("window.scrollTo(0, 0)"),
        # ),
    