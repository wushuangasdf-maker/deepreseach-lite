"""
网页正文抓取工具 — fetch_page.py

从给定的 URL 获取 HTML，提取正文内容，返回清洗后的纯文本。
优先使用 trafilatura（需 pip install trafilatura）进行高精度提取，
如果未安装则回退到标准库 html.parser + 正则的轻量方案。

用法（供 Agent 调用）:
    from tools.fetch_page import fetch_page_tool, get_tool_schema
    text = fetch_page_tool("https://example.com/article")
    schema = get_tool_schema()
"""

import os
import sys
import re
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOOL_NAME = "fetch_page_tool"
TOOL_DESCRIPTION = (
    "抓取指定 URL 的网页并提取正文纯文本内容。"
    "适用场景：搜索返回的链接需要查看完整内容时、需要核对事实细节时、需要从页面中提取具体数据时。"
    "不适用场景：需要登录才能访问的页面、PDF 或其他非 HTML 资源、纯前端渲染的 SPA 页面。"
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "要抓取的网页 URL，必须是以 http:// 或 https:// 开头的完整链接",
        },
        "max_length": {
            "type": "integer",
            "description": "返回文本的最大字符数，默认 8000。超出部分会被截断并标注。",
            "default": 8000,
        },
    },
    "required": ["url"],
}


# ── 公开工具函数 ─────────────────────────────────────────────

def fetch_page_tool(url: str, max_length: int = 8000) -> str:
    """
    抓取网页正文，返回适合 LLM 阅读的纯文本。

    参数:
        url (str): 目标网页的完整 URL。
        max_length (int): 返回文本的最大字符数，默认 8000。

    返回:
        str: 格式化后的正文文本，或自然语言错误提示。

    注意:
        本函数绝不抛出异常 —— 所有错误都被捕获并转为字符串返回，
        因为 LLM 只能处理文本。
    """
    if not url or not url.strip():
        return "错误：URL 不能为空。"

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        return (
            f"错误：URL 必须以 http:// 或 https:// 开头。"
            f"实际收到：{url}"
        )

    if max_length < 100:
        max_length = 8000
#双层防护避免出现问题
    try:
        html = _fetch_html(url)
    except Exception as e:
        return _format_http_error(e, url)

    if html is None:
        return (
            f"无法获取页面内容（{url}）。"
            f"可能原因：网站拒绝访问、网络超时、或链接已失效。"
            f"建议尝试其他来源或检查 URL 是否正确。"
        )

    try:
        text = _extract_content(html)
    except Exception as e:
        return (
            f"正文提取失败（{type(e).__name__}）。URL：{url}\n"
            f"详细信息：{e}。页面可能为纯 JS 渲染或非标准 HTML。"
        )

    if not text or len(text.strip()) < 50:
        return (
            f"未能从页面中提取到有效正文（{url}）。"
            f"可能原因：页面主要为图片/视频内容、需要 JS 渲染、或为列表/导航页。"
            f"建议更换来源。"
        )

    original_len = len(text)

    if len(text) > max_length:
        text = text[:max_length] + (
            f"\n\n... [内容已截断，原文共 {original_len} 字符，"
            f"此处仅展示前 {max_length} 字符]"
        )

    header = f"【网页正文】来源：{url}\n\n"
    return header + text


def get_tool_schema() -> dict:
    """
    返回此工具的 OpenAI Function Calling 格式定义。

    Agent 调用此函数获取 schema 后，注入到 LLM 请求的 tools 参数中，
    LLM 即可了解此工具的能力并按需生成调用指令。

    返回:
        dict: 符合 OpenAI tools 格式的字典
    """
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": TOOL_DESCRIPTION,
            "parameters": TOOL_PARAMETERS,
        },
    }


# ── 内部实现 ─────────────────────────────────────────────────

def _fetch_html(url: str) -> str | None:
    """
    用 httpx 发送 GET 请求获取原始 HTML。

    模拟真实浏览器请求头以降低被反爬拦截的概率；
    httpx 自动处理 gzip 解压、编码检测、重定向跟随。
    失败时返回 None，不抛异常。
    """
    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }

    try:
        with httpx.Client(
            timeout=15, follow_redirects=True, headers=headers
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
    except Exception:
        return None


def _format_http_error(e: Exception, url: str) -> str:
    """将 httpx 异常转为对用户友好的错误提示。"""
    import httpx

    error_type = type(e).__name__

    if isinstance(e, httpx.TimeoutException):
        hint = "请求超时（15 秒），网站响应过慢或网络不稳定。建议稍后重试。"
    elif isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 404:
            hint = "服务器返回 404，页面不存在或链接已失效。"
        elif code == 403:
            hint = "服务器返回 403，网站拒绝了访问请求。"
        elif code >= 500:
            hint = f"服务器返回 {code}，目标网站自身故障。建议稍后重试。"
        else:
            hint = f"服务器返回 HTTP {code}，请求未成功。"
    elif isinstance(e, httpx.ConnectError):
        hint = "无法建立连接，可能是域名解析失败、网站已下线、或网络不通。"
    else:
        hint = f"详细信息：{e}。建议检查链接是否可访问。"

    return f"网络请求失败（{error_type}）。URL：{url}\n{hint}"


def _extract_content(html: str) -> str:
    """
    从 HTML 中提取正文。

    优先使用 trafilatura（科研场景最精准的正文提取库，
    pip install trafilatura 即可安装）。
    如果未安装，自动回退到标准库 html.parser + 正则。
    """
    # 优先方案：trafilatura
    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            include_links=False,       # 不保留链接标记，减少噪声
            include_images=False,      # 不保留图片 alt
            include_tables=False,      # 不保留表格
            favor_precision=True,      # 偏向精确率（宁可漏一些也不混入噪声）
        )
        if text and len(text.strip()) >= 100:
            return text.strip()
    except ImportError:
        pass

    # 回退方案：纯标准库
    return _fallback_extract(html)


def _fallback_extract(html: str) -> str:
    """
    纯标准库回退方案：去除脚本/样式/导航等噪声标签后提取文本。

    这是一个轻量级提取器，准确度不如 trafilatura，
    但确保在无任何第三方依赖时仍可工作。
    """
    # 这些标签的内容通常不是正文
    SKIP_TAGS = {
        "script", "style", "nav", "footer", "header", "aside",
        "code", "noscript", "iframe", "svg", "canvas", "form",
        "select", "textarea", "button", "template",
    }

    # 这些标签结束时应插入换行，使输出格式更清晰
    BLOCK_TAGS = {
        "p", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "div", "section", "article", "tr", "blockquote",
        "pre", "hr", "ul", "ol", "dl", "dt", "dd",
    }

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self.skip_depth = 0

        def handle_starttag(self, tag, attrs):
            if tag.lower() in SKIP_TAGS:
                self.skip_depth += 1

        def handle_endtag(self, tag):
            if tag.lower() in SKIP_TAGS:
                self.skip_depth = max(0, self.skip_depth - 1)
            elif tag.lower() in BLOCK_TAGS:
                self.parts.append("\n")

        def handle_data(self, data):
            if self.skip_depth > 0:
                return
            text = data.strip()
            if text:
                self.parts.append(text)
                self.parts.append(" ")

    extractor = TextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass

    text = "".join(extractor.parts)

    # 压缩多余空白
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    return text.strip()


# ── 自测 ─────────────────────────────────────────────────────

if __name__ == "__main__":
    test_url = "https://httpbin.org/html"
    print(f"测试抓取: {test_url}")
    print(fetch_page_tool(test_url, max_length=500))
