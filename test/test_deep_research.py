"""
深度研究编排测试 — test_deep_research.py

覆盖 agent/agents.py 的 deep_research 编排逻辑（mock 集成测试）。

特点：
  - mock 掉 LLM 客户端（脚本化 fake client），不真调 DeepSeek。
  - mock 掉 save_report_tool，不真写 reports/ 文件。
  - verbose=False 关闭打印，同时验证静默路径不崩溃。
"""

from agent.agents import deep_research


# ── fake 结构：脚本化 client 与响应 ──────────────────────

class _Message:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _ToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = _Function(name, arguments)


class _Function:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _Choice:
    def __init__(self, message):
        self.message = message


class _Response:
    def __init__(self, message):
        self.choices = [_Choice(message)]


class _ScriptedClient:
    """按脚本顺序返回预设响应；用完返回空文本响应兜底。"""

    def __init__(self, responses, model="deepseek-chat"):
        self.model = model
        self._responses = list(responses)
        self._cursor = 0
        self.call_count = 0

    def chat_completion_with_retry(self, **kwargs):
        self.call_count += 1
        if self._cursor < len(self._responses):
            resp = self._responses[self._cursor]
            self._cursor += 1
            return resp
        # 脚本耗尽兜底：返回纯文本
        return _Response(_Message(content=""))

    @property
    def remaining(self):
        return len(self._responses) - self._cursor


def _text(content: str) -> _Response:
    return _Response(_Message(content=content))


def _tool_calls(calls) -> _Response:
    return _Response(_Message(tool_calls=calls))


def _save_call(arguments: str) -> _ToolCall:
    return _ToolCall("call_save", "save_report_tool", arguments)


# ── deep_research：happy path ─────────────────────────────

def test_deep_research_happy_path(monkeypatch):
    """规划 2 个子问题 → 各研究 2 轮 → 汇总 → 报告触发保存。"""
    plan_text = (
        "1. 市场规模与增长 | 2026 AI芯片 市场规模\n"
        "2. 竞争格局 | AI芯片 厂商 份额"
    )
    client = _ScriptedClient([
        _text(plan_text),                    # 1 规划
        _text("研究了市场规模。"),             # 2 子问题1 第1轮
        _text("补充了竞争信息。"),             # 3 子问题1 第2轮
        _text("研究了竞争格局。"),             # 4 子问题2 第1轮
        _text("补充了厂商份额。"),             # 5 子问题2 第2轮
        _text("总体总结。"),                  # 6 汇总
        _tool_calls([_save_call('{"report": "报告正文", "title": "标题"}')]),  # 7 报告
    ])

    monkeypatch.setattr("agent.agents.get_llm_client", lambda **kw: client)
    monkeypatch.setattr("agent.agents.save_report_tool", lambda **kw: "已保存")

    result = deep_research("AI芯片市场", max_turns=12, force_report_at=8, verbose=False)

    assert result == "报告已成功生成并保存。"
    # 全部 7 个脚本响应都被消费，验证轮数推进符合预期
    assert client.remaining == 0


# ── deep_research：规划失败降级 ───────────────────────────

def test_deep_research_plan_failure_degrades(monkeypatch):
    """规划阶段 LLM 失败（返回 None）→ 降级为不拆解模式，流程不崩溃。"""
    client = _ScriptedClient([
        None,                               # 1 规划失败
        _text("研究了整体课题。"),             # 2 子问题(整体) 第1轮
        _text("补充信息。"),                  # 3 子问题(整体) 第2轮
        _text("总结。"),                     # 4 汇总
        _tool_calls([_save_call('{"report": "r", "title": "t"}')]),  # 5 报告
    ])

    monkeypatch.setattr("agent.agents.get_llm_client", lambda **kw: client)
    monkeypatch.setattr("agent.agents.save_report_tool", lambda **kw: "已保存")

    result = deep_research("AI芯片市场", max_turns=12, force_report_at=8, verbose=False)

    assert result == "报告已成功生成并保存。"
