# Phase 3: Tool Module - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-16
**Phase:** 03-tool-module
**Areas discussed:** 模块粒度, forward() 语义, 参数暴露策略, Schema 冻结机制

---

## 模块粒度

| Option | Description | Selected |
|--------|-------------|----------|
| 单一模块 | 所有工具描述打包进一个 ToolModule，GEPA 一次优化所有描述。和 TOOL-03 完全对应。 | ✓ |
| 每工具一个模块 | 每个工具一个 SingleToolModule，评估时组合为 joint evaluation。灵活但复杂。 | |
| 按工具组分模块 | 按功能组（文件/浏览器/内存等）分模块。中间方案。 | |

**User's choice:** 单一模块 (推荐)
**Notes:** 和需求 TOOL-03 直接对应，最简单直接。

---

## forward() 语义

| Option | Description | Selected |
|--------|-------------|----------|
| 工具选择模拟 | forward(task, tools) 模拟给定任务选择正确工具。和 Phase 4 binary metric 对接。 | ✓ |
| 描述质量评估 | forward(tool_description) 输出质量评分。类似 Phase 1 但不直接测量选择效果。 | |
| 纯参数容器 | forward() 是简单 passthrough，评估逻辑完全外部定义。 | |

**User's choice:** 工具选择模拟 (推荐)
**Notes:** 直接和 Phase 4 的 binary tool selection metric 对接。

---

## 参数暴露策略

| Option | Description | Selected |
|--------|-------------|----------|
| 独立参数 | 每个工具描述是独立的可优化参数。参数数量 = 工具数量（~50）。 | ✓ |
| 单一拼接字符串 | 所有描述拼接成一个大字符串。简单但解析写回复杂。 | |
| 两层参数 | 工具描述 + 参数描述分两层。更细粒度但参数数 200+。 | |

**User's choice:** 独立参数 (推荐)
**Notes:** 给 GEPA 最大优化粒度，每个工具可独立进化。

---

## Schema 冻结机制

| Option | Description | Selected |
|--------|-------------|----------|
| 设计级隔离 | GEPA 只能看到 description 文本，frozen 字段根本不暴露为参数。 | ✓ |
| Runtime 校验 | 写回前对比进化前后 ToolDescription，检测 frozen 字段变化。 | |
| 双重保障 | 设计隔离 + runtime 校验。 | |

**User's choice:** 设计级隔离 (推荐)
**Notes:** 物理上无法触碰 frozen 字段，最安全。

## Claude's Discretion

- ToolModule 的 DSPy Signature 内部类设计
- 工具描述参数的命名约定
- 从 ToolDescription 列表构建模块参数的实现方式
- forward() 输出格式的具体 Signature 设计

## Deferred Ideas

None — discussion stayed within phase scope
