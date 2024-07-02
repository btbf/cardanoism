import reflex as rx
from typing import Any, Dict, List, Union

from cardanoism import styles
from cardanoism.templates import template
from cardanoism.components.proposal_card import card_foreach_dict
from cardanoism.components.proposal_detail import detail_foreach_dict
from cardanoism.components.proposal_pagenation import pagination_component
from cardanoism.components.componets import top_button_component
from cardanoism.backend.db_connect import AppState,ProposalAppState


class ReactSelectLib(rx.Component):
    library = "react-select"
    tag = "Select"


class CatalystChallengeSelect(ReactSelectLib):
    is_default = True
    isClearable = True
    placeholder:rx.Var[str]
    options: rx.Var[List[Dict[str, str]]]
    defaultValue: rx.Var[Dict[str, str]]
    onChange: rx.EventHandler[lambda value: [value] ]


challegeFilter = CatalystChallengeSelect.create


class ChallengeState(rx.State):
    defaultValue: Dict[str, str]
    value: str
    
@template(route="/catalyst/", title="カタリストファンド", on_load=AppState.on_load)
def catalyst() -> rx.Component:
    return rx.vstack(
            rx.cond(
                AppState.load,
                rx.box(
                    rx.callout(
                    "AI翻訳で日本語化しておりますが完璧な翻訳精度ではないため、分かりづらい日本語になっている箇所が多数あります",
                    icon="info",
                    color_scheme="red",
                    margin_bottom="20px"
                    ),
                    rx.flex(
                        rx.flex(
                            rx.input(
                                placeholder="全文検索...(IdeascaleNo、タイトル、提案者、課題、解決策、本文、etc...)",
                                size="3",
                                max_length=100,
                                on_change=lambda value: AppState.set_inputed_value(value,ChallengeState.value),
                                width=["90%","90%","90%","300px","300px"],
                                margin_x="10px",
                                margin_bottom="10px"
                            ),
                            challegeFilter(
                                options = [
                                    {'value': '142', 'label': 'F12：カルダノのパートナーと実世界の統合'},
                                    {'value': '143', 'label': 'F12：カルダノの使用事例：コンセプト'},
                                    {'value': '144', 'label': 'F12：カルダノの使用事例：MVP'},
                                    {'value': '145', 'label': 'F12：カルダノの使用事例：製品'},
                                    {'value': '140', 'label': 'F12：カルダノオープン：開発者'},
                                    {'value': '141', 'label': 'F12：カルダノオープン：エコシステム'},
                                ],
                                #defaultValue = ChallengeState.defaultValue,
                                #value = ChallengeState.value,
                                placeholder="ファンドカテゴリ選択",
                                onChange = lambda value: AppState.set_selected_value(value),
                                width=["90%","90%","90%","500px","500px"],
                                margin_x="10px"
                            ),
                            #width="100%",
                            spacing="2",
                            #position="fixed",
                            #z_index="500",
                            padding_y="10px",
                            background_color="white",
                            display=["block","block","block","flex","flex"],
                        ),
                        rx.box(
                            rx.flex(
                               rx.text(AppState.total_items, size='6', weight="bold", color_scheme="crimson"),
                               rx.text("件"),
                            #    rx.text("1件～30件を表示中"),
                               spacing="2",
                               align_items="center"
                            ),
                            widht="100%",
                            padding_y="10px"
                        ),
                        justify_content="space-between",
                        align_items="end",
                        display=["block","block","block","flex","flex"],
                    ),
                    
                card_foreach_dict(),
                top_button_component(),
                pagination_component(AppState),
                ),
                rx.box(
                    rx.spinner(size="3"),
                    padding_y="15px",
                ),
            ),
            rx.script(
                    """
                    window.addEventListener('scroll', function() {
                        var topButton = document.getElementById('top-button');
                        if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
                            topButton.style.display = 'block';
                        } else {
                            topButton.style.display = 'none';
                        }
                    });
                    """
                ),
    )
    

class proposal_detail_State(rx.State):
    @rx.var
    def ideascale_id(self) -> str:
        return self.router.page.params.get("ideascale_id", False)

@template(route="/catalyst/[ideascale_id]", title="カタリストファンド", on_load=ProposalAppState.on_load(proposal_detail_State.ideascale_id))
def proposal_detail_page() -> rx.Component:
    return rx.vstack(
        detail_foreach_dict(),
        margin_top="15px",
    )