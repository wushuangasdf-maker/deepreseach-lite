"""
报告保存工具测试 — test_save_report.py

覆盖 tools/save_report.py 的 save_report_tool 与 _format_size。

特点：
  - 落盘用例用 pytest 内置 tmp_path，不碰真实 reports/ 目录。
  - 时间戳用 monkeypatch 固定（方式 A），文件名可精确断言。
"""

from datetime import datetime

from tools.save_report import _format_size, save_report_tool


# ── 时间戳 mock 辅助 ──────────────────────────────────────

class _FakeDateTime(datetime):
    """固定 now() 返回，使文件名中的时间戳可预测。"""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 8, 27, 12, 0, 0)


# ── save_report_tool ──────────────────────────────────────

def test_save_report_empty_report():
    """report 为空 → 返回错误提示。"""
    result = save_report_tool("", "标题")
    assert "报告内容不能为空" in result


def test_save_report_empty_title():
    """title 为空 → 返回错误提示。"""
    result = save_report_tool("内容", "")
    assert "报告标题不能为空" in result


def test_save_report_sanitize_illegal_chars(monkeypatch, tmp_path):
    """标题中的非法文件名字符被替换为连字符。"""
    monkeypatch.setattr("tools.save_report.datetime", _FakeDateTime)
    result = save_report_tool("正文", "报告:第*一?版", output_dir=str(tmp_path))
    assert "报告已保存" in result
    # 非法字符 : * ? 均被替换为 -，且空格保留（此处标题无空格）
    assert "报告-第-一-版_20260827_120000.md" in result


def test_save_report_title_all_special_chars():
    """标题清洗后为空 → 返回错误提示。"""
    result = save_report_tool("正文", "***")
    assert "去除特殊字符后为空" in result


def test_save_report_success(monkeypatch, tmp_path):
    """正常保存：文件存在、内容正确、文件名含固定时间戳。"""
    monkeypatch.setattr("tools.save_report.datetime", _FakeDateTime)
    output_dir = tmp_path / "reports"
    report = "# 标题\n\n这是报告正文。"

    result = save_report_tool(report, "测试报告", output_dir=str(output_dir))

    assert "报告已保存" in result
    filename = "测试报告_20260827_120000.md"
    filepath = output_dir / filename
    assert filepath.exists()
    assert filepath.read_text(encoding="utf-8") == report


# ── _format_size ──────────────────────────────────────────

def test_format_size_bytes():
    """小于 1024 → 以 B 显示。"""
    assert _format_size(0) == "0 B"
    assert _format_size(1023) == "1023 B"


def test_format_size_kilobytes():
    """1024 ~ 1024*1024-1 → 以 KB 显示，保留一位小数。"""
    assert _format_size(1024) == "1.0 KB"
    assert _format_size(1536) == "1.5 KB"


def test_format_size_megabytes():
    """大于等于 1024*1024 → 以 MB 显示。"""
    assert _format_size(3 * 1024 * 1024) == "3.0 MB"
