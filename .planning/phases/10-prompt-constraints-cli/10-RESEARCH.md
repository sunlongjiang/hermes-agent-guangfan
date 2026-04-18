# Phase 10: Prompt Constraints & CLI - Research

**Researched:** 2026-04-16
**Domain:** 约束验证 (growth + role preservation) + CLI 编排 (Python/DSPy/Click)
**Confidence:** HIGH

## Summary

Phase 10 将 Phase 7-9 的所有提示词进化组件串联为端到端可运行的管道，与 Phase 5 (Tool Constraints & CLI) 完全对称。主要工作分三块：(1) 新建 `PromptRoleChecker` 做 LLM-based 角色保持验证（对称 `ToolFactualChecker`），(2) 在 CLI 中正确调用已有的 `ConstraintValidator._check_growth()` 和 `_check_non_empty()` 实施增长约束，(3) 构建 `evolve_prompt_sections.py` CLI 入口点。

所有组件均有完整的参考实现：`evolve_tool_descriptions.py` 提供了 CLI + evolve() 编排流程模板（409 行）；`ToolFactualChecker` 提供了 DSPy Signature + ChainOfThought + bool 解析的模式；`ConstraintValidator._check_growth()` 已内建 `max_prompt_growth=0.2` 的增长限制。Phase 10 的唯一新创建类是 `PromptRoleChecker`。CLI 编排逻辑需要适配提示词管道的特殊性：per-section 优化（而非 joint）、section 选择、frozen context 传递。

**Primary recommendation:** 严格照搬 `evolve_tool_descriptions.py` 的编排结构，新建 `prompt_constraints.py`（`PromptRoleChecker`）和 `evolve_prompt_sections.py`（CLI），复用现有所有基础设施。CLI 额外增加 `--section` 参数用于指定优化哪个段落。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D1:** 增长约束 -- 复用 `ConstraintValidator._check_growth()` 方法，传入 `artifact_type="prompt_section"`。`max_prompt_growth` 已在 `EvolutionConfig` 中定义为 `0.2`（20%）。
- **D2:** 角色保持检查 -- 创建 `PromptRoleChecker` 类，用 DSPy ChainOfThought 对比原始段落和进化后段落，判断功能角色是否保持。与 Phase 5 的 `ToolFactualChecker` 对称。
- **D3:** CLI 入口 -- 创建 `evolve_prompt_sections.py`，Click CLI，选项包含 `--section`、`--iterations`、`--hermes-repo`、`--dry-run`。编排流程：extract -> module -> dataset -> GEPA -> constraints -> evaluate -> save。
- **D4:** 约束门禁顺序 -- growth + role 在 GEPA 之后、holdout 之前执行。

### Claude's Discretion
- `PromptRoleChecker` 内部的 DSPy Signature 设计（字段名、判断 prompt 措辞）
- diff 输出格式（section text before/after）
- 输出目录子结构（时间戳组织方式）
- `--section` 参数的默认行为（优化所有 vs 必须指定）
- per-section 循环优化的具体流程（round-robin vs 单 section 聚焦）

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PMPT-08 | Growth constraint enforced -- evolved section must not exceed baseline by >20% | 直接复用 `ConstraintValidator._check_growth()`，`max_prompt_growth=0.2` 已在 `EvolutionConfig` 中定义。`_check_non_empty()` 同样适用。 |
| PMPT-09 | Section role preservation -- LLM-based check that evolved text maintains its functional role | 新建 `PromptRoleChecker` 类，使用 DSPy ChainOfThought 对比原始 vs 进化段落，判断功能角色是否保持，返回 `ConstraintResult` |
| PMPT-10 | CLI entry point `python -m evolution.prompts.evolve_prompt_section` with --section, --iterations, --hermes-repo, --dry-run options | 照搬 `evolve_tool_descriptions.py` 的 Click CLI 模式，适配 per-section 优化流程 |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | >=3.0.0 | ChainOfThought for PromptRoleChecker + GEPA 优化 | 项目核心框架，Phase 1-9 全部使用 [VERIFIED: pyproject.toml] |
| click | >=8.0 | CLI 参数解析 | 项目标准 CLI 框架 [VERIFIED: evolve_tool_descriptions.py] |
| rich | >=13.0 | Console/Table/Panel 终端输出 | 项目标准输出库 [VERIFIED: evolve_tool_descriptions.py] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| evolution.core.constraints | - | ConstraintValidator._check_growth(), _check_non_empty(), ConstraintResult | 增长约束和非空检查 |
| evolution.core.config | - | EvolutionConfig (max_prompt_growth=0.2) | 配置参数 |
| evolution.prompts.prompt_loader | - | extract_prompt_sections(), write_back_section(), PromptSection | 提取和写回段落 |
| evolution.prompts.prompt_module | - | PromptModule, set_active_section(), get_evolved_sections() | DSPy 可优化模块 |
| evolution.prompts.prompt_dataset | - | PromptDatasetBuilder, PromptBehavioralDataset | 数据集生成/加载 |
| evolution.prompts.prompt_metric | - | PromptBehavioralMetric | GEPA 评估指标 |

**Installation:** 无新依赖。所有依赖已在 pyproject.toml 中声明。

## Architecture Patterns

### File Structure
```
evolution/prompts/
├── __init__.py              # 已存在 -- 需更新 __all__
├── prompt_loader.py         # Phase 7 -- extract/write-back
├── prompt_module.py         # Phase 8 -- DSPy Module
├── prompt_dataset.py        # Phase 9 -- dataset builder
├── prompt_metric.py         # Phase 9 -- behavioral metric
├── prompt_constraints.py    # Phase 10 NEW -- PromptRoleChecker
└── evolve_prompt_sections.py # Phase 10 NEW -- CLI + evolve()
```

### Pattern 1: PromptRoleChecker (对称 ToolFactualChecker)

**What:** LLM-based 角色保持检查器，判断进化后的段落是否仍执行其原始功能角色。
**When to use:** GEPA 优化后、holdout 评估前的约束门禁。
**Template from:** `evolution/tools/tool_constraints.py` [VERIFIED: codebase]

```python
# Source: 对称 ToolFactualChecker (tool_constraints.py lines 32-112)
class PromptRoleChecker:
    """Checks evolved prompt sections for role preservation."""

    class RoleCheckSignature(dspy.Signature):
        """Compare original and evolved prompt sections to verify role preservation.

        Determine whether the evolved section still fulfills the same functional
        role as the original. Rewording, improving clarity, or restructuring is
        acceptable. Changing the fundamental purpose (e.g., memory guidance
        becoming identity guidance) is a role violation.
        """
        section_id: str = dspy.InputField(desc="Section identifier")
        original_text: str = dspy.InputField(desc="Original section text")
        evolved_text: str = dspy.InputField(desc="Evolved section text to check")
        role_preserved: bool = dspy.OutputField(
            desc="True if evolved text maintains the same functional role as original",
        )
        explanation: str = dspy.OutputField(desc="Explanation of role assessment")

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.checker = dspy.ChainOfThought(self.RoleCheckSignature)

    def check(self, section_id, original_text, evolved_text) -> ConstraintResult:
        ...  # LM call + _parse_bool + ConstraintResult

    def check_all(self, original_sections, evolved_sections) -> list[ConstraintResult]:
        ...  # Match by section_id, call check() for each
```

**Key differences from ToolFactualChecker:**
- 输出字段名为 `role_preserved`（True = pass），而非 `has_false_claims`（True = fail）。注意布尔值方向相反。[ASSUMED]
- Signature 需描述"功能角色保持"而非"虚假声明检测" [ASSUMED]
- `check_all` 通过 `section_id` 匹配（而非 `name`）[VERIFIED: PromptSection.section_id]

### Pattern 2: CLI 编排 (对称 evolve_tool_descriptions.py)

**What:** 端到端优化管道的 Click CLI 入口。
**Template from:** `evolution/tools/evolve_tool_descriptions.py` [VERIFIED: codebase]

CLI 编排步骤（照搬 evolve_tool_descriptions.py，适配提示词管道）：

```
1. Configuration    -- EvolutionConfig + hermes_repo
2. Extract          -- extract_prompt_sections(prompt_builder_path)
3. Dry-run gate     -- 验证设置，展示段落列表
4. Module           -- PromptModule(sections) + set_active_section()
5. Dataset          -- PromptDatasetBuilder.generate() or load()
6. GEPA optimize    -- per-section: set_active -> GEPA.compile -> next
7. Extract evolved  -- get_evolved_sections()
8. Constraints      -- growth + non_empty + role preservation
9. Holdout eval     -- baseline vs evolved behavioral scoring
10. Report + save   -- metrics, diff, evolved text
```

**与 Tool CLI 的关键差异：**
- **新增 `--section` 参数：** 指定优化哪个段落（如 `--section memory_guidance`），或不指定则优化所有 [ASSUMED]
- **Per-section 循环：** Tool CLI 一次优化所有工具描述（joint）；Prompt CLI 需要为每个 section 单独调用 `set_active_section()` + GEPA [VERIFIED: PromptModule.set_active_section()]
- **prompt_builder.py 路径：** 需要从 hermes_repo 构造 `prompt_builder_path`（非 tools/*.py） [VERIFIED: prompt_loader.py]
- **Dataset 需要 section_texts 参数：** `to_dspy_examples()` 接受可选的 `section_texts` dict [VERIFIED: prompt_dataset.py line 128]

### Pattern 3: _parse_bool 复用

**What:** 从 LLM 输出解析布尔值的保守策略。
**Reuse:** 直接从 `tool_constraints.py` 复制 `_parse_bool()` 函数到 `prompt_constraints.py`。[VERIFIED: tool_constraints.py lines 15-29]

注意：`PromptRoleChecker` 的布尔值方向是 `role_preserved=True` 表示通过，与 `ToolFactualChecker` 的 `has_false_claims=True` 表示不通过相反。

### Anti-Patterns to Avoid
- **不要修改 ConstraintValidator 类本身：** D1 明确说"复用"，不是"扩展"。在 CLI 中直接调用 `_check_growth()` 和 `_check_non_empty()`，不添加新的 artifact_type 分支。[VERIFIED: evolve_tool_descriptions.py 的用法 lines 214-244]
- **不要在 prompt_constraints.py 中放增长检查：** 增长检查已在 core/constraints.py 中，prompt_constraints.py 只放 PromptRoleChecker。保持单一职责。[VERIFIED: Phase 5 模式]
- **不要联合优化所有段落：** PromptModule 设计为 per-section 优化。联合优化是 PMPT-V2-01 的 v2 需求。[VERIFIED: REQUIREMENTS.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 增长百分比计算 | 自定义增长检查函数 | `ConstraintValidator._check_growth()` | 已处理 division-by-zero (max(1, len(baseline)))，经过测试 [VERIFIED: constraints.py line 120] |
| 非空检查 | 自定义空值检查 | `ConstraintValidator._check_non_empty()` | 标准模式，strip() 后判断 [VERIFIED: constraints.py line 136] |
| LLM 布尔解析 | 自定义解析 | 复制 `_parse_bool()` 函数 | 保守策略：只有明确的 truthy 值才返回 True [VERIFIED: tool_constraints.py line 15] |
| CLI 参数解析 | argparse | Click decorators | 项目标准，所有 CLI 都用 Click [VERIFIED: codebase convention] |
| diff 生成 | 自定义文本对比 | `difflib.unified_diff` | 标准库，evolve_tool_descriptions.py 已使用 [VERIFIED: evolve_tool_descriptions.py line 56] |

## Common Pitfalls

### Pitfall 1: 布尔值方向错误
**What goes wrong:** `PromptRoleChecker` 的 `role_preserved=True` 意味着通过，但如果照搬 `ToolFactualChecker` 的逻辑不修改判断方向，会把"保持角色"判为失败。
**Why it happens:** `ToolFactualChecker` 是 `has_false_claims=True` -> fail（负向判断），`PromptRoleChecker` 是 `role_preserved=True` -> pass（正向判断）。
**How to avoid:** 在 `check()` 方法中，`_parse_bool(result.role_preserved)` 返回 True 时构造 `passed=True` 的 ConstraintResult。
**Warning signs:** 所有 section 都被判为 fail 或所有都 pass。

### Pitfall 2: ConstraintValidator._check_growth() 的 artifact_type 不影响增长阈值
**What goes wrong:** 误以为传入 `artifact_type="prompt_section"` 会使用不同的增长阈值。
**Why it happens:** `_check_growth()` 使用 `self.config.max_prompt_growth` 作为固定阈值，不根据 artifact_type 区分。artifact_type 参数实际上只被 `_check_size()` 用于选择 size limit。
**How to avoid:** 理解 `_check_growth()` 的 artifact_type 参数在当前实现中未使用（但传入无害）。增长限制统一为 20%。
**Warning signs:** 无。

### Pitfall 3: Per-section 优化时 dataset 过滤
**What goes wrong:** 使用全部 section 的数据集来优化单个 section，导致不相关的训练数据干扰优化。
**Why it happens:** `PromptBehavioralDataset` 包含所有 section 的 scenario。GEPA 需要仅与当前 active section 相关的 examples。
**How to avoid:** 在 GEPA 优化前，按 `section_id` 过滤 dataset：

```python
# 从 PromptBehavioralExample 中提取 section_id 并过滤
section_train = [ex for ex in dataset.train if ex.section_id == active_section_id]
```

然后将过滤后的 examples 传给 `to_dspy_examples()`。或者，由于 `to_dspy_examples()` 不保留 section_id，需要在调用前手动过滤。
**Warning signs:** 优化结果与 section 功能无关，evaluation 分数不提升。

### Pitfall 4: prompt_builder.py 路径发现
**What goes wrong:** 硬编码 prompt_builder.py 路径，在不同 hermes-agent 版本中失效。
**Why it happens:** prompt_builder.py 在 hermes-agent 的特定子目录下。
**How to avoid:** 使用 `config.hermes_agent_path / "hermes_agent" / "prompt_builder.py"` 或通过 glob 发现。参考 `extract_prompt_sections()` 需要明确的 Path 参数。[VERIFIED: prompt_loader.py line 80]
**Warning signs:** FileNotFoundError 在不同环境下。

### Pitfall 5: 批量 write-back 时行号偏移
**What goes wrong:** 按文件顺序写回多个 section 时，第一个 write-back 改变了文件长度，后续 section 的 `line_range` 失效。
**Why it happens:** `write_back_section()` 修改文件内容后，后续 section 的行号可能偏移。
**How to avoid:** `write_back_section()` 文档已说明：从文件底部向上处理（highest line_range first）。[VERIFIED: prompt_loader.py line 155-156]
**Warning signs:** 写回后文件语法错误。

## Code Examples

### PromptRoleChecker.check() 返回 ConstraintResult
```python
# Source: 对称 ToolFactualChecker.check() (tool_constraints.py lines 71-112)
def check(self, section_id: str, original_text: str, evolved_text: str) -> ConstraintResult:
    lm = dspy.LM(self.config.eval_model)
    with dspy.context(lm=lm):
        result = self.checker(
            section_id=section_id,
            original_text=original_text,
            evolved_text=evolved_text,
        )

    role_kept = _parse_bool(result.role_preserved)
    explanation = str(result.explanation)

    if role_kept:
        return ConstraintResult(
            passed=True,
            constraint_name="role_preservation",
            message=f"Role preserved in '{section_id}'",
            details=explanation,
        )
    else:
        return ConstraintResult(
            passed=False,
            constraint_name="role_preservation",
            message=f"Role changed in '{section_id}'",
            details=explanation,
        )
```

### CLI 约束门禁段落（对称 evolve_tool_descriptions.py step 8）
```python
# Source: 对称 evolve_tool_descriptions.py lines 206-273
# ── 8. Constraint validation (GEPA -> constraints -> holdout) ────
original_map = {s.section_id: s for s in original_sections}
all_constraint_results = []
all_pass = True

validator = ConstraintValidator(config)
for evolved in evolved_sections:
    original = original_map.get(evolved.section_id)

    # Growth check
    if original:
        result = validator._check_growth(evolved.text, original.text, "prompt_section")
        all_constraint_results.append(result)
        if not result.passed:
            all_pass = False

    # Non-empty check
    result = validator._check_non_empty(evolved.text)
    all_constraint_results.append(result)
    if not result.passed:
        all_pass = False

# Role preservation check
role_checker = PromptRoleChecker(config)
role_results = role_checker.check_all(original_sections, evolved_sections)
all_constraint_results.extend(role_results)
for r in role_results:
    if not r.passed:
        all_pass = False
```

### Per-section GEPA 优化循环
```python
# Source: based on PromptModule.set_active_section() (prompt_module.py)
sections_to_optimize = [sid] if section else module._section_ids

for active_sid in sections_to_optimize:
    module.set_active_section(active_sid)

    # Filter dataset for this section
    section_train = [ex for ex in dataset.train if ex.section_id == active_sid]
    section_val = [ex for ex in dataset.val if ex.section_id == active_sid]

    section_texts = {s.section_id: s.text for s in original_sections}
    trainset = PromptBehavioralDataset(train=section_train).to_dspy_examples(
        "train", section_texts=section_texts
    )
    valset = PromptBehavioralDataset(val=section_val).to_dspy_examples(
        "val", section_texts=section_texts
    )

    optimizer = dspy.GEPA(metric=metric, max_steps=iterations)
    module = optimizer.compile(module, trainset=trainset, valset=valset)
```

### Click CLI 签名
```python
# Source: 对称 evolve_tool_descriptions.py lines 391-408
@click.command()
@click.option("--section", default=None, help="Section ID to optimize (default: all sections)")
@click.option("--iterations", default=10, help="Number of GEPA iterations per section")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "load"]),
              help="Source for evaluation dataset")
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo")
@click.option("--dry-run", is_flag=True, help="Validate setup without running optimization")
def main(section, iterations, eval_source, hermes_repo, dry_run):
    """Evolve hermes-agent prompt sections using DSPy + GEPA optimization."""
    evolve(section=section, iterations=iterations, ...)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 手动审查提示词变更 | LLM-based 角色保持自动验证 | Phase 10 (新增) | 自动化约束门禁 |
| 无增长限制 | 20% 增长上限（ConstraintValidator） | Phase 1 已有 | 防止提示词膨胀 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `role_preserved=True` 作为 PromptRoleChecker 正向判断（而非 ToolFactualChecker 的负向 `has_false_claims`） | Architecture Patterns | 布尔方向错误会导致所有 section 通过/失败反转 -- 但实现时容易验证 |
| A2 | `--section` 不指定时默认优化所有 section（round-robin） | Architecture Patterns | 影响 CLI 默认行为 -- discuss 阶段标记为 Claude's Discretion |
| A3 | prompt_builder.py 在 hermes_agent/prompt_builder.py 路径下 | Common Pitfalls | 路径错误导致 FileNotFoundError -- 但代码中已有 extract_prompt_sections() 接受明确路径 |

## Open Questions

1. **Per-section dataset 过滤机制**
   - What we know: `PromptBehavioralDataset` 包含所有 section 的 example，`PromptBehavioralExample` 有 `section_id` 字段
   - What's unclear: `to_dspy_examples()` 返回的 DSPy Example 不包含 section_id，需要在调用前过滤原始 list
   - Recommendation: 在 CLI 中优化前，先按 section_id 过滤 `dataset.train`/`dataset.val`，再构造临时 PromptBehavioralDataset 传给 `to_dspy_examples()`

2. **GEPA 重编译是否保持之前 section 的优化结果**
   - What we know: `optimizer.compile()` 返回优化后的 module 副本
   - What's unclear: 连续优化多个 section 时，第二次 compile 是否保持第一次的优化结果
   - Recommendation: 使用同一个 module 实例，每次 set_active_section() 切换后再 compile，依赖 PromptModule 内部的 frozen/active 切换逻辑保持已优化的 section

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/prompts/ -x -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PMPT-08 | Growth constraint rejects >20% growth | unit | `python -m pytest tests/prompts/test_prompt_constraints.py::TestGrowthConstraint -x` | Wave 0 |
| PMPT-09 | Role preservation LLM check pass/fail | unit | `python -m pytest tests/prompts/test_prompt_constraints.py::TestPromptRoleChecker -x` | Wave 0 |
| PMPT-10 | CLI runs end-to-end | unit | `python -m pytest tests/prompts/test_evolve_prompt_sections.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/prompts/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/prompts/test_prompt_constraints.py` -- covers PMPT-08, PMPT-09
- [ ] `tests/prompts/test_evolve_prompt_sections.py` -- covers PMPT-10

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | -- |
| V3 Session Management | no | -- |
| V4 Access Control | no | -- |
| V5 Input Validation | yes | ConstraintValidator size/growth limits; _parse_bool conservative parsing |
| V6 Cryptography | no | -- |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM 输出注入（role check bypass） | Tampering | _parse_bool 保守策略：只有明确 truthy 值才返回 True |
| 进化文本无限增长 | Denial of Service | _check_growth() 强制 20% 上限 |
| 空文本替换 | Tampering | _check_non_empty() 门禁 |

## Sources

### Primary (HIGH confidence)
- `evolution/tools/tool_constraints.py` -- ToolFactualChecker 完整实现参考
- `evolution/tools/evolve_tool_descriptions.py` -- CLI 编排模板（409 行）
- `evolution/core/constraints.py` -- ConstraintValidator, ConstraintResult, _check_growth(), _check_non_empty()
- `evolution/prompts/prompt_module.py` -- PromptModule.set_active_section(), get_evolved_sections()
- `evolution/prompts/prompt_loader.py` -- extract_prompt_sections(), write_back_section(), PromptSection
- `evolution/prompts/prompt_dataset.py` -- PromptDatasetBuilder, PromptBehavioralDataset.to_dspy_examples()
- `evolution/prompts/prompt_metric.py` -- PromptBehavioralMetric
- `evolution/core/config.py` -- EvolutionConfig.max_prompt_growth = 0.2
- `tests/tools/test_tool_constraints.py` -- 测试模式参考（mock DSPy 调用）

### Secondary (MEDIUM confidence)
- None

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- 全部为已有依赖，无新引入
- Architecture: HIGH -- 完全对称 Phase 5，所有参考实现已验证
- Pitfalls: HIGH -- 基于代码分析识别，非假设性风险

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable domain, no external dependencies)
