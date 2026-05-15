---
phase: 17
plan: 02
subsystem: prompts
tags: [click, cli, gepa, joint-optimization, dspy-component-selector, w1-helper, w2-loud-fail]
requires:
  - evolution/prompts/prompt_module.py (Plan 17-01: JOINT_SENTINEL + set_joint_mode + named_predictors override)
  - dspy>=3.0 (GEPA component_selector="all" support)
  - click>=8.0 (click.Choice for --mode validation)
provides:
  - evolution/prompts/evolve_prompt_sections.py:EPSILON_PP (module constant, 0.01)
  - evolution/prompts/evolve_prompt_sections.py:_resolve_effective_mode (W1 helper)
  - evolution/prompts/evolve_prompt_sections.py:evolve(mode="joint") (new signature parameter)
  - evolution/prompts/evolve_prompt_sections.py:main --mode joint|round-robin flag
  - tests/prompts/test_evolve_prompt_sections_cli.py (4 new CLI integration tests)
affects:
  - tests/prompts/test_evolve_prompt_sections.py: zero regression — all 6 existing tests still PASS without modification (the mock stack does not assert on component_selector, so the new default `mode="joint"` still passes the orchestration-shape assertions).
  - Plan 17-03 (inline A/B branch): can reuse _resolve_effective_mode for any future mode-conditional logic; will consume EPSILON_PP for soft-gate; must preserve W2 loud-fail invariant.
tech-stack:
  added: []
  patterns:
    - W1 helper "_resolve_effective_mode(section, mode) -> str" as single-source-of-truth for D-RR-03 routing (called by both dry-run gate AND main path); literal "round-robin" if section else mode appears exactly once in the file.
    - W2 invariant — joint branch GEPA.compile() has NO try/except wrapping (Phase 13 D-15a "loud GEPA failure" parity); round-robin branch retains its legacy GEPA→MIPROv2 fallback chain.
    - num_predictors-dynamic budget (Resolved decision 4): max(iterations*50, 3*num_predictors) * num_predictors (joint), iterations*50 per section (round-robin); num_predictors computed at runtime after set_joint_mode(True) via len(list(module.named_predictors())).
    - D-IT-03 three-line stdout budget preview ("Joint optimization:", "Round-robin A/B baseline:", "Total est. LM calls:") printed in BOTH --dry-run and main optimization path.
    - Mode fork at Step 6 of evolve(): single-compile joint branch vs per-section for-loop round-robin branch; section_texts dict reused across both branches.
key-files:
  created:
    - tests/prompts/test_evolve_prompt_sections_cli.py (271 lines — 4 tests in 2 classes)
  modified:
    - evolution/prompts/evolve_prompt_sections.py (518 → 682 lines; +164 net)
decisions:
  - "D-RR-04 implementation: click.Choice([\"joint\", \"round-robin\"]) default=\"joint\" — strict whitelist validation at CLI boundary; future hybrid modes can be added without breaking interface."
  - "D-RR-03 (--section X implicit RR) routed through single _resolve_effective_mode helper (W1 revision) — dry-run gate and main path both call the helper; the conditional literal lives in exactly ONE place in the file."
  - "D-IT-02 / Resolved decision 4: joint budget = max(iterations*50, 3*num_predictors) * num_predictors (NOT the CONTEXT.md ×5 hardcoded value); num_predictors retrieved at runtime via len(list(module.named_predictors())) AFTER set_joint_mode(True) so selector is filtered out."
  - "D-IT-03: 3-line stdout budget preview shown BEFORE GEPA.compile in main path AND inside the --dry-run early-return — users see cost estimate before any LM call lands."
  - "W2 invariant (this plan adds; Plan 17-03+ must preserve): joint branch's optimizer.compile() is intentionally NOT wrapped in try/except — Phase 13 D-15a loud-fail parity. The round-robin branch's existing GEPA→MIPROv2 fallback is preserved unchanged."
  - "Test fixture: holdout split intentionally empty in _make_mocked_dataset() — keeps CLI-shape tests free of LM dependencies (baseline_module.forward() in the holdout loop would otherwise require a configured dspy.LM)."
metrics:
  duration_seconds: 0
  duration_human: "(see commits f9b7d16, 1590a28 timestamps)"
  completed: 2026-05-15
  tasks_completed: 2
  files_modified: 1
  files_created: 1
  lines_added: 435
  commits: 2
  tests_added: 4
  tests_total_in_file: 4
  full_suite_status: "510 passed, 1 skipped, 1 xfailed (zero regression vs Plan 17-01 baseline of 506)"
---

# Phase 17 Plan 02: CLI Joint Pipeline Summary

One-line: 把 Plan 17-01 的 `PromptModule` 三态状态机经 Click CLI 暴露 — 新 `--mode joint|round-robin` flag(joint 默认 + 静默切换)+ W1 `_resolve_effective_mode` helper(单一 D-RR-03 路由源)+ W2 loud-fail joint 分支(NO try/except)+ D-IT-03 三行 stdout 预算预估(`max(iter*50, 3*N_pred)*N_pred` 公式),覆盖 ROADMAP §Phase 17 Success Criterion 2(GEPA 单 pass mutate 多 section)。

## Scope

- `evolve_prompt_sections.py` 从 single-mode round-robin per-section CLI 升级为 mode-fork(`--mode joint` 默认 + `--mode round-robin` legacy),通过 click.Choice 严格白名单。
- joint 分支调用 `module.set_joint_mode(True)` 后用 `dspy.GEPA(component_selector="all", max_metric_calls=...).compile(module, trainset, valset)` 一次,覆盖 N 个 section。
- round-robin 分支保留现有 per-section for-loop 与 `GEPA→MIPROv2` fallback,行为零改动。
- 新建 `tests/prompts/test_evolve_prompt_sections_cli.py` 共 2 类 4 测试(CliRunner + fake-GEPA mock 风格),覆盖 joint 默认、round-robin、`--section X` 隐式 RR(D-RR-03)、`--dry-run` 预算预估。

## Implementation Details

### `evolution/prompts/evolve_prompt_sections.py` (518 → 682 lines)

| Region | Change | Lines (final) |
|--------|--------|---------------|
| `EPSILON_PP = 0.01` 常量(Phase 17 / D-AB-03 软门阈值,Plan 17-03 复用) | NEW(module-level,顶部) | 36-42 |
| `_resolve_effective_mode(section, mode) -> str` W1 helper | NEW(D-RR-03 单源路由) | 45-63 |
| `evolve()` 签名追加 `mode: str = "joint"` | MODIFY | 116 (signature line) |
| `evolve()` docstring 追加 `mode` 参数说明 | MODIFY | 128-133 |
| `evolve()` 函数体头部 `effective_mode = _resolve_effective_mode(section, mode)` | NEW(Step 0) | 137 |
| `# ── 3. Dry-run gate` — 三行预算预估(D-IT-03) + helper 调用 | REWRITE(原 L131-150 → L173-209) | 173-209 |
| `# ── 6. Optimization (joint vs round-robin fork)` 块 | REWRITE(原 Step 6 per-section for-loop → mode fork) | 257-450 |
| Step 6a 预算计算块(joint 时 set_joint_mode 后 len(list(named_predictors()))) | NEW | 263-285 |
| Step 6b JOINT 分支(NO try/except,`component_selector="all"`, `seed=0`, `track_stats=True`) | NEW(W2 invariant) | 314-358 |
| Step 6c ROUND-ROBIN 分支(legacy 保留,GEPA→MIPROv2 fallback 完整) | KEEP(从原 L213-283 平移) | 359-450 |
| `@click.option("--mode", ...)` Click decorator | NEW | 633-641 |
| `main(...)` 签名追加 `mode` 参数 + `evolve(... mode=mode)` 调用 | MODIFY | 642-654 |

**关键代码片段:**

`_resolve_effective_mode` helper(W1 single source of truth):

```python
def _resolve_effective_mode(section: Optional[str], mode: str) -> str:
    """Return the effective optimization mode after applying D-RR-03 routing."""
    return "round-robin" if section else mode
```

Step 6a 预算计算(`num_predictors`-dynamic):

```python
if effective_mode == "joint":
    module.set_joint_mode(True)
    num_predictors = len(list(module.named_predictors()))
    joint_budget = max(iterations * 50, 3 * num_predictors) * num_predictors
else:
    num_predictors = len(module._section_ids)
    joint_budget = 0
rr_per_section_budget = iterations * 50
rr_total_budget = rr_per_section_budget * len(module._section_ids)
```

Step 6b JOINT 分支(W2 loud-fail 内嵌注释):

```python
if effective_mode == "joint":
    # W2 invariant: NO try/except wrapping GEPA.compile here. Joint mode
    # follows Phase 13 D-15a "loud GEPA failure" pattern — any exception
    # propagates uncaught to Click main and exits non-zero.
    ...
    optimizer = dspy.GEPA(
        metric=metric,
        max_metric_calls=joint_budget,
        reflection_lm=reflection_lm,
        component_selector="all",
        track_stats=True,
        seed=0,
    )
    # NO try/except: loud-fail per W2 invariant / D-15a parity
    module = optimizer.compile(module, trainset=trainset, valset=valset)
```

### `tests/prompts/test_evolve_prompt_sections_cli.py` (NEW, 271 lines)

| Class | Test | Validates |
|-------|------|-----------|
| TestJointPipeline | `test_joint_mode_default_calls_gepa_with_component_selector_all` | 默认 `--mode joint`:`dspy.GEPA` 被实例化时 `component_selector="all"`,`compile.call_count == 1`,`spy_module.set_joint_mode.assert_called_with(True)`,`set_active_section.call_count == 0` |
| TestJointPipeline | `test_round_robin_mode_compiles_per_section` | `--mode round-robin`:`component_selector != "all"`,`compile.call_count == 3`(= fake_sections 数),`set_active_section.call_count == 3`,`set_joint_mode.assert_not_called()` |
| TestJointPipeline | `test_section_flag_forces_round_robin_even_when_mode_joint` | `--section section_1 --mode joint`:`set_active_section.assert_called_with("section_1")`,`set_active_section.call_count == 1`,`compile.call_count == 1`,`set_joint_mode.assert_not_called()`(D-RR-03 隐式 RR) |
| TestDryRun | `test_dry_run_joint_prints_budget_estimate` | `--dry-run --mode joint --iterations 10`(5 fake sections):stdout 含 3 行预算字串(`Joint optimization:` / `Round-robin A/B baseline:` / `Total est. LM calls:`),`max_metric_calls=2500`(`max(10*50, 3*5)*5 = max(500,15)*5 = 2500`),`mock_gepa.called == False` |

## CLI --mode flag help text (for README reference)

```
  --mode [joint|round-robin]      Optimization mode: 'joint' (default,
                                  optimizes all sections simultaneously via
                                  GEPA) or 'round-robin' (legacy, optimizes
                                  section-by-section). --section <id>
                                  implicitly forces round-robin
                                  single-section even with --mode joint.
```

CLI smoke verification:

```bash
$ .venv/bin/python -c "
from click.testing import CliRunner
from evolution.prompts.evolve_prompt_sections import main
r = CliRunner().invoke(main, ['--help'])
assert '--mode' in r.output
assert 'joint' in r.output
assert 'round-robin' in r.output
print('CLI smoke: PASS')
"
CLI smoke: PASS
```

## `_resolve_effective_mode` Final Location (for Plan 17-03+ Reuse)

- **Location:** `evolution/prompts/evolve_prompt_sections.py` line 47
- **Signature:** `def _resolve_effective_mode(section: Optional[str], mode: str) -> str:`
- **Behavior:** Returns `"round-robin"` when `section` is non-empty(truthy);否则原样返回 `mode`。
- **W1 invariant:** 文件内字面量 `"round-robin" if section else mode` 只在 helper 实现内出现 **正好 1 次**。任何未来 plan(17-03/17-04+)若需要新的 mode-conditional 分支,**MUST** 复用此 helper,不得在 evolve_prompt_sections.py 内引入重复条件表达式。

## Deviations from Plan

None — plan executed exactly as written, with one **operational note**:

**Operational note (not a deviation):** 在初次 Edit 操作时,Edit 工具的绝对路径写入意外命中了**主仓**而非 **worktree** 的 `evolution/prompts/evolve_prompt_sections.py`(主仓与 worktree 共享 git working tree 但是独立路径)。Detected via `wc -l` 与 `git diff` 对比 — 主仓出现了未追踪改动而 worktree 文件没变。Reverted via `git -C <main-repo> checkout -- evolution/prompts/evolve_prompt_sections.py`,然后重新对 worktree 路径执行 Edit。这是 Plan 17-01 SUMMARY 中也提到的相同坑(worktree-mode bash `cd` reset 行为可能导致 Edit 命中错误路径);**本次通过显式 worktree 路径 + 中途的 `wc -l` 双检测早发现早修正。** 没有数据丢失,no impact on plan correctness。

## Interface Contracts for Plan 17-03 (inline A/B branch)

Plan 17-03 在 joint mode optimization 完成后会跑一次 round-robin baseline(inline A/B),消费以下契约:

| Symbol / Pattern | Location | Contract for Plan 17-03 |
|------------------|----------|------------------------|
| `EPSILON_PP: float = 0.01` | `evolution.prompts.evolve_prompt_sections` (module-level) | D-AB-03 软门阈值。Plan 17-03 直接 `from ... import EPSILON_PP` 用作 `if joint_score < roundrobin_score - EPSILON_PP: ... [yellow]warning[/yellow]`。 |
| `_resolve_effective_mode(section, mode)` | line 47 | 若 Plan 17-03 需要在 A/B 块内决策(例如 `--no-ab` flag)继续用此 helper。**W1 invariant:不要在文件内重新写 `"round-robin" if section else mode` 字面量。** |
| `PromptModule(original_sections)` 是 A/B baseline 起点 | Plan 17-03 will use a **fresh** PromptModule, not the joint-optimized one | 因为 joint mode 把 sections 提升为 Predict 实例并被 GEPA 变异;baseline 必须从原始 `original_sections` 重新构造一个 module,call set_active_section per section in for-loop,确保 apples-to-apples 同条件对比。 |
| `module.named_predictors()` 在 joint mode 自动过滤 selector | Plan 17-01 已实现 | Plan 17-03 不要重写 named_predictors;直接相信 `len(list(joint_module.named_predictors())) == N_sections`(N=13 production, 3-5 test fixture)。 |
| **W2 invariant:joint 分支 NO try/except** | line 314-358 (Step 6b) | Plan 17-03 在 evolve() 内追加 A/B 段时,**不要在 joint compile 周围引入 try/except 兜底**;A/B 评分失败应让 Click main 退出非零(D-15a parity)。round-robin baseline 跑失败时可保留软处理。 |
| Empty `dataset.holdout` 路径已存在但未跑 | line 511+ | Plan 17-03 的 A/B 段在 holdout eval **之前**(Step 8 constraints **之后**),复用 dataset.holdout 跑 baseline_module(round-robin) vs module(joint) 两套打分。若 dataset.holdout 为空,Plan 17-03 应优雅降级(打印 warning 而非崩溃)。 |

## Adjustment to `tests/prompts/test_evolve_prompt_sections.py`

None — **零个** existing tests 因为 `mode="joint"` 默认而需要修改。这是因为现有 6 个测试的 mock 链都不断言 `component_selector` 也不计数 `set_active_section/set_joint_mode` 的特定次数,只验证总体调用顺序(extract → module → dataset → GEPA.compile.called → validator),而这套调用顺序在 joint mode 下仍然成立。

具体地:
- `test_evolve_orchestration_order`: assert `mock_gepa.compile.assert_called()` — joint 单次 compile 仍命中此断言。
- `test_section_filter`: assert `calls[0] == call("memory_guidance")` — 这是 D-RR-03 自动路由的副产品,joint default + `--section memory_guidance` → effective_mode=round-robin → 单 set_active_section 调用,仍 PASS。
- `test_dry_run_validates_and_returns`: assert `mock_gepa.assert_not_called()` — dry-run 早 return,joint 模式下 GEPA 同样不调,PASS。

## Verification Results

```bash
# Plan-level verification (verbatim from plan <verification>):
$ grep -q 'click.Choice(\["joint", "round-robin"\])' evolution/prompts/evolve_prompt_sections.py      # exit 0 ✅
$ grep -q 'component_selector="all"' evolution/prompts/evolve_prompt_sections.py                      # exit 0 ✅
$ grep -q "def _resolve_effective_mode" evolution/prompts/evolve_prompt_sections.py                    # exit 0 ✅
$ grep -c "_resolve_effective_mode(section, mode)" evolution/prompts/evolve_prompt_sections.py        # 5 (≥ 2) ✅
$ grep -c '"round-robin" if section else mode' evolution/prompts/evolve_prompt_sections.py            # 1 (exact) ✅
$ grep -q "NO try/except: loud-fail per W2 invariant" evolution/prompts/evolve_prompt_sections.py     # exit 0 ✅
$ grep -c "effective_mode" evolution/prompts/evolve_prompt_sections.py                                 # 12 (≥ 3) ✅
$ .venv/bin/python -m pytest tests/prompts/test_evolve_prompt_sections_cli.py -v -x                    # 4 passed in 6.14s ✅
$ .venv/bin/python -m pytest tests/prompts/ -v -x                                                      # 94 passed in 7.49s ✅
$ .venv/bin/python -m pytest tests/ -x -q                                                              # 510 passed, 1 skipped, 1 xfailed in 16.16s ✅
$ .venv/bin/python -c "from click.testing import CliRunner; from evolution.prompts.evolve_prompt_sections import main; r = CliRunner().invoke(main, ['--help']); assert '--mode' in r.output and 'joint' in r.output and 'round-robin' in r.output"  # exit 0 ✅
```

## Threat Model Compliance

| Threat ID | Disposition | Mitigation Outcome |
|-----------|-------------|-------------------|
| T-17-05 (--mode 输入注入) | mitigate | ✅ `click.Choice(["joint", "round-robin"])` 严格白名单;非法值由 Click 在 argv 解析阶段拒绝。注:CliRunner test 中 invalid mode 直接拿到非零 exit_code 不进入 evolve()。 |
| T-17-06 (--iterations 极值) | accept | ✅ 沿用 Phase 10 决策;Python int 无溢出;预算预估在跑前打印,用户可决定终止。 |
| T-17-07 (joint budget 爆炸) | mitigate | ✅ D-IT-03 3 行预算预估在 GEPA.compile 之前打印(主路径 + dry-run 两路径都打);`--dry-run` 进一步允许零成本验证。 |
| T-17-08 (--hermes-repo 路径) | accept | ✅ 未引入新 IO 边界,继承 Phase 7 read-only 实现。 |
| T-17-09 (测试 fixture 篡改) | accept | ✅ Fixtures 是本地 Python 字面量,无外部输入。 |
| T-17-16 (未来 PR 静默引入 try/except) | mitigate | ✅ 三层防护:(1) joint 分支内嵌注释 "NO try/except: loud-fail per W2 invariant / D-15a parity";(2) Step 6b 头部 5 行 comment 块解释 W2 invariant;(3) 本 SUMMARY 在 "Interface Contracts for Plan 17-03" 中显式标注 "Plan 17-03 不要在 joint compile 周围引入 try/except 兜底"。 |

No new threat surface introduced — Phase 17-02 是 CLI 层 + 测试,无新 IO 边界、新网络调用、新凭据处理。

## TDD Gate Compliance

This plan followed the **RED → GREEN** cycle as a single feature(plan type frontmatter 是 `execute` 而非 `tdd`,但两个 task 都标 `tdd="true"`,所以按 TDD 节奏交付):

1. **RED gate (commit `f9b7d16`):** `test(17-02)` — 新建 `tests/prompts/test_evolve_prompt_sections_cli.py` 4 个 failing 测试,验证 4 项失败原因均为 "No such option: --mode" 等预期错误。
2. **GREEN gate (commit `1590a28`):** `feat(17-02)` — 实现 `evolve_prompt_sections.py` 改造(EPSILON_PP 常量 + _resolve_effective_mode helper + mode fork + dry-run budget preview + --mode CLI flag)。同 commit 内对测试 fixture 做了 GREEN-supporting 微调(holdout=[] 跳过 LM-dependent 评估;spy_module.return_value 兜底)。验证 4 PASS + 94 prompts 测试 PASS + 510 全套件 PASS。

No REFACTOR gate needed — GREEN 实现遵循现有代码风格(snake_case、Optional 类型提示、Google docstrings、`# ── ──` 区段分隔)。

## Commits

- `f9b7d16` test(17-02): add CLI integration tests for joint mode + --mode flag
- `1590a28` feat(17-02): wire joint mode CLI pipeline with --mode flag + budget preview

## Self-Check: PASSED

- `evolution/prompts/evolve_prompt_sections.py` exists at 682 lines — FOUND
- `tests/prompts/test_evolve_prompt_sections_cli.py` exists at 271 lines — FOUND
- Commit `f9b7d16` exists in `git log` — FOUND
- Commit `1590a28` exists in `git log` — FOUND
- `--mode` flag importable + visible in CLI --help — VERIFIED
- 4 new tests collected in target file, all PASS — VERIFIED
- Full suite: 510 passed + 1 skipped + 1 xfailed, zero regression vs Plan 17-01 baseline of 506 (delta = +4 new tests) — VERIFIED
- All 13 plan grep-based done-criteria checks return expected counts — VERIFIED
- W1 invariant: `"round-robin" if section else mode` literal occurs **exactly 1** time in the file — VERIFIED
- W2 invariant: joint branch's GEPA.compile() has NO try/except wrapping; comment "NO try/except: loud-fail per W2 invariant / D-15a parity" present — VERIFIED
