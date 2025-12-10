import reflex as rx
from cardanoism.backend.db_connect import AppState

def pagination_component(state: AppState):
    
    def create_page_button(page):
        is_active = page == state.current_page
        return rx.button(
            rx.text(page, weight="bold"),
            on_click=lambda: state.set_page(page),
            variant=rx.cond(is_active, "solid", "soft"),
            color_scheme="indigo",
            radius="full",
            size="2",
            padding_x="10px",
            class_name="md:inline-flex hidden",
            _hover={"cursor": "pointer"},
        )

    def create_ellipsis():
        return rx.button(
            "...",
            radius="full",
            size="2",
            variant="soft",
            color_scheme="gray",
            class_name="md:inline-flex hidden",
            _hover={"cursor": "pointer"},
        )

    return rx.flex(
        rx.button(
            rx.icon(tag="chevron-left"),
            on_click=state.prev_page,
            radius="full",
            size="2",
            variant="soft",
            color_scheme="indigo",
            disabled=state.current_page == 1,
            _hover={"cursor": "pointer"},
        ),
       
        # 最初のページ
        rx.cond(state.start_page > 1, 
                rx.box(
                create_page_button(1),
                rx.cond(state.start_page > 2, 
                        create_ellipsis())
        )),
      
        #中央のページ
        rx.foreach(AppState.middle_page, create_page_button),
    
        # 最後のページ
        rx.cond(state.end_page < state.total_pages, rx.box(
            rx.cond(state.end_page < state.total_pages - 1, create_ellipsis()),
            create_page_button(state.total_pages)
        )),

        rx.button(
            rx.icon(tag="chevron-right"),
            on_click=state.next_page,
            radius="full",
            size="2",
            variant="soft",
            color_scheme="indigo",
            disabled=state.current_page == state.total_pages,
            _hover={"cursor": "pointer"},
        ),
        class_name="pagination gap-2",
        padding_top="2em",
        justify="end",
        align="center",
    )
