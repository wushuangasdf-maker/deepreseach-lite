"""
pytest 共享配置 — conftest.py

为所有测试提供统一的环境隔离。

职责：
  1. 隔离 logging_setup 的副作用：测试期间的 logger.error() 既不落盘、
     也不污染 error_records 收集器、更不打断 pytest 输出。
  2. 每个测试前后自动清理/还原，保证测试之间互不影响。

为什么需要：
  - core/logging_setup.py 的 FileHandler 会把 logger.error() 写入真实的
    logs/deepresearch.log，测试跑多了会污染生产日志。
  - _error_records 是模块级全局 list，跨测试累积会导致断言误判。
"""

import logging

import pytest

from core.logging_setup import _error_records


@pytest.fixture(autouse=True)
def _isolate_logging():
    """每个测试前后备份并还原 root logger，隔离日志副作用。"""
    root = logging.getLogger()

    # ── 备份当前状态 ──
    saved_handlers = list(root.handlers)
    saved_level = root.level

    # ── 测试前：清空收集器 + 移除所有 handler ──
    _error_records.clear()
    root.handlers.clear()
    # 禁用 propagation 到 lastResort，避免未配置时往 stderr 喷日志
    root.addHandler(logging.NullHandler())

    try:
        yield
    finally:
        # ── 测试后：还原 handler 与 level ──
        root.handlers.clear()
        root.handlers.extend(saved_handlers)
        root.setLevel(saved_level)
        _error_records.clear()
