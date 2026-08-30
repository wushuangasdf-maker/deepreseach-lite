import logging
import requests
from core.config import Baidu_Api, Baidu_Url, Baidu_Search_Count

logger = logging.getLogger(__name__)


def baidu_search(query: str, count: int = Baidu_Search_Count) -> list[dict]:
    """
    使用百度智能云千帆「百度搜索」API 进行网页搜索。

    参数:
        query (str): 搜索查询字符串。
        count (int): 返回的搜索结果数量，默认为 Baidu_Search_Count。

    返回:
        list[dict]: 搜索结果列表，每项含 title/url/snippet 字段，
                    与 bocha_search 返回结构一致，便于上层统一处理。

    注意:
        本函数绝不抛出异常 —— 所有错误都会被捕获并转为空列表返回，
        供 search_with_fallback 降级使用。
    """
    # ── 网络请求层：捕获 requests 各类异常，失败返回空列表 ──
    try:
        response = requests.post(
            Baidu_Url,
            headers={
                "Authorization": f"Bearer {Baidu_Api}",
                # 部分文档要求用 X-Appbuilder-Authorization 携带 AppBuilder Key，
                # 同时带上以兼容两种鉴权约定。
                "X-Appbuilder-Authorization": f"Bearer {Baidu_Api}",
                "Content-Type": "application/json",
            },
            json={
                "messages": [{"role": "user", "content": query}],
                "search_source": "baidu_search_v2",
                "resource_type_filter": [{"type": "web", "top_k": count}],
            },
            timeout=15,  # 对齐 bocha_search / fetch_page 的超时设计
        )
        response.raise_for_status()  # 非 2xx 抛出 HTTPError
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        hint = f"（HTTP {status}）" if status else ""
        logger.error("百度搜索请求失败（%s）%s。%s", type(e).__name__, hint, e)
        return []

    # ── 响应解析层：JSON 解析失败（如网关返回 HTML 错误页）──
    try:
        data = response.json()
    except ValueError as e:
        logger.error("百度搜索响应解析失败（%s）。%s", type(e).__name__, e)
        return []

    # ── 防御性取值：references 数组可能缺失或为空 ──
    refs = data.get("references", [])
    if not refs:
        logger.warning("百度搜索成功，但未返回任何结果。")
        return []

    results = []
    for ref in refs:
        if not isinstance(ref, dict):  # 跳过异常条目
            continue
        results.append({
            "title": ref.get("title", ""),
            "url": ref.get("url", ""),
            # snippet 与 content 语义一致，snippet 缺失时回退到 content
            "snippet": ref.get("snippet") or ref.get("content", ""),
        })

    return results
