import requests
import json
import sys

from db_connect import dbConnect
from chatgpt_api import chatgpt_api

dbCon = dbConnect()
cursor = dbCon[0]
conn = dbCon[1]
print(cursor)
print(conn)


url = "https://www.lidonation.com/api/catalyst-explorer/challenges"
meta_params = {'fund_id': '146'}
headers = {'X-CSRF-TOKEN': 'yCI49F04Ok1vtXXOV1DLUbttlpLLpJvEBN303A3E'}

meta_response = requests.get(url, params=meta_params, headers=headers)


#lidonation API challengeデータ取得
if meta_response.status_code == 200:
    perPageData = json.loads(meta_response.text)
    len_proposal = len(perPageData['data'])
    api_data = []
    for x in range(len_proposal):
        id = perPageData['data'][x]['id']
        fundId = perPageData['data'][x]['fundId']
        title = perPageData['data'][x]['title']
        proposalsCount = perPageData['data'][x]['proposalsCount']
        amount = perPageData['data'][x]['amount']
        currency = perPageData['data'][x]['currency']
        #print(pre_id)
        
        #chatGPT翻訳
        gpt_assistant="You are half American, half Japanese.You were born and raised in New York, USA for 20 years, and are bilingual in English and Japanese.You have been living in Japan for 10 years now, working as a programmer and Japanese-English translator.No greetings necessary. You are also familiar with the Cardano blockchain.You will now be translated into Japanese from the English you typed in.No supplementary or explanations are required for the translation results, just translate the characters you typed in and respond.Please translate in a headline tone.Please use カルダノ consistently for the word cardano."
        word = title
        title_ja = chatgpt_api(gpt_assistant,word)
        print(id)
        print(title)
        print(title_ja)
        print("")
        api_data.append([id, fundId, title, title_ja, proposalsCount, amount, currency])
        
    # データベースに一括挿入
    insert_query = "INSERT INTO challenges (id, fund_id, title, title_ja, proposals_count, amount, currency) VALUES (?, ?, ?, ?, ?, ?, ?)"
    cursor.executemany(insert_query, api_data)
    
    conn.commit()
    cursor.close()
    conn.close()

#         title = translate(pre_title.replace('\n', ''))
#         #title = pre_title
#         if not pre_problem:
#             problem = pre_problem
#         else:
#             #problem = translate(pre_problem.replace('\n', ''))
#             problem = re.sub("\\!\\[[^\\!\\[]+\\/+(jpeg|jpg|JPG|JPEG|png|PNG|gif|GIF)\\)|<[^>]+>", "", pre_problem.replace('\n', ''))
#             translate_problem = translate(problem)
        
#         if not pre_solution:
#             solution = pre_solution
#         else:
#             #solution = translate(pre_solution.replace('\n', ''))
#             solution = re.sub("\\!\\[[^\\!\\[]+\\/+(jpeg|jpg|JPG|JPEG|png|PNG)\\)|<[^>]+>", "", pre_solution.replace('\n', ''))
#             translate_solution = translate(solution)
        
        
#         id = perPageData['data'][x]['id']
#         fund_id = perPageData['data'][x]['fund_id']
#         challenge_id = perPageData['data'][x]['challenge_id']
#         ideascale_link = perPageData['data'][x]['ideascale_link']
#         ideascale_user = perPageData['data'][x]['ideascale_user']
#         amount_requested = perPageData['data'][x]['amount_requested']
#         alignment_score = float(perPageData['data'][x]['alignment_score'])
#         feasibility_score = float(perPageData['data'][x]['feasibility_score'])
#         auditability_score = float(perPageData['data'][x]['auditability_score'])
#         #print(type(perPageData['data'][x]['alignment_score']))
#         avg_score = round((alignment_score + feasibility_score + auditability_score)/3, 1)
#         link = perPageData['data'][x]['link']
#         #SQLインサート
#         conn.cursor().execute("INSERT INTO PROPOSALS(id, fund_id, challenge_id, title, ideascale_link, user_name, amount_requested, problem, solution, alignment_score, feasibility_score, auditability_score, avg_score, link) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", (id, fund_id, challenge_id, title, ideascale_link, ideascale_user, amount_requested, translate_problem, translate_solution, alignment_score, feasibility_score, auditability_score, avg_score, link))
#         print(title)
        
#         # f = codecs.open('write_test3.txt', 'a',"utf-8")
#         # f.write(title + "\n")
#         # f.close()
else:
    print("Error: ", meta_response.status_code)
        
#conn.cursor().execute("DELETE FROM PROPOSALS WHERE id = 12600")
