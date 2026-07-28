import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
#---获取对应的API Key---
BoCha_Api = os.getenv("BoCha_API")
DeepSeek_Api = os.getenv("DeepSeek_API")
#---获取对应的URL---
BoCha_Url = "https://api.bochaai.com/v1/web-search"
DeepSeek_Url = "https://api.deepseek.com"
#---获取对应的模型---
DeepSeek_Model = "deepseek-chat"
BoCha_Search_Count = 5
#---LLM 供应商配置字典---
LLM_Config={
    "deepseek":{
        "api_key":DeepSeek_Api,
        "url":DeepSeek_Url,
        "model":DeepSeek_Model
    },
}