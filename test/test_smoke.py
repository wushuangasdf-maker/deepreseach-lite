"""
冒烟测试 — 验证测试环境搭建正确。

用途：
  1. 证明 pytest 能正常跑通（配置、导入路径、coverage 均生效）
  2. 证明 core/tools 模块可从项目根直接导入

这不是业务测试，只是环境自检。
"""

from core.bocha_search import build_context
from core.source_ranker import rank_sources
from tools.save_report import save_report_tool


def test_pytest_runs():
    """pytest 框架本身能运行。"""
    assert True


def test_core_modules_importable():
    """core 与 tools 的公开函数可从项目根导入（pythonpath=. 生效）。"""
    assert callable(build_context)
    assert callable(rank_sources)
    assert callable(save_report_tool)
