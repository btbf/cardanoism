import os
import sys
import mariadb
import reflex as rx

#Connect to MariaDB Platform
def dbConnect():
    print(os.getenv("DB_USER"))
    print(os.getenv("DB_PASS"))
    print(os.getenv("DB_HOST"))
    print(os.getenv("DB_PORT"))
    print(os.getenv("DB_NAME"))
    try:
        conn = mariadb.connect(
            user=os.getenv("DB_USER"),
            password=os.getenv('DB_PASS'),
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT')),
            database=os.getenv('DB_NAME')
            
        )
    except mariadb.Error as e:
        print(f"Error connecting to MariaDB Platform: {e}")
        sys.exit(1)

    #Get Cursor
    cursor = conn.cursor(dictionary=True)
    return cursor, conn


class AppState(rx.State):
    challenge_id: str = ""
    proposals: list[dict[str, str]] = []
    current_page: int = 1
    items_per_page: int = 30
    page_number: list[int]
    pagenation_number: list[int]
    total_pages: int = 0
    total_items: int = 0
    inputed_value: str = ""
    start_page: int = ""
    end_page: int = ""
    middle_page:list[str]
    load: bool = False
    
    def on_load(self):
        # super().__init__()
        self.data_fetch()
        
    
    
    def data_fetch(self):
        dbCon = dbConnect()
        cursor = dbCon[0]
        conn = dbCon[1]
        print(cursor)
        print(conn)
        
        data_query = """
        SELECT proposals.*,
        challenges.title as challenge_title, 
        challenges.title_ja as challenge_title_ja,
        proposal_detail.headline_problem_ja,
        proposal_detail.applicant_name,
        proposal_detail.project_duration,
        proposal_detail.headline_solution_ja,
        proposal_detail.open_source,
        proposal_detail.tag
        FROM proposals
        INNER JOIN challenges
        ON proposals.challenge_id = challenges.id
        INNER JOIN proposal_detail
        ON proposals.ideascale_id = proposal_detail.ideascale_id
        """
        count_query = f"SELECT COUNT(*) as total FROM proposals"
        
        if self.challenge_id:
            where_query = f" WHERE proposals.challenge_id LIKE '{self.challenge_id}'"
            data_query += where_query
            count_query += where_query
            
        if self.inputed_value:
            cursor.execute("SHOW COLUMNS FROM proposals")
            columns = [column["Field"] for column in cursor.fetchall()]
            search_value = f"%{str(self.inputed_value).lower()}%"
            # WHERE句を動的に生成
            where_clause = " OR ".join([f"proposals.{column} LIKE '{search_value}'" for column in columns])
            
            if self.challenge_id:
                data_query += f" AND ({where_clause})"
                count_query += f" AND ({where_clause})"
            else:
                data_query += f" WHERE {where_clause}"
                count_query += f" WHERE {where_clause}"
            
        limit_query = f" LIMIT {self.items_per_page} OFFSET {(self.current_page - 1) * self.items_per_page}"
        
        #データ取得クエリ
        query = data_query + limit_query
        print(query)
        cursor.execute(query)
        self.proposals = cursor.fetchall()
        
        #データ件数クエリ
        print(count_query)
        cursor.execute(count_query)
        self.total_items = cursor.fetchone()['total']
        print(self.total_items)
        
        #ページネーション変数
        self.total_pages = (self.total_items + self.items_per_page - 1) // self.items_per_page
        self.start_page = max(1, self.current_page - 3)
        self.end_page = min(self.total_pages, self.current_page + 3)
        self.middle_page = list(range(self.start_page, self.end_page))
        print(self.middle_page)
        self.load = True
        #データベースクローズ
        cursor.close()
        conn.close()
    
    
    #--------フィルター関数群----------------
    
    def set_selected_value(self, value: dict[str, str]):
        print(value)
        if value:
            self.challenge_id = value["value"]
        else:
            self.challenge_id = "%"
            
        self.data_fetch()
        
    def set_inputed_value(self, value: str):
        self.inputed_value = value
        self.current_page = 1
        self.data_fetch()
        
    #--------------------------------------------------
    
    #--------ページネーション関数群----------------------
    
    def go_to_page(self, page: int):
        self.current_page = page
        self.data_fetch()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.data_fetch()
        return rx.call_script("window.scrollTo(0, 0)")

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.data_fetch()
        return rx.call_script("window.scrollTo(0, 0)")

    def set_page(self, page: int):
        if 1 <= page <= self.total_pages:
            self.current_page = page
            self.data_fetch()
        return rx.call_script("window.scrollTo(0, 0)")
            
            
    
    #--------------------------------------------------
            
class ProposalAppState(rx.State):
    proposal: list[dict[str, str]] = []
    ideascale_id: str
    load: bool = False
    
    def on_load(self, id:str):
        self.ideascale_id = id
        if self.ideascale_id.isdecimal():
            self.data_fetch()
        else:
            self.proposal = ""
        
    def data_fetch(self):
        dbCon = dbConnect()
        cursor = dbCon[0]
        conn = dbCon[1]
        print(cursor)
        print(conn)
        
        proposal_query = f"""
        SELECT proposals.*,
        challenges.title as challenge_title,
        challenges.title_ja as challenge_title_ja,
        proposal_detail.title as proposal_title,
        proposal_detail.title_ja as proposal_title_ja,
        proposal_detail.headline_problem_ja,
        proposal_detail.applicant_name,
        proposal_detail.project_duration,
        proposal_detail.headline_solution_ja,
        proposal_detail.open_source,
        proposal_detail.tag,
        proposal_detail.solution,
        proposal_detail.impact,
        proposal_detail.capability_feasibility,
        proposal_detail.project_milestones,
        proposal_detail.budget_costs,
        proposal_detail.value_for_money
        FROM proposals
        INNER JOIN challenges
        ON proposals.challenge_id = challenges.id
        INNER JOIN proposal_detail
        ON proposals.ideascale_id = proposal_detail.ideascale_id
        WHERE proposals.ideascale_id LIKE '{self.ideascale_id}'
        """
        
        print(proposal_query)
        cursor.execute(proposal_query)
        self.proposal = cursor.fetchall()
        self.load = True
        print(self.proposal)
        
        #データベースクローズ
        cursor.close()
        conn.close()
