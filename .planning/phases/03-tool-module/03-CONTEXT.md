# Phase 3: Tool Module - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

将所有工具描述包装为一个 GEPA 可优化的 DSPy 模块（`ToolModule`），其中只有 description 文本可进化，schema 结构（param names, types, required, enum）完全冻结。

覆盖 TOOL-03（单一 DSPy 可优化模块）和 TOOL-04（schema 冻结，只有描述文本进化）两个需求。

</domain>

<decisions>
## Implementation Decisions

### 模块粒度
- **D-01:** 所有工具描述打包进一个 `ToolModule(dspy.Module)` 类，GEPA 一次优化所有描述。和需求 TOOL-03「单一 DSPy 可优化模块」直接对应。不做 per-tool 或 per-group 拆分。

### forward() 语义
- **D-02:** `forward(task_input, tool_descriptions)` 模拟工具选择场景——给定任务描述和所有可用工具描述列表，输出选择的工具名称。这直接和 Phase 4 的 binary tool selection metric 对接。
- **D-03:** 和 Phase 1 的 `SkillModule` 模式类似，使用 `dspy.ChainOfThought` 做推理，但 Signature 是工具选择专用的（不是通用任务完成）。

### 参数暴露策略
- **D-04:** 每个工具的 top-level description 是一个独立的可优化参数（如 `self.tool_memory_desc = "..."`），GEPA 可以细粒度地独立修改每个工具的描述文本。参数数量 = 工具数量（~50 个）。
- **D-05:** 参数暴露只包含 description 文本，不包含 param descriptions（per-parameter 描述优化推迟到 v2, TOOL-V2-02）。

### Schema 冻结机制
- **D-06:** 设计级隔离——GEPA 只能看到和修改 description 文本参数。param names, types, required, enum 等 frozen 字段根本不作为参数暴露，优化器物理上无法触碰。写回时使用 `ToolDescription` 的 frozen 字段原值重建 schema，保证结构不变。

### Claude's Discretion
- `ToolModule` 的 DSPy Signature 内部类设计（字段名、desc 文本）
- 工具描述参数的命名约定（如 `tool_{name}_desc` 或其他方式）
- 从 `ToolDescription` 列表构建模块参数的具体实现方式
- forward() 输出格式的具体 Signature 设计

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 参考实现
- `evolution/skills/skill_module.py` — Phase 1 的 DSPy 模块模式（`SkillModule(dspy.Module)`、inner `TaskWithSkill(dspy.Signature)`、`ChainOfThought` predictor）。Phase 3 的 `ToolModule` 应遵循相同的模块结构模式。
- `evolution/skills/evolve_skill.py` lines 130-178 — GEPA/MIPROv2 优化循环，展示如何将 DSPy 模块接入优化器（`optimizer.compile(module, trainset, valset)`）。

### Phase 2 产出
- `evolution/tools/tool_loader.py` — `ToolDescription`、`ToolParam`、`DescFormat` 数据类，`extract_tool_descriptions()`、`discover_tool_files()`、`write_back_description()` 函数。Phase 3 的 `ToolModule` 从这里获取工具数据。

### DSPy 框架
- DSPy `dspy.Module` 文档 — 模块参数定义和优化接口

### 项目规划文档
- `.planning/REQUIREMENTS.md` — TOOL-03 和 TOOL-04 的需求定义
- `.planning/ROADMAP.md` §Phase 3 — 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evolution/tools/tool_loader.py` — Phase 2 实现的完整提取/写回管道，`ToolModule` 直接调用 `discover_tool_files()` + `extract_tool_descriptions()` 获取所有工具数据
- `evolution/skills/skill_module.py` — `SkillModule` 类是 DSPy 模块包装的参考模板，`ToolModule` 应遵循相同结构
- `evolution/core/config.py` — `get_hermes_agent_path()` 定位 hermes-agent 仓库

### Established Patterns
- DSPy Module 结构: inner Signature class + ChainOfThought predictor + forward() method
- Dataclass + `to_dict()`/`from_dict()` 序列化（`ToolDescription`, `ToolParam`, `EvalExample`, `FitnessScore`）
- Module-level `Console()` + Rich 输出

### Integration Points
- `evolution/tools/` 包——`ToolModule` 的目标位置（`evolution/tools/tool_module.py`）
- `evolution/tools/tool_loader.py` — 提供输入数据（`ToolDescription` 列表）
- Phase 4 的 metric 函数将接收 `ToolModule` 的输出（工具名称）进行二值评分

</code_context>

<specifics>
## Specific Ideas

- `ToolModule.__init__` 接收 `list[ToolDescription]`，为每个工具创建一个名为 `tool_{name}_desc` 的字符串参数
- `forward()` 将所有当前的 description 文本组装为工具列表，传给 ChainOfThought 做工具选择
- 提供 `get_evolved_descriptions() -> list[ToolDescription]` 方法，返回带有进化后 description 的 ToolDescription 列表，供 `write_back_description()` 写回
- 参考 Phase 1 的 `SkillModule` 结构，保持模块设计一致性

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-tool-module*
*Context gathered: 2026-04-16*
