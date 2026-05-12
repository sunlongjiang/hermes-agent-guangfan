---
plan: 16-00-foundation
phase: 16
status: complete
completed: 2026-05-12
commits:
  - 0332ed5 feat(16-00): add persist_raw_predictions helper + unit tests (D-12)
  - 1246711 feat(16-00): extend to_dspy_examples to include difficulty field (D-11)
  - 1b75cd6 feat(16-00): wire persist_raw_predictions into evolve_tool_params CLI (D-12)
  - 4097bf8 feat(16-00): wire persist_per_tool_rates + persist_raw_predictions into evolve_tool_descriptions CLI (D-12)
  - ec1aa68 feat(16-00): add _score_with_predictions + wire persist helpers into evolve_tool_reasoning CLI (D-12)
key-files:
  created:
    - tests/tools/test_persist_raw_predictions.py
  modified:
    - evolution/tools/tool_metric.py
    - evolution/tools/tool_dataset.py
    - evolution/tools/evolve_tool_params.py
    - evolution/tools/evolve_tool_descriptions.py
    - evolution/tools/evolve_tool_reasoning.py
    - tests/tools/test_tool_dataset.py
    - tests/tools/test_evolve_tool_params_cli.py
    - tests/tools/test_evolve_tool_descriptions.py
    - tests/tools/test_evolve_tool_reasoning.py
---

## Wave 0 — 数据基础

实现 Phase 16 dashboard 所需的 metrics.json schema 落地：raw_predictions 列表 +
三 CLI 统一接 persist_per_tool_rates/persist_raw_predictions 双 helper。

### D-12 Schema 决议

`raw_predictions = list[dict]`，每条 record 含且仅含四个 key：
- `correct_tool: str` — 数据集 ground truth
- `selected_tool: str` — 模型实际选择
- `difficulty: str` — `"easy" | "medium" | "hard"`，缺失或 None 时回退 `"medium"`
- `num_available_tools: int` — `len(confuser_tools) + 1`（D-11，无 available_tools 字段）

helper 实现镜像 `persist_per_tool_rates` 不可变模式：shallow copy 入参 metrics，
None 容错，按 record 严格清洗字段（额外 key 不泄漏，None 强转 `""`/`0`/`"medium"`）。
当 `len(raw_predictions) > 2000` 时 stdout 黄色 warning，但不截断。

### Open Question 决议

- **OQ-1（D-12 amend 范围）**：用户已锁定「三 CLI 同时接两 helper」。`evolve_tool_descriptions`
  与 `evolve_tool_reasoning` 之前完全没接 `persist_per_tool_rates` —— 本 wave 同时新接两 helper，
  确保 dashboard 启动时 desc / reasoning 两 CLI 的 run 都能读到 per_tool 数据。
- **OQ-2（num_available_tools 公式）**：采用 `len(confuser_tools) + 1`。代码库 `ToolSelectionExample`
  没有 `available_tools` 字段，`confuser_tools` 是切片源，+1 代表正确工具自身。
- **OQ-3（_evaluate_holdout 签名）**：保持不变。在外部 zip `holdout × evolved_tool_pairs`
  构造 raw_preds，避免修改 Phase 13 已稳定的内部接口。

### Out-of-scope（W4 / Out-of-scope §6 同步）

- 老的 `FAILED_*/` run 不被回填。FAILED 分支（line 356-369 in
  `evolve_tool_descriptions`）不被注入 metrics_extra。`evolve_tool_reasoning`
  失败路径 metrics 走原 schema（不含 raw_predictions）。
- D-12 amend 仅针对未来新跑的 run；历史 run 仍走 D-08 dropped_runs fallback。
  两策略并存，无冲突。

### Continuation 记录（操作纪要）

原始 executor 在 Task 4 中途因 Claude API socket 超时（`The socket connection was closed
unexpectedly`）而中断。已落地的 3 个提交（Tasks 1-3，commits 0332ed5/1246711/1b75cd6）
仍在 orphan worktree branch `worktree-agent-a6ad7907514a303a0` 上完整可见。

第一次 continuation 子代理因 Claude Code 子代理沙盒未授权 Bash 而立即终止。
Orchestrator 进入 orphan worktree 直接接续：
- 丢弃 task 4 的部分未提交 diff（重新按 plan 严格实现）
- 验证 3 个继承提交的测试集（8 tests）全绿
- Task 4 - evolve_tool_descriptions 接两 helper（commit 4097bf8）
- Task 5 - evolve_tool_reasoning 加 _score_with_predictions + 接两 helper（commit ec1aa68）
- 写本 SUMMARY.md

整个 plan 5 个 task 全部落地，`pytest tests/tools/` 217 passed / 1 skipped。

### W1 fix 说明（plan acceptance gate 微差异）

Plan 的 `_safe_score 总调用数为 2` gate 期望 grep 输出 `2`，但实际 grep 输出 `3`。
原因：grep 命令 `grep -c '_safe_score('` 同时匹配函数定义行
`def _safe_score(module: Any, examples: list, lm: Any) -> float:`，
未过滤掉。语义意图（full holdout 不再用 _safe_score；ambiguous 保留两调用）已正确落地：

| Line | 调用形态 |
|------|----------|
| 470  | `th_off_full, tool_pairs_off, _ = _score_with_predictions(...)` |
| 471  | `th_on_full, tool_pairs_on, raw_preds_on = _score_with_predictions(...)` |
| 472  | `th_off_ambig = _safe_score(baseline_module, ambiguous_subset, lm)` ← 保留 |
| 473  | `th_on_ambig = _safe_score(optimized_module, ambiguous_subset, lm)` ← 保留 |
| 684  | `def _safe_score(module: Any, ...)` ← 函数定义 |

Phase 16 Wave 1+ 可读 `metrics["raw_predictions"]` 做 difficulty 分桶 / 切片分析；
dropped_runs fallback 仅作用于 D-08 历史 run。Wave 0 数据基础完成。
