import logging
import requests
from core.config import BoCha_Api, BoCha_Url, BoCha_Search_Count

logger = logging.getLogger(__name__)


def _format_search_error(e: Exception) -> str:
    """
    将 requests 异常转为对用户友好的错误提示。

    对齐 fetch_page.py 的 _format_http_error 风格：
    针对不同异常类型给出针对性的排查建议。
    """
    error_type = type(e).__name__

    if isinstance(e, requests.Timeout):
        hint = "请求超时，搜索服务响应过慢或网络不稳定。建议稍后重试。"
    elif isinstance(e, requests.ConnectionError):
        hint = "无法连接搜索服务，可能是网络不通或 DNS 解析失败。"
    elif isinstance(e, requests.HTTPError):
        code = e.response.status_code if e.response is not None else 0
        if code in (401, 403):
            hint = f"搜索 API 鉴权失败（HTTP {code}），请检查 BoCha_API 密钥是否有效。"
        elif code == 429:
            hint = "请求过于频繁（HTTP 429），已触发搜索 API 的速率限制，请稍后重试。"
        elif code >= 500:
            hint = f"搜索服务端故障（HTTP {code}），建议稍后重试。"
        else:
            hint = f"搜索请求未成功（HTTP {code}）。"
    else:
        hint = f"详细信息：{e}。建议检查网络与 API 配置。"

    return f"搜索请求失败（{error_type}）。{hint}"


def bocha_search(query: str, count: int = BoCha_Search_Count) -> list[dict]:
    """
    使用BoCha API进行网页搜索。

    参数:
        query (str): 搜索查询字符串。
        count (int): 返回的搜索结果数量，默认为BoCha_Search_Count。

    返回:
        list[dict]: 搜索结果列表，每项含 title/url/snippet 字段。

    注意:
        本函数绝不抛出异常 —— 所有错误都会被捕获并转为空列表返回，
        同时将友好错误提示输出到 stderr，确保上层调用不会因网络问题崩溃。
    """
    # ── 网络请求层：捕获 requests 各类异常，失败返回空列表 ──
    try:
        response = requests.post(
            BoCha_Url,
            headers={"Authorization": f"Bearer {BoCha_Api}"},
            json={
                "query": query,
                "count": count,
            },
            timeout=15,  # 对齐 fetch_page 的超时设计，避免永久阻塞
        )
        response.raise_for_status()  # 非 2xx 抛出 HTTPError
    except requests.RequestException as e:
        logger.error("%s", _format_search_error(e))
        return []

    # ── 响应解析层：JSON 解析失败（如网关返回 HTML 错误页）──
    try:
        data = response.json()
    except ValueError as e:
        logger.error("搜索响应解析失败（%s）。详细信息：%s", type(e).__name__, e)
        return []

    # ── 防御性取值：data.webPages.value 结构可能缺失或为空 ──
    try:
        pages = data["data"]["webPages"]["value"]
    except (KeyError, TypeError):
        pages = []

    if not pages:
        logger.warning("搜索请求成功，但未返回任何结果。")
        return []

    results = []
    for p in pages:
        if not isinstance(p, dict):  # 跳过异常条目
            continue
        results.append({
            "title": p.get("name", ""),
            "url": p.get("url", ""),
            "snippet": p.get("snippet", ""),
        })

    return results

def build_context(pages: list[dict]) -> str:
    """
    构建搜索结果的上下文字符串。
    如果 page 中包含 _score 和 _flags 字段（来自 source_ranker），
    会自动添加质量标签。
    """
    search_context = ""
    for i, page in enumerate(pages, start=1):
        title = page.get("title", "无标题")
        snippet = page.get("snippet", "")
        url = page.get("url", "")

        # ── 评分标签（如果有）──
        score_badge = ""
        score = page.get("_score")
        flags = page.get("_flags", [])

        if score is not None:
            # 按分数分档（用 ASCII 标签，避免 Windows GBK 终端乱码）
            if score >= 70:
                label = "[推荐抓取]"
            elif score >= 50:
                label = "[可抓取]"
            elif score >= 30:
                label = "[质量一般]"
            else:
                label = "[不建议抓取]"

            score_badge = f"  [{score}分 {label}]"
            if flags:
                score_badge += f" [{', '.join(flags)}]"

        search_context += (
            f"第{i}条{score_badge}\n"
            f"标题：{title}\n"
            f"摘要：{snippet}\n"
            f"链接：{url}\n\n"
        )

    return search_context
