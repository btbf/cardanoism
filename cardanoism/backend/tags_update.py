import requests
import json

import deepl
from cardanoism.backend.db_connect import dbConnect


dbCon = dbConnect()
cursor = dbCon[0]
conn = dbCon[1]
print(cursor)
print(conn)

url = "https://www.lidonation.com/api/catalyst-explorer/tags"
meta_params = {'page':'2'}
headers = {'X-CSRF-TOKEN': 'AjGbJ4A63nZnRgtY3uh1zOzgRdwcCkkx8USlWH6R'}

meta_response = requests.get(url, params=meta_params, headers=headers)
#print(meta_response.status_code)

####Deepleコード
def translate(text):
    #text = "F11: Cardano Open: Ecosystem - non-technical"
    translator = deepl.Translator("6efcae24-97b6-4dbe-ada8-ec9508ffe329:fx")
    result = translator.translate_text(text, target_lang="JA")
    return result.text

#lidonation API challengeデータ取得
if meta_response.status_code == 200:
    perPageData = json.loads(meta_response.text)
    len_proposal = len(perPageData['data'])
    print(len_proposal)
    api_data = []
    for x in range(len_proposal):
        id = perPageData['data'][x]['id']
        title = perPageData['data'][x]['title']
        title_ja = translate(title.replace('\n', ''))
        #content = perPageData['data'][x]['content']
        print(title_ja)
        api_data.append([id, title, title_ja])
        
    #データベースに一括挿入
    insert_query = "INSERT INTO tags (id, title, title_ja) VALUES (?, ?, ?)"
    cursor.executemany(insert_query, api_data)
    
    conn.commit()
    cursor.close()
    conn.close()

else:
    print("Error: ", meta_response.status_code)
        

