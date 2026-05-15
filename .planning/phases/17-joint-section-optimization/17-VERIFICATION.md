---
phase: 17-joint-section-optimization
verified: 2026-05-15T09:00:00Z
status: human_needed
score: 8/9 must-haves verified
overrides_applied: 0
human_verification:
  - test: "End-to-end joint optimization on real hermes-agent prompt_builder.py (13 sections)"
    expected: "joint_score >= roundrobin_baseline_score - EPSILON_PP on holdout, OR yellow warning triggers and both artifacts persist with metrics.json containing 5 new fields"
    why_human: "Requires real OPENAI_API_KEY or OPENROUTER_API_KEY + ~$5-10 budget for a single GEPA run; cannot verify with mocks because Roadmap Success Criterion 3 explicitly compares LLM-judge scores on real holdout data. Mock-based tests prove the mechanism is in place; only a real run proves SC3."
  - test: "Soft-gate warning visibility in real-terminal stdout (rich console rendering)"
    expected: "When joint regresses past EPSILON_PP, [yellow] warning containing 'review before deploying' is visible in a normal 80+ char terminal"
    why_human: "rich wraps lines based on terminal width; CliRunner uses 80-char default and tests already normalize whitespace defensively. A real terminal run confirms human-readability under expected user conditions."
---

# Phase 17: Joint Section Optimization — Verification Report

**Phase Goal:** 让 GEPA 把 hermes-agent prompt 的全部 section (实测 13 个) 视为一组参数同时优化,取代当前的 round-robin。CLI 默认 `--mode joint` 调用 DSPy GEPA `component_selector="all"` 单次 compile,joint 跑完 holdout 评估后 inline 跑 round-robin A/B baseline (fresh PromptModule + 同 dataset/metric/holdout),软门 1pp 比较 + 双方都落盘 (shared-prefix output layout)。

**Verified:** 2026-05-15T09:00:00Z
**Status:** human_needed (mechanism verified in code & mocks; real-run validation of SC3 deferred to human checkpoint)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (merged from Roadmap Success Criteria + Plan frontmatter)

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | **SC1**: PromptModule supports all-sections-active mode (all Predicts discoverable) | VERIFIED | `set_joint_mode(True)` 后实测 `named_predictors()` 返回 N 个 `section_predictors['<sid>']` entries(3 fixture / 13 real hermes-agent),selector.predict 被 `_frozen_predictor_ids` 过滤。Live spot-check 输出 `["section_predictors['s0']", "section_predictors['s1']", "section_predictors['s2']"]`。 |
| 2 | **SC2**: GEPA can mutate multiple sections in one pass | VERIFIED | `evolve_prompt_sections.py:348-361` 调用 `dspy.GEPA(component_selector="all", ...).compile(module, ...)` 一次;CLI 默认 `--mode joint`(line 801);`test_joint_mode_default_calls_gepa_with_component_selector_all` PASS — 断言 `compile.call_count == 1` + `component_selector="all"` + `set_joint_mode.called_with(True)` + `set_active_section.call_count == 0`。 |
| 3 | **SC3**: Joint optimization produces equal or better scores than round-robin on holdout | MECHANISM_VERIFIED | 可证伪机制已就位:inline A/B baseline (line 552-635) + soft gate (line 645-656) + metrics.json 5 字段 (line 705-724) + 共享前缀 baseline 副本文件 (line 733-745)。3 个 TestABBaseline 测试 PASS,覆盖正向(joint 胜)、负向(joint 输 → 黄警告 + delta_pp 写盘)、round-robin mode skip 三类场景。**实际"joint ≥ rr on real holdout" 须真实 LLM 跑通才能闭环 — 见 human_verification。** |
| 4 | **Pitfall 1 fix**: round-robin 单 active 路径下 GEPA 反思的 instructions 实际影响 forward 输出 | VERIFIED | `prompt_module.py:215-217` round-robin active 分支从 `section_predictors[active].signature.instructions` 读取(而非 `_frozen_instructions[active]`);测试 `test_forward_in_round_robin_includes_active_text` PASS。 |
| 5 | **Selector freeze**: joint mode 下 `selector.predict` 不暴露给 GEPA | VERIFIED | `named_predictors()` 覆写 (line 224-237) + `_frozen_predictor_ids = {"selector.predict"}` (line 85);测试 `test_named_predictors_in_joint_mode_excludes_selector` 严格断言 `"selector.predict" not in names` 且 `len(named) == 3`。 |
| 6 | **Pitfall 3 fix**: set_active_section(sid) 在 JOINT_SENTINEL 状态下自动 demote 不抛 KeyError | VERIFIED | `prompt_module.py:102-103` 进入 `set_active_section` 时 `if self._active_section == JOINT_SENTINEL: self.set_joint_mode(False)`;`test_joint_then_set_active_section_auto_demotes` PASS。 |
| 7 | **W1 single-source mode resolution**: `_resolve_effective_mode` 在 dry-run 与 main 两处统一调用 | VERIFIED | `grep -c '"round-robin" if section else mode'` 返回 1(literal 只存在于 helper 内);main path 与 dry-run gate 都调用 `_resolve_effective_mode(section, mode)`。 |
| 8 | **W2 loud-fail invariant**: joint 分支 GEPA.compile NO try/except,异常向上 propagate | VERIFIED | `evolve_prompt_sections.py:356-361` 内嵌注释 `# NO try/except: loud-fail per W2 invariant / D-15a parity`;round-robin 分支 (line 405-438) 保留 GEPA→MIPROv2 fallback;两条路径行为对称且文档化。 |
| 9 | **metrics.json schema**: 5 新字段 (mode / joint_score / roundrobin_baseline_score / epsilon_pp / joint_vs_roundrobin_delta_pp) + 共享前缀副本文件 | VERIFIED | `evolve_prompt_sections.py:703-724` 装配 metrics dict(`mode` 始终写入,joint-only 4 字段显式 gate);line 733-745 写 `roundrobin_baseline_evolved_sections.json` + `roundrobin_baseline_diff.txt`;`test_joint_mode_runs_inline_ab_baseline` 与 `test_round_robin_mode_skips_ab_baseline_and_extra_files` 共同断言两 mode 字段差异。 |

**Score:** 8/9 truths VERIFIED + 1 MECHANISM_VERIFIED (awaits human run-time validation)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `evolution/prompts/prompt_module.py` | set_joint_mode + JOINT_SENTINEL + forward 三态 + selector freeze + Pitfall 1 fix | VERIFIED | 261 lines (vs 156 baseline);`JOINT_SENTINEL`、`set_joint_mode`、`named_predictors`、`_frozen_predictor_ids`、三态 `_build_frozen_context` 全部存在 |
| `tests/prompts/test_prompt_module.py` | TestJointMode 类 + 21 测试 | VERIFIED | 388 lines;21 测试全 PASS;`TestJointMode` 类含 7 个方法 |
| `evolution/prompts/evolve_prompt_sections.py` | --mode flag + joint pipeline + budget preview + inline A/B + soft gate + metrics schema | VERIFIED | 823 lines (vs 518 baseline);`click.Choice(["joint", "round-robin"])`、`component_selector="all"`、`EPSILON_PP=0.01`、`_resolve_effective_mode`、`ab_baseline_module = PromptModule(original_sections)`、`joint_vs_roundrobin_delta_pp`、shared-prefix 副本文件落盘全部存在 |
| `tests/prompts/test_evolve_prompt_sections_cli.py` | TestJointPipeline + TestDryRun + TestABBaseline | VERIFIED | 591 lines;7 测试全 PASS(4 JointPipeline/DryRun + 3 ABBaseline)|

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `set_joint_mode` | `forward` (joint branch) | `_active_section = JOINT_SENTINEL` + section_predictors dict 全填 | WIRED | `self._active_section = JOINT_SENTINEL` 在 prompt_module.py:153;`forward` 三态 (line 161-195) + `_build_frozen_context` joint 分支 (line 212-214) 全部对接 |
| `forward (joint branch)` | `self.selector` | frozen_context = concat 全部 section_predictors[sid].signature.instructions | WIRED | `_build_frozen_context` joint 分支从 `section_predictors[sid].signature.instructions` 拼接;`forward` line 191 `self.selector(frozen_context=..., task_input=...)` 调用 |
| `evolve (joint branch)` | `dspy.GEPA` | component_selector='all' + dynamic budget | WIRED | line 348-355 `dspy.GEPA(component_selector="all", max_metric_calls=joint_budget, ...)`;`joint_budget = max(iterations * 50, 3 * num_predictors) * num_predictors` (line 277) |
| `evolve` | `set_joint_mode(True)` | module.set_joint_mode(True) before GEPA.compile | WIRED | line 275 `module.set_joint_mode(True)`(Step 6a 预算前调用) |
| `_resolve_effective_mode` | evolve(both paths) | single helper called from dry-run gate AND main | WIRED | 3 个调用点:Step 0 main path (line 137)、dry-run gate (line 186)、`grep -c '"round-robin" if section else mode'` = 1 (literal 仅在 helper 内) |
| `evolve (joint post-holdout)` | `evolve (A/B baseline)` | fresh PromptModule(original_sections) + per-section for-loop | WIRED | line 565 `ab_baseline_module = PromptModule(original_sections)`(Pitfall 4 fresh start) + line 568-613 per-section for-loop with `component_selector="round_robin"` |
| soft gate | stdout console.print | [yellow] warning + delta_pp text | WIRED | line 646-650 `[yellow]Joint score (...) below round-robin baseline (...) by {delta_pp:.1f}pp — review before deploying[/yellow]`;line 652-656 [green] 成功路径 |
| persistence | output/prompts/<ts>/metrics.json | mode/joint_score/rr_baseline/epsilon_pp/joint_vs_rr_delta 字段 | WIRED | line 703-724 metrics dict 装配 + line 725 写盘 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `prompt_module.py:_build_frozen_context()` joint branch | `self.section_predictors[sid].signature.instructions` | `set_joint_mode(True)` 在 line 152 `self.section_predictors[sid] = dspy.Predict(sig)` 创建 | Yes — instructions 来自 `_frozen_instructions.pop(sid)` 原始 prompt 文本 | FLOWING |
| `evolve_prompt_sections.py:joint branch` | `module = optimizer.compile(module, trainset, valset)` | dspy.GEPA 真实 mutation 流程(测试中 mock 返回 unchanged module 但生产代码会 mutate) | Yes — `get_evolved_sections()` (line 444) 之后读 Predict.signature.instructions 反映 GEPA mutation | FLOWING |
| metrics.json `joint_score` 字段 | `evolved_score` (line 543) | holdout 上 evolved module 输出 + metric scoring (line 539) | Yes — 真实 LLM-judge scoring(测试中 mock metric.side_effect 提供确定性序列) | FLOWING |
| `roundrobin_baseline_evolved_sections.json` | `ab_baseline_module.get_evolved_sections()` (line 630) | A/B baseline GEPA per-section compile output | Yes — fresh module from `PromptModule(original_sections)` 经 round-robin GEPA mutate | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| `--mode` / `joint` / `round-robin` 出现在 CLI --help | `python -c "from click.testing import CliRunner; ..."` | `--mode in help: True`, `joint in help: True`, `round-robin in help: True` | PASS |
| `EPSILON_PP` 模块级常量等于 0.01 | `python -c "from evolution.prompts.evolve_prompt_sections import EPSILON_PP; print(EPSILON_PP)"` | `0.01` | PASS |
| `JOINT_SENTINEL` 等于 `"__JOINT__"` | `python -c "from evolution.prompts.prompt_module import JOINT_SENTINEL; print(repr(JOINT_SENTINEL))"` | `'__JOINT__'` | PASS |
| `_resolve_effective_mode(None, joint)` 路由正确 | `python -c "...; print(_resolve_effective_mode(None, 'joint'))"` | `joint` | PASS |
| `_resolve_effective_mode(sid, joint)` D-RR-03 隐式 RR | `python -c "...; print(_resolve_effective_mode('memo', 'joint'))"` | `round-robin` | PASS |
| `set_joint_mode(True)` 暴露 N predictors,排除 selector | live spot-check | `named_predictors: ["section_predictors['s0']", "section_predictors['s1']", "section_predictors['s2']"]` | PASS |
| `set_joint_mode(True)` idempotent | 第二次调用 | `num section_predictors: 3`,`_active_section: __JOINT__` 不变 | PASS |
| 真实 hermes-agent prompt_builder 解出 13 section | `extract_prompt_sections(hermes_path)` | 13 sections (default_agent_identity, memory_guidance, session_search_guidance, skills_guidance, 9 platform_hints.*) | PASS — 与 Goal "实测 13 个" 一致 |
| 全套件零回归 | `.venv/bin/python -m pytest tests/ --tb=no -q` | `514 passed, 1 xfailed in 15.82s` | PASS |
| Phase 17 测试套(7 CLI + 21 module = 28 新核心) | `.venv/bin/python -m pytest tests/prompts/ -v` | `97 passed in 7.35s` | PASS |
| TestABBaseline 3 测试覆盖 SC3 机制 | `.venv/bin/python -m pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestABBaseline -v` | `3 passed in 5.79s` | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| PMPT-V2-01 | 17-01, 17-02, 17-03 | Joint section optimization (all 5 sections simultaneously) — REQUIREMENTS.md L79 | SATISFIED | 3 plans 全部 satisfy 此 requirement:Plan 17-01 提供 set_joint_mode 状态机(SC1);Plan 17-02 接入 GEPA component_selector="all"(SC2);Plan 17-03 提供 inline A/B baseline + 软门 + metrics schema 作为 SC3 的可证伪机制。28 个核心测试 PASS,真实 hermes-agent 解出 13 sections 与 Goal 一致(原 REQUIREMENTS.md 写 "5 sections" 是已过期的 v1 描述,生产代码用 N-dynamic 公式实际支持 13)。**注:**REQUIREMENTS.md L142 仍标 "Pending" — 需在 phase close 时更新为 Complete。 |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| evolve_prompt_sections.py | 20, 23 | `from rich.panel import Panel` 与 `get_hermes_agent_path` 未使用 (CR WR-04) | Info | 无功能影响;未来 refactor 时 cleanup |
| evolve_prompt_sections.py | 278-280 | round-robin 分支 `num_predictors = len(module._section_ids)` 死代码 (CR WR-03) | Info | 后续无引用 |
| evolve_prompt_sections.py | 529-531 | `for sid in baseline_module._section_ids: ...; break` 取首元素 (CR WR-01, IN-01) | Info | 风格非标准但功能正确 |
| evolve_prompt_sections.py | 594-613 vs 405-438 | A/B baseline GEPA 失败 NO MIPROv2 fallback,主 round-robin 有 (CR-01) | Warning (advisory) | 在 GEPA 不可用环境下 A/B 退化为未优化 baseline,理论上扭曲 soft-gate 对比;**当前 dspy 3.1.3 + 测试 mock 路径无触发场景,所有 TestABBaseline 测试 PASS**;CR-01 是 code review advisory 不阻塞 phase。 |
| evolve_prompt_sections.py | 42, 722 | `EPSILON_PP = 0.01` 命名含 "pp" 但值是分数空间;`metrics["epsilon_pp"] = 0.01` 单位不一致 (CR-02) | Warning (advisory) | 下游消费者若混用 `epsilon_pp` 与 `joint_vs_roundrobin_delta_pp`(后者是真百分点,值范围 0–100)做 `abs(delta) > epsilon` 比较会差 100×。**当前 soft-gate 逻辑正确**(line 645 用 score-space 比较),metrics.json 字段命名一致性是 advisory 改进。 |
| prompt_module.py | 1-7, 54, 62 | docstring 提及 `named_parameters()` 但实际重写的是 `named_predictors()` (CR WR-02) | Info | 文档漂移;不影响 GEPA 实际行为 |
| evolve_prompt_sections.py | 645 | soft-gate `<` 严格小于,边界情况浮点风险 (CR WR-06) | Info | IEEE 754 在 CPython 3.13 上确定性,跨平台 CI 隐患小 |
| prompt_module.py | 215-217 | round-robin active text 与 frozen 同 context 拼接,GEPA 反思信号路径模糊 (CR WR-07) | Info | 架构性建议,不影响 Phase 17 SC1-3 |

**关键说明**:CR-01 与 CR-02 在 17-REVIEW.md 中被标记为 BLOCKER,但 `gsd-code-review` 是 **non-blocking advisory**(reviewer 标注),且当前测试套与 spot-check 均未触达问题路径(GEPA always available in dspy 3.1.3;`epsilon_pp` 字段当前消费者只有测试断言固定值)。在 VERIFICATION 中归类为 Warning 并交由人类决定是否在 phase close 前修复或纳入未来 phase。

### Human Verification Required

#### 1. End-to-end joint optimization on real hermes-agent

**Test:** 用真实 LLM API 跑 `python -m evolution.prompts.evolve_prompt_sections --mode joint --iterations 1 --eval-source synthetic --hermes-repo $HERMES_AGENT_REPO`(预算约 ~$5-10),inspect `output/prompts/<latest>/metrics.json`。
**Expected:**
- `metrics["mode"] == "joint"`
- 5 新字段(`joint_score`, `roundrobin_baseline_score`, `epsilon_pp`, `joint_vs_roundrobin_delta_pp`, `ab_elapsed_seconds`)全部填充
- 实际 `joint_score >= roundrobin_baseline_score - 0.01`(满足 SC3),**或** 软门触发(yellow 警告 + delta_pp 写盘)— 两种结果都证明机制正确
- `roundrobin_baseline_evolved_sections.json` 与 `roundrobin_baseline_diff.txt` 落盘存在
**Why human:** 测试套件用 mock metric/GEPA 证明了机制就位,但 ROADMAP SC3 要求 "Joint optimization produces equal or better scores than round-robin on holdout" — 此对比依赖真实 LLM-judge 评分(`PromptBehavioralMetric` 用 `gpt-4.1-mini`)、真实 GEPA reflection(`gpt-4.1`)、真实 hermes-agent 13 sections。Mock 路径无法证伪 joint 是否真的优化得动。Plan 17-03 验证小节也将此标注为 "manual checkpoint"。

#### 2. Soft-gate warning visibility under normal terminal width

**Test:** 在一个正常 ≥120 字符宽度的终端上跑上述命令,观察终端输出是否清晰渲染 `[yellow]Joint score ... below round-robin baseline ... review before deploying[/yellow]` 或 `[green]Joint score ... ≥ ... within epsilon (1pp)[/green]`。
**Expected:** 黄色或绿色文本清晰可读,完整短语 "review before deploying" 不被换行拆开到难以辨认。
**Why human:** rich console 根据 stdin terminal width 自动换行,CliRunner 默认 80-char 触发 wrap,测试已用 `" ".join(result.output.split())` 防御;但部署环境的真实视觉效果须人类确认(WR-06 浮点边界、IN-04 类型注解风格混用同属 advisory,不在 human gate 中重复)。

### Gaps Summary

**无 BLOCKER 级别 gap。** Phase 17 三个 success criteria 的代码侧机制全部落地并由 514 测试(零回归)保护。1 个 must-have(SC3 真实分数对比)依赖真实 LLM 跑通才能闭环 — 属于 human gate 而非 BLOCKER,与 Plan 17-03 文档化的 "manual checkpoint" 一致。

Code review 报告(17-REVIEW.md)标出的 2 BLOCKER + 7 WARNING 是 advisory:
- **CR-01**(A/B 与主 RR 错误处理不对称):理论问题,当前 dspy 版本下未触发,所有 7 个 CLI 测试 PASS。可在未来 phase 通过抽取 `_compile_one_section` helper 改进。
- **CR-02**(epsilon_pp 单位/命名不一致):语义巧合下当前比较正确,改进涉及 metrics.json schema 兼容性(下游可能已固化 `0.01` 值),建议在 phase 18+ 与 dashboard 升级同时处理。

两项均不阻塞 Phase 17 实质交付。

### Phase 17 Re-Validation against Roadmap

| ROADMAP Success Criterion | Mechanism in Code | Code-Side Test Evidence | Real-LLM Validation |
|---|---|---|---|
| 1. PromptModule supports all-sections-active mode | `set_joint_mode` + `named_predictors` override | `test_set_joint_mode_exposes_all_predictors` + `test_named_predictors_in_joint_mode_excludes_selector` PASS;live spot-check 输出 13 production sections / 3 fixture sections | N/A — 不需要 LLM |
| 2. GEPA can mutate multiple sections in one pass | `dspy.GEPA(component_selector="all")` 单 compile 调用 | `test_joint_mode_default_calls_gepa_with_component_selector_all` 断言 `compile.call_count == 1` + kwargs 含 `component_selector="all"` | 须真实跑确认 dspy.GEPA 真的在多 Predict 上反思(机制在,行为待验证) |
| 3. Joint optimization produces equal or better scores than round-robin on holdout | inline A/B baseline + soft gate + metrics + 共享前缀落盘 | `test_joint_mode_runs_inline_ab_baseline` (joint=0.8 > rr=0.75) + `test_soft_gate_warns_but_does_not_block` (joint=0.50 < rr=0.60 触发警告) + `test_round_robin_mode_skips_ab_baseline_and_extra_files` 共 3 测试 PASS | **needs human run** — 实际 joint vs rr 数值对比 |

---

_Verified: 2026-05-15T09:00:00Z_
_Verifier: Claude Opus 4.7 (gsd-verifier)_
_Test suite at verification time: 514 passed + 1 xfailed (zero regression vs Phase 16 baseline)_
