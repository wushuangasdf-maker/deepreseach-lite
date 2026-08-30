"""
博查搜索模块测试 — test_bocha_search.py

覆盖 core/bocha_search.py 的 bocha_search 与 _format_search_error。

特点：
  - bocha_search 的网络边界用 monkeypatch 替换 requests.post。
  - _format_search_error 用真实 requests 异常类构造，确保 isinstance 分支命中。
"""

import requests

from core.bocha_search import _format_search_error, bocha_search


# ── 辅助：构造带/不带 response 的 HTTPError ───────────────

def _http_error(status_code: int | None) -> requests.HTTPError:
    """构造携带指定状态码的 requests.HTTPError；status_code=None 时不带 response。"""
    if status_code is None:
        return requests.HTTPError("boom")
    resp = requests.Response()
    resp.status_code = status_code
    return requests.HTTPError("boom", response=resp)


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


# ── _format_search_error ─────────────────────────────────

def test_format_search_error_timeout():
    assert "请求超时" in _format_search_error(requests.Timeout("t"))


def test_format_search_error_connection():
    assert "无法连接搜索服务" in _format_search_error(requests.ConnectionError("c"))


def test_format_search_error_401():
    msg = _format_search_error(_http_error(401))
    assert "鉴权失败" in msg
    assert "401" in msg


def test_format_search_error_403():
    msg = _format_search_error(_http_error(403))
    assert "鉴权失败" in msg
    assert "403" in msg


def test_format_search_error_429():
    msg = _format_search_error(_http_error(429))
    assert "429" in msg
    assert "速率限制" in msg


def test_format_search_error_5xx():
    assert "服务端故障" in _format_search_error(_http_error(500))


def test_format_search_error_no_response():
    """HTTPError 但 response 为 None → code 兜底为 0，走「未成功」分支。"""
    assert "HTTP 0" in _format_search_error(_http_error(None))


def test_format_search_error_other():
    assert "搜索请求失败" in _format_search_error(ValueError("v"))


# ── bocha_search ─────────────────────────────────────────

def test_bocha_search_success(monkeypatch):
    """正常返回：name→title 映射正确。"""
    payload = {
        "data": {
            "webPages": {
                "value": [
                    {"name": "标题A", "url": "https://a.com", "snippet": "摘要A"},
                ]
            }
        }
    }
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResponse(json_data=payload))

    assert bocha_search("query") == [
        {"title": "标题A", "url": "https://a.com", "snippet": "摘要A"},
    ]


def test_bocha_search_missing_name(monkeypatch):
    """结果缺 name 字段 → title 兜底为空字符串。"""
    payload = {
        "data": {
            "webPages": {
                "value": [
                    {"url": "https://a.com", "snippet": "摘要A"},
                ]
            }
        }
    }
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResponse(json_data=payload))

    assert bocha_search("query") == [
        {"title": "", "url": "https://a.com", "snippet": "摘要A"},
    ]


def test_bocha_search_http_error(monkeypatch):
    """非 2xx（raise_for_status 抛 HTTPError）→ 返回空列表。"""
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **kw: _FakeResponse(raise_error=_http_error(500)),
    )
    assert bocha_search("query") == []


def test_bocha_search_json_parse_error(monkeypatch):
    """响应 JSON 解析失败 → 返回空列表。"""
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **kw: _FakeResponse(json_error=ValueError("bad json")),
    )
    assert bocha_search("query") == []


def test_bocha_search_missing_webpages(monkeypatch):
    """结构缺 webPages 字段 → 返回空列表。"""
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **kw: _FakeResponse(json_data={"data": {}}),
    )
    assert bocha_search("query") == []


def test_bocha_search_empty_value(monkeypatch):
    """webPages.value 为空列表 → 返回空列表。"""
    payload = {"data": {"webPages": {"value": []}}}
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResponse(json_data=payload))
    assert bocha_search("query") == []


def test_bocha_search_skips_non_dict(monkeypatch):
    """value 中混入非 dict 条目 → 跳过，只保留 dict。"""
    payload = {
        "data": {
            "webPages": {
                "value": [
                    {"name": "标题A", "url": "https://a.com", "snippet": "摘要A"},
                    None,
                    "not-a-dict",
                ]
            }
        }
    }
    monkeypatch.setattr("requests.post", lambda *a, **kw: _FakeResponse(json_data=payload))

    assert bocha_search("query") == [
        {"title": "标题A", "url": "https://a.com", "snippet": "摘要A"},
    ]
