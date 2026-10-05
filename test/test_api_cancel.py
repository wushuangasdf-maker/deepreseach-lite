"""
取消 API 端点测试 — test_api_cancel.py

覆盖 api/main.py 的 DELETE /research/{task_id} 返回码。

特点：
  - 用 FastAPI TestClient 直测路由，不真正启动服务。
  - 复用全局 research_service，每个测试创建独立任务。
"""

from fastapi.testclient import TestClient

from agent.service import research_service, TaskStatus
from api.main import app


client = TestClient(app)


def test_delete_missing_returns_404():
    resp = client.delete("/research/nonexistent")
    assert resp.status_code == 404


def test_delete_pending_returns_200():
    task = research_service.create_task("测试课题", "quick")
    resp = client.delete(f"/research/{task.task_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_delete_completed_returns_409():
    task = research_service.create_task("测试课题", "quick")
    task.status = TaskStatus.COMPLETED
    resp = client.delete(f"/research/{task.task_id}")
    assert resp.status_code == 409


def test_delete_running_returns_202():
    task = research_service.create_task("测试课题", "standard")
    task.status = TaskStatus.RUNNING
    resp = client.delete(f"/research/{task.task_id}")
    assert resp.status_code == 202
    assert task.cancel_event.is_set()
