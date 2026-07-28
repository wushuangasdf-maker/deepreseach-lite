"""
深度研究 Agent — agents.py

编排 LLM、工具和提示词，实现多轮自主研究循环，最终产出研究报告。

核心职责：
  1. 消息管理：构建并维护完整的对话上下文（system / user / assistant / tool）
  2. 工具循环：检测 LLM 的 tool_calls → 执行工具 → 回填结果 → 继续对话
  3. 阶段切换：研究阶段 → 报告阶段（含轮数超时保护）
  4. 容错处理：JSON 解析失败、工具执行异常、LLM 调用失败等边缘情况

不包含的职责：
  - 领域逻辑（在 prompts/ 中）
  - 工具实现（在 tools/ 中）
  - LLM 接口（在 core/llm.py 中）

用法:
    from agent.agents import deep_research
    result = deep_research("2026 年 AI 芯片市场格局", verbose=True)

    # 或直接从命令行运行
    python agent/agents.py
"""

import json
import sys
import os
import re

# 确保项目根目录在 sys.path 中，方便直接从命令行运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.llm import get_llm_client
from agent.prompts.system import build_system_prompt
from agent.prompts.tools import build_tools_prompt
from agent.prompts.report import build_report_prompt
from tools.web_search import web_search_tool, get_tool_schema as web_search_schema
from tools.fetch_page import fetch_page_tool, get_tool_schema as fetch_page_schema
from tools.kb_search import kb_search_tool, get_tool_schema as kb_search_schema
from tools.save_report import save_report_tool, get_tool_schema as save_report_schema
from agent.prompts.plan import build_plan_prompt, parse_plan_result

# ── 工具注册表 ─────────────────────────────────────────────────
# 每项为 (可调用函数, schema 获取函数)。
# 新增工具只需在此追加一行，agent 循环会自动感知。

_TOOL_REGISTRY = [
    (web_search_tool,  web_search_schema),
    (fetch_page_tool,  fetch_page_schema),
    (kb_search_tool,   kb_search_schema),
    (save_report_tool, save_report_schema),
]


def _build_tool_schemas() -> list[dict]:
    """构建 OpenAI Function Calling 格式的 tools 数组。"""
    return [schema_fn() for _, schema_fn in _TOOL_REGISTRY]


def _build_tool_map() -> dict:
    """构建 tool_name → tool_function 的映射表。"""
    tool_map = {}
    for func, schema_fn in _TOOL_REGISTRY:
        schema = schema_fn()
        name = schema["function"]["name"]
        tool_map[name] = func
    return tool_map


def _execute_tool(name: str, args: dict, tool_map: dict) -> str:
    """
    执行单个工具调用。

    所有工具本身已保证不抛异常，此处再加一层防御，
    处理未知工具名和参数绑定失败等边缘情况。

    返回:
        str: 工具执行结果字符串（成功或错误描述）。
    """
    if name not in tool_map:
        available = ", ".join(tool_map.keys())
        return f"错误：未找到工具「{name}」。当前可用工具：{available}"

    func = tool_map[name]
    try:
        return func(**args)
    except TypeError as e:
        return (
            f"工具「{name}」参数错误：{e}\n"
            f"传入参数：{json.dumps(args, ensure_ascii=False)}\n"
            f"请检查参数名称和类型是否正确，修正后重试。"
        )
    except Exception as e:
        return f"工具「{name}」执行异常（{type(e).__name__}）：{e}"


# ── 评分提取 ──────────────────────────────────────────────────


def _extract_highest_score(text: str) -> int:
    """
    从搜索结果文本中提取最高来源评分。

    搜索结果经 source_ranker 处理后，每条带有 [XX分] 标签，
    此函数提取所有分数并返回最高值。

    参数:
        text (str): web_search_tool 返回的文本

    返回:
        int: 最高评分（0~100），未找到评分时返回 0
    """
    scores = re.findall(r'\[(\d+)分', text)
    if not scores:
        return 0
    return max(int(s) for s in scores)


# ── 单轮执行 ──────────────────────────────────────────────────


def _run_single_turn(
    messages: list[dict],
    tool_schemas: list[dict],
    tool_map: dict,
    client,
    verbose: bool = True,
) -> dict:
    """
    执行单轮 ReAct 循环：调用 LLM → 处理响应 → 执行工具 → 回填结果。

    从主循环中抽取出来，使子问题循环和报告阶段都能复用。

    参数:
        messages:      对话历史（会原地修改）
        tool_schemas:  OpenAI tools 格式列表
        tool_map:      tool_name → 可调用函数的映射
        client:        LLM 客户端实例
        verbose:       是否打印详细信息

    返回:
        dict: {
            "type":          "tool_calls" | "text" | "error"
            "tool_names":    list[str],   本轮调用的工具名列表
            "content":       str,          LLM 的文本输出（如有）
            "source_delta":  int,          本轮新抓取的页面数
            "highest_score": int,          搜索结果中的最高评分
            "report_saved":  bool,         是否调用了 save_report_tool
        }
    """
    result = {
        "type": "error",
        "tool_names": [],
        "content": "",
        "source_delta": 0,
        "highest_score": 0,
        "report_saved": False,
    }

    # ── 调用 LLM ─────────────────────────────────────────────
    try:
        response = client.client.chat.completions.create(
            model=client.model,
            messages=messages,
            tools=tool_schemas,
        )
    except Exception as e:
        error_text = f"LLM API 调用失败（{type(e).__name__}）：{e}"
        if verbose:
            print(f"  ❌ {error_text}")
        messages.append({
            "role": "user",
            "content": (
                f"上一轮 API 调用发生错误：{error_text}\n"
                f"请根据已有信息继续任务，不要重复刚才失败的操作。"
            ),
        })
        result["type"] = "error"
        result["content"] = error_text
        return result

    choice = response.choices[0]
    message = choice.message

    # ── 情况 A：LLM 返回 tool_calls ──────────────────────────
    if message.tool_calls:
        result["type"] = "tool_calls"
        tc_names = [tc.function.name for tc in message.tool_calls]
        result["tool_names"] = tc_names

        # 序列化并追加 assistant 消息
        serialized = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": serialized,
        })

        # 逐个执行工具
        for tc in message.tool_calls:
            tool_name = tc.function.name

            # JSON 参数解析
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                error_msg = (
                    f"工具调用参数 JSON 解析失败：{e}\n"
                    f"原始参数：{tc.function.arguments}\n"
                    f"请修正为合法 JSON 后重试。"
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": error_msg,
                })
                if verbose:
                    print(f"  ❌ {tool_name} → JSON 解析失败")
                continue

            # 统计
            if tool_name == "fetch_page_tool":
                result["source_delta"] += 1

            if tool_name == "save_report_tool":
                result["report_saved"] = True

            # verbose：打印调用信息
            if verbose:
                args_preview = json.dumps(tool_args, ensure_ascii=False)
                if len(args_preview) > 100:
                    args_preview = args_preview[:97] + "..."
                print(f"  🔧 {tool_name}({args_preview})")

            # 执行工具
            tool_result = _execute_tool(tool_name, tool_args, tool_map)

            # 从搜索结果中提取最高评分
            if tool_name == "web_search_tool":
                score = _extract_highest_score(tool_result)
                result["highest_score"] = max(result["highest_score"], score)

            # verbose：打印结果摘要
            if verbose:
                preview = tool_result[:150].replace("\n", " ")
                if len(tool_result) > 150:
                    preview += "..."
                print(f"     ↳ {preview}")

            # 回填 tool 结果到消息历史
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })

        return result

    # ── 情况 B：LLM 返回纯文本 ────────────────────────────────
    content = message.content or ""
    messages.append({"role": "assistant", "content": content})
    result["type"] = "text"
    result["content"] = content

    if verbose:
        preview = content[:200].replace("\n", " ")
        if len(content) > 200:
            preview += "..."
        print(f"  💬 {preview}")

    return result

# ── 汇总辅助 ──────────────────────────────────────────────────


def _summarize_findings(
    messages: list[dict],
    client,
    label: str = "当前批次",
    verbose: bool = True,
) -> str:
    """
    让 LLM 对当前对话中的研究发现进行简要总结。

    这次调用不带 tools —— 强制 LLM 只做总结，不发起搜索。

    参数:
        messages: 对话历史（总结结果会追加为 user 消息）
        client:   LLM 客户端
        label:    总结标签（如「批次 1」「全部子问题」）
        verbose:  是否打印

    返回:
        str: 总结文本（也为空字符串兜底）
    """
    summary_prompt = (
        f"【{label}研究完毕，请做简要总结】\n"
        f"请回顾以上研究发现，用 3-5 句话总结关键信息：\n"
        f"1. 核心发现（数据、趋势、结论）\n"
        f"2. 重要来源（名称 + URL）\n"
        f"3. 信息缺口（哪些方面还未覆盖）\n\n"
        f"只输出总结，不要发起搜索或抓取。"
    )

    messages.append({"role": "user", "content": summary_prompt})

    if verbose:
        print(f"  📋 正在生成{label}总结...")

    try:
        # 不带 tools —— 强制纯文本总结
        response = client.client.chat.completions.create(
            model=client.model,
            messages=messages,
        )
        summary = response.choices[0].message.content or ""
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 总结失败（{type(e).__name__}），跳过")
        summary = ""

    # 将总结作为 assistant 消息追加（保留在上下文）
    messages.append({
        "role": "assistant",
        "content": summary or f"（{label}总结生成失败）",
    })

    if verbose and summary:
        preview = summary[:200].replace("\n", " ")
        if len(summary) > 200:
            preview += "..."
        print(f"     ↳ {preview}")

    return summary


# ── 渐进式摘要（方案A）────────────────────────────────────────────

# deepseek-chat 上下文窗口 64K，用量超 70% 或子问题超阈值时触发压缩
_CONTEXT_WINDOW = 64000
_BUDGET_RATIO = 0.7
_SUMMARIZE_THRESHOLD = 5


def _estimate_tokens(messages: list[dict]) -> int:
    """
    估算 messages 列表的总 token 数（粗略值，用于溢出判断）。

    使用字符数 / 2.5 的简单启发式（中英文混合场景下误差约 ±15%，
    足以判断是否接近上下文窗口上限）。

    参数:
        messages: 对话历史列表

    返回:
        int: 估算的 token 数
    """
    total_chars = 0
    for m in messages:
        total_chars += len(json.dumps(m, ensure_ascii=False))
    return int(total_chars / 2.5)


def _build_research_notes(notes: list[dict], topic: str) -> str:
    """
    将累积的子问题摘要格式化为一条「研究笔记」消息。

    参数:
        notes: 已完成子问题的摘要列表，每项含 desc 和 summary
        topic: 原始研究课题

    返回:
        str: Markdown 格式的研究笔记文本
    """
    lines = [
        "## 研究笔记（已完成子问题的摘要）",
        "",
        f"原始课题：{topic}",
        "",
    ]
    for i, note in enumerate(notes, 1):
        lines.append(f"### 子问题{i}：{note['desc']}")
        lines.append(note.get("summary", "（总结生成失败）"))
        lines.append("")

    lines.append(
        "---\n"
        "以上是已完成子问题的研究摘要。研究新的子问题时，"
        "如果相关信息已在笔记中，可跳过重复搜索直接引用。"
    )
    return "\n".join(lines)


def _compress_current_sub_question(
    sq: dict,
    messages: list[dict],
    client,
    research_notes: list[dict],
    preamble_end_index: int,
    topic: str,
    verbose: bool = True,
) -> None:
    """
    压缩当前子问题的研究成果：总结 → 存入笔记 → 裁剪消息 → 重建笔记。

    这是渐进式摘要（方案A）的核心编排函数，每个子问题完成后调用一次。

    步骤：
      1. 调用 _summarize_sub_question() 获得当前子问题的摘要
      2. 将摘要追加到 research_notes 列表
      3. 裁剪 messages：保留前导部分（0..preamble_end_index），删除其余
      4. 将更新后的研究笔记作为一条 user 消息重新注入 messages

    参数:
        sq:                 当前子问题 {"desc": ..., "search_kw": ...}
        messages:           对话历史（会被原地修改）
        client:             LLM 客户端
        research_notes:     研究笔记累积列表（会被原地修改）
        preamble_end_index: 前导消息的结束索引
        topic:              原始研究课题
        verbose:            是否打印详情
    """
    # Step 1: 总结当前子问题
    summary = _summarize_sub_question(
        sq_desc=sq["desc"],
        messages=messages,
        client=client,
        verbose=verbose,
    )

    # Step 2: 追加到研究笔记
    research_notes.append({
        "desc": sq["desc"],
        "summary": summary,
    })

    # Step 3: 裁剪 messages —— 仅保留前导消息
    del messages[preamble_end_index + 1:]

    # Step 4: 重新注入研究笔记
    notes_text = _build_research_notes(research_notes, topic)
    messages.append({"role": "user", "content": notes_text})

    if verbose:
        print(f"  📋 子问题已压缩（研究笔记累计 {len(research_notes)} 条，"
              f"上下文约 {_estimate_tokens(messages)} tokens）")


def _summarize_sub_question(
    sq_desc: str,
    messages: list[dict],
    client,
    verbose: bool = True,
) -> str:
    """
    对当前子问题的研究发现做简要总结。

    与 _summarize_findings 的区别：
      - 向 messages 末尾临时追加总结指令和 LLM 回复
      - 调用方随后会裁剪 messages，所以这里的副作用是设计内的
      - 返回纯文本摘要

    参数:
        sq_desc:  子问题描述
        messages: 对话历史（会被原地追加 2 条消息）
        client:   LLM 客户端
        verbose:  是否打印

    返回:
        str: 摘要文本，失败时返回空字符串
    """
    summary_prompt = (
        f"【子问题「{sq_desc}」研究完毕，请做简要总结】\n"
        f"请回顾刚才对该子问题的研究发现，用 3-5 句话总结：\n"
        f"1. 核心发现（关键数据、趋势、结论）\n"
        f"2. 重要来源（名称 + URL，不要省略链接）\n"
        f"3. 信息缺口（本子问题未覆盖的方面）\n\n"
        f"只输出总结，不要发起搜索或抓取。"
    )

    messages.append({"role": "user", "content": summary_prompt})

    if verbose:
        print(f"  📋 正在压缩子问题「{sq_desc}」...")

    try:
        response = client.client.chat.completions.create(
            model=client.model,
            messages=messages,
        )
        summary = response.choices[0].message.content or ""
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 子问题总结失败（{type(e).__name__}），使用原始内容摘要")
        summary = f"（总结失败：{e}）"

    messages.append({
        "role": "assistant",
        "content": summary or f"（子问题「{sq_desc}」总结生成失败）",
    })

    if verbose and summary:
        preview = summary[:200].replace("\n", " ")
        if len(summary) > 200:
            preview += "..."
        print(f"     ↳ {preview}")

    return summary


# ── 主循环 ─────────────────────────────────────────────────────


def deep_research(
    topic: str,
    max_turns: int = 12,
    force_report_at: int = 8,
    verbose: bool = True,
    depth: str = "standard",
) -> str:
    """
    执行深度研究并返回结果摘要。

    流程:
      1. 构建 system prompt（角色 + 工具 + 研究流程 + 行为准则）
      2. 进入研究循环：LLM 自由使用搜索/抓取工具搜集信息
      3. 信息充足（或超时）后，注入报告撰写指令
      4. LLM 撰写报告并调用 save_report_tool 保存

    参数:
        topic:           研究课题，如 "2026 年 AI 芯片市场格局"
        max_turns:       最大对话轮数（含报告阶段），默认 12
        force_report_at: 在此轮数后开始建议 LLM 进入撰写阶段，默认 8
        verbose:         是否实时打印每个 tool call 和 LLM 响应

    返回:
        str: 研究完成的最终状态描述
    """
    # ── 初始化 ─────────────────────────────────────────────────
    tool_schemas = _build_tool_schemas()
    tool_map = _build_tool_map()
    tool_names = list(tool_map.keys())

    # 拼接完整系统提示词：角色/流程 + 工具使用策略
    full_system_prompt = (
        build_system_prompt(tool_schemas,depth=depth)
        + "\n\n"
        + build_tools_prompt()
    )

    messages: list[dict] = [
        {"role": "system", "content": full_system_prompt},
        {"role": "user",   "content": topic},
    ]

    client = get_llm_client(provider="deepseek")

    # 状态变量
    source_count = 0        # 已成功抓取的页面数（供报告阶段统计）
    report_phase = False    # 是否已进入报告阶段
    hint_given = False      # 是否已发出"建议动笔"提示

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"🔍  深度研究开始")
        print(f"📋  课题：{topic}")
        print(f"🔧  可用工具：{tool_names}")
        print(f"📐  最大 {max_turns} 轮，第 {force_report_at} 轮后建议撰写报告")
        print(f"{'=' * 60}\n")
    # ── 阶段 0：任务拆解 ──────────────────────────────────────
    # 在开始搜索之前，先让 LLM 拆解课题为子问题。
    # 这次调用不带 tools —— 强制 LLM 停留在思考模式。
    
    plan_prompt = build_plan_prompt(topic, depth=depth)
    messages.append({"role": "user", "content": plan_prompt})

    if verbose:
        print("🧠  规划阶段：正在拆解研究课题...")

    sub_questions: list[dict] = []

    try:
        # 不带 tools 参数 → LLM 只能输出文本，不能调用工具
        plan_response = client.client.chat.completions.create(
            model=client.model,
            messages=messages,
            # 注意：没有 tools=tool_schemas
        )
        plan_text = plan_response.choices[0].message.content or ""

        if verbose:
            preview = plan_text[:300].replace("\n", " ")
            print(f"📋  规划结果：{preview}...")

        # 解析子问题列表
        sub_questions = parse_plan_result(plan_text)

    except Exception as e:
        if verbose:
            print(f"⚠️  规划失败（{type(e).__name__}: {e}），降级为不拆解模式")
        # 降级：整个课题作为一个子问题
        sub_questions = parse_plan_result("")

    # 将规划结果作为 assistant 消息加入（保留上下文）
    plan_text_final = (
        plan_text if 'plan_text' in dir()
        else f"将研究课题「{topic}」作为整体进行研究。"
    )
    messages.append({
        "role": "assistant",
        "content": plan_text_final,
    })

    # ── 渐进式摘要（方案A）初始化 ─────────────────────────────
    # 研究笔记：累积每个已完成子问题的摘要，格式 [{"desc": ..., "summary": ...}]
    research_notes: list[dict] = []

    # 锚点索引：前导消息的结束位置（system + topic + plan_prompt + plan_response）
    # messages[0 .. preamble_end_index] 永久保留，之后的内容可被裁剪
    preamble_end_index = len(messages) - 1

    # 是否启用渐进式摘要（子问题数超阈值 或 后续可能接近上下文窗口）
    should_summarize = (
        len(sub_questions) > _SUMMARIZE_THRESHOLD
    )

    # 动态重新计算 max_turns：
    # 规划(1) + 子问题数×(2轮研究 + 可选1轮总结) + 汇总(1) + 报告(2) + 缓冲(1)
    extra_per_sq = 1 if should_summarize else 0
    calculated_turns = 1 + len(sub_questions) * (2 + extra_per_sq) + 1 + 2 + 1
    if depth == "quick":
      max_turns = min(max_turns, calculated_turns)
    else:
      max_turns = max(max_turns, calculated_turns)
    force_report_at = max_turns - 4  # 最后 4 轮留给汇总和报告

    if verbose:
        print(f"\n📋  拆解完成：{len(sub_questions)} 个子问题")
        for i, sq in enumerate(sub_questions, 1):
            print(f"     {i}. {sq['desc']}")
            print(f"        搜索词：{sq['search_kw']}")
        print(f"📐  轮数调整为 {max_turns}（原定上限已覆盖）")
        if should_summarize:
            print(f"📋  渐进式摘要已激活（子问题>{_SUMMARIZE_THRESHOLD}个，每项完成后自动压缩）")
        print(f"{'=' * 60}\n")

    # ── 阶段 1：串行研究 ──────────────────────────────────────
    # 按子问题逐项研究，每项 1-2 轮（取决于来源评分）

    global_turn = 1  # 全局轮数计数器（规划阶段已用 1 轮）

    for sq_index, sq in enumerate(sub_questions):
        if global_turn > max_turns:
            if verbose:
                print(f"  ⚠️ 已达最大轮数 {max_turns}，跳过剩余子问题")
            break

        # ── 打印子问题标题 ──
        if verbose:
            print(f"\n{'─' * 40}")
            print(f"📋 子问题 [{sq_index + 1}/{len(sub_questions)}]：{sq['desc']}")
            print(f"   搜索建议：{sq['search_kw']}")
            print(f"   （第 {global_turn}/{max_turns} 轮）")
            print(f"{'─' * 40}")

        # ── 注入子问题指令 ──
        sq_instruction = (
            f"【当前研究 [{sq_index + 1}/{len(sub_questions)}]】{sq['desc']}\n"
            f"请聚焦以上子问题，使用搜索词「{sq['search_kw']}」"
            f"或你认为更好的关键词发起搜索。"
            f"只研究这个子问题，不要跳到其他维度。"
        )
        # 研究笔记模式下提示 LLM 先查看已有摘要
        if research_notes:
            sq_instruction += (
                f"\n\n对话中的「研究笔记」包含前 {len(research_notes)} 个子问题的摘要。"
                f"如果当前子问题与已完成的子问题相关，可引用笔记中的信息，"
                f"避免重复搜索相同内容。"
            )
        messages.append({"role": "user", "content": sq_instruction})

        # ── 第 1 轮 ──
        if verbose:
            print(f"  🔍 第 1 轮...")

        r1 = _run_single_turn(
            messages, tool_schemas, tool_map, client, verbose,
        )
        global_turn += 1
        source_count += r1["source_delta"]

        if r1["report_saved"]:
            if verbose:
                print(f"\n✅ 研究报告已生成并保存")
                print(f"📊 共收集 {source_count} 个页面来源")
                print(f"🔄 共执行 {global_turn - 1} 轮对话")
            return "报告已成功生成并保存。"

        # ── 评分判断：是否需要第 2 轮 ──
        if r1["highest_score"] >= 75:
            if verbose:
                print(f"  ✅ 来源评分 {r1['highest_score']} ≥ 75，一轮通过")
            # ── 渐进式摘要（方案A）：压缩当前子问题 ──
            if should_summarize:
                _compress_current_sub_question(
                    sq, messages, client, research_notes,
                    preamble_end_index, topic, verbose,
                )
                global_turn += 1  # 总结消耗 1 轮
            continue

        if global_turn > max_turns:
            if verbose:
                print(f"  ⚠️ 已达最大轮数，跳过第 2 轮")
            # ── 渐进式摘要（方案A）──
            if should_summarize:
                _compress_current_sub_question(
                    sq, messages, client, research_notes,
                    preamble_end_index, topic, verbose,
                )
                global_turn += 1
            continue

        # ── 第 2 轮 ──
        if verbose:
            print(f"  🔍 第 2 轮补充搜索（最高评分 {r1['highest_score']} < 75）...")

        messages.append({
            "role": "user",
            "content": (
                f"当前子问题「{sq['desc']}」的信息质量不够理想。"
                f"请换个角度或搜索词，再搜一轮补充信息。"
                f"之后无论结果如何，都继续下一个子问题。"
            ),
        })

        r2 = _run_single_turn(
            messages, tool_schemas, tool_map, client, verbose,
        )
        global_turn += 1
        source_count += r2["source_delta"]

        if r2["report_saved"]:
            if verbose:
                print(f"\n✅ 研究报告已生成并保存")
                print(f"📊 共收集 {source_count} 个页面来源")
                print(f"🔄 共执行 {global_turn - 1} 轮对话")
            return "报告已成功生成并保存。"

        # ── 渐进式摘要（方案A）：第 2 轮完成后压缩 ──
        if should_summarize:
            _compress_current_sub_question(
                sq, messages, client, research_notes,
                preamble_end_index, topic, verbose,
            )
            global_turn += 1  # 总结消耗 1 轮

    # ── 阶段 2：汇总 ──
    if verbose:
        print(f"\n{'─' * 40}")
        print(f"📋 所有子问题研究完毕")
        print(f"📊 共收集 {source_count} 个页面来源")
        print(f"🔄 共执行 {global_turn - 1} 轮")
        if research_notes:
            print(f"📋 研究笔记模式：已累积 {len(research_notes)} 条子问题摘要")
        print(f"{'─' * 40}")

    if research_notes:
        # 渐进摘要模式：研究笔记已是汇总，做一次轻量全局聚合即可
        if global_turn <= max_turns:
            _summarize_findings(
                messages, client,
                label="全部子问题（基于研究笔记）",
                verbose=verbose,
            )
            global_turn += 1
    else:
        # 子问题数少，未触发压缩，走原始汇总逻辑
        _summarize_findings(
            messages, client,
            label="全部子问题",
            verbose=verbose,
        )
        global_turn += 1

    # ── 阶段 3：报告撰写 ──────────────────────────────────────
    if verbose:
        print(f"\n📝 进入报告撰写阶段...")

    report_prompt = build_report_prompt(
        topic, source_count, depth=depth,
    )
    # 研究笔记模式下，提醒 LLM 充分利用笔记中的已有摘要
    if research_notes:
        report_prompt += (
            "\n\n**注意：** 对话中的「研究笔记」包含了所有子问题的研究摘要。"
            "请基于这些摘要撰写报告，覆盖每个子问题的核心发现。"
            "摘要中标注的来源 URL 可直接引用到参考资料中。"
        )
    messages.append({"role": "user", "content": report_prompt})

    while global_turn <= max_turns:
        if verbose:
            print(f"--- 📝 报告阶段 | 第 {global_turn}/{max_turns} 轮 ---")

        result = _run_single_turn(
            messages, tool_schemas, tool_map, client, verbose,
        )
        global_turn += 1
        source_count += result["source_delta"]

        if result["report_saved"]:
            if verbose:
                print(f"\n✅ 研究报告已生成并保存")
                print(f"📊 共收集 {source_count} 个页面来源")
                print(f"🔄 共执行 {global_turn - 1} 轮对话")
            return "报告已成功生成并保存。"

    # ── 超时未生成报告 ──
    if verbose:
        print(
            f"\n⚠️ 达到最大轮数上限（{max_turns}），"
            f"但 LLM 未显式调用 save_report_tool。"
        )
        print(f"📊 共收集 {source_count} 个页面来源")

    return (
        f"研究循环结束（共 {global_turn - 1} 轮）。"
        f"收集了 {source_count} 个页面来源。"
        f"最终消息已保留在对话历史中，请人工检查报告是否完整。"
    )


# ── CLI 入口 ──────────────────────────────────────────────────

if __name__ == "__main__":
    topic = input("请输入研究课题：").strip()
    if not topic:
        print("错误：研究课题不能为空。")
    else:
        result = deep_research(topic, verbose=True)
        print(f"\n{'=' * 60}")
        print(f"结果：{result}")
        print(f"{'=' * 60}")
