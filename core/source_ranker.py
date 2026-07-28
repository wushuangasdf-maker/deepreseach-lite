"""
来源质量评分模块 — source_ranker.py

对搜索结果进行多维度质量评分，帮助 LLM 做出更好的抓取决策。

评分维度：
  1. 来源权威度（30%）：基于域名白名单判断来源是否可靠
  2. 标题质量（25%）：检测标题党、无意义标题
  3. 摘要信息密度（25%）：摘要是否包含具体数据和事实
  4. 关键词相关性（20%）：搜索结果与搜索词的匹配程度

设计原则：
  - 纯规则引擎，不调用任何 AI/LLM —— 快且免费
  - 不删除低分结果，只排序和标注 —— LLM 保留最终决策权
  - 未识别的域名给中性分不扣分 —— 白名单有限，不误伤

用法:
    from core.source_ranker import rank_sources

    pages = [{"title": "...", "url": "...", "snippet": "..."}, ...]
    ranked = rank_sources(pages, "AI芯片 市场规模")
    
    for p in ranked:
        print(f"[{p['_score']}] {p['title']}")  # 按质量从高到低排列

输入格式（来自 bocha_search 的返回）:
    [
        {"title": str, "url": str, "snippet": str},
        ...
    ]

输出格式:
    [
        {"title": str, "url": str, "snippet": str, "_score": int, "_flags": list[str]},
        ...
    ]
    按 _score 从高到低排序
"""

import re
from urllib.parse import urlparse


# ═══════════════════════════════════════════════════════════════════════
# 域名权威度白名单
# ═══════════════════════════════════════════════════════════════════════
# 
# 设计说明：
#   - 基础分范围 0~30，对应 _score_authority() 的满分
#   - 未列入的域名 → 给中性分 15（不扣不奖）
#   - 低质量域名明确给低分（5~10），防止 LLM 误采
#   - 键是域名的主体部分（去掉 www. 前缀和路径），方便匹配
#
# 如何扩展：
#   把你认为靠谱的域名加进来，赋值一个你认为合理的分数。
#   宁缺毋滥——不确定的不要加。


DOMAIN_AUTHORITY: dict[str, float] = {

    # ── 政府与教育机构（28~30 分）────────────────────────────
    # 这类来源信息最权威，但更新频率低，适合找政策、法规、统计数据
    "gov.cn":        30.0,
    "edu.cn":        29.0,
    "cas.cn":        28.0,   # 中国科学院
    "cae.cn":        28.0,   # 中国工程院
    "stats.gov.cn":  30.0,   # 国家统计局
    "miit.gov.cn":   29.0,   # 工信部
    "most.gov.cn":   28.0,   # 科技部

    # ── 权威综合媒体（22~26 分）────────────────────────────
    # 编辑审核严格，事实核查到位，适合找主流新闻和事件背景
    "xinhuanet.com":   26.0,   # 新华社
    "people.com.cn":   25.0,   # 人民网
    "cctv.com":        25.0,   # 央视
    "thepaper.cn":     24.0,   # 澎湃新闻
    "china.com.cn":    23.0,   # 中国网
    "gmw.cn":          23.0,   # 光明网
    "youth.cn":        22.0,   # 中国青年网
    "ce.cn":           22.0,   # 中国经济网
    "chinanews.com":   23.0,   # 中国新闻网
    "cnr.cn":          23.0,   # 央广网

    # ── 财经/科技垂直媒体（18~22 分）────────────────────────
    # 行业分析深度好，但权威性不如官方来源
    "36kr.com":        20.0,   # 36氪
    "huxiu.com":       20.0,   # 虎嗅
    "geekpark.net":    19.0,   # 极客公园
    "ifeng.com":       19.0,   # 凤凰网
    "caixin.com":      22.0,   # 财新（付费墙，但摘要可信）
    "cls.cn":          20.0,   # 财联社
    "eastmoney.com":   18.0,   # 东方财富（数据多，但注意自媒体）
    "jiemian.com":     19.0,   # 界面新闻
    "tmtpost.com":     19.0,   # 钛媒体
    "iyiou.com":       18.0,   # 亿欧（产业研究）

    # ── 百科/学术（20~25 分）───────────────────────────────
    "wikipedia.org":   25.0,
    "baike.baidu.com": 22.0,   # 百度百科（质量在提升，但商业化重）
    "zh.wikipedia.org": 25.0,
    "scholar.google.com": 24.0,
    "cnki.net":        24.0,   # 知网
    "wanfangdata.com": 23.0,   # 万方

    # ── 技术社区（12~16 分）─────────────────────────────────
    # 内容质量方差大，取决于作者。高分文章很好，低分不少
    "zhihu.com":           14.0,
    "zhuanlan.zhihu.com":  13.0,   # 知乎专栏（门槛比主站低）
    "juejin.cn":           15.0,   # 掘金（技术文章质量偏高）
    "segmentfault.com":    14.0,
    "sspai.com":           16.0,   # 少数派（编辑审核较严）
    "infoq.cn":            16.0,   # InfoQ 中文
    "v2ex.com":            12.0,

    # ── 低质量来源（5~10 分）───────────────────────────────
    # 海量转载、SEO 驱动、内容门槛低。不禁止但标注低分
    "csdn.net":       8.0,    # CSDN（大量转载和机翻）
    "jianshu.com":    7.0,    # 简书（个人博客聚合，门槛很低）
    "cnblogs.com":    10.0,   # 博客园（有好有坏，整体偏个人）
    "163.com":        12.0,   # 网易（门户，自媒体报道多）
    "sina.com.cn":    11.0,   # 新浪（同门户）
    "sohu.com":       10.0,   # 搜狐（同门户）
    "qq.com":         10.0,   # 腾讯网（同门户，注意区分腾讯科技）
}


# ═══════════════════════════════════════════════════════════════════════
# 标题党特征词
# ═══════════════════════════════════════════════════════════════════════
# 标题中出现这些词的 → 扣标题质量分
# 收集方式：打开今日头条或百度首页，看推荐流里的标题

CLICKBAIT_WORDS: list[str] = [
    # 煽动性
    "震惊", "惊呆", "震撼", "吓傻", "吓尿",
    "万万没想到", "竟然", "居然",
    # 情绪勒索
    "赶紧看", "速看", "马上删", "紧急", "刚刚",
    "出大事了", "炸了", "炸裂",
    # 虚假稀缺
    "不转不是", "绝密", "内部", "独家揭秘",
    # 悬念党
    "你绝对想不到", "让人意外", "竟然是这样",
    # 量化党
    "排名第一", "最全", "史上最", "全球最",
]


# ═══════════════════════════════════════════════════════════════════════
# 低质量摘要特征
# ═══════════════════════════════════════════════════════════════════════
# 摘要中出现这些模式 → 扣信息密度分

LOW_QUALITY_SNIPPET_MARKERS: list[str] = [
    "请点击", "点击查看", "阅读全文", "展开全文",
    "JavaScript", "请启用", "请打开",
    "404", "页面不存在", "抱歉",
    "登录", "注册", "扫码", "关注公众号",
    "Copyright", "All Rights Reserved",
]


# ═══════════════════════════════════════════════════════════════════════
# 公开入口（步骤 6 实现）
# ═══════════════════════════════════════════════════════════════════════

def rank_sources(pages: list[dict], query: str) -> list[dict]:
    """
    对搜索结果进行质量评分并排序。

    参数:
        pages: bocha_search() 返回的原始列表，每项含 title/url/snippet
        query: 用户原始搜索词，用于计算相关性

    返回:
        同结构列表，每项增加了 _score (int 0~100) 和 _flags (list[str])，
        按 _score 从高到低排列。
    """
     # ── 去重：相同 URL 只保留第一条 ──
    seen_urls = set()
    unique_pages = []
    for p in pages:
        url = p.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_pages.append(p)
    pages = unique_pages

    
    for page in pages:
        auth = _score_authority(page.get("url", ""))
        title_s = _score_title(page.get("title", ""), query)
        snippet_s = _score_snippet(page.get("snippet", ""))
        relevance = _score_relevance(
            page.get("title", ""),
            page.get("snippet", ""),
            query,
        )
        total = auth + title_s + snippet_s + relevance
        page["_score"] = round(total)
        page["_flags"] = _collect_flags(auth, title_s, snippet_s, relevance)

    pages.sort(key=lambda p: p.get("_score", 0), reverse=True)
    return pages


# ═══════════════════════════════════════════════════════════════════════
# 内部评分函数（步骤 3~5 实现，目前为占位）
# ═══════════════════════════════════════════════════════════════════════

def _score_authority(url: str) -> float:
    """从 URL 中提取域名，查 DOMAIN_AUTHORITY 表，返回 0~30 分。"""
    if not url:
        return 15.0  # 无 URL → 中性分
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return 15.0

    # 精确匹配 + 后缀模糊匹配（如 xxx.gov.cn 匹配 gov.cn）
    for key, score in DOMAIN_AUTHORITY.items():
        if domain == key or domain.endswith("." + key):
            return score

    return 15.0  # 未命中白名单 → 中性分

def _score_title(title: str, query: str) -> float:
    """
    评估搜索结果标题的质量，返回 0~25 分。

    评分逻辑：
      - 基础分 15（中性起评分）
      - 检测到标题党特征词 → 扣分
      - 标题过短（≤5 字）→ 扣分
      - 标题中感叹号过多 → 扣分
      - 看起来像正式文章标题 → 加分
      - 标题包含 query 中的关键词 → 加分
    """
    if not title or not title.strip():
        return 5.0

    title = title.strip()
    base = 15.0

    # ── 扣分项 ──

    # 1. 标题党特征词
    clickbait_count = 0
    for word in CLICKBAIT_WORDS:
        if word in title:
            clickbait_count += 1
    base -= min(clickbait_count * 5, 15)

    # 2. 标题过短
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', title))
    if chinese_chars <= 5:
        base -= 8
    elif chinese_chars <= 10:
        base -= 3

    # 3. 感叹号过多
    exclamation_count = title.count("！") + title.count("!")
    if exclamation_count >= 2:
        base -= 5
    elif exclamation_count >= 1:
        base -= 2

    # 4. 英文比例过高（中文搜索场景下异常）
    ascii_chars = len(re.findall(r'[a-zA-Z]', title))
    if ascii_chars > len(title) * 0.5:
        base -= 3

    # ── 加分项 ──

    # 正式标题：长度够 + 无标题党词
    if chinese_chars >= 15 and clickbait_count == 0:
        base += 4

    # 标题命中搜索关键词（额外奖励）
    if query and query.strip():
        query_keywords = re.split(r'[\s,，。；;、！!？?：:]+', query.strip())
        query_keywords = [kw for kw in query_keywords if len(kw) > 1]
        title_lower = title.lower()
        match_count = sum(1 for kw in query_keywords if kw.lower() in title_lower)
        if match_count >= len(query_keywords) * 0.7 and len(query_keywords) >= 2:
            base += 3

    return max(0.0, min(base, 25.0))


def _score_snippet(snippet: str) -> float:
    """
    评估搜索摘要的信息密度，返回 0~25 分。

    评分逻辑：
      - 基础分 15
      - 包含具体数字/日期 → 加分（信息密度高）
      - 摘要过短或为空 → 扣分
      - 摘要包含导航/登录/Javascript 等提示 → 扣分（页面不可用）
      - 摘要全是英文 → 扣分（中文搜索场景）

    为什么需要这个函数：
      搜索结果摘要决定了 LLM 是否要抓取该页面。
      信息密度高的摘要 → 抓取后大概率有收获
      信息密度低的摘要 → 抓了也是浪费时间和 token
    """
    if not snippet or not snippet.strip():
        return 3.0  # 空摘要 → 极低分但不是 0（可能是 API 未抓取到）

    snippet = snippet.strip()
    base = 15.0

    # ── 扣分项 ──────────────────────────────────────────

    # 1. 摘要中出现低质量标记（登录墙、JS 渲染提示等）
    low_quality_hits = 0
    for marker in LOW_QUALITY_SNIPPET_MARKERS:
        if marker.lower() in snippet.lower():
            low_quality_hits += 1
    base -= min(low_quality_hits * 6, 18)  # 每命中一个扣 6 分

    # 2. 摘要过短
    if len(snippet) < 30:
        base -= 8
    elif len(snippet) < 80:
        base -= 3

    # 3. 摘要几乎全是英文（中文搜索场景下通常无价值）
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', snippet))
    total_alpha = len(re.findall(r'[a-zA-Z]', snippet))
    if total_alpha > len(snippet) * 0.6 and chinese_chars < 10:
        base -= 6

    # ── 加分项 ──────────────────────────────────────────

    # 1. 包含具体数字（年份、百分比、金额、数量）
    #    这些是硬信息的信号——摘要里带数字说明原文有数据
    number_patterns = [
        r'\d{4}年',           # 2026年
        r'\d+%',              # 80%
        r'\d+\.?\d*亿',       # 3.5亿
        r'\d+\.?\d*万',       # 200万
        r'\d+\.?\d*元',       # 5000元
        r'第\s*\d+',          # 第一、第 3
    ]
    number_score = 0
    for pattern in number_patterns:
        if re.search(pattern, snippet):
            number_score += 1
    base += min(number_score * 2, 8)  # 每种数字类型加 2 分，最多加 8 分

    # 2. 摘要长度适中（80~300 字），信息量通常刚好
    if 80 <= len(snippet) <= 300:
        base += 2

    # ── 限制范围 ──────────────────────────────────────────
    return max(0.0, min(base, 25.0))


def _score_relevance(title: str, snippet: str, query: str) -> float:
    """
    评估搜索词与结果的相关性，返回 0~20 分。

    方法：
      1. 把 query 按空格/标点拆成关键词
      2. 过滤掉太短的词（≤1 个字符，如"的"、"了"）
      3. 在 title + snippet 里逐词检查是否命中
      4. 按命中比例给分，title 命中权重比 snippet 高

    满分 20 分：
      - 所有关键词都在 title 中命中 → 接近满分
      - 所有关键词都在 snippet 中命中 → 约 16 分
      - 部分命中 → 按比例折算
      - 几乎没命中 → 0~3 分（给低分但不给 0，保留一丝希望）
    """
    if not query or not query.strip():
        return 10.0  # 没有搜索词 → 无法判断相关性 → 给中性分

    # ── 1. 拆词 ──────────────────────────────────────────
    # 按空格、中文标点、英文标点拆分
    raw_keywords = re.split(r'[\s,，。；;、！!？?：:（）()【】\[\]{}"\'·]+', query)
    # 去掉太短的词和空字符串
    keywords = [kw for kw in raw_keywords if len(kw) > 1]

    if not keywords:
        return 10.0  # 搜索词全是单字 → 无法拆词 → 中性分

    # ── 2. 在标题中查找 ──────────────────────────────────
    title_lower = title.lower() if title else ""
    title_hits = 0
    for kw in keywords:
        if kw.lower() in title_lower:
            title_hits += 1

    # ── 3. 在摘要中查找 ──────────────────────────────────
    snippet_lower = snippet.lower() if snippet else ""
    snippet_hits = 0
    for kw in keywords:
        # 只查标题中没命中的词（避免重复计数）
        if kw.lower() not in title_lower and kw.lower() in snippet_lower:
            snippet_hits += 1

    # ── 4. 算分 ──────────────────────────────────────────
    total_keywords = len(keywords)
    # title 命中一个词值 2 分，snippet 命中一个词值 1.2 分
    # 上限 20 分
    raw = title_hits * (20.0 / total_keywords) * 1.0 + snippet_hits * (20.0 / total_keywords) * 0.6
    score = min(raw, 20.0)

    # 如果几乎没命中（< 3 分），给一个保底分
    if score < 3.0 and (title_hits + snippet_hits) >= 1:
        score = 3.0

    return score



def _collect_flags(auth: float, title_s: float, snippet_s: float, relevance: float) -> list[str]:
    """收集评分标记，用于解释得分原因（给 build_context 展示用）。"""
    flags = []
    if auth >= 25:
        flags.append("权威来源")
    elif auth <= 8:
        flags.append("来源可信度低")
    if title_s <= 8:
        flags.append("标题质量差")
    if snippet_s <= 8:
        flags.append("摘要信息少")
    if relevance >= 15:
        flags.append("高度相关")
    return flags
