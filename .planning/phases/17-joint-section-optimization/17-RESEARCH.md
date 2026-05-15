# Phase 17: Joint Section Optimization - Research

**Researched:** 2026-05-15
**Domain:** DSPy GEPA 多参数 (multi-predictor) 联合优化 + PromptModule 状态机改造 + inline A/B baseline
**Confidence:** HIGH（DSPy 上游源码 + 本地 dspy 3.1.3 行为已实测验证）

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Round-robin 共存策略**
- **D-RR-01:** 保留 round-robin 实现为 `--mode round-robin` 显式 fallback。`PromptModule.set_active_section()` 不动,所有现有调用走 round-robin 分支不变。11 个现有测试用例零改写。
- **D-RR-02:** Joint 是 CLI 默认 mode,**静默切换**,不打 deprecation 警告。
- **D-RR-03:** `--section <section_id>` flag **隐含** round-robin 单点优化路径,用户不需要同时传 `--mode round-robin`。`--section X` 与 `--mode joint` 同时存在时按 round-robin 单点处理,不报错。
- **D-RR-04:** `--mode` 用 `click.Choice(["joint", "round-robin"])`,默认 `joint`。

**A/B baseline 与软门**
- **D-AB-01:** 采用 **inline A/B**:joint 跑完 holdout 评估后,同一 CLI 进程内再跑一次完整 round-robin,用相同 dataset、metric、holdout 打分。
- **D-AB-02:** 软门:`joint_score < roundrobin_score - epsilon` 时,stdout 黄警告 + 两者都落盘,**不 exit 2**,**不阻断 constraint validation 与 evolved_sections.json 写出**。
- **D-AB-03:** Epsilon 默认 **0.01 (1pp)**,固定常量不暴露为 flag。
- **D-AB-04:** Round-robin baseline 跑全量 `iterations × 5` 调用(与 `--mode round-robin` 单跑等价),不做 budget 压缩。

**CLI 与 iteration 预算**
- **D-IT-01:** joint mode 下 `--iterations N` 是 **GEPA 总轮数**;round-robin baseline 仍是 N 次/section × 5 section。
- **D-IT-02:** joint 的 GEPA `max_metric_calls = iterations × 50 × 5`(乘 5 因 5 个参数;若 researcher 在 DSPy 文档中查到更精确公式可微调,本期定为 `× 5` 起点)。
- **D-IT-03:** CLI 启动时 stdout 打预算预估行,格式见 CONTEXT.md 样例;与 Phase 5/13 现有的 "Configuring optimizer" stdout 块风格一致。

**Output schema & metrics.json**
- **D-OUT-01:** joint run 与 round-robin run 共用 `output/prompts/<YYYYMMDD_HHMMSS>/` 目录,**不另起 `output/prompts_joint/`**。
- **D-OUT-02:** metrics.json 新增字段(joint mode 下):`mode`、`joint_score`、`roundrobin_baseline_score`、`epsilon_pp`;保留现有字段 `baseline_score`、`evolved_score`、`improvement`、`iterations`、`eval_model`。
- **D-OUT-03:** diff.txt 沿用现有 `_generate_diff()`,多 section 的 unified diff 自然拼接成单文件。零代码改动。
- **D-OUT-04:** **不**修改 `evolution/tools/regression_dashboard.py`,**不**为 prompt run 接入仪表盘。

### Claude's Discretion

- joint mode 下 `PromptModule` 状态机的具体设计 — 用 `_active_section = "__ALL__"` 哨兵、新 `_joint_mode: bool` flag、还是分离的 `JointPromptModule` 子类。约束:不破坏现有 11 个测试用例;round-robin 路径 set/forward/get_evolved_sections 行为完全等价。
- joint mode 下 `forward()` 的具体实现 — concat 还是串行 Predict 调用合并 output。约束:joint 与 round-robin 的 forward 输入输出契约必须可被同一 `PromptBehavioralMetric` 评分。
- A/B baseline run 在 metrics.json / diff.txt / evolved_sections.json 中的存储位置 — 同 `output/prompts/<ts>/` 共享前缀 vs 子目录 `baseline/`。
- 软门 stdout 警告的精确文案、颜色规则。

### Deferred Ideas (OUT OF SCOPE)

- per-section growth_pct / delta_score 数组进 metrics.json — YAGNI 至 dashboard 接入。
- dashboard 接入 prompt run(`--prompt-runs` flag) — Phase 22+。
- `--joint-iterations N` 单独 flag — 当前 `--iterations` 同步控制。
- A/B 硬门 + exit code — 当前 LLM-judge 方差不支持硬门。
- `hybrid` mode(joint warmup → round-robin fine-tune) — Click.Choice 留扩展空间,实现待后续 phase。
- 多种 GEPA `max_metric_calls` 公式 — 本期 `iterations × 50 × 5` 起点。
- Cross section 联动检查 — Phase 18 (Personality Drift Detection) 范围。

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PMPT-V2-01 | Joint section optimization (all 5 sections simultaneously) | 本研究确认 DSPy GEPA `component_selector="all"` 是上游原生支持的 joint-update 路径(实测 dspy 3.1.3 接受该参数);PromptModule.section_predictors 已是 dict[str, Predict],dict 中所有 Predict 自动通过 `named_predictors()` 暴露给 GEPA;ROADMAP §Phase 17 三条 Success Criteria(PromptModule 全 section 可见、GEPA 一次 pass 可 mutate 多 section、joint ≥ round-robin on holdout)均由本研究的 §Architecture Patterns 与 §Code Examples 章节支撑。 |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Architecture:** 严格遵循 Phase 1 代码模式和目录结构。
- **Dependency:** 不引入新外部依赖,复用 DSPy/Click/Rich 栈。
- **hermes-agent:** 只读访问,通过 `HERMES_AGENT_REPO` 环境变量定位。Phase 17 完全不触碰 hermes-agent — 优化结果落 `output/prompts/<ts>/evolved_sections.json`,不 write-back。
- **Size:** prompt section growth ≤ 基线 +20%(`EvolutionConfig.max_prompt_growth = 0.2`)— 与 round-robin 共用 `ConstraintValidator._check_growth`。
- **Coding style:** snake_case 模块、PascalCase 类、`@dataclass` for plain data、`Console()` + Rich markup 而非 `print()`、`@click.command()` + `@click.option()` CLI 风格、JSONL/JSON 持久化、`from typing import Optional` for optional params。
- **GSD workflow:** 通过 GSD 命令进入文件编辑路径,不绕过。

## Summary

Phase 17 的核心是把 PromptModule 从「单 section 激活 + round-robin for-loop」改造成「全 section 激活 + GEPA 单次 compile() 多参数反思」,新 mode 成 CLI 默认,但保留 round-robin 作为显式 `--mode round-robin` fallback 与 inline A/B baseline 来源。

研究的高价值发现是:**DSPy GEPA 上游已原生支持 `component_selector="all"` 多参数联合优化** —— 这是 dspy 3.1.3 `dspy.GEPA.__init__` 的第一类参数,内部映射到 gepa 包的 `AllReflectionComponentSelector`(每个 GEPA iteration 同时为所有 named_predictors 提议新 instructions,而非默认 `round_robin` 单参数轮转)。Phase 13 (`evolution/tools/evolve_tool_params.py:579-581`) 已经把 `--component-selector` 作为用户可见 flag 暴露并锁定 `Choice(["round_robin", "all"])`,Phase 17 应直接复用这一模式,避免重新发明轮子。这意味着:joint mode 不需要重写 GEPA 调用、不需要自定义 ReflectionComponentSelector — 只需(a) 让 PromptModule 的 `section_predictors` dict 同时挂 13 个 active Predict、(b) 调用 GEPA 时传 `component_selector="all"`、(c) 重写 `forward()` 让所有 section 文本实际流入 selector 输入(当前 round-robin 实现里 active section 文本对 forward 输出无路径,见 §Pitfall 1)。

GEPA 内部的 `auto_budget` 公式已能精确计算多参数预算 —— `num_trials = max(2 × (num_preds × 2) × log2(num_candidates), 1.5 × num_candidates)`,然后按 trial 数 × valset 推算 max_metric_calls。CONTEXT.md D-IT-02 的「`iterations × 50 × 5`」公式与 DSPy 上游公式不完全一致(上游用 log2 缩放而非线性 × num_preds),但作为外部用户给的起点 budget 合理 —— 13 section 时大致与 `auto="medium"` 等价(详见 §Standard Stack §Budget Formula)。建议 planner 把 D-IT-02 的「× 5」按实际 section 数(13)换为「× num_predictors」,与 Phase 13 `evolve_tool_params.py:806` 的 `max(iterations * 50, 3 * num_predictors)` 公式风格对齐。

**Primary recommendation:** PromptModule 加 `set_joint_mode(active: bool)` 方法,把所有 frozen 段落升级为 Predict;`forward()` 用 `_active_section in (None | "__JOINT__")` 三态控制:None 报错(向后兼容)、单 sid 走现有 frozen_context 路径、`"__JOINT__"` 走新的 multi-Predict 序列调用拼接 output。CLI 端复用 Phase 13 `--component-selector` 接线模式,joint mode 强制 `"all"`,round-robin 走 `"round_robin"`。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `PromptModule.set_joint_mode()` / `set_active_section()` 状态切换 | Optimization Module Layer (`evolution/prompts/prompt_module.py`) | — | 与 Phase 8 / Phase 12 PromptModule 同层;dict-based section_predictors 已是该层数据结构,joint 是状态机扩展。 |
| GEPA 多参数联合 compile() | Optimization Module Layer 调用 DSPy 框架 | DSPy GEPA 框架(`dspy.GEPA(component_selector="all")`) | DSPy 已原生支持;Phase 17 仅消费,不自实现 ReflectionComponentSelector。 |
| Inline A/B baseline 跑 round-robin | Orchestration Layer (`evolution/prompts/evolve_prompt_sections.py`) | Optimization Module Layer(复用 set_active_section + for-loop) | A/B 是 CLI 编排逻辑,不污染 PromptModule 内部。 |
| 软门 epsilon 比较 + 黄警告 | Orchestration Layer | — | 与 Phase 16 D-13 dashboard `--warning-threshold-pp` 同模式 — stdout 警告 + 不影响 exit。 |
| metrics.json 字段扩展 + 落盘 | Orchestration Layer | (可选)Persistence Helper Layer(`evolution/prompts/prompt_metric.py:persist_ab_baseline`) | 与 Phase 13 `persist_per_tool_rates` / Phase 16 `persist_raw_predictions` 同模式;helper 是 Claude's Discretion,planner 决定是否值得抽。 |
| Constraint validation(growth + role)| Constraint Layer (`evolution/core/constraints.py`、`evolution/prompts/prompt_constraints.py`) | — | joint mode 下 13 section 各跑一次现有 per-section 检查,自然适配,无新代码。 |
| Diff 生成 | Orchestration Layer (`_generate_diff()`)| — | D-OUT-03 锁定零代码改动。 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | 3.1.3 (本地 venv 已装) | GEPA optimizer + Predict/Module 抽象 | Phase 1-16 全栈统一;3.x 引入 `component_selector` 参数支持 joint update[VERIFIED: dspy/teleprompt/gepa/gepa.py L351, 本地 `python -c "import dspy; print(dspy.__version__)"` = 3.1.3] |
| gepa | (transitive via dspy) | DSPy 底层进化引擎,提供 `AllReflectionComponentSelector` | DSPy 3.x 的 `dspy.GEPA` 是 `gepa.optimize` 的 thin wrapper[VERIFIED: dspy/teleprompt/gepa/gepa.py L1-15 imports `from gepa import GEPAResult`, `from gepa.proposer.reflective_mutation.base import ReflectionComponentSelector`] |
| click | >=8.0 | CLI flag 解析 | 现有 evolve_prompt_sections.py 已用[VERIFIED: pyproject.toml L21] |
| rich | >=13.0 | Console / Panel / Table / 黄警告 markup | 现有代码已用[VERIFIED: pyproject.toml L22] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=7.0 (dev) | 测试框架 | 14 个 PromptModule + 4 个 CLI test 现有 |
| `unittest.mock` (stdlib) | — | `patch("dspy.GEPA")` 模拟 GEPA 不发起真 LM 调用 | 复用 `tests/tools/test_evolve_tool_params_cli.py` patch 风格 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `component_selector="all"` | 自定义 `ReflectionComponentSelector`(`ReflectionComponentSelector` Protocol) | 自定义有更细粒度控制(如 "前 N iteration round-robin 暖启再切 all"),但本期 Deferred `hybrid` mode 已锁定不实现 — 用 `"all"` 字符串即可。[VERIFIED: dspy/teleprompt/gepa/gepa.py docstring L254-261] |
| `dspy.GEPA(component_selector=...)` 直传 | `gepa_kwargs={"module_selector": ...}` 走 passthrough | DSPy 已显式提升 `component_selector` 为顶层参数(L351),无需走 `gepa_kwargs` 后门。[VERIFIED: dspy/teleprompt/gepa/gepa.py L351 `component_selector: "ReflectionComponentSelector | str" = "round_robin"`] |
| Linear budget `iterations × 50 × num_predictors` | DSPy `auto="medium"` 让上游算 | `auto` 公式 `num_trials = max(2 × (num_preds × 2) × log2(num_candidates), 1.5 × num_candidates)`(`AUTO_RUN_SETTINGS["medium"]["n"]=12`)对 13 section 算出 num_trials ≈ 96,加 valset eval 推到 ~1500-2500 max_metric_calls,与本期 D-IT-02 的「`iterations=10 × 50 × 13 = 6500`」同量级但 `auto` 更稳。**建议 planner 评估让 `--auto medium` 与 `--iterations N` 互斥**,与 Phase 13/15 现有 `--auto` flag 风格对齐(Phase 13 用 `click.Choice(["light", "medium", "heavy"])`)。[VERIFIED: dspy/teleprompt/gepa/gepa.py L23-27 + L450-456 + Phase 13 `evolution/tools/evolve_tool_params.py:582-584`] |

**Installation:** 无新依赖。已装栈直接复用。

**Version verification:**
```bash
.venv/bin/python -c "import dspy; print(dspy.__version__)"  # → 3.1.3
.venv/bin/python -c "from dspy.teleprompt.gepa.gepa import GEPA; import inspect; print(inspect.signature(GEPA.__init__).parameters.get('component_selector').default)"  # → 'round_robin'
.venv/bin/python -c "import dspy; g = dspy.GEPA(metric=lambda *a,**k: 0.5, max_metric_calls=10, reflection_lm=dspy.LM('openai/dummy', api_key='x'), component_selector='all'); print(g.component_selector)"  # → 'all' (verified accepted)
```
All checks PASS as of 2026-05-15.[VERIFIED: 本地 venv 实测]

### Budget Formula (DSPy GEPA `auto_budget` upstream)

```python
# dspy/teleprompt/gepa/gepa.py L443-471 (verified verbatim)
AUTO_RUN_SETTINGS = {"light": {"n": 6}, "medium": {"n": 12}, "heavy": {"n": 18}}

def auto_budget(self, num_preds, num_candidates, valset_size, minibatch_size=35, full_eval_steps=5) -> int:
    num_trials = int(max(2 * (num_preds * 2) * math.log2(num_candidates), 1.5 * num_candidates))
    total = valset_size                              # initial full eval
    total += num_candidates * 5                       # bootstrap
    total += num_trials * minibatch_size              # N minibatch evals
    if num_trials > 0:
        periodic_fulls = (num_trials + 1) // full_eval_steps + 1
        extra_final = 1 if num_trials < full_eval_steps else 0
        total += (periodic_fulls + extra_final) * valset_size
    return total
```

**Empirical numbers for joint mode (13 sections + 1 selector = 14 predictors, valset≈20):**
- `auto="light"` (n=6): num_trials ≈ max(2×28×log2(6), 1.5×6) = max(145, 9) = 145 → ~5200 metric_calls
- `auto="medium"` (n=12): num_trials ≈ max(2×28×log2(12), 1.5×12) = max(201, 18) = 201 → ~7200 metric_calls
- `auto="heavy"` (n=18): num_trials ≈ max(2×28×log2(18), 1.5×18) = max(234, 27) = 234 → ~8400 metric_calls

For round-robin baseline (each section runs with num_preds=2 = 1 active + 1 selector,共 13 段):
- per-section `auto="medium"`: num_trials ≈ max(2×4×log2(12), 18) = max(28.6, 18) = 28 → ~1000 metric_calls/section → × 13 sections ≈ 13000 metric_calls 总和

**D-IT-02 起点公式重估:** `iterations × 50 × 5` 假设 5 个 section。实际 13 section,planner 应改为 `iterations × 50 × num_predictors`,与 Phase 13 `evolve_tool_params.py:806` `max(iterations * 50, 3 * num_predictors)` 公式风格对齐。或直接用 `--auto medium` 让上游算。

## Architecture Patterns

### System Architecture Diagram

```
                       CLI (evolve_prompt_sections.py)
                                │
                                ▼
            ┌──────────── parse args ────────────┐
            │  --mode joint | round-robin       │
            │  --section <sid>  (→ implicit RR)  │
            │  --iterations N                    │
            └────────────────────────────────────┘
                                │
                                ▼
                  extract_prompt_sections(prompt_builder.py)
                  → list[PromptSection] (13 sections)
                                │
                                ▼
            ┌─────────────── DRY-RUN GATE ────────────────┐
            │  budget estimate stdout: joint X + RR Y     │
            └─────────────────────────────────────────────┘
                                │
                                ▼
                      PromptDatasetBuilder / loader
                      → PromptBehavioralDataset (train/val/holdout)
                                │
                                ▼
                  ┌─────────── MODE FORK ───────────┐
                  │                                 │
                  ▼                                 ▼
         JOINT BRANCH                       ROUND-ROBIN BRANCH
                  │                                 │
   ┌──────────────┴──────────────┐     ┌────────────┴────────────┐
   │ module.set_joint_mode(True) │     │ for sid in section_ids: │
   │ all 13 section_predictors   │     │   set_active_section(sid)│
   │ now Predict (named_pred-    │     │   filter dataset[sid]   │
   │  ictors() returns 14)       │     │   GEPA.compile(...)     │
   │                             │     │   single-param          │
   │ trainset = full (no filter) │     └────────────┬────────────┘
   │ dspy.GEPA(                  │                  │
   │   metric=PromptBehavior...  │                  ▼
   │   component_selector="all", │           module evolved
   │   max_metric_calls=...,     │
   │ ).compile(module, train,    │
   │           valset=val)       │
   └──────────────┬──────────────┘
                  │
                  ▼
        evolved_sections = module.get_evolved_sections()
                  │
                  ▼
     ┌────────── CONSTRAINT GATE ──────────┐
     │  _check_growth(per section) × 13    │
     │  _check_non_empty(per section)      │
     │  PromptRoleChecker.check_all(...)   │
     │  All must pass → continue,          │
     │  Any fail → FAILED_<ts>/ + return   │
     └─────────────┬───────────────────────┘
                   │
                   ▼
         HOLDOUT EVAL (joint module)
         baseline_score, joint_score = ...
                   │
                   ▼ ── IF mode == joint ──
       ┌──────────────────────────────────┐
       │ INLINE A/B BASELINE RUN           │
       │ fresh PromptModule(originals)     │
       │ for sid in section_ids:           │
       │   set_active_section(sid)         │
       │   GEPA.compile(per-section)       │
       │ → roundrobin_baseline_score on    │
       │   same holdout                    │
       └─────────────┬────────────────────┘
                     │
                     ▼
        SOFT GATE (epsilon = 0.01)
        joint_score < roundrobin - 0.01 ?
        → YES: stdout yellow warning, NO exit
        → NO:  green success message
                     │
                     ▼
      ┌──── PERSIST output/prompts/<ts>/ ────┐
      │  metrics.json (mode, joint_score,    │
      │   roundrobin_baseline_score,         │
      │   epsilon_pp, +existing fields)      │
      │  evolved_sections.json               │
      │  diff.txt (unchanged _generate_diff) │
      └──────────────────────────────────────┘
```

### Recommended Project Structure (no new files unless helper extracted)

```
evolution/prompts/
├── prompt_module.py            # MODIFY: + set_joint_mode(), + joint forward() path
├── evolve_prompt_sections.py   # MODIFY: + --mode flag, + joint pipeline, + A/B baseline,
│                               # + budget stdout, + soft-gate warning
├── prompt_dataset.py           # UNCHANGED (to_dspy_examples(split, section_texts) 已通用)
├── prompt_metric.py            # UNCHANGED (joint output 同样是 prediction.output, metric 不变);
│                               # OPTIONAL: + persist_ab_baseline() helper if planner chooses
├── prompt_constraints.py       # UNCHANGED (per-section check 自然适配 joint)
└── prompt_loader.py            # UNCHANGED

tests/prompts/
├── test_prompt_module.py       # MODIFY: + joint mode 单测(set_joint_mode + named_predictors visibility)
├── test_evolve_prompt_sections.py  # MODIFY: + --mode joint default、--mode round-robin、
│                               # --section X 自动 RR、软警告触发四类 CLI 集成测试
└── (rest UNCHANGED)
```

### Pattern 1: 上游 GEPA component_selector="all" 调用
**What:** DSPy `dspy.GEPA` 接受 `component_selector="all"` 字符串,内部由 `gepa.strategies.component_selector.AllReflectionComponentSelector` 实现:每个 iteration 返回 `list(candidate.keys())` —— 即所有 named_predictors。
**When to use:** Joint mode 下,replace 现有 `dspy.GEPA(metric=..., max_metric_calls=..., reflection_lm=...)` 调用,加 `component_selector="all"` 即可。
**Example:**
```python
# Source: dspy/teleprompt/gepa/gepa.py L351 (default), evolution/tools/evolve_tool_params.py L797
# Verified upstream (dspy 3.1.3 release).
reflection_lm = dspy.LM(config.optimizer_model, **config.get_lm_kwargs())
optimizer = dspy.GEPA(
    metric=metric,                              # PromptBehavioralMetric, 5-param signature
    max_metric_calls=iterations * 50 * num_predictors,  # 或用 auto="medium"
    reflection_lm=reflection_lm,
    component_selector="all",                   # NEW: joint update of all 13 sections
    track_stats=True,                           # optional, 落 detailed_results
    seed=0,                                     # reproducibility
)
module = optimizer.compile(
    module,                                     # 已 set_joint_mode(True), all 13 in section_predictors
    trainset=trainset,                          # full dataset, no section filter
    valset=valset,
)
```
[VERIFIED: 本地 dspy 3.1.3 接受该参数;upstream source L351 锁定为字符串 Choice]

### Pattern 2: PromptModule joint mode 状态机扩展(推荐设计)
**What:** 加 `set_joint_mode(active: bool)` 方法 + `_joint_mode: bool` flag,joint mode 下把所有 frozen instructions 升级为 Predict,`_active_section` 设为哨兵 `"__JOINT__"`。
**When to use:** CLI 走 joint branch 时调一次 `module.set_joint_mode(True)`;若用户混用(先 joint 后 set_active_section X),按方法语义切回单 active(自动从 joint 退化为 round-robin)。
**Example:**
```python
# Source: design proposal — extends existing evolution/prompts/prompt_module.py L71-99 (set_active_section)
# Pattern mirrors set_active_section but operates on all sections simultaneously.

JOINT_SENTINEL = "__JOINT__"

def set_joint_mode(self, active: bool = True) -> None:
    """Activate all sections as optimizable Predicts simultaneously.

    Joint mode is the new CLI default. In joint mode, every section's text
    becomes a Predict.signature.instructions, making all of them
    discoverable by named_predictors() and mutable by GEPA in a single
    optimizer.compile() pass with component_selector='all'.
    """
    if active:
        # Move any single active back to frozen first (idempotent)
        if self._active_section is not None and self._active_section != JOINT_SENTINEL:
            pred = self.section_predictors.pop(self._active_section)
            self._frozen_instructions[self._active_section] = pred.signature.instructions
        # Promote all frozen instructions to Predicts
        for sid in list(self._frozen_instructions.keys()):
            text = self._frozen_instructions.pop(sid)
            sig = dspy.Signature("section_text -> confirmation", instructions=text)
            self.section_predictors[sid] = dspy.Predict(sig)
        self._active_section = JOINT_SENTINEL
    else:
        # Reverse: demote all Predicts back to frozen strings
        for sid in list(self.section_predictors.keys()):
            pred = self.section_predictors.pop(sid)
            self._frozen_instructions[sid] = pred.signature.instructions
        self._active_section = None
```
[CITED: prompt_module.py L71-99 (existing set_active_section)]

### Pattern 3: forward() 三态调度(joint / single / none)
**What:** `forward()` 检查 `_active_section`,分发到三个路径。
**When to use:** Always — joint mode 与 round-robin 共用一个 forward 入口,metric 端零改动。
**Example:**
```python
def forward(self, task_input: str) -> dspy.Prediction:
    if self._active_section is None:
        raise RuntimeError("No active section set. Call set_active_section() or set_joint_mode() first.")

    if self._active_section == JOINT_SENTINEL:
        # Joint mode: concatenate all section texts (each from its Predict's
        # signature.instructions) as the active-instruction block, plus a
        # task_input. The selector receives the FULL evolved prompt as context.
        sections_block = "\n\n".join(
            f"[{sid}]: {self.section_predictors[sid].signature.instructions}"
            for sid in self._section_ids
        )
        result = self.selector(
            frozen_context=sections_block,  # the entire evolved prompt sits in frozen_context
            task_input=task_input,
        )
        return dspy.Prediction(output=result.output)

    # Single-section (round-robin) path — UNCHANGED from current impl:
    frozen_context = self._build_frozen_context()
    result = self.selector(frozen_context=frozen_context, task_input=task_input)
    return dspy.Prediction(output=result.output)
```
[CITED: prompt_module.py L101-122]

### Anti-Patterns to Avoid
- **不要为 joint mode 创建独立的 selector**:`PromptSectionSignature` 的 `frozen_context + task_input → output` 已能消费任意拼接 prompt。新增第二个 selector 会让 metric/scoring 不一致(D-discretion 锁定"joint 与 round-robin 必须用同一 metric")。
- **不要在 joint mode 下 filter dataset**:joint 看完整 train/val,GEPA 内部依靠 `pred_name` 把反馈路由到对应 section_predictors[sid]。filter 会让 GEPA 看不到部分 section 的覆盖样本。CONTEXT D-IT-01 已锁定。
- **不要在 forward() joint 路径里循环调用所有 Predict**(候选方案 b):每个 Predict 单独发 LM 调用,N 倍成本且 GEPA reflection 无法把多输出归因到单 section。Pattern 3 中"concat 所有 instructions 进 frozen_context"是唯一让 GEPA 能正确 attribute 的设计 — selector 看到的完整 prompt 包含所有 13 section,GEPA 的 trace 里每个 section_predictors[sid] 都被 named_predictors() 暴露,reflection_lm 通过 pred_name 反馈定向到具体 section instructions。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 多参数轮转 / 联合选择策略 | 自定义 `ReflectionComponentSelector` 类 | `component_selector="all"` 字符串 | DSPy 上游已映射到 `AllReflectionComponentSelector`,字符串接口 stable[VERIFIED: gepa/strategies/component_selector.py L24-32] |
| GEPA budget 估算 | 自己手写公式 | `dspy.GEPA(auto="medium")` 让上游算 | `auto_budget()` 已按 num_preds + valset 智能缩放,公式 verified[VERIFIED: dspy/teleprompt/gepa/gepa.py L443-471] |
| named_parameters() 可见性控制 | 手动 setattr / 删 attr 控制可见性 | `section_predictors: dict[str, dspy.Predict]` | DSPy `dspy.Module` 自动遍历 dict-typed Predict 字段并把所有 entries 通过 `named_predictors()` 暴露 — 当前实现已是这个 pattern[VERIFIED: 本地 venv 实测,见 §Code Examples Pattern 4] |
| Inline A/B 跑两次 baseline 的 module 共享 | 复用 joint 后的 module 跑 round-robin | 新建 fresh `PromptModule(original_sections)` 跑 A/B | joint 已 mutate 过 module 的 instructions;A/B 必须从 originals 重新构造,否则不公平[ASSUMED: 标准 ML 评估实践;无 DSPy 文档直接说明] |
| Diff 多 section 输出 | 自己拼接 section diff | 现有 `_generate_diff()`(evolve_prompt_sections.py L40-72) | 已通过 section_id 遍历输出,joint 多 section 同时变只是 diff_parts 列表更长,零代码改动[VERIFIED: evolve_prompt_sections.py L54-72] |
| 软门 stdout 警告 | 自己设计 exit code / 阻断 | Phase 16 D-13 的 `--warning-threshold-pp` 模式 — yellow stdout + 不影响 exit | 一致风格,运维方已熟悉[CITED: .planning/phases/16-per-tool-regression-dashboard/16-CONTEXT.md §D-13] |

**Key insight:** Phase 13 (`evolve_tool_params.py`) 已经把 `--component-selector` 暴露为 CLI flag,锁定 `Choice(["round_robin", "all"])`。Phase 17 应直接复用同样的 flag 名(但不暴露给用户 — 因为 Phase 17 用 `--mode` 间接控制),内部 mapping:`--mode joint → component_selector="all"`,`--mode round-robin → component_selector="round_robin"`(round-robin baseline 内部 for-loop 用单参 module + `"round_robin"` 都行)。

## Runtime State Inventory

> Phase 17 是新增 feature(joint mode + A/B baseline),无 rename/refactor/迁移成分。

**SKIPPED** — Phase 17 is a feature-addition phase, not a rename/migration phase. No stored data, live service config, OS-registered state, secrets/env vars, or build artifacts need to be migrated:
- **Stored data:** None — Phase 17 不动 ChromaDB/Mem0/Redis/任何外部数据库。
- **Live service config:** None — 不动 n8n/Datadog/Cloudflare 等。
- **OS-registered state:** None — 不动 systemd/cron/launchd。
- **Secrets/env vars:** None — `HERMES_AGENT_REPO` env var 不变;eval_model / optimizer_model 沿用 `EvolutionConfig`。
- **Build artifacts:** None — 不改 pyproject.toml,不重装包。

## Common Pitfalls

### Pitfall 1: 当前 PromptModule forward() 不把 active section 文本流入 selector
**What goes wrong:** 现有 `forward()`(prompt_module.py L101-122)只把 `_frozen_instructions` 拼成 `frozen_context`,而 active section 的文本(在 `section_predictors[active].signature.instructions`)从未传给 selector。换言之,GEPA 反思后修改 active section 的 instructions,实际不会改变 forward() 的输出,metric 给出的反馈对该 section 的 mutation 是 random noise。
**Why it happens:** Round-robin 设计假设 GEPA 内部会自己消费 `Predict.signature.instructions`,但 PromptModule 的 selector 是独立的 ChainOfThought,不引用 active section 的 Predict。
**How to avoid:** Joint mode 的 forward() (Pattern 3) 必须把 **所有 section instructions 拼入 frozen_context** — 包括"active"段。这样 GEPA mutation 的 instructions 真正影响 selector 输出。同时 round-robin 路径也建议在本期顺手修复:`_build_frozen_context()` 改为遍历所有 sections(包括 active),从 `section_predictors[active].signature.instructions` 读 active 文本拼入。
**Warning signs:** 现有 Phase 8/9 测试用 mock selector,无法暴露此问题。运行时 GEPA holdout_score 与 baseline_score 差异极小(<1pp)是信号。
**Confidence:** HIGH — 本研究通过阅读 prompt_module.py L101-131 实测确认 active section 的 instructions 未流入 selector。[VERIFIED: source code inspection]
**Action item for planner:** 把"修复 round-robin 路径也注入 active section text 进 frozen_context"作为 Phase 17 范围内的 hygiene 任务(顺带改);否则 round-robin baseline 的得分代表的是"无 active section 影响下的随机基线",A/B 比较失真。**注意:这是 Phase 17 范围外的隐含 scope creep — planner 应在 plan 阶段标注并询问用户**。如果用户确认不在 Phase 17 修复,A/B 对比的语义就是「joint 全 section 注入 vs round-robin 仅 frozen 注入」,planner 必须在 metrics.json `epsilon_pp` 注释或 README 注明此差异。

### Pitfall 2: `auto` + `max_metric_calls` 互斥导致 GEPA 抛 AssertionError
**What goes wrong:** `dspy.GEPA.__init__` 强制三选一 `(auto, max_full_evals, max_metric_calls)` exactly-one;`gepa_kwargs={"stop_callbacks": [...]}` override 时仍计 1。
**Why it happens:** Upstream assertion `(max_metric_calls is not None) + (max_full_evals is not None) + (auto is not None) == 1`[VERIFIED: dspy/teleprompt/gepa/gepa.py L394-399]。
**How to avoid:** CLI 只允许 `--iterations N` 或 `--auto X` 之一,与 Phase 13 `evolve_tool_params.py:802-806` mutex 风格对齐。joint mode 默认 `--iterations`,planner 决定是否暴露 `--auto`(可走 Phase 13 模式)。
**Warning signs:** CLI 跑起来立刻 assert 报错。
**Confidence:** HIGH

### Pitfall 3: PromptModule.set_active_section() 在 joint mode 后被调用,行为未定义
**What goes wrong:** 用户先 `set_joint_mode(True)`,然后再传 `--section X`(或用户脚本误调),`set_active_section(X)` 当前实现会 pop X 然后试图把"current active"(__JOINT__ 哨兵)塞回 frozen — 而 __JOINT__ 不在 _frozen_sections,会报 KeyError。
**Why it happens:** 现有 `set_active_section` 实现假设 `_active_section in (None, <real_sid>)`,不处理 sentinel。
**How to avoid:** `set_active_section()` 入口加 guard:if `_active_section == JOINT_SENTINEL`,先调 `set_joint_mode(False)` 全部 demote 回 frozen,再走原逻辑。或抛 explicit ValueError。CONTEXT 把这个 decision 显式列为 Claude's Discretion,planner 三选一:**报错 / 自动退化为 round-robin / 静默切换**。**研究推荐:自动退化** — 最低惊讶原则,与 D-RR-03 "--section X 隐含 round-robin 单点" 语义一致。
**Warning signs:** KeyError on `set_active_section` after joint mode。新单测应覆盖此场景。
**Confidence:** HIGH — 通过阅读 prompt_module.py L86-99 确认。

### Pitfall 4: Joint baseline 得分计算需要 fresh PromptModule
**What goes wrong:** 跑完 joint 拿到 `joint_score` 后,直接复用同一 module 跑 round-robin baseline → roundrobin baseline 实际是「在 joint 已 mutate 过 instructions 之上 round-robin 再 mutate」,A/B 失真为 "joint+RR串行" vs "joint 单跑"。
**Why it happens:** module 是可变对象,GEPA.compile 直接 mutate instructions in-place(无 deep copy by default)。
**How to avoid:** A/B baseline 必须 `baseline_ab_module = PromptModule(original_sections)` 重新构造一个 fresh module,从原始 frozen 文本开始 round-robin。
**Warning signs:** roundrobin_baseline_score ≈ joint_score(几乎相同),怀疑 A/B 失败。
**Confidence:** HIGH — DSPy `Module.deepcopy()` / `Module.reset_copy()` 存在但需显式调用;`compile()` 默认返回 mutated student[CITED: dspy/teleprompt/gepa/gepa.py L477-489 compile signature]。

### Pitfall 5: PromptBehavioralMetric 期待 `section_text` 字段,但 joint mode 没有单一 section_text
**What goes wrong:** prompt_metric.py L68 `section_text = getattr(example, "section_text", "") or ""`,然后 LLMJudge 把 `skill_text=section_text` 传给评分 prompt。joint mode 下 `to_dspy_examples(split, section_texts=section_texts)` 会按 ex.section_id 注入单 section_text,但 GEPA 看的是全 dataset 混杂,每个 example 仍只对应一个 section_id — metric 收到的 example 仍带原 section_id 的 section_text,所以这点其实自然 work。
**Why it happens:** 一开始读以为是 bug,深入看 `to_dspy_examples` L146-153 按 ex.section_id 查 dict 注入,每个 example 一个 section_text,joint 下不需要改 metric。
**How to avoid:** 不需要修复 — metric 已自然兼容 joint。**仅需保留 `section_texts=section_texts` 调用语义不变**,但 joint pipeline 调用 `to_dspy_examples("train", section_texts=section_texts)` 时传 `section_texts={sid: original.text for original in original_sections}`(joint 用 baseline 原文,与 round-robin 一致 — section_text 是 judge 评分时的"参考标准",不该用 evolved 文本)。
**Confidence:** HIGH

### Pitfall 6: 13 sections 不是 5 — CONTEXT.md 的预算公式偏小
**What goes wrong:** CONTEXT D-IT-02 `iterations × 50 × 5`,假设 5 section。实际 prompt_loader 提取 4 个 string constants + 9 个 platform_hints.* 子 key = **13 sections**(见 §Verification 中 dataset 实测)。budget 估算偏小 ~2.6×,joint mode 可能在 GEPA 内部还没 converge 就耗尽 budget。
**Why it happens:** CONTEXT 作者按 hermes-agent prompt_builder 的 4+1=5 心智模型估算;但 prompt_loader.py L34 `TARGET_DICT_VAR = "PLATFORM_HINTS"` 与 `_compute_section_targets`(prompt_dataset.py L242-260)按 key 展开,生成 13 个 section_id。
**How to avoid:** Planner 重写 D-IT-02 公式为 `iterations × 50 × num_predictors`,运行时 `num_predictors = len(module.predictors())`(joint mode 下 = 13 + 1 selector = 14)。或暴露 `--auto medium`(推荐)。stdout 预算行打实际 num_predictors 数。
**Warning signs:** GEPA 日志 "Running GEPA for approx N metric calls" 中 N 远低于真实需要;evolved_score 比 baseline_score 改善 <1pp。
**Confidence:** HIGH — dataset.jsonl 实测 13 unique section_ids,prompt_loader.py + prompt_dataset.py 源码已验证。

### Pitfall 7: GEPA metric must accept 5 positional args(`gold, pred, trace, pred_name, pred_trace`)
**What goes wrong:** Phase 12 已修;`PromptBehavioralMetric.__call__` L44-50 已是 5-param 签名。joint mode 下 GEPA 用 `component_selector="all"` 仍然每 iteration 用每个 predictor name 调 metric 取 feedback,所以 metric 必须接受 pred_name 参数。**当前 prompt_metric.py 已合规**,无需改。
**How to avoid:** 单测应继续 patch metric 在 joint mode 下被 5-arg 调用。
**Confidence:** HIGH — 本研究通过 prompt_metric.py L44-50 + dspy GEPAFeedbackMetric Protocol L30-50 双向确认[VERIFIED]。

### Pitfall 8: PromptModule.set_joint_mode 没设 `_active_section` 时 forward 仍走 RuntimeError 分支
**What goes wrong:** 用户实现 `set_joint_mode(True)` 但忘了把 `_active_section = JOINT_SENTINEL`,forward() 第一行 `if self._active_section is None` 仍触发 RuntimeError。
**How to avoid:** Pattern 2 代码中 `self._active_section = JOINT_SENTINEL` 那行必须存在。新单测 `test_forward_in_joint_mode_works` 覆盖。
**Confidence:** HIGH — 推荐设计自身保证。

### Pitfall 9: 14 tests vs CONTEXT.md 说 "11 tests"
**What goes wrong:** CONTEXT.md 多处提"11 个现有测试用例零回归",但 `tests/prompts/test_prompt_module.py` 实测共 14 个 test。
**Why it happens:** CONTEXT 作者按记忆估算,未实际 `pytest --collect-only`。
**How to avoid:** Planner 按实际 14 个为基线,plan 验证步骤明确 "tests/prompts/test_prompt_module.py 14 tests zero regression"。
**Confidence:** HIGH — `.venv/bin/python -m pytest tests/prompts/test_prompt_module.py --collect-only` 实测输出 "14 tests collected"。

## Code Examples

### Pattern 4: Verify `named_predictors()` exposes all dict entries (实测)
```python
# Source: 本研究通过本地 venv 实测 (.venv/bin/python; dspy 3.1.3)
# Confirms section_predictors: dict[str, Predict] 自动暴露所有 entries 给 GEPA。

import dspy
from evolution.prompts.prompt_module import PromptModule
from evolution.prompts.prompt_loader import PromptSection
from pathlib import Path

sections = [
    PromptSection('a', 'A text', 6, (1,2), Path('/fake')),
    PromptSection('b', 'B text', 6, (3,4), Path('/fake')),
    PromptSection('c', 'C text', 6, (5,6), Path('/fake')),
]
m = PromptModule(sections)
# Phase 17 joint mode 模拟:把所有 sections 升级为 Predict
for sid in ['a', 'b', 'c']:
    text = m._frozen_instructions.pop(sid)
    sig = dspy.Signature('section_text -> confirmation', instructions=text)
    m.section_predictors[sid] = dspy.Predict(sig)

print([n for n, _ in m.named_predictors()])
# 实测输出:
# ["section_predictors['a']", "section_predictors['b']", "section_predictors['c']", 'selector.predict']
# → 4 个 Predict 全可见,GEPA component_selector="all" 会同时反思 a/b/c。
```

### Pattern 5: A/B baseline run 编排(inline,新建 fresh module)
```python
# Source: design proposal — extends evolution/prompts/evolve_prompt_sections.py L356-388

if mode == "joint":
    # ── joint already done by this point; joint_score computed ──

    console.print(f"\n[bold]Inline A/B baseline: round-robin on same dataset[/bold]")
    ab_baseline_module = PromptModule(original_sections)  # fresh copy
    metric_ab = PromptBehavioralMetric(config)             # same metric instance OK

    start_ab = time.time()
    for active_sid in ab_baseline_module._section_ids:
        ab_baseline_module.set_active_section(active_sid)
        section_train = [ex for ex in dataset.train if ex.section_id == active_sid]
        section_val   = [ex for ex in dataset.val   if ex.section_id == active_sid]
        if not section_train:
            continue
        temp_ds = PromptBehavioralDataset(train=section_train, val=section_val, holdout=[])
        trainset_ab = temp_ds.to_dspy_examples("train", section_texts=section_texts)
        valset_ab   = temp_ds.to_dspy_examples("val",   section_texts=section_texts)

        optimizer = dspy.GEPA(
            metric=metric_ab,
            max_metric_calls=iterations * 50,           # single-param budget
            reflection_lm=dspy.LM(config.optimizer_model, **config.get_lm_kwargs()),
            component_selector="round_robin",            # default, but explicit for clarity
        )
        ab_baseline_module = optimizer.compile(
            ab_baseline_module, trainset=trainset_ab, valset=valset_ab,
        )

    # Score A/B baseline on SAME holdout
    rr_baseline_scores = []
    for ex in holdout_examples:
        with dspy.context(lm=lm):
            for sid in ab_baseline_module._section_ids:
                ab_baseline_module.set_active_section(sid); break
            rrp = ab_baseline_module(task_input=ex.task_input)
            rr_baseline_scores.append(metric_ab(ex, rrp, trace=None))
    roundrobin_baseline_score = sum(rr_baseline_scores) / max(1, len(rr_baseline_scores))
    elapsed_ab = time.time() - start_ab

    # Soft gate
    epsilon_pp = 0.01
    if joint_score < roundrobin_baseline_score - epsilon_pp:
        delta_pp = (roundrobin_baseline_score - joint_score) * 100
        console.print(
            f"[yellow]Joint score ({joint_score:.3f}) below round-robin baseline "
            f"({roundrobin_baseline_score:.3f}) by {delta_pp:.1f}pp — review before deploying[/yellow]"
        )
    else:
        console.print(
            f"[green]Joint score ({joint_score:.3f}) ≥ round-robin baseline "
            f"({roundrobin_baseline_score:.3f}) within epsilon ({epsilon_pp*100:.0f}pp)[/green]"
        )

    # Persist
    metrics.update({
        "mode": "joint",
        "joint_score": joint_score,
        "roundrobin_baseline_score": roundrobin_baseline_score,
        "epsilon_pp": epsilon_pp,
        "ab_elapsed_seconds": elapsed_ab,
    })
```
[CITED: Phase 16 D-13 soft-gate pattern; Phase 13 `--component-selector` reuse]

### Pattern 6: Budget pre-flight stdout (Phase 13 风格)
```python
# Source: design proposal — extends Phase 13 dry-run stdout (evolve_tool_params.py L743-751)
# Also extends Phase 17 D-IT-03 sample format.

num_predictors = len(module.predictors())            # = 14 (13 sections + 1 selector)
joint_budget = iterations * 50 * num_predictors      # or use auto_budget for accuracy
rr_per_sec_budget = iterations * 50                  # single-param baseline
rr_total_budget = rr_per_sec_budget * len(module._section_ids)

console.print(f"\n[bold]Configuring optimizer[/bold]")
console.print(f"  Joint optimization:        iterations={iterations}, max_metric_calls={joint_budget}")
console.print(f"  Round-robin A/B baseline:  iterations={iterations}/section × {len(module._section_ids)} sections, "
              f"max_metric_calls={rr_per_sec_budget}/section")
console.print(f"  Total est. LM calls:       ~{joint_budget} (joint) + ~{rr_total_budget} (baseline) "
              f"= ~{joint_budget + rr_total_budget}")
console.print(f"  Eval model: {config.eval_model}")
console.print(f"  Reflection model: {config.optimizer_model}")
```
[CITED: evolution/tools/evolve_tool_params.py L743-751; CONTEXT.md D-IT-03]

### Pattern 7: Fake GEPA mock 风格(测试)
```python
# Source: tests/tools/test_evolve_tool_params_cli.py L66-93 (Phase 13 风格)
# Confirmed working in production test suite.

with patch("evolution.prompts.evolve_prompt_sections.dspy.GEPA") as mock_gepa, \
     patch("evolution.prompts.evolve_prompt_sections.dspy.LM"), \
     patch("evolution.prompts.evolve_prompt_sections.extract_prompt_sections", return_value=fake_sections), \
     patch("evolution.prompts.evolve_prompt_sections.PromptDatasetBuilder") as mock_ds_builder:
    # mock GEPA.compile() returns the module unchanged (deterministic)
    mock_gepa.return_value.compile.side_effect = lambda mod, trainset, valset=None: mod
    # ... (mock dataset, metric, constraints) ...

    runner = CliRunner()
    result = runner.invoke(main, ["--mode", "joint", "--iterations", "2"])
    assert result.exit_code == 0
    # CRITICAL: prove component_selector="all" was actually passed to GEPA
    init_kwargs = mock_gepa.call_args.kwargs
    assert init_kwargs.get("component_selector") == "all", (
        f"Joint mode must call GEPA with component_selector='all', "
        f"got {init_kwargs.get('component_selector')!r}"
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `for sid in sections: set_active_section(sid); GEPA.compile(...)` 5 次串行 | `set_joint_mode(True); GEPA(component_selector="all").compile(...)` 1 次 | DSPy 3.0+ `component_selector` 参数 expose(2025) | 1 次 compile,GEPA pareto frontier 跨 13 section 联合维护;反思 LM 可以"section A 改 X 顺手把 B 也改成 Y"做协调更新。 |
| 自定义 ReflectionComponentSelector class | `component_selector="all"` 字符串 | DSPy 显式映射(L351) | 字符串接口 stable;自定义 selector 是 Advanced API,本期 deferred 不动 |
| Linear budget `iterations × 50 × num_predictors` | `auto="medium"` 内部 log2 缩放 | DSPy `auto_budget` 公式锁定 | 上游公式对 14 predictors / 20 val example 计算 ~7200 metric_calls(medium),与本期"iterations=10 × 50 × 14 = 7000"几乎重合。Planner 可任选,但 `auto` 更未来 proof。 |

**Deprecated/outdated:** 无 — joint section optimization 是上游近期 (2025) 新引入的多参数优化能力,本期是首次在 hermes-agent self-evolution 项目中使用。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "Fresh PromptModule(original_sections) 跑 A/B baseline 避免 mutation 污染" 是标准 ML 实践 | Pitfall 4 / Pattern 5 | DSPy 文档未直接说;若 `optimizer.compile()` 内部 deep-copy student 而非 mutate,fresh module 是多余的(成本无差异)。验证:用 `id()` 对比 compile 前后 module。无负影响 — fresh module 总安全。 |
| A2 | "GEPA reflection_lm 能正确把多 section 反思归因到各自 Predict" 在 joint mode 下成立 | Architecture Patterns Pattern 3 | 若 reflection_lm 难以归因(全 13 section 文本同时进 reflection prompt,模型可能笼统建议),joint 实际收敛慢于 round-robin。但这是 GEPA upstream 的设计选择,本研究不能预先证伪 — 必须实测 holdout 验证。Phase 17 success criteria 3 "joint ≥ round-robin on holdout" 本身就是这个 hypothesis 的实证测试。 |
| A3 | "把所有 section instructions concat 进 frozen_context 是正确的 joint forward 设计"(Pattern 3) | Architecture Patterns Pattern 3 | 候选方案 b(per-section 串行 Predict 调用)未实测;若 concat 让 selector 输入过长(13 section × ~500 chars = 6500 chars + frozen_context overhead),可能触发 LM context 上限。需 planner 在 plan 阶段评估 — 若 hermes-agent prompt 总长 >7000 chars,需考虑 context truncation。 |
| A4 | "13 sections 是稳定数量"(prompt_loader 不会再增加 platform 子 key) | Pitfall 6 / Budget Formula | hermes-agent prompt_builder.py 若新增 platform(如 platform_hints.facetime),section 数会变。num_predictors 应运行时取 `len(module.predictors())`,不能 hardcode 13/14。 |
| A5 | "Phase 17 不需要修复 Pitfall 1(active section 文本未流入 selector)" 是默认选择 | Pitfall 1 | 若用户审 plan 时要求顺手修(scope creep),Phase 17 plan 多 1-2 task。若不修,A/B 比较的"joint vs round-robin"语义实际是"全文注入 vs 仅 frozen 注入"— planner 必须在 README/metrics.json 注明此语义差。 |

**确认需求(planner 应在 plan-check 阶段问用户):**
- A5:Pitfall 1 是否纳入 Phase 17 范围?推荐"是",但属 scope creep 决定。
- A3:joint forward concat 设计 vs per-section serial — 若用户对 selector LM context 长度敏感,需要另设计。

## Open Questions

1. **Phase 17 是否顺手修复 Pitfall 1?**
   - What we know: 现有 round-robin forward() 不把 active section 文本注入 selector → A/B baseline 的 round-robin 实际跑的是"无 active section 影响"基线。
   - What's unclear: 修复后所有 Phase 8/9/10 baseline metrics 都会变;CONTEXT D-RR-01 锁定"11(实际 14)个现有测试用例零改写",修 forward() 会让现有 `test_forward_returns_prediction` 之类的 mock 期望失效。
   - Recommendation: Planner 在 plan-check 显式问用户 → 推荐"修",同时把现有 forward 测试改为 explicit 验证"frozen_context 包含所有 section"(不是仅 frozen)。

2. **num_predictors 是 13 还是 14?**
   - What we know: prompt_module 有 13 section_predictors + 1 self.selector(ChainOfThought 内含 1 Predict)= 14 predictors。
   - What's unclear: GEPA `component_selector="all"` 会把 selector.predict 也当作 candidate 反思 — 这是希望的吗?selector 的 instructions 来自 `PromptSectionSignature` 的 docstring,被 GEPA 改写可能引入意外行为。
   - Recommendation: Planner 评估是否在 joint mode 下 freeze selector(`self.selector` 改为外部传入或加 `_frozen_selector_instructions`)。或简单接受"GEPA 也优化 selector docstring"作为额外收益(selector 是 reasoning template,GEPA 改它实际可能有用)。

3. **GEPA `auto` vs `iterations` 哪个作 Phase 17 CLI 默认?**
   - What we know: D-IT-02 锁 `iterations × 50 × 5`(实际应 `× num_predictors`);Phase 13/15 已暴露 `--auto`。
   - What's unclear: CONTEXT 未明确 Phase 17 CLI 是否新增 `--auto` flag。
   - Recommendation: 保持 CONTEXT D-IT-01 锁定的 `--iterations N` 为主,**不加** `--auto` flag(deferred);planner 内部把 `iterations × 50 × num_predictors` 当 max_metric_calls 即可。若用户后续要求暴露 `--auto`,可后期加。

4. **A/B baseline 储存布局:同目录前缀 vs 子目录(D-discretion)?**
   - What we know: D-OUT-01 锁定共用 `output/prompts/<ts>/`;D-discretion 说"shared prefix vs `baseline/` subdir"。
   - What's unclear: Phase 22+ dashboard 未来如何扫描 — 但本期 D-OUT-04 锁"不接 dashboard",所以扫描复杂度不是约束。
   - Recommendation: **shared prefix**(`joint_metrics.json` 内嵌 `roundrobin_baseline_score` 字段、`diff.txt` 不区分、`evolved_sections.json` 仅 joint 结果)— 最小目录嵌套,A/B baseline 的中间产物(roundrobin_evolved_sections.json)若用户后续要看可加 `baseline_evolved_sections.json` 同级文件。Planner 决定具体文件名。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | ✓ | 3.13.3 (.venv) | — |
| dspy | GEPA optimizer + component_selector="all" | ✓ | 3.1.3 (≥3.0 requires) | — |
| gepa (transitive) | AllReflectionComponentSelector | ✓ (via dspy) | bundled | — |
| openai | LM API client | ✓ | (via dspy) | — |
| click | CLI flags | ✓ | (via existing) | — |
| rich | console output | ✓ | (via existing) | — |
| pytest | Test runner | ✓ | (dev extra) | — |
| `HERMES_AGENT_REPO` env var | Locate prompt_builder.py | ✓ (project convention) | — | Falls back to `~/.hermes/hermes-agent` or `../hermes-agent` |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | LM calls | (external) | — | CLI dry-run 不需要 |
| LLM credits | GEPA reflection_lm + eval_lm | (external) | — | dry-run 不消耗;真实跑预算 $5-15(joint × 1 + round-robin × 1 同跑) |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 (+ pytest-asyncio >=0.21 dev extra) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` (testpaths = ["tests"], python_files = ["test_*.py"]) |
| Quick run command | `.venv/bin/python -m pytest tests/prompts/test_prompt_module.py tests/prompts/test_evolve_prompt_sections.py -q` |
| Full suite command | `.venv/bin/python -m pytest tests/ -q` |
| Conftest | `tests/conftest.py` (existing, shared fixtures) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PMPT-V2-01 / SC1: PromptModule supports all-sections-active mode | `set_joint_mode(True)` makes all 13 (or N) sections discoverable via `named_predictors()` | unit | `pytest tests/prompts/test_prompt_module.py::TestJointMode::test_set_joint_mode_exposes_all_predictors -x` | Wave 0 (NEW class) |
| PMPT-V2-01 / SC1: idempotency | `set_joint_mode(True)` then `set_joint_mode(True)` again should not error / double-add | unit | `pytest tests/prompts/test_prompt_module.py::TestJointMode::test_set_joint_mode_idempotent -x` | Wave 0 NEW |
| PMPT-V2-01 / SC1: backward compat | After `set_joint_mode(True)`, calling `set_active_section(X)` auto-demotes joint and activates single | unit | `pytest tests/prompts/test_prompt_module.py::TestJointMode::test_joint_then_set_active_section_auto_demotes -x` | Wave 0 NEW (resolves Pitfall 3) |
| PMPT-V2-01 / SC2: GEPA mutates multiple sections in one pass | CLI invocation with `--mode joint` calls `dspy.GEPA(..., component_selector="all").compile(...)` exactly once with all 13 sections in section_predictors | integration | `pytest tests/prompts/test_evolve_prompt_sections.py::TestJointPipeline::test_joint_mode_calls_gepa_with_component_selector_all -x` | Wave 0 NEW |
| PMPT-V2-01 / SC2: Single GEPA call in joint mode | `mock_gepa.compile.call_count == 1` for joint, not 13 | integration | (same) | Wave 0 NEW |
| PMPT-V2-01 / SC2: --mode round-robin legacy | `--mode round-robin` still calls compile 13 times (one per section) | integration | `pytest tests/prompts/test_evolve_prompt_sections.py::TestJointPipeline::test_round_robin_mode_compiles_per_section -x` | Wave 0 NEW |
| PMPT-V2-01 / SC2: --section X implicit round-robin | `--section memory_guidance --mode joint` 仍走 round-robin 单点,不报错 | integration | `pytest tests/prompts/test_evolve_prompt_sections.py::TestJointPipeline::test_section_flag_forces_round_robin -x` | Wave 0 NEW |
| PMPT-V2-01 / SC3: Joint score ≥ round-robin on holdout | A/B 跑通,metrics.json 含 `mode`、`joint_score`、`roundrobin_baseline_score`、`epsilon_pp` | integration | `pytest tests/prompts/test_evolve_prompt_sections.py::TestABBaseline::test_joint_mode_runs_inline_ab_baseline -x` | Wave 0 NEW |
| Soft-gate / D-AB-02 | joint < rr - epsilon 时 stdout 含黄警告但 exit_code == 0 | integration | `pytest tests/prompts/test_evolve_prompt_sections.py::TestABBaseline::test_soft_gate_warns_but_does_not_block -x` | Wave 0 NEW |
| Zero regression: existing 14 PromptModule tests | All 14 tests in `tests/prompts/test_prompt_module.py` pass unchanged | unit | `pytest tests/prompts/test_prompt_module.py -v` | Existing ✅ |
| Zero regression: existing CLI tests | 4 tests in `tests/prompts/test_evolve_prompt_sections.py` (test_cli_help, test_cli_help_section_option, test_dry_run, test_evolve_orchestration_order, test_section_filter, test_module_importable) pass with `--mode round-robin` mode-equivalent behavior | integration | `pytest tests/prompts/test_evolve_prompt_sections.py -v` | Existing — may need minor mock adjustment |
| Budget stdout pre-flight (D-IT-03) | dry-run with `--mode joint` 输出含 "Joint optimization:" / "Round-robin A/B baseline:" / "Total est." 三行 | integration | `pytest tests/prompts/test_evolve_prompt_sections.py::TestDryRun::test_dry_run_prints_budget_estimate -x` | Wave 0 NEW |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/prompts/ -q` (~30s,33 tests after Wave 0 完成)
- **Per wave merge:** `.venv/bin/python -m pytest tests/ -q` (~3-5min,~400 tests total project)
- **Phase gate:** Full suite green + manual smoke `python -m evolution.prompts.evolve_prompt_sections --dry-run --hermes-repo /fake` 验证 budget stdout 格式

### Wave 0 Gaps
- [ ] `tests/prompts/test_prompt_module.py::TestJointMode` — covers SC1 (joint mode visibility, idempotency, auto-demote)
- [ ] `tests/prompts/test_evolve_prompt_sections.py::TestJointPipeline` — covers SC2 (component_selector="all" wiring, --mode round-robin legacy, --section implicit RR)
- [ ] `tests/prompts/test_evolve_prompt_sections.py::TestABBaseline` — covers SC3 + soft-gate (joint runs A/B inline, metrics.json schema, yellow warning + exit 0)
- [ ] `tests/prompts/test_evolve_prompt_sections.py::TestDryRun::test_dry_run_prints_budget_estimate` — covers D-IT-03 budget stdout
- [ ] Optional shared fixture: `_make_joint_promptmodule_with_n_sections(n: int)` helper in test file or conftest — DRY for joint mode test setup

**Framework install:** No new install — pytest + pytest-asyncio + dspy + click + rich all present.

## Security Domain

> Phase 17 是内部优化管道,无外部接口/认证/会话/数据持久化层(metrics.json + evolved_sections.json 是本地 file dump,无网络暴露)。下表列出适用 ASVS 类别。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — CLI 工具,无认证 |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A |
| V5 Input Validation | yes | `click.Choice(["joint", "round-robin"])` 强制 mode 输入合法;`--iterations` 用 `click.IntRange(min=1)` 限制(planner 决定是否加);`--section X` 现有 validation 在 evolve_prompt_sections.py L156-161 已 fail-fast。 |
| V6 Cryptography | no | N/A — 无加密需求 |
| V7 Error Handling | yes | constraint validation 失败落 `FAILED_<ts>/` 目录(现有模式),不暴露 stack trace。GEPA 抛 RuntimeError 时:Phase 17 应沿用 Phase 13 D-15a "loud GEPA failure" 模式 — 不静默 fallback 到 MIPROv2,而是 propagate 异常(`--allow-miprov2-fallback` opt-in 是 Phase 13 决定,本期不强制对齐,planner 决定)。 |
| V14 Configuration | yes | `HERMES_AGENT_REPO` env var 走 `EvolutionConfig.load()` 现有路径,不引入新配置。`max_prompt_growth = 0.2` 在 EvolutionConfig 中央。 |

### Known Threat Patterns for {DSPy/GEPA optimization}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection from synthetic dataset | Tampering | Phase 9 `PromptDatasetBuilder` 已用 LLM 生成 — 输出受 judge_model 控制,不直接进 hermes-agent prompt;Phase 17 joint mode 把 evolved instructions 落 `evolved_sections.json`,**不 write-back** hermes-agent — 攻击面 = 文件落盘,本地隔离。 |
| LLM cost runaway(GEPA budget 不限) | Denial of Service(对用户钱包) | `--iterations N` 用户显式控制;Phase 13 `CostTracker` + `_CostStopper`(Phase 13 D-15)在 tool 管道已有;Phase 17 可考虑沿用(planner 决定是否纳入 — CONTEXT 未列入 in-scope)。**Researcher 建议:本期不引入 CostTracker**,保持范围聚焦,joint+RR 串跑确实 2× cost,但用户已知(D-AB-04)。 |
| Evolved instructions 含恶意指令(jailbreak) | Tampering | `PromptRoleChecker.check_all` LLM-based 检查角色保持,捕获大部分功能漂移;`_check_growth` 限 +20% size。两者已 in-place,joint mode 自然适配。 |
| 反思 LM 看到敏感数据(synthetic example 含 secrets) | Information Disclosure | `evolution/core/external_importers._contains_secret` 已在 dataset 生成层过滤;Phase 17 不动 dataset 生成路径,继承现有保护。 |

## Sources

### Primary (HIGH confidence)
- **DSPy GEPA upstream source** — `https://raw.githubusercontent.com/stanfordnlp/dspy/main/dspy/teleprompt/gepa/gepa.py`:
  - `AUTO_RUN_SETTINGS = {"light":{"n":6}, "medium":{"n":12}, "heavy":{"n":18}}` L21-25
  - `component_selector: "ReflectionComponentSelector | str" = "round_robin"` L351 (constructor default)
  - `component_selector` docstring L254-261 (lists `"round_robin"` and `"all"` as built-in options)
  - `auto_budget(num_preds, num_candidates, valset_size, ...)` L443-471 (full formula)
  - `compile()` budget resolution L477-489 (auto → max_metric_calls via auto_budget; max_full_evals → linear × len(train+val))
  - `GEPAFeedbackMetric` Protocol L31-50 (5-arg signature: gold, pred, trace, pred_name, pred_trace)
- **gepa upstream selectors** — `https://raw.githubusercontent.com/gepa-ai/gepa/main/src/gepa/strategies/component_selector.py`:
  - `RoundRobinReflectionComponentSelector` L10-22 (cycles through `state.list_of_named_predictors`)
  - `AllReflectionComponentSelector` L25-32 (returns `list(candidate.keys())` — all predictors per iteration)
- **Local DSPy 3.1.3 实测** — `.venv/bin/python` 直接验证:
  - `dspy.__version__ == '3.1.3'`
  - `dspy.GEPA(... component_selector='all' ...)` 接受参数,`.component_selector == 'all'`
  - `PromptModule` 加 3 dict entries 后 `named_predictors()` 返回 4 项(3 section_predictors + 1 selector.predict)
- **Phase 13 prior art** — `evolution/tools/evolve_tool_params.py`:
  - L579-581 `--component-selector` CLI flag 定义(`click.Choice(["round_robin", "all"])`)
  - L797 `component_selector` 传 GEPA init kwargs
  - L805-807 `max_metric_calls=max(iterations * 50, 3 * num_predictors)` 多参数 budget 公式
  - L743-751 dry-run budget stdout pre-flight pattern
- **Phase 16 prior art** — `.planning/phases/16-per-tool-regression-dashboard/16-CONTEXT.md` §D-13:
  - Soft-gate "warning + 不返 exit code" 模式(直接照搬给 Phase 17 A/B 软门)
  - §D-12 schema 扩展 + persist helper 不可变模式(`persist_per_tool_rates` 镜像)
- **PromptModule existing source** — `evolution/prompts/prompt_module.py` L1-156:
  - `section_predictors: dict[str, dspy.Predict]` L52 (dict 已是 DSPy named_predictors() 自动遍历的容器)
  - `set_active_section()` L71-99 (round-robin 切换语义,joint mode 设计延展)
  - `forward()` L101-122(本研究 Pitfall 1 重大发现的源头)
  - `get_evolved_sections()` L133-155(joint mode 仅多走 13 个 section_predictors 分支,自然适配)
- **Existing test baseline** — `tests/prompts/test_prompt_module.py` 14 tests collected via `pytest --collect-only`(CONTEXT.md "11 tests" 偏差 — 见 Pitfall 9)
- **Phase 17 CONTEXT.md** — `.planning/phases/17-joint-section-optimization/17-CONTEXT.md` — 所有 D-* decisions

### Secondary (MEDIUM confidence)
- DSPy GEPA Advanced docs — `https://dspy.ai/api/optimizers/GEPA/GEPA_Advanced/` (WebFetch 受限,通过 WebSearch 摘要 + GitHub 源码交叉验证 — 公开文档与源码 L254-261 docstring 内容一致)
- DSPy GEPA Overview — `https://dspy.ai/api/optimizers/GEPA/overview/` (WebSearch 摘要;component_selector / auto / max_metric_calls 三参数关系与 GitHub 源码 L394-399 assertion 一致)
- HuggingFace Open-Source AI Cookbook — `https://huggingface.co/learn/cookbook/en/dspy_gepa` (经验性 budget number 来源)
- DeepWiki "GEPA & SIMBA: Reflective and Stochastic Optimization" — `https://deepwiki.com/stanfordnlp/dspy/4.5-gepa:-reflective-prompt-evolution`(component_selector round-robin/all 实现细节描述)

### Tertiary (LOW confidence)
- Medium / Gist / individual tutorial blog posts(列在 WebSearch 结果中)— 用于多源交叉验证 budget 经验数字,不作为 primary。

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — DSPy 上游源码 + 本地 venv 双向实测,Phase 13 prior art 现成。
- Architecture: HIGH — `component_selector="all"` 是上游原生 API;PromptModule 三态状态机为本研究新设计,但与现有 set_active_section 同源,planner 可信。Pitfall 1(active section 文本未流入 selector)是本研究通过源码阅读发现的关键 issue,需 planner 评估 scope。
- Pitfalls: HIGH — 9 个 pitfall 均有源码引用或实测验证,无猜测。
- A/B baseline 设计: MEDIUM-HIGH — Pattern 5 是新代码设计,Phase 13/16 模式可类比但本期是首次 prompt 维度 inline A/B,planner plan 阶段值得过一遍。
- Budget formula: HIGH — 上游 `auto_budget` 公式逐行验证。

**Research date:** 2026-05-15
**Valid until:** 2026-06-15(DSPy 3.x stable;若 dspy 升级到 4.x 需重新验证 `component_selector` API stability)。本研究的 dspy 上游引用基于 `main` 分支源码 — 若 stanfordnlp/dspy upstream 在 1 个月内对 GEPA API 做 breaking change,部分细节需重新拉取。本地 venv 锁 3.1.3 减轻该风险。

---

*Phase: 17-joint-section-optimization*
*Research completed: 2026-05-15*
*Researcher: gsd-researcher*
