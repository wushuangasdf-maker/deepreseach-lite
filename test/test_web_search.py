"""
网络搜索工具测试 — test_web_search.py

覆盖 tools/web_search.py 的 web_search_tool 各分支。
mock search_with_fallback / rank_sources / build_context，不真发请求。
"""

import tools.web_search as ws


def _pages():
    return [
        {"title": "A", "url": "https://a.com", "snippet": "snippet a"},
        {"title": "B", "url": "https://b.com", "snippet": "snippet b"},
    ]


def test_web_search_empty_query():
    """空查询 → 提示不能为空。"""
    assert "搜索查询不能为空" in ws.web_search_tool("")


def test_web_search_whitespace_query():
    """全空格查询 → 提示不能为空。"""
    assert "搜索查询不能为空" in ws.web_search_tool("   ")


def test_web_search_clamps_count(monkeypatch):
    """count 超上限（>10）→ 被钳制为 10。"""
    captured = {}

    def fake_search(query, count):
        captured["count"] = count
        return []

    monkeypatch.setattr(ws, "search_with_fallback", fake_search)
    ws.web_search_tool("query", count=99)
    assert captured["count"] == 10


def test_web_search_no_results(monkeypatch):
    """搜索返回空列表 → 提示未找到。"""
    monkeypatch.setattr(ws, "search_with_fallback", lambda q, c: [])
    assert "未找到" in ws.web_search_tool("query")


def test_web_search_exception(monkeypatch):
    """底层搜索抛异常 → 转为错误字符串。"""
    def boom(q, c):
        raise RuntimeError("network down")

    monkeypatch.setattr(ws, "search_with_fallback", boom)
    assert "搜索失败" in ws.web_search_tool("query")


def test_web_search_success(monkeypatch):
    """正常路径：评分 + 拼接上下文 + 头部统计。"""
    monkeypatch.setattr(ws, "search_with_fallback", lambda q, c: _pages())
    monkeypatch.setattr("core.source_ranker.rank_sources", lambda pages, q: pages)
    monkeypatch.setattr(ws, "build_context", lambda pages: "BUILT")

    result = ws.web_search_tool("query")
    assert "共找到 2 条" in result
    assert "BUILT" in result
