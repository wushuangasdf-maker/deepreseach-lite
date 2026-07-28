"""
任务拆解提示词构建 — plan.py

在进入研究循环之前，用此模块构建"规划指令"，让 LLM 将复杂课题
拆解为 3-5 个独立子问题，每个子问题附带建议搜索词。

拆解完成后，Agent 按子问题逐项研究（串行），避免扁平搜索遗漏角度。

与 system.py 的分工：
  - system.py：研究阶段的持久背景指令（角色、工具、搜索流程）
  - plan.py：  研究前的规划指令（只调用一次，不带 tools）

用法:
    from agent.prompts.plan import build_plan_prompt

    # 研究开始前，作为 user 消息插入
    plan_instruction = build_plan_prompt("2026年AI芯片市场格局")
    messages.append({"role": "user", "content": plan_instruction})

    # LLM 返回后，调用解析函数提取子问题列表
    sub_questions = parse_plan_result(llm_response_text)
"""


def build_plan_prompt(topic: str, depth: str = "standard") -> str:
    """
    构建任务拆解提示词，作为 user 消息注入对话。

    参数:
        topic (str): 用户原始研究课题

    返回:
        str: 任务拆解指令字符串，追加到 messages 列表的 user role 中。
    """
    parts: list[str] = [
        _stop_and_think(),
        _decomposition_rules(depth=depth),
        _output_format(),
        _example(topic),
    ]
    return "\n\n".join(parts)


# ── 各段落构建函数 ──────────────────────────────────────────────


def _stop_and_think() -> str:
    """停止搜索指令 —— 让 LLM 先思考再行动"""
    return (
        "## 指令：任务拆解\n\n"
        "**在开始搜索之前，先完成以下思考。不要调用任何工具——"
        "你只需要用纯文本回答。**"
    )


def _decomposition_rules(depth: str = "standard") -> str:
    """拆解规则 —— 告诉 LLM 怎么拆、拆多细，根据 depth 调整"""
    if depth == "quick":
        count_guide = "拆解为 **1-2 个最核心的子问题**（快速模式，只关注最重要的角度）"
        principle5 = (
            "5. **速度优先**：只选最核心的 1-2 个角度，跳过次要维度\n"
            "   简单问题只输出 1 个即可"
        )
    elif depth == "deep":
        count_guide = "拆解为 **5-7 个相互独立的子问题**（深度模式，覆盖更多维度）"
        principle5 = (
            "5. **全面覆盖**：从更多角度审视课题，不遗漏任何重要维度\n"
            "   常见角度之外还可考虑：历史背景、国际比较、行业案例、未来风险"
        )
    else:  # standard
        count_guide = "拆解为 **3-5 个相互独立的子问题**"
        principle5 = (
            "5. **实事求是**：简单课题拆 1-2 个即可，不要强行拆多\n"
            "   极简单的问题（如「今天天气」）可以不拆——只输出 1 个子问题"
        )

    return (
        "## 拆解规则\n\n"
        f"将研究课题{count_guide}，每个子问题"
        "代表一个不同的研究角度或维度。\n\n"
        "拆解原则：\n"
        "1. **覆盖全面**：确保子问题合起来能覆盖课题的主要方面\n"
        "   常见角度：市场规模、竞争格局、技术路线、政策环境、发展趋势\n"
        "2. **相互独立**：子问题之间不重叠，各有明确的搜索目标\n"
        "3. **粒度适中**：每个子问题应能在 1-2 次搜索内基本回答\n"
        "4. **附带搜索词**：每个子问题给出简洁、具体的搜索关键词\n"
        f"{principle5}\n\n"
        "搜索词构造提醒：\n"
        "- 用 2-5 个关键词组合，不要整句\n"
        "- 把年份、专有名词、关键数据点放进去\n"
        "- 例如「市场规模」→「2026年 AI芯片 市场规模 亿美元」"
    )


def _output_format() -> str:
    """输出格式 —— 严格的解析格式，方便程序提取"""
    return (
        "## 输出格式\n\n"
        "**严格按以下格式输出，每行一个子问题，不要加序号之外的任何内容：**\n\n"
        "```\n"
        "1. [子问题描述] | [建议搜索词]\n"
        "2. [子问题描述] | [建议搜索词]\n"
        "3. [子问题描述] | [建议搜索词]\n"
        "```\n\n"
        "格式说明：\n"
        "- 以「数字. 」开头\n"
        "- 描述和搜索词之间用「 | 」分隔（竖线前后各有一个空格）\n"
        "- 只输出子问题列表，不要加「以下是拆解结果」之类的开场白\n"
        "- 不要输出序号之外的编号或符号"
    )


def _example(topic: str) -> str:
    """示例 —— 给 LLM 一个具体参考，提高输出稳定性"""
    return (
        "## 示例\n\n"
        f"课题：「{topic}」\n\n"
        "你应输出类似以下格式（内容仅为示意，你需要根据实际课题调整）：\n\n"
        "1. 市场规模与增长趋势 | 2026年 [相关关键词] 市场规模\n"
        "2. 主要参与者竞争格局 | [相关厂商] 市场份额 2026\n"
        "3. 技术路线与产品演进 | [相关技术] 最新进展 2026\n"
        "4. 政策环境与监管动态 | [相关政策] 监管 2026\n"
        "5. 未来展望与挑战 | [相关领域] 发展趋势 预测\n\n"
        "**请将方括号中的占位内容替换为与课题实际相关的具体关键词。**"
    )


# ── 解析函数 ──────────────────────────────────────────────────


def parse_plan_result(text: str) -> list[dict]:
    """
    解析 LLM 返回的子问题列表。

    期望格式：
        1. 子问题描述 | 搜索词
        2. 子问题描述 | 搜索词

    解析策略：
        逐行扫描 → 匹配「数字. 描述 | 搜索词」模式 →
        解析成功则加入结果，失败则跳过该行

    降级策略：
        如果一条都没解析出来，返回单元素列表
        ——把整个课题当作唯一的子问题（不拆解模式）

    参数:
        text (str): LLM 返回的原始文本

    返回:
        list[dict]: 子问题列表，每项含 desc 和 search_kw
            例如: [{"desc": "市场规模", "search_kw": "AI芯片 市场规模 2026"}, ...]
    """
    import re

    sub_questions: list[dict] = []

    for line in text.strip().split("\n"):
        line = line.strip()
        # 匹配格式: "1. 描述 | 搜索词" 或 "1.描述|搜索词"
        match = re.match(
            r'^\d+\.\s*(.+?)\s*\|\s*(.+?)$',
            line,
        )
        if match:
            desc = match.group(1).strip()
            search_kw = match.group(2).strip()
            if desc and search_kw:
                sub_questions.append({
                    "desc": desc,
                    "search_kw": search_kw,
                })

    # ── 降级：解析失败则整个课题作为一个子问题 ──
    if not sub_questions:
        sub_questions.append({
            "desc": topic_from_text(text),
            "search_kw": topic_from_text(text),
        })

    return sub_questions


def topic_from_text(text: str) -> str:
    """
    从 LLM 返回文本中提取课题名（降级场景用）。

    当 parse_plan_result 解析失败时，用此函数取文本第一行
    作为兜底的子问题描述。

    参数:
        text (str): LLM 返回的原始文本

    返回:
        str: 截取后的课题描述（最多 100 字符）
    """
    first_line = text.strip().split("\n")[0].strip()
    # 去掉可能的编号前缀
    cleaned = first_line.lstrip("0123456789. ).：: ")
    if len(cleaned) > 100:
        cleaned = cleaned[:97] + "..."
    return cleaned or "原始研究课题"
