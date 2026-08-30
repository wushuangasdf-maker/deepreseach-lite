"""
来源质量评分模块测试 — test_source_ranker.py

覆盖 core/source_ranker.py 的纯规则引擎：
  _score_authority / _score_title / _score_snippet / _score_relevance
  / _collect_flags / rank_sources

特点：全部为纯函数，零外部依赖，无需 mock。用精确数值断言。
"""

from core.source_ranker import (
    _collect_flags,
    _score_authority,
    _score_relevance,
    _score_snippet,
    _score_title,
    rank_sources,
)


# ── _score_authority（满分 30，中性 15）──────────────────────

def test__score_authority_exact_match():
    """权威域名精确匹配。"""
    assert _score_authority("https://www.gov.cn/xx") == 30.0


def test__score_authority_strips_www():
    """去掉 www. 前缀后匹配。"""
    assert _score_authority("https://www.people.com.cn/a") == 25.0


def test__score_authority_low_quality():
    """低质量域名命中白名单。"""
    assert _score_authority("https://news.csdn.net/xxx") == 8.0


def test__score_authority_suffix_match():
    """后缀模糊匹配：foo.stats.gov.cn 命中 .gov.cn。"""
    assert _score_authority("https://foo.stats.gov.cn/x") == 30.0


def test__score_authority_unknown_domain():
    """未命中白名单 → 中性分。"""
    assert _score_authority("https://example.com") == 15.0


def test__score_authority_empty_url():
    """空 URL → 中性分。"""
    assert _score_authority("") == 15.0


# ── _score_title（满分 25）──────────────────────────────────

def test__score_title_empty():
    """空标题 → 极低分。"""
    assert _score_title("", "") == 5.0


def test__score_title_clickbait():
    """含 2 个标题党词 + 1 感叹号：15 - 10 - 2 = 3。"""
    assert _score_title("震惊！这个秘密你绝对想不到", "") == 3.0


def test__score_title_too_short():
    """标题过短（≤5 中文字）扣 8 分。"""
    assert _score_title("标题", "") == 7.0


def test__score_title_many_exclamation():
    """感叹号 ≥2 扣 5 分。"""
    assert _score_title("这个产品真的非常非常厉害啊！！！", "") == 10.0


def test__score_title_keyword_bonus():
    """正式标题(+4) + 关键词全命中(+3) = 22。"""
    assert _score_title("量子计算技术的最新进展与应用前景分析", "量子 计算") == 22.0


# ── _score_snippet（满分 25）────────────────────────────────

def test__score_snippet_empty():
    """空摘要 → 极低分。"""
    assert _score_snippet("") == 3.0


def test__score_snippet_low_quality_marker():
    """含低质量标记「登录」扣 6 分，长度 39<80 再扣 3 分：15 - 6 - 3 = 6。"""
    snippet = "这篇文章内容非常丰富，涵盖了多个方面的详细分析，但是需要登录后才能查看完整内容"
    assert _score_snippet(snippet) == 6.0


def test__score_snippet_numeric_info():
    """含数字信息加分 6，长度 44<80 扣 3：15 + 6 - 3 = 18。"""
    snippet = "根据最新统计数据，2026年中国市场规模达到3.5亿元，同比增长80%，增速位居全球前列"
    assert _score_snippet(snippet) == 18.0


def test__score_snippet_too_short():
    """摘要过短（<30 字）扣 8 分。"""
    assert _score_snippet("内容很短") == 7.0


# ── _score_relevance（满分 20，中性 10）─────────────────────

def test__score_relevance_empty_query():
    """空 query → 中性分。"""
    assert _score_relevance("", "", "") == 10.0


def test__score_relevance_all_in_title():
    """关键词全命中标题 → 满分。"""
    assert _score_relevance("量子计算芯片最新突破", "", "量子计算 芯片") == 20.0


def test__score_relevance_only_in_snippet():
    """关键词只在摘要命中 → 折合分。"""
    assert _score_relevance("最新科技新闻", "量子计算和芯片技术", "量子计算 芯片") == 12.0


def test__score_relevance_no_match():
    """完全没命中 → 0 分。"""
    assert _score_relevance("美食推荐", "今天吃什么", "量子计算 芯片") == 0.0


def test__score_relevance_floor():
    """几乎没命中但有 1 词命中 → 触发 3.0 保底分。"""
    assert _score_relevance("量子技术", "", "量子 计算 芯片 人工 智能 大模 突破") == 3.0


# ── _collect_flags ─────────────────────────────────────────

def test__collect_flags_high_quality():
    """权威 + 高度相关。"""
    assert _collect_flags(30.0, 25.0, 25.0, 20.0) == ["权威来源", "高度相关"]


def test__collect_flags_low_quality():
    """低可信度 + 标题差 + 摘要少。"""
    assert _collect_flags(5.0, 3.0, 3.0, 2.0) == ["来源可信度低", "标题质量差", "摘要信息少"]


# ── rank_sources（入口）────────────────────────────────────

def test_rank_sources_dedup_by_url():
    """相同 URL 只保留第一条。"""
    pages = [
        {"title": "a", "url": "https://same.com/x", "snippet": "b"},
        {"title": "c", "url": "https://same.com/x", "snippet": "d"},
    ]
    result = rank_sources(pages, "query")
    assert len(result) == 1
    assert result[0]["url"] == "https://same.com/x"


def test_rank_sources_filters_empty_url():
    """URL 为空的条目被过滤掉。"""
    pages = [
        {"title": "a", "url": "", "snippet": "b"},
        {"title": "c", "url": "https://keep.com/x", "snippet": "d"},
    ]
    result = rank_sources(pages, "query")
    assert len(result) == 1
    assert result[0]["url"] == "https://keep.com/x"


def test_rank_sources_sorted_and_annotated():
    """返回按 _score 降序，且每条含 int 分数与 list 标记。"""
    pages = [
        {"title": "量子计算突破", "url": "https://www.gov.cn/a", "snippet": "2026年重大进展"},
        {"title": "震惊！秘密", "url": "https://example.com/b", "snippet": "点击查看"},
        {"title": "", "url": "https://example.com/c", "snippet": ""},
    ]
    result = rank_sources(pages, "量子计算")

    assert len(result) == 3
    for page in result:
        assert isinstance(page["_score"], int)
        assert isinstance(page["_flags"], list)
    # 降序：前一条分数 >= 后一条
    assert result[0]["_score"] >= result[1]["_score"] >= result[2]["_score"]
