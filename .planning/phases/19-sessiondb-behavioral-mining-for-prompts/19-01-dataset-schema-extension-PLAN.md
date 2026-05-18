---
phase: 19-sessiondb-behavioral-mining-for-prompts
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - evolution/prompts/prompt_dataset.py
autonomous: true
requirements:
  - PMPT-V2-04
tags:
  - prompt
  - dataset
  - schema

must_haves:
  truths:
    - "[D-02] PromptBehavioralExample 暴露 mining_signals: list[str] 字段，默认 []，旧 JSONL 加载时 mining_signals 自动为 []（向后兼容）"
    - "[D-02] PromptBehavioralExample.source 文档允许 'synthetic' | 'golden' | 'session' 三值（dataclass 不做枚举校验，但 docstring 显式列出枚举）"
    - "[D-02] to_dict 序列化包含 mining_signals 键，from_dict 仍走 __dataclass_fields__ 过滤路径（保留旧 JSONL 兼容性）"
    - "[D-10] PromptBehavioralExample 字段集只增加 mining_signals 一项；不引入 session_path / turn_idx / verdict_rationale（PII + schema 简洁性约束）"
    - "[D-15] 模块级辅助 `_normalize_task_hash(task)` + `_hash_to_split(h)` 与 Phase 14 (`evolution/tools/session_miner.py:50-63`) 字节一致，可被 Plan 02/04 直接 import"
  artifacts:
    - path: "evolution/prompts/prompt_dataset.py"
      provides: "PromptBehavioralExample.mining_signals 字段 + source 文档扩展"
      contains: "mining_signals: list[str] = field(default_factory=list)"
    - path: "evolution/prompts/prompt_dataset.py"
      provides: "Hash-bucket split 辅助（与 Phase 14 对称）"
      exports:
        - "_normalize_task_hash"
        - "_hash_to_split"
  key_links:
    - from: "evolution/prompts/prompt_dataset.py:PromptBehavioralExample"
      to: "evolution/prompts/session_prompt_miner.py (Plan 02)"
      via: "import + dataclass instantiation with mining_signals=[...]"
      pattern: "from evolution.prompts.prompt_dataset import PromptBehavioralExample"
    - from: "evolution/prompts/prompt_dataset.py:_normalize_task_hash"
      to: "evolution/prompts/evolve_prompt_sections.py (Plan 04 D-16 union)"
      via: "import for hash-based dedup at union site"
      pattern: "from evolution.prompts.prompt_dataset import _normalize_task_hash"
---

<objective>
扩展 PromptBehavioralExample 以承载 SessionDB 挖矿信号 (D-02)，并在 prompt_dataset.py 中暴露 hash-bucket split 辅助函数（D-15），为 Plan 02 SessionPromptMiner 与 Plan 04 evolve_prompt_sections union 提供可复用入口。

Purpose: Phase 19 是 Phase 14 的 prompt 镜像，schema 改动是其他 4 个 plan 的依赖前置。该 plan 是 Wave 1 唯一节点。
Output: 修改后的 `evolution/prompts/prompt_dataset.py`，含 `mining_signals` 字段、`source` 文档扩展、`_normalize_task_hash` 与 `_hash_to_split` 辅助函数。
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-CONTEXT.md
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md
@evolution/prompts/prompt_dataset.py
@evolution/tools/session_miner.py
</context>

<interfaces>
<!-- Current PromptBehavioralExample (prompt_dataset.py:33-66) — keep all fields, ADD mining_signals -->
```python
@dataclass
class PromptBehavioralExample:
    section_id: str
    user_message: str
    expected_behavior: str
    difficulty: str = "medium"
    source: str = "synthetic"
    # NEW (D-02):
    mining_signals: list[str] = field(default_factory=list)
```

<!-- Verbatim helpers from evolution/tools/session_miner.py:50-63 (Phase 14) — keep IDENTICAL signature -->
```python
def _normalize_task_hash(task: str) -> str:
    """Return sha256(strip + lower + collapse_whitespace(task))[:16]."""
    norm = re.sub(r"\s+", " ", (task or "").lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _hash_to_split(h: str) -> str:
    """Bucket: <70 train / <85 val / else holdout."""
    bucket = int(h[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "val"
    return "holdout"
```

<!-- Existing PromptBehavioralDataset.save (lines 85-101) and load (lines 103-122) — DO NOT MODIFY.
     CONTEXT D-24 explicit: "**不**重写 PromptBehavioralDataset.load (v2-STAB-01 独立清理范围)"
     The JSONL try/except resilience lives in evolve_prompt_sections.py (Plan 04). -->
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1.1: 扩展 PromptBehavioralExample dataclass 加 mining_signals 字段 + 文档</name>
  <files>evolution/prompts/prompt_dataset.py</files>

  <read_first>
    - evolution/prompts/prompt_dataset.py (整文件，重点 lines 13-66：imports + dataclass 块)
    - evolution/tools/tool_dataset.py (查看 Phase 14 ToolSelectionExample.misselection_signals 的镜像写法)
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §2.1.A (lines 556-625)
  </read_first>

  <behavior>
    - Test 1: 旧 JSONL（无 mining_signals 键）通过 from_dict 加载后，对象的 mining_signals 字段是空 list []
    - Test 2: 新 to_dict 输出 6 个键：section_id, user_message, expected_behavior, difficulty, source, mining_signals
    - Test 3: 直接构造 `PromptBehavioralExample(section_id="x", user_message="m", expected_behavior="e", mining_signals=["user_correction"])` 不抛错
    - Test 4: from_dict 仍过滤未知键（喂入 `{"section_id":..., "rogue_key":"x", ...}` 不抛错，不保留 rogue_key）
  </behavior>

  <action>
    打开 `evolution/prompts/prompt_dataset.py`，在 lines 33-66 内做以下精确修改：

    1. 在 dataclass 字段块尾追加：
    ```python
    mining_signals: list[str] = field(default_factory=list)
    ```
    放在 `source: str = "synthetic"` 后面，缩进 4 空格（与其他字段对齐）。

    2. 更新 dataclass docstring 中 `Args:` 块：
       - 修改 `source:` 行为：`source: Provenance: 'synthetic', 'golden', 'session' (Phase 19 D-02 extends enum).`
       - 在 `source:` 之后追加：`mining_signals: Which session-mining signal(s) produced this example; empty for synthetic/golden. Phase 19 D-02.`

    3. 更新 `to_dict()` 方法（lines 53-61），在 return 字典末尾追加键值：
    ```python
    "mining_signals": self.mining_signals,
    ```
    保持其他键不变；返回的字典严格 6 个键。

    4. 更新 `from_dict()` 方法（lines 63-66）的 docstring，加一句：
       `Backward compatible: pre-Phase-19 JSONL has no mining_signals key → defaults to []. The existing __dataclass_fields__ filter handles unknown keys, so historical Phase 9 datasets load unchanged.`
       不要修改 from_dict 的实现代码（已经通过 `__dataclass_fields__` 过滤未知键 — D-02 显式记录）。

    5. 在 imports 块顶部确认 `from dataclasses import dataclass, field` 已存在（line 16 — 已存在 `field`，无需新增）。

    依据 (per D-02 + D-10)：
    - 不加 session_path / turn_idx / verdict_rationale（PII + 简洁性）
    - source 仍是 str 不引入 Enum 类型（避免破坏 from_dict / to_dict round-trip）
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
from evolution.prompts.prompt_dataset import PromptBehavioralExample
# T1: legacy load
legacy = PromptBehavioralExample.from_dict({'section_id':'memory_guidance','user_message':'m','expected_behavior':'e','difficulty':'easy','source':'synthetic'})
assert legacy.mining_signals == [], f'expected [], got {legacy.mining_signals}'
# T2: to_dict has 6 keys
d = legacy.to_dict()
assert set(d.keys()) == {'section_id','user_message','expected_behavior','difficulty','source','mining_signals'}, d.keys()
# T3: construct with signals
ex = PromptBehavioralExample(section_id='x',user_message='m',expected_behavior='e',mining_signals=['user_correction'])
assert ex.mining_signals == ['user_correction']
# T4: from_dict drops unknown keys
ex2 = PromptBehavioralExample.from_dict({'section_id':'x','user_message':'m','expected_behavior':'e','rogue':'drop'})
assert not hasattr(ex2,'rogue')
print('PASS')
"</automated>
    Expected stdout: `PASS`
  </verify>

  <acceptance_criteria>
    - `grep -n "mining_signals: list\[str\] = field(default_factory=list)" evolution/prompts/prompt_dataset.py` 命中 1 行
    - `grep -n '"mining_signals": self.mining_signals' evolution/prompts/prompt_dataset.py` 命中 1 行
    - `grep -c "'session'" evolution/prompts/prompt_dataset.py` ≥ 1（docstring 提及 session 枚举）
    - `python -c "from evolution.prompts.prompt_dataset import PromptBehavioralExample; print(sorted(PromptBehavioralExample.__dataclass_fields__.keys()))"` 输出含 `mining_signals`
    - 现有 `from_dict` 行（line 66）未被修改（grep 检查仍存在 `**{k: v for k, v in d.items() if k in cls.__dataclass_fields__}`）
    - Existing test suite passes: `python -m pytest tests/prompts/ -x -q` 无 regression
  </acceptance_criteria>

  <done>
    PromptBehavioralExample 含 6 个字段，新增 mining_signals 默认 []；to_dict / from_dict 互逆；旧 JSONL 自动获得 mining_signals=[]；docstring 显式列出 source 枚举包含 'session'。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 1.2: 暴露 _normalize_task_hash 与 _hash_to_split 模块级辅助</name>
  <files>evolution/prompts/prompt_dataset.py</files>

  <read_first>
    - evolution/prompts/prompt_dataset.py (imports + 顶部模块块)
    - evolution/tools/session_miner.py lines 22-74 (Phase 14 verbatim 模板)
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §1.1.B (lines 82-110)
  </read_first>

  <behavior>
    - Test 1: `_normalize_task_hash("  Hello   WORLD  ")` 等于 `_normalize_task_hash("hello world")`（whitespace collapse + lower + strip 确定性）
    - Test 2: `_normalize_task_hash("")` 与 `_normalize_task_hash(None)` 都返回 16 字符 hex（不抛错）
    - Test 3: 三个 hash 的 bucket 分布 — 输入 1000 个不同字符串，`_hash_to_split` 输出 train/val/holdout 桶大致符合 70/15/15（each bucket count > 100）
    - Test 4: 同一输入 `_normalize_task_hash` 调用两次结果一致（确定性）
  </behavior>

  <action>
    打开 `evolution/prompts/prompt_dataset.py`，在文件顶部 imports 块之后、`@dataclass` 定义之前插入两个模块级函数。

    1. 在 line 13-19 imports 区域确认包含：
    ```python
    import hashlib
    import json
    import re
    ```
    （`json` 与 `re` 已存在 line 13/15；`hashlib` 当前缺失 — 需要新增 `import hashlib` 紧跟 `import json` 之后）。

    2. 在现有 imports 块结尾（`from evolution.prompts.prompt_loader import PromptSection` 后）+ console 定义 (`console = Console()`) 之前插入 section comment 与两个函数（精确字节复制 `evolution/tools/session_miner.py:50-63`）：

    ```python
    # ── Hash + bucket helpers (D-15, mirror evolution/tools/session_miner.py:50-63) ──
    def _normalize_task_hash(task: str) -> str:
        """Return sha256(strip + lower + collapse_whitespace(task))[:16].

        Used by SessionPromptMiner (Plan 02) for cross-split dedup and by
        evolve_prompt_sections.py (Plan 04) for D-16 union dedup. Mirrors
        evolution/tools/session_miner._normalize_task_hash byte-for-byte.
        """
        norm = re.sub(r"\s+", " ", (task or "").lower()).strip()
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


    def _hash_to_split(h: str) -> str:
        """Bucket per D-15: <70 train / <85 val / else holdout.

        Deterministic split using first 8 hex chars mod 100. Mirrors
        evolution/tools/session_miner._hash_to_split byte-for-byte.
        """
        bucket = int(h[:8], 16) % 100
        if bucket < 70:
            return "train"
        if bucket < 85:
            return "val"
        return "holdout"
    ```

    3. 不要修改 PromptBehavioralExample / PromptBehavioralDataset / PromptDatasetBuilder 任何已有定义。

    依据 (per D-15)：
    - 与 Phase 14 字节一致是显式 D-15 约束（"hash mod 100" + "70/85/100" + "sha256 + strip + lower + collapse_whitespace + [:16]"）
    - 暴露在 `prompt_dataset.py` 顶层而非 `session_prompt_miner.py`，是因为 Plan 04 evolve_prompt_sections.py 的 union 路径也需要 import 这两个函数（避免 session_prompt_miner.py 反向被 evolve_prompt_sections.py 强依赖）
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
from evolution.prompts.prompt_dataset import _normalize_task_hash, _hash_to_split
# T1: whitespace + case normalization
assert _normalize_task_hash('  Hello   WORLD  ') == _normalize_task_hash('hello world')
# T2: empty / None safe
assert len(_normalize_task_hash('')) == 16
assert len(_normalize_task_hash(None)) == 16
# T3: split distribution
import collections
counts = collections.Counter(_hash_to_split(_normalize_task_hash(f'msg{i}')) for i in range(1000))
assert counts['train'] > 100 and counts['val'] > 100 and counts['holdout'] > 100, counts
# T4: determinism
h1 = _normalize_task_hash('repeat me')
h2 = _normalize_task_hash('repeat me')
assert h1 == h2
print('PASS')
"</automated>
    Expected stdout: `PASS`
  </verify>

  <acceptance_criteria>
    - `grep -n "^def _normalize_task_hash" evolution/prompts/prompt_dataset.py` 命中 1 行
    - `grep -n "^def _hash_to_split" evolution/prompts/prompt_dataset.py` 命中 1 行
    - `grep -n "^import hashlib" evolution/prompts/prompt_dataset.py` 命中 1 行（新增 import）
    - `grep -nE "hashlib\.sha256\(norm\.encode\(.utf-8.\)\)\.hexdigest\(\)\[:16\]" evolution/prompts/prompt_dataset.py` 命中 1 行
    - `python -c "from evolution.prompts.prompt_dataset import _normalize_task_hash, _hash_to_split; print(_normalize_task_hash('test'))"` 输出 16 字符 hex
    - 现有 PromptBehavioralExample / Dataset / Builder 仍可 import 不报错（`python -m evolution.prompts.prompt_dataset` 不抛 SyntaxError）
    - `python -m pytest tests/prompts/ -x -q` 无 regression
  </acceptance_criteria>

  <done>
    `evolution/prompts/prompt_dataset.py` 顶层暴露 `_normalize_task_hash` 与 `_hash_to_split` 两个纯函数，行为与 Phase 14 字节一致；可被 Plan 02 与 Plan 04 直接 `from evolution.prompts.prompt_dataset import _normalize_task_hash, _hash_to_split` 复用。
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| File system → in-memory dataclass | 旧 JSONL 文件解析为 PromptBehavioralExample；未知字段（含潜在恶意键）必须被丢弃 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-19-01-S | Spoofing | PromptBehavioralExample.from_dict | mitigate | 已有 `__dataclass_fields__` 过滤未知键；本任务不改该路径，新增 mining_signals 走同一过滤 |
| T-19-01-T | Tampering | PromptBehavioralExample 持久化 schema | mitigate | mining_signals 默认 [] 保证旧 JSONL 行为不变；新字段加入不破坏 round-trip |
| T-19-01-I | Information Disclosure | dataclass 字段集 | mitigate | 显式不加 session_path / turn_idx（D-10）— PII 不落 schema |
| T-19-01-D | DoS | _normalize_task_hash | accept | sha256 单字符串调用 O(len) 成本极低；输入长度由 session JSON 限定 |
| T-19-01-E | Elevation | _hash_to_split | accept | 纯计算函数，无副作用；模 100 桶分布固定 |

T1 (Session text 泄漏) 在本 plan 不适用（仅 schema 改动，不读 session）；T1 在 Plan 02/03 落地。
T3 (JSONL 损坏) 在本 plan 不落地（D-24 显式说"不重写 PromptBehavioralDataset.load"，由 Plan 04 在 evolve_prompt_sections.py 的 union 调用点处理）。
</threat_model>

<verification>
- 修改后 `prompt_dataset.py` 通过 Python 解析（no SyntaxError）
- 现有 prompt 测试 110 全部通过：`python -m pytest tests/prompts/ -x`
- 新增 dataclass 字段反向兼容历史 Phase 9 数据集（Task 1.1 verify 步骤 T1 验证）
- 模块级 helper 行为与 Phase 14 ToolSelectionExample dedup 对称（Task 1.2 verify 步骤 T1-T4）
</verification>

<success_criteria>
- PromptBehavioralExample 暴露 6 个字段（含 mining_signals: list[str] = []）
- prompt_dataset.py 顶层导出 `_normalize_task_hash` + `_hash_to_split` 函数
- 不改 PromptBehavioralDataset.save/load 任何代码（D-24 显式约束）
- 现有 tests/prompts/ 110 通过零 regression
- 后续 Plan 02 / Plan 04 可直接 import 三个新符号（mining_signals 字段 + 两个 helper）
</success_criteria>

<output>
After completion, create `.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-01-SUMMARY.md` 记录：
- 修改文件路径与精确 line ranges
- 旧 JSONL 兼容性确认证据（运行 Task 1.1 verify 输出）
- _normalize_task_hash / _hash_to_split 与 Phase 14 字节一致的 diff 证据
- 下游 plan (02 / 04) 的 import 入口锚点
</output>
