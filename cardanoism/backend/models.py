import reflex as rx

from typing import Optional
from typing import Any, Dict, List, Union
from sqlmodel import Field, select, or_

class tags(rx.Model, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    title_ja: str
    
    
class funds(rx.Model, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    proposals_count: int
    amount: int
    currency: str
    launch_date: str
    currency_symbol: int
    slug: str
    
class proposals(rx.Model, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    fund_id: int 
    challenge_id: int 
    title: str
    ideascale_link: str
    ideascale_user: str
    ideascale_id: int
    amount_requested: int
    project_status: str
    funding_status: str
    problem: str
    solution: str
    currency_symbol: str
    currency: str


class proposalsState(rx.State):
    proposalsList: list[proposals] = []
    search_value: str = ""
    #challenge_id: str = ""
    # ページネーションのパラメータ
    
    def load_entries(self) -> list[proposals]:
        #from cardanoism.pages.dbtest import ChallengeState
        page = 1  # 現在のページ
        page_size = 30  # 1ページあたりのアイテム数
        # print(value)
        with rx.session() as session:
            query = select(proposals).limit(page_size)
            #query = query.where(proposals.challenge_id == value)
            if self.search_value:
                #query = select(proposals).where(proposals.challenge_id == 143).limit(page_size)
                search_value = f"%{str(self.search_value).lower()}%"
                query = query.where(
                    or_(
                        *[
                            getattr(proposals, field).ilike(search_value)
                            for field in proposals.get_fields()
                        ],
                    )
                )
            
            self.proposalsList = session.exec(query).all()


    def filter_values(self, search_value):
        self.search_value = search_value
        self.load_entries()
        
    
    def challenge_values(self):
        self.load_entries()
        