"""
百度千帆搜索模块测试 — test_baidu_search.py

覆盖 core/baidu_search.py 的 baidu_search。

特点：
  - 网络边界用 monkeypatch 替换 requests.post。
  - 验证 references → title/url/snippet 的字段映射，
    以及 snippet 缺失时回退到 content。
"""

import requests

from core.baidu_search import baidu_search


class _FakeResponse:
    """假 response，通过控制 raise_for_status / json 行为触发各分支。"""

    def __init__(self, json_data=None, raise_error=None, json_error=None):
        self._json_data = json_data
        self._raise_error = raise_error
        self._json_error = json_error

    def raise_for_status(self):
        if self._raise_error is not None:
            raise self._raise_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


def _http_error(status_code: int) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status_code
    return requests.HTTPError("boom", response=resp)


# ── baidu_search ─────────────────────────────────────────

def test_baidu_search_success(monkeypatch):
    """正常返回：references → title/url/snippet 映射正确。"""
    payload = {
        "references": [
            {"title": "标题A", "url": "https://a.com", "snippet": "摘要A"},
        ]
    }
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResponse(json_data=payload))

    assert baidu_search("query") == [
        {"title": "标题A", "url": "https://a.com", "snippet": "摘要A"},
    ]


def test_baidu_search_snippet_falls_back_to_content(monkeypatch):
    """snippet 缺失时回退到 content。"""
    payload = {
        "references": [
            {"title": "标题A", "url": "https://a.com", "content": "内容A"},
        ]
    }
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResponse(json_data=payload))

    assert baidu_search("query") == [
        {"title": "标题A", "url": "https://a.com", "snippet": "内容A"},
    ]


def test_baidu_search_missing_fields(monkeypatch):
    """结果缺 title/url 字段 → 兜底为空字符串。"""
    payload = {"references": [{"snippet": "摘要A"}]}
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResponse(json_data=payload))

    assert baidu_search("query") == [
        {"title": "", "url": "", "snippet": "摘要A"},
    ]


def test_baidu_search_http_error(monkeypatch):
    """非 2xx（raise_for_status 抛 HTTPError）→ 返回空列表。"""
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **kw: _FakeResponse(raise_error=_http_error(500)),
    )
    assert baidu_search("query") == []


def test_baidu_search_json_parse_error(monkeypatch):
    """响应 JSON 解析失败 → 返回空列表。"""
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **kw: _FakeResponse(json_error=ValueError("bad json")),
    )
    assert baidu_search("query") == []


def test_baidu_search_empty_references(monkeypatch):
    """references 为空列表 → 返回空列表。"""
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **kw: _FakeResponse(json_data={"references": []}),
    )
    assert baidu_search("query") == []


def test_baidu_search_missing_references(monkeypatch):
    """结构缺 references 字段 → 返回空列表。"""
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **kw: _FakeResponse(json_data={}),
    )
    assert baidu_search("query") == []


def test_baidu_search_skips_non_dict(monkeypatch):
    """references 中混入非 dict 条目 → 跳过，只保留 dict。"""
    payload = {
        "references": [
            {"title": "标题A", "url": "https://a.com", "snippet": "摘要A"},
            None,
            "not-a-dict",
        ]
    }
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResponse(json_data=payload))

    assert baidu_search("query") == [
        {"title": "标题A", "url": "https://a.com", "snippet": "摘要A"},
    ]
