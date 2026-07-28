import requests
from core.config import BoCha_Api, BoCha_Url, BoCha_Search_Count

def bocha_search(query: str, count: int = BoCha_Search_Count) -> list[dict]:
    """
    使用BoCha API进行网页搜索。

    参数:
        query (str): 搜索查询字符串。
        count (int): 返回的搜索结果数量，默认为BoCha_Search_Count。
    """
    response = requests.post(
        BoCha_Url,
        headers={ "Authorization": f"Bearer {BoCha_Api}"},
        json={
            "query": query,
            "count": count,
        }
    )
    response.raise_for_status()  # 如果请求失败，抛出异常
    pages=response.json()["data"]["webPages"]["value"]
    return [
        {"title": p["name"], "url": p.get("url", ""), "snippet": p.get("snippet", "")}
        for p in pages
    ]

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
