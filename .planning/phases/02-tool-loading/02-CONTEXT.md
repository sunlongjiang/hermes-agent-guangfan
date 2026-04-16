# Phase 2: Tool Loading - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

从 hermes-agent 的 `tools/*.py` 文件中可靠提取工具描述（top-level + per-parameter），以及将进化后的描述写回文件，不破坏 schema 结构（param names, types, required fields 冻结）。

覆盖 TOOL-01（提取）和 TOOL-02（写回）两个需求。

</domain>

<decisions>
## Implementation Decisions

### 提取策略
- **D-01:** 使用正则表达式从 `tools/*.py` 文件提取描述，和 Phase 1 的 skill frontmatter 解析模式一致
- **D-02:** 同时提取 top-level description 和每个参数的 description，两者都是可进化目标
- **D-03:** 需要处理多种描述格式：内联 dict 字面量、字符串隐式拼接（括号内多行）、命名常量引用

### 写回方式
- **D-04:** 使用正则定位 + 字符串替换写回进化后的描述，和 Phase 1 的 `reassemble_skill()` 模式一致
- **D-05:** 保留原文件的格式——如果原始描述是多行字符串拼接，写回时也保持多行拼接格式；如果是单行则保持单行。目标是最小化 diff 噪音
- **D-06:** 写回只修改 description 文本，param names/types/required/enum 等 schema 结构完全不碰

### 中间数据结构
- **D-07:** 使用 `@dataclass` 定义 `ToolDescription` 和 `ToolParam`。`ToolDescription` 包含 name、file_path、description (evolvable)、params: list[ToolParam]。`ToolParam` 区分 frozen 字段（name, type, required, enum）和 evolvable 字段（description）
- **D-08:** 提供 `to_dict()` / `from_dict()` 序列化方法，和 Phase 1 的 `EvalExample`、`FitnessScore` 等保持一致

### Claude's Discretion
- 正则表达式的具体模式设计，包括处理字符串拼接、命名常量等边界情况的策略
- `ToolDescription` dataclass 的具体字段设计细节（例如是否包含 raw_source、line_number 等辅助字段）
- 文件发现逻辑（哪些 `*.py` 文件包含工具定义，哪些是辅助模块如 `registry.py`、`__init__.py`）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 参考实现
- `evolution/skills/skill_module.py` — Phase 1 的 loader 模式（`load_skill()`、`find_skill()`、`reassemble_skill()`），提取和写回的参考实现
- `evolution/core/config.py` — `EvolutionConfig` 和 `get_hermes_agent_path()` 用于定位 hermes-agent 仓库

### hermes-agent 工具定义格式
- `~/.hermes/hermes-agent/tools/memory_tool.py` — 典型工具定义示例：多行字符串拼接 description + 嵌套参数 description
- `~/.hermes/hermes-agent/tools/registry.py` — 工具注册机制，`registry.register()` 接受 schema dict
- `~/.hermes/hermes-agent/tools/web_tools.py` — 另一种工具定义模式的示例

### 项目规划文档
- `PLAN.md` §Phase 2 (line 369-438) — Phase 2 的原始详细规划，包含数据源、评估指标、约束条件
- `.planning/REQUIREMENTS.md` — TOOL-01 和 TOOL-02 的需求定义

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evolution/skills/skill_module.py` 中的 `load_skill()`/`reassemble_skill()` — 提取和写回的模式参考，但工具描述是 Python dict 不是 YAML frontmatter
- `evolution/core/config.py` 中的 `get_hermes_agent_path()` — 直接复用，用于定位 hermes-agent/tools/ 目录
- `evolution/tools/__init__.py` — 已存在的占位包，代码直接写入此包

### Established Patterns
- Dataclass + `to_dict()`/`from_dict()` 序列化（`EvalExample`, `FitnessScore`, `ConstraintResult`）
- 正则表达式解析文本制品（skill frontmatter parsing in `load_skill()`）
- Module-level `Console()` + Rich 输出（全项目统一）

### Integration Points
- `evolution/tools/` 包——Phase 2 代码的目标位置
- `datasets/tools/` 目录——提取结果的持久化位置（已有 `.gitkeep`）
- hermes-agent `tools/*.py` 文件（53 个文件，通过 `HERMES_AGENT_REPO` 环境变量定位）
- 工具定义格式：OpenAI function-calling schema dict (`{name, description, parameters: {type, properties, required}}`)

</code_context>

<specifics>
## Specific Ideas

- hermes-agent 有 53 个 `tools/*.py` 文件，其中约 40+ 个包含实际工具定义（排除 `__init__.py`、`registry.py`、`debug_helpers.py` 等辅助模块）
- 描述格式有三种主要模式：内联 dict、字符串隐式拼接 `("a " "b " "c")`、命名常量
- 参数描述嵌套在 `parameters.properties.<param_name>.description` 中
- 成功标准：round-trip test（提取 → 修改 → 写回 → 再提取 = 得到修改内容）

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-tool-loading*
*Context gathered: 2026-04-16*
