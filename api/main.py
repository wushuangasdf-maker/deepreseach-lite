"""
FastAPI 路由 — 将 deep_research() 暴露为 HTTP 服务。
启动：
pip install fastapi uvicorn
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

端点一览：
  POST   /research                    创建并启动研究任务
  GET    /research                    列出最近的任务
  GET    /research/{task_id}          查询单个任务状态
  GET    /research/{task_id}/stream   SSE 实时进度流
  GET    /research/{task_id}/report   获取完整报告
  GET    /health                      健康检查
"""

import json
import asyncio

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from agent.service import research_service, TaskStatus, ResearchTask

# ── FastAPI 应用 ──────────────────────────────────────

app = FastAPI(
    title="DeepResearch-Lite API",
    description="深度研究 HTTP 服务 — 提交课题 → 异步执行 → 获取报告",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic 请求/响应模型 ───────────────────────────

class ResearchRequest(BaseModel):
    topic: str = Field(
        ..., min_length=4, max_length=500,
        description="研究课题，如「2026 年 AI 芯片市场格局」",
    )
    depth: str = Field(
        "standard",
        pattern="^(quick|standard|deep)$",
        description="研究深度：quick=单轮快搜，standard=两轮交叉验证，deep=三轮深挖",
    )


class TaskResponse(BaseModel):
    task_id: str
    status: str
    topic: str
    depth: str
    elapsed_seconds: Optional[float] = None
    result_preview: Optional[str] = None   # 末尾 500 字预览
    error: Optional[str] = None


class TaskListResponse(BaseModel):
    total: int
    tasks: list[TaskResponse]


def _to_response(t: ResearchTask) -> TaskResponse:
    preview = None
    if t.result:
        preview = t.result[-500:]
    return TaskResponse(
        task_id=t.task_id,
        status=t.status.value,
        topic=t.topic,
        depth=t.depth,
        elapsed_seconds=t.elapsed,
        result_preview=preview,
        error=t.error or None,
    )


# ── 路由 ─────────────────────────────────────────────

@app.post("/research", response_model=TaskResponse, status_code=201)
def create_research(req: ResearchRequest):
    """提交研究课题，立即返回 task_id，后台异步执行"""
    task = research_service.create_task(topic=req.topic, depth=req.depth)
    research_service.run_async(task.task_id)
    return _to_response(task)


@app.get("/research", response_model=TaskListResponse)
def list_tasks(limit: int = Query(20, ge=1, le=100)):
    """列出最近的研究任务（按时间倒序）"""
    all_tasks = research_service.list_tasks()
    tasks = [_to_response(t) for t in all_tasks[:limit]]
    return TaskListResponse(total=len(all_tasks), tasks=tasks)


@app.get("/research/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    """查询单个任务状态"""
    task = research_service.get_task(task_id)
    if task is None:
        raise HTTPException(404, detail=f"任务 {task_id} 不存在")
    return _to_response(task)


@app.get("/research/{task_id}/stream")
async def stream_task(task_id: str):
    """
    SSE 端点：实时推送研究进度。

    事件格式：
      {"type": "log", "content": "..."}   — 一行控制台输出
      {"type": "done", "status": "...", ...} — 研究完成
    """
    task = research_service.get_task(task_id)
    if task is None:
        raise HTTPException(404, detail=f"任务 {task_id} 不存在")

    async def event_generator():
        sent_count = 0

        # 轮询：等任务完成，期间推送新日志
        while task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            current_lines = task.log_lines
            new_lines = current_lines[sent_count:]
            for line in new_lines:
                yield f"data: {json.dumps({'type': 'log', 'content': line}, ensure_ascii=False)}\n\n"
            sent_count = len(current_lines)
            await asyncio.sleep(0.3)

        # 推送剩余日志 + 最终状态
        remaining = task.log_lines[sent_count:]
        for line in remaining:
            yield f"data: {json.dumps({'type': 'log', 'content': line}, ensure_ascii=False)}\n\n"

        final = {
            "type": "done",
            "status": task.status.value,
            "result": task.result[-3000:] if task.result else "",
            "error": task.error or None,
        }
        yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 禁用 nginx 缓冲
        },
    )


@app.get("/research/{task_id}/report")
def get_report(task_id: str):
    """获取完整研究输出（纯文本）"""
    task = research_service.get_task(task_id)
    if task is None:
        raise HTTPException(404, detail=f"任务 {task_id} 不存在")
    if task.status == TaskStatus.PENDING:
        raise HTTPException(202, detail="任务尚未开始")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(202, detail="任务执行中，可通过 /stream 查看进度")
    if task.status == TaskStatus.FAILED:
        raise HTTPException(500, detail=task.error)
    return {
        "task_id": task.task_id,
        "topic": task.topic,
        "depth": task.depth,
        "report": task.result,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "DeepResearch-Lite"}
