# Phase 2: Tool Loading - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-16
**Phase:** 02-tool-loading
**Areas discussed:** 提取策略, 写回方式, 中间数据结构

---

## 提取策略

| Option | Description | Selected |
|--------|-------------|----------|
| 正则提取 | 用正则表达式匹配 *_SCHEMA 变量 + description 字段。跟 Phase 1 的 skill frontmatter 解析模式一致，简单可靠，但需要处理字符串拼接等边界情况。 | ✓ |
| AST 解析 | 用 Python ast 模块解析源代码，精确定位 dict 字面量中的 description 字段。更精确但复杂度高，且字符串拼接的 AST 处理麻烦。 | |
| 运行时导入 | 导入模块、读取已注册的 schema dict，直接获取 description 值。最准确但需要 hermes-agent 运行时环境，违反"只读不依赖运行时"约束。 | |

**User's choice:** 正则提取
**Notes:** 和 Phase 1 模式保持一致

### 提取范围

| Option | Description | Selected |
|--------|-------------|----------|
| 两者都提取 | 提取 top-level description 和每个参数的 description，两者都是可进化目标。覆盖面最广，但参数描述的正则匹配更复杂。 | ✓ |
| 先只做 top-level | 先只做 top-level description，参数描述在后续阶段加。减少复杂度，但 Phase 3 (Tool Module) 时需要两者都准备好。 | |

**User's choice:** 两者都提取
**Notes:** None

---

## 写回方式

| Option | Description | Selected |
|--------|-------------|----------|
| 正则定位 + 替换 | 用正则定位 description 字段的位置（行号 + 缩进），然后用字符串替换。和 Phase 1 的 reassemble_skill() 模式一致。简单直接，但字符串拼接和多行情况需要特别处理。 | ✓ |
| AST 修改 + unparse | AST 解析源代码，修改 description 节点，用 ast.unparse 重新生成。精确但 ast.unparse 会改变格式和缩进，导致大量 diff 噪音。 | |
| 字节偏移替换 | 提取时记录原始 description 字符串的确切位置（字节偏移），写回时直接替换该字节范围。最精确，但实现复杂度高。 | |

**User's choice:** 正则定位 + 替换
**Notes:** None

### 写回格式

| Option | Description | Selected |
|--------|-------------|----------|
| 保留原格式 | 保持原始文件的格式——如果原来是多行拼接，写回时也用多行拼接。复杂一些但 diff 更干净。 | ✓ |
| 统一单行 | 新描述统一写成单行字符串，不管原来是单行还是多行拼接。更简单但会改变代码风格。 | |

**User's choice:** 保留原格式
**Notes:** None

---

## 中间数据结构

| Option | Description | Selected |
|--------|-------------|----------|
| Dataclass | 用 @dataclass 定义 ToolDescription 和 ToolParam。ToolDescription 包含 name、file_path、description (evolvable)、params: list[ToolParam]。ToolParam 区分 frozen (name, type, required, enum) 和 evolvable (description)。更清晰，但比 Phase 1 的 dict 更重。 | ✓ |
| 普通 dict | 和 Phase 1 一样用 dict。结构如 {name, path, raw, description, params: [{name, type, description, ...}]}。简单，和现有模式一致，但没有类型安全。 | |
| Claude 决定 | 由 Claude 决定，根据 Phase 1 模式和实际复杂度选择。 | |

**User's choice:** Dataclass
**Notes:** None

### 序列化

| Option | Description | Selected |
|--------|-------------|----------|
| to_dict/from_dict | 和 Phase 1 一样用 to_dict()/from_dict() 方法，保持一致性。输出到 datasets/tools/ 目录。 | ✓ |
| dataclasses.asdict | 用 dataclasses.asdict() 自动序列化，不写自定义方法。更简单但控制力更弱。 | |

**User's choice:** to_dict/from_dict
**Notes:** 和 Phase 1 的 EvalExample、FitnessScore 等保持一致

---

## Claude's Discretion

- 正则表达式的具体模式设计
- ToolDescription dataclass 的辅助字段设计
- 文件发现逻辑（哪些文件包含工具定义）

## Deferred Ideas

None — discussion stayed within phase scope
