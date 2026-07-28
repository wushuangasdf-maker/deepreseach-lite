# 阶段 3 验证：测试规划阶段能否正常运行
from agent.agents import deep_research
test1=input("请输入问题：")
# 用快速模式跑，只看规划阶段输出（在 verbose 下能看到拆解结果）
result = deep_research(test1, max_turns=5, force_report_at=3, verbose=True)