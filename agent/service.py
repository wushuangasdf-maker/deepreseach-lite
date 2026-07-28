"""
研究服务层 — 将 deep_research() 包装为异步任务服务。

设计要点：
  - ThreadPoolExecutor: 在独立线程中运行同步的 deep_research()
  - sys.stdout 重定向: 捕获 verbose 输出 → 供 SSE 实时推送
  - 内存任务表: 线程安全的 dict，最多保留 100 个任务
"""

import uuid
import time
import threading
import traceback
import io
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from agent.agents import deep_research


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ResearchTask:
    task_id: str
    topic: str
    depth: str
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""          # 完整的控制台输出 + 最终结果
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @property
    def elapsed(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)

    @property
    def log_lines(self) -> list[str]:
        """将 result 按行拆分，供 SSE 逐行推送"""
        return self.result.split("\n") if self.result else []


class ResearchService:
    """研究服务单例。线程安全。"""

    _max_tasks = 100

    def __init__(self, max_workers: int = 3):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, ResearchTask] = {}
        self._lock = threading.Lock()

    # ── 任务管理 ──────────────────────────────────────

    def create_task(self, topic: str, depth: str = "standard") -> ResearchTask:
        task = ResearchTask(
            task_id=uuid.uuid4().hex[:12],
            topic=topic,
            depth=depth,
        )
        with self._lock:
            self._tasks[task.task_id] = task
            # 超出上限时清理最旧的任务
            if len(self._tasks) > self._max_tasks:
                oldest = sorted(
                    self._tasks.keys(),
                    key=lambda tid: self._tasks[tid].created_at,
                )
                for tid in oldest[:len(self._tasks) - self._max_tasks]:
                    del self._tasks[tid]
        return task

    def get_task(self, task_id: str) -> Optional[ResearchTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[ResearchTask]:
        return sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )

    # ── 异步执行 ──────────────────────────────────────

    def _run_research(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        # 用 StringIO 捕获所有 verbose 输出
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured

        try:
            final = deep_research(
                topic=task.topic,
                depth=task.depth,
                verbose=True,
            )
            # 拼接：捕获的日志 + 最终返回值
            task.result = captured.getvalue()
            if final:
                task.result += f"\n{final}"
            task.status = TaskStatus.COMPLETED

        except Exception as e:
            task.result = captured.getvalue()
            task.result += f"\n{traceback.format_exc()}"
            task.error = f"{type(e).__name__}: {str(e)}"
            task.status = TaskStatus.FAILED

        finally:
            sys.stdout = old_stdout
            task.finished_at = time.time()

    def run_async(self, task_id: str) -> None:
        """提交到线程池，立即返回"""
        self._executor.submit(self._run_research, task_id)


# 全局单例
research_service = ResearchService()
