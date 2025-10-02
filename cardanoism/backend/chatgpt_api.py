import os
import openai
from openai import OpenAI

# OpenAI APIキー
client = OpenAI(
    # This is the default and can be omitted
   api_key = os.getenv('GPT_API_KEY')
)

def chatgpt_api(assistant, word):
# リクエストの設定
    response = client.chat.completions.create(
    model="gpt-4.1-nano",  # 使用するモデル
    messages=[
            {"role": "system", "content": assistant},
            {"role": "user", "content": word},
        ]
    )
    #print(response.choices[0].message.content)
    return response.choices[0].message.content
    

#chatgpt_api()