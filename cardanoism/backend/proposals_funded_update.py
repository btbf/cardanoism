#import deepl
import requests
import json
import time

from db_connect import dbConnect


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

#i = 1
api_data = []
total_page = data['meta']['last_page']
#total_page = 1

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
            project_status = ""
            funding_status = ""
            yes_votes_count = ""
            no_votes_count = ""
            abstain_votes_count = ""
            unique_wallets = ""
            api_data = []
            

            id = perPageData['data'][x]['id']
            title = perPageData['data'][x]['title']

            project_status = perPageData['data'][x]['project_status']
            funding_status = perPageData['data'][x]['funding_status']
            yes_votes_count = perPageData['data'][x]['yes_votes_count']
            no_votes_count = perPageData['data'][x]['no_votes_count']
            abstain_votes_count = perPageData['data'][x]['abstain_votes_count']
            unique_wallets = perPageData['data'][x]['unique_wallets']
            
            print(f"{x} {id} {title}")
            print(project_status,funding_status)
            print("")
            api_data = [project_status, funding_status, yes_votes_count, no_votes_count, abstain_votes_count, unique_wallets, id]
        
        #データベースに一括挿入
            update_query = "UPDATE proposals SET project_status = %s, funding_status = %s, yes_votes_count = %s, no_votes_count = %s, abstain_votes_count = %s, unique_wallets = %s WHERE id = %s"
            cursor.execute(update_query, api_data)
            conn.commit()
        
    else:
        print("Error: ", data_response.status_code)


time.sleep(5)

cursor.close()
conn.close()
        
#conn.cursor().execute("DELETE FROM PROPOSALS WHERE id = 12600")


