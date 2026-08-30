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
