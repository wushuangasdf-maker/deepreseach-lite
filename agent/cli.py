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
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.agents import deep_research
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
        print("❌ 错误：研究主题不能为空。", file=sys.stderr)
        sys.exit(1)

    if len(question) < 4:
        print("❌ 错误：研究主题太短（至少 4 个字符）。", file=sys.stderr)
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
        print("\n\n⚠️  用户中断。已搜索的信息已丢失。", file=sys.stderr)
        sys.exit(130)  # 128 + SIGINT(2) = 130，Unix 约定
    except Exception as e:
        print(f"\n❌ 研究过程出错：{type(e).__name__}: {e}", file=sys.stderr)

        # 针对常见错误给出具体建议
        if "Connection" in str(e) or "Timeout" in str(e):
            print("   提示：检查网络连接和 API 服务状态。", file=sys.stderr)
        elif "API key" in str(e).lower() or "401" in str(e) or "403" in str(e):
            print("   提示：检查 .env 文件中的 API Key 是否正确。", file=sys.stderr)
        elif "quota" in str(e).lower() or "429" in str(e):
            print("   提示：API 配额可能已用完，请检查账户余额。", file=sys.stderr)

        sys.exit(1)

    # ── 输出最终结果 ──────────────────────────────────────
    if not args.quiet:
        print(f"\n{'=' * 60}")
        print(f"  {result}")
        print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
