# Phase 4: Tool Dataset & Evaluation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-16
**Phase:** 04-tool-dataset-evaluation
**Areas discussed:** 数据集格式与生成, 二值指标设计, 跨工具回归检测, 难度分布与 confuser, 工具覆盖率

---

## 数据集格式与生成

### 数据类设计

| Option | Description | Selected |
|--------|-------------|----------|
| 新建专用数据类（推荐） | 新建 ToolSelectionExample(task, correct_tool, correct_params, difficulty, confuser_tools)，与 EvalExample 并存 | ✓ |
| 扩展现有 EvalExample | 在 EvalExample 加 correct_tool / correct_params / confuser_tools 字段（Optional） | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 新建专用数据类
**Notes:** 清晰分离工具选择和技能评估的数据格式

### Confuser 生成策略

| Option | Description | Selected |
|--------|-------------|----------|
| 工具相似度分析驱动（推荐） | 先分析工具描述找功能重叠的工具对，再针对性生成任务 | ✓ |
| 纯 LLM 一次性生成 | LLM 读取所有工具描述，一次性生成包含 confuser 的数据集 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 工具相似度分析驱动
**Notes:** 更精准的 confuser 生成，需要工具相似度分析步骤

### Builder 复用方式

| Option | Description | Selected |
|--------|-------------|----------|
| 新建专用 builder（推荐） | 新建 ToolDatasetBuilder，参考 SyntheticDatasetBuilder 模式 | ✓ |
| 扩展现有 builder | 在 SyntheticDatasetBuilder 加方法支持工具选择场景 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 新建专用 builder
**Notes:** 无

### 数据集来源

| Option | Description | Selected |
|--------|-------------|----------|
| 纯合成生成（推荐） | 只用 LLM 合成生成，工具选择场景结构化程度高 | ✓ |
| 合成 + SessionDB | 同时支持合成和真实工具选择数据 | |
| 合成 + golden set | 支持手动编辑的 golden set 作为补充 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 纯合成生成
**Notes:** 无

### 保存格式

| Option | Description | Selected |
|--------|-------------|----------|
| 标准 JSONL 分割（推荐） | train.jsonl / val.jsonl / holdout.jsonl，50/25/25 | ✓ |
| 单文件 + split 字段 | 单文件保存，内部带 split 标记字段 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 标准 JSONL 分割
**Notes:** 无

---

## 二值指标设计

### 匹配策略

| Option | Description | Selected |
|--------|-------------|----------|
| 精确匹配（推荐） | tool name 大小写不敏感 + strip 后精确比较 | ✓ |
| 模糊匹配 | 允许工具名称的常见变体 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 精确匹配
**Notes:** 工具名称在 hermes-agent 中是唯一的

### Params 评分

| Option | Description | Selected |
|--------|-------------|----------|
| 不纳入（推荐） | Phase 4 只关注工具选择正确率 | ✓ |
| 作为辅助指标 | 选对工具后额外检查参数匹配 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 不纳入
**Notes:** correct_params 仍记录在数据集中供未来使用

### GEPA 对接

| Option | Description | Selected |
|--------|-------------|----------|
| 独立 metric 函数（推荐） | tool_selection_metric() 返回 0 或 1，直接作为 GEPA compile() 的 metric | ✓ |
| 复用 LLMJudge | 用 LLM 评判工具选择是否正确 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 独立 metric 函数
**Notes:** 工具选择是确定性的，不需要 LLM 评判

---

## 跨工具回归检测

### Baseline 计算

| Option | Description | Selected |
|--------|-------------|----------|
| 优化前全量评估（推荐） | 用原始描述在整个数据集上跑一遍，记录 per-tool 正确选中率 | ✓ |
| 数据集分布作为 proxy | 用每个工具的样本数作为预期选中率 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 优化前全量评估
**Notes:** 无

### 阈值含义

| Option | Description | Selected |
|--------|-------------|----------|
| 绝对值 2 个百分点（推荐） | 80% → 78% 以下触发回归 | ✓ |
| 相对值 2% | 80% → 78.4% 以下触发回归 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 绝对值 2 个百分点
**Notes:** 无

### 检测时机

| Option | Description | Selected |
|--------|-------------|----------|
| 最终门禁（推荐） | 优化完成后在 holdout 集上做一次性回归检测 | ✓ |
| 每轮检测 | 每轮 GEPA 迭代后都检测 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 最终门禁
**Notes:** 和 Phase 1 的 constraint validation 模式一致

---

## 难度分布与 Confuser

### 难度分布

| Option | Description | Selected |
|--------|-------------|----------|
| 30/40/30 分布（推荐） | easy 30% / medium 40% / hard 30% | ✓ |
| 20/30/50 偏难 | 偏重 confuser，强调辨别能力 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 30/40/30 分布
**Notes:** 无

### Confuser 生成流程

| Option | Description | Selected |
|--------|-------------|----------|
| 工具对分析 + 针对生成（推荐） | 先找功能重叠工具对，再针对每对生成 5-10 个 confuser | ✓ |
| 随机 confuser 标注 | 对每个工具随机挑选 1-2 个相似工具作为 confuser | |

**User's choice:** 工具对分析 + 针对生成
**Notes:** 无

---

## 工具覆盖率

### 每工具最少任务数

| Option | Description | Selected |
|--------|-------------|----------|
| 每工具至少 3 条（推荐） | 1 easy + 1 medium + 1 hard/confuser | ✓ |
| 每工具至少 5 条 | 更稳健但数据集更大 | |
| 不强制覆盖 | 允许少用工具没有任务 | |
| 你来决定 | Claude 自行选择 | |

**User's choice:** 每工具至少 3 条
**Notes:** 50 工具 × 3 = 150 条起步，加上 confuser 达到 200-400 总量

---

## Claude's Discretion

- `ToolSelectionExample` 和 `ToolSelectionDataset` 的具体字段命名和辅助方法
- `ToolDatasetBuilder` 内部的 DSPy Signature 设计
- 工具相似度分析的具体实现
- 跨工具回归检测函数的具体接口设计

## Deferred Ideas

None — discussion stayed within phase scope
