# tests/ — 回归测试语料（故意埋了问题，请勿"修复"）

`fixtures/` 里的冗余是**故意埋的**已知问题样本，供 `scripts/kb_slim_selftest.py` 断言检出能力——SKILL.md §十四「真空绿的正解」的落地。

- 改样本 = 改断言基准：必须同步改 `fixtures/expected.json`
- 这些文件**不是**本仓的内容文档，瘦身审查、脱敏直觉都别往这儿招呼
- 跑法：`python scripts/kb_slim_selftest.py`（退出码 0 = 全过）
