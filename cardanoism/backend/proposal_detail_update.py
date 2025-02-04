#import deepl
import requests
import json
import re
import fnmatch

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from time import sleep


from db_connect import dbConnect
from chatgpt_api import chatgpt_api
from scraping import login_ideascale


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

fundId=146
per_page=25

url = "https://www.lidonation.com/api/catalyst-explorer/proposals"
meta_params = {'fund_id':fundId,'per_page':per_page,'page':'1'}
headers = {'X-CSRF-TOKEN': 'e3kqXYQ53ALXrumrDWouoN2ouWRWoLEIeIkau9jH'}

meta_response = requests.get(url, params=meta_params, headers=headers)

if meta_response.status_code == 200:
    data = json.loads(meta_response.text)
    print(len(data['data']))
    print(data['meta']['last_page'])
    print(data['data'][0]['title'])
    print(data['meta']['current_page'])
    # データを加工するなどの処理を行う
else:
    print("Error: ", meta_response.status_code)

i = 1
api_data = []
total_page = data['meta']['last_page']
total_page = 1
# 正規表現パターン画像リンク削除
pattern = r'!\[.*?\]\(.*?\)'
#chatGPT翻訳
gpt_assistant_headline="You are half American, half Japanese.You were born and raised in New York, USA for 20 years, and are bilingual in English and Japanese.You have been living in Japan for 10 years now, working as a programmer and Japanese-English translator. You are also familiar with the Cardano blockchain.You will now be translated into Japanese from the English you typed in.No supplementary or explanations are required for the translation results, just translate the characters you typed in and respond.Please translate in a headline tone.Please use カルダノ consistently for the word cardano."
gpt_assistant_detail="You are half American, half Japanese.You were born and raised in New York, USA for 20 years, and are bilingual in English and Japanese.You have been living in Japan for 10 years now, working as a programmer and Japanese-English translator. You are also familiar with the Cardano blockchain.You will now be translated into Japanese from the English you typed in.No supplementary or explanations are required for the translation results, just translate the characters you typed in and respond.Please use カルダノ consistently for the word cardano.If HTML tags are included, please output them as they are."
#APIページ処理
for i in range(i,total_page+1):
    print(i)
    data_params = {'fund_id':fundId,'per_page':per_page,'page':i}
    data_response = requests.get(url, params=data_params, headers=headers)
    api_data = []
    
    #1ページごとのデータ取得
    if data_response.status_code == 200:
        perPageData = json.loads(data_response.text)
        len_proposal = len(perPageData['data'])
        len_proposal = 1
        for x in range(len_proposal):
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

            #スクレイピングSTART
            id = perPageData['data'][x]['id']
            ideascale_id = perPageData['data'][x]['ideascale_id']

            #提案個別ページ
            chrome_driver.get(f"https://cardano.ideascale.com/c/idea/{ideascale_id}")
            sleep(5)
            
            #プロフィールモーダルウィンドウ有無
            profile_modal_window = chrome_driver.find_elements(By.CSS_SELECTOR, "#edit-profile-questions-form > div:nth-child(1) > div.ideascale-custom-checkbox.checkbox-field > label > span.check-mark")
            if len(profile_modal_window) > 0:
                #ファンド規則クリック
                fundRules_checkbox_selector = "#edit-profile-questions-form > div:nth-child(1) > div.ideascale-custom-checkbox.checkbox-field > label > span.check-mark"
                fundRules_checkbox_element = chrome_driver.find_element(By.CSS_SELECTOR, value=fundRules_checkbox_selector)
                fundRules_checkbox_element.click()
                
                #利用規約クリック
                term_checkbox_selector = "#edit-profile-questions-form > div:nth-child(2) > div.ideascale-custom-checkbox.checkbox-field > label > span.check-mark"
                term_checkbox_element = chrome_driver.find_element(By.CSS_SELECTOR, value=term_checkbox_selector)
                term_checkbox_element.click()

                #プライバシーポリシークリック
                privacy_checkbox_selector = "#edit-profile-questions-form > div:nth-child(2) > div.ideascale-custom-checkbox.checkbox-field > label > span.check-mark"
                privacy_checkbox_element = chrome_driver.find_element(By.CSS_SELECTOR, value=privacy_checkbox_selector)
                privacy_checkbox_element.click()
                
                #プライバシーポリシークリック
                modal_button_selector = "#edit-profile-questions-form > div.d-flex.flex-row.justify-content-end > button"
                modal_button_element = chrome_driver.find_element(By.CSS_SELECTOR, value=modal_button_selector)
                modal_button_element.click()
                
            sleep(5)
            wait = WebDriverWait(chrome_driver, 60)
            result = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'custom-field-section-content')))
            title = chrome_driver.find_element(By.CSS_SELECTOR, "#main-content > div > article > header > h2")
            headline_problem = chrome_driver.find_element(By.CSS_SELECTOR, f"#idea-{ideascale_id}-attachments-container > div")
            print(f"{x} {id} {ideascale_id} {title_ja}")
            print(title.text)
            print(headline_problem.text)
            proposal_contexts = chrome_driver.find_elements(By.CLASS_NAME, 'custom-field-section-content')
            detail_fetch = len(proposal_contexts)
            indices = ["[GENERAL] NAME AND SURNAME",
                        "[GENERAL] PLEASE SPECIFY",
                        "[GENERAL] SUMMARI",
                        "[GENERAL] WILL YOUR",
                        "[METADATA]",
                        "[SOLUTION]",
                        "[IMPACT]",
                        "[CAPABILITY & FEASIBILITY]",
                        "[PROJECT MILESTONES]",
                        "[RESOURCES]",
                        "[BUDGET & COSTS]",
                        "[VALUE FOR MONEY]",
                        ]
                    
            
            for context in proposal_contexts:
                field_title=context.find_element(By.TAG_NAME, 'h2').text.upper()
                for index, i in enumerate(indices):
                    if field_title.startswith(i):
                        if index < 5:
                            #print(i)
                            print(context.find_element(By.TAG_NAME, 'h2').text)
                            print(context.find_element(By.CSS_SELECTOR, 'dd.custom-fields').text)
                            custom_fields.append(context.find_element(By.CSS_SELECTOR, 'dd.custom-fields').text)
                        else:
                            print(context.find_element(By.TAG_NAME, 'h2').text)
                            print(context.find_element(By.CSS_SELECTOR, '[id^="custom-field-section-"]').get_attribute('innerHTML'))
                            custom_fields.append(context.find_element(By.CSS_SELECTOR, '[id^="custom-field-section-"]').get_attribute('innerHTML'))
                            # print(context.find_element(By.CSS_SELECTOR, '[id^="custom-field-section-"]').text)
                            # custom_fields.append(context.find_element(By.CSS_SELECTOR, '[id^="custom-field-section-"]').text)
                    else:
                        continue
                            
            print(len(custom_fields))
            print("----------")


            sleep(5)

            #スクレイピングEND
            
            
            
            # pre_title = perPageData['data'][x]['title']
            # pre_problem = perPageData['data'][x]['problem']
            # pre_problem = re.sub(pattern, "", pre_problem.replace('\n', ''))
            # pre_solution = perPageData['data'][x]['solution']
            # pre_solution = re.sub(pattern, "", pre_solution.replace('\n', ''))
            
            # #画像リンク置換
            re_before='src="/a/attachments/embedded'
            re_after='src="https://cardano.ideascale.com/a/attachments/embedded'
            pre_solution = custom_fields[5].replace(re_before, re_after)
            pre_impact = custom_fields[6].replace(re_before, re_after)
            pre_capability_feasibility = custom_fields[7].replace(re_before, re_after)
            pre_milestones = custom_fields[8].replace(re_before, re_after)
            pre_resources = custom_fields[9].replace(re_before, re_after)
            pre_budget_costs = custom_fields[10].replace(re_before, re_after)
            pre_value_for_money = custom_fields[11].replace(re_before, re_after)
            
            id = id
            ideascale_id = ideascale_id
            title = title.text
            #title_ja = translate(gpt_assistant_headline, title)
            headline_problem = headline_problem.text
            #headline_problem_ja = translate(gpt_assistant_detail, headline_problem)
            applicant_name = custom_fields[0]
            project_duration = custom_fields[1]
            headline_solution = custom_fields[2]
            #headline_solution_ja = translate(gpt_assistant_detail, custom_fields[2])
            open_source = custom_fields[3]
            tag = custom_fields[4]
            solution = pre_solution
            #solution_ja = translate(gpt_assistant_detail, pre_solution)
            impact = pre_impact
            #impact_ja = translate(gpt_assistant_detail, pre_impact)
            capability_feasibility = pre_capability_feasibility
            #capability_feasibility_ja = translate(gpt_assistant_detail, pre_capability_feasibility)
            project_milestones = pre_milestones
            #project_milestones_ja = translate(gpt_assistant_detail, pre_milestones)
            resources = pre_resources
            #resources_ja = translate(gpt_assistant_detail, pre_resources)
            budget_costs = pre_budget_costs
            #budget_costs_ja = translate(gpt_assistant_detail, pre_budget_costs)
            value_for_money = pre_value_for_money
            #value_for_money_ja = translate(gpt_assistant_detail, pre_value_for_money)

            
            #problem_ja = translate()
            #solution_ja = translate(solution.get_attribute('innerHTML'))
            
            
            
            #SQLインサート

            #api_data.append([id, ideascale_id, title, title_ja, headline_problem, headline_problem_ja, applicant_name, project_duration, headline_solution, headline_solution_ja, open_source, tag, solution, solution_ja, impact, impact_ja, capability_feasibility, capability_feasibility_ja, project_milestones, project_milestones_ja, resources, resources_ja, budget_costs, budget_costs_ja, value_for_money, value_for_money_ja])
            api_data.append([id, ideascale_id, title, headline_problem, applicant_name, project_duration, headline_solution, open_source, tag, solution, impact, capability_feasibility, project_milestones, resources, budget_costs, value_for_money])
  
            insert_query = "INSERT INTO proposal_detail(id, ideascale_id, title, headline_problem, applicant_name, project_duration, headline_solution, open_source, tag, solution, impact, capability_feasibility, project_milestones, resources, budget_costs, value_for_money) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            cursor.executemany(insert_query, api_data)
            conn.commit()

    else:
        print("Error: ", data_response.status_code)

    #データベースに一括挿入
    #insert_query = "INSERT INTO PROPOSAL_DETAIL(id, ideascale_id, title, title_ja, headline_problem, headline_problem_ja, applicant_name, project_duration, headline_solution, headline_solution_ja, open_source, tag, solution, solution_ja, impact, impact_ja, capability_feasibility, capability_feasibility_ja, project_milestones, project_milestones_ja, resources, resources_ja, budget_costs, budget_costs_ja, value_for_money, value_for_money_ja) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    
    # chrome_driver.quit()


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


