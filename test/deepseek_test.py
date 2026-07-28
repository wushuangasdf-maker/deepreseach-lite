from openai import OpenAI
import os
from dotenv import load_dotenv,find_dotenv
load_dotenv(find_dotenv())
api_key=os.getenv("DeepSeek_API")
client=OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)
response=client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "user", "content": "请计算1+1的结果"}
        ],
)
print(response.choices[0].message.content)