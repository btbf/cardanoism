import requests
import json

from db_connect import dbConnect


dbCon = dbConnect()
cursor = dbCon[0]
conn = dbCon[1]
print(cursor)
print(conn)

url = "https://www.lidonation.com/api/catalyst-explorer/funds/146"
headers = {'X-CSRF-TOKEN': 'AjGbJ4A63nZnRgtY3uh1zOzgRdwcCkkx8USlWH6R'}

meta_response = requests.get(url, headers=headers)
#print(meta_response.status_code)

#lidonation API challengeデータ取得
if meta_response.status_code == 200:
    perPageData = json.loads(meta_response.text)
    len_proposal = len(perPageData['data'])
    print(len_proposal)
    api_data = []
    # for x in range(len_proposal):
    #     id = perPageData['data'][x]['id']
    #     title = perPageData['data'][x]['title']
    #     proposals_count = perPageData['data'][x]['proposals_count']
    #     amount = perPageData['data'][x]['amount']
    #     currency = perPageData['data'][x]['currency']
    #     launch_date = perPageData['data'][x]['launch_date']
    #     currency_symbol = perPageData['data'][x]['currency_symbol']
    #     slug = perPageData['data'][x]['slug']
    #     #content = perPageData['data'][x]['content']
    id = perPageData['data']['id']
    title = perPageData['data']['title']
    proposals_count = perPageData['data']['proposals_count']
    amount = perPageData['data']['amount']
    currency = perPageData['data']['currency']
    launch_date = perPageData['data']['launch_date']
    currency_symbol = perPageData['data']['currency_symbol']
    slug = perPageData['data']['slug']
    #content = perPageData['data'][x]['content']

    print(launch_date)
    
    api_data.append([id, title, proposals_count, amount, currency, launch_date, currency_symbol, slug])
        
    #データベースに一括挿入
    insert_query = "INSERT INTO funds (id, title, proposals_count, amount, currency, launch_date, currency_symbol, slug) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
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
