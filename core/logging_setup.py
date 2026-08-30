"""
统一日志配置 — logging_setup.py

为 DeepResearch-Lite 提供统一的日志配置与错误汇总。

职责：
  1. setup_logging()：配置控制台 + 文件两个 handler，集中记录错误
  2. 收集运行时 WARNING/ERROR 记录，供运行结束时汇总展示

设计说明：
  - 库模块（core / tools / agent）只调用 logging.getLogger(__name__)，
    禁止自行配置，否则会出现重复 handler 与日志乱序。
  - 仅在入口（如 agent/cli.py 的 main）调用 setup_logging() 一次。

用法:
    from core.logging_setup import setup_logging, collect_error_summary

    setup_logging()
    ...  # 业务逻辑中的 logger.error(...) 会被记录
    print(collect_error_summary())   # 运行结束时汇总
"""
import logging
import os

# 本次运行收集到的 WARNING 及以上记录（供结束时汇总）
_error_records: list[logging.LogRecord] = []


class _CollectingHandler(logging.Handler):
    """静默收集 WARNING 及以上级别的记录，不额外输出。"""

    def emit(self, record: logging.LogRecord) -> None:
        _error_records.append(record)


def setup_logging(log_dir: str = "logs") -> None:
    """
    配置根 logger，输出到控制台（stderr）与文件 logs/deepresearch.log。

    只在入口调用一次。
    """
    os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.WARNING)  # 只记录 WARNING 及以上

    # 控制台：简洁格式，写到 stderr，避免污染 stdout 的进度输出
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(console)

    # 文件：完整格式（含时间戳/模块名），方便事后定位问题
    log_path = os.path.join(log_dir, "deepresearch.log")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(file_handler)

    # 收集：静默汇总，供运行结束时展示
    root.addHandler(_CollectingHandler())


def collect_error_summary(log_path: str = "logs/deepresearch.log") -> str:
    """
    返回本次运行收集到的错误汇总文本；无错误时返回空串。

    供入口在结束时调用，把散落在各模块的错误集中展示一次，
    并指出完整日志文件的位置。
    """
    if not _error_records:
        return ""

    lines = [f"本次运行共出现 {len(_error_records)} 条警告/错误："]
    for rec in _error_records:
        lines.append(f"  [{rec.levelname}] {rec.name}: {rec.getMessage()}")
    lines.append(f"完整日志见 {log_path}")
    return "\n".join(lines)
