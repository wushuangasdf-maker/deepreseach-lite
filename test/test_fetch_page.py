"""
网页抓取工具测试 — test_fetch_page.py

覆盖 tools/fetch_page.py：
  fetch_page_tool 的 URL 校验 / _format_http_error / _fallback_extract
  / _extract_content

特点：
  - 网络边界用 monkeypatch 替换 _fetch_html，不碰 httpx 内部实现。
  - _format_http_error 用真实 httpx 异常类构造，确保 isinstance 分支命中。
"""

import httpx

from tools.fetch_page import (
    _extract_content,
    _fallback_extract,
    _fetch_html,
    _format_http_error,
    fetch_page_tool,
)


# ── 辅助：构造带 response 的 HTTPStatusError ───────────────

def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """构造一个携带指定状态码的 httpx.HTTPStatusError。"""
    request = httpx.Request("GET", "http://example.com")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


# ── fetch_page_tool：URL 校验（纯逻辑，不发请求）───────────

def test_fetch_page_empty_url():
    """空字符串 → 提示 URL 不能为空。"""
    assert "URL 不能为空" in fetch_page_tool("")


def test_fetch_page_whitespace_url():
    """全空格 → 提示 URL 不能为空。"""
    assert "URL 不能为空" in fetch_page_tool("   ")


def test_fetch_page_invalid_scheme():
    """非 http/https 协议 → 提示必须以 http/https 开头。"""
    assert "必须以 http:// 或 https:// 开头" in fetch_page_tool("ftp://x.com")


def test_fetch_page_no_scheme():
    """无协议 → 提示必须以 http/https 开头。"""
    assert "必须以 http:// 或 https:// 开头" in fetch_page_tool("example.com")


# ── _format_http_error ────────────────────────────────────

def test_format_http_error_timeout():
    """超时异常 → 含「请求超时」。"""
    assert "请求超时" in _format_http_error(httpx.TimeoutException("t"), "http://x")


def test_format_http_error_404():
    """404 → 含「404」与「页面不存在」。"""
    assert "404" in _format_http_error(_http_status_error(404), "http://x")


def test_format_http_error_5xx():
    """500 → 含「目标网站自身故障」。"""
    assert "目标网站自身故障" in _format_http_error(_http_status_error(500), "http://x")


def test_format_http_error_connect():
    """连接失败 → 含「无法建立连接」。"""
    assert "无法建立连接" in _format_http_error(httpx.ConnectError("c"), "http://x")


def test_format_http_error_other():
    """其他异常 → 含「网络请求失败」。"""
    assert "网络请求失败" in _format_http_error(ValueError("v"), "http://x")


# ── _fallback_extract ────────────────────────────────────

def test_fallback_extract_strips_script():
    """去除 script 标签内容。"""
    html = "<script>var x=1;</script><p>正文</p>"
    text = _fallback_extract(html)
    assert "正文" in text
    assert "var x=1" not in text


def test_fallback_extract_strips_nav_footer():
    """去除 nav / article 语义标签之外的噪声。"""
    html = "<nav>菜单</nav><article>内容</article>"
    text = _fallback_extract(html)
    assert "内容" in text
    assert "菜单" not in text


def test_fallback_extract_block_newline():
    """块级标签之间插入换行（文本节点后带尾随空格）。"""
    html = "<p>段落一</p><p>段落二</p>"
    assert _fallback_extract(html) == "段落一 \n段落二"


def test_fallback_extract_collapses_whitespace():
    """压缩多余空白：无连续双空格、无三连换行。"""
    html = "<p>a   b</p><p></p><p></p><p>c</p>"
    text = _fallback_extract(html)
    assert "  " not in text
    assert "\n\n\n" not in text


# ── _extract_content（当前环境无 trafilatura，走 fallback）──

def test_extract_content_returns_text():
    """入口函数对简单 HTML 返回非空文本。"""
    html = "<p>这是一段正文内容，用于验证提取入口可用。</p>"
    assert _extract_content(html).strip()


def test_extract_content_trafilatura(monkeypatch):
    """trafilatura 可用且返回长文本时，走 trafilatura 分支。"""
    import sys
    import types

    traf = types.ModuleType("trafilatura")
    traf.extract = lambda html, **kw: "这是一段超过一百字符的正文内容。" * 8
    monkeypatch.setitem(sys.modules, "trafilatura", traf)

    text = _extract_content("<html>x</html>")
    assert "正文内容" in text


# ── fetch_page_tool：完整执行路径（mock _fetch_html / _extract_content）──

def test_fetch_page_success(monkeypatch):
    """正常抓取：返回带【网页正文】头与正文文本。"""
    monkeypatch.setattr("tools.fetch_page._fetch_html", lambda url: "<html>ok</html>")
    monkeypatch.setattr(
        "tools.fetch_page._extract_content",
        lambda html: "这是一段足够长的正文内容，用于验证抓取成功的完整路径。" * 2,
    )
    result = fetch_page_tool("http://example.com")
    assert "【网页正文】" in result
    assert "http://example.com" in result


def test_fetch_page_truncates(monkeypatch):
    """正文超过 max_length → 截断并标注。"""
    monkeypatch.setattr("tools.fetch_page._fetch_html", lambda url: "<html>ok</html>")
    monkeypatch.setattr("tools.fetch_page._extract_content", lambda html: "x" * 500)
    result = fetch_page_tool("http://example.com", max_length=200)
    assert "已截断" in result


def test_fetch_page_max_length_clamped(monkeypatch):
    """max_length < 100 → 钳制为 8000，不按原值截断。"""
    monkeypatch.setattr("tools.fetch_page._fetch_html", lambda url: "<html>ok</html>")
    monkeypatch.setattr("tools.fetch_page._extract_content", lambda html: "y" * 120)
    result = fetch_page_tool("http://example.com", max_length=50)
    assert "已截断" not in result  # 120 < 8000，未被截断


def test_fetch_page_html_none(monkeypatch):
    """抓取返回 None → 提示无法获取页面。"""
    monkeypatch.setattr("tools.fetch_page._fetch_html", lambda url: None)
    assert "无法获取页面内容" in fetch_page_tool("http://example.com")


def test_fetch_page_fetch_error(monkeypatch):
    """抓取抛异常 → 走 _format_http_error。"""
    def boom(url):
        raise httpx.ConnectError("c")

    monkeypatch.setattr("tools.fetch_page._fetch_html", boom)
    assert "网络请求失败" in fetch_page_tool("http://example.com")


def test_fetch_page_extract_error(monkeypatch):
    """正文提取抛异常 → 提示提取失败。"""
    monkeypatch.setattr("tools.fetch_page._fetch_html", lambda url: "<html>ok</html>")

    def boom(html):
        raise ValueError("bad html")

    monkeypatch.setattr("tools.fetch_page._extract_content", boom)
    assert "正文提取失败" in fetch_page_tool("http://example.com")


def test_fetch_page_short_content(monkeypatch):
    """提取正文过短 → 提示未提取到有效正文。"""
    monkeypatch.setattr("tools.fetch_page._fetch_html", lambda url: "<html>ok</html>")
    monkeypatch.setattr("tools.fetch_page._extract_content", lambda html: "太短")
    assert "未能从页面中提取到有效正文" in fetch_page_tool("http://example.com")


# ── _fetch_html：httpx 边界 ──────────────────────────────

def test_fetch_html_success(monkeypatch):
    """httpx 成功响应 → 返回 response.text。"""
    class _Resp:
        text = "<html>ok</html>"

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    assert _fetch_html("http://example.com") == "<html>ok</html>"


def test_fetch_html_error_returns_none(monkeypatch):
    """httpx 抛异常 → 返回 None。"""
    class _Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            raise httpx.ConnectError("c")

    monkeypatch.setattr(httpx, "Client", _Client)
    assert _fetch_html("http://example.com") is None
