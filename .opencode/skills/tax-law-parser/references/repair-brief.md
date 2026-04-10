# Repair Brief

repair brief 是诊断工具，不是修复工具。

脚本负责：

- 跑测试
- 汇总 compile / run / validate / compare
- 计算结构质量指标
- 给出修复优先级建议

OpenCode agent 负责：

- 阅读 brief
- 结合 `repair-playbook.md` 决定该改 registry、overlay 还是 family base
- 直接修改 profile / overlay Python
- 重新测试

主路径不允许脚本直接调模型修代码。
