"""
任务取消原语测试 — test_agents_cancel.py

覆盖 agent/agents.py 的 ResearchCancelled 与 _check_cancelled，
以及 deep_research 在检查点抛出的行为。

特点：
  - 已置位的 Event 会让 deep_research 在 CP0（初始化前）立即抛异常，
    不触发任何 LLM 调用，因此无需 mock 网络。
"""

import threading

import pytest

from agent.agents import ResearchCancelled, _check_cancelled, deep_research


# ── _check_cancelled ───────────────────────────────────

def test_check_cancelled_none_no_raise():
    """event 为 None（CLI/旧调用方未传）→ 放行不抛。"""
    _check_cancelled(None)


def test_check_cancelled_not_set_no_raise():
    """event 未置位 → 放行不抛。"""
    _check_cancelled(threading.Event())


def test_check_cancelled_set_raises():
    """event 已置位 → 抛 ResearchCancelled。"""
    event = threading.Event()
    event.set()
    with pytest.raises(ResearchCancelled):
        _check_cancelled(event)


# ── deep_research 检查点 ───────────────────────────────

def test_deep_research_cancelled_before_start():
    """事件已置位 → deep_research 在 CP0 立即抛异常，不触发 LLM。"""
    event = threading.Event()
    event.set()
    with pytest.raises(ResearchCancelled):
        deep_research("测试课题", cancel_event=event)
