---
phase: 17
plan: 03
subsystem: prompts
tags: [ab-baseline, soft-gate, metrics-schema, joint-optimization, w3-explicit-delta, w6-full-budget]
requires:
  - evolution/prompts/evolve_prompt_sections.py (Plan 17-02: EPSILON_PP constant + _resolve_effective_mode helper + joint pipeline + Click --mode flag)
  - evolution/prompts/prompt_module.py (Plan 17-01: JOINT_SENTINEL + set_joint_mode + named_predictors override)
  - dspy>=3.0 (GEPA component_selector="round_robin" for per-section A/B baseline)
provides:
  - evolution/prompts/evolve_prompt_sections.py:evolve() inline A/B baseline block (lines 546-657, after holdout eval, before report results)
  - evolution/prompts/evolve_prompt_sections.py:metrics.json schema extension (5 new fields gated on effective_mode == "joint")
  - evolution/prompts/evolve_prompt_sections.py:roundrobin_baseline副本文件 persistence (D-OUT-01 shared-prefix layout)
  - tests/prompts/test_evolve_prompt_sections_cli.py:TestABBaseline (3 integration tests with BLOCKER-1 + BLOCKER-2 fixes)
affects:
  - tests/prompts/test_evolve_prompt_sections.py::TestEvolve::test_evolve_orchestration_order: ONE assertion updated — PromptModule instantiation count is now 3 in joint mode (main + holdout baseline + A/B baseline), was 2 before Plan 17-03.
  - tests/prompts/test_evolve_prompt_sections_cli.py::TestJointPipeline::test_joint_mode_default_calls_gepa_with_component_selector_all: assertion updated to inspect ALL GEPA call_args (not just last) since A/B baseline also instantiates GEPA per-section. Total compile calls now `1 + N` (joint + A/B per-section).
tech-stack:
  added: []
  patterns:
    - Inline A/B baseline pattern — fresh `PromptModule(original_sections)` per Pitfall 4 (no joint mutation pollution); per-section for-loop mirrors round-robin legacy branch; W6 budget = `iterations*50` per section (D-AB-04, NOT compressed, 1:1 vs `--mode round-robin` legacy single-arg formula).
    - Soft-gate pattern (Phase 16 D-13 mirror) — `[yellow]` stdout warning + NO exit + NO blocking when `evolved_score < roundrobin_baseline_score - EPSILON_PP`; `[green]` success otherwise. Warning text contains 3 numbers (joint_score / rr_baseline / delta_pp) + "review before deploying" guidance.
    - W3 dual-delta semantics — `improvement` (= evolved - baseline_unoptimized) stays untouched; new `joint_vs_roundrobin_delta_pp` (= joint_score - rr_baseline_score) is a DISTINCT field with comment block disambiguating the two; downstream dashboards cannot conflate.
    - Mode-gated metrics fields — `mode` field always written; joint-only fields (`joint_score / roundrobin_baseline_score / epsilon_pp / joint_vs_roundrobin_delta_pp / ab_elapsed_seconds`) explicitly gated on `effective_mode == "joint" and roundrobin_baseline_score is not None`.
    - D-OUT-01 shared-prefix file layout — joint mode writes `roundrobin_baseline_evolved_sections.json` + `roundrobin_baseline_diff.txt` SIBLING to `evolved_sections.json` + `diff.txt`; NO `baseline/` subdir; round-robin mode skips them.
    - BLOCKER-1 fix in tests — `PromptBehavioralExample` fixture uses real dataclass fields only (`section_id` / `user_message` / `expected_behavior` / `difficulty`); `task_input` is NEVER used (that's a dspy.Example attribute from `to_dspy_examples()` mapping).
    - BLOCKER-2 fix in tests — `PromptModule` patched as factory (`side_effect=_make_spy_module`) returning `MagicMock(wraps=real_PromptModule)` with `__call__` returning fake `dspy.Prediction` (no real ChainOfThought LM calls); `score_sequence` via `metric.side_effect` deterministically controls A/B holdout scoring.
key-files:
  created: []
  modified:
    - evolution/prompts/evolve_prompt_sections.py (682 → 823 lines; +141 net)
    - tests/prompts/test_evolve_prompt_sections.py (264 → 271 lines; +7 net — one assertion updated, fixture untouched)
    - tests/prompts/test_evolve_prompt_sections_cli.py (286 → 591 lines; +305 net — entire TestABBaseline class)
decisions:
  - "D-AB-01 (inline A/B): Same-CLI-process round-robin baseline runs AFTER joint holdout eval. Fresh `PromptModule(original_sections)` per Pitfall 4 (no mutation pollution from joint compile)."
  - "D-AB-02 (soft gate): [yellow] stdout warning when joint regresses past EPSILON_PP; NO exit code change, NO constraint validation block, NO evolved_sections.json blocking. Phase 16 D-13 dashboard pattern mirror."
  - "D-AB-03 (epsilon constant): EPSILON_PP = 0.01 module constant (defined Plan 17-02 line 42); NOT a CLI flag — fixed 1pp threshold balances LLM-judge variance vs deployment safety. Future phase can parameterize if holdout grows to ≥50 examples."
  - "D-AB-04 (full budget, W6 revision): A/B baseline per-section budget = iterations*50 — NO compression, 1:1 with round-robin legacy single-arg formula. A/B must be symmetric to be valid evidence."
  - "D-OUT-01 (shared-prefix layout, resolved decision 3): NO baseline/ subdir; baseline副本 files use roundrobin_baseline_ prefix sibling to joint main artifacts."
  - "D-OUT-02 + W3 (metrics schema): 5 new fields, joint-mode-only — mode/joint_score/roundrobin_baseline_score/epsilon_pp/joint_vs_roundrobin_delta_pp. W3 revision added joint_vs_roundrobin_delta_pp as the EXPLICIT A/B delta to disambiguate from `improvement` (vs unoptimized baseline)."
  - "D-OUT-03 (diff.txt zero codechange): _generate_diff() handles multi-section naturally; joint main diff.txt + baseline副本 diff.txt both use same helper."
  - "D-OUT-04 (no regression_dashboard touch): metrics.json schema additions are forward-compatible; future Phase 22+ dashboard can consume `mode` field for joint vs round-robin bucketing without code changes here."
  - "Resolved BLOCKER-1 (test fixture): PromptBehavioralExample dataclass has section_id/user_message/expected_behavior/difficulty/source (per evolution/prompts/prompt_dataset.py L33-51); fixture never references `task_input` (which is the dspy.Example attribute that `to_dspy_examples()` injects from user_message)."
  - "Resolved BLOCKER-2 (test PromptModule patch): patch PromptModule as a side_effect factory returning spy modules wrapping real instances. Per-call new spy ensures all 3 PromptModule instantiations (main + holdout baseline + A/B baseline) get independent spies. __call__ override → fake dspy.Prediction avoids real ChainOfThought LM calls in baseline_module + ab_baseline_module holdout scoring."
  - "Test scoring sequence design: metric calls in holdout eval are INTERLEAVED (baseline then evolved per example); A/B holdout is SEQUENTIAL. score_sequence pattern = `[baseline, evolved] * n_holdout + [ab_score] * n_holdout`."
  - "Test rich-wrap defensive normalization: result.output.split() ↔ ' '.join(...) collapses rich's terminal-width line wrapping so 'review before deploying' phrase matches across CliRunner's default 80-char terminal."
metrics:
  duration_seconds: 0
  duration_human: "(commit timestamps: 58bee3a → 00a4134)"
  completed: 2026-05-15
  tasks_completed: 2
  files_modified: 3
  files_created: 0
  lines_added: 453
  commits: 2
  tests_added: 3
  tests_total_in_file: 7
  full_suite_status: "513 passed, 1 skipped, 1 xfailed (zero regression vs Plan 17-02 baseline 510; net +3 new TestABBaseline tests)"
---

# Phase 17 Plan 03: Inline A/B Baseline + Soft Gate + Metrics Schema Summary

One-line: 把 Plan 17-02 的 joint pipeline 补上 inline round-robin A/B baseline（fresh `PromptModule(original_sections)` + per-section `iterations*50` budget + same holdout）+ 软门 `[yellow]` 警告（W3 双 delta 语义,joint_vs_roundrobin_delta_pp 独立字段）+ metrics.json 5 新字段 + D-OUT-01 shared-prefix `roundrobin_baseline_*.{json,txt}` 副本落盘 — 完成 PMPT-V2-01 success criterion 3（joint ≥ round-robin on holdout 的可证伪护栏）。

## Scope

- `evolve_prompt_sections.py` 在 Step 9（holdout eval）完成后追加 Step 9.5（inline A/B baseline）+ Step 9.6（soft gate）+ Step 11.5（baseline 副本落盘）。
- `metrics.json` schema 扩展 — `mode` 字段始终写，joint-only 4 字段（`joint_score / roundrobin_baseline_score / epsilon_pp / joint_vs_roundrobin_delta_pp`）+ `ab_elapsed_seconds` 仅在 `effective_mode == "joint"` 时写入。
- 新增 `TestABBaseline` 测试类（3 tests）— BLOCKER-1 修复（fixture 字段）+ BLOCKER-2 修复（PromptModule factory spy）双管齐下,使 fake-LM mock 链覆盖 baseline + evolved + A/B 三个 holdout 评分,严格断言软门触发/不触发/round-robin skip 三类场景。

## Implementation Details

### `evolution/prompts/evolve_prompt_sections.py` (682 → 823 lines)

| Region | Change | Lines (final) |
|--------|--------|---------------|
| 9.5 Joint mode inline A/B baseline block — fresh `PromptModule(original_sections)` + per-section for-loop + score on same holdout | NEW(D-AB-01/02/03/04) | 546-635 |
| 9.6 Soft gate (W3 dual-delta — `delta_pp` for warning text, `joint_vs_roundrobin_delta_pp` for metrics) + `[yellow]/[green]` console.print | NEW(D-AB-02 + W3) | 637-657 |
| metrics dict — `mode: effective_mode` always written + joint-only block adds 5 fields | MODIFY(D-OUT-02 + W3) | 705-724 |
| 11.5 Joint mode persist baseline 副本文件(shared-prefix layout) — `roundrobin_baseline_evolved_sections.json` + `roundrobin_baseline_diff.txt` | NEW(D-OUT-01) | 733-746 |

**关键代码片段:**

A/B baseline per-section for-loop(`component_selector="round_robin"`):

```python
for ab_sid in ab_baseline_module._section_ids:
    ab_baseline_module.set_active_section(ab_sid)
    # ... filter dataset by section_id, build temp dataset ...
    ab_optimizer = dspy.GEPA(
        metric=metric,
        max_metric_calls=ab_per_section_budget,  # iterations*50 (D-AB-04 full)
        reflection_lm=ab_reflection_lm,
        component_selector="round_robin",
    )
    ab_baseline_module = ab_optimizer.compile(...)
```

Soft gate(W3 dual-delta):

```python
delta_pp = (roundrobin_baseline_score - evolved_score) * 100
joint_vs_roundrobin_delta_pp = (evolved_score - roundrobin_baseline_score) * 100
if evolved_score < roundrobin_baseline_score - EPSILON_PP:
    console.print(
        f"[yellow]Joint score ({evolved_score:.3f}) below "
        f"round-robin baseline ({roundrobin_baseline_score:.3f}) "
        f"by {delta_pp:.1f}pp — review before deploying[/yellow]"
    )
else:
    console.print(
        f"[green]Joint score ({evolved_score:.3f}) ≥ "
        f"round-robin baseline ({roundrobin_baseline_score:.3f}) "
        f"within epsilon ({EPSILON_PP * 100:.0f}pp)[/green]"
    )
```

metrics.json schema gate:

```python
metrics = {
    "timestamp": timestamp,
    "mode": effective_mode,  # always written
    "iterations": iterations,
    "eval_model": config.eval_model,
    "baseline_score": baseline_score,
    "evolved_score": evolved_score,
    "improvement": improvement,
    # ... existing fields unchanged ...
}
if effective_mode == "joint" and roundrobin_baseline_score is not None:
    metrics["joint_score"] = evolved_score
    metrics["roundrobin_baseline_score"] = roundrobin_baseline_score
    metrics["epsilon_pp"] = EPSILON_PP
    metrics["joint_vs_roundrobin_delta_pp"] = joint_vs_roundrobin_delta_pp
    metrics["ab_elapsed_seconds"] = ab_elapsed
```

### `tests/prompts/test_evolve_prompt_sections_cli.py` (286 → 591 lines)

| Region | Change | Lines (final) |
|--------|--------|---------------|
| `TestABBaseline` 类 NEW(类 docstring 显式列 5 项验证 + BLOCKER-1 / BLOCKER-2 修复说明) | NEW(D-AB / D-OUT 全覆盖) | 304-591 |
| `_ab_patched_run` helper(BLOCKER-1 用 4 必填字段 + BLOCKER-2 PromptModule 工厂 spy + tmp_path cwd 沙盒 + dspy.context patch) | NEW | 330-461 |
| `test_joint_mode_runs_inline_ab_baseline` — metrics.json 5 字段完整性 + 副本文件存在 + GEPA compile count = 1+N | NEW | 464-514 |
| `test_soft_gate_warns_but_does_not_block` — `review before deploying` 在 stdout + exit_code==0 + metrics 字段反映 negative delta | NEW | 516-556 |
| `test_round_robin_mode_skips_ab_baseline_and_extra_files` — RR mode 不写 joint-only 字段 + 不落副本文件 + GEPA compile count = N (无 +1) | NEW | 558-591 |

### `tests/prompts/test_evolve_prompt_sections.py` (264 → 271 lines)

| Region | Change | Lines (final) |
|--------|--------|---------------|
| `test_evolve_orchestration_order` 中 `assert mock_module_cls.call_count == 2` → `== 3` + 注释说明 Plan 17-03 引入第 3 个 PromptModule(A/B baseline) | MODIFY(Rule 1 fix — task-induced) | 166-174 |

## metrics.json Schema Comparison (W3 final)

| Field | round-robin mode | joint mode |
|-------|-----------------|-----------|
| timestamp | ✓ | ✓ |
| **mode** (NEW) | "round-robin" | "joint" |
| iterations | ✓ | ✓ |
| eval_model | ✓ | ✓ |
| baseline_score (unoptimized prompt) | ✓ | ✓ |
| evolved_score | ✓ | ✓ (= joint_score) |
| improvement (evolved - baseline_unoptimized) | ✓ | ✓ |
| section_count | ✓ | ✓ |
| train_examples / val_examples / holdout_examples | ✓ | ✓ |
| elapsed_seconds | ✓ | ✓ |
| constraints_passed | ✓ | ✓ |
| **joint_score** (NEW, joint-only) | — | ✓ |
| **roundrobin_baseline_score** (NEW, joint-only) | — | ✓ |
| **epsilon_pp** (NEW, joint-only) | — | 0.01 |
| **joint_vs_roundrobin_delta_pp** (NEW, W3 — A/B delta vs round-robin baseline) | — | (joint_score - roundrobin_baseline_score) × 100 |
| **ab_elapsed_seconds** (NEW, joint-only) | — | A/B baseline wall-clock |

**W3 key insight:** `improvement` 与 `joint_vs_roundrobin_delta_pp` 是两个**独立**的语义维度 — 前者是"演化质量 vs 未优化原文"(适用于所有 mode),后者是"joint 优势 vs round-robin legacy"(仅 joint mode)。下游 dashboard 必须分别消费,**不可叠加/混用**。

## Soft-Gate stdout Phrases (for future README/dashboard reference)

Warning(joint < rr - 0.01):
```
[yellow]Joint score (0.500) below round-robin baseline (0.600) by 10.0pp — review before deploying[/yellow]
```

Success(joint ≥ rr - 0.01):
```
[green]Joint score (0.800) ≥ round-robin baseline (0.750) within epsilon (1pp)[/green]
```

## Test Behavior — score_sequence Layout

Tests 用 `metric.side_effect = score_sequence` 控制 holdout 评分。**调用顺序(实际跟代码验证):**

1. Step 9 holdout eval loop:每个 `ex` **interleaved** 调一次 baseline metric + 一次 evolved metric → `[b0, e0, b1, e1, ..., b_n, e_n]`
2. Step 9.5 A/B baseline holdout loop:**sequential** 调每个 holdout example 一次 → `[ab0, ab1, ..., ab_n]`

测试 fixture 4 holdout examples + 3 sections 配方:
- `test_joint_mode_runs_inline_ab_baseline`: `[0.5, 0.8] * 4 + [0.75] * 4` → baseline=0.5, joint=0.8, rr=0.75, **delta=+5pp(joint wins)**
- `test_soft_gate_warns_but_does_not_block`: `[0.4, 0.50] * 4 + [0.60] * 4` → baseline=0.4, joint=0.50, rr=0.60, **delta=-10pp(joint regresses → warn)**
- `test_round_robin_mode_skips_ab_baseline`: `[0.5, 0.7] * 4` → baseline=0.5, evolved=0.7, NO A/B(round-robin mode)

## Deviations from Plan

**1 deviation, all rule-1 (auto-fix bugs caused by current task's changes):**

### [Rule 1 - Test assertion update] `test_evolve_orchestration_order` PromptModule.call_count 期望值

- **Found during:** Task 1 GREEN(初次跑 `pytest tests/prompts/ -v`)
- **Issue:** Existing test `tests/prompts/test_evolve_prompt_sections.py::TestEvolve::test_evolve_orchestration_order` had `assert mock_module_cls.call_count == 2`(main + holdout baseline)。Plan 17-03 在 joint mode 下额外实例化 `ab_baseline_module = PromptModule(original_sections)`,使 joint mode 默认下 count == 3。
- **Fix:** 更新 assertion 为 `== 3` + 增加注释说明 round-robin 仍是 2 / joint 是 3 的 mode 差异
- **Files modified:** tests/prompts/test_evolve_prompt_sections.py L166-174
- **Commit:** 00a4134(与 GREEN 同 commit 内,以保证 RED→GREEN 干净切换)

### [Rule 1 - Test assertion update] `test_joint_mode_default_calls_gepa_with_component_selector_all` mock_gepa.call_args 期望

- **Found during:** Task 1 GREEN
- **Issue:** Existing test 检查 `mock_gepa.call_args.kwargs.get("component_selector") == "all"`,但 `call_args` 只反映**最后一次**调用。Plan 17-03 A/B baseline 在 joint mode 之后又调 `dspy.GEPA(component_selector="round_robin")` N 次,所以 last call 是 "round_robin"。
- **Fix:** 改用 `mock_gepa.call_args_list` 收集所有调用的 `component_selector` → `assert "all" in joint_selectors`。同时把 compile.call_count 期望从 `== 1` 改为 `== 1 + len(fake_sections)`(joint + per-section A/B)。
- **Files modified:** tests/prompts/test_evolve_prompt_sections_cli.py L155-200
- **Commit:** 00a4134

### [Rule 1 - Test soft-gate phrase wrap robustness] rich console line wrap 处理

- **Found during:** Task 2 GREEN(初次跑 `pytest TestABBaseline::test_soft_gate_warns_but_does_not_block`)
- **Issue:** CliRunner 默认 80-char terminal,rich wrap 在 "review before" 后插入 `\n`,使 raw `result.output` 中 "review before deploying" 不连续。
- **Fix:** 用 `output_normalized = " ".join(result.output.split())` 折叠所有空白(包括换行),然后做子串匹配。这是测试侧防御性写法,生产代码 stdout 文案不变。
- **Files modified:** tests/prompts/test_evolve_prompt_sections_cli.py L527-535
- **Commit:** 00a4134

### [Rule 1 - Test score sequence pattern] holdout metric 调用顺序认知修正

- **Found during:** Task 2 GREEN
- **Issue:** 初版 score_sequence 用 `[0.5]*4 + [0.8]*4 + [0.75]*4`,假设 baseline 和 evolved 是分别批跑;实际代码在 holdout loop 中**交替**调 baseline metric → evolved metric per example。所以 `joint_score` 错算成 0.65 而非 0.8。
- **Fix:** 重写 score_sequence 为 `[baseline, evolved] * n_holdout + [ab] * n_holdout` 交替模式,与生产代码 Step 9 实际行为对齐。
- **Files modified:** tests/prompts/test_evolve_prompt_sections_cli.py L469-475 / L520-524 / L562-566
- **Commit:** 00a4134

## Phase 17 全 Plan 对账表(D-* decisions → 实现锚点)

| Decision | Spec | Plan 17-01 anchor | Plan 17-02 anchor | Plan 17-03 anchor |
|----------|------|--------------------|---------------------|----------------------|
| D-RR-01(保留 round-robin) | --mode round-robin 显式 fallback | — | evolve_prompt_sections.py L367-449(Step 6c) | (沿用,未改) |
| D-RR-02(静默切换) | joint default 不打 deprecation | — | Click default="joint" L660 | (沿用) |
| D-RR-03(--section 隐式 RR) | section→round-robin 路由单源 | — | `_resolve_effective_mode` L47-64 | (沿用,A/B 块 gate by `effective_mode == "joint"` 自动同步) |
| D-RR-04(click.Choice) | 白名单 mode 入参 | — | L661 | (沿用) |
| D-AB-01(inline A/B) | fresh PromptModule | — | — | evolve_prompt_sections.py L565 `ab_baseline_module = PromptModule(original_sections)` |
| D-AB-02(soft gate) | yellow 警告 + 不阻断 | — | EPSILON_PP=0.01 L42 | L637-657 + L644 `joint_vs_roundrobin_delta_pp` |
| D-AB-03(epsilon=0.01) | 固定常量,非 flag | — | L42 EPSILON_PP=0.01 | (沿用 + 测试断言) |
| D-AB-04(全 budget,W6 修订) | iterations*50/section,不压缩 | — | — | L554 `ab_per_section_budget = iterations * 50` |
| D-IT-01(GEPA 总轮数语义) | joint=N pass / RR=N×N_sec | — | L271-282 budget compute | (joint 沿用,A/B 用 RR 单参公式) |
| D-IT-02(joint budget 多参公式) | max(iter*50, 3*N_pred)*N_pred | — | L277 | (joint 不变,A/B 用 iter*50 per section) |
| D-IT-03(stdout 预算行) | 3 行预算预估 | — | L196-209 / L289-307 | (沿用,A/B 块也打 1 行预算注释) |
| D-OUT-01(shared-prefix layout) | NO baseline/ subdir | — | — | evolve_prompt_sections.py L733-746 `roundrobin_baseline_*.{json,txt}` |
| D-OUT-02 + W3(metrics 5 字段) | mode/joint/rr/epsilon/joint_vs_rr_delta | — | — | L705-724 |
| D-OUT-03(diff.txt 零改动) | _generate_diff 复用 | — | — | L741-744(joint 主 + baseline 副本同用) |
| D-OUT-04(不改 dashboard) | regression_dashboard 不动 | — | — | (本 plan 范围外,沿用) |

**结论:** Phase 17 三个 plan + 4 类 14 项 decisions 全数落地,W3 修订(joint_vs_roundrobin_delta_pp 显式独立字段)与 W6 修订(D-AB-04 全 budget 1:1)都已在 Plan 17-03 完整体现。

## Phase 17 Success Criteria Compliance

Phase 17 ROADMAP §Success Criteria(3 项):

| # | Criterion | Implementing Plan | Evidence |
|---|-----------|-------------------|----------|
| 1 | PromptModule supports all-sections-active mode | Plan 17-01 | `set_joint_mode(True)` 让 13 (production) / 3 (test fixture) sections 同时 in section_predictors;`named_predictors()` 过滤 selector.predict |
| 2 | GEPA can mutate multiple sections in one pass | Plan 17-02 | `dspy.GEPA(component_selector="all").compile(...)` 单次调用;`test_joint_mode_default_calls_gepa_with_component_selector_all` 断言 PASS |
| 3 | Joint score ≥ round-robin baseline on holdout(可证伪机制) | Plan 17-03 | inline A/B baseline + 软门 + metrics.json 5 字段 + 双方落盘三机制联立,`test_soft_gate_warns_but_does_not_block` 与 `test_joint_mode_runs_inline_ab_baseline` 共同证明软门对正向/负向两种 case 行为正确 |

## Interface Contracts for Phase 18 (Personality Drift Detection)

Phase 18 可消费 Phase 17 的以下接口:

| Symbol / File | Location | Contract for Phase 18 |
|---------------|----------|----------------------|
| `output/prompts/<ts>/metrics.json` | Joint mode artifact | Field `mode` 区分 joint vs round-robin runs;joint runs 含 `joint_score / roundrobin_baseline_score / joint_vs_roundrobin_delta_pp / epsilon_pp` 4 字段,Phase 18 dashboard 可扫描 `output/prompts/` 计算 joint 优势随时间漂移趋势 |
| `output/prompts/<ts>/roundrobin_baseline_evolved_sections.json` | Joint mode artifact (shared-prefix layout) | Phase 18 可对 baseline 副本与 joint 主结果做 cross-mode 文本相似度对比,识别"哪些 section 在 joint 模式下被改得更激进" |
| `EPSILON_PP = 0.01` | `evolution.prompts.evolve_prompt_sections` module-level | Phase 18 若需要类似软门(personality drift),可 `from ... import EPSILON_PP` 复用同一 1pp 阈值或独立常量定义 |
| `_resolve_effective_mode(section, mode)` | line 47 | Phase 18 引入新 mode(如 `--mode joint-with-drift-check`)时复用此 helper,**不要**写新的 mode-conditional 字面量,保持 W1 invariant |

## Verification Results

```bash
# Plan-level verification (verbatim from plan <verification>):
$ grep -c "roundrobin_baseline" evolution/prompts/evolve_prompt_sections.py       # 13 (≥ 5 ✅)
$ grep -q "EPSILON_PP" evolution/prompts/evolve_prompt_sections.py                 # exit 0 ✅
$ grep -q "ab_baseline_module = PromptModule(original_sections)" evolution/prompts/evolve_prompt_sections.py  # exit 0 ✅
$ grep -q "ab_per_section_budget = iterations \* 50" evolution/prompts/evolve_prompt_sections.py              # exit 0 ✅
$ grep -q "joint_vs_roundrobin_delta_pp" evolution/prompts/evolve_prompt_sections.py                          # exit 0 ✅
$ grep -q 'component_selector="round_robin"' evolution/prompts/evolve_prompt_sections.py                      # exit 0 ✅
$ .venv/bin/python -m pytest tests/prompts/test_evolve_prompt_sections_cli.py -v -x                            # 7 passed (Plan 17-02 4 + Plan 17-03 3) ✅
$ .venv/bin/python -m pytest tests/prompts/ -v -x                                                              # 97 passed ✅
$ .venv/bin/python -m pytest tests/ -x -q                                                                       # 513 passed, 1 skipped, 1 xfailed ✅
```

## Threat Model Compliance

| Threat ID | Disposition | Mitigation Outcome |
|-----------|-------------|-------------------|
| T-17-10 (A/B mutate 污染) | mitigate | ✅ `ab_baseline_module = PromptModule(original_sections)` fresh 实例化(L565);测试 1 断言 PromptModule 总实例化 ≥ 2 次(在 joint 模式下实际 3 次) |
| T-17-11 (schema 不一致 KeyError) | mitigate | ✅ `mode` 字段始终写,joint-only 字段显式 gate by `effective_mode == "joint" and roundrobin_baseline_score is not None`(L719);test_round_robin_mode_skips_ab_baseline 显式断言缺失字段 |
| T-17-12 (A/B 成本 2-3×) | accept | ✅ D-AB-04 W6 修订接受 1:1 budget;`--mode round-robin` flag opt-out;Plan 17-02 stdout 预算预估(L289-307)告知用户 |
| T-17-13 (baseline 副本误打包) | accept | ✅ `output/` 已 .gitignore(Phase 12 post-audit 7500abc);shared-prefix `roundrobin_baseline_` 前缀使 commit diff 一目了然 |
| T-17-14 (软门后无审计) | mitigate | ✅ metrics.json 4 字段(`mode / joint_score / roundrobin_baseline_score / joint_vs_roundrobin_delta_pp`)提供完整 audit trail;W3 修订新增 `joint_vs_roundrobin_delta_pp` 字段免去下游自计算 |
| T-17-15 (metric mock 类型) | mitigate | ✅ 测试 score_sequence 都是 float ∈ [0,1],sum/division 正确;`PromptBehavioralMetric` 生产代码已 Phase 9 验证返回 float |

无新 threat surface 引入 — Plan 17-03 是 Plan 17-02 的扩展层,新 I/O 全在 `output/prompts/<ts>/` 边界内,无外部接口、无凭据处理、无新用户输入。

## TDD Gate Compliance

This plan followed the **RED → GREEN** cycle as a single feature(plan type frontmatter `execute`,两个 task 都 `tdd="true"`):

1. **RED gate (commit `58bee3a`):** `test(17-03)` — 新建 `TestABBaseline` 类 3 个 failing 测试,失败原因是 `KeyError: 'mode'` / `"review before deploying"` 缺失 / `joint_vs_roundrobin_delta_pp` 缺失 — 证明 Task 1 生产代码尚未引入对应字段/文案。Test 数 506 → 509(+3 RED)。
2. **GREEN gate (commit `00a4134`):** `feat(17-03)` — 实现 9.5 A/B baseline 块 + 9.6 软门 + metrics schema 扩展 + 11.5 副本落盘。同时 Rule 1 fix 两个上游测试的 PromptModule.call_count / GEPA last-call kwargs 期望、修订 score_sequence 交替模式、rich-wrap stdout 防御性 normalize。结果:97 tests/prompts/ PASS + 513 tests/ PASS,零回归。

No REFACTOR gate needed — GREEN 实现遵循现有代码风格(snake_case、`Optional` 类型提示、Google docstrings、`# ── ──` 区段分隔)。

## Commits

- `58bee3a` test(17-03): add TestABBaseline RED tests for inline A/B + soft gate + metrics schema
- `00a4134` feat(17-03): inline A/B baseline + soft gate + metrics.json 5 new fields

## Self-Check: PASSED

- `evolution/prompts/evolve_prompt_sections.py` exists at 823 lines — FOUND
- `tests/prompts/test_evolve_prompt_sections_cli.py` exists at 591 lines — FOUND
- `tests/prompts/test_evolve_prompt_sections.py` exists at 271 lines — FOUND
- Commit `58bee3a` exists in `git log` — FOUND
- Commit `00a4134` exists in `git log` — FOUND
- All 12 Task 1 grep done-criteria PASS — VERIFIED
- All 11 Task 2 grep done-criteria PASS — VERIFIED
- TestABBaseline 3 tests PASS — VERIFIED
- tests/prompts/ 97 tests PASS — VERIFIED
- Full suite 513 passed + 1 skipped + 1 xfailed, zero regression vs Plan 17-02 baseline 510 + 3 new TestABBaseline tests — VERIFIED
- W1 invariant: `"round-robin" if section else mode` literal still occurs exactly 1 time — VERIFIED
- W2 invariant: joint branch's GEPA.compile() (Plan 17-02 line 357-361) has NO try/except wrapping; comment "NO try/except: loud-fail per W2 invariant / D-15a parity" present — VERIFIED(Plan 17-03 only adds A/B baseline AFTER the joint compile, does not wrap it)
- W3 invariant: `joint_vs_roundrobin_delta_pp` 是 distinct metrics field 且 `improvement` 注释明确两者语义独立 — VERIFIED
- W6 invariant: A/B per-section budget = `iterations * 50`(NOT compressed) — VERIFIED via grep + 测试 dry-run 输出 "max_metric_calls=100/section" (iterations=2)
