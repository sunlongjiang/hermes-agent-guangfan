# Agent Evolve SDK — 设计文档

**日期**：2026-06-13
**状态**：设计已批准，待 writing-plans
**作者**：Brainstorming 会话产出（用户 + Claude）
**范围**：把 Hermes Agent Self-Evolution 从"hermes 专用"泛化为"任意 Python agent 可接入"的 SDK

---

## 1. 背景与目标

### 1.1 现状

`evolution/` 已实现完整能力（Phase 1-5）：技能进化、工具描述/参数/推理优化、提示词段进化、代码进化、基准回归、持续进化循环（GitHub Actions 周调度）。

**所有能力硬绑定到 hermes-agent**：
- `HERMES_AGENT_REPO` 环境变量
- `~/.hermes/sessions/*.json` 会话格式
- 专用的 `tool_loader` / `discover_tool_files` / `extract_tool_descriptions`

### 1.2 目标

让任意 Python agent 通过装饰器接入：

```python
@evolvable_agent(name="my-bot", schedule="weekly", min_samples=50)
class MyBot:
    @evolvable_prompt(id="system", text="You are...")
    def system_prompt(self): ...

    @evolvable_tool(id="search", max_chars=500)
    def search(self):
        """Search the web."""
```

接入后系统**自动**：采集执行轨迹 → 生成评估数据集 → GEPA 优化 → 候选过滤 → 运行时加载优化版本。可声明 `schedule` 让外部调度器（GH Actions / cron / launchd）周期触发优化。

### 1.3 非目标

- 不替代 DSPy / LangGraph / OpenAI Agents SDK —— SDK 是**追加层**
- 不做 UI / 可视化 dashboard（P2 之后再说）
- 不做多 agent 协同优化（每 agent 独立）
- 不做上线后自动回滚（监测到优化版本表现下降不会自动撤回）
- 不做 agent 间数据共享（共享 prompt 库等不在范围）
- 不做在线 A/B（生产流量分流）—— optimized 文件是全有全无切换
- 不做分布式多机注册（flock 是单机的）

---

## 2. 关键决策（来自 brainstorming）

| # | 决策 | 替代选项 |
|---|---|---|
| D1 | Python SDK 装饰器路线 | 配置文件 / SDK + 标准协议 |
| D2 | 两层装饰器（agent 外层 + prompt/tool 内层） | 单装饰器 |
| D3 | 三者组合判分：LLM-judge + 自动信号 + 可选 metric | 单一来源 |
| D4 | 装饰器自带调度参数 | 独立 CLI / 中心配置 |
| D5 | 生成 cron/launchd/GH Actions 配置，不内置 daemon | 进程内线程 / 独立 daemon |
| D6 | 三种文本来源：装饰器参数 > 函数返回值 > docstring | 单一来源 |
| D7 | 本地 JSONL 轨迹存储（接口预留扩展） | SQLite / OTel |
| D8 | 默认运行时加载优化版本 + 可选 patch/pr 模式 | 强制 PR / 强制改源码 |
| D9 | 独立 `evolution/sdk/` 子包 + `evolution/adapters/hermes.py` | 全量重构 / 拆姊妹项目 |

---

## 3. 架构总览

### 3.1 包结构

```
evolution/
├── core/                    # 不动 —— 通用底座
│   ├── fitness.py
│   ├── constraints.py
│   ├── dataset_builder.py
│   └── external_importers.py
│
├── sdk/                     # 新增：泛化层
│   ├── decorators.py        # @evolvable_agent / @evolvable_prompt / @evolvable_tool
│   ├── registry.py          # 进程内注册表 + ~/.evolution/registry.json 持久化
│   ├── runtime.py           # 拦截调用、解析文本、加载优化版本、baseline_hash 校验
│   ├── trace_sink.py        # TraceSink 接口 + LocalJsonlSink 实现
│   ├── signals.py           # 自动信号挖掘
│   ├── artifact.py          # EvolvableArtifact 数据类
│   ├── agent_module.py      # AgentModule (dspy.Module)
│   ├── optimizer.py         # GEPA 主循环 + 三道门
│   ├── ast_writer.py        # patch/pr 模式的源码 AST 重写
│   ├── scaffold.py          # 生成 cron / launchd / GH Actions
│   └── cli.py               # evolution-sdk CLI
│
├── adapters/                # 新增
│   └── hermes.py            # 现有 hermes 专用流水线包为 adapter
│
├── skills/, tools/, prompts/, code/   # 不变 —— 现有 CLI 不破坏
├── loop/, monitor/, benchmarks/       # 不变
```

### 3.2 心智模型

```
用户 agent.py                            ~/.evolution/
┌──────────────────────┐                ┌─────────────────────┐
│ @evolvable_agent     │  run()         │ traces/<agent>/     │
│ class MyBot:         │ ────traces───► │   YYYYMMDD.jsonl    │
│   @evolvable_prompt  │                │                     │
│   def sys_prompt...  │  load          │ optimized/<agent>/  │
│   @evolvable_tool    │ ◄──optimized── │   sys_prompt.json   │
│   def search...      │                │   search.json       │
└──────────────────────┘                │                     │
                                         │ registry.json       │
              evolution scaffold ◄──read─┤   (agent meta)      │
                       │                 └─────────────────────┘
                       ▼
              .github/workflows/
              evolve-my-bot.yml  ── cron / launchd 同理
                       │
                       ▼  (周期触发)
              python -m evolution.sdk.optimizer --agent my-bot
                       │
                       ├──► 读 traces → 自动信号挖掘
                       ├──► 生成/累积 EvalDataset
                       ├──► GEPA + LLM-judge 评分 + constraints 校验
                       └──► 写 ~/.evolution/optimized/<agent>/*.json
                            (可选：apply=patch/pr → 写源码或开 PR)
```

### 3.3 核心不变量

- **agent 进程只采集，不优化**。优化在独立进程（cron / GH Actions）里跑
- 现有 `evolution/{skills,tools,prompts,code}` CLI 和 `evolution-loop.yml` 完全不动
- hermes 走 `adapters/hermes.py`，自定义 agent 走 `sdk/`，两者共享 `core/`
- 每个 artifact 是独立事务边界（单 artifact 失败不影响其他）

---

## 4. 装饰器 API

### 4.1 外层：`@evolvable_agent`

```python
@evolvable_agent(
    name="research-bot",                    # 必填：agent 全局唯一标识
    version="0.1.0",                        # 进入 trace metadata
    metric=None,                            # (trace, output) -> float ∈ [0,1]
    judge_dimensions=("correctness", "conciseness"),  # LLM-judge 维度
    min_samples=50,                         # 累积多少 trace 后允许触发优化
    schedule="weekly",                      # weekly | daily | hourly | "cron:..." | None | "on_min_samples"
    auto_optimize=True,
    apply="runtime",                        # runtime | patch | pr
    sink=None,                              # TraceSink 实例；None = LocalJsonlSink
    max_cost_usd=5.0,                       # 单次优化预算上限
    entrypoint=None,                        # 显式指定拦截方法，默认自动发现
)
class ResearchBot: ...
```

**装饰器职责**：
1. 注册元数据到内存 `_REGISTRY`（必须）；仅在 `--discover` 或 `EVOLUTION_AUTO_REGISTER=1` 时落 `~/.evolution/registry.json`
2. 包裹 `__init__` + 入口方法（默认查找 `run` / `__call__` / `invoke` / `execute`）
3. 实例化时检查 `~/.evolution/optimized/<name>/`，校验 `baseline_hash` 通过则注入优化版本
4. 在类上挂 `_evolution_meta` 供 scaffold/optimizer 反射

**装饰器导入期不变量**：禁止网络 IO 和写文件 IO；**允许**一次性读 `~/.evolution/optimized/<name>/*.json`（有 fallback，文件不存在或损坏即静默回退基线）；性能预算 < 10ms per agent（含一次本地小文件读）。

### 4.2 内层：`@evolvable_prompt` / `@evolvable_tool`

```python
class ResearchBot:
    # 形态 1：装饰器参数传字符串（最直接）
    @evolvable_prompt(
        id="system",                        # agent 内唯一
        text="You are a research assistant...",
        max_chars=2000,
        max_growth=0.20,
    )
    def system_prompt(self) -> str:
        return self._evolved_text or "..."

    # 形态 2：函数返回值（无参数函数自动提取唯一字符串字面量）
    @evolvable_prompt(id="planner")
    def planner_prompt(self) -> str:
        return "Plan the steps..."

    # 形态 3：docstring（无 text、非纯返回字符串 → 用 docstring）
    @evolvable_tool(id="web_search", max_chars=500)
    def web_search(self, query: str):
        """Search the public web and return the top 5 result snippets."""
```

**文本解析优先级**（import 期一次性确定）：

```
text 参数  >  函数返回值（仅当无入参且函数体唯一字面量）  >  docstring
```

三者都没有 → 装饰器 **import 时 raise `ArtifactExtractionError`**。

**写回策略**（仅 `apply="patch"` / `"pr"`）：
- 形态 1：AST 重写装饰器调用里的 `text=...` 字符串字面量
- 形态 2：AST 重写函数体里**唯一**的字符串字面量；多个时拒绝并提示用户改用形态 1
- 形态 3：AST 重写 docstring

### 4.3 运行时加载

```python
# runtime.py 伪代码
def resolve_text(meta, agent_name):
    optimized = _load_optimized(agent_name, meta.id)
    if optimized and optimized.baseline_hash == meta.baseline_hash:
        return optimized.text                       # 注入优化版本
    return meta.baseline_text                       # 回退基线（包括 hash 不匹配场景）
```

`baseline_hash` 不匹配 → 静默回退到基线 + log info。这避免"用户改了源码但被旧 optimized 静默覆盖"的隐蔽 bug。

### 4.4 TraceRecord JSONL schema

落到 `~/.evolution/traces/<agent>/YYYYMMDD.jsonl`：

```json
{
  "ts": "2026-06-13T10:30:00Z",
  "agent": "research-bot",
  "agent_version": "0.1.0",
  "run_id": "uuid",
  "input": {"query": "..."},
  "output": "...",
  "artifacts": [
    {"id": "system", "kind": "prompt", "text_hash": "sha256:..."},
    {"id": "web_search", "kind": "tool", "text_hash": "sha256:..."}
  ],
  "tool_calls": [
    {"id": "web_search", "args": {...}, "result": "...", "error": null, "latency_ms": 420}
  ],
  "signals": {
    "errors": 0, "retries": 0, "user_correction": null
  },
  "scores": {
    "metric": null, "signal_score": 1.0, "judge_score": null
  }
}
```

`judge_score: null` 是有意的 —— LLM-judge **不在 agent 进程里跑**（成本+延迟），由后台 optimizer 批量补判。

---

## 5. 轨迹采集与数据集生成

### 5.1 三阶段流水线

```
agent 进程         optimizer 进程（后台/cron）        数据集
───────────       ──────────────────────────         ──────
TraceSink ──► ① 信号补判 ──► ② 抽样筛选 ──► ③ 合成扩充 ──► EvalDataset
```

### 5.2 阶段 ①：信号补判

**自动信号检测**（`sdk/signals.py`）：

| 信号 | 检测方式 | 含义 |
|---|---|---|
| `error_in_run` | `tool_calls[*].error != null` 或 output 含 traceback | 负 |
| `retry_pattern` | 同 tool_id 连续 ≥2 次相同参数调用 | 负 |
| `user_correction` | 下一条 trace 的 input 含 "不对" / "应该是" / "redo" / "actually" | 负 |
| `clean_completion` | 无 error、无 retry、output 非空 | 正 |
| `latency_outlier` | 总耗时 > p95 × 2 | 弱负 |

**signal_score**：

```
1.0
- 0.4 if error_in_run
- 0.3 if retry_pattern
- 0.5 if user_correction
- 0.1 if latency_outlier
clamp [0, 1]
```

**LLM-judge 补判**（复用 `core/fitness.py`）：
- 异步批量跑（不阻塞 agent）
- 跳过条件：`signal_score < 0.3`（已知是坏样本）或用户 metric 已给分
- 输出：每维度 0-1 分 + rationale，写回 `scores.judge_score`

**三者组合公式**：

```
default:                       0.5 × metric + 0.3 × judge + 0.2 × signal
无 metric 有 judge:            0.7 × judge + 0.3 × signal
无 metric 无 judge:            1.0 × signal
```

任一组件缺失自动重分配权重 —— 用户少配置一项不会跑不起来。

### 5.3 阶段 ②：抽样筛选

复用 `core/dataset_builder.py` 的 `EvalDataset`。规则：

| 规则 | 默认值 |
|---|---|
| 去重 | `text_hash(input) + text_hash(output)` 一致即去重 |
| 时间窗 | 最近 90 天 |
| 版本过滤 | `agent_version == current` |
| 双尾抽样 | 60% 高分（≥0.7）+ 30% 低分（≤0.3）+ 10% 中间 |
| 难度均衡 | 按 input 长度三分位采样 |
| 总量上限 | 200 条 |
| 切分 | 50% train / 25% val / 25% holdout |

### 5.4 阶段 ③：合成扩充

**触发条件**：`min_samples ≤ N < 2 × min_samples`

两条路径（复用 `core/dataset_builder.py` `SyntheticDatasetBuilder`）：
1. **种子改写**（首选）：从真实 traces 抽 10 条作为 few-shot 让 LLM 生成新 input
2. **零样本生成**（兜底）：从装饰器声明的 baseline + judge_dimensions 推 input 分布

**反污染**：合成样本打 `source: "synthetic"`，与真实混存；**holdout 切片只取真实样本**。

### 5.5 数据集持久化

```
~/.evolution/datasets/<agent>/
├── <YYYYMMDD_HHMMSS>/
│   ├── train.jsonl
│   ├── val.jsonl
│   ├── holdout.jsonl
│   ├── metrics.json
│   └── source_traces.txt     # 用了哪些 trace_id
└── latest/ → symlink
```

---

## 6. GEPA 优化编排

### 6.1 EvolvableArtifact 抽象

```python
@dataclass
class EvolvableArtifact:
    agent_name: str
    artifact_id: str
    kind: Literal["prompt", "tool"]
    baseline_text: str
    text_source: Literal["param", "return_value", "docstring"]
    source_file: Path
    decorator_lineno: int
    constraints: dict                   # max_chars / max_growth / forbidden_patterns
```

GEPA 每次只优化**一个 artifact**，多个 artifact 串行（不并行 —— 避免 trace 归因混淆）。

### 6.2 AgentModule（DSPy Module）

类比 `evolution/skills/skill_module.py` `SkillModule`：

```python
class AgentModule(dspy.Module):
    def __init__(self, artifact: EvolvableArtifact, judge_dimensions: tuple[str, ...]):
        super().__init__()
        self.artifact = artifact
        self.instructions = dspy.Parameter(artifact.baseline_text)
        self.predictor = dspy.ChainOfThought(self._build_signature())

    def forward(self, **kwargs):
        return self.predictor(instructions=self.instructions.value, **kwargs)
```

`kind="tool"` 比 `kind="prompt"` 多一步：dataset 包含真实 `tool_input → tool_output` 对。

### 6.3 主循环

```python
def optimize_artifact(artifact, dataset, config):
    module = AgentModule(artifact, config.judge_dimensions)
    metric = build_composite_metric(dataset, config)

    baseline_score = evaluate(module, dataset.val, metric)
    if config.budget.remaining() < config.min_run_cost:
        return BaselineKept("budget_exhausted")

    try:
        optimizer = dspy.GEPA(
            metric=metric,
            auto="light",
            max_metric_calls=config.max_metric_calls,
            reflection_lm=dspy.LM(config.optimizer_model),
            track_stats=True,
        )
        optimized = optimizer.compile(module, trainset=dataset.train.to_dspy_examples())
    except Exception as e:
        # 复用 evolve_skill.py 的 GEPA → MIPROv2 fallback
        log.warning(f"GEPA failed: {e}, falling back to MIPROv2")
        optimizer = dspy.MIPROv2(metric=metric, auto="light")
        optimized = optimizer.compile(module, trainset=dataset.train.to_dspy_examples())

    return optimized
```

### 6.4 候选过滤（三道门）

```
[门 1] 结构 + 大小 + 增长率
        - len ≤ max_chars
        - len ≤ baseline × (1 + max_growth)
        - 不含 SECRET_PATTERNS（复用 external_importers）
        - kind=tool 时不能丢失 {arg_name} 占位符
[门 2] holdout 评估
        - composite_score(holdout) ≥ baseline × (1 - regression_tolerance)
        - regression_tolerance 默认 0.02
[门 3] 回归冒烟（仅 prompt kind）
        - 抽 10 条历史"已知正确"的 traces 重放
        - LLM-judge 评分不得低于基线 0.05

任一门失败：保留基线 + 记录 rejection_reason
```

### 6.5 写回格式

```
~/.evolution/optimized/<agent>/<artifact_id>.json
```

```json
{
  "agent": "research-bot",
  "agent_version": "0.1.0",
  "artifact_id": "system",
  "kind": "prompt",
  "baseline_hash": "sha256:...",
  "optimized_text": "...",
  "optimization": {
    "run_id": "uuid",
    "ts": "2026-06-13T...",
    "optimizer": "GEPA",
    "judge_model": "openai/gpt-4.1",
    "baseline_score": 0.61,
    "optimized_score": 0.78,
    "holdout_score": 0.74,
    "dataset_size": 187,
    "cost_usd": 3.42
  }
}
```

### 6.6 Apply 模式

| 模式 | 行为 |
|---|---|
| `runtime`（默认） | 只写 optimized JSON，agent 下次启动自动加载 |
| `patch` | 同上 + 写 `output/<agent>/<ts>/changes.patch`（标准 unified diff） |
| `pr` | 同上 + 调用 `loop/pr_creator.py` 开 PR（需 git 仓库 + `GH_TOKEN`） |

### 6.7 预算控制

复用 `evolution/core/cost_tracker.py`：跑 GEPA 前估算开销 = `dataset_size × judge_calls_per_example × per_call_cost`；超预算降级 `auto="light"` + 减少 `max_metric_calls`；预算耗尽早退。

### 6.8 run_summary.json

```json
{
  "agent": "research-bot",
  "ts": "2026-06-13T08:57:00Z",
  "trigger": "schedule",
  "artifacts": [
    {
      "id": "system",
      "status": "improved",
      "baseline_score": 0.61,
      "optimized_score": 0.78,
      "rejection_reason": null,
      "cost_usd": 3.42
    },
    {
      "id": "web_search",
      "status": "rejected",
      "rejection_reason": "holdout_regression: 0.65 < 0.72 × 0.98",
      "cost_usd": 1.10
    }
  ],
  "dataset_path": "~/.evolution/datasets/research-bot/20260613_085700",
  "total_cost_usd": 4.52,
  "duration_seconds": 412
}
```

---

## 7. 调度与 scaffold

### 7.1 scaffold 的职责

`evolution scaffold` 是**一次性代码生成器**，不是常驻调度器。运行一次 → 输出原生平台调度配置 → 用户提交/安装 → 平台原生调度器负责触发。

### 7.2 CLI 入口

```bash
# 注册：import 模块 + 刷新 registry.json
evolution discover myapp/bots/research.py myapp/bots/writer.py
evolution discover --package myapp.bots

# 生成调度配置
evolution scaffold --backend gh-actions --output .github/workflows/
evolution scaffold --backend cron       --output ~/.evolution/crontab
evolution scaffold --backend launchd    --output ~/Library/LaunchAgents/

# 单 agent
evolution scaffold --backend gh-actions --agent research-bot

# 预览
evolution scaffold --backend gh-actions --dry-run

# Drift 检测（CI 用）
evolution scaffold --check

# 手动触发
evolution optimize --agent research-bot
```

### 7.3 注册表

```json
{
  "version": 1,
  "agents": {
    "research-bot": {
      "module": "myapp.bots.research:ResearchBot",
      "version": "0.1.0",
      "schedule": "weekly",
      "min_samples": 50,
      "auto_optimize": true,
      "apply": "runtime",
      "max_cost_usd": 5.0,
      "artifacts": [
        {"id": "system", "kind": "prompt"},
        {"id": "web_search", "kind": "tool"}
      ],
      "source_files": ["myapp/bots/research.py"],
      "registered_at": "2026-06-13T08:00:00Z",
      "last_optimized": "2026-06-06T08:57:00Z"
    }
  }
}
```

**注册时机**：装饰器 import 期写**内存** `_REGISTRY`，文件持久化只在 `evolution discover` 或 `EVOLUTION_AUTO_REGISTER=1` 下发生。避免"生产 import 用户模块就污染家目录"的安全雷区。

### 7.4 schedule 语法

```
"weekly"           → 每周一 08:57 UTC（沿用 evolution-loop.yml 错峰）
"daily"            → 每天 08:57 UTC
"hourly"           → 每小时 :57
"cron:0 8 * * 1"   → 自定义 5 字段 cron
None               → 不生成调度，纯手动
"on_min_samples"   → agent 进程退出时检查，默认关闭（atexit 副作用）
```

### 7.5 三种后端

**A. GitHub Actions**（P0 必做）

每 agent 一个 `.github/workflows/evolve-<agent>.yml`：

- 复用 `evolution-loop.yml` 的环境变量约定 + artifact 上传模式
- 文件头注明"自动生成"+ 重新生成命令
- 默认权限最小：仅 `apply="pr"` 时加 `pull-requests: write`
- 命名空间隔离：scaffold 生成的都叫 `evolve-*`，hermes 的叫 `evolution-loop`

**B. cron**（P1）

写 `~/.evolution/crontab` 的 `BEGIN:evolution-sdk` / `END:evolution-sdk` 块；`--install` 自动合并到 `crontab -e`。使用 `env -i` 显式声明环境变量。

**C. launchd**（P1）

生成 `~/Library/LaunchAgents/com.evolution.<agent>.plist` + wrapper 脚本 `~/.evolution/bin/run-<agent>.sh`（避免 API key 写进 plist 被备份到 iCloud）。

### 7.6 触发模式正交化

| 触发源 | 检测点 |
|---|---|
| `schedule` 到点 | 平台调度器（主要路径） |
| `min_samples` 达标 | optimizer 入口检查（不是独立触发，只是"门"） |
| `manual` | `evolution optimize --agent X` |
| `on_demand` | agent 进程 atexit（默认关闭） |

### 7.7 Drift 检测（`--check`）

```
对每个 registry agent:
  ① 期望文件存在？           ── 否 → MISSING
  ② hash 匹配 manifest？     ── 否 → 比对内容
       ├─ schedule 不一致？   → DRIFT
       └─ 其他不一致？        → MANUAL_EDIT（保留 + 警告）
  ③ schedule=None 但文件存在 → STALE

退出码：
  CLEAN          → 0
  DRIFT/MISSING  → 2  (CI 挂)
  MANUAL_EDIT    → 1  (警告)
```

### 7.8 与 hermes 的边界

- `evolution-loop.yml` 不被 scaffold 触碰
- scaffold 文件统一前缀 `evolve-*`，hermes 的叫 `evolution-loop`
- registry 中 hermes adapter 标 `schedule_managed_by: "evolution-loop.yml"`，scaffold 跳过

---

## 8. 错误处理

### 8.1 两类进程的不变量

**A. agent 进程：永不因 SDK crash**

| 失败点 | 行为 |
|---|---|
| 装饰器解析失败（id 冲突 / 找不到文本） | import 时 raise（唯一例外） |
| TraceSink 写入失败 | log warning + 静默 |
| 加载 optimized 失败 / JSON 损坏 | 回退基线 + warning |
| `baseline_hash` 不匹配 | 回退基线 + info |
| registry.json 写入失败 | 内存注册生效 + warning |
| `on_demand` 钩子 subprocess 失败 | 完全静默 |

**B. optimizer 进程：可失败但必须可观测**

| 失败点 | 行为 |
|---|---|
| agent 模块 import 失败 | 写 `FAILED/<ts>/error.json` + 退出码 1 → CI 红 |
| 单个 artifact 提取失败 | 跳过 + 计入 run_summary.failed_artifacts |
| traces 不足 | `SKIPPED/<ts>/` + 退出码 0 |
| GEPA 抛异常 | MIPROv2 fallback；都失败 → rejected 继续下一个 |
| 三道门拒绝 | rejected + rejection_reason，不影响其他 artifact |
| 预算耗尽 | 当前完成、剩余 budget_skipped、退出码 0 |
| 写回失败（磁盘/权限） | 退出码 1 + stderr `EVOLUTION_FATAL:` 前缀 |

### 8.2 跨进程一致性

| 风险 | 防御 |
|---|---|
| optimized 写中途崩溃 | 原子写：`<file>.tmp` + `os.rename` |
| agent 读 / optimizer 写竞态 | 原子写消解 |
| registry 多进程并发写 | `fcntl.flock` + 退避重试 3 次 |
| 同 agent 多 optimizer 并发 | `~/.evolution/locks/<agent>.lock` 文件锁 |
| GH Actions 超时 | 每 artifact 跑完立即写，已完成成果保留 |

---

## 9. 测试策略

### 9.1 金字塔四层

```
┌─────────────────────────────┐
│ ① 端到端：example_bot/       │  1 个，CI 必跑（mock LLM）
│   + nightly 真 LLM           │  1 个，scheduled，可关
├─────────────────────────────┤
│ ② 集成：sdk × core           │  10-15 个，每条流水线一个
├─────────────────────────────┤
│ ③ Adapter 对照               │  P0 仅 skill + tool_descriptions
│                              │  P1 扩到全 6 CLI
├─────────────────────────────┤
│ ④ 单元：每个模块              │  80+ 个，纯函数为主
└─────────────────────────────┘
```

### 9.2 端到端：`tests/sdk/example_bot/`

`EchoBot` 在 CI 跑完整 optimize 循环（mock LLM）：
1. 跑 20 次 → 落 traces
2. `python -m evolution.sdk.optimizer --agent echo-bot-test --mock-llm`
3. 断言 optimized 文件 + run_summary status=improved + 下次加载新版本
4. 改 source baseline → 断言 hash 不匹配回退新基线

`--mock-llm` 是 testability 核心：所有 `dspy.LM` 走可预测字符串替换。CI < 30 秒、$0。

### 9.3 集成

`test_trace_to_dataset.py` / `test_artifact_extraction.py` / `test_constraint_gates.py` / `test_optimized_loading.py` / `test_scaffold_generation.py` / `test_scaffold_drift.py` / `test_registry_concurrency.py` / `test_budget.py` / `test_apply_modes.py` / `test_failure_isolation.py` / `test_hermes_adapter_parity.py`

### 9.4 Adapter 对照测试 —— 关键防线

**P0 范围**：仅 `skill` + `tool_descriptions` 两个 CLI 对照。

**对照标准**（分两层）：
- **纯函数路径**（trace 解析、constraint 校验、数据集构造）→ **byte-equal**
- **GEPA 优化产物**（受 LLM 不确定性影响）→ **score 差异 < 5% 且 候选文本字符长度差异 < 10%**

走"快照 + 容差"，不强等价。P1 扩到 `tool_params` / `tool_reasoning` / `prompt_sections` / `code`。

### 9.5 测试基础设施

```
tests/sdk/
├── conftest.py              # tmp registry, mock LLM, fake traces fixtures
├── fixtures/
│   ├── traces/              # 预录 JSONL（含错误/重试/纠正样本）
│   ├── agents/              # 各种装饰器形态样例
│   │   ├── three_form_bot.py
│   │   ├── bad_id_conflict.py
│   │   └── echo_bot.py
│   └── snapshots/hermes_parity/
├── example_bot/
├── unit/
├── integration/
└── parity/
```

---

## 10. 最小可用切片

### 10.1 P0 — 必做（可发布最小 SDK）

1. `sdk/decorators.py` — 两层装饰器，三种文本来源解析
2. `sdk/runtime.py` — 运行时加载 + baseline_hash 校验
3. `sdk/trace_sink.py` — TraceSink 接口 + LocalJsonlSink
4. `sdk/registry.py` — 进程内 + 文件持久化 + flock
5. `sdk/artifact.py` — EvolvableArtifact 数据类
6. `sdk/agent_module.py` — AgentModule
7. `sdk/signals.py` — 5 个自动信号检测
8. `sdk/optimizer.py` — 主循环（GEPA + MIPROv2 fallback、三道门）
9. `sdk/ast_writer.py` — patch 模式的 AST 重写
10. `sdk/scaffold.py` — **仅 GH Actions 后端**
11. `sdk/cli.py` — `discover` / `scaffold` / `optimize`
12. `adapters/hermes.py` — 现有 6 CLI 包为 adapter
13. 测试：单元 ④ + 集成 ② + adapter 对照（skill + tool_descriptions）+ 端到端
14. **apply="patch" 模式**（runtime 之外的逃生口）

### 10.2 P1 — 推荐

15. cron 后端
16. launchd 后端 + wrapper 脚本
17. `apply="pr"` 模式（复用 `loop/pr_creator.py`）
18. judge_dimensions 完整配置 + 降级权重重分配
19. 合成数据集扩充（双门槛触发）
20. 预算估算 + 自动降级
21. adapter 对照测试扩到全 6 CLI

### 10.3 P2 — 视使用情况

22. 远程 TraceSink（HTTP / S3 / Postgres）
23. OpenTelemetry / OpenInference 兼容
24. 多 agent matrix workflow
25. Dashboard（web UI）
26. 用户 metric 安全沙箱（脚本字符串）

### 10.4 P0 规模估算

约 2500-3500 行代码 + 1500-2000 行测试。比 hermes 现有 `evolution/skills` 单模块大约 2-3x。

---

## 11. 风险清单

| 风险 | 缓解 |
|---|---|
| 装饰器拦截破坏用户类元属性（pickle / dataclass / 序列化） | 最小侵入：方法包装用 `functools.wraps`；类装饰器用 `setattr` 注入 `_evolution_meta`，不修改 `__init_subclass__` / 元类。**已知不兼容**：被装饰类不能是 `frozen=True` 的 dataclass（属性注入受阻），文档警告 |
| AST 写回改坏用户源码 | `apply="runtime"` 默认；patch/pr 生成 diff 给用户审；提供 `--ast-dry-run` |
| LLM-judge 漂移（模型升级使旧 score 失效） | run_summary 记 judge_model；baseline_hash 同时记 judge_model_hash |
| 分布式多机注册同 agent | flock 单机；多机场景显式不支持 + 文档警告 |
| 装饰器 import 期副作用拖慢冷启动 | 注册只做内存写 + hash，禁止网络/IO；预算 < 10ms/agent |
| `auto_optimize=True` + `EVOLUTION_AUTO_REGISTER=1` 在生产意外触发优化 | optimizer 需显式调用，装饰器不触发；环境变量需显式启用 |
| 用户 metric 函数抛异常 | 在 optimizer 进程里 try/except，metric 失败 → 降级到 judge+signal 加权 |

---

## 12. 与现有 hermes 流水线的兼容性

| 现有路径 | 处理 |
|---|---|
| `evolution/skills/evolve_skill.py` CLI | 不动，仍可单独调用 |
| `evolution/tools/evolve_tool_*.py` CLIs | 不动 |
| `evolution/prompts/evolve_prompt_sections.py` | 不动 |
| `evolution/code/evolve_code.py` | 不动 |
| `evolution/loop/run_loop.py` | 不动 |
| `.github/workflows/evolution-loop.yml` | 不动 |
| `~/.hermes/sessions/*.json` 会话格式 | 不动；adapter 内部读取 |
| `HERMES_AGENT_REPO` 环境变量 | 不动；hermes adapter 内部用 |

**adapter 接入路径**（可选）：用户也可以在 hermes 仓库的 PR 工作流里用 `evolution.adapters.hermes.HermesAdapter(name="hermes")` 把 hermes 同时注册进 registry，实现"统一视图"，但 schedule 仍由 `evolution-loop.yml` 管。

---

## 13. 开放问题（不在 P0 解决）

1. **用户 metric 的安全边界**：目前只支持 Python 函数引用（必须可 import），不支持脚本字符串。如果未来要支持，需要沙箱（subprocess / pyodide / restricted exec）。
2. **跨 agent 共享 prompt 库**：明确不做。如果用户有共享需求，由用户自己定义全局变量 + 多 agent 各自装饰器引用。
3. **Trace 隐私**：默认本地存储，依赖 `SECRET_PATTERNS` 过滤。企业部署的 PII 脱敏由用户在 TraceSink 实现里自己做。
4. **多语言 agent**：明确不支持。Python 装饰器路线 = Python only。未来若需要，走"运行时 SDK + 标准协议"重做。

---

## 附录 A — 包外部 API 表

```python
# evolution.sdk
from evolution.sdk import (
    evolvable_agent,
    evolvable_prompt,
    evolvable_tool,
    TraceSink,
    LocalJsonlSink,
)

# 用户扩展点
class TraceSink:
    def write(self, record: TraceRecord) -> None: ...
    def read(self, agent: str, since: datetime) -> Iterator[TraceRecord]: ...
    def count(self, agent: str, since: datetime) -> int: ...
```

## 附录 B — CLI 命令汇总

| 命令 | 作用 |
|---|---|
| `evolution discover <paths...>` | import 模块、刷新 registry.json |
| `evolution scaffold --backend ...` | 生成调度配置 |
| `evolution scaffold --check` | drift 检测 |
| `evolution optimize --agent <name>` | 手动触发优化 |
| `evolution status --agent <name>` | 查看 agent 状态（traces 计数、最近优化、当前 optimized）|
| `evolution rollback --agent <name> --artifact <id>` | 回滚到基线（删除 optimized 文件）|
