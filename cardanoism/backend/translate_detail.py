from db_connect import dbConnect
from chatgpt_api import chatgpt_api
from bs4 import BeautifulSoup

#chatGPT翻訳
gpt_assistant_detail="You are half American, half Japanese.You were born and raised in New York, USA for 20 years, and are bilingual in English and Japanese.You have been living in Japan for 10 years now, working as a programmer and Japanese-English translator. You are also familiar with the Cardano blockchain.You will now be translated into Japanese from the English you typed in.No supplementary or explanations are required for the translation results, just translate the characters you typed in and respond.Please use カルダノ consistently for the word cardano.If HTML tags are included, please output them as they are."


def extract_and_translate_tags(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    dl_elements = soup.find_all('dl')
    translated_html = ''

    for dl in dl_elements:
        for element in dl.children:
            if element.name in ['dt', 'dd']:
                original_text = str(element)
                translated_text = translate(gpt_assistant_detail, original_text)
                translated_html += translated_text

    return translated_html


def translate(gpt_assistant, pre_word):
    if pre_word:
        word_ja = chatgpt_api(gpt_assistant,pre_word)
        print(word_ja)
    else:
        word_ja = pre_word
    return word_ja

def create_dl_tag(row):
    return f"<dl>{row}</dl>"

dbCon = dbConnect()
cursor = dbCon[0]
conn = dbCon[1]
print(cursor)
print(conn)


proposals: list[dict[str, str]] = []
id = 13363

data_query =f"""
SELECT id,
solution,
impact,
capability_feasibility,
project_milestones,
resources,
budget_costs,
value_for_money
FROM proposal_detail WHERE id >= {id} ORDER BY id ASC LIMIT 10;"""

print(data_query)
cursor.execute(data_query)
proposals = cursor.fetchall()

# 取得したデータを一つずつ取り出す
for row in proposals:
    # 各列の値を変数に代入
    id = row["id"]
    solution = create_dl_tag(row["solution"])
    impact = create_dl_tag(row["impact"])
    capability_feasibility = create_dl_tag(row["capability_feasibility"])
    project_milestones = create_dl_tag(row["project_milestones"])
    resources = create_dl_tag(row["resources"])
    budget_costs = create_dl_tag(row["budget_costs"])
    value_for_money = create_dl_tag(row["value_for_money"])


    solution_ja = extract_and_translate_tags(solution)
    impact_ja = extract_and_translate_tags(impact)
    capability_feasibility_ja = extract_and_translate_tags(capability_feasibility)
    project_milestones_ja = extract_and_translate_tags(project_milestones)
    resources_ja = extract_and_translate_tags(resources)
    budget_costs_ja = extract_and_translate_tags(budget_costs)
    value_for_money_ja = extract_and_translate_tags(value_for_money)
    print(id,"翻訳完了")
    


    columns_values = {
    'solution_ja': solution_ja,
    'impact_ja': impact_ja,
    'capability_feasibility_ja': capability_feasibility_ja,
    'project_milestones_ja': project_milestones_ja,
    'resources_ja': resources_ja,
    'budget_costs_ja': budget_costs_ja,
    'value_for_money_ja': value_for_money_ja
    }
    
    # カラムと値のリストを準備
    columns = ', '.join([f"{col} = %s" for col in columns_values.keys()])
    values = list(columns_values.values())
    values.append(str(id))
    
    # SQLクエリを準備
    sql_query = f"""
    UPDATE proposal_detail
    SET {columns}
    WHERE id = %s;
    """
    
    # クエリを実行
    cursor.execute(sql_query, values)
    
    # 変更をコミット
    conn.commit()
    print(id,"DB挿入完了")


#DBクローズ
cursor.close()
conn.close()