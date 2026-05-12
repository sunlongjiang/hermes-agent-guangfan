---
status: partial
phase: 15-think-augmented-tool-selection
source: [15-VERIFICATION.md]
started: "2026-05-12T07:09:32Z"
updated: "2026-05-12T07:09:32Z"
---

## Current Test

[awaiting human testing]

## Tests

### 1. 真实 LM API + hermes-agent 仓库下完整 CLI 运行
expected: exit code 0 或 1（THINK_AB_FAILED 为合理失败）;`output/tools_reasoning/<ts>/` 含 4 文件（metrics.json / reasoning_prompt.txt / diff.txt / ab_comparison.json）;metrics.json 含 think_on_score / think_off_score / ambiguous_think_on / ambiguous_think_off / latency_stats / think_ab_gate 全字段
why_human: 需要真实 LM API key 与 $2 预算;CI 不具备此条件。CR-01~CR-04 BLOCKER 在真实运行下可能导致 ab_comparison.json latency 标签错位、V1Gate 静默 PASS、--ambiguous-only three-AND 退化、cost tracker inf 中止 — 需要人工核验这些场景在实际运行中是否触发
result: [pending]

### 2. --ambiguous-only 标志退化场景验证 (CR-03)
expected: full_regression_delta 与 ambiguous_delta 有数值差异,或 CLI 打印警告说明 full_regression gate 已失效
why_human: 当前代码中 --ambiguous-only 时 eval_holdout==ambiguous_subset,导致两个 delta 完全相同,three-AND 退化为 two-AND;需要人工决策是否接受此限制或要求修复
result: [pending]

### 3. inf cost 注入场景验证 (CR-04)
expected: CostTracker 抛出 ValueError 或返回 fallback 而非累加 inf
why_human: 自动测试已 mock 了 cost path,inf 路径未被测试覆盖;需要人工决定是否补测或视为可接受风险
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
