"""
报告撰写提示词构建 — report.py

在研究搜集阶段结束后，通过此模块生成"撰写指令"注入对话，
强制 LLM 从搜索模式切换到撰写模式，按规范格式产出报告并保存。

与 system.py 的分工：
  - system.py：研究阶段的持久背景指令（角色、工具、搜索流程）
  - report.py：撰写阶段的触发指令（停止搜索、动笔、格式、保存）

用法（Agent 循环中，判断研究充分后调用）:
    from agent.prompts.report import build_report_prompt

    # 研究完成后，作为 user 消息插入
    report_instruction = build_report_prompt("2026年AI芯片市场格局")
    messages.append({"role": "user", "content": report_instruction})

    # LLM 收到此指令后应停止搜索，直接撰写报告并调用 save_report_tool
"""


def build_report_prompt(
    research_topic: str,
    source_count: int = 0,
    depth: str = "standard",
) -> str:
    """
    构建报告撰写提示词，作为 user 消息注入对话。

    参数:
        research_topic (str): 原始研究课题，用于生成报告标题。
        source_count (int): 已搜集的来源/页面数量。传入实际数字可激励 LLM
                            充分利用已有材料，而非要求追加搜索。

    返回:
        str: 报告撰写指令字符串，追加到 messages 列表的 user role 中。
    """
    parts: list[str] = [
        _stop_instruction(),
        _source_reminder(source_count),
        _template_section(research_topic, depth=depth),
        _citation_section(),
        _save_instruction(),
    ]
    return "\n\n".join(parts)


# ── 各段落构建函数 ──────────────────────────────────────────────


def _stop_instruction() -> str:
    """停止搜索指令 —— 强制 LLM 切换行为模式"""
    return (
        "## 指令：开始撰写报告\n\n"
        "**研究阶段已结束。** 不要再发起新的搜索或页面抓取。\n"
        "现在使用你已搜集到的所有信息，撰写最终研究报告。\n\n"
        "**报告应覆盖研究计划中的所有子问题，不要遗漏任何一个维度。**\n"
        "如果某个子问题的信息来源不足，在对应章节明确标注「信息不足」而非捏造。"
    )


def _source_reminder(source_count: int) -> str:
    """来源提醒 —— 利用已有的材料"""
    if source_count <= 0:
        return (
            "请充分利用你在研究过程中抓取到的所有页面内容，"
            "确保报告中的每个观点都有来源支撑。"
        )
    return (
        f"你在研究中共搜集了 {source_count} 个信息来源。\n"
        "请充分利用这些材料，确保报告中的每个观点都有来源支撑。"
        "如果有重要的信息缺口导致无法完成某个章节，"
        "在对应位置标注「信息不足」而非捏造内容。"
    )


def _template_section(topic: str, depth: str = "standard") -> str:
    """报告模板段落 —— 比 system.py 中的更详细"""
    # 根据 depth 调整报告长度建议
    if depth == "quick":
        length_guide = "报告长度建议：500-1000 字，简洁扼要，抓住核心信息即可。"
    elif depth == "deep":
        length_guide = "报告长度建议：2000-4000 字，深入分析，详细引用来源，覆盖所有子问题维度。"
    else:
        length_guide = "报告长度建议：800-2000 字，视课题复杂程度而定。"
    return (
        "## 报告格式要求\n\n"
        f"报告标题自拟，应准确概括「{topic}」的核心发现。\n"
        "严格按以下结构组织报告（Markdown 格式）：\n\n"
        "```markdown\n"
        f"# [自拟标题]\n\n"
        "## 一、概述\n"
        "用 3-5 句话概括本次研究的核心发现和结论，让读者快速了解全貌。\n\n"
        "## 二、[分主题标题]\n"
        "围绕一个具体方面展开论述。每段 2-4 句话，\n"
        "用事实和数据说话，段末标注引用来源。\n\n"
        "## 三、[分主题标题]\n"
        "围绕另一个方面展开。对于复杂课题，可分 2-4 个分主题。\n"
        "各分主题之间应有逻辑递进关系（如：背景→现状→趋势→挑战）。\n\n"
        "## 四、总结与展望\n"
        "- 归纳 2-3 条核心要点\n"
        "- 展望后续发展趋势（基于来源中的信息，不做无依据的预测）\n"
        "- 标注研究中发现的存疑之处或信息缺口\n\n"
        "## 参考资料\n"
        "列出所有引用来源的名称和 URL。\n"
        "```\n\n"
        + length_guide
    )


def _citation_section() -> str:
    """引用规范段落 —— LLM 撰写时的具体引用规则"""
    return (
        "## 引用规则\n\n"
        "正文中使用 `[^1]`、`[^2]` 格式标注引用，"
        "在「参考资料」章节用 `[^1]: 来源名称 - URL` 列出对应链接。\n\n"
        "引用示例：\n"
        "```markdown\n"
        "据工信部数据，2025年中国AI芯片市场规模达到800亿元[^1]。\n"
        "但英伟达仍占据全球数据中心GPU市场超过80%的份额[^2]。\n\n"
        "[^1]: 工信部《2025年人工智能产业发展报告》- https://example.com/report\n"
        "[^2]: Tom's Hardware 报道 - https://example.com/nvidia-dcgpu-share\n"
        "```\n\n"
        "引用要求：\n"
        "- 关键数据（数字、百分比、日期）必须有引用\n"
        "- 引用来源必须是你实际搜索和抓取到的，不得编造 URL\n"
        "- 同一来源多次引用使用不同编号，不要重复使用同一个脚注编号"
    )


def _save_instruction() -> str:
    """保存指令 —— 告诉 LLM 完稿后调用保存工具"""
    return (
        "## 完稿后的操作\n\n"
        "报告撰写完成后，**立即调用 save_report_tool 保存文件**，参数为：\n"
        "- `title`：你自拟的报告标题\n"
        "- `report`：完整的报告 Markdown 正文\n\n"
        "保存成功后，向用户回复简短的完成提示（一句话即可），不要重复报告全文。"
    )
