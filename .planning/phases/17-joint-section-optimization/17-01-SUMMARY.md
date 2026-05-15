---
phase: 17
plan: 01
subsystem: prompts
tags: [dspy, gepa, prompt-evolution, joint-optimization, state-machine, pitfall-1-fix]
requires:
  - evolution/prompts/prompt_module.py (Phase 8 baseline state machine + selector)
  - dspy>=3.0 (named_predictors() auto-traversal of dict[str, Predict])
provides:
  - evolution/prompts/prompt_module.py:JOINT_SENTINEL
  - evolution/prompts/prompt_module.py:PromptModule.set_joint_mode
  - evolution/prompts/prompt_module.py:PromptModule._frozen_predictor_ids
  - evolution/prompts/prompt_module.py:PromptModule.named_predictors (override)
affects:
  - 14 existing tests in tests/prompts/test_prompt_module.py — 13 unchanged, 1 renamed (excludes→includes) with inverted assertion to match Pitfall 1 fix semantics
  - Phase 9/10 (downstream prompt pipeline tests): zero regression confirmed (full suite 506 passed)
tech-stack:
  added: []
  patterns:
    - JOINT_SENTINEL three-state machine (None / "__JOINT__" / real sid) — extends Phase 8 binary state machine
    - Override named_predictors() to filter selector.predict via _frozen_predictor_ids set — analog: dspy.Module.named_predictors() yield-pattern
    - Pitfall 1 fix in _build_frozen_context: active text now read from section_predictors[active].signature.instructions (not _frozen_instructions[active])
    - Pitfall 3 auto-demote guard in set_active_section: detect JOINT_SENTINEL and call set_joint_mode(False) before original demote logic
key-files:
  created: []
  modified:
    - evolution/prompts/prompt_module.py (156 → 261 lines)
    - tests/prompts/test_prompt_module.py (224 → 388 lines)
decisions:
  - "Resolved Decision 1 (Pitfall 1 fix): forward() in single-active mode now concats active section's CURRENT Predict.signature.instructions into frozen_context. Round-robin mode no longer no-ops GEPA mutations."
  - "Resolved Decision 2 (selector freeze): named_predictors() in joint mode filters selector.predict via _frozen_predictor_ids set. Only the 3 (fixture) / 13 (production) section_predictors entries are GEPA-mutable; selector instructions remain stable."
  - "Pitfall 3 mitigation: set_active_section() detects JOINT_SENTINEL and auto-demotes via set_joint_mode(False) before original demote logic. No KeyError when mixing joint/round-robin calls."
  - "Idempotency: set_joint_mode(True) on a module already in JOINT_SENTINEL returns immediately (no duplicate promotion, no side effects)."
metrics:
  duration_seconds: 388
  duration_human: "6m 28s"
  completed: 2026-05-15T07:49:15Z
  tasks_completed: 2
  files_modified: 2
  lines_added: 282
  commits: 2
  tests_added: 7
  tests_renamed: 1
  tests_total_in_file: 21
  full_suite_status: "506 passed, 1 skipped, 1 xfailed (zero regression)"
---

# Phase 17 Plan 01: Joint Section Optimization (PromptModule State Machine) Summary

One-line: 扩展 `PromptModule` 三态状态机 — None / `JOINT_SENTINEL` / 单 sid — 解锁 GEPA `component_selector="all"` 多 Predict 联合优化,并顺手修复 Pitfall 1（active section 文本未流入 selector）+ Pitfall 3（joint→single 切换 KeyError）+ Resolved Decision 2（selector freeze）。

## Scope

- 让 `PromptModule.set_joint_mode(True)` 把全部 N 个 section 同时提升为 `dspy.Predict` 实例,挂到 `section_predictors: dict[str, Predict]`,通过 `named_predictors()` 暴露给 GEPA 的 `component_selector='all'`。
- `forward()` 三态分发: None 抛 `RuntimeError`(向后兼容)、`JOINT_SENTINEL` 全 section concat、单 sid round-robin 含 active text(Pitfall 1 fix)。
- `named_predictors()` 在 joint mode 下过滤 `selector.predict`,使其在 GEPA 优化时保持冻结(Resolved Decision 2)。

## Implementation Details

### `evolution/prompts/prompt_module.py` (156 → 261 lines)

| Region | Change | Lines (final) |
|--------|--------|---------------|
| `JOINT_SENTINEL = "__JOINT__"` 常量块 | NEW(模块顶部 `# ── Constants ──` 节) | 14-21 |
| `__init__` 末尾 `_frozen_predictor_ids: set[str] = {"selector.predict"}` | NEW(Resolved Decision 2 selector freeze 数据结构) | 80-83 |
| `set_active_section` 中的 "Move current active back to frozen" 块 | MODIFY: 加 `if self._active_section == JOINT_SENTINEL: self.set_joint_mode(False)` 自动退化 guard(Pitfall 3 fix) | 96-104 |
| `set_joint_mode(active: bool = True)` 方法 | NEW(主入口:active=True 全 promote,active=False 全 demote,JOINT_SENTINEL 时 active=True 返 idempotent) | 116-156 |
| `forward()` | REWRITE: 三态分发 docstring 显式化,行为上 None 仍抛 `RuntimeError`,但消息加 "or set_joint_mode()" 指引(Pitfall 8 防御) | 158-191 |
| `_build_frozen_context()` | REWRITE: 三分支拼接(JOINT_SENTINEL → all Predict、active → Predict、frozen → string),Pitfall 1 修复在 round-robin 路径 | 193-220 |
| `named_predictors()` 覆写 | NEW(joint mode 时跳过 `_frozen_predictor_ids` 中的 name) | 222-236 |
| `get_evolved_sections()` | UNCHANGED(L238-261)— 现有 `if sid in self.section_predictors` 二选一已天然兼容 joint mode 全 Predict 分支 | — |

**关键代码片段:**

`set_joint_mode` 入口 idempotent guard + 全 promote 循环:

```python
def set_joint_mode(self, active: bool = True) -> None:
    if active:
        if self._active_section == JOINT_SENTINEL:
            return  # idempotent
        if self._active_section is not None:
            pred = self.section_predictors.pop(self._active_section)
            self._frozen_instructions[self._active_section] = pred.signature.instructions
        for sid in list(self._frozen_instructions.keys()):
            text = self._frozen_instructions.pop(sid)
            sig = dspy.Signature("section_text -> confirmation", instructions=text)
            self.section_predictors[sid] = dspy.Predict(sig)
        self._active_section = JOINT_SENTINEL
    else:
        for sid in list(self.section_predictors.keys()):
            pred = self.section_predictors.pop(sid)
            self._frozen_instructions[sid] = pred.signature.instructions
        self._active_section = None
```

`_build_frozen_context` 三分支(Pitfall 1 修复在 active 分支):

```python
for sid in self._section_ids:
    if self._active_section == JOINT_SENTINEL:
        text = self.section_predictors[sid].signature.instructions
    elif sid == self._active_section:
        text = self.section_predictors[sid].signature.instructions  # Pitfall 1 fix
    else:
        text = self._frozen_instructions[sid]
    parts.append(f"[{sid}]: {text}")
```

`named_predictors` 覆写 — Resolved Decision 2 selector freeze:

```python
def named_predictors(self):
    for name, pred in super().named_predictors():
        if self._active_section == JOINT_SENTINEL and name in self._frozen_predictor_ids:
            continue
        yield name, pred
```

### `tests/prompts/test_prompt_module.py` (224 → 388 lines)

| Region | Change | Lines (final) |
|--------|--------|---------------|
| `TestFrozenContext::test_frozen_context_excludes_active` | RENAME → `test_frozen_context_includes_active`;反转 assertion 为 `"[memory_guidance]:" in context` + 显式 active text 内容存在;追加 Phase 17/Pitfall 1 注释(Resolution 1 的语义变更) | 111-130 |
| `TestJointMode` 新类 | NEW: 7 个测试方法 1:1 对应 Task 1 `<behavior>` 块 Test 1-7(Test 8 仅声明与现有 `test_forward_without_active_raises` 同语义,不重复编码) | 240-388 |

**新增测试一览(全部 PASS):**

| # | Method | Validates |
|---|--------|-----------|
| 1 | `test_set_joint_mode_exposes_all_predictors` | promote 后 `len(section_predictors) == 3`、`_frozen_instructions == {}`、`_active_section == JOINT_SENTINEL`、各 Predict 保留原 instructions |
| 2 | `test_set_joint_mode_idempotent` | 连调两次 `set_joint_mode(True)` 不抛、state 不变 |
| 3 | `test_set_joint_mode_false_demotes_all` | `set_joint_mode(False)` 后 `section_predictors == {}`、`_frozen_instructions` 含 3 段、`_active_section is None` |
| 4 | `test_joint_then_set_active_section_auto_demotes` | Pitfall 3 fix: joint→single 不抛 KeyError、active 切到目标 sid、其它两段回到 frozen |
| 5 | `test_named_predictors_in_joint_mode_excludes_selector` | W4 严格校验: `named_predictors()` 返回 exactly 3 项(13 production), `"selector.predict" not in names` |
| 6 | `test_forward_in_joint_mode_uses_all_section_texts` | joint forward 的 `frozen_context` kwarg 包含全 3 段前缀 `[<sid>]:` + 各自 instructions 内容 |
| 7 | `test_forward_in_round_robin_includes_active_text` | Pitfall 1 fix: round-robin forward 的 `frozen_context` 含 active section 前缀 + 内容(修复前不含) |

## Deviations from Plan

None — plan executed exactly as written, with one operational learning:

**Operational note (not a deviation):** Worktree-mode bash `cd` reset behavior caused the initial `Edit` tool calls to write to the main repo's `tests/prompts/test_prompt_module.py` (via the absolute `/Users/slj/项目/hermes-agent-self-evolution/...` path) rather than the worktree's copy at `.claude/worktrees/agent-a42d2926a38822a5b/...`. Detected when `pytest --collect-only` still reported 14 (not 21) tests. Reverted the main-repo file (`git checkout --` in main repo) and re-applied edits to the worktree path. No lost work, no impact on plan correctness — the worktree-isolated commits are the canonical source.

## Pitfall 1 Fix Impact Analysis

The plan asked to call out any impact on Phase 8/9/10 tests from the `_build_frozen_context()` semantic change (active section now flows into `frozen_context`).

- **Inside the plan scope:** `TestFrozenContext::test_frozen_context_excludes_active` was the only test whose assertion contradicted the new semantics. Plan Task 2 explicitly renamed+inverted it (not deleted), with comments referencing Phase 17 / Pitfall 1.
- **Phase 8/9/10 downstream tests:** Full project suite `.venv/bin/python -m pytest tests/ -q` after both commits reports **506 passed, 1 skipped, 1 xfailed** — zero regression. No other test in `tests/prompts/`, `tests/tools/`, `tests/core/`, `tests/skills/` had an implicit assumption that active section text was absent from `frozen_context`.

## Interface Contracts for Plan 17-02 (CLI joint pipeline)

The following symbols are now stable contracts that Plan 17-02 will consume:

| Symbol | Location | Contract |
|--------|----------|----------|
| `JOINT_SENTINEL: str` | `evolution.prompts.prompt_module` (module-level constant) | Equal to `"__JOINT__"`. Plan 17-02 imports this for state machine compares (`if module._active_section == JOINT_SENTINEL`). |
| `PromptModule.set_joint_mode(active: bool = True) -> None` | `evolution.prompts.prompt_module` | Idempotent state transition. Plan 17-02 CLI joint branch calls `module.set_joint_mode(True)` before `dspy.GEPA(component_selector="all").compile(...)`. |
| `PromptModule._frozen_predictor_ids: set[str]` | `evolution.prompts.prompt_module.__init__` | Initialized to `{"selector.predict"}`. Plan 17-02 may extend if dspy versions introduce new internal sub-predictors that should also be GEPA-invisible. |
| `PromptModule.named_predictors()` (override) | `evolution.prompts.prompt_module` | Filters `_frozen_predictor_ids` entries iff `_active_section == JOINT_SENTINEL`. Round-robin behavior unchanged (selector visible). Plan 17-02's GEPA `component_selector="all"` call relies on this filtering — assertion: `len(list(module.named_predictors())) == N` (N = section count). |

## Verification Results

```bash
# Plan-level verification (verbatim from plan <verification>):
$ grep -q "JOINT_SENTINEL = \"__JOINT__\"" evolution/prompts/prompt_module.py        # exit 0 ✅
$ grep -q "def set_joint_mode" evolution/prompts/prompt_module.py                    # exit 0 ✅
$ grep -q "def named_predictors" evolution/prompts/prompt_module.py                  # exit 0 ✅
$ grep -q "self._frozen_predictor_ids" evolution/prompts/prompt_module.py            # exit 0 ✅
$ grep -q "class TestJointMode" tests/prompts/test_prompt_module.py                  # exit 0 ✅
$ grep -c "def test_" tests/prompts/test_prompt_module.py                            # 21 (exact) ✅
$ .venv/bin/python -m pytest tests/prompts/test_prompt_module.py -v -x               # 21 passed in 7.20s ✅
$ .venv/bin/python -c "from evolution.prompts.prompt_module import PromptModule, JOINT_SENTINEL; assert JOINT_SENTINEL == '__JOINT__'"  # exit 0 ✅
$ .venv/bin/python -m pytest tests/ -x -q                                            # 506 passed, 1 skipped, 1 xfailed ✅
```

## Threat Model Compliance

| Threat ID | Disposition | Mitigation Outcome |
|-----------|-------------|-------------------|
| T-17-01 (Pitfall 3 KeyError) | mitigate | ✅ `set_active_section` 入口 guard 调 `set_joint_mode(False)`;Test 4 `test_joint_then_set_active_section_auto_demotes` PASS |
| T-17-02 (selector.predict 暴露给 GEPA) | mitigate | ✅ `named_predictors()` 覆写过滤 `_frozen_predictor_ids`;Test 5 `test_named_predictors_in_joint_mode_excludes_selector` PASS,严格断言 `len(named) == 3` |
| T-17-03 (内部状态外泄) | accept | ✅ 仅添加单进程内部 attr 与模块级 const,不持久化到 metrics.json 或 hermes-agent |
| T-17-04 (重复 promote 内存增长) | mitigate | ✅ `set_joint_mode(True)` 入口 idempotent guard;Test 2 `test_set_joint_mode_idempotent` PASS |

No new threat surface introduced — Phase 17 is a pure internal Python class extension with no network, user input, or disk persistence dataflow.

## TDD Gate Compliance

This plan followed the RED/GREEN cycle for both tasks:

1. **RED gate (commit `43a0252`):** `test(17-01)` — Added `TestJointMode` class with 7 failing tests + renamed `test_frozen_context_includes_active` (asserting new Pitfall 1 fix semantics). Verified 8 RED failures, 13 baseline tests still pass.
2. **GREEN gate (commit `76f2fa4`):** `feat(17-01)` — Implemented `JOINT_SENTINEL`, `set_joint_mode`, Pitfall 3 guard, three-state `forward()`, Pitfall 1 fix in `_build_frozen_context`, `named_predictors()` override. Verified 21 PASS in plan file + 506 PASS in full suite.

No REFACTOR gate needed — the GREEN implementation already follows existing code style (snake_case, type hints, Google-docstrings, `# ── ──` section separators).

## Commits

- `43a0252` test(17-01): add TestJointMode RED tests + rename frozen_context test for Pitfall 1
- `76f2fa4` feat(17-01): extend PromptModule with joint mode state machine

## Self-Check: PASSED

- `evolution/prompts/prompt_module.py` exists at 261 lines — FOUND
- `tests/prompts/test_prompt_module.py` exists at 388 lines — FOUND
- Commit `43a0252` exists in `git log` — FOUND
- Commit `76f2fa4` exists in `git log` — FOUND
- `JOINT_SENTINEL` importable from `evolution.prompts.prompt_module` — VERIFIED
- 21 tests collected in target file, all PASS — VERIFIED
- Full suite: 506 passed + 1 skipped + 1 xfailed, zero regression — VERIFIED
