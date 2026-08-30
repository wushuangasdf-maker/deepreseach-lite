import logging

from core.bocha_search import bocha_search
from core.baidu_search import baidu_search

logger = logging.getLogger(__name__)


def search_with_fallback(query: str, count: int = 5) -> list[dict]:
    """
    优先使用博查搜索，失败或返回空结果时降级到百度千帆搜索。

    参数:
        query (str): 搜索查询字符串。
        count (int): 返回的搜索结果数量。

    返回:
        list[dict]: 搜索结果列表，每项含 title/url/snippet 字段。

    注意:
        绝不抛出异常 —— 两个搜索引擎均保证失败时返回空列表，
        因此本函数只会返回结果列表或空列表。
    """
    pages = bocha_search(query, count)
    if pages:
        return pages

    logger.warning("博查搜索无结果，降级到百度千帆搜索。")
    return baidu_search(query, count)
