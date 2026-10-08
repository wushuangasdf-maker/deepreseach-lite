"""
CLI 入口测试 — test_cli.py

覆盖 agent/cli.py 的 main()：参数解析、校验、--depth/--output 映射与异常分支。

特点：
  - monkeypatch sys.argv 模拟命令行，monkeypatch deep_research / setup_logging /
    collect_error_summary，不真跑研究、不落日志。
  - 错误路径用 pytest.raises(SystemExit) 断言退出码。
"""

import sys

import pytest

import agent.cli as cli


@pytest.fixture
def _patch_cli(monkeypatch):
    """隔离副作用并记录 deep_research 收到的参数。"""
    monkeypatch.setattr(cli, "setup_logging", lambda **kw: None)
    monkeypatch.setattr(cli, "collect_error_summary", lambda: "")

    calls = []

    def fake_deep_research(**kwargs):
        calls.append(kwargs)
        return "报告已成功生成并保存。"

    monkeypatch.setattr(cli, "deep_research", fake_deep_research)

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["cli.py", *argv])
        cli.main()

    run.calls = calls
    return run


# ── 正常路径 ─────────────────────────────────────────────

def test_happy_path_defaults(_patch_cli, capsys):
    """默认参数：standard 深度、无 output_dir、verbose 开启。"""
    _patch_cli("AI芯片市场研究")
    kw = _patch_cli.calls[-1]
    assert kw["topic"] == "AI芯片市场研究"
    assert kw["depth"] == "standard"
    assert kw["max_turns"] == 12
    assert kw["force_report_at"] == 8
    assert kw["verbose"] is True
    assert kw["output_dir"] is None
    assert "报告已成功生成并保存" in capsys.readouterr().out


def test_happy_path_output_dir(_patch_cli):
    """--output 作为输出目录透传给 deep_research，depth 映射正确。"""
    _patch_cli("--depth", "deep", "--output", "my_reports", "AI芯片市场研究")
    kw = _patch_cli.calls[-1]
    assert kw["depth"] == "deep"
    assert kw["max_turns"] == 20
    assert kw["force_report_at"] == 14
    assert kw["output_dir"] == "my_reports"


def test_quiet_mode(_patch_cli):
    """--quiet 关闭 verbose。"""
    _patch_cli("--quiet", "AI芯片市场研究")
    assert _patch_cli.calls[-1]["verbose"] is False


# ── 参数校验 ─────────────────────────────────────────────

def test_empty_question(_patch_cli):
    """纯空白主题 → 退出码 1。"""
    with pytest.raises(SystemExit) as e:
        _patch_cli("   ")
    assert e.value.code == 1


def test_short_question(_patch_cli):
    """主题 < 4 字符 → 退出码 1。"""
    with pytest.raises(SystemExit) as e:
        _patch_cli("abc")
    assert e.value.code == 1


def test_invalid_depth(_patch_cli):
    """非法 --depth → argparse 报错退出码 2。"""
    with pytest.raises(SystemExit) as e:
        _patch_cli("--depth", "invalid", "AI芯片市场研究")
    assert e.value.code == 2


# ── 异常分支 ─────────────────────────────────────────────

def test_keyboard_interrupt(_patch_cli, monkeypatch):
    """研究被 Ctrl-C 中断 → 退出码 130。"""
    def boom(**kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli, "deep_research", boom)
    with pytest.raises(SystemExit) as e:
        _patch_cli("AI芯片市场研究")
    assert e.value.code == 130


def test_generic_exception(_patch_cli, monkeypatch):
    """研究抛普通异常 → 退出码 1。"""
    def boom(**kwargs):
        raise RuntimeError("Connection timeout")

    monkeypatch.setattr(cli, "deep_research", boom)
    with pytest.raises(SystemExit) as e:
        _patch_cli("AI芯片市场研究")
    assert e.value.code == 1
