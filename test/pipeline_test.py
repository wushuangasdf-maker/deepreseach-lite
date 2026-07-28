from core.bocha_search import bocha_search, build_context
from core.llm import DeepSeekClient,get_llm_client
query=input("请输入搜索查询：")
count=int(input("请输入搜索结果数量："))
pages=bocha_search(query,count)
context=build_context(pages)

client=get_llm_client(provider="deepseek")
question=input("请输入您的问题：")
result=client.answer(question,context)
print(result)













