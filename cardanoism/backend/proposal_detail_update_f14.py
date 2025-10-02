#import deepl
import requests
import json
import re
import fnmatch
from typing import List, Dict, Any

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from time import sleep
from bs4 import BeautifulSoup

from db_connect import dbConnect
from chatgpt_api import chatgpt_api
from scraping_f14 import login_ideascale


def translate(gpt_assistant, pre_word):
    if pre_word:
        word_ja = chatgpt_api(gpt_assistant,pre_word)
        print(word_ja)
    else:
        word_ja = pre_word
    return word_ja

def wildcard_to_regex(pattern):
    # '.'は任意の文字、'*'は0回以上の繰り返しを表す正規表現に変換
    regex_pattern = pattern.replace('*', '.*')
    return re.compile(regex_pattern)
    
    
dbCon = dbConnect()
cursor = dbCon[0]
conn = dbCon[1]
print(cursor)
print(conn)

chrome_driver = login_ideascale()

fundId=147
#chatGPT翻訳
# 見出し翻訳用（headline tone）
gpt_assistant_headline = """
You are half American and half Japanese. 
You were born and raised in New York, USA, for 20 years, and you are perfectly bilingual in English and Japanese. 
You have been living in Japan for 10 years, working as a programmer and Japanese-English translator. 
You are also familiar with the カルダノ blockchain and Project カタリスト.

Your task is strict:
- Translate any English text you receive into **natural, correct Japanese**. 
- Output must always be in **headline tone**. 
- Do not add, omit, summarize, or explain anything. 
- Always translate "Cardano" as **カルダノ**, "Catalyst" as **カタリスト**. 
- Do not output anything other than the translated text.
"""

# 本文翻訳用（詳細）
gpt_assistant_detail = """
You are half American and half Japanese. 
You were born and raised in New York, USA, for 20 years, and you are perfectly bilingual in English and Japanese. 
You have been living in Japan for 10 years, working as a programmer and Japanese-English translator. 
You are also familiar with the カルダノ blockchain and Project カタリスト.

Your task is strict:
- Translate any English text you receive into **accurate, natural Japanese**. 
- Do not add, omit, summarize, or explain anything. Translate only the given content. 
- If the input contains **HTML tags**, preserve them exactly as they are and only translate the text content inside. 
- Always translate "Cardano" as **カルダノ**, "Catalyst" as **カタリスト**. 
- Output must be only the translation result, nothing else.
"""


proposals: List[Dict] = []
error_ids = []

data_query =f"""
SELECT id,title,ideascale_link,ideascale_id
FROM proposals
WHERE fund_id = 147
AND id >= 24141
ORDER BY id ASC;"""

print(data_query)
cursor.execute(data_query)
proposals = cursor.fetchall()

for index, row in enumerate(proposals):
    try:
        #変数初期化
        id = ""
        ideascale_id = ""
        title = ""
        title_ja = ""
        headline_problem = ""
        headline_problem_ja = ""
        applicant_name = ""
        project_duration = ""
        headline_solution = ""
        headline_solution_ja = ""
        open_source = ""
        tag = ""
        solution = ""
        solution_ja = ""
        impact = ""
        impact_ja = ""
        capability_feasibility = ""
        capability_feasibility_ja = ""
        project_milestones = ""
        project_milestones_ja = ""
        budget_costs = ""
        budget_costs_ja = ""
        value_for_money = ""
        value_for_money_ja = ""
        custom_fields = []
        api_data = []
        api_data2 = []

        #スクレイピングSTART
        ideascale_link = row["ideascale_link"]

        #提案個別ページ
        chrome_driver.get(ideascale_link)
        sleep(1)
                
        wait = WebDriverWait(chrome_driver, 60)
        result = wait.until(EC.presence_of_all_elements_located((By.ID, 'stats')))


        # 対象とする見出しリスト
        targets = [
            "[Your Project and Solution] Solution",
            "[Your Project and Solution] Impact",
            "[Your Project and Solution] Capabilities & Feasibility",
            "[Milestones] Project Milestones",
            "[Final Pitch] Budget & Costs",
            "[Final Pitch] Value for Money",
            "[Proposal Summary] Time",
            "[Proposal Summary] Project Open Source"
        ]

        # まず「sc-170e960f-0 iwcLVh」クラスのブロックを取得
        
        block = chrome_driver.find_element(By.CSS_SELECTOR, "#about > section > div > div.sc-3a69686e-2.cBXzTX > div > div")
        html_inside = block.get_attribute("innerHTML")
        


        # BeautifulSoupでパース
        soup = BeautifulSoup(html_inside, "html.parser")

        # 出力用の辞書 {見出し: [HTMLリスト]}
        sections = {}

        # H3タグを順番に走査
        for h3 in soup.find_all("h3"):
            title = h3.get_text(strip=True)

            if title in targets:
                collected = []

                # H3の次の兄弟要素をたどる
                for sibling in h3.find_next_siblings():
                    if sibling.name == "h3":  # 次のH3が来たら終了
                        break
                    collected.append(str(sibling))  # HTMLそのまま追加

                # 特定の見出しは2つ目だけ、それ以外は全部
                if title in ["[Proposal Summary] Time", "[Proposal Summary] Project Open Source"]:
                    soup_item = BeautifulSoup(collected[1], "html.parser")
                    sections[title] = [soup_item.get_text(strip=True)]
                else:
                    sections[title] = collected

        # ===== 出力確認 =====
        # for heading, items in sections.items():
        #     print("====", heading, "====")
        #     for html in items:
        #         print(html)


        id = row["id"]
        ideascale_id = row["ideascale_id"]

        title = row["title"]
        title_ja = translate(gpt_assistant_headline,title)

        headline_problem = chrome_driver.find_element(By.CSS_SELECTOR, "#stats > section:nth-child(2) > div > div:nth-child(1) > div").text
        headline_problem_ja = translate(gpt_assistant_headline, headline_problem)

        applicant_name = chrome_driver.find_element(By.CSS_SELECTOR, "#team > div.sc-7aeda4c0-16.fJvyoX > a > div > span").text

        project_duration = sections["[Proposal Summary] Time"][0]
        
        headline_solution = chrome_driver.find_element(By.CSS_SELECTOR, "#stats > section:nth-child(2) > div > div:nth-child(2) > div").text
        headline_solution_ja = translate(gpt_assistant_detail, headline_solution)

        open_source = sections["[Proposal Summary] Project Open Source"][0]
        # #tag = custom_fields[4]

        get_solution = sections["[Your Project and Solution] Solution"]
        solution = "\n".join(get_solution)
        solution_ja = translate(gpt_assistant_detail,solution)

        get_impact = sections["[Your Project and Solution] Impact"]
        impact = "\n".join(get_impact)
        impact_ja = translate(gpt_assistant_detail, impact)

        get_capability_feasibility = sections["[Your Project and Solution] Capabilities & Feasibility"]
        capability_feasibility = "\n".join(get_capability_feasibility)
        capability_feasibility_ja = translate(gpt_assistant_detail, capability_feasibility)

        get_project_milestones = sections["[Milestones] Project Milestones"]
        project_milestones = "\n".join(get_project_milestones)
        project_milestones_ja = translate(gpt_assistant_detail,project_milestones)

        get_budget_costs = sections["[Final Pitch] Budget & Costs"]
        budget_costs = "\n".join(get_budget_costs)
        budget_costs_ja = translate(gpt_assistant_detail, budget_costs)

        get_value_for_money = sections["[Final Pitch] Value for Money"]
        value_for_money = "\n".join(get_value_for_money)
        value_for_money_ja = translate(gpt_assistant_detail, value_for_money)

        
        # #SQLインサート
        # api_data.append([id, ideascale_id, title, headline_problem, applicant_name, project_duration, headline_solution, open_source, tag, solution, impact, capability_feasibility, project_milestones, resources, budget_costs, value_for_money])
        # insert_query = "INSERT INTO proposal_detail(id, ideascale_id, title, headline_problem, applicant_name, project_duration, headline_solution, open_source, tag, solution, impact, capability_feasibility, project_milestones, resources, budget_costs, value_for_money) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"



        #データベースに一括挿入
        api_data.append((id, ideascale_id, title, title_ja, headline_problem, headline_problem_ja, applicant_name, project_duration, headline_solution, headline_solution_ja, open_source, solution, solution_ja, impact, impact_ja, capability_feasibility, capability_feasibility_ja, project_milestones, project_milestones_ja, budget_costs, budget_costs_ja, value_for_money, value_for_money_ja))
        insert_query = "INSERT INTO proposal_detail(id, ideascale_id, title, title_ja, headline_problem, headline_problem_ja, applicant_name, project_duration, headline_solution, headline_solution_ja, open_source, solution, solution_ja, impact, impact_ja, capability_feasibility, capability_feasibility_ja, project_milestones, project_milestones_ja, budget_costs, budget_costs_ja, value_for_money, value_for_money_ja) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.executemany(insert_query, api_data)

        api_data2.append((title_ja, headline_problem, headline_problem_ja, headline_solution, headline_solution_ja, id))
        insert_query2 = "UPDATE proposals SET title_ja = %s, problem = %s, problem_ja = %s, solution = %s, solution_ja = %s WHERE id = %s"
        cursor.executemany(insert_query2, api_data2)

        conn.commit()

    except Exception as e:
        print(f"⚠️ Proposal {id} エラー: {e}")
        error_ids.append(id)  # エラーIDを控える
        conn.rollback()  # DBエラー時はロールバック


chrome_driver.quit()
cursor.close()
conn.close()
# cursor.executemany(insert_query, api_data)
#print(title)
#print(link)
# conn.commit()
# cursor.close()
# conn.close()
#conn.cursor().execute("DELETE FROM PROPOSALS WHERE id = 12600")

# エラーIDをファイルに保存
if error_ids:
    with open("error_ids.txt", "w", encoding="utf-8") as f:
        for eid in error_ids:
            f.write(str(eid) + "\n")

    print("❌ エラーになったIDを error_ids.txt に保存しました")
else:
    print("🎉 エラーはありませんでした")
