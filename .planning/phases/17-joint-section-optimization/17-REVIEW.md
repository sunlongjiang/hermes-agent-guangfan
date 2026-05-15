---
phase: 17-joint-section-optimization
reviewed: 2026-05-15T08:24:39Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - evolution/prompts/evolve_prompt_sections.py
  - evolution/prompts/prompt_module.py
  - tests/prompts/test_evolve_prompt_sections.py
  - tests/prompts/test_evolve_prompt_sections_cli.py
  - tests/prompts/test_prompt_module.py
findings:
  critical: 2
  warning: 7
  info: 4
  total: 13
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-05-15T08:24:39Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 17 引入 joint 模式三态状态机、`--mode` CLI 路由、内联 A/B 基线对比、soft-gate 警告以及 D-OUT-01 共享前缀输出布局。整体架构与 `<adversarial_stance>` 检视目标一致，但仍发现 2 个 BLOCKER（A/B 基线与主 round-robin 分支错误处理不对称破坏严格可比性、`epsilon_pp` 字段单位与变量名不一致导致下游消费者误解）以及 7 个 WARNING（包括 holdout baseline 评估循环冗余、注释与代码漂移、未使用导入/变量、A/B 基线复用迭代变量在 compile 重赋值后的隐含语义、soft-gate 边界条件等）。测试侧覆盖良好但 W4 严格断言、A/B 路径 GEPA 失败兜底场景缺少回归测试。

---

## Critical Issues

### CR-01: A/B 基线分支错误处理与主 round-robin 分支不对称，破坏 D-AB-04 "1:1 严格可比" 不变量

**File:** `evolution/prompts/evolve_prompt_sections.py:594-613` (vs `evolve_prompt_sections.py:405-438`)

**Issue:**
代码注释（line 554）明确声明 A/B 基线"与 round-robin legacy 路径单参数公式 1:1 对齐(NO 压缩),保证 A/B 严格可比"。然而错误处理分支并未对齐：

- **主 round-robin 分支**（line 405-438）GEPA 异常时回退到 MIPROv2，再失败才跳过该 section；
- **A/B 基线分支**（line 594-613）GEPA 异常时直接 `console.print` 警告后 `continue`，**没有 MIPROv2 fallback**。

后果：在 GEPA 调用失败的环境（dspy 版本变化、网络瞬时故障、API 限流等），主 round-robin 路径仍能产出 MIPROv2 优化结果，而 A/B 基线则全部退回原始未优化文本。joint vs round-robin 的 holdout 对比就从"两条同等尽力的优化路径"变成"joint 优化 vs 未优化"，**soft-gate（D-AB-02）会基于失真的 baseline 误判** —— 可能错误地将 joint 标记为"超过基线"，导致部署不应部署的回归。这直接违背了 D-AB 系列决策的核心目的。

**Fix:**
A/B 分支应使用与主 round-robin 完全一致的 GEPA → MIPROv2 嵌套 try/except 结构。最干净的修复是抽出共享 helper：

```python
def _compile_one_section(
    module: PromptModule,
    trainset, valset,
    metric, config,
    max_metric_calls: int,
    component_selector: str | None = None,
    section_label: str = "",
) -> PromptModule:
    """Single-section GEPA -> MIPROv2 fallback chain.
    Used by both the main round-robin loop AND the A/B baseline loop to
    guarantee D-AB-04 '1:1 strict comparability'."""
    try:
        reflection_lm = dspy.LM(config.optimizer_model, **config.get_lm_kwargs())
        gepa_kwargs = dict(
            metric=metric,
            max_metric_calls=max_metric_calls,
            reflection_lm=reflection_lm,
        )
        if component_selector is not None:
            gepa_kwargs["component_selector"] = component_selector
        optimizer = dspy.GEPA(**gepa_kwargs)
        return optimizer.compile(module, trainset=trainset, valset=valset)
    except Exception as e:
        console.print(
            f"  [yellow]GEPA not available ({e}), falling back to MIPROv2"
            f"{' for ' + section_label if section_label else ''}[/yellow]"
        )
        try:
            optimizer = dspy.MIPROv2(metric=metric, auto="light")
            return optimizer.compile(module, trainset=trainset)
        except Exception as e2:
            console.print(
                f"  [red]MIPROv2 also failed ({e2})"
                f"{', skipping section ' + section_label if section_label else ''}[/red]"
            )
            return module
```

然后 line 405-438 与 line 594-613 都改用此 helper。另外建议为 A/B 路径添加一个回归测试：mock `dspy.GEPA().compile` 抛 `RuntimeError`，断言 `dspy.MIPROv2().compile` 被调用一次（per section）。

---

### CR-02: `epsilon_pp` 字段值与字段名/输出文本单位不一致，下游消费者会误读 100×

**File:** `evolution/prompts/evolve_prompt_sections.py:42, 645, 655, 722`

**Issue:**
变量名 `EPSILON_PP` 暗示单位是"百分点（percentage point）"，但实际值是 `0.01`（即分数空间 0.01，等价于 1pp）。具体表现：

| 位置 | 用法 | 单位 |
|------|------|------|
| line 42 | `EPSILON_PP = 0.01` | 分数空间（0–1） |
| line 645 | `evolved_score < roundrobin_baseline_score - EPSILON_PP` | 分数空间，正确 |
| line 655 | `f"within epsilon ({EPSILON_PP * 100:.0f}pp)"` → "within epsilon (1pp)" | 显示乘 100，正确 |
| line 722 | `metrics["epsilon_pp"] = EPSILON_PP` → JSON 中是 `0.01` | **字段名说 "pp"，值却是分数空间** |

同一份 `metrics.json` 中 `joint_vs_roundrobin_delta_pp` 字段（line 723）是真正的百分点（line 644 `* 100`），值范围 0–100。下游 dashboard/比较脚本拿到 `epsilon_pp: 0.01` 和 `joint_vs_roundrobin_delta_pp: -10.0`，直接做 `delta < -epsilon` 比较会得出"-10.0 < -0.01 → 触发"——结果正确**但语义巧合**。如果未来有人写 `if abs(delta_pp) > epsilon_pp` 来对齐两边的"pp"单位，比较结果将完全错误（因为左边是 10.0，右边是 0.01，相差 100 倍）。测试也仅断言 `metrics["epsilon_pp"] == 0.01`（test_evolve_prompt_sections_cli.py:494），把 bug 钉死了。

**Fix:**
统一单位约定。建议方案 A（最小改动）：把存到 JSON 的字段值改为真正的百分点：

```python
# evolve_prompt_sections.py:42
EPSILON_PP = 1.0  # percentage points (1pp = 0.01 score units)

# Internal comparisons must convert pp -> score units:
if evolved_score < roundrobin_baseline_score - (EPSILON_PP / 100):  # line 645
    ...
console.print(f"within epsilon ({EPSILON_PP:.0f}pp)")  # line 655

# JSON output now has unit-consistent fields:
metrics["epsilon_pp"] = EPSILON_PP  # = 1.0 pp, matches `joint_vs_roundrobin_delta_pp` units
```

并在 `test_evolve_prompt_sections_cli.py:494` 把断言改为 `metrics["epsilon_pp"] == 1.0`。同时为该单位约定加一行 module docstring（"All `_pp` suffixed values are in percentage points: 1.0 == 1pp == 0.01 score units."）以预防未来回归。

或者方案 B：保留 0.01 但把字段名改为 `epsilon`（去掉 `_pp` 后缀），把 `joint_vs_roundrobin_delta_pp` 也改为分数空间 `joint_vs_roundrobin_delta` 并去除 `* 100`。两个字段单位一致才是关键。

---

## Warnings

### WR-01: Holdout baseline 评估循环内重复 `set_active_section`，每次都会 pop/重建 Predict 对象

**File:** `evolution/prompts/evolve_prompt_sections.py:525-534`

**Issue:**
```python
for ex in holdout_examples:
    with dspy.context(lm=lm):
        for sid in baseline_module._section_ids:
            baseline_module.set_active_section(sid)
            break
        bp = baseline_module(task_input=ex.task_input)
        ...
```

第二次及以后迭代时，`baseline_module` 的 `_active_section` 已是 `_section_ids[0]`，再次调用 `set_active_section(_section_ids[0])` 会走入 `prompt_module.py:105-109` 分支：把当前 Predict pop 出来写回 `_frozen_instructions`，然后第 112-117 行重新 `dspy.Predict(sig)` 创建新实例。**这是无意义的对象拆解-重建循环**，每次 holdout 样本都重复一次。

虽然不破坏正确性，但：
1. 浪费 CPU（虽然 v1 不评 perf，但这是逻辑冗余而非算法复杂度）；
2. 代码意图模糊：`for / break` 模式让维护者难以理解为什么不直接 `if baseline_module._section_ids: baseline_module.set_active_section(baseline_module._section_ids[0])`；
3. 暗示作者可能误以为每次 holdout 调用前都需要"重置"baseline 状态——但 Pitfall 1 fix 后 `_build_frozen_context` 已包含所有 section 文本，无论激活哪个都一样。

**Fix:**
把 set_active_section 提到外层循环之外，避免每个样本重复：

```python
baseline_module = PromptModule(original_sections)
if baseline_module._section_ids:
    baseline_module.set_active_section(baseline_module._section_ids[0])
# ...
for ex in holdout_examples:
    with dspy.context(lm=lm):
        bp = baseline_module(task_input=ex.task_input)
        b_score = metric(ex, bp, trace=None)
        baseline_scores.append(b_score)
        ep = module(task_input=ex.task_input)
        ...
```

A/B 路径 line 618-621 已经是这种正确的提取模式——主路径却没对齐。

---

### WR-02: PromptModule 顶层 docstring 与代码漂移，提及不存在的语义

**File:** `evolution/prompts/prompt_module.py:1-7, 4, 54, 62, 74`

**Issue:**
模块/类 docstring 反复声明"Only the active section is discoverable by `named_parameters()`"（行 4、54、62、74）。但 Phase 17 实际重写的是 `named_predictors()`（line 224），而 GEPA 用 `named_predictors`、不是 `named_parameters`。`named_parameters()` 默认行为是遍历所有 `dspy.Parameter` 子对象 —— `_frozen_instructions` 是 `dict[str, str]`，不是 Parameter，所以原本就不会被发现。代码上**没有 bug**（frozen 字符串确实不被 GEPA 看见），但 docstring 在错误的方法名上做承诺。

Phase 17 引入的 joint 模式让这种漂移更危险：未来有人读 docstring 误以为 frozen 是靠 `named_parameters` 重写实现的，可能会在 `named_parameters` 上加额外过滤——这是无用功而且可能破坏 dspy 内部假设。

**Fix:**
全局替换 docstring 中 `named_parameters()` → `named_predictors()`，并在 line 224 `named_predictors` 重写处的 docstring 显式说明："Frozen sections are dict[str, str], not dspy.Parameter, so they are invisible to BOTH named_parameters() and named_predictors() by default. This override additionally excludes selector.predict in joint mode."

---

### WR-03: 死代码 — round-robin 分支预算计算赋值未使用变量

**File:** `evolution/prompts/evolve_prompt_sections.py:278-280`

**Issue:**
```python
else:
    num_predictors = len(module._section_ids)
    joint_budget = 0  # not running joint
```

`num_predictors` 在 else 分支被赋值但**整个 else 分支后续没有任何引用**（joint_budget 仅在 line 288 的 if 分支被读，rr_per_section_budget 不依赖 num_predictors）。这是死代码，且和 joint 分支的 `num_predictors = len(list(module.named_predictors()))` 含义不同（一个是 `_section_ids`，另一个是 named_predictors 长度），加深歧义。

**Fix:**
删掉 line 279。若想保留对称结构以便日后启用 round-robin 预算细节，则改成显式标注：

```python
else:
    joint_budget = 0  # not running joint; num_predictors unused in rr branch
```

---

### WR-04: 未使用导入 `Panel` 和 `get_hermes_agent_path`

**File:** `evolution/prompts/evolve_prompt_sections.py:20, 23`

**Issue:**
```python
from rich.panel import Panel                                                     # line 20
from evolution.core.config import EvolutionConfig, get_hermes_agent_path        # line 23
```

`Panel` 在整个文件中没有任何引用；`get_hermes_agent_path` 也没有调用（hermes 路径在 line 142-147 通过 `EvolutionConfig.load(hermes_repo=...)` 间接处理）。

虽然 `<review_scope>` 把 unused imports 列为 Info，但这两个导入加在一起暗示该模块经历过 refactor 但清理不彻底，对于 BLOCKER 级别审查阶段建议归 Warning：未来同名符号若在 evolution.core.config 中被改签名/移除，会让本文件无故抛 ImportError。

**Fix:**
```python
from rich.console import Console
from rich.table import Table

from evolution.core.config import EvolutionConfig
```

如未来确实想用 Panel 做美观输出，再恢复 import。

---

### WR-05: A/B 基线循环中迭代 `_section_ids` 的同时重赋值 `ab_baseline_module`，依赖隐式语义

**File:** `evolution/prompts/evolve_prompt_sections.py:568-608`

**Issue:**
```python
for ab_sid in ab_baseline_module._section_ids:           # line 568
    ab_baseline_module.set_active_section(ab_sid)        # line 569
    ...
    ab_baseline_module = ab_optimizer.compile(           # line 604 — REBIND
        ab_baseline_module, trainset=..., valset=...
    )
```

第 568 行 `for ab_sid in ab_baseline_module._section_ids` 在循环开始前**对当时 ab_baseline_module 的 `_section_ids` 列表对象建立迭代器**（Python iteration semantics）。然后第 604 行把变量名 `ab_baseline_module` 重绑定到 GEPA 返回的对象（同一对象或副本，dspy 实现决定）。第二轮迭代时：

- `ab_sid` 仍来自最初的 `_section_ids` 列表（OK）；
- 但 line 569 `ab_baseline_module.set_active_section(ab_sid)` 调用的是**新对象**的方法。

如果 GEPA.compile 返回 deep-copy 的新 module，新 module 的 `_section_ids` 应当与原列表内容相同（dspy 通常保留 dict/list 属性），但新 module 的 `_active_section` 可能是 None（重置）或保留——**此行为依赖 dspy 内部实现而不是显式契约**。代码在测试中通过 mock 让 `compile` 返回原 module（`side_effect = lambda mod, ...: mod`），所以测试不会暴露这条路径上的真实问题。

类似潜在风险还出现在主 round-robin 分支 line 414-418、joint 分支 line 357-361。

**Fix:**
显式注释这一不变量，并在循环顶用 `original_section_ids = list(ab_baseline_module._section_ids)` 把 ID 列表 snapshot 出来，让代码意图独立于 dspy.GEPA.compile 的返回语义：

```python
original_section_ids = list(ab_baseline_module._section_ids)
for ab_sid in original_section_ids:
    ab_baseline_module.set_active_section(ab_sid)
    ...
    ab_baseline_module = ab_optimizer.compile(ab_baseline_module, ...)
```

同时建议为 dspy.GEPA.compile 返回新对象 vs 修改原对象添加一个集成测试，确认 hermes 当前 dspy>=3.0 版本的实际行为；若是新对象，本文件还需在 line 357-361/414-418 同步加 snapshot。

---

### WR-06: Soft-gate 边界条件 `< baseline - epsilon` 把 "刚好回归 epsilon" 算作通过，与"超出 1pp"自然语言描述错位

**File:** `evolution/prompts/evolve_prompt_sections.py:645`

**Issue:**
```python
if evolved_score < roundrobin_baseline_score - EPSILON_PP:
    # WARN
```

当 `evolved_score == roundrobin_baseline_score - EPSILON_PP`（即恰好回归 1pp），条件为 False，落入 else "within epsilon"。Plan 17-03 中描述 soft-gate 含义为"joint 回归**超过** 1pp 时警告"，所以严格小于 `<` 是与文档一致的；但用户可能预期"回归刚好 1pp 也警告"。

更重要的：浮点等价场景。当 `evolved_score = 0.59`，`roundrobin_baseline_score = 0.60`，理论 delta = -0.01 pp = -EPSILON_PP，但浮点表示下 `0.60 - 0.59` 实际等于 `0.010000000000000009`，所以 `evolved_score < roundrobin_baseline_score - EPSILON_PP` → `0.59 < 0.5899999...` → False。**该边界对浮点的依赖会让测试在不同硬件/Python 版本下行为不稳定**（虽然 IEEE 754 让 CPython 3.13 实际是确定性的，但 pytest 跨平台 CI 仍是隐患）。

**Fix:**
1. 边界语义文档化：在 line 645 上方加一行 `# Strictly less-than: equal-to-epsilon regression is treated as acceptable.`
2. 浮点鲁棒性：考虑加上一个小 `eps` tolerance（`< baseline - EPSILON_PP - 1e-9`），或者把分数计算移到固定小数位（`round(evolved_score, 4)`）。后者更稳。

---

### WR-07: `_build_frozen_context` 中 round-robin 模式仍把 active section text 与 frozen 一同拼接，形成"既是输入又是 instructions"的双重通路

**File:** `evolution/prompts/prompt_module.py:197-222`

**Issue:**
Pitfall 1 fix 是必要的——active section instructions 必须流入 selector 才能让 GEPA 突变生效。**但**当前实现把 active section 文本拼接到 `frozen_context` 字符串里和其他 frozen sections 同等对待，**同时**该文本仍是 `section_predictors[active].signature.instructions`（被 GEPA 突变）。这意味着：

- forward 时，active section 文本以"frozen 上下文的一员"身份进入 selector 的 `frozen_context` 输入字段；
- 但 GEPA 在优化 active.signature.instructions 时，并没有把它视为 selector 的 instruction 来 reflect ——它只看到 active_predictor 的 signature input/output schema（`section_text -> confirmation`，line 113-116）。

后果：GEPA reflection 流程对 active section 突变的"反馈信号"是经过 selector 的最终 output，但 active section 的 instructions 在 selector 视角下只是一段"上下文文本"，与其他 frozen sections 在语法/位置上不可区分。GEPA 学到的可能是"如何写一段更好的上下文文字"而非"如何写出 active section 应有的角色指令"。这削弱了 component_selector='all' 的语义清晰度。

**Fix:**
两种方案，需要架构讨论：

A. 显式区分：在 `_build_frozen_context` 把 active section 标记为 `[ACTIVE: {sid}]:` 而非 `[{sid}]:`，让 selector 知道哪一段是被优化目标。这至少给 LLM/reflection 一个明确信号。

B. 重构 forward：让 selector 的 Signature 多一个 `active_section_text` 输入字段，把 active 文本与 frozen 上下文物理分开。

建议在 CONTEXT.md 中记录决策，并加测试断言 frozen_context 与 active text 的位置/格式约定。否则后续维护者改 `_build_frozen_context` 时容易破坏 Pitfall 1 fix 而无 CI 信号。

---

## Info

### IN-01: `for sid in baseline_module._section_ids: ...; break` 模式不符合项目 conventions

**File:** `evolution/prompts/evolve_prompt_sections.py:529-531`

**Issue:**
项目 CLAUDE.md 强调"Step numbering in orchestration functions"和清晰意图。`for X in L: do(); break` 取首元素的写法不直观，标准 Python 是 `L[0] if L else None`。已经在 WR-01 中作为改进项一并提及，此处单独标记为 Info 是因为这是一个跨多处出现的代码味道。

**Fix:**
替换为 `baseline_module.set_active_section(baseline_module._section_ids[0])`（外加空列表保护），见 WR-01 修复建议。

---

### IN-02: `_make_mocked_dataset()` 注释提到的回归被新测试同时覆盖，但 docstring 未更新

**File:** `tests/prompts/test_evolve_prompt_sections_cli.py:30-39`

**Issue:**
`_make_mocked_dataset` docstring：
> "holdout is intentionally LEFT EMPTY so we don't run holdout evaluation ... For these CLI tests we only assert optimization-step shape; holdout regression is covered by the existing tests/prompts/test_evolve_prompt_sections.py::TestEvolve suite."

但同一文件 `TestABBaseline._ab_patched_run` 又通过 `holdout=examples`（line 361）启用了 holdout 评估，并且测试 A/B 流程。docstring 暗示"holdout regression 在其他文件"，但实际 TestABBaseline 就在同文件做 holdout 验证。

**Fix:**
更新 docstring 反映双重设计：
```python
"""...
holdout is intentionally LEFT EMPTY for TestJointPipeline / TestDryRun (they
assert optimization-step shape only).  TestABBaseline._ab_patched_run uses
its own dataset factory with populated holdout to exercise the A/B flow.
"""
```

---

### IN-03: TestABBaseline 注释提到的 BLOCKER B1/B2 在审查文件中未明显标注修复完成

**File:** `tests/prompts/test_evolve_prompt_sections_cli.py:314-326`

**Issue:**
class docstring 标注"BLOCKER fixes applied (revision pass)"——B1/B2 列出了之前 review 发现的问题。这种留痕对短期 PR 有帮助，但作为长期代码注释会让未来维护者困惑（"现在 B1 还是 BLOCKER 吗？"）。考虑迁移到 PR description 或 17-DISCUSSION-LOG.md。

**Fix:**
保留行内注释 `# BLOCKER-1 fix: ...` 因为它解释了为什么用真实 dataclass 字段；删除 class docstring 的 BLOCKER 部分，迁移到 phase log。

---

### IN-04: `Optional[float]` 与 `str | None` 类型注解风格混用

**File:** `evolution/prompts/evolve_prompt_sections.py:547-550` (uses Optional) vs `evolution/prompts/prompt_module.py:67` (uses `str | None`)

**Issue:**
`evolve_prompt_sections.py` 用 `Optional[float] = None`、`from typing import Optional`；`prompt_module.py` 用 `str | None`（PEP 604 新语法）。CLAUDE.md 写 "Use modern Python type hints throughout"，但具体偏好 Optional vs `|` 没明说。混用本身不破坏功能，但项目内一致性更好。

**Fix:**
统一为 PEP 604 `X | None` 语法（Python 3.10+，与项目 minimum 一致），删除 `from typing import Optional`。或反过来全部用 Optional。建议在 CLAUDE.md 添加一条约定。

---

_Reviewed: 2026-05-15T08:24:39Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
