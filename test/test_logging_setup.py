"""
日志配置测试 — test_logging_setup.py

覆盖 core/logging_setup.py 的 setup_logging / collect_error_summary /
_CollectingHandler。

conftest 的 _isolate_logging 自动隔离 root logger 并清理 _error_records，
测试无需手动还原。
"""

import logging

from core.logging_setup import (
    _CollectingHandler,
    _error_records,
    collect_error_summary,
    setup_logging,
)


def test_setup_logging_creates_dir_and_handlers(tmp_path):
    """setup_logging 创建日志目录、配置级别并挂载 handler。"""
    log_dir = tmp_path / "logs"
    setup_logging(str(log_dir))

    root = logging.getLogger()
    assert (log_dir / "deepresearch.log").exists()
    assert root.level == logging.WARNING
    assert any(isinstance(h, logging.FileHandler) for h in root.handlers)
    assert any(isinstance(h, _CollectingHandler) for h in root.handlers)


def test_collect_error_summary_empty():
    """无记录 → 返回空串。"""
    assert collect_error_summary() == ""


def test_collect_error_summary_with_records():
    """有记录 → 汇总含记录内容与日志路径。"""
    _error_records.append(
        logging.LogRecord("pkg", logging.ERROR, "path", 1, "出错了", None, None)
    )
    summary = collect_error_summary(log_path="/tmp/x.log")
    assert "出错了" in summary
    assert "/tmp/x.log" in summary


def test_collecting_handler_emit():
    """_CollectingHandler.emit 把记录收集进 _error_records。"""
    handler = _CollectingHandler()
    handler.emit(
        logging.LogRecord("pkg", logging.WARNING, "path", 1, "warn", None, None)
    )
    assert len(_error_records) == 1
    assert _error_records[-1].getMessage() == "warn"
