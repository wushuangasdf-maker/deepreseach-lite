"""
DeepResearch-Lite 命令行入口。

用法:
    python cli.py "量子计算对现有加密体系的冲击"
    python cli.py --depth quick "今天的天气"
    python cli.py --depth deep --output my_report.md "AI Agent 最新进展"

参数:
    question       研究主题（位置参数，必填）
    --depth        研究深度: quick | standard | deep（默认 standard）
                     quick:    只搜索一轮，快速出结果
                     standard: 两轮搜索 + 交叉验证（推荐）
                     deep:     三轮搜索，覆盖更全面
    --output       报告输出路径（默认 data/reports/<时间戳>.md）
    --verbose      显示详细的工具调用过程（默认开启，--quiet 关闭）
    --quiet        静默模式，只输出最终报告路径
"""
import argparse
import logging
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.agents import deep_research
from core.logging_setup import setup_logging, collect_error_summary

logger = logging.getLogger(__name__)


def _print_error_summary() -> None:
    """运行结束时，若有收集到的错误则汇总打印到 stderr。"""
    summary = collect_error_summary()
    if summary:
        print(f"\n{'=' * 60}\n{summary}\n{'=' * 60}", file=sys.stderr)
# ── 研究深度 → Agent 参数映射 ───────────────────────

# 不同深度对应不同的 max_turns 和 force_report_at
#   max_turns:      最大对话轮数（含报告撰写）
#   force_report_at: 在此轮数后追加"建议动笔"提示
#
# 设计思路：
#   - quick:   给 LLM 很小的时间窗口，强迫它快速收敛
#   - standard: 给 LLM 合理的搜索空间，但到第 4 轮开始催促
#   - deep:     给 LLM 更多搜索轮次，允许探索更多角度

DEPTH_CONFIG = {
    "quick": {
        "max_turns": 5,
        "force_report_at": 3,
    },
    "standard": {
        "max_turns": 12,
        "force_report_at": 8,
    },
    "deep": {
        "max_turns": 20,
        "force_report_at": 14,
    },
}
def main():
    """
    CLI 主入口。

    做的事：
    1. 解析命令行参数（argparse）
    2. 校验参数合法性
    3. 根据 --depth 选择 Agent 参数
    4. 调用 deep_research()
    5. 输出结果（报告路径或错误信息）
    """
    # ── 日志配置（错误统一走 logging 并落盘汇总）──
    setup_logging()

    # ── 参数解析 ─────────────────────────
    parser = argparse.ArgumentParser(
        description="DeepResearch-Lite 命令行入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
         示例:
         python cli.py "量子计算对银行业的冲击"
         python cli.py --depth quick "今天天气怎么样"
         python cli.py --depth deep --output 报告.md "2026年AI趋势"
            """,
          )
    parser.add_argument("question", type=str, help="研究主题（必填）")
    parser.add_argument("--depth",type=str,choices=["quick","standard","deep"],default="standard",
                        help="研究深度（默认 standard）。quick=一轮快搜，standard=两轮+交叉验证，deep=三轮深挖",)
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="报告输出路径。不指定则自动生成到 data/reports/ 目录",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式，不打印工具调用过程，只输出最后结果",
    )
    args=parser.parse_args()
     # ── 参数校验 ──────────────────────────────────────────
    question = args.question.strip()

    if not question:
        logger.error("研究主题不能为空。")
        _print_error_summary()
        sys.exit(1)

    if len(question) < 4:
        logger.error("研究主题太短（至少 4 个字符）。")
        _print_error_summary()
        sys.exit(1)
     # ── 获取深度配置 ──────────────────────────────────────
    config = DEPTH_CONFIG[args.depth]
    verbose = not args.quiet
     # ── 打印启动信息 ──────────────────────────────────────
    if not args.quiet:
        print(f"\n{'=' * 60}")
        print(f"  DeepResearch-Lite")
        print(f"  主题：{question}")
        print(f"  深度：{args.depth}（最多 {config['max_turns']} 轮）")
        print(f"{'=' * 60}\n")

    # ── 执行研究 ──────────────────────────────────────────
    try:
        result = deep_research(
            topic=question,
            depth=args.depth,
            max_turns=config["max_turns"],
            force_report_at=config["force_report_at"],
            verbose=verbose,
        )
    except KeyboardInterrupt:
        logger.warning("用户中断，已搜索的信息已丢失。")
        _print_error_summary()
        sys.exit(130)  # 128 + SIGINT(2) = 130，Unix 约定
    except Exception as e:
        # 针对常见错误给出具体建议
        hint = ""
        if "Connection" in str(e) or "Timeout" in str(e):
            hint = "检查网络连接和 API 服务状态。"
        elif "API key" in str(e).lower() or "401" in str(e) or "403" in str(e):
            hint = "检查 .env 文件中的 API Key 是否正确。"
        elif "quota" in str(e).lower() or "429" in str(e):
            hint = "API 配额可能已用完，请检查账户余额。"

        logger.error(
            "研究过程出错：%s: %s%s",
            type(e).__name__, e, f"（提示：{hint}）" if hint else "",
        )
        _print_error_summary()
        sys.exit(1)

    # ── 输出最终结果 ──────────────────────────────────────
    if not args.quiet:
        print(f"\n{'=' * 60}")
        print(f"  {result}")
        print(f"{'=' * 60}\n")

    # ── 错误汇总（若有）──────────────────────────────────
    _print_error_summary()


if __name__ == "__main__":
    main()
