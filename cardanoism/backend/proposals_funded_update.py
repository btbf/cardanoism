#import deepl
import requests
import json
import time

from db_connect import dbConnect

#DB接続
dbCon = dbConnect()
cursor = dbCon[0]
conn = dbCon[1]
print(cursor)
print(conn)

# SQLクエリ：fund_id でグループ化し、各グループの件数を取得
get_fundId_quey = "SELECT fund_id, COUNT(*) AS count FROM proposals GROUP BY fund_id"
cursor.execute(get_fundId_quey)

# クエリ結果を取得してループ処理
results = cursor.fetchall()
for row in results:
    fund_id = row['fund_id']
    count = row['count']
    print(f"Fund ID: {fund_id} - 件数: {count}")
    
    # 各 fund_id ごとに必要な処理

    per_page=25

    url = "https://www.lidonation.com/api/catalyst-explorer/proposals"
    meta_params = {'fund_id':fund_id,'per_page':per_page,'page':'1'}
    headers = {'X-CSRF-TOKEN': 'DZb2ZgIcYTlsIaoCInN5mfdPqAbgYgv9UVyN2TFE'}

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
        data_params = {'fund_id':fund_id,'per_page':per_page,'page':i}
        data_response = requests.get(url, params=data_params, headers=headers)
        #api_data = []
        
        #1ページごとのデータ取得
        if data_response.status_code == 200:
            perPageData = json.loads(data_response.text)
            len_proposal = len(perPageData['data'])
            for x in range(len_proposal):
                #変数初期化
                amount_received = ""
                project_status = ""
                funding_status = ""
                yes_votes_count = ""
                no_votes_count = ""
                abstain_votes_count = ""
                unique_wallets = ""
                api_data = []
                

                id = perPageData['data'][x]['id']
                title = perPageData['data'][x]['title']
                
                amount_received = perPageData['data'][x]['amount_received']
                project_status = perPageData['data'][x]['project_status']
                funding_status = perPageData['data'][x]['funding_status']
                yes_votes_count = perPageData['data'][x]['yes_votes_count']
                no_votes_count = perPageData['data'][x]['no_votes_count']
                abstain_votes_count = perPageData['data'][x]['abstain_votes_count']
                unique_wallets = perPageData['data'][x]['unique_wallets']
                
                print(f"{x} {id} {title}")
                print(project_status,funding_status)
                print("")
                api_data = [amount_received, project_status, funding_status, yes_votes_count, no_votes_count, abstain_votes_count, unique_wallets, id]
            
            #データベースに一括挿入
                update_query = "UPDATE proposals SET amount_received = %s, project_status = %s, funding_status = %s, yes_votes_count = %s, no_votes_count = %s, abstain_votes_count = %s, unique_wallets = %s WHERE id = %s"
                cursor.execute(update_query, api_data)
                conn.commit()
            
        else:
            print("Error: ", data_response.status_code)


time.sleep(5)

cursor.close()
conn.close()
        
#conn.cursor().execute("DELETE FROM PROPOSALS WHERE id = 12600")


