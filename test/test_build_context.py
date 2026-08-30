"""
搜索结果格式化测试 — test_build_context.py

覆盖 core/bocha_search.py 的 build_context(pages)：
将搜索结果列表格式化为给 LLM 阅读的纯文本。

特点：纯函数，零依赖。整体输出用 == 断言完整字符串，
局部（score 分档 / flags 追加）用 in 断言精确子串。
"""

from core.bocha_search import build_context


# ── build_context ─────────────────────────────────────────

def test_build_context_empty_list():
    """空列表 → 空字符串。"""
    assert build_context([]) == ""


def test_build_context_single_page():
    """单条完整字段的格式化输出。"""
    pages = [{"title": "标题A", "url": "https://a.com", "snippet": "摘要A"}]
    expected = (
        "第1条\n"
        "标题：标题A\n"
        "摘要：摘要A\n"
        "链接：https://a.com\n"
        "\n"
    )
    assert build_context(pages) == expected


def test_build_context_missing_fields():
    """缺 title/url/snippet 时的兜底值。"""
    pages = [{}]
    expected = (
        "第1条\n"
        "标题：无标题\n"
        "摘要：\n"
        "链接：\n"
        "\n"
    )
    assert build_context(pages) == expected


def test_build_context_score_70():
    """score=70 命中「推荐抓取」档。"""
    page = {"title": "t", "url": "u", "snippet": "s", "_score": 70}
    assert "[70分 [推荐抓取]]" in build_context([page])


def test_build_context_score_50():
    """score=50 命中「可抓取」档。"""
    page = {"title": "t", "url": "u", "snippet": "s", "_score": 50}
    assert "[50分 [可抓取]]" in build_context([page])


def test_build_context_score_30():
    """score=30 命中「质量一般」档。"""
    page = {"title": "t", "url": "u", "snippet": "s", "_score": 30}
    assert "[30分 [质量一般]]" in build_context([page])


def test_build_context_score_29():
    """score=29 命中「不建议抓取」档。"""
    page = {"title": "t", "url": "u", "snippet": "s", "_score": 29}
    assert "[29分 [不建议抓取]]" in build_context([page])


def test_build_context_flags_appended():
    """有 _flags 时追加到标签后，用逗号连接。"""
    page = {
        "title": "t",
        "url": "u",
        "snippet": "s",
        "_score": 80,
        "_flags": ["权威来源", "高度相关"],
    }
    assert "[80分 [推荐抓取]] [权威来源, 高度相关]" in build_context([page])


def test_build_context_flags_empty_list():
    """_flags 为空列表时只出标签，不追加空 []。"""
    page = {"title": "t", "url": "u", "snippet": "s", "_score": 80, "_flags": []}
    text = build_context([page])
    assert "[80分 [推荐抓取]]" in text
    assert "[]" not in text


def test_build_context_sequence_numbering():
    """多条结果按 第1条/第2条/第3条 递增编号。"""
    pages = [
        {"title": "a", "url": "ua", "snippet": "sa"},
        {"title": "b", "url": "ub", "snippet": "sb"},
        {"title": "c", "url": "uc", "snippet": "sc"},
    ]
    text = build_context(pages)
    assert "第1条" in text
    assert "第2条" in text
    assert "第3条" in text
