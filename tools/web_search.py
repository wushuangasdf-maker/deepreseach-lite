import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.bocha_search import build_context
from core.search import search_with_fallback
TOOL_NAME="web_search_tool"
TOOL_DESCRIPTION=(
    "使用博查 AI 搜索引擎搜索互联网，获取与查询相关的网页信息。"
    "博查无结果时自动降级到百度千帆搜索。"
    "返回每条结果的标题、URL 和内容摘要。"
    "适用场景：需要最新信息、事实核查、查找资料、了解当前事件。"
    "不适用场景：纯数学计算、代码生成、翻译。"
)
TOOL_PARAMETERS={
     "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词，应为简洁、明确的查询短语，例如 '2026年世界杯主办城市'",
        },
        "count": {
            "type": "integer",
            "description": "返回结果数量，默认 5,最大 10",
            "default": 5,
        },
    },
    "required": ["query"],
}

def web_search_tool(query: str, count: int = 5) -> str:
      """                                                             
    执行一次网络搜索，将结果拼接为适合 LLM 阅读的纯文本。

    参数:
        query (str): 搜索关键词
        count (int): 期望返回的结果数，默认 5 条

    返回:
        str: 格式化后的搜索结果文本，或错误提示文本。

    注意:
        本函数绝不抛出异常 —— 所有错误都会被 catch
        并转为自然语言字符串返回，因为 LLM 只能处理文本。
    """
      if not query or not query.strip():
          return "错误：搜索查询不能为空。"
      if count < 1 or count > 10:
           count=10
      try:
           pages:list[dict]=search_with_fallback(query,count)
      except Exception as e:
           error_type=type(e).__name__
           return (                                                      
            f"搜索失败（{error_type}）。可能是网络问题或 API 服务异常。"
            f"详细信息：{e}。建议稍后重试或更换搜索关键词。"
        )
      if not pages:
          return f"未找到与「{query}」相关的搜索结果，请尝试其他关键词。" 
      # ── 新增：来源质量评分 ──
      from core.source_ranker import rank_sources
      pages = rank_sources(pages, query)
      result_text=build_context(pages)
      header = f"【网络搜索结果】共找到 {len(pages)} 条与「{query}」相关的内容：\n\n" 
      return header + result_text

def get_tool_schema() -> dict: 
     """                                                              
    返回此工具的 OpenAI Function Calling 格式定义。
    Agent 调用此函数获取 schema 后，注入到 LLM 请求的 tools 参数中，
    LLM 即可了解此工具的能力并按需生成调用指令。

    返回:
        dict: 符合 OpenAI tools 格式的字典
    """
     return {                                                      
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": TOOL_DESCRIPTION,
            "parameters": TOOL_PARAMETERS,
        },
    }