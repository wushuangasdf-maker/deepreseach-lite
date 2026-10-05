"""
取消服务层测试 — test_service_cancel.py

覆盖 agent/service.py 的 cancel_task 与 _run_research 取消分支。

特点：
  - 每个测试用独立的 ResearchService 实例，避免共享状态。
  - 不真正跑 deep_research（用 monkeypatch 替换或直接验证状态迁移）。
"""

import pytest

from agent.service import ResearchService, TaskStatus
from agent.agents import ResearchCancelled


@pytest.fixture
def service():
    return ResearchService(max_workers=1)


# ── cancel_task 返回值与状态迁移 ───────────────────────

def test_cancel_pending(service):
    t = service.create_task("测试课题", "quick")
    assert service.cancel_task(t.task_id) is True
    assert t.status == TaskStatus.CANCELLED
    assert t.cancel_event.is_set()


def test_cancel_terminal_returns_false(service):
    t = service.create_task("测试课题", "quick")
    t.status = TaskStatus.COMPLETED
    assert service.cancel_task(t.task_id) is False


def test_cancel_missing_returns_none(service):
    assert service.cancel_task("nonexistent") is None


def test_cancel_running_sets_event(service):
    t = service.create_task("测试课题", "standard")
    t.status = TaskStatus.RUNNING
    assert service.cancel_task(t.task_id) is True
    assert t.cancel_event.is_set()
    # 状态保持 RUNNING，由 worker 在检查点转 CANCELLED
    assert t.status == TaskStatus.RUNNING


# ── _run_research 取消分支 ─────────────────────────────

def test_run_research_cancelled_before_start(service):
    """排队期已被取消 → 直接标记 CANCELLED，不启动。"""
    t = service.create_task("测试课题", "standard")
    t.cancel_event.set()
    service._run_research(t.task_id)
    assert t.status == TaskStatus.CANCELLED
    assert "启动前被取消" in t.result


def test_run_research_catches_cancelled(service, monkeypatch):
    """deep_research 抛出 ResearchCancelled → 标记 CANCELLED。"""
    def fake_deep_research(**kwargs):
        raise ResearchCancelled()

    monkeypatch.setattr("agent.service.deep_research", fake_deep_research)
    t = service.create_task("测试课题", "standard")
    service._run_research(t.task_id)
    assert t.status == TaskStatus.CANCELLED
    assert "[任务已取消]" in t.result
