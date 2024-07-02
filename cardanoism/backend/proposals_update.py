#import deepl
import requests
import json
import re
import time
import deepl

from db_connect import dbConnect
from chatgpt_api import chatgpt_api


dbCon = dbConnect()
cursor = dbCon[0]
conn = dbCon[1]
print(cursor)
print(conn)

fundId=139
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

#deeple
def translate(text):
    #text = "F11: Cardano Open: Ecosystem - non-technical"
    translator = deepl.Translator("6efcae24-97b6-4dbe-ada8-ec9508ffe329:fx")
    result = translator.translate_text(text, target_lang="JA")
    return result.text

#i = 1
api_data = []
total_page = data['meta']['last_page']
#total_page = 1
# 正規表現パターン画像リンク削除
pattern = r'!\[.*?\]\(.*?\)'
#chatGPT翻訳
gpt_assistant_headline="You are half American, half Japanese.You were born and raised in New York, USA for 20 years, and are bilingual in English and Japanese.You have been living in Japan for 10 years now, working as a programmer and Japanese-English translator.No greetings necessary. You are also familiar with the Cardano blockchain.You will now be translated into Japanese from the English you typed in.No supplementary or explanations are required for the translation results, just translate the characters you typed in and respond.Please translate in a headline tone.Please use カルダノ consistently for the word cardano."
gpt_assistant_detail="You are half American, half Japanese.You were born and raised in New York, USA for 20 years, and are bilingual in English and Japanese.You have been living in Japan for 10 years now, working as a programmer and Japanese-English translator. No greetings necessary. You are also familiar with the Cardano blockchain.You will now be translated into Japanese from the English you typed in.No supplementary or explanations are required for the translation results, just translate the characters you typed in and respond.Please use カルダノ consistently for the word cardano."

#APIページ処理
for i in range(1,total_page+1):
    print(i)
    data_params = {'fund_id':fundId,'per_page':per_page,'page':i}
    data_response = requests.get(url, params=data_params, headers=headers)
    #api_data = []
    
    #1ページごとのデータ取得
    if data_response.status_code == 200:
        perPageData = json.loads(data_response.text)
        len_proposal = len(perPageData['data'])
        for x in range(len_proposal):
            #変数初期化
            id = ""
            user_id = ""
            fund_id = ""
            challenge_id = ""
            title = ""
            ideascale_link = ""
            ideascale_user = ""
            ideascale_id = ""
            amount_requested = ""
            project_status = ""
            funding_status = "" 
            problem = ""
            solution = ""
            currency_symbol = ""
            currency = ""
            alignment_score = ""
            feasibility_score = ""
            auditability_score = ""
            pre_title = ""
            pre_problem = ""
            pre_solution = ""
            title_ja = ""
            problem_ja = ""
            solution_ja = ""
            word = ""
            api_data = []
            
            pre_title = perPageData['data'][x]['title']
            pre_problem = perPageData['data'][x]['problem']
            pre_solution = perPageData['data'][x]['solution']
            
            word = pre_title
            title_ja = chatgpt_api(gpt_assistant_headline,word)
            #title_ja = translate(pre_title)
            
            if pre_problem:
                #problem = translate(pre_problem.replace('\n', ''))
                problem = re.sub(pattern, "", pre_problem.replace('\n', ''))
                word = problem
                problem_ja = chatgpt_api(gpt_assistant_detail,word)
                #problem_ja = translate(word)
            else:
                problem = pre_problem
            
            if pre_solution:
                solution = re.sub(pattern, "", pre_solution.replace('\n', ''))
                word = solution
                solution_ja = chatgpt_api(gpt_assistant_detail,word)
                #solution_ja = translate(word)
            else:
                solution = pre_solution

            
            id = perPageData['data'][x]['id']
            user_id = perPageData['data'][x]['user_id']
            fund_id = perPageData['data'][x]['fund_id']
            challenge_id = perPageData['data'][x]['challenge_id']
            title = perPageData['data'][x]['title']
            ideascale_link = perPageData['data'][x]['ideascale_link']
            ideascale_user = perPageData['data'][x]['ideascale_user']
            ideascale_id = perPageData['data'][x]['ideascale_id']
            amount_requested = perPageData['data'][x]['amount_requested']
            project_status = perPageData['data'][x]['project_status']
            funding_status = perPageData['data'][x]['funding_status']     
            problem = perPageData['data'][x]['problem']
            solution = perPageData['data'][x]['solution']
            currency_symbol = perPageData['data'][x]['currency_symbol']
            currency = perPageData['data'][x]['currency']
            alignment_score = perPageData['data'][x]['alignment_score']
            feasibility_score = perPageData['data'][x]['feasibility_score']
            auditability_score = perPageData['data'][x]['auditability_score']

            #print(type(perPageData['data'][x]['alignment_score']))
            #avg_score = round((alignment_score + feasibility_score + auditability_score)/3, 1)
            # link = perPageData['data'][x]['link']
            #SQLインサート
            
            print(f"{x} {id} {title_ja}")
            print(problem_ja)
            print(solution_ja)
            print("")
            api_data.append([id, user_id, fund_id, challenge_id, title, title_ja, ideascale_link, ideascale_user, ideascale_id, amount_requested, project_status, funding_status, problem, problem_ja, solution, solution_ja, currency_symbol, currency, alignment_score, feasibility_score, auditability_score])
        
        #データベースに一括挿入
            insert_query = "INSERT INTO proposals(id, user_id, fund_id, challenge_id, title, title_ja, ideascale_link, ideascale_user, ideascale_id, amount_requested, project_status, funding_status, problem, problem_ja, solution, solution_ja, currency_symbol, currency, alignment_score, feasibility_score, auditability_score) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            cursor.executemany(insert_query, api_data)
            conn.commit()
        
    else:
        print("Error: ", data_response.status_code)


time.sleep(30)

cursor.close()
conn.close()
        
#conn.cursor().execute("DELETE FROM PROPOSALS WHERE id = 12600")


