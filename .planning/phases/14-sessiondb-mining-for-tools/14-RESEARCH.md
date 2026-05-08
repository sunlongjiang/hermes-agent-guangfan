# Phase 14: SessionDB Mining for Tools — Research

**Researched:** 2026-05-08
**Domain:** Hermes session JSON 离线挖矿 + LLM judge + 数据集 union/dedup/duplication（read-only pipeline）
**Confidence:** HIGH（CONTEXT 已锁 18 个决策；本次研究只验证落地路径与边角）

## Summary

Phase 14 的实现风险**不在算法层**，而在三类边界：(1) hermes session JSON 的真实 schema 与 CONTEXT.md `<canonical_refs>` §Session 数据格式参考的描述一致，但有未列出的字段（`reasoning`、`reasoning_details`、`tool_call_id`、`call_id`、`response_item_id`），candidate 抽取必须容错；(2) LLM judge 沿用 `ToolFactualChecker` / `ParamConsistencyChecker` 的 inner Signature + `_parse_bool` 模式即可，但 D-04 user_correction 的"LLM 二判"是新加的额外调用面，需要并入 cost 估算；(3) 数据通路存在三处现成的"小坑"：`ToolSelectionDataset.load`（`tool_dataset.py:122-127`）目前**仍是单行 abort**，D-18 必须 patch 这一处而不是只 patch session_miner 自己的 reader；secret patterns 扩展点（`external_importers.py:45-70 + 78-80`）已经在 v1 importers 路径上 in-use，扩展时必须确保 `HermesSessionImporter` 现有用户/助手抽取行为不回归；Phase 13 cost cap 模式（`cost_tracker.py` + `_CostStopper`）虽不强制启用，但 `metrics.json` 字段命名（`cost_usd_spent`、`judge_calls`）应预留以与 Phase 16 dashboard 对齐。

**Primary recommendation:** session_miner 走"三路 extractor → 候选合并按 `sha256(normalized task)[:16]` key 去重 union → 单一 LLM judge 批次（每候选一次 dspy.Predict + `_parse_bool` 解析）→ surface drift 名字过滤 → split-then-duplicate → JSONL 写出 + 容错 reader"的线性管线。所有 LLM 解析路径走 DSPy 类型化 OutputField + 异常包装（同 `ParamConsistencyChecker.check` lines 248-262 的 `try/except → ConstraintResult.passed=False` 模式），不允许任何 candidate 因为 JSON parse 失败被静默接受。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Session JSON 读取与三路 candidate 抽取 | session_miner（新文件） | — | `~/.hermes/sessions/` 是磁盘 I/O 层；与现有 `HermesSessionImporter` 解耦（CONTEXT D-10） |
| LLM judge（confirm_misselection / verdict） | session_miner inner Signature + dspy.LM | EvolutionConfig.judge_model | 与 `ToolFactualChecker` (`tool_constraints.py:32-112`) / `ParamConsistencyChecker` (`tool_constraints.py:152-307`) 同层同风格 |
| 工具表面对照（surface drift） | session_miner.mine() 入口 | tool_loader.extract_tool_descriptions | 现存工具来源唯一 |
| 数据集 union + dedup（synthetic+session） | evolve_tool_descriptions / evolve_tool_params 启动期（新加的 `--session-source` 加载分支） | ToolSelectionDataset | 不下沉到 ToolSelectionDataset（CONTEXT D-09 union 在 CLI 层而非数据类层） |
| Sample duplication（仅 train） | session_miner 写出阶段（写 train.jsonl 之前在内存中复制） | — | CONTEXT D-11："复制仅在 train 切分发生" |
| Hash splitting（70/85 桶） | session_miner 工具函数 | — | 新增私有 `_normalize_task_hash` + `_hash_to_split` |
| Privacy gate Layer 1 | `external_importers.SECRET_PATTERNS` + `_contains_secret`（D-15 扩展现有路径） | session_miner candidate 过滤 | 复用 v1 入口；不在 session_miner 复制一份 |
| Privacy gate Layer 3 | `mine_tool_sessions.py` CLI flag `--i-have-consent` | — | 信任已审过的 JSONL 输出；evolve CLI `--session-source` 不重复检查 |
| JSONL 容错读 | 新增 `_load_jsonl_skip_bad` helper（最小子集，CONTEXT D-18） | session_miner write + evolve --session-source load | EvalDataset/GoldenDatasetLoader 不动 |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-V2-01 | SessionDB-mined misselection patterns as high-value training data | (1) 三路 candidate 抽取来自 session JSON 实测格式确认（§Pitfalls 1）；(2) LLM judge 风格沿用现有 ToolFactualChecker/ParamConsistencyChecker 模板（§Analog Code）；(3) 加权机制走 sample 复制而非 metric 修改（§Architectural Responsibility Map）；(4) 与现有 evolve_tool_descriptions/evolve_tool_params 集成路径在 §Integration Points 给出 |

## Project Constraints (from CLAUDE.md)

- **Python ≥3.10**：本研究推荐用 `list[ToolSelectionExample]` / `dict[str, int]` 等现代类型注解，与现有 `tool_dataset.py:48-53` 一致
- **Snake_case + 私有下划线前缀**：`_extract_error_retry`, `_extract_user_correction`, `_extract_oracle_disagreement`, `_normalize_task_hash`, `_load_jsonl_skip_bad`, `_shannon_entropy`
- **Dataclass + `@dataclass`**：candidate 中间结构若需要持久化（miner_log.jsonl），用 `@dataclass` + `to_dict`，与 `ToolSelectionExample.to_dict` 同模式
- **Rich console**：所有 CLI 输出走模块级 `console = Console()`，复用 `evolve_tool_params.py:99` 的模式；不要 print()
- **不引入新依赖**：本 phase 用 stdlib `hashlib`/`re`/`json`/`math`（Shannon 熵）+ dspy + click + rich，**全部已在依赖中**
- **GSD 工作流强制**：开发要走 `/gsd-execute-phase`；研究产物直接被 planner 消费，不需要 commit hooks 介入
- **hermes-agent 只读**：CONCERNS §M6；本 phase 完全不调用 `tool_loader.write_back_description` —— planner 必须在 PLAN 中显式 scope guard（参考 `evolve_tool_params.py:36-38` 的脚注）

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | >=3.0.0 | inner Signature 类 + dspy.Predict + dspy.LM 用作 LLM judge / user_correction 二判 | [VERIFIED] CONTEXT D-06 显式要求与 ToolFactualChecker 风格对齐；codebase 已统一此模式 |
| click | >=8.0 | mine_tool_sessions 主 CLI + evolve_tool_descriptions/params 的 `--session-source` flag | [VERIFIED] 现有 evolve_tool_descriptions.py:400-407 / evolve_tool_params.py:509-540 均用 click.option |
| rich | >=13.0 | Console + Table + Progress（CLI 输出 + miner 进度） | [VERIFIED] tool_dataset.py:22, evolve_tool_params.py:57 全部使用 |
| stdlib `hashlib` | (stdlib) | sha256 正规化 hash 用于 train/val/holdout 桶 | [VERIFIED] CONTEXT D-13 / specifics 显式要求 |
| stdlib `re` | (stdlib) | Shannon 熵 token 切分 + JWT/AWS 正则 + collapse_whitespace | [VERIFIED] external_importers.py:25 已 import |
| stdlib `math` | (stdlib) | Shannon 熵计算（`math.log2`） | [VERIFIED] 标准做法 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (无新增) | — | — | CONTEXT 明确"不引入新依赖"，且当前栈足够覆盖范围 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 内部 dspy.Signature inner class | dspy.ChainOfThought 顶层 module | 顶层 module 在仓库中无先例；inner class 是 ToolFactualChecker / ParamConsistencyChecker / SyntheticDatasetBuilder.* 三处统一模式 |
| Shannon 熵手动实现 | `scipy.stats.entropy` / `numpy` | 引入 scipy / numpy 违反 "不引入新依赖" 约束（约 ~30 行 stdlib 实现即可） |
| 共用 EvalDataset.load 容错路径 | 修改 dataset_builder.py:62-75 | CONTEXT D-18 显式禁止改动 EvalDataset/GoldenDatasetLoader（v2-STAB-01 独立做） |
| 串行 LLM judge | ThreadPoolExecutor 并发 | CONTEXT 已标 "默认串行；如发现慢可加 ThreadPool"（Claude's Discretion）— 默认串行，量化结果出来再决策 |

**Installation:** 无新增（验证：`grep -r "import scipy\|import numpy" evolution/` 应返回空）

**Version verification:**
```bash
# 验证 dspy 版本未漂移（H1/M2 风险面）
.venv/bin/python -c "import dspy; print(dspy.__version__)"
# 期望 >= 3.0.0；如 >= 3.2.x 则 reflection_lm 可能 API 变化（M2 silent fallback）
# 本 phase 不触发 GEPA，所以版本风险只影响 dspy.Predict / dspy.LM —— 这两个 API 稳定
```

## Architecture Patterns

### System Architecture Diagram

```
~/.hermes/sessions/*.json (44 个文件，~70KB-300KB/份)
        │
        ▼
┌──────────────────────── mine_tool_sessions CLI ─────────────────────────┐
│  --i-have-consent (强制) / --sessions-dir / --signals / --baseline-module│
│  --judge-model / --misselection-multiplier / --output / --dry-run        │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  SessionToolMiner.mine()    │
                    │  (新文件 session_miner.py)  │
                    └──────────────┬──────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
  ┌────────────┐           ┌──────────────┐           ┌──────────────────┐
  │_extract_   │           │_extract_user_│           │_extract_oracle_  │
  │error_retry │           │correction    │           │disagreement      │
  │(B 信号)    │           │(A 信号: 关键  │           │(C 信号: 加载     │
  │            │           │ 词→LLM 二判)  │           │ baseline ToolMod)│
  └─────┬──────┘           └───────┬──────┘           └────────┬─────────┘
        │                          │                          │
        └────────── candidates: list[Candidate] ───────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │  surface drift filter: drop if name not in current  │
        │  hermes-agent extract_tool_descriptions() 名字集合  │
        └──────────────────────────┬──────────────────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │  privacy gate: _contains_secret(text) (扩展后)       │
        │  → 命中即丢弃 + secret_filter_skipped++              │
        └──────────────────────────┬──────────────────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │  LLM judge (ConfirmMisselection Signature):         │
        │  per-candidate dspy.Predict + _parse_bool +         │
        │  try/except → fail-closed (false_positive)          │
        │  verdict ∈ {confirm_misselection, false_positive}   │
        └──────────────────────────┬──────────────────────────┘
                                   │
                        confirm_misselection only
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │  hash bucket: int(sha256(normalized_task)[:8],16)%  │
        │  100 → train (<70) / val (<85) / holdout (else)     │
        │  同 hash 跨 candidates union signals (D-02 max 复制) │
        └──────────────────────────┬──────────────────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │  duplicate (仅 train):                              │
        │  multiplier = max(per-signal-mult)                  │
        │  → train.jsonl 写入时同例 N×                         │
        └──────────────────────────┬──────────────────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │  output/<ts>/{train,val,holdout}.jsonl              │
        │           + metrics.json + miner_log.jsonl          │
        └──────────────────────────────────────────────────────┘
                                   │
        ────────────── 后续：evolve_tool_descriptions/params ───
                                   │
                          --session-source <path>
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │  _load_jsonl_skip_bad (CONTEXT D-18)                 │
        │  → ToolSelectionDataset.train/val/holdout            │
        │  → 与 ToolDatasetBuilder synthetic dataset union     │
        │  → 同 hash → session 优先 (D-14)                     │
        │  → 进 GEPA / 优化（已存在路径不变）                   │
        └──────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
evolution/tools/
├── session_miner.py             # 新增：SessionToolMiner + 3 extractor + ConfirmMisselection
├── mine_tool_sessions.py        # 新增：Click CLI（独立 entry point）
├── evolve_tool_descriptions.py  # 修改：加 --session-source flag + load+union 分支
├── evolve_tool_params.py        # 修改：加 --session-source flag + load+union 分支
├── tool_dataset.py              # 修改：ToolSelectionExample 加 misselection_signals 字段
├── tool_loader.py               # 不动（read 接口 extract_tool_descriptions 已就绪）
├── tool_module.py               # 不动
├── tool_constraints.py          # 不动（ConfirmMisselection 不放这里——是 mining-time judge，不是 constraint gate）
└── ...

evolution/core/
├── external_importers.py        # 修改：SECRET_PATTERNS 扩展 + 新增 _shannon_entropy
└── (其他不动)

tests/tools/                     # Wave 0 测试位
├── test_session_miner.py        # 新增（单元层）
├── test_session_signal_extract.py # 新增（B/A/C 三 extractor）
├── test_session_judge.py        # 新增（ConfirmMisselection round-trip + mock_lm）
├── test_session_split.py        # 新增（hash bucket 边界 + dedup union）
├── test_secret_patterns_v2.py   # 新增（JWT/AWS/熵 + 不回归 v1 行为）
├── test_jsonl_skip_bad.py       # 新增（D-18 容错）
├── test_surface_drift.py        # 新增（drop + report）
├── test_mine_cli.py             # 新增（CLI flag + dry-run）
└── test_evolve_with_session_source.py # 新增（--session-source union）

tests/fixtures/sessions/         # 新增 fixture 目录
├── error_retry_b.json           # B 信号典型场景
├── user_correction_a.json       # A 信号
├── oracle_disagreement_c.json   # C 信号
├── malformed_msg.json           # 旧版/破损消息（pitfall 5）
└── multi_signal.json            # 多源命中 → max multiplier
```

### Pattern 1: Inner Signature + dspy.ChainOfThought + try/except → fail-closed

**What:** mining-time LLM 调用的统一封装，与 `ToolFactualChecker` / `ParamConsistencyChecker` 完全对齐
**When to use:** ConfirmMisselection（D-04）+ user_correction LLM 二判（specifics）

**Example (replicate from `tool_constraints.py:180-262`):**
```python
class ConfirmMisselection(dspy.Signature):
    """Decide whether `originally_used_tool` was a misselection given the
    downstream context that followed the call.

    Respond strictly with verdict (confirm_misselection|false_positive),
    correct_tool (must be one of the names in available_tools_summary),
    and a one-sentence rationale. When uncertain, prefer false_positive.
    """
    task_description: str = dspy.InputField(desc="...")
    available_tools_summary: str = dspy.InputField(desc="newline list of name+desc+param schema")
    originally_used_tool: str = dspy.InputField(desc="...")
    signal_source: str = dspy.InputField(desc="error_retry|user_correction|oracle_disagreement")
    downstream_context: str = dspy.InputField(desc="next 1-3 turns after the tool call")
    verdict: str = dspy.OutputField(desc="confirm_misselection or false_positive; default false_positive")
    correct_tool: str = dspy.OutputField(desc="one tool name from available_tools_summary")
    rationale: str = dspy.OutputField(desc="one sentence")

# Per-candidate call, mirrors ParamConsistencyChecker.check at tool_constraints.py:222-262
lm = dspy.LM(self.config.judge_model, **self.config.get_lm_kwargs())
try:
    with dspy.context(lm=lm):
        result = self.judge(
            task_description=cand.task,
            available_tools_summary=cand.tools_summary,
            originally_used_tool=cand.original_tool,
            signal_source=cand.signal,
            downstream_context=cand.context,
        )
except Exception as e:
    # Conservative: any LM/parse failure -> false_positive (drop candidate).
    return Verdict(label="false_positive", correct_tool="", rationale=f"judge_error: {e}")

verdict_label = (str(result.verdict).strip().lower() or "false_positive")
if verdict_label not in ("confirm_misselection", "false_positive"):
    verdict_label = "false_positive"  # fail-closed unknown verdicts (M4)
```

### Pattern 2: Hash-bucket task split (replicate Phase 4 ratio semantics with deterministic key)

**What:** sha256(normalized_task)[:8] mod 100 → split bucket（CONTEXT D-13）
**When to use:** `_extract_*` 之后、复制之前

```python
import hashlib, re

def _normalize_task_hash(task: str) -> str:
    """sha256 of strip+lower+collapse_whitespace, hex-truncated to 16."""
    norm = re.sub(r"\s+", " ", (task or "").lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]

def _hash_to_split(h: str) -> str:
    """Bucket per CONTEXT D-13: <70 train / <85 val / else holdout."""
    bucket = int(h[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "val"
    return "holdout"
```

### Pattern 3: JSONL bad-line skip helper (CONTEXT D-18 minimal subset)

**What:** 行级 try/except json.JSONDecodeError + 计数 + 5% 阈值 warn
**When to use:** session_miner 写出 + evolve_* `--session-source` 加载（**不**在 EvalDataset/GoldenDatasetLoader）

```python
import json
from rich.console import Console
console = Console()

def _load_jsonl_skip_bad(path: Path) -> tuple[list[dict], int]:
    """Read JSONL line-by-line; return (rows, skipped_count).

    Mirrors external_importers.py:185-188 pattern (which already does this
    for ClaudeCodeImporter — D-18 is bringing dataset loaders to parity).
    """
    rows: list[dict] = []
    skipped = 0
    if not path.exists():
        return rows, 0
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    total = len(rows) + skipped
    if total and skipped / total > 0.05:
        console.print(
            f"[yellow]⚠ {path.name}: skipped {skipped}/{total} bad JSONL "
            f"lines ({skipped/total*100:.1f}%)[/yellow]"
        )
    return rows, skipped
```

### Pattern 4: Per-candidate sample duplication (CONTEXT D-11)

**What:** 仅复制到 train.jsonl，按 misselection_signals union 后取 max(multiplier)
**When to use:** split bucket 落定后、写文件之前

```python
DEFAULT_MULTIPLIER = {"error_retry": 3, "user_correction": 3, "oracle_disagreement": 2}

def _multiplier_for(signals: list[str], override: dict[str, int]) -> int:
    """max over hit signals; default 1 if no signals match."""
    hits = [override.get(s, DEFAULT_MULTIPLIER[s]) for s in signals if s in DEFAULT_MULTIPLIER]
    return max(hits) if hits else 1

# train 写入：
for ex in train_examples:
    n = _multiplier_for(ex.misselection_signals, multiplier_override)
    for _ in range(n):
        f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")
```

### Anti-Patterns to Avoid

- **不要在 metric 层加权**：CONTEXT D-11 / Phase 13 deferred 显式选择"样本复制"而非 metric 乘权——避免改 metric/schema，metric 接口稳定是 GEPA 5-param 签名约束的（CONCERNS §H1/M2）。
- **不要扩展 EvalDataset.load / GoldenDatasetLoader 的 try/except**：CONTEXT D-18 把这两处明确划给 v2-STAB-01；本 phase 越界改动会引发 plan-checker 拒收。
- **不要在 evolve_tool_descriptions / evolve_tool_params 里复制 mining 逻辑**：`--session-source` 只读已生成的 JSONL，**不**触发 mining；mining 仅由 mine_tool_sessions 单一入口完成（D-09/D-16 边界）。
- **不要把 ConfirmMisselection 放在 tool_constraints.py**：这是 mining-time judge，不是部署门禁；放 session_miner.py 的 inner class，与 SyntheticDatasetBuilder 内部 Signatures 一致（`tool_dataset.py:164-205`）。
- **不要假设 tool 消息 content 是合法 JSON**：实测 16/16 是合法 JSON，但 CONTEXT specifics 已嘱"解析失败也算成功（保守）"——B 信号识别要兼容 raw string 中含 `error` / `Error` / `Exception` 关键字（pitfall 1）。
- **不要把 oracle 信号 candidate 直接当成 misselection 入库**：D-04 末："所有 candidate（含 verdict=false_positive）一并送 LLM judge；只有 confirm_misselection 才进数据集"——C 信号也必须过 judge，不允许走捷径。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM JSON output 解析 | 自己写 brace-counting / 手 split | `dspy.OutputField(desc=..., type=bool)` + `_parse_bool` (`tool_constraints.py:15-29`) | DSPy 3.x 类型化 OutputField 已内置；CONCERNS §M4 警告自实现易脆 |
| Bool 解析（verdict / has_false_claims 风格） | `text == "true"` | `_parse_bool` from `tool_constraints.py:15` | "unknown → False" 是仓库统一约定（fail-closed） |
| Train/val/holdout split | 自己 random.shuffle + 切片 | `_normalize_task_hash` + `_hash_to_split`（本研究 Pattern 2） | 必须可重现且按 task 去重——random 不满足 |
| sha256 hash | 手写 hex 切片 | `hashlib.sha256(...).hexdigest()[:16]` | stdlib，CONTEXT specifics 显式指定切片长度 |
| Shannon 熵 | 自己写 prob 表 | 标准做法：`-Σ p_i * log2(p_i)`（~30 行 stdlib，math.log2） | scipy/numpy 是新依赖；本仓库无先例 |
| Tool 消息 content JSON 解析 | 自己 split 字符串 | `json.loads(content)` + try/except，参考 `external_importers.py:185-188` 处理风格 | 已有保守 fallback 模式 |
| Session 文件遍历 | os.walk + glob 混用 | `Path.home() / ".hermes" / "sessions"` + `.glob("*.json")`（与 `HermesSessionImporter.SESSION_DIR` 同源） | 现有路径已 verify |
| CLI cost 估算 dry-run | 手写 token 计数 | dry-run 仅按 `len(candidates) * 平均 token` 输出粗估（不调真实 LLM） | CONTEXT specifics 显式：dry-run 不消耗 API 配额 |

**Key insight:** 本 phase 90% 是"组合既有零件"——LLM judge = ToolFactualChecker 模板；JSONL 加载 = ClaudeCodeImporter 模板；CLI 三件套 = evolve_tool_descriptions 模板；secret detect = SECRET_PATTERNS 已 in-use。**新代码主要是 3 个 extractor 的 session 解析逻辑 + 1 个 hash-bucket 工具函数 + 1 个 Shannon 熵函数**。其他都是 wiring。

## Common Pitfalls

### Pitfall 1: Session JSON schema 比 CONTEXT 列出的更复杂——必须容错抽取

**What goes wrong:**
CONTEXT canonical_refs §Session 数据格式参考列出 `messages: list[{role, content, tool_calls?, name?, tool_call_id?}]`，但实测 44 份 session 中 assistant 消息**还含** `reasoning`, `reasoning_details`, `finish_reason`；tool_call 含 `id`, `call_id`, `response_item_id`, `type`, `function: {name, arguments}`；tool 消息额外有 `tool_call_id`, `name` 字段。如果 extractor 用严格 schema 校验，新字段会让 v0.x 旧 session 文件被误判破损。

**实测样本（`/Users/slj/.hermes/sessions/session_20260411_141731_f8aff8.json`，27 messages）：**
```python
# assistant turn with tool_calls:
{
  "role": "assistant",
  "content": "好的，让我先看看当前目录的结构。",  # 注意：可与 tool_calls 共存
  "reasoning": "...",                            # 旧版本可能没有
  "finish_reason": "tool_use",
  "reasoning_details": {...},
  "tool_calls": [
    {
      "id": "toolu_bdrk_01YRfegnkf4PiiRaKGJ...",
      "call_id": "...",
      "response_item_id": "...",
      "type": "function",
      "function": {"name": "terminal", "arguments": '{"command": "pwd"}'}
    },
    {  # 同一 turn 多 tool_call 是常见的
      "id": "toolu_bdrk_017RMTgx7WLw7VtzBcr...",
      "function": {"name": "search_files", "arguments": '{"pattern": "*", "target": "files", "limit": 50}'}
    }
  ]
}

# tool message:
{
  "role": "tool",
  "content": '{"output": "/Users/slj/项目/...", "exit_code": 0, "error": null}',  # 总是 JSON 字符串
  "tool_call_id": "toolu_bdrk_01YRfegnkf4PiiRaKGJ..."
  # 注意：name 字段在实测 session 中是 None / 缺失，**不能依赖 name 反查工具名**
}
```

**Why it happens:** session schema 由 hermes-agent 各版本累积演化；旧 session（v0.5 之前）可能没有 `reasoning_details`；新 session（v0.7+）多了 `call_id`/`response_item_id`。

**How to avoid:**
- 仅依赖 **`role`** 分流 + **`tool_calls[*].function.name`**（不依赖顶层 `name`）+ **`tool_call_id`** 跨消息关联——这三组字段在所有 v0.x 实测里稳定
- 反查工具名走 `tool_call_id` map：`assistant.tool_calls[i].id == tool.tool_call_id`，**不用 tool.name**（实测为 None）
- 同一 assistant turn 多 tool_calls 时，每个 tool_call 各自当独立 candidate（D-04 不限制 1 turn = 1 candidate）

**Warning signs (early symptoms):**
- mining 出来的 originally_used_tool 出现 None / "" → 反查逻辑用错了字段
- candidate 数远低于 session 总数 × 平均 tool_call 数 → 可能在解析新版 reasoning_details 时 abort
- 同 session 不同消息抽出 candidate 数突然为 0 → 旧版本 schema 不兼容

### Pitfall 2: B 信号 "tool 报错" 必须容错三种表达

**What goes wrong:**
CONTEXT specifics 给出"tool 消息 content JSON-encoded → 查 `error` 字段或 `exit_code != 0`"，但实测 16 个 tool 消息里**只有 2 个 `with_error` / 2 个 `with_exit_code`**，且 `error: null` 也算"无错"——naive 解析会把 None / "null" / "" 都判成"有错"。

**实测：** `{"output": "...", "exit_code": 0, "error": null}` 是成功；`error: null` 不是错误信号。

**How to avoid:**
- B 信号判定函数 `_is_tool_error(parsed: dict | None, raw: str) -> bool`：
  ```python
  def _is_tool_error(parsed, raw):
      if isinstance(parsed, dict):
          # exit_code 优先：非零即错
          ec = parsed.get("exit_code")
          if isinstance(ec, int) and ec != 0:
              return True
          # error 字段：必须是 truthy 字符串（None / "" / "null" 不算）
          err = parsed.get("error")
          if isinstance(err, str) and err.strip() and err.strip().lower() != "null":
              return True
          return False
      # parse 失败 fallback：raw string 含 Exception/Error/Traceback 字眼
      return any(kw in raw for kw in ("Traceback", "Exception:", "Error:", '"error":'))
  ```
- 在测试 fixture 里至少覆盖：`exit_code=0,error=null`（成功）/ `exit_code=1`（错）/ `error="ENOENT: no such file"`（错）/ raw `Traceback...` 字符串（解析失败但是错）

**Warning signs:** B 信号 candidate 数 == tool 消息总数 → 判定过松；B 信号数远小于 visual inspection 看到的失败次数 → 判定过严。

### Pitfall 3: Same-task chunk 边界识别（B 信号 D-04）

**What goes wrong:**
"turn N+M 内同一 task chunk（user 消息切分边界内）改用不同工具完成"——但实测 session 通常**一个 user message 后跟 10+ assistant/tool 来回**才完成。M 设多大？怎么界定"完成"？

**实测：** session_20260411_141731_f8aff8 有 1 个 user + 10 assistant + 16 tool，全是同一个任务。

**How to avoid:**
- **task chunk 边界 = 下一个 `role=="user"` 消息**（最简单的 robust 定义；与 specifics 一致）
- chunk 内 "改用不同工具完成" = 后续任何 assistant tool_call 用了不同 `function.name` **且**该工具的 tool 消息**未报错**
- M 不设上限——chunk 内所有后续 tool_call 都参与对照
- candidate 抽取时只取**第一次错误后第一次成功**的工具切换；不递归抽多次

**Warning signs:** B 信号 candidate 数膨胀到 candidate / session > 5 → 没正确切分 chunk；同一 task 抽出多个相互冲突的 correct_tool → chunk 边界没收紧。

### Pitfall 4: Oracle (C) 信号 baseline-module artifact 加载——核对 Phase 5/13 实际 output 形态

**What goes wrong:**
CONTEXT D-07 + specifics："`--baseline-module <output-dir>` 指向已有 evolve 产物用作 oracle"。但 Phase 5 (`evolve_tool_descriptions.py:355-379`) 输出的是 `evolved_descriptions.json`（列表 of `{name, description}`），Phase 13 (`evolve_tool_params.py:1037-1057`) 输出 `evolved_descriptions.json`（列表 of `{name, description, params: [{name,type,required,description}]}`）——两者 schema 不同，没有 `best_toolmodule.pkl`。也没有公共 baseline 加载器。

**重要发现：** **Phase 5 的 metrics.json 不含 best_score 之外的可执行 ToolModule 状态**——意思是 oracle 重打分**必须**重建 ToolModule from `evolved_descriptions.json`。

**How to avoid:**
- 加一个 helper `_load_baseline_module(output_dir: Path) -> ToolModule`：
  ```python
  def _load_baseline_module(output_dir: Path) -> ToolModule:
      """Reconstruct a ToolModule from a Phase 5/13 output dir.

      Reads evolved_descriptions.json and combines with current hermes-agent
      tool list (param schema is frozen — only desc text comes from artifact).
      Falls back to current hermes-agent tools if file missing/malformed.
      """
      evolved_path = output_dir / "evolved_descriptions.json"
      if not evolved_path.exists():
          raise click.UsageError(f"--baseline-module {output_dir} missing evolved_descriptions.json")
      payload = json.loads(evolved_path.read_text())
      # Merge against current hermes-agent toolset (param schema is frozen).
      # If artifact is Phase 5 schema (no params), fall back to current params.
      desc_map = {item["name"]: item.get("description", "") for item in payload}
      current_tools = _load_tool_descriptions(config.hermes_agent_path)
      # 用 artifact 的 desc 覆写当前 tool list
      for t in current_tools:
          if t.name in desc_map:
              t.description = desc_map[t.name]
              # Phase 13 schema 含 params: 也覆写 params[i].description
              params_payload = next(
                  (item.get("params", []) for item in payload if item["name"] == t.name), []
              )
              pm = {p["name"]: p.get("description", "") for p in params_payload}
              for p in t.params:
                  if p.name in pm:
                      p.description = pm[p.name]
      return ToolModule(current_tools)
  ```
- C 信号重打分入口：直接 `module(task_description=task)`（与 holdout eval 同形式，参考 `evolve_tool_params.py:329-355`），取 `pred.selected_tool` 与 session 实际 `tool_calls[i].function.name` 比对

**Warning signs:** `--baseline-module` 路径 OK 但 candidate 数 == 0 → 多半是 schema mismatch 导致全 tool 重打分都 == session 用的工具，没分歧

### Pitfall 5: Sample duplication 时机错位会破坏 dedup 不变量

**What goes wrong:**
"复制仅在 train 切分发生"——如果在 hash bucket 之前复制，会把同一例子分到不同 split；如果在 evolve_tool_* 加载时再复制，CONTEXT D-11 + 12 的"miner 出 pre-duplicated dataset"语义就破了。

**How to avoid:** **铁律——`session_miner.mine()` 输出阶段，写 `train.jsonl` **之前**在 train list 内复制；val / holdout 一律保留 1 份。Evolve CLI 看到 train.jsonl 时已经是预复制好的，**不能**再加倍。

```python
# Correct ordering：
candidates → judge filter → hash bucket (per-task) → split(train/val/holdout) →
  for ex in train: write multiplier(ex) copies; for ex in val/holdout: write 1
```

**Warning signs:** train 例子数远超 unique-task 数 × 平均 multiplier → 重复加倍；holdout 出现重复 task → 复制泄漏到非 train 切分

### Pitfall 6: Privacy gate 扩展不能回归 v1 importers

**What goes wrong:**
D-15 在 `external_importers.py:45-70` 扩展 `SECRET_PATTERNS`、`_contains_secret` 加 Shannon 熵分支。但 `_contains_secret` 当前在 4 处被调用（ClaudeCodeImporter L193, CopilotImporter L297/319, HermesSessionImporter L389/403）——熵阈值 4.0 会把**正常的 32+ 字符 base64 token**（如 commit hash, UUID）误判，让现有 v1 importers 突然 drop 大量合法消息。

**实测：** 一个 Mac MD5 hash `5d41402abc4b2a76b9719d911017c592` 长度 32，熵 ≈ 3.95（边缘）；一个 SHA256 hex `a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3` 长度 64，熵 ≈ 4.20。一个真 JWT 可能熵 4.5+。阈值 4.0 会卡到 SHA256 + 真 secret。

**How to avoid:**
- Shannon 熵阈值要测：用 `tests/fixtures/sessions/` 里的真 user message + 一组已知 commit hash / UUID / SHA256 做 negative fixture；JWT、长 base64 secret 做 positive fixture；调阈值到能区分（CONTEXT 给 4.0，但这是建议值——开发期需 calibrate）
- 熵分支只对**长度 ≥24** 的 `[A-Za-z0-9_/+=-]+` token 生效（不打整段文本——避免散文 / 中文文本误中）
- v1 importers 行为不回归测试：`test_secret_patterns_v2.py` 必须包含 v1 测试集（`tests/test_external_importers.py` 现有用例）作为子集，**通过 = 现有正反例完全保留**

**Warning signs:** 跑完 mining 后 `secret_filter_skipped` 占比 > 20% → 熵阈值过严或 Layer 1 正则误中（注意 AWS-secret 的 `[A-Za-z0-9/+=]{32,}` 邻近模式不能太宽，否则 hash 全中）

### Pitfall 7: LLM judge cost 在 user_correction 路径会翻倍

**What goes wrong:**
CONTEXT specifics 给的 cost 估算 "44 sessions × ~20 candidate × ~2k token × $5/1M ≈ $9" 只算 ConfirmMisselection 一次 judge。但 D-04 user_correction extractor 还要"关键词列表预热召回，LLM 终审"——意思是 A 信号的 candidate 在送 ConfirmMisselection **之前**，已经过了一次 LLM 二判。两次叠加，A 信号路径 token 翻倍。

**估算修正：**
- 假设 candidate 分布 B:A:C ≈ 0.4:0.3:0.3（凭 specifics "44 sessions × 20 candidate" 和典型分布推测）
- A 信号额外二判：~0.3 × 20 × 44 × 1k token × $5/1M ≈ $1.3
- ConfirmMisselection：~$9（specifics 估算）
- 加总 ~$10.3；切到 `gpt-4.1-mini` 约 $1.7

**How to avoid:**
- 关键词预过滤要尽量收紧（specifics 给的关键词集已不错）——不要对**所有** assistant.tool_call 后的 user 消息无脑送 LLM 二判
- mine_tool_sessions CLI 加 `--judge-model` flag（D-07 已有）+ CLI 启动时打印估算的 candidate 数 × 估算 cost（dry-run 模式必出）
- metrics.json 字段 `judge_calls: int`（按 signal 分桶：`judge_calls_by_signal: dict[str, int]`），便于事后 audit
- 不强制 cost cap（CONTEXT canonical_refs 已声明"本 phase 不强制启用 cost_tracker"），但 metrics.json 字段命名要与 Phase 13 `cost_usd_spent` 对齐——为 Phase 16 dashboard 留 hook

**Warning signs:** mining 实际花 >$15 而 candidate 数 ~ 估算量 → user_correction 关键词召回率过高，需要收紧

### Pitfall 8: Surface drift 报告不能截断错关键信息

**What goes wrong:**
D-17 "整例丢弃 + 打印 dropped_count + dropped_tool_distribution"。但如果 `dropped_tool_distribution` 是个长 dict（同一 typo 的 100 个变体），CLI 表格会爆。Claude's Discretion 已经允许"截断 N 个"。

**How to avoid:** Rich Table 显示 top-10 by count；metrics.json 写完整 dict（无截断，方便事后过滤）；`surface_drift_tools` JSON 字段实际是 list of unique tool names, 用 dict 存按计数排好（dict 里键序 by Python 3.7+ insertion order = sorted by count desc）

### Pitfall 9: train/val/holdout 跨 candidates 同 hash 必须 union signals 而非生成多 example

**What goes wrong:**
CONTEXT D-02 末尾："同一 (normalized task hash, correct_tool) 被多路命中时 union 信号集合，**不去重多产 example**"。意思是：**1 个 task hash → 至多 1 个 ToolSelectionExample**（misselection_signals 是 list）。如果 extractor 各自产 example 然后简单 concat，会出 3 个不同 example 同 task。

**How to avoid:**
- mine() 末尾用 `dict[hash, ToolSelectionExample]` 做 reduce：相同 hash 进来时 `merge.misselection_signals = list(set(a.misselection_signals + b.misselection_signals))`，task/correct_tool/correct_params 取**第一次出现**或**主信号源**（建议优先级 oracle_disagreement > error_retry > user_correction，因为 oracle 用 ToolModule 出对照值最可信）
- `confuser_tools` 也 union（同 hash 跨信号源可能不同 originally_used_tool）
- 实现 helper：

```python
def _union_examples(by_hash: dict, ex: ToolSelectionExample, h: str):
    if h not in by_hash:
        by_hash[h] = ex
        return
    prev = by_hash[h]
    prev.misselection_signals = sorted(set(prev.misselection_signals) | set(ex.misselection_signals))
    prev.confuser_tools = sorted(set(prev.confuser_tools) | set(ex.confuser_tools))
```

### Pitfall 10: evolve CLI `--session-source` union 顺序不当导致 hash 冲突时 synthetic 错误占优

**What goes wrong:**
CONTEXT D-14："先各自 hash 去重，再两路 union；同 hash 例子 session 优先"。如果实现先 union 再 dedup，python dict 行为是后者覆盖前者——concat 顺序错了 session 会被 synthetic 覆盖。

**How to avoid:**
```python
# Correct (D-14):
synth_ds = ToolSelectionDataset.load(Path("datasets/tools"))
session_ds = ToolSelectionDataset(...)  # built from --session-source
for split in ("train", "val", "holdout"):
    by_hash: dict[str, ToolSelectionExample] = {}
    # 1. synthetic 先入：
    for ex in getattr(synth_ds, split):
        by_hash[_normalize_task_hash(ex.task_description)] = ex
    # 2. session 后入 → 同 hash 覆写：
    for ex in getattr(session_ds, split):
        by_hash[_normalize_task_hash(ex.task_description)] = ex
    # 注意：不再做 train 的 multiplier 复制——session_miner 已在 train.jsonl 预复制
    setattr(merged_ds, split, list(by_hash.values()))
```

**Warning signs:** session 例子的 misselection_signals 字段在 union 后变空 → 顺序倒了

## Code Examples

### Example 1: Inner Signature 模板（直接复制本仓库 `tool_constraints.py:180-216` 的风格）

```python
# Source: /Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_constraints.py:180-216
class ConsistencySignature(dspy.Signature):
    """Verify a tool's frozen top-level description and all evolved
    parameter descriptions are mutually consistent.

    ...
    """
    tool_name: str = dspy.InputField(desc="Name of the tool whose descriptions are being checked")
    frozen_tool_description: str = dspy.InputField(desc="The tool-level description (frozen ...)")
    evolved_param_descriptions: str = dspy.InputField(desc="JSON object mapping param_name to its description text")
    is_consistent: bool = dspy.OutputField(desc="True ONLY if ... When uncertain, prefer False.")
    explanation: str = dspy.OutputField(desc="If False: name the conflicting params...")
```

### Example 2: per-candidate LLM 调用 + try/except + _parse_bool（直接复制 `tool_constraints.py:222-281`）

```python
# Source: /Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_constraints.py:222-281
def check(self, tool_name: str, frozen_desc: str, param_descs: dict) -> ConstraintResult:
    import json as _json
    lm = dspy.LM(self.config.eval_model, **self.config.get_lm_kwargs())
    params_json = _json.dumps(param_descs or {}, ensure_ascii=False, sort_keys=True)
    try:
        with dspy.context(lm=lm):
            result = self.checker(...)
    except Exception as e:
        return ConstraintResult(passed=False, ..., details=str(e))
    is_consistent = _parse_bool(getattr(result, "is_consistent", None))  # unknown -> False
    explanation = str(getattr(result, "explanation", "") or "")
    if is_consistent:
        return ConstraintResult(passed=True, ...)
    return ConstraintResult(passed=False, ..., details=explanation or "...")
```

### Example 3: CLI 模板（复制 `evolve_tool_params.py:509-540` 的 click.option 序列）

```python
# Source: /Users/slj/项目/hermes-agent-self-evolution/evolution/tools/evolve_tool_params.py:509-540
@click.command()
@click.option("--iterations", default=10, type=int, help="...")  # mine_tool_sessions 不需要
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo (overrides HERMES_AGENT_REPO env var)")
@click.option("--dry-run", is_flag=True, help="Show setup + discovered count, no LLM calls")
@click.option("--model", default=None, help="Override all LLM model names")
@click.option("--api-base", default=None, help="Override API base URL")
# Phase 14 新增：
@click.option("--sessions-dir", default=None, type=click.Path(), help="Default ~/.hermes/sessions")
@click.option("--output", default=None, type=click.Path(), help="Default datasets/tools/sessions/<ts>/")
@click.option("--limit", default=0, type=int, help="0=all sessions")
@click.option("--i-have-consent", is_flag=True, help="REQUIRED — consents to read session data (Layer 3 privacy)")
@click.option("--signals", default="error_retry,user_correction,oracle_disagreement",
              help="Comma-separated subset")
@click.option("--baseline-module", default=None, type=click.Path(),
              help="Path to a Phase 5/13 output dir for oracle (C signal); omitted -> skip C")
@click.option("--judge-model", default=None, help="Default openai/gpt-4.1; falls back to config.judge_model")
@click.option("--misselection-multiplier", default=None,
              help='Override defaults, format "error_retry=3,user_correction=3,oracle_disagreement=2"')
def main(...):
    """Mine session transcripts for tool misselection patterns."""
    if not i_have_consent:
        click.echo("--i-have-consent is REQUIRED — refusing to read session data without consent", err=True)
        sys.exit(1)
    # ... rest of pipeline
```

### Example 4: ToolSelectionExample.to_dict / from_dict pattern（D-02 加字段后保持向后兼容）

```python
# Source: /Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_dataset.py:56-71
@dataclass
class ToolSelectionExample:
    task_description: str
    correct_tool: str
    correct_params: dict = field(default_factory=dict)
    difficulty: str = "medium"
    confuser_tools: list[str] = field(default_factory=list)
    reason: str = ""
    source: str = "synthetic"
    # Phase 14 新增（D-02）—— 旧 JSONL（无此字段）通过 from_dict 默认空 list 兼容
    misselection_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            ...
            "misselection_signals": self.misselection_signals,  # 新增
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolSelectionExample":
        # 现有实现已经做字段过滤 (line 71)：cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        # 旧 JSONL 没有 misselection_signals → 取 dataclass 默认值 []
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
```

## Runtime State Inventory

> Phase 14 主要是新增文件 + 扩展现有，**几乎没有 rename/refactor**。仅一处涉及修改既有数据契约（`ToolSelectionExample` 加字段，向后兼容）。

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `datasets/tools/{train,val,holdout}.jsonl` 现有 Phase 4 数据；新增 `datasets/tools/sessions/<ts>/` 目录（不冲突）。`ToolSelectionExample.from_dict` 已按 dataclass 字段过滤（`tool_dataset.py:71`），旧 JSONL 不需迁移 | 无数据迁移；新加 `misselection_signals=[]` 默认即兼容 |
| Live service config | None — 本 phase 不触及 hermes-agent 服务、CI/CD、Datadog | None — 验证：`grep -rn 'hermes-agent' .planning/phases/14*` 仅出现在 only-read 上下文 |
| OS-registered state | None — 没有定时任务、launchd、systemd 注册 | None |
| Secrets/env vars | `HERMES_AGENT_REPO`（read，不变）、`EVOLUTION_*` 系列（不变）、`OPENAI_API_KEY`/`OPENROUTER_API_KEY`（不变） | None — 不新增，CLI flag 走 `EvolutionConfig.load(model=..., api_base=...)` 既有路径 |
| Build artifacts | `output/tools/<ts>/` 现有 Phase 5/13 产物；新增 mining 产物路径 `datasets/tools/sessions/<ts>/` 与之**正交**（一个在 datasets，一个在 output） | 无；`.gitignore` 应已覆盖 `datasets/**/*.jsonl`（CONCERNS §H4 已 close）。建议 plan-checker 复查 `.gitignore` 包含 `datasets/tools/sessions/` |

## Common Pitfalls (Synthesis Across Pitfalls 1-10)

总结：本 phase 的核心风险在 **schema 容错** + **ordering correctness**：
- Schema：session JSON、tool 消息 content、artifact JSON 三个层面的版本兼容（Pitfalls 1, 2, 4）
- Ordering：candidate union 顺序、duplicate 时机、union session+synthetic 顺序、judge 调用顺序（Pitfalls 5, 9, 10）
- Cost / 安全：LLM judge 双调（Pitfall 7）、隐私 gate 不回归（Pitfall 6）、surface drift 不丢失审计信息（Pitfall 8）
- 边界：chunk 边界、test fixture 覆盖、metrics.json 字段命名一致性（Pitfall 3, 各 sample 错误）

## Analog Code（必复制的现有签名 + 行号）

| 复制对象 | 源文件 | 行号 | 用途 |
|---------|-------|------|------|
| `_parse_bool(value) -> bool` | `evolution/tools/tool_constraints.py` | 15-29 | LLM verdict / has_X bool 解析；fail-closed unknown |
| `class ToolFactualChecker` | `evolution/tools/tool_constraints.py` | 32-146 | inner Signature + ChainOfThought + check() / check_all() |
| `class ParamConsistencyChecker.check` | `evolution/tools/tool_constraints.py` | 222-281 | per-candidate LLM 调用 + try/except → ConstraintResult |
| `ToolSelectionExample` dataclass | `evolution/tools/tool_dataset.py` | 32-71 | D-02 加字段 + to_dict/from_dict 模板 |
| `ToolSelectionDataset.save / load` | `evolution/tools/tool_dataset.py` | 90-128 | D-08 输出 JSONL；D-18 在 load 处加 try/except（仅本 phase 新加 helper，不动这个类） |
| `ClaudeCodeImporter` jsonl skip 模式 | `evolution/core/external_importers.py` | 185-188 | D-18 `_load_jsonl_skip_bad` 的现成模板 |
| `SECRET_PATTERNS` + `_contains_secret` | `evolution/core/external_importers.py` | 45-70 + 78-80 | D-15 扩展点；新加 `_shannon_entropy` 辅助 |
| `HermesSessionImporter.SESSION_DIR` | `evolution/core/external_importers.py` | 346 | session_miner 使用同一默认路径 `Path.home() / ".hermes" / "sessions"` |
| `ToolModule.forward` | `evolution/tools/tool_module.py` | 162-184 | C 信号 oracle 重打分入口 — 直接 module(task_description=...) |
| `_evaluate_holdout` per-example loop | `evolution/tools/evolve_tool_params.py` | 300-383 | session_miner C 信号重打分循环可直接借用 try/except 风格 |
| Click CLI 三件套 | `evolution/tools/evolve_tool_descriptions.py` | 400-417 | mine_tool_sessions 主 CLI 模板（standard 4-flag + 自定义） |
| Phase 5 metrics.json 字段集 | `evolution/tools/evolve_tool_descriptions.py` | 365-378 | mining 输出的 metrics.json 字段命名对齐基准 |
| Phase 13 metrics.json 扩展集 | `evolution/tools/evolve_tool_params.py` | 829-856 | `cost_usd_spent`、`*_failures` 命名风格 |
| `_filter_tools` | `evolution/tools/evolve_tool_params.py` | 154-194 | mine_tool_sessions 的 `--signals` flag 解析风格（"逗号分隔 + 未知 warn + 空 abort"） |
| `pytest fixture mock_lm_with_usage` | `tests/conftest.py` | 7-38 | 所有 LLM judge 单元测试的 mock 工厂 |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 + pytest-asyncio >=0.21（仅有的异步路径）|
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest tests/tools/test_session_*.py -x --tb=short` |
| Full suite command | `.venv/bin/pytest tests/ -v` |

### Phase Requirements → Test Map

每行 = 一个验证单元；File Exists 列指明 Wave 0 是否需要新建测试文件。

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOOL-V2-01 | session JSON 解析容错（reasoning/reasoning_details/multi tool_calls/旧版 schema） | unit | `pytest tests/tools/test_session_signal_extract.py::test_parse_assistant_with_tool_calls -x` | ❌ Wave 0 |
| TOOL-V2-01 | B 信号 candidate 抽取（exit_code != 0 / error truthy / parse-fail fallback） | unit | `pytest tests/tools/test_session_signal_extract.py::test_b_error_retry -x` | ❌ Wave 0 |
| TOOL-V2-01 | A 信号 candidate 抽取（关键词匹配 + LLM 二判 mock） | unit | `pytest tests/tools/test_session_signal_extract.py::test_a_user_correction -x` | ❌ Wave 0 |
| TOOL-V2-01 | C 信号 candidate 抽取（baseline ToolModule mock + 名字不匹配 → candidate） | unit | `pytest tests/tools/test_session_signal_extract.py::test_c_oracle_disagreement -x` | ❌ Wave 0 |
| TOOL-V2-01 | ConfirmMisselection Signature round-trip：confirm/false_positive verdict 都被正确解析 | unit | `pytest tests/tools/test_session_judge.py::test_verdict_round_trip -x` | ❌ Wave 0 |
| TOOL-V2-01 | LLM judge try/except → false_positive（fail-closed） | unit | `pytest tests/tools/test_session_judge.py::test_lm_failure_drops_candidate -x` | ❌ Wave 0 |
| TOOL-V2-01 | hash bucket 边界：bucket 69→train, 70→val, 84→val, 85→holdout（构造 task 文本使 mod 100 == 69/70/84/85） | unit | `pytest tests/tools/test_session_split.py::test_hash_bucket_edges -x` | ❌ Wave 0 |
| TOOL-V2-01 | hash 是确定性：同一 task 反复 hash 进同一桶 | unit | `pytest tests/tools/test_session_split.py::test_hash_determinism -x` | ❌ Wave 0 |
| TOOL-V2-01 | normalized hash 抗大小写/空白漂移（"Read   FILE" == "read file"） | unit | `pytest tests/tools/test_session_split.py::test_normalize_robust -x` | ❌ Wave 0 |
| TOOL-V2-01 | 同一 hash 跨多信号源 → 1 个 example，misselection_signals union | unit | `pytest tests/tools/test_session_split.py::test_signals_union -x` | ❌ Wave 0 |
| TOOL-V2-01 | sample duplication 仅 train（val/holdout 1×） | unit | `pytest tests/tools/test_session_miner.py::test_duplicate_train_only -x` | ❌ Wave 0 |
| TOOL-V2-01 | duplication multiplier 取 max（多源命中不累乘） | unit | `pytest tests/tools/test_session_miner.py::test_multiplier_max -x` | ❌ Wave 0 |
| TOOL-V2-01 | secret patterns v2: JWT positive, AWS positive, 高熵 positive, 低熵 negative | unit | `pytest tests/tools/test_secret_patterns_v2.py::test_layer1_positives -x` | ❌ Wave 0 |
| TOOL-V2-01 | secret patterns v2: 不回归 v1 行为（sk-ant-api / ghp_ / xoxb-... 仍命中） | unit | `pytest tests/tools/test_secret_patterns_v2.py::test_v1_regression -x` | ❌ Wave 0 |
| TOOL-V2-01 | secret patterns v2: 中文 / 散文 / 短英文不被熵误判 | unit | `pytest tests/tools/test_secret_patterns_v2.py::test_low_entropy_negatives -x` | ❌ Wave 0 |
| TOOL-V2-01 | surface drift: tool not in current → drop + count + dist | unit | `pytest tests/tools/test_surface_drift.py::test_drop_unknown_tool -x` | ❌ Wave 0 |
| TOOL-V2-01 | surface drift report 截断 top-N 但 metrics.json 完整 | unit | `pytest tests/tools/test_surface_drift.py::test_report_truncation -x` | ❌ Wave 0 |
| TOOL-V2-01 | JSONL 容错 load: 单行破损 → skip + 计数 + 5% 阈值 warn | unit | `pytest tests/tools/test_jsonl_skip_bad.py::test_skip_bad_line -x` | ❌ Wave 0 |
| TOOL-V2-01 | JSONL 容错 load: 不影响 EvalDataset.load（仍是严格模式） | unit | `pytest tests/tools/test_jsonl_skip_bad.py::test_evaldataset_strict_unchanged -x` | ❌ Wave 0 |
| TOOL-V2-01 | mine CLI: --i-have-consent 缺省 abort（exit 1 + 明确消息） | unit | `pytest tests/tools/test_mine_cli.py::test_consent_required -x` | ❌ Wave 0 |
| TOOL-V2-01 | mine CLI: --dry-run 不调 LLM, 打印 candidate 估算 | unit | `pytest tests/tools/test_mine_cli.py::test_dry_run -x` | ❌ Wave 0 |
| TOOL-V2-01 | mine CLI: --signals=error_retry,user_correction 跳过 oracle | unit | `pytest tests/tools/test_mine_cli.py::test_signal_subset -x` | ❌ Wave 0 |
| TOOL-V2-01 | mine CLI: --misselection-multiplier "error_retry=5,user_correction=2" 解析 | unit | `pytest tests/tools/test_mine_cli.py::test_multiplier_override -x` | ❌ Wave 0 |
| TOOL-V2-01 | mine CLI: --baseline-module 缺省 → C 信号自动跳过（warn 但不失败） | unit | `pytest tests/tools/test_mine_cli.py::test_baseline_module_optional -x` | ❌ Wave 0 |
| TOOL-V2-01 | evolve_tool_descriptions --session-source: union 顺序正确（session 同 hash 优先） | integration | `pytest tests/tools/test_evolve_with_session_source.py::test_session_overrides_synth -x` | ❌ Wave 0 |
| TOOL-V2-01 | evolve_tool_params --session-source: train.jsonl 已预复制（不再二次加倍） | integration | `pytest tests/tools/test_evolve_with_session_source.py::test_no_double_duplication -x` | ❌ Wave 0 |
| TOOL-V2-01 | metrics.json schema 完整：所有 CONTEXT specifics 字段都被写入 | unit | `pytest tests/tools/test_session_miner.py::test_metrics_schema -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/tools/test_session_*.py -x --tb=short`（约 25 测试，~30s with mock LM）
- **Per wave merge:** `.venv/bin/pytest tests/tools/ -v`（约 130 测试，包含 Phase 4/5/13 既有 tools 测试，确保不回归）
- **Phase gate:** `.venv/bin/pytest tests/ -v`（385 全套 + 28 新增；Phase 13 完成时基线为 385 passed + 1 xfailed）

### Wave 0 Gaps

所有测试文件均为新建，且依赖 fixture：

- [ ] `tests/fixtures/sessions/error_retry_b.json` —— 1 user + assistant tool_call(name=A) + tool error + assistant tool_call(name=B) + tool success；覆盖 REQ B 信号
- [ ] `tests/fixtures/sessions/user_correction_a.json` —— 1 user + assistant tool_call + tool success + user "不对，应该用 X" + assistant tool_call(name=X)；覆盖 REQ A 信号
- [ ] `tests/fixtures/sessions/oracle_disagreement_c.json` —— 1 user + assistant tool_call(name=Y) + tool success；预期 baseline ToolModule 会推荐 X；覆盖 REQ C 信号
- [ ] `tests/fixtures/sessions/malformed_msg.json` —— 包含一条缺失 `role` 的消息和一条 `tool_calls` 为非数组类型的消息；覆盖容错
- [ ] `tests/fixtures/sessions/multi_signal.json` —— 同时命中 B + A → max(3,3)=3x train multiplier；覆盖 D-11 max 语义
- [ ] `tests/fixtures/sessions/surface_drift.json` —— assistant 调用一个**不在** current hermes-agent 的工具名（例如 `legacy_tool_v0`）；覆盖 D-17
- [ ] `tests/fixtures/sessions/secret_in_user_msg.json` —— user 消息含 JWT / 高熵 token；覆盖 D-15 隐私过滤
- [ ] `tests/tools/test_session_signal_extract.py` —— 覆盖 B/A/C 三 extractor + 容错
- [ ] `tests/tools/test_session_judge.py` —— 复用 `mock_lm_with_usage` fixture（`tests/conftest.py:7-38`）；覆盖 ConfirmMisselection round-trip + LM error → false_positive
- [ ] `tests/tools/test_session_split.py` —— hash bucket 边界 + 确定性 + 跨信号 union
- [ ] `tests/tools/test_session_miner.py` —— mine() 端到端（mock LM）+ metrics schema + duplication
- [ ] `tests/tools/test_secret_patterns_v2.py` —— Layer 1 + 不回归 v1（subset 现有 `tests/test_external_importers.py` 用例）
- [ ] `tests/tools/test_jsonl_skip_bad.py` —— skip + 5% 阈值 + EvalDataset 不变
- [ ] `tests/tools/test_surface_drift.py` —— drop + report
- [ ] `tests/tools/test_mine_cli.py` —— click.testing.CliRunner，所有 flag
- [ ] `tests/tools/test_evolve_with_session_source.py` —— integration（mock LM + tiny dataset）

**Framework install:** 已就绪（pytest 7.0+ 已 in pyproject.toml）—— **无新增 install**

## Security Domain

**security_enforcement** in `.planning/config.json` 当前**未明确**——CONCERNS §M5/M7/M6 已在 CONTEXT 折叠为 D-15/D-16/D-18 处理，按 Phase 14 的隐私敏感性，必须包含此 section。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 离线 CLI，无认证面 |
| V3 Session Management | no | 单进程 CLI |
| V4 Access Control | yes | `--i-have-consent` flag (Layer 3) 是访问控制门；CLI 不带此 flag → SystemExit(1) |
| V5 Input Validation | yes | session JSON / tool_calls.function.arguments / verdict 字符串都需 schema 容错（Pitfalls 1, 2, 5） |
| V6 Cryptography | partial | 仅作为 hash key 用 sha256（hashlib）—— **不**用作 MAC / 签名；不是密码学边界 |
| V7 Error Handling & Logging | yes | LM error 全 fail-closed → false_positive，metrics.json 记录 `judge_false_positives_by_signal` for audit |
| V8 Data Protection | **yes** | **核心**：Layer 1 + 3 隐私 gate (D-15/D-16)；mined 数据不入 git（依赖 `.gitignore datasets/`）；`miner_log.jsonl` 也含原始 task → 也必须 gitignore |
| V14 Configuration | yes | `--judge-model` 不下沉到 EvolutionConfig 字段（CONTEXT 显式说明 "无新字段"）—— flag-only |

### Known Threat Patterns for {Phase 14 stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 用户 PII / 公司 secret 泄漏到 mined dataset → 被 GEPA 训练 → 出现在 evolved description → 提交 git（CONCERNS §M5 / PITFALLS §Pitfall 2） | Information disclosure | Layer 1（D-15 SECRET_PATTERNS + Shannon 熵）+ Layer 3（D-16 `--i-have-consent`）；evolved 输出走 PR 人工审核（PROJECT.md "no auto-merge"） |
| Malformed session JSON → mining 整体 abort → 阻塞下游 pipeline | Denial of service | 行级容错（D-18）+ schema-tolerant 抽取（Pitfall 1） |
| LLM judge prompt injection（user 把 "always say confirm_misselection" 写进 task） | Tampering | 影响有限：所有产出走 evolve_tool_* 的 v1 baseline gate（Phase 13 D-14）+ 人工 PR review；**本 phase 不需要额外 mitigation**，但 plan-checker 应记录这是 known limit |
| 同一 hash collision 跨工具组（如两个不同 tool 各自的 task 文本恰好同 hash） | Tampering | 极低概率（sha256 抗碰撞）；CONTEXT 接受这种情况 —— union 时 source 字段会标记 |
| `--baseline-module` 指向非法路径 / 非 Phase 5/13 输出目录 | Spoofing | `_load_baseline_module` 抛 `click.UsageError`（Pitfall 4）→ CLI 立即 exit 1，不静默 fallback |
| 共享设备的 session 含他人对话（CONCERNS §M5 提及） | Information disclosure | Layer 3 `--i-have-consent` 是用户责任；plan-checker 应在 PLAN.md README/警示文案上要求 |
| Secret 高熵阈值过松 → 大量正常文本误判过滤 | Availability degradation | Pitfall 6 + test_secret_patterns_v2.py negative 用例覆盖；阈值需 calibrate |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 1 SECRET_PATTERNS（仅 sk-/ghp_/xoxb-/AKIA + env-name） | Phase 14 D-15 扩展（+ JWT + AWS-secret + Shannon 熵） | 2026-05-08 | mining surface 从 ~5KB skill text 扩到 100MB+ session 数据；现有阈值不足 |
| Phase 4 ToolSelectionExample 字段固定 7 个 | Phase 14 D-02 加 `misselection_signals: list[str]` | 2026-05-08 | from_dict 已用字段过滤兼容（`tool_dataset.py:71`）；旧 JSONL 自动 default `[]` |
| Phase 5/13 dataset 单一 synthetic 来源 | Phase 14 union synthetic + session（D-09/D-14） | 2026-05-08 | evolve_tool_* 加 `--session-source` flag；不传 = 行为不变 |
| EvalDataset.load 单行 abort | Phase 14 仅在 session_miner output / evolve `--session-source` load 路径加 try/except（D-18 最小子集） | 2026-05-08 | EvalDataset/GoldenDatasetLoader 不动，留 v2-STAB-01 |
| Phase 1 `HermesSessionImporter` 仅抽 user/assistant text | Phase 14 session_miner 抽 tool_calls + tool result + 跨 turn 关联 | 2026-05-08 | 两个数据通道**独立**（D-10）；不扩展 HermesSessionImporter |

**Deprecated/outdated:** N/A —— Phase 14 是新增能力，无替代既有路径

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | dspy 3.x `dspy.Predict` + inner Signature + `dspy.context(lm=...)` 模式在本 phase 量级（~20 candidate × 44 sessions = 880 LLM calls）下稳定，无 connection pool / rate-limit 自爆 | Standard Stack / Pattern 1 | [VERIFIED 通过既有 ParamConsistencyChecker 用法] 量大约 1/10 of GEPA reflection 量；CONCERNS §M9 提到无显式 retry，但本 phase 不调 reflection_lm，cost 远低 |
| A2 | Shannon 熵阈值 4.0 区分能区分真 secret 和 SHA256/UUID/commit hash | Pitfall 6 | [ASSUMED] 实测 SHA256 hex 64 字符熵约 4.20——阈值 4.0 会误判。**需 plan 阶段加 calibration test 或调到 4.3+。建议 PLAN 留一个 calibration 任务**。 |
| A3 | 44 sessions 平均 ~20 candidate/session 是 cost 估算的合理基准 | Pitfall 7 / specifics | [ASSUMED] 实测一份大 session 27 messages 共 16 tool_calls，~10 个独立 (user, tool_call) 配对——specifics 的 20 candidate/session 上限略乐观，实际更可能是 10。这意味着 cost 估算偏高（保守），不影响安全。 |
| A4 | Phase 5/13 输出的 `evolved_descriptions.json` schema 足以重建 ToolModule | Pitfall 4 | [VERIFIED 通过 `evolve_tool_params.py:1037-1057` 字段集] Phase 13 schema 含 `params[*].{name, type, required, description}`，足够构造 ToolDescription/ToolParam（其余 `desc_format`, `enum`, `raw_source` 用 current hermes-agent 工具的对应字段补全） |
| A5 | `~/.hermes/sessions/` 实测 44 份样本对 hermes-agent 当前版本是稳定路径 | canonical_refs / D-07 | [VERIFIED 当前实例] `Path.home() / ".hermes" / "sessions"` 与 `HermesSessionImporter.SESSION_DIR` 一致 |
| A6 | tool 消息 `name` 字段为 None 是 hermes 当前版本的稳定行为 | Pitfall 1 | [VERIFIED in 抽样] 反查工具名靠 `tool_call_id` 而非 `name`；如果未来 hermes-agent 修复了 `name` 字段，extractor 也无 regression（提示 plan 留 test 既覆盖 None 也覆盖 string） |
| A7 | session_miner 串行 LLM judge 在量化 cost 之内可接受（不需要并发） | Standard Stack alternative | [ASSUMED] CONTEXT Claude's Discretion 已批准；如实跑 mining 出 >5 分钟可在后续 phase 加 ThreadPool |
| A8 | metrics.json 字段命名与 Phase 5/13 保持前缀一致后 Phase 16 dashboard 能直接 union | Pitfall 7 / Phase 16 ref | [ASSUMED] Phase 16 尚未 plan，但建议 metrics.json 字段保持 `cost_usd_spent`/`*_failures`/`per_*_distribution` 风格 |

**6 项 [ASSUMED]，2 项 [VERIFIED]。** 关键 assumption A2（熵阈值）需 PLAN 显式加 calibration 任务。

## Open Questions

1. **熵阈值 4.0 vs 4.3 选择**
   - What we know: CONTEXT specifics 给 4.0；实测 SHA256 hex 熵 ≈4.20 会误中
   - What's unclear: 真实 user message 中长 high-entropy token 占比是否高到使 4.0 损失 >5% 合法消息
   - Recommendation: PLAN 加一个独立子任务 "calibrate_entropy_threshold" —— 用 5 份真实 session 跑 dry-run, 输出 token-by-token 熵分布，与已知 secret fixture 比对，**最终在 PLAN 中固化阈值**（可能是 4.0、4.2、或 4.5）

2. **多 tool_call 同 turn 时 user_correction 信号归属**
   - What we know: 实测一个 assistant turn 同时 call terminal + search_files
   - What's unclear: 用户后续 "应该用 X" 是纠正哪个 tool？
   - Recommendation: A 信号 candidate 抽取仅认 **assistant turn 的最后一个 tool_call**（最近一次决策）；其余 tool_call 不归 A 信号。在 PLAN 中明确并加 fixture 验证

3. **Surface drift 当 tool 名只是 alias 变更（如 `bash` → `terminal`）**
   - What we know: CONTEXT D-17 "不维护 alias 表"
   - What's unclear: 当前工具集是否真有 alias 历史？
   - Recommendation: 不在 Phase 14 处理；**记入 deferred**：将 surface drift 报告中的 `surface_drift_tools` 名字 list 给到 Phase 16 dashboard，由人工决策是否补 alias

4. **JSONL bad-line 阈值 5% 是否合适**
   - What we know: D-18 用 5% 触发 warn（不 abort）
   - What's unclear: 100MB+ session JSONL 是否会更宽容（比如 1% 都很多）
   - Recommendation: 5% 跟既有 `external_importers.py:529-541` 误判率 warn 模式一致；保持，必要时下游 phase 再调

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | 全 phase | ✓ | 3.13.3 (`.venv`) | — |
| dspy | LLM judge | ✓ | >=3.0.0 | — |
| click | CLI | ✓ | >=8.0 | — |
| rich | console output | ✓ | >=13.0 | — |
| pytest | tests | ✓ | >=7.0 | — |
| pytest-asyncio | (未用到 asyncio) | ✓ | >=0.21 | — |
| `~/.hermes/sessions/` 真实数据 | 集成测试（可选） | ✓ | 44 文件，2026-04-08 ~ 2026-04-15 | fixtures 模拟（必须）|
| `HERMES_AGENT_REPO` 真实 repo | surface drift 对照 | ✓ (env or `~/.hermes/hermes-agent`) | — | mock `extract_tool_descriptions` (CI/test) |
| Phase 5/13 历史 output（C 信号） | C 信号 oracle | 部分（仅 1 个 FAILED_ 输出可见） | — | C 信号自动跳过（CLI flag 缺省即 skip） |
| LLM API key（mining 实跑） | 实际挖矿 | 用户提供 | — | dry-run 模式不需要 |

**Missing dependencies with no fallback:** 无

**Missing dependencies with fallback:**
- 真实 hermes-agent repo —— 测试用 mock
- Phase 5/13 历史 output —— `--baseline-module` 缺省即跳过 C 信号（CLI 必须 graceful 处理）

## Sources

### Primary (HIGH confidence)
- `/Users/slj/项目/hermes-agent-self-evolution/.planning/phases/14-sessiondb-mining-for-tools/14-CONTEXT.md` — 18 D-01..D-18 锁定决策
- `/Users/slj/项目/hermes-agent-self-evolution/.planning/codebase/CONCERNS.md` §M4/M5/M6/M7 — 隐私 / 解析 / 容错的根因分析
- `/Users/slj/项目/hermes-agent-self-evolution/.planning/research/PITFALLS.md` §Pitfall 2 — PII 三层 sanitization 完整论证
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_constraints.py` — ToolFactualChecker / ParamConsistencyChecker 完整模板（lines 32-307）
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_dataset.py` — ToolSelectionExample / Dataset / Builder（lines 32-435）
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_module.py` — ToolModule.forward + get_evolved_descriptions（lines 89-232）
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/evolve_tool_descriptions.py` / `evolve_tool_params.py` — CLI 模板 + metrics.json schema
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/core/external_importers.py` — SECRET_PATTERNS / `_contains_secret` / HermesSessionImporter / ClaudeCodeImporter（lines 45-416）
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/core/config.py` — EvolutionConfig.load 优先级链（lines 86-203）
- 实测 hermes session 文件抽样：`session_20260411_141731_f8aff8.json`（27 messages, 16 tool calls）

### Secondary (MEDIUM confidence)
- Phase 4/5/13 历史 CONTEXT.md —— 数据集 split / CLI 模式 / cost cap 的先例

### Tertiary (LOW confidence)
- 无 —— 全部信息已通过本仓库代码与 CONTEXT 文件交叉验证

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH —— 全部依赖已 in-use 且代码模式有先例
- Architecture: HIGH —— 每条 D-01..D-18 都映射到具体文件/行号
- Pitfalls: HIGH —— 10 个 pitfall 均给出 root cause + how to avoid + warning signs；其中 6 个有真实 session 抽样作证
- Validation: HIGH —— 测试矩阵覆盖 28 个 unit 测试 + 3 个 integration；fixture 列表齐全
- Privacy/Security: HIGH —— ASVS V8 + STRIDE 已覆盖；CONCERNS §M5/M7 ↔ D-15/D-16/D-18 完整闭环
- 假设项：A2（熵阈值）是唯一 MEDIUM 置信度，已在 Open Questions 留 calibration 任务

**Research date:** 2026-05-08
**Valid until:** 2026-06-07（30 天，stable 域）—— 失效触发条件：dspy 升至 3.2+（API 变化）、hermes-agent session schema 大改、新增 hermes session 比例 >100 份（cost 估算需重算）

## RESEARCH COMPLETE

**Phase:** 14 - SessionDB Mining for Tools
**Confidence:** HIGH

### Key Findings
- Phase 14 实现风险集中在三处边界：session JSON schema 容错（实测 schema 有 CONTEXT 未列字段）、union/duplicate ordering 正确性、隐私 gate 阈值 calibration
- 90% 代码可从既有零件组合（ToolFactualChecker / ParamConsistencyChecker / ClaudeCodeImporter / evolve_tool_params CLI）；新代码主要是 3 extractor + hash bucket + Shannon 熵
- LLM judge cost 估算需含 user_correction 二判（约 +$1.3）；总成本 ~$10-11 with gpt-4.1，可降至 ~$1.7 with gpt-4.1-mini
- A2 熵阈值 4.0 与 SHA256 hex 实测熵 4.20 接近，需 PLAN 加 calibration 任务
- ToolSelectionExample.from_dict 字段过滤已确保新加 `misselection_signals` 字段对旧 JSONL 向后兼容
- D-18 JSONL 容错最小子集仅触及 session_miner 输出 + evolve --session-source 加载，明确**不**改 EvalDataset/GoldenDatasetLoader（v2-STAB-01 边界）

### File Created
`.planning/phases/14-sessiondb-mining-for-tools/14-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | 所有依赖 in-use，模式有先例 |
| Architecture | HIGH | D-01..D-18 全部映射到具体文件 + 行号 |
| Pitfalls | HIGH | 10 项 pitfall 含 root cause + 实测样本佐证 |
| Validation | HIGH | 28+3 测试 + 7 fixture 完整列出 |
| Security | HIGH | ASVS V8 + STRIDE 闭环 |
| 熵阈值 (A2) | MEDIUM | 需 calibration 任务 |

### Open Questions
1. 熵阈值 4.0 vs 4.3（已留 calibration sub-task 建议）
2. 多 tool_call 同 turn 的 user_correction 归属（建议取最后一次 tool_call）
3. Surface drift alias 表（确认 deferred；feed Phase 16）
4. JSONL bad-line 5% 阈值（与既有 `external_importers.py:529-541` 一致，保持）

### Ready for Planning
研究完成。Planner 现在可以基于本 RESEARCH.md 创建 PLAN.md 文件。建议 PLAN 拆分为：
- **Wave 0 — Test Scaffolding & Fixtures** （新建 7 fixture session JSON + 9 RED 测试文件）
- **Wave 1 — Data Layer** （`misselection_signals` 字段 + `_load_jsonl_skip_bad` helper + SECRET_PATTERNS 扩展）
- **Wave 2 — Core Mining** （session_miner.py 三 extractor + ConfirmMisselection judge + hash bucket + dedup union + duplication）
- **Wave 3 — CLI & Integration** （mine_tool_sessions.py + evolve_tool_descriptions/params 加 --session-source flag）
- **Wave 4 — Calibration & Smoke** （熵阈值 calibration 任务 + 真实 44 sessions dry-run 验证 candidate count + cost 估算 ✓ CONTEXT 范围内）
