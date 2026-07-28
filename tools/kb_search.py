"""
知识库搜索工具 — kb_search.py

将私有知识库检索（FAISS + bge-small）暴露为 LLM 可调用的工具。

与 web_search_tool 的区别：
  - web_search_tool：搜索互联网公开信息
  - kb_search_tool：  搜索本地私有文档

用法:
    from tools.kb_search import kb_search_tool, get_tool_schema
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.knowledge_base import KnowledgeBase

TOOL_NAME = "kb_search_tool"
TOOL_DESCRIPTION = (
    "搜索私有知识库，获取与查询相关的本地文档内容。"
    "适用场景：查询内部资料、项目规范、历史报告、领域专有知识。"
    "不适用场景：实时新闻、最新公开数据、互联网热点事件。"
    "如果知识库返回空结果或不相关内容，应改用 web_search_tool 搜索互联网。"
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "搜索查询文本。使用文档中可能出现的关键词，"
                "例如「RAG 技术原理」「API 异步任务设计」「产品核心优势」"
            ),
        },
        "top_k": {
            "type": "integer",
            "description": "返回结果数量，默认 5。需要更多上下文时可设为 10。",
            "default": 5,
        },
    },
    "required": ["query"],
}

# 默认索引目录
_DEFAULT_INDEX_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "kb_index",
)

# 延迟初始化单例（避免 API 启动时就加载模型）
_kb: KnowledgeBase | None = None


def _get_kb() -> KnowledgeBase | None:
    """获取 KnowledgeBase 单例。索引不存在时返回 None。"""
    global _kb
    if _kb is None:
        index_dir = os.environ.get("KB_INDEX_DIR", _DEFAULT_INDEX_DIR)
        if os.path.exists(os.path.join(index_dir, "index.faiss")):
            _kb = KnowledgeBase(index_dir)
    return _kb


def kb_search_tool(query: str, top_k: int = 5) -> str:
    """
    在私有知识库中搜索相关文档块。

    参数:
        query: 搜索查询文本
        top_k: 返回结果数，默认 5

    返回:
        str: 格式化的检索结果文本。

    注意:
        本函数绝不抛出异常 —— 所有错误都会被 catch
        并转为自然语言字符串返回，因为 LLM 只能处理文本。
    """
    if not query or not query.strip():
        return "错误：知识库搜索查询不能为空。"

    kb = _get_kb()
    if kb is None:
        return (
            "（知识库未初始化。请先构建索引："
            "python core/knowledge_base.py --build --doc_dir ./my_knowledge）"
        )

    try:
        results = kb.search(query, top_k=top_k)
    except Exception as e:
        error_type = type(e).__name__
        return (
            f"知识库搜索失败（{error_type}）。"
            f"详细信息：{e}。建议改用 web_search_tool 搜索互联网。"
        )

    if not results:
        return (
            f"未在知识库中找到与「{query}」相关的内容。"
            f"建议：1) 换用其他搜索词 2) 使用 web_search_tool 搜索互联网"
        )

    # 格式化输出
    lines = [f"【知识库搜索结果】共找到 {len(results)} 条与「{query}」相关的内容：\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"[{i}] 来源：{r['source']}  (相似度: {r['score']:.2f})\n"
            f"    {r['text'][:500]}"
        )

    return "\n".join(lines)


def get_tool_schema() -> dict:
    """
    返回此工具的 OpenAI Function Calling 格式定义。

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
