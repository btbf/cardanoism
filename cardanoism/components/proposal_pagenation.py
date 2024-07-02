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

        )

    def create_ellipsis():
        return rx.button("...", radius="none", class_name="inactive relative inline-flex items-center bg-white px-4 py-2 text-sm font-semibold text-gray-700 ring-1 ring-inset ring-gray-300 focus:outline-offset-0")

    return rx.flex(
        rx.button(rx.icon(tag="chevron-left"), on_click=state.prev_page, radius="none", class_name="relative inline-flex items-center rounded-l-md px-2 py-2 bg-white text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0", disabled=state.current_page == 1),
       
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

        rx.button(rx.icon(tag="chevron-right"), on_click=state.next_page, radius="none", class_name="relative inline-flex items-center rounded-r-md bg-white px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0", disabled=state.current_page == state.total_pages),
        class_name="pagination",
        padding_top="2em",
        justify="end",
    # )
    )
#     start_page = max(1, state.current_page - 3)
#     end_page = min(state.total_pages, state.current_page + 3)

#     def create_page_buttons():
#         pages = []
        
#         # 最初のページを表示
#         if start_page > 1:
#             pages.append(rx.button("1", on_click=lambda: state.set_page(1)))
#             if start_page > 2:
#                 pages.append(rx.text("..."))

#         # 中央のページを表示
#         for page in range(start_page, end_page + 1):
#             pages.append(
#                 rx.button(
#                     str(page),
#                     on_click=lambda p=page: state.set_page(p),
#                     class_name=rx.cond(page == state.current_page, "active", "inactive")
#                 )
#             )

#         # 最後のページを表示
#         if end_page < state.total_pages:
#             if end_page < state.total_pages - 1:
#                 pages.append(rx.text("..."))
#             pages.append(rx.button(str(state.total_pages), on_click=lambda: state.set_page(state.total_pages)))

#         return pages

    # return rx.box(
    #     rx.button("Previous", on_click=state.prev_page, disabled=state.current_page == 1),
    #     #*create_page_buttons(),
    #     rx.button("Next", on_click=state.next_page, disabled=state.current_page == state.total_pages),
    #     class_name="pagination"
    # )


# def pagination_component(page_number: int):
#     #total_pages = (AppState.total_items + AppState.items_per_page - 1) // AppState.items_per_page
#     # print(AppState.total_items)
#     return rx.button(
#             page_number + 1, 
#             on_click=lambda page_number=page_number: AppState.go_to_page(page_number + 1),
#             radius="none"
#             )
    
# def pagenation():
#     return rx.hstack(
#         rx.foreach(AppState.page_number, pagination_component),
#         spacing="0",
#     )