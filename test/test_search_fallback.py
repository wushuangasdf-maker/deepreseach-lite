"""
兜底调度模块测试 — test_search_fallback.py

覆盖 core/search.py 的 search_with_fallback。

特点：
  - 用 monkeypatch 替换 core.search 中引用的 bocha_search / baidu_search，
    验证「博查优先、失败降级」的调度逻辑。
"""

from core.search import search_with_fallback


def test_bocha_has_result_skips_baidu(monkeypatch):
    """博查有结果 → 直接返回，不触发百度。"""
    bocha_called = {"n": 0}
    baidu_called = {"n": 0}

    def _bocha(q, c):
        bocha_called["n"] += 1
        return [{"title": "t", "url": "u", "snippet": "s"}]

    def _baidu(q, c):
        baidu_called["n"] += 1
        return []

    monkeypatch.setattr("core.search.bocha_search", _bocha)
    monkeypatch.setattr("core.search.baidu_search", _baidu)

    assert search_with_fallback("q") == [{"title": "t", "url": "u", "snippet": "s"}]
    assert bocha_called["n"] == 1
    assert baidu_called["n"] == 0


def test_bocha_empty_falls_back_to_baidu(monkeypatch):
    """博查空结果 → 降级到百度。"""
    monkeypatch.setattr("core.search.bocha_search", lambda q, c: [])
    monkeypatch.setattr(
        "core.search.baidu_search",
        lambda q, c: [{"title": "b", "url": "bu", "snippet": "bs"}],
    )

    assert search_with_fallback("q") == [{"title": "b", "url": "bu", "snippet": "bs"}]


def test_both_empty_returns_empty(monkeypatch):
    """博查与百度均空 → 返回空列表。"""
    monkeypatch.setattr("core.search.bocha_search", lambda q, c: [])
    monkeypatch.setattr("core.search.baidu_search", lambda q, c: [])

    assert search_with_fallback("q") == []
