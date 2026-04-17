# Phase 8: Prompt Module — Context

## Domain Boundary

将 Phase 7 提取的 PromptSection 包装为 DSPy 可优化模块，支持 per-section 优化时其余段落作为 frozen context 传递。

## Decisions

### D1: 模块结构 → 复用 ToolModule 模式

**选择**: 按 Phase 3 ToolModule 的模式，创建 `PromptModule(dspy.Module)`，每个 PromptSection 的 text 作为一个 `dspy.Predict` 实例的 Signature instructions。

### D2: Frozen context 传递 → 拼接为输入字段

**选择**: 优化某一段落时，其余段落的文本作为 frozen context 拼接传入 `dspy.InputField`，不暴露给优化器。

### D3: Round-robin 支持 → 方法级控制

**选择**: 提供 `set_active_section(section_id)` 方法控制当前优化的段落。GEPA 每轮迭代可切换 active section 实现 round-robin。

### D4: 进化结果提取 → get_evolved_sections()

**选择**: 类似 `ToolModule.get_evolved_descriptions()`，提供 `get_evolved_sections()` 返回 `list[PromptSection]`。

## Carrying Forward

- **Phase 3**: ToolModule 模式（Signature instructions 作为可优化参数，frozen schema 不暴露）
- **Phase 7**: PromptSection 数据类 + extract_prompt_sections() 已就绪

## Canonical Refs

- `evolution/tools/tool_module.py` — Phase 3 的 ToolModule 模式参考
- `evolution/prompts/prompt_loader.py` — Phase 7 的 PromptSection 数据类
- `evolution/core/config.py` — EvolutionConfig

## Deferred Ideas

None.
