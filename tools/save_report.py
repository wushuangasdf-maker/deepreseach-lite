import os
import sys
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOOL_NAME = "save_report_tool"
TOOL_DESCRIPTION = (
    "将撰写好的研究报告保存为本地 Markdown 文件（.md）。"
    "适用场景：研究报告定稿后需要持久化保存时、需要导出为文件供后续查阅时。"
    "不适用场景：仅需在对话中展示而不需要保存的报告。"
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "report": {
            "type": "string",
            "description": "研究报告的完整 Markdown 正文，由 LLM 生成。支持标题、列表、引用、代码块等标准 Markdown 语法。",
        },
        "title": {
            "type": "string",
            "description": "报告标题，用于生成文件名。例如 '2026年量子计算产业现状'。会自动去除非法字符并截断至合理长度。",
        },
        "output_dir": {
            "type": "string",
            "description": "输出目录的路径。默认为项目根目录下的 reports/。如果目录不存在会自动创建。",
            "default": "reports",
        },
    },
    "required": ["report", "title"],
}
# ── 公开工具函数 ──────────────────────────────
def save_report_tool(report,title,output_dir : str="reports",)->str:
      """
    将研究报告保存为 Markdown 文件，返回适合 LLM 阅读的结果描述。

    参数:
        report (str): 报告全文（Markdown 格式）。
        title (str): 报告标题，用于生成文件名。
        output_dir (str): 输出目录路径，默认为 "reports"。

    返回:
        str: 保存成功时返回文件路径，失败时返回自然语言错误提示。

    注意:
        本函数绝不抛出异常 —— 所有错误都被捕获并转为字符串返回，
        因为 LLM 只能处理文本。
    """
      if not report or not report.strip():
          return "错误：报告内容不能为空。"
      if not title or not title.strip():
          return "错误：报告标题不能为空。"
      title=title.strip()
      # 去除非法文件名字符
      report=report.strip()
      output_dir=output_dir.strip() or "reports"
  # ── 安全文件名生成 ─────────────────────────
      safe_title=re.sub(r'[\\/:*?\"<>/]',"-",title)
      safe_title=re.sub(r"[\s\-]+","-",safe_title)
      safe_title=safe_title[:80].strip("-")
      if not safe_title:
           return  (
            f"错误：标题「{title}」在去除特殊字符后为空。"
            f"请使用包含至少一个有效字符的标题。"
        )
       # 拼接时间戳，确保不会覆盖已有文件
      timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
      filename = f"{safe_title}_{timestamp}.md"
      os.makedirs(output_dir, exist_ok=True)
      filepath = os.path.join(output_dir, filename)
       # ── 写入文件 ─────────────────────────────────────────
      try:
          with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
      except OSError as e:
          return (
              f"写入文件失败（{type(e).__name__}）。"
              f"文件路径：{filepath}\n"
              f"详细信息：{e}。可能是磁盘空间不足或权限不足。"
          )
      except UnicodeEncodeError as e:
          return (
              f"编码错误（{type(e).__name__}）。"
              f"报告包含无法以 UTF-8 编码的字符。"
              f"详细信息：{e}。"
          )
  
      # ── 成功返回 ─────────────────────────────────────────
      file_size = os.path.getsize(filepath)
      size_hint = f"（{_format_size(file_size)}）"
  
      return (
        f"【报告已保存】\n"
          f"文件路径：{filepath}\n"
          f"文件大小：{size_hint}\n"
          f"标题：{title}\n"
          f"保存时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
      )  


def get_tool_schema() -> dict:
    """
    返回此工具的 OpenAI Function Calling 格式定义。

    Agent 调用此函数获取 schema 后，注入到 LLM 请求的 tools 参数中，
    LLM 即可了解此工具的能力并按需生成调用指令。

    返回:
        dict: 符合 OpenAI tools 格式的字典
    """
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": TOOL_DESCRIPTION,
            "parameters": TOOL_PARAMETERS,
        },
    }


# ── 内部实现 ─────────────────────────────────────────────────

def _format_size(size_bytes: int) -> str:
    """将字节数格式化为人类可读的大小字符串。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"