"""
知识库搜索工具测试 — test_kb_search.py

覆盖 tools/kb_search.py 的 kb_search_tool 各分支。
mock _get_kb，不加载模型/索引。
"""

import tools.kb_search as kbs


class _FakeKB:
    def __init__(self, results=None, error=None):
        self._results = results or []
        self._error = error

    def search(self, query, top_k=5):
        if self._error:
            raise self._error
        return self._results


def test_kb_search_empty_query():
    """空查询 → 提示不能为空。"""
    assert "知识库搜索查询不能为空" in kbs.kb_search_tool("")


def test_kb_search_uninitialized(monkeypatch):
    """索引不存在（_get_kb 返回 None）→ 提示未初始化。"""
    monkeypatch.setattr(kbs, "_get_kb", lambda: None)
    assert "知识库未初始化" in kbs.kb_search_tool("query")


def test_kb_search_exception(monkeypatch):
    """检索抛异常 → 转为错误字符串。"""
    monkeypatch.setattr(kbs, "_get_kb", lambda: _FakeKB(error=RuntimeError("boom")))
    assert "知识库搜索失败" in kbs.kb_search_tool("query")


def test_kb_search_no_results(monkeypatch):
    """检索返回空列表 → 提示未找到。"""
    monkeypatch.setattr(kbs, "_get_kb", lambda: _FakeKB(results=[]))
    assert "未在知识库中找到" in kbs.kb_search_tool("query")


def test_kb_search_success(monkeypatch):
    """正常路径：格式化结果，含来源与相似度。"""
    results = [{"source": "a.md", "score": 0.95, "text": "正文内容"}]
    monkeypatch.setattr(kbs, "_get_kb", lambda: _FakeKB(results=results))

    out = kbs.kb_search_tool("query", top_k=5)
    assert "共找到 1 条" in out
    assert "a.md" in out
    assert "0.95" in out
    assert "正文内容" in out
