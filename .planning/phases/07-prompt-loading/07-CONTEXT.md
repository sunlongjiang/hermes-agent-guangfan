# Phase 7: Prompt Loading — Context

## Domain Boundary

从 hermes-agent 的 `agent/prompt_builder.py` 中提取 5 个可进化的提示词段落，并支持格式保持的写回。

## Decisions

### D1: PLATFORM_HINTS 处理方式 → 按 key 展开

**选择**: 每个平台 key (whatsapp, telegram, discord, slack, signal 等) 展开为独立的 `PromptSection`。

**标识格式**: `platform_hints.{key}`，如 `platform_hints.whatsapp`。

**原因**: GEPA 可以针对每个平台的 hint 独立优化，粒度更细，优化空间更大。

**影响**: 加载器返回 4 个 str 段落 + N 个 platform hint 段落（N = dict key 数量）。

### D2: 提取/写回策略 → AST 解析

**选择**: 使用 `ast.parse()` 解析 `prompt_builder.py`，遍历 AST 找到 `ast.Assign` 节点匹配目标变量名。

**写回**: 基于 AST 提取的行号范围进行位置替换（与 tool_loader 的 write-back 模式一致）。

**关键点**:
- 4 个 str 常量是括号拼接字符串 `("a " "b ")`，AST 会自动合并为单一字符串
- `PLATFORM_HINTS` 是 `ast.Dict`，需要遍历 keys 提取每个 value
- 写回时需要将进化后的字符串重新格式化为括号拼接格式以保持代码风格

### D3: 段落元数据 → 四项全要

每个提取的 `PromptSection` 需携带:

| 字段 | 类型 | 用途 |
|------|------|------|
| `section_id` | `str` | 段落标识符，如 `default_agent_identity` 或 `platform_hints.whatsapp` |
| `char_count` | `int` | 字符数，用于 max_prompt_growth 20% 约束 |
| `line_range` | `tuple[int, int]` | 源文件行号范围 (start, end)，用于写回 |
| `source_path` | `Path` | 提取源文件路径 |

格式类型（str 括号拼接 vs dict value）隐含在 section_id 命名中（`platform_hints.*` = dict value）。

## Carrying Forward

- **从 Phase 2**: AST 解析 + 位置替换 write-back 模式已验证
- **从 Phase 2**: `DescFormat` enum 模式可参考（但提示词格式更统一，可能不需要 enum）
- **项目约束**: `max_prompt_growth = 0.2`（20%），`EvolutionConfig` 已定义

## Canonical Refs

- `agent/prompt_builder.py` in hermes-agent — 5 个目标变量的源文件
- `evolution/tools/tool_loader.py` — Phase 2 的 loader 模式参考
- `evolution/core/config.py` — `EvolutionConfig` 中的 `max_prompt_growth` 约束

## Deferred Ideas

None.
