# Phase 21: Darwinian Code Evolution — Research

**研究日期:** 2026-05-20
**Domain:** LLM-driven code evolution，subprocess 沙箱评估，pytest fitness gate
**Confidence:** HIGH（openevolve API 已在 venv 内实测；ansi_strip.py 隔离运行已验证）

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01** openevolve (Apache-2.0, ≥0.2.27) 作为底层 evolutionary code search 库。darwinian-evolver 不存在于 PyPI，AGPL 问题永久关闭。

**D-02** pyproject.toml 加 `[project.optional-dependencies] code = ["openevolve>=0.2.27"]`，移除现存 `[darwinian]` extra。`pip install .[code]` 显式 opt-in。

**D-03** 单点 import 面架构：`evolution/code/code_evolver_adapter.py` 是项目内唯一写 `import openevolve` 的文件。

**D-04** LLM 路径走 openevolve 原生 client + 复用 EvolutionConfig 配置值（`optimizer_model` / `api_base` / `api_key` 三层链）。不走 `dspy.LM`。

**D-05** 不复用 GEPA reflection_lm 模式；接受 openevolve 自己的反思机制。反思 feedback 写入 openevolve trajectory log + metrics.json。

**D-06** PoC 组件 = `~/.hermes/hermes-agent/tools/ansi_strip.py`（44 行纯算法，已验证）。

**D-07** 测试切分 = 20/10 stratified + 5-10 手补 holdout edge case；stratify 按 CSI/SGR/OSC/other 四桶；seed=42。

**D-08** 测试发现走 AST + 静态扫描，不在主进程 exec 真实测试代码。

**D-09** 每个 candidate 评分建隔离目录 `~/.hermes/tmp/code_eval_<ts>_<candidate_id>/`，copy 最小 import 闭包（已验证 ansi_strip.py 闭包为空，只需 `tools/ansi_strip.py + tools/__init__.py`）。

**D-10** Baseline 跑一次缓存到磁盘；commit hash 命中缓存。

**D-11** Fitness 三段：`composite = pytest_score * 0.80 + size_component * 0.10 + ruff_score * 0.10`；pytest 不全过 → composite=0 直接 reject。

**D-12** size_component 三段线性映射：≤1.0 → 1.0；≤1.2 线性降至 0.7；≤1.5 线性降至 0.0；>1.5 硬 reject。

**D-13** ruff_score：0 violations → 1.0；1-2 → 0.7；3-5 → 0.4；6-10 → 0.1；>10 → 0.0。

**D-14** 无 LLM-as-judge 评分（连 nudge 也不开）。

**D-15** Holdout gate：best candidate 跑全 holdout，pytest 100% + size_component ≥ 0.7 + ruff_score ≥ 0.4 才进 output/code/。

**D-16** GEPA-like reflection feedback 字段：`pytest_failures` / `size_ratio` / `ruff_violations` / `composite_fitness` / `decision` / `reject_reason`。

**D-17** LICENSE 文件落仓根（MIT），本期第一个 plan 之前完成。

**D-18** CI lint gate：pre-commit local hook + pytest test_import_boundary.py 双层防御校 `import openevolve` 单点边界。

**D-19** output/code/<ts>/NOTICE.md 每次 evolve 都生成（含 LLM 生成源 + 未审核警示 + fitness 指标）。

**D-20** 沙箱：subprocess + restricted_env（删去所有 API key 环境变量） + timeout（120s）；不用 docker/firejail。

**D-21** evolution/code/LICENSING.md 文档说明 phase 内 license boundary。

### Claude's Discretion

- openevolve evolutionary loop 参数（population_size / archive_size / max_iterations）的保守 PoC 默认值
- code_target_loader.find_target_tests 的 AST 实现细节（ast.walk vs NodeVisitor）
- ruff_score / size_component 分位的 ±0.1 调整
- eval_dir 命名与清理（tempfile.TemporaryDirectory vs 手动 shutil.rmtree）
- openevolve native client 的具体 SDK 接入方式（已验证，见下）
- holdout edge case 测试的具体内容（planner 读源码后补真实 gap）
- metrics.json 字段是否走 `code_*` 前缀
- LICENSE 版权人（建议用 git config user.name，提交前人工 review）

### Deferred Ideas (OUT OF SCOPE)

- 多组件批量进化（Phase 23+）
- LLM-as-judge code quality nudge
- Property-based / fuzzing holdout
- Modal / firejail / docker sandbox
- CodeMetric 抽象 + 多 evolver plugin 注册中心
- evolved 代码自动 PR / 自动 merge
- Recursive self-evolution（永久 out-of-scope）
- 安全敏感组件演化（永久 out-of-scope）
- darwinian-evolver / AGPL 隔离基础设施（已 defuse，永久不需要）
- cross-run 历史 metrics 持久化
- `--allow-fallback` 真实降级路径
- 多语言代码进化
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| V2-CODE-01 | Darwinian code evolution — at least one hermes-agent code component evolvable | openevolve 0.2.27 已验证可安装；ansi_strip.py 已验证在隔离 dir 运行 30 个 pytest 全过；fitness 公式已设计完毕 |
</phase_requirements>

---

## Summary

Phase 21 将自进化能力从文本制品扩展到代码。核心决定已在 21-CONTEXT.md 锁定 21 条：用 openevolve (Apache-2.0, 0.2.27) 作进化引擎，以 `tools/ansi_strip.py`（44 行，1784 字节）作 PoC 目标，fitness = pytest 二进制硬门 (80%) + size_penalty (10%) + ruff lint (10%)。

本研究通过实际 tool 调用完成了 CONTEXT.md 全部 Risk Anchors 的 spike 验证：

1. **openevolve API surface 已完全验证**（[VERIFIED: venv pip install openevolve==0.2.27]）：openevolve 使用 `openai.OpenAI(api_key=..., base_url=api_base, ...)` 直接实例化 OpenAI-compatible client，`api_base` 通过 `LLMModelConfig.api_base` 注入，完全支持 DashScope / OpenRouter 等兼容端点。adapter 只需把 `EvolutionConfig.optimizer_model` / `api_base` / `api_key` 填入 `openevolve.Config`，无需 monkey-patch。

2. **ansi_strip.py 在隔离 dir 可独立运行**（[VERIFIED: 本地实测]）：30 个 pytest 全过，耗时 0.09s。只需复制 `tools/ansi_strip.py + tools/__init__.py`，不需要 hermes-agent root conftest（conftest 的 `_isolate_hermes_home` autouse fixture 在 isolated dir 缺失 hermes_cli 时会静默跳过，不影响 strip_ansi 函数测试）。

3. **size_penalty 阈值在 44 行小文件上的合理性**（[VERIFIED: wc -c]）：baseline_size_bytes = 1784。×1.2 = 2140 字节 (约 53 行)，×1.5 = 2676 字节 (约 66 行)。对算法改进而言 ×1.2 略紧，D-12 允许 planner 实测后放宽到 ×1.3/×1.6。

4. **ruff 未安装，需加入 [dev]**（[VERIFIED: pip show ruff NOT FOUND]）：ruff JSON 输出格式已验证，每条包含 `code` / `message` / `location` / `severity` 字段，直接解析 len(violations) 即可。

5. **pyproject.toml 现状**：`[darwinian]` extra 存在（需删除替换），`.gitignore` 已含 `output/`（CONCERNS H4 已修复），无 `.pre-commit-config.yaml`（新建），无 `LICENSE`（Wave 0 必须新建），无 ruff config（Wave 0 新建最小配置）。

**主要建议：** adapter 直接用 `openevolve.run_evolution(initial_program, evaluator_file, config=oe_config, iterations=N, output_dir=str(output_dir), cleanup=False)` 接口；evaluator 写成独立 Python 文件（含 `def evaluate(program_path): ...`），在 subprocess 中运行 pytest，返回 `{"combined_score": float, "pytest_passed": int, ...}` 字典。

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 代码进化调度（LLM mutation loop） | evolution/code layer | openevolve（外部库） | openevolve 内部维护 population/archive/MAP-Elites；adapter 只负责配置注入和 result 提取 |
| Fitness 评估（pytest + size + ruff） | evolution/code layer | subprocess（stdlib） | fitness 是本项目的核心业务逻辑，openevolve 只消费浮点数 combined_score |
| 沙箱隔离（candidate 安全运行） | evolution/code/sandbox_runner | subprocess（stdlib） | 直接等价 tblite_runner.py 模式，无外部依赖 |
| 目标发现（AST 解析 tests/） | evolution/code/code_target_loader | ast（stdlib） | 纯 stdlib，静态分析不 exec 代码 |
| CLI 入口 | evolution/code/evolve_code.py | Click + EvolutionConfig | 复用 evolve_tool_descriptions.py 三件套模式 |
| 许可证边界 | evolution/code/code_evolver_adapter.py | CI lint gate | 单点 import 面 + pre-commit + pytest 双层护栏 |
| 产物落盘 | output/code/<ts>/ | .gitignore | output/ 已在 .gitignore，NOTICE.md + metrics.json 同目录 |

---

## Standard Stack

### Core（Phase 21 新增）

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| openevolve | 0.2.27 [VERIFIED: pip index versions] | LLM-driven code evolution（MAP-Elites + population + mutation reflection） | PyPI 上唯一 actively-maintained 的 LLM-driven code evolution 库；Apache-2.0；API surface 完整映射需求 |
| ruff | latest (≥0.4) [VERIFIED: pip install ruff 成功] | lint score 计算（D-13 ruff_score） | 业界标准 Python linter；`--output-format=json` 输出结构简单稳定；stdlib subprocess 调用即可 |

### 复用（已有，无新依赖）

| Library | Version | Purpose | 来源 |
|---------|---------|---------|------|
| subprocess / ast / shutil / tempfile / json | stdlib | sandbox_runner / target_loader / fitness / output | Python stdlib |
| click / rich | ≥8.0 / ≥13.0 | CLI + terminal output | 已在 pyproject.toml dependencies |
| EvolutionConfig | 项目内 | 三层配置链复用 | evolution/core/config.py |
| ConstraintResult | 项目内 | size / ruff 约束结果封装 | evolution/core/constraints.py |

### 安装命令

```bash
# 安装 openevolve（显式 opt-in）
pip install -e ".[code]"

# 开发时同时安装 ruff（加入 [dev] extra）
pip install -e ".[dev,code]"
```

**Version verification** [VERIFIED: pip index versions openevolve]:
- openevolve 最新版 = 0.2.27（PyPI 确认，发布活跃，最后版本 2025 年）
- openevolve 依赖：dacite / flask / numpy / openai / pyyaml / tqdm（均为常见包，无冲突）

---

## Architecture Patterns

### System Architecture Diagram

```
evolve_code CLI (Click)
        │
        ▼
EvolutionConfig.load(yaml / env / CLI)
        │ optimizer_model / api_base / api_key
        ▼
code_evolver_adapter.evolve(target, fitness_fn, config)
        │  构造 openevolve.Config(llm=LLMConfig(models=[LLMModelConfig(name=model, api_base=..., api_key=...)]))
        │  调用 openevolve.run_evolution(program_path, evaluator_file, config=oe_config)
        ▼
openevolve 内部 (MAP-Elites + LLM mutation)
        │  每次 candidate 生成后调用 evaluator_file.evaluate(program_path)
        ▼
evaluator_file.evaluate(program_path)  [独立 .py 文件，openevolve 在 subprocess 中 importlib 加载]
        │  调用 sandbox_runner.run_pytest_in_sandbox(candidate_path, eval_dir)
        ▼
sandbox_runner
        │  mkdir eval_dir
        │  copy tools/ansi_strip.py(candidate) + tools/__init__.py + test_ansi_strip.py
        │  subprocess.run(pytest, cwd=eval_dir, env=restricted_env, timeout=120)
        ▼
code_fitness.score_candidate(evolved_path, eval_dir, baseline_size) -> CodeFitness
        │  pytest_score (硬门) + size_component + ruff_score → composite_fitness
        │  返回 {"combined_score": float, "pytest_passed": int, ...}
        ▼
openevolve 接收 combined_score，更新 MAP-Elites archive，生成下一个 mutation
        │
        ▼ (max_iterations 或 cost cap 触发)
EvolutionResult.best_code  (openevolve 追踪 best_program_id)
        │
        ▼
holdout gate：score_candidate(best_candidate, holdout_tests)
        │  所有 gate 过 → output/code/<ts>/{ansi_strip.py, NOTICE.md, metrics.json, diff.txt}
        │  任一不过 → output/code/FAILED_<ts>/
        ▼
output/code/<ts>/  (永久产物，不写回 hermes-agent)
```

### Recommended Project Structure

```
evolution/code/
├── __init__.py              # lazy ImportError guard（openevolve 未安装时不 crash）
├── code_target_loader.py    # CodeTarget dataclass + find_target_tests (AST)
├── code_fitness.py          # CodeFitness dataclass + score_candidate()
├── code_evolver_adapter.py  # 唯一 import openevolve 的文件
├── sandbox_runner.py        # subprocess + timeout + restricted_env
├── evolve_code.py           # Click CLI 入口
└── LICENSING.md             # license boundary 文档

tests/code/
├── __init__.py
├── test_import_boundary.py  # CI lint gate pytest 层
├── test_code_target_loader.py
├── test_code_fitness.py
├── test_sandbox_runner.py
├── test_evolve_code_cli.py
└── test_ansi_strip_holdout.py  # 5-10 edge case（evolution 仓内，不入 hermes-agent）

output/code/             # .gitignore 已含
├── .gitkeep
└── <ts>/
    ├── ansi_strip.py    # best evolved candidate
    ├── NOTICE.md
    ├── metrics.json
    ├── diff.txt
    └── eval_holdout.json
```

---

## openevolve API Surface — Spike 验证结论

**[VERIFIED: venv import + source read, openevolve 0.2.27]**

### 1. LLM client 接口

openevolve 使用 `openai.OpenAI(api_key=api_key, base_url=api_base, ...)` 实例化 client（`llm/openai.py` line 85-90）。`api_base` 通过 `LLMModelConfig.api_base` 字段传入，默认值 `"https://api.openai.com/v1"`。

**结论：完全支持 OpenAI-compatible 端点（DashScope / OpenRouter）。adapter 只需：**

```python
from openevolve import Config
from openevolve.config import LLMModelConfig

oe_config = Config()
oe_config.llm.api_base = evolution_config.api_base or "https://api.openai.com/v1"
oe_config.llm.api_key = evolution_config.api_key
oe_config.llm.models = [
    LLMModelConfig(
        name=evolution_config.optimizer_model,
        api_base=evolution_config.api_base or "https://api.openai.com/v1",
        api_key=evolution_config.api_key,
    )
]
oe_config.max_iterations = iterations
```

**无需 monkey-patch，无需 shim。** D-04 Risk Anchor 已消解。

### 2. fitness function 接入接口

openevolve 的 evaluator 是一个独立 `.py` 文件，必须包含 `def evaluate(program_path: str) -> dict` 函数，返回含 `"combined_score"` 的字典（或任意含数值的字典，openevolve 自动平均）。

```python
# evaluator_file.py（由 adapter 动态生成，写入临时目录）
def evaluate(program_path: str) -> dict:
    from evolution.code.code_fitness import score_candidate
    # ... 调用 sandbox_runner ...
    fitness = score_candidate(Path(program_path), eval_dir, baseline_size)
    return {
        "combined_score": fitness.composite,
        "pytest_passed": fitness.pytest_passed,
        "pytest_total": fitness.pytest_total,
        "size_component": fitness.size_component,
        "ruff_score": fitness.ruff_score,
        # feedback 字段（D-16）：让 openevolve 反思 prompt 拿到详情
        "pytest_failures": fitness.pytest_failures,
        "ruff_violations": fitness.ruff_findings,
    }
```

**openevolve 在独立子进程中 `importlib.util.spec_from_file_location` 加载 evaluator_file，所以 evaluator 必须是 self-contained（不能依赖 lambda/closure）。** adapter 需要把 sandbox_runner 的路径写入 evaluator 文件，或通过环境变量传递。

**推荐实现：** adapter 生成一个临时 evaluator .py 文件，将 `eval_dir_base`、`baseline_size`、`train_test_ids` 等作为 module-level constants 写入。这样 evaluator 是 self-contained，openevolve subprocess 可直接加载。

### 3. best candidate 获取

`run_evolution` 返回 `EvolutionResult`，含：
- `best_code: str`：直接是代码字符串，可写入文件
- `best_score: float`：`combined_score` 的值
- `metrics: dict`：last evaluated metrics
- `output_dir: str`：openevolve 内部 checkpoint 目录（cleanup=False 时保留）

```python
result = openevolve.run_evolution(
    initial_program=str(target_path),
    evaluator=str(evaluator_file_path),
    config=oe_config,
    iterations=max_iterations,
    output_dir=str(oe_internal_dir),
    cleanup=False,  # 保留 trajectory log 供人工审计
)
best_code = result.best_code  # str
```

### 4. 关键演化参数默认值与 PoC 推荐值

| 参数 | 默认值 | PoC 推荐值 | 说明 |
|------|--------|-----------|------|
| `Config.max_iterations` | 10000 | 20-50 | PoC 阶段保守，约 $2-5 |
| `DatabaseConfig.population_size` | 1000 | 50 | 小文件进化，不需要大池 |
| `DatabaseConfig.archive_size` | 100 | 20 | MAP-Elites 存档 |
| `DatabaseConfig.num_islands` | 5 | 3 | 减少并发 LLM 调用 |
| `EvaluatorConfig.timeout` | 300s | 120s | 对齐 D-09 sandbox timeout |
| `EvaluatorConfig.parallel_evaluations` | 1 | 1 | PoC 单评估，避免 tmp dir 冲突 |
| `LLMConfig.temperature` | 0.7 | 0.7 | 默认即可 |

**注意：** openevolve 的 `EvaluatorConfig.timeout` 是 openevolve 内部对 evaluator 子进程的超时，与 sandbox_runner 的 pytest timeout 叠加。建议 openevolve timeout (120s) ≥ pytest timeout (30s per test，120s total)。

### 5. evolution markers 要求

openevolve 需要 initial_program 中存在 `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` 注释标记来标识可进化区域（api.py line 219-226）。如果不存在，openevolve 自动将整个文件包裹。

**对 ansi_strip.py：** 文件只有 44 行，应将整个函数体（`strip_ansi` 函数内部）标记为 EVOLVE-BLOCK，保留 module docstring 和 import 行不变。adapter 写入 initial_program 时加入这两个注释。

---

## ansi_strip.py 隔离运行可行性 — Spike 验证结论

**[VERIFIED: 本地 subprocess 实测，Python 3.13.3，0.09s，30/30 passed]**

### import 闭包分析

`tools/ansi_strip.py`（1784 字节，44 行）仅有一个 import：
```python
import re
```
闭包极简，完全 stdlib-only。

### 测试文件 import 路径

`tests/tools/test_ansi_strip.py` line 8：
```python
from tools.ansi_strip import strip_ansi
```
要求 `eval_dir` 根目录能解析 `tools` 包。

### D-09 最小 eval_dir 拷贝清单

```
eval_dir/
├── tools/
│   ├── __init__.py     (空文件即可)
│   └── ansi_strip.py   (candidate 版本)
└── test_ansi_strip.py  (从 hermes-agent/tests/tools/ 复制)
```

**hermes-agent root conftest.py 无需复制**。conftest 的 `_isolate_hermes_home` autouse fixture 依赖 `hermes_cli` 模块，但 test_ansi_strip.py 不 import 任何 hermes 模块，fixture 中的 `try/except` 会静默跳过 plugin manager 重置，不影响测试结果。

### pytest 运行命令（sandbox_runner 参考）

```python
subprocess.run(
    [sys.executable, "-m", "pytest", "test_ansi_strip.py",
     "-x", "--tb=line", "-q", "--no-header",
     "--json-report",  # 若有 pytest-json-report；否则解析 stdout
    ],
    cwd=str(eval_dir),
    env=restricted_env,
    timeout=120,
    capture_output=True,
    text=True,
)
```

**注意：** `pytest-json-report` 不在 venv dev 依赖中。推荐不用 json-report，改用解析 pytest 的 `--tb=line -q` 输出（失败行 `FAILED test_name::test_method - AssertionError: ...`），正则提取 test_name + 错误信息写入 CodeFitness.pytest_failures。

---

## size_penalty 阈值合理性验证

**[VERIFIED: wc -c ansi_strip.py = 1784 bytes]**

| 阈值 | 字节数 | 约等于行数 | 评估 |
|------|--------|-----------|------|
| baseline | 1784 | 44 行 | — |
| ×1.2 | 2140 | ~53 行 | 偏紧：一个 docstring 扩展或一个辅助函数即越界 |
| ×1.3 | 2319 | ~57 行 | 合理：允许小幅结构改进 |
| ×1.5 | 2676 | ~66 行 | D-12 当前硬 reject 上限 |
| ×1.6 | 2854 | ~71 行 | 松上限备选 |

**建议（Claude's Discretion）：** planner 将 D-12 软警告阈值从 ×1.2 放宽到 ×1.3，硬 reject 上限从 ×1.5 放宽到 ×1.6（size_component 映射相应调整）。44 行小文件的进化很可能需要添加一些辅助逻辑，×1.2 实测容易触发 soft penalty 导致 fitness 信号过早惩罚正确方向的探索。

---

## ruff 配置现状与推荐

**[VERIFIED: ruff.toml NOT FOUND; pyproject.toml [tool.ruff] NOT FOUND; ruff NOT IN VENV]**

### 现状

仓内无 ruff 配置。ruff 未安装（即使 venv）。D-13 要求 `ruff check --output-format=json`。

### Wave 0 必须完成

1. 在 pyproject.toml `[dev]` extra 中加 `ruff`（或在 `[code]` extra 中）
2. 在 pyproject.toml 或 ruff.toml 加最小配置：

```toml
[tool.ruff]
line-length = 120
select = ["E", "F", "W"]
# 排除 evolution/ 内的配置不影响 hermes-agent 代码评估
# ruff check 对 evolved 文件用的是全局 select
```

### ruff JSON 输出格式（已验证）

[VERIFIED: 本地运行 ruff check --output-format=json /tmp/test_ruff_target.py]

每条 violation 的结构：
```json
{
  "code": "F401",
  "message": "`os` imported but unused",
  "filename": "/path/to/file.py",
  "location": {"row": 1, "column": 8},
  "severity": "error"
}
```

**score_candidate 实现：**
```python
def _run_ruff(evolved_path: Path) -> tuple[int, list[dict]]:
    result = subprocess.run(
        ["ruff", "check", "--output-format=json", str(evolved_path)],
        capture_output=True, text=True, timeout=10
    )
    # ruff 返回 exit code 1 表示有 violations（不是错误）
    try:
        findings = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        findings = []
    return len(findings), [{"rule_id": f["code"], "message": f["message"], "line": f["location"]["row"]} for f in findings]
```

---

## 基础设施前置状态（Wave 0 依赖）

**[VERIFIED: 本地文件系统检查]**

| 项目 | 现状 | Wave 0 行动 |
|------|------|------------|
| `LICENSE` 仓根 | **NOT FOUND** | 新建 MIT LICENSE（D-17，不可逆，executor 提交前 AskUserQuestion 确认版权人） |
| `.pre-commit-config.yaml` | **NOT FOUND** | 新建，含 `openevolve-single-import-surface` local hook |
| `output/` in `.gitignore` | **已存在**（CONCERNS H4 已修复） | 无需操作 |
| `[darwinian]` extra in pyproject.toml | **已存在**（`"darwinian-evolver"` 指向不存在包） | 删除并替换为 `code = ["openevolve>=0.2.27"]` |
| ruff in pyproject.toml dev/code extra | **未声明** | 加入 `[dev]` extra（或 `[code]`） |
| `ruff.toml` or `[tool.ruff]` | **NOT FOUND** | 在 pyproject.toml 加 `[tool.ruff]` 最小配置 |
| `tests/code/` 目录 | 不存在 | Wave 0 新建（+7 个测试文件） |
| `evolution/code/` 包 | 不存在 | Wave 0 新建（+6 个生产文件） |
| `output/code/.gitkeep` | 不存在 | Wave 0 新建（output/ 已 gitignored，目录占位） |

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM-driven code mutation + MAP-Elites archive | 自己实现 population + mutation + diversity | openevolve.run_evolution() | openevolve 内置 MAP-Elites、island migration、diversity metric、edit_distance tracking；自研需要 ~1000 LOC |
| OpenAI-compatible HTTP client | 自己 requests.post | openai.OpenAI（openevolve 内部） | openevolve 已处理 retry / timeout / reasoning model 差异（gpt-o1 需要 max_completion_tokens 而非 max_tokens）；config.py line 118 有完整分支 |
| ruff violation 解析 | 正则解析 ruff 文本输出 | `ruff check --output-format=json` | JSON 输出稳定有 schema，文本输出随版本变化 |
| pytest 结果解析 | 解析 pytest stdout 文本 | `pytest --tb=line -q`（加简单正则） | 注：pytest-json-report 不在 dev deps，用 `--tb=line -q` 正则解析 FAILED 行即可；结构简单 |
| subprocess 沙箱 | 自己实现 timeout + SIGTERM/SIGKILL | 直接复用 tblite_runner.py 的 Popen + state-monitor 模式 | Phase 20 已验证可靠；只需简化版（无 heartbeat 因 candidate eval 是短任务）|

---

## Common Pitfalls

### Pitfall 1：openevolve evaluator 必须是 self-contained Python 文件

**What goes wrong:** 传递 lambda / closure / method 作为 evaluator，openevolve 的 evaluator subprocess 无法序列化跨进程。

**Why it happens:** openevolve 用 `importlib.util.spec_from_file_location` 在子进程中加载 evaluator，无法访问父进程内存。`evolve_code()` API 虽然尝试 `inspect.getsource()` 序列化 callable，但依赖外部闭包变量（`eval_dir`, `baseline_size`）的函数无法被完整序列化。

**How to avoid:** adapter 动态生成一个完整的 evaluator .py 文件，将所有需要的参数（eval_dir_base、baseline_size、train_test_ids 等）作为 module-level 常量写入。文件是 self-contained，可在任何 Python 进程中独立运行。

**Warning signs:** `ImportError` 或 `AttributeError: module has no attribute 'evaluate'` 在 openevolve evaluator 加载时。

### Pitfall 2：ruff 返回 exit code 1 ≠ 运行失败

**What goes wrong:** `subprocess.run(["ruff", ...], check=True)` 因 ruff 有 violations 而触发 CalledProcessError，导致 score_candidate 意外抛异常。

**Why it happens:** ruff exit code：0 = 无 violations，1 = 有 violations（正常），2 = 内部错误。

**How to avoid:** 不传 `check=True`；检查 `returncode in (0, 1)` 为正常情况，解析 stdout JSON；`returncode == 2` 时记录 ruff 内部错误，ruff_score 降级为 0.5（避免因 ruff 自身崩溃惩罚 candidate）。

### Pitfall 3：ansi_strip.py candidate 中隐式 import hermes 模块

**What goes wrong:** openevolve LLM 生成的 mutation 意外 `from hermes.agent import ...`，subprocess pytest 尝试解析 hermes 导致 ImportError，表现为 pytest 失败但非 assertion 失败，容易误判为 candidate 逻辑错误。

**How to avoid:** sandbox_runner 设置 `PYTHONPATH=eval_dir`（只含 tools/ 目录），不包含 hermes-agent 源码路径；`restricted_env` 显式删除 `PYTHONPATH` 后重设为仅 eval_dir。测试 `test_import_boundary_in_candidate` 专门注入一个含 `import hermes` 的 candidate 验证 fitness=0 且 reject_reason="pytest_fail"。

### Pitfall 4：openevolve CONFIG 默认 population_size=1000 导致内存/时间问题

**What goes wrong:** 忘记覆盖默认参数，openevolve 初始化 1000 候选程序的数据库，内存占用高，第一轮迭代就需要大量 LLM 调用。

**How to avoid:** adapter 始终显式设置 PoC 保守参数：`oe_config.database.population_size = 50`，`oe_config.database.archive_size = 20`，`oe_config.max_iterations = 20`（CLI flag 可覆盖）。

### Pitfall 5：evolution markers 覆盖 import 行导致 candidate 无法运行

**What goes wrong:** adapter 把 `# EVOLVE-BLOCK-START` 放在文件最顶部（包含 `import re`），openevolve 生成的 patch 去掉了 import，candidate 运行 NameError。

**How to avoid:** evolution markers 只包裹 strip_ansi 函数体（第 36-44 行），保留 `import re`、模块 docstring 和正则常量定义在 EVOLVE-BLOCK 之外。ansi_strip.py 有两个 module-level 正则常量（`_ANSI_ESCAPE_RE`、`_HAS_ESCAPE`），这些也应放在 EVOLVE-BLOCK 内（允许进化），但 `import re` 固定不变。

### Pitfall 6：eval_dir 未清理积累大量临时文件

**What goes wrong:** 每个 candidate 建一个 eval_dir，20 轮 × 50 candidates = 1000 个目录，磁盘占满。

**How to avoid:** sandbox_runner 每次 evaluate 后立即 `shutil.rmtree(eval_dir, ignore_errors=True)`；evolve 结束后（成功或失败）统一清理 `~/.hermes/tmp/code_eval_<run_ts>/` 整个 run 目录。推荐 `contextlib.contextmanager` + `tempfile.mkdtemp` 包裹 eval_dir 生命周期，确保异常时也清理。

### Pitfall 7：NOTICE.md 中误写入 API key（来自 LLM 反思 log）

**What goes wrong:** openevolve feedback/reflection 内容包含用户 API key 字面量（极少见，但 LLM 可能在 mutation prompt 里回显 config）。

**How to avoid:** NOTICE.md 写入前用 `_contains_secret`（来自 evolution/core/external_importers.py，已有 SECRET_PATTERNS）过滤所有 fitness.pytest_failures / ruff_findings 字段。

---

## Code Examples

### openevolve Config 构造（adapter 核心）

```python
# Source: [VERIFIED: openevolve/config.py, openevolve/api.py]
from openevolve import Config, run_evolution
from openevolve.config import LLMModelConfig

def _build_oe_config(evolution_config, iterations: int, sandbox_timeout: int) -> Config:
    oe_config = Config()
    model_cfg = LLMModelConfig(
        name=evolution_config.optimizer_model,
        api_base=evolution_config.api_base or "https://api.openai.com/v1",
        api_key=evolution_config.api_key,
        temperature=0.7,
        max_tokens=4096,
        timeout=sandbox_timeout,
    )
    oe_config.llm.models = [model_cfg]
    oe_config.llm.evaluator_models = [model_cfg]
    oe_config.max_iterations = iterations
    oe_config.database.population_size = 50    # PoC 保守值
    oe_config.database.archive_size = 20
    oe_config.database.num_islands = 3
    oe_config.evaluator.timeout = sandbox_timeout  # 与 D-09 对齐
    oe_config.evaluator.cascade_evaluation = False  # 单 evaluate() 函数
    oe_config.evaluator.parallel_evaluations = 1    # 避免 tmp dir 冲突
    return oe_config
```

### sandbox_runner 核心（简化版 tblite_runner）

```python
# Source: [VERIFIED: 本地实测；基于 evolution/benchmarks/tblite_runner.py 模式]
import subprocess, sys, shutil, os
from pathlib import Path

def run_pytest_in_sandbox(
    candidate_path: Path,
    eval_dir_base: Path,
    test_file_path: Path,
    run_id: str,
    restricted_env: dict,
    timeout_seconds: int = 120,
) -> tuple[int, int, list[dict]]:
    """返回 (passed, total, failures)"""
    eval_dir = eval_dir_base / run_id
    eval_dir.mkdir(parents=True, exist_ok=True)
    try:
        # 最小 import 闭包：tools/__init__.py + candidate + test
        tools_dir = eval_dir / "tools"
        tools_dir.mkdir(exist_ok=True)
        (tools_dir / "__init__.py").write_text("")
        shutil.copy2(candidate_path, tools_dir / "ansi_strip.py")
        shutil.copy2(test_file_path, eval_dir / "test_ansi_strip.py")

        env = restricted_env.copy()
        env["PYTHONPATH"] = str(eval_dir)  # 只允许 eval_dir + stdlib

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "test_ansi_strip.py",
             "-x", "--tb=line", "-q", "--no-header"],
            cwd=str(eval_dir),
            env=env,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
        )
        return _parse_pytest_output(result.stdout, result.returncode)
    except subprocess.TimeoutExpired:
        return 0, -1, [{"test_name": "timeout", "assertion_msg": f"Timeout after {timeout_seconds}s"}]
    finally:
        shutil.rmtree(eval_dir, ignore_errors=True)
```

### restricted_env 构造

```python
# Source: [ASSUMED - 基于 D-20 决策；API key 列表来自 CONTEXT.md §D-20]
_API_KEY_ENV_VARS = {
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "DASHSCOPE_KEY",
    "EVOLUTION_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET",
}

def build_restricted_env(eval_dir: Path) -> dict:
    env = os.environ.copy()
    for key in _API_KEY_ENV_VARS:
        env.pop(key, None)
    env["HERMES_AGENT_REPO"] = str(eval_dir)  # 隔离到 eval_dir
    env["PYTHONPATH"] = str(eval_dir)
    return env
```

### evolve_code CLI skeleton（对齐 evolve_tool_descriptions.py 三件套）

```python
# Source: [VERIFIED: evolution/tools/evolve_tool_descriptions.py 模式]
import click
from evolution.core.config import EvolutionConfig

@click.command()
@click.option("--component", required=True, help="Target component relative path (e.g. tools/ansi_strip.py)")
@click.option("--iterations", default=20, help="Max evolution iterations")
@click.option("--max-cost", default=5.0, type=float, help="Max LLM cost in USD")
@click.option("--hermes-repo", default=None, help="Override HERMES_AGENT_REPO")
@click.option("--model", default=None, help="Override optimizer model")
@click.option("--api-base", default=None, help="Override API base URL")
@click.option("--dry-run", is_flag=True, help="Pre-flight + baseline only, skip evolution")
@click.option("--allow-fallback", is_flag=True, help="(未来) openevolve 不可用时降级（本期占位）")
def main(component, iterations, max_cost, hermes_repo, model, api_base, dry_run, allow_fallback):
    config = EvolutionConfig.load(
        hermes_repo=hermes_repo,
        model=model,
        api_base=api_base,
        max_cost_usd=max_cost,
        iterations=iterations,
    )
    evolve(config, component, dry_run=dry_run)

if __name__ == "__main__":
    main()
```

### CodeFitness dataclass

```python
# Source: [ASSUMED - 基于 D-11..D-15 决策；结构类比 evolution/core/constraints.py ConstraintResult]
from dataclasses import dataclass, field

@dataclass
class CodeFitness:
    pytest_passed: int
    pytest_total: int
    size_baseline_bytes: int
    size_evolved_bytes: int
    ruff_violations: int
    pytest_score: float       # 0.0 或 1.0（硬二进制）
    size_component: float     # 0.0..1.0
    ruff_score: float         # 0.0..1.0
    composite: float          # weighted sum
    decision: str             # "accept" | "reject"
    reject_reason: str        # "" 或 "pytest_fail:..." / "size_oversize:..." / "timeout"
    pytest_failures: list[dict] = field(default_factory=list)
    ruff_findings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """metrics.json 序列化格式（code_* 前缀）"""
        return {
            "code_pytest_passed": self.pytest_passed,
            "code_pytest_total": self.pytest_total,
            "code_size_baseline_bytes": self.size_baseline_bytes,
            "code_size_evolved_bytes": self.size_evolved_bytes,
            "code_size_ratio": round(self.size_evolved_bytes / self.size_baseline_bytes, 3),
            "code_ruff_violations": self.ruff_violations,
            "code_pytest_score": self.pytest_score,
            "code_size_component": self.size_component,
            "code_ruff_score": self.ruff_score,
            "code_composite_fitness": self.composite,
            "code_decision": self.decision,
            "code_reject_reason": self.reject_reason,
        }
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| darwinian-evolver (AGPL, 不存在) | openevolve 0.2.27 (Apache-2.0) | 2026-04-23 研究验证 | AGPL 边界问题永久消解；可直接 import |
| subprocess 进程隔离 AGPL 包 | 直接 `from openevolve import ...` 在 adapter | D-01 决策 | 去掉 .venv-agpl/，架构大幅简化 |
| 全文件 EVOLVE-BLOCK | 只包裹函数体 | openevolve 0.2.x | 保留 import 稳定性，减少 mutation 破坏 |

**Deprecated/outdated:**
- `pyproject.toml [darwinian]` extra：指向 `"darwinian-evolver"` 不存在包，Wave 0 必须删除替换为 `code = ["openevolve>=0.2.27"]`

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `_contains_secret` 过滤足以防止 NOTICE.md 写入 API key | Code Examples（restricted_env + NOTICE.md） | NOTICE.md 可能包含明文 key；风险低（openevolve 不回显 config） |
| A2 | ansi_strip.py 的 `tools/__init__.py` 空文件已足够（无隐式 hermes 注册） | sandbox_runner 部分 | hermes tools/ 可能有 `__init__.py` 内容；实测 test 过了说明可以空文件 |
| A3 | PoC 参数 pop_size=50 / iterations=20 足以在 $5 内找到改进 | openevolve Config | openevolve 对 44 行小文件可能需要更多迭代；--iterations CLI flag 可覆盖 |
| A4 | pytest 在 venv Python 中调用（`sys.executable`）即可在 eval_dir 运行（无需安装 hermes deps） | sandbox_runner | 若 venv 缺 pytest，则失败；pre-flight 检查 `python -m pytest --version` 即可 |
| A5 | `ruff check` 的 `--select E,F,W` 对 LLM 生成的 Python 代码有合理覆盖率 | ruff 配置 | 过严（太多误报）或过松（漏洞）；实测后可调 |

---

## Open Questions

1. **evolve_code 在 pre-flight 检查中如何优雅处理 pytest-json-report 未安装？**
   - What we know：pytest-json-report 不在 dev deps；`--tb=line -q` stdout 解析可行（FAILED 行格式稳定）
   - What's unclear：是否值得添加 pytest-json-report 以获得结构化输出
   - Recommendation：不添加；用正则解析 `FAILED {test_id} - {exception_type}: {msg}` 已经足够（D-16 feedback 只需 test_name + assertion_msg）

2. **openevolve 内部 evolution_trace log 落在哪里？如何对接 metrics.json？**
   - What we know：EvolutionTraceConfig.enabled 默认 False；output_dir 下有 checkpoint/ 目录
   - What's unclear：是否需要启用 trace 来获取 per-iteration fitness 历史
   - Recommendation：D-05 说明 feedback 写入 openevolve trajectory log，cleanup=False 保留 output_dir 即可供人工审计；metrics.json 只记录 final best candidate 的指标

3. **test_ansi_strip.py 中 `test_none` 断言 `strip_ansi(None) is None`，而函数签名 `text: str`——evolved 版本可能改类型注解导致测试失败？**
   - What we know：当前实现 `if not text or not _HAS_ESCAPE.search(text)` 对 None 直接走 `if not text` 分支返回 None
   - What's unclear：openevolve 是否会修改函数签名或 None 处理
   - Recommendation：在 evaluator feedback 中不特殊处理 None 测试；如果 openevolve 生成的代码改了 None 行为，pytest 就会抓到——这正是测试的价值

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13.3 (.venv) | 所有组件 | ✓ | 3.13.3 | — |
| openevolve | code_evolver_adapter | ✓（pip install 成功） | 0.2.27 | 无（pip install .[code] Wave 0 前置） |
| ruff | code_fitness.score_candidate | ✗（venv 未安装） | — | 加入 [dev] extra，Wave 0 安装 |
| pytest (.venv) | sandbox_runner / tests | ✓ | 9.0.3 | — |
| hermes-agent ansi_strip.py | CodeTarget | ✓ (`~/.hermes/hermes-agent/tools/ansi_strip.py`) | 44 行，1784 bytes | — |
| hermes-agent test_ansi_strip.py | CodeTarget | ✓ (`~/.hermes/hermes-agent/tests/tools/`) | 30 tests，168 行 | — |
| subprocess / ast / shutil / tempfile | sandbox_runner / target_loader | ✓ | stdlib | — |

**Missing dependencies with no fallback:**
- `ruff`：Wave 0 必须通过 `pip install ruff`（加 dev extra）安装

**Missing dependencies with fallback:**
- 无

---

## Validation Architecture

> workflow.nyquist_validation 未设置 false，本节必须包含。

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` testpaths = ["tests"] |
| Quick run command | `pytest tests/code/ -x -q` |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| V2-CODE-01 | at least one code component evolvable | E2E dry-run | `pytest tests/code/test_evolve_code_cli.py::test_dry_run_e2e -x` | ❌ Wave 0 |
| V2-CODE-01 | fitness function 评分 pytest 二进制硬门 | unit | `pytest tests/code/test_code_fitness.py::test_pytest_fail_gives_zero -x` | ❌ Wave 0 |
| V2-CODE-01 | fitness function size penalty | unit | `pytest tests/code/test_code_fitness.py::test_size_oversize_rejects -x` | ❌ Wave 0 |
| V2-CODE-01 | fitness function ruff score | unit | `pytest tests/code/test_code_fitness.py::test_ruff_score_mapping -x` | ❌ Wave 0 |
| V2-CODE-01 | sandbox timeout 不泄漏 API key | unit | `pytest tests/code/test_sandbox_runner.py::test_restricted_env_removes_api_keys -x` | ❌ Wave 0 |
| V2-CODE-01 | import 边界 CI gate | unit | `pytest tests/code/test_import_boundary.py -x` | ❌ Wave 0 |

### 完整 12+ 测试清单

**`tests/code/test_import_boundary.py`** — CI lint gate pytest 层（D-18）
- `test_openevolve_import_only_in_adapter`：pathlib.Path 遍历 `evolution/` 下所有 `.py` 文件，正则匹配 `^import openevolve|^from openevolve`，断言仅在 `code_evolver_adapter.py` 中出现。不 import openevolve 本身，允许在未安装 openevolve 的 CI 环境通过。

**`tests/code/test_code_target_loader.py`** — CodeTarget + AST 测试发现（D-06/D-08）
- `test_find_target_by_relative_path`：mock hermes-agent 路径，验证 `find_target("tools/ansi_strip.py")` 返回正确 CodeTarget
- `test_ast_parse_discovers_30_tests`：读真实 test_ansi_strip.py，验证 find_target_tests 发现 30 个 test function
- `test_stratified_split_respects_buckets`：验证 20/10 split 每桶至少 1 个
- `test_loader_rejects_evolution_path`：传入 `evolution/core/config.py` 路径应 raise ValueError（防 recursive self-evolution）

**`tests/code/test_code_fitness.py`** — 三段评分（D-11/D-12/D-13）
- `test_pytest_pass_gives_score_1`：mock subprocess 返回 exit 0，验证 pytest_score=1.0
- `test_pytest_fail_gives_zero_and_reject`：mock subprocess 返回 exit 1 + FAILED 行，验证 composite=0，decision="reject"
- `test_size_within_1_2x_gives_partial_score`：size_evolved = baseline × 1.15，验证 0.7 < size_component < 1.0
- `test_size_over_1_5x_rejects`：size_evolved = baseline × 1.6，验证 decision="reject", reject_reason 含 "size_oversize"
- `test_ruff_zero_violations_gives_1`：mock ruff 返回 `[]` JSON，验证 ruff_score=1.0
- `test_ruff_3_violations_gives_0_4`：mock ruff 返回 3 条 violation，验证 ruff_score=0.4

**`tests/code/test_sandbox_runner.py`** — subprocess 沙箱（D-09/D-20）
- `test_restricted_env_removes_api_keys`：传入含 `OPENAI_API_KEY` 的 env，验证 `build_restricted_env()` 输出不含该 key
- `test_sandbox_timeout_returns_zero_fitness`：mock subprocess 抛 TimeoutExpired，验证返回 `(0, -1, [{"test_name": "timeout", ...}])`
- `test_eval_dir_is_cleaned_after_run`：eval_dir 路径在 run 后 `not eval_dir.exists()`
- `test_candidate_with_implicit_hermes_import_fails_cleanly`：写一个含 `import hermes` 的 candidate，验证 pytest 失败且 reject_reason 含 "pytest_fail"（不 crash sandbox）

**`tests/code/test_evolve_code_cli.py`** — 端到端 dry-run + CLI（D-21 整合）
- `test_dry_run_exits_0_without_openevolve_call`：mock `code_evolver_adapter.evolve`，`--dry-run` flag 下不调用 evolve，返回 0
- `test_preflight_fails_without_license`：mock `LICENSE` 不存在，pre-flight 返回 SystemExit(1)
- `test_cli_passes_model_to_evolution_config`：`--model qwen-plus` 正确传入 EvolutionConfig

**`tests/code/test_ansi_strip_holdout.py`** — 5-10 edge case holdout（D-07，evolution 仓内）
- `test_extreme_long_input_10k_chars`：10K chars 随机文本混入 CSI 序列，验证全部剥离
- `test_unicode_boundary_in_escape`：`\x1b[42m中文\x1b[0m` 验证中文字符完整保留
- `test_nested_escape_sequences`：嵌套/重叠转义
- `test_empty_string`：`strip_ansi("") == ""`
- `test_single_char`：`strip_ansi("a") == "a"`
- `test_truncated_csi_at_eof`：`\x1b[31` 无终止字节
- `test_unknown_osc_command`：`\x1b]99;unknown\x07`
- `test_mixed_invalid_bytes`：`\x80\x81\x82` 孤立 C1 控制字节
- `test_crlf_inside_escape`：`\x1b[0m\r\n` 换行保留

### Sampling Rate

- **Per task commit:** `pytest tests/code/ -x -q`（< 2s，无 LLM 调用）
- **Per wave merge:** `pytest tests/ -q`（全套，含 fixture 加载）
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/code/__init__.py` — 空文件
- [ ] `tests/code/test_import_boundary.py` — covers D-18 grep gate
- [ ] `tests/code/test_code_target_loader.py` — covers D-06/D-08
- [ ] `tests/code/test_code_fitness.py` — covers D-11/D-12/D-13（6 个路径）
- [ ] `tests/code/test_sandbox_runner.py` — covers D-09/D-20（包含 timeout 注入 + import 防御）
- [ ] `tests/code/test_evolve_code_cli.py` — covers E2E dry-run
- [ ] `tests/code/test_ansi_strip_holdout.py` — covers D-07 edge case
- [ ] ruff 安装：`pip install -e ".[dev]"` — Wave 0 加 ruff 到 dev extra 后执行

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | 否 | N/A（no user auth）|
| V3 Session Management | 否 | N/A |
| V4 Access Control | 是（hermes-agent read-only）| output-only 策略 + white-list component paths |
| V5 Input Validation | 是（LLM generated code） | sandbox_runner subprocess + restricted_env + timeout |
| V6 Cryptography | 否 | N/A（不存储加密数据）|

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM 生成的 candidate 代码意外删除文件 | Tampering | subprocess + restricted_env + eval_dir 隔离（D-20）；PYTHONPATH 限制 |
| LLM 生成的 candidate 通过 env var 泄漏 API key | Information Disclosure | restricted_env 删去所有 API key env vars（D-20）|
| 恶意 component 路径（如 `../../etc/passwd`）| Elevation of Privilege | code_target_loader 白名单校验（reject `evolution/` + `agent/redact.py` 等路径）|
| openevolve subprocess evaluator 访问真实 hermes-agent | Tampering | `HERMES_AGENT_REPO=eval_dir` 在 restricted_env 中覆盖为 eval_dir |
| NOTICE.md 写入含 API key 的 LLM 反思内容 | Information Disclosure | `_contains_secret` 过滤（evolution/core/external_importers.py SECRET_PATTERNS）|

---

## Sources

### Primary (HIGH confidence)

- [VERIFIED: venv pip install + source read] openevolve 0.2.27 — API surface（`__init__.py`、`api.py`、`config.py`、`llm/openai.py`、`evaluator.py`）全部验证
- [VERIFIED: wc -c + pytest 实测] hermes-agent ansi_strip.py — 1784 bytes，44 行，30 tests，隔离 dir 全过
- [VERIFIED: find/grep] pyproject.toml `[darwinian]` extra 存在，`.gitignore` output/ 已含，`.pre-commit-config.yaml` 不存在，`LICENSE` 不存在，ruff config 不存在
- [VERIFIED: ruff check --output-format=json] ruff JSON 输出格式已确认（code / message / location / severity）

### Secondary (MEDIUM confidence)

- [CITED: evolution/benchmarks/tblite_runner.py] subprocess + Popen + state monitor 模式直接复用
- [CITED: evolution/benchmarks/benchmark_gate.py] `score_candidate` 接口形状参考
- [CITED: evolution/core/config.py] EvolutionConfig.load 三层配置链，Phase 21 新增字段沿用同模式
- [CITED: evolution/tools/evolve_tool_descriptions.py] Click CLI 三件套模板
- [CITED: .planning/phases/21-darwinian-code-evolution/21-CONTEXT.md] 全部 21 条锁定决策

### Tertiary (LOW confidence)

- 无（所有关键声明均已验证或引用官方源）

---

## Metadata

**Confidence breakdown:**

- openevolve API surface: HIGH — venv 内实测 + 源码阅读
- ansi_strip.py 隔离可行性: HIGH — 本地运行 30 tests 通过
- ruff JSON 格式: HIGH — 本地运行验证
- size penalty 阈值建议: MEDIUM — 基于字节数计算 + 工程经验
- openevolve PoC 参数推荐值: MEDIUM — 基于 config.py 默认值 + 成本推断（pop_size=50 vs 默认 1000）

**Research date:** 2026-05-20
**Valid until:** 2026-06-20（openevolve 活跃开发中，30 天内建议重新检查版本）

---

## RESEARCH COMPLETE

**Phase:** 21 - Darwinian Code Evolution
**Confidence:** HIGH

### Key Findings

- **openevolve API 完全兼容 EvolutionConfig**：`LLMModelConfig.api_base` 直接对应 `api_base`，通过 `openai.OpenAI(base_url=api_base)` 实现，无需 monkey-patch。D-04 Risk Anchor 已消解。
- **ansi_strip.py 隔离运行已验证**：只需复制 `tools/__init__.py` + `tools/ansi_strip.py` + `test_ansi_strip.py`，30 个 pytest 0.09s 全过，无 hermes conftest 依赖。D-09 Risk Anchor 已消解。
- **基础设施缺口明确**：`LICENSE`（不可逆）、`.pre-commit-config.yaml`、ruff、`pyproject.toml [code]` extra 是 Wave 0 必须前置的 4 项。
- **openevolve evaluator 必须是 self-contained Python 文件**：adapter 需动态生成 evaluator .py，将 eval_dir / baseline_size 写为 module-level constants。
- **size penalty ×1.2 偏紧建议放宽到 ×1.3**：ansi_strip.py baseline 1784 bytes，×1.2 = 2140 bytes 仅 ~9 行增量空间，轻微文档改进就会触发软惩罚；×1.3 = 2319 bytes 更合理。

### File Created

`.planning/phases/21-darwinian-code-evolution/21-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| openevolve API Surface | HIGH | venv 内安装 + 源码全读 |
| sandbox 可行性 | HIGH | 本地实测 30 tests 通过 |
| fitness 设计 | HIGH | D-11..D-15 已锁定，ruff 格式已验证 |
| PoC 进化参数 | MEDIUM | 基于 config defaults 推断，未实跑完整 evolution loop |
| ruff config 影响 | MEDIUM | 最小 E,F,W 配置足够，细分规则未穷举 |

### Open Questions

- pytest-json-report 是否值得加入 dev deps（推荐：不加，解析 `--tb=line` stdout 已够）
- evolution marker 粒度（建议只包裹 `strip_ansi` 函数体）
- `--allow-fallback` 最终降级路径（本期 CLI 占位，不实做）

### Ready for Planning

Research complete. Planner 可基于本 RESEARCH.md 创建 PLAN.md。Wave 0 必须完成 4 项基础设施（LICENSE / .pre-commit-config.yaml / pyproject.toml code extra + ruff / tests/code/ 目录初始化）再进 Wave 1 代码开发。
