"""
API 端点测试 — test_api.py

覆盖 api/main.py 的 POST /research、GET /research（列表/单条）、
/research/{id}/report、/health、SSE stream（已完成态）。

特点：
  - 用 FastAPI TestClient 直测路由，不真正启动服务。
  - POST 端点 mock 掉 run_async，避免后台线程真跑 deep_research。
"""

from fastapi.testclient import TestClient

from agent.service import research_service, TaskStatus
from api.main import app


client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_research(monkeypatch):
    """POST 提交课题 → 201，返回 task_id 与状态。"""
    monkeypatch.setattr(research_service, "run_async", lambda tid: None)
    resp = client.post("/research", json={"topic": "测试研究课题", "depth": "quick"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["topic"] == "测试研究课题"
    assert body["depth"] == "quick"
    assert body["status"] == "pending"
    assert body["task_id"]


def test_create_research_invalid_depth():
    """非法 depth → 422（pydantic 校验）。"""
    resp = client.post("/research", json={"topic": "测试研究课题", "depth": "bad"})
    assert resp.status_code == 422


def test_list_tasks():
    """列出任务 → 返回 total 与 tasks。"""
    research_service.create_task("测试课题", "standard")
    resp = client.get("/research")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_list_tasks_with_preview():
    """带 result 的任务 → 返回 result_preview。"""
    task = research_service.create_task("测试课题", "quick")
    task.result = "报告内容" * 200  # 触发 preview 截取
    resp = client.get("/research")
    assert resp.status_code == 200
    previews = [t["result_preview"] for t in resp.json()["tasks"]]
    assert any(p is not None for p in previews)


def test_get_task():
    """查询单任务 → 返回其字段。"""
    task = research_service.create_task("测试课题", "quick")
    resp = client.get(f"/research/{task.task_id}")
    assert resp.status_code == 200
    assert resp.json()["topic"] == "测试课题"


def test_get_task_404():
    """查询不存在任务 → 404。"""
    resp = client.get("/research/nonexistent")
    assert resp.status_code == 404


def test_get_report_pending_202():
    """PENDING 状态取报告 → 202。"""
    task = research_service.create_task("测试课题", "quick")
    resp = client.get(f"/research/{task.task_id}/report")
    assert resp.status_code == 202


def test_get_report_completed():
    """COMPLETED 状态取报告 → 200 含 report。"""
    task = research_service.create_task("测试课题", "quick")
    task.status = TaskStatus.COMPLETED
    task.result = "完整报告内容"
    resp = client.get(f"/research/{task.task_id}/report")
    assert resp.status_code == 200
    assert resp.json()["report"] == "完整报告内容"


def test_get_report_failed_500():
    """FAILED 状态取报告 → 500 含错误。"""
    task = research_service.create_task("测试课题", "quick")
    task.status = TaskStatus.FAILED
    task.error = "出错了"
    resp = client.get(f"/research/{task.task_id}/report")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "出错了"


def test_stream_completed():
    """SSE：已完成任务 → 返回日志行与 done 事件。"""
    task = research_service.create_task("测试课题", "quick")
    task.status = TaskStatus.COMPLETED
    task.result = "第一行\n第二行"
    resp = client.get(f"/research/{task.task_id}/stream")
    assert resp.status_code == 200
    assert "data: " in resp.text
    assert "done" in resp.text
