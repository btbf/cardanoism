import reflex as rx
from cardanoism.backend.db_connect import AppState

def pagination_component(state: AppState):
    
    def create_page_button(page):
        return rx.button(
            rx.text(page),
            on_click=lambda: state.set_page(page),
            #on_click=click(),
            class_name=rx.cond(page == state.current_page, "active relative z-10 inline-flex items-center bg-indigo-600 px-4 py-2 text-sm font-semibold text-white focus:z-20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600", "inactive relative hidden items-center bg-white px-4 py-2 text-sm font-semibold text-gray-900 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0 md:inline-flex"),
            radius="none",
            _hover={"cursor": "pointer"}

        )

    def create_ellipsis():
        return rx.button("...", radius="none", class_name="inactive relative inline-flex items-center bg-white px-4 py-2 text-sm font-semibold text-gray-700 ring-1 ring-inset ring-gray-300 focus:outline-offset-0", _hover={"cursor": "pointer"})

    return rx.flex(
        rx.button(rx.icon(tag="chevron-left"), on_click=state.prev_page, radius="none", class_name="relative inline-flex items-center rounded-l-md px-2 py-2 bg-white text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0", disabled=state.current_page == 1, _hover={"cursor": "pointer"}),
       
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

        rx.button(rx.icon(tag="chevron-right"), on_click=state.next_page, radius="none", class_name="relative inline-flex items-center rounded-r-md bg-white px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0", disabled=state.current_page == state.total_pages, _hover={"cursor": "pointer"}),
        class_name="pagination",
        padding_top="2em",
        justify="end",
    )
