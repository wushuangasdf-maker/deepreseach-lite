# DeepResearch-Lite

LLM 驱动的自主深度研究系统 — 输入一个课题，Agent 自动搜索、抓取、交叉验证，产出结构化中文研究报告。

## ✨ 特性

- 🔍 **多轮自主研究** — ReAct 循环编排，LLM 自主决定搜索与抓取策略
- 🧠 **子问题拆解** — 自动将复杂课题拆分为子问题，逐项深挖
- 📋 **渐进式摘要** — 上下文超 70% 自动压缩，应对长文档 64K 窗口限制
- 📊 **来源评分** — 搜索结果自动评分（0-100），优先抓取高质量页面
- 🔄 **双引擎兜底** — 博查搜索失败/空结果时自动降级到百度千帆搜索
- 🌐 **HTTP 服务** — FastAPI + SSE 实时进度推送，支持异步任务
- 🎚️ **三种深度** — quick / standard / deep，适配不同场景

## 🏗️ 架构

```
用户输入 → 规划阶段（拆解子问题）→ 串行研究（逐项搜索+抓取）→ 汇总 → 报告撰写 → 保存
                                      ↑ 渐进式摘要保护上下文 ↑
```

```
deepresearch-lite/
├── agent/                  # Agent 核心
│   ├── agents.py           #   ReAct 循环编排、多轮研究引擎
│   ├── cli.py              #   命令行入口
│   ├── service.py          #   异步任务服务（ThreadPoolExecutor）
│   └── prompts/            #   系统提示词
│       ├── system.py       #     角色/流程/行为准则
│       ├── plan.py         #     课题拆解规划
│       ├── report.py       #     报告撰写指令
│       └── tools.py        #     工具使用策略
├── core/                   # 基础设施
│   ├── llm.py              #   LLM 客户端工厂（OpenAI 兼容接口）
│   ├── bocha_search.py     #   博查 AI 搜索引擎封装
│   ├── baidu_search.py     #   百度千帆搜索引擎封装（兜底）
│   ├── search.py           #   双引擎兜底调度（博查 → 百度）
│   ├── knowledge_base.py   #   本地知识库（FAISS + BGE）
│   ├── source_ranker.py    #   搜索结果评分排序
│   └── config.py           #   配置中心（从 .env 读取）
├── api/                    # HTTP 服务
│   └── main.py             #   FastAPI 路由（SSE 实时推送）
├── tools/                  # Agent 可调用工具
│   ├── web_search.py       #   网页搜索
│   ├── fetch_page.py       #   网页内容抓取
│   ├── kb_search.py        #   本地知识库检索
│   └── save_report.py      #   报告保存
└── test/                   # 测试脚本
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+
- [博查 AI](https://open.bochaai.com/) API Key（网页搜索）
- [百度智能云千帆](https://cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5) API Key（可选，搜索失败时兜底）
- [DeepSeek](https://platform.deepseek.com/) API Key（LLM）

### 2. 安装

```bash
git clone https://github.com/wushuangasdf-maker/deepreseach-lite.git
cd deepreseach-lite
pip install -r requirements.txt
```

### 3. 配置

创建 `.env` 文件（已加入 `.gitignore`，不会提交到仓库）：

```env
DeepSeek_API="sk-your-deepseek-key"
BoCha_API="sk-your-bocha-key"
Baidu_API="bce-v3-your-baidu-qianfan-key"
```

### 4. 使用

**命令行**：

```bash
# 标准研究（推荐）
python agent/cli.py "2026 年 AI 芯片市场格局"

# 快速模式
python agent/cli.py --depth quick "今天科技圈有什么大新闻"

# 深度模式
python agent/cli.py --depth deep "量子计算对现有加密体系的冲击"
```

**HTTP 服务**：

```bash0
...........0uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```
| 端点 | 方法 | 说明 |
|------|------|------|
| `/research` | `POST` | 创建并启动研究任务 |
| `/research` | `GET` | 列出最近的任务 |
| `/research/{task_id}` | `GET` | 查询单个任务状态 |
| `/research/{task_id}/stream` | `GET` | SSE 实时进度流 |
| `/research/{task_id}/report` | `GET` | 获取完整报告 |
| `/health` | `GET` | 健康检查 |

## 🎚️ 研究深度

| 深度 | 说明 | max_turns | force_report_at |
|------|------|-----------|-----------------|
| `quick` | 单轮快搜，秒级出结果 | 5 | 3 |
| `standard` | 两轮 + 交叉验证，默认推荐 | 12 | 8 |
| `deep` | 三轮深挖 + 多角度验证 | 20 | 14 |

## 🛠️ 工作原理

1. **规划阶段** — LLM 将研究课题拆解为 N 个子问题，每个子问题配有建议搜索词
2. **串行研究** — 逐项研究子问题，每项 1-2 轮搜索（评分 ≥ 75 一轮通过，否则追搜）
3. **渐进式摘要** — 子问题 > 5 个时启用，每项完成后压缩上下文为摘要笔记
4. **全局汇总** — 全部子问题完成后，LLM 总结所有发现
5. **报告生成** — 按模板撰写 Markdown 报告，调用 `save_report_tool` 保存到 `reports/`

## 📄 许可证

MIT
