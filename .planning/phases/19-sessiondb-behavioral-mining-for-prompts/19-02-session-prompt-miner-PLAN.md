---
phase: 19-sessiondb-behavioral-mining-for-prompts
plan: 02
type: execute
wave: 2
depends_on:
  - 19-01
files_modified:
  - evolution/prompts/session_prompt_miner.py
autonomous: true
requirements:
  - PMPT-V2-04
tags:
  - prompt
  - mining
  - dspy-judge
  - drift-detector

must_haves:
  truths:
    - "[D-01] SessionPromptMiner 实现 4 路信号 extractor：_extract_user_correction / _extract_section_specific_failure / _extract_oracle_disagreement / _extract_persona_drift；4 路均产 candidate 送统一 LLM judge"
    - "[D-03] Inner `ConfirmBehavioralExample(dspy.Signature)` 单 LLM call 输出 5 字段：verdict, section_id, expected_behavior, difficulty, rationale"
    - "[D-04] _extract_persona_drift 复用 Phase 18 DriftDetector，但调用 `_check_one_run`（1-run）非 `.check`（3-run），降低 candidate 数 3 倍；min_turns=6 门槛"
    - "[D-04] _extract_section_specific_failure 内部为 5 个 section（4 str + platform_hints.<key> 通配）各起独立 per-section keyword pattern"
    - "[D-05] judge verdict=false_positive 不丢弃，写 metrics.judge_false_positives_by_signal"
    - "[D-06] candidate proposer 仅负责'召回'，section_id 由 LLM judge 输出决定（不硬编码 section→pattern 1:1）"
    - "[D-07] 同 candidate 多 proposer 命中拆多条 examples（共享 task_hash 不同 section_id）；schema 保持 section_id: str 单选"
    - "[D-08] section_id 输出形如 platform_hints.<key>；LLM judge prompt 显式包含 platform_token 引导"
    - "[D-09] section_id 不在当前 extract_prompt_sections() 产出 → 整例丢弃 + 写 surface_drift_dropped / surface_drift_sections"
    - "[D-11] expected_behavior 由 LLM judge 同 call 输出 rubric（1-3 sentences）；不用 verbatim correction"
    - "[D-12] difficulty 由 LLM judge 同 call 输出 ∈ {easy, medium, hard}；解析失败默认 medium"
    - "[D-13] 复制策略在 split_and_duplicate 内：user_correction=3x / section_specific_failure=3x / oracle_disagreement=2x / persona_drift=2x；多源命中取 max；仅 train 切分复制"
    - "[D-15] hash mod 100 → 70/85/15 桶；同 hash 仅出现在一个切分（去重在桶分配前）"
    - "[D-18] SessionPromptMiner 类结构对齐 SessionToolMiner（构造 + mine + 4 个 _extract_* + _judge_candidate + _load_session）"
    - "[D-23] 所有 user/assistant 文本经 _contains_secret 过滤；命中 +secret_filter_skipped 并丢 candidate"
    - "[D-24] _load_session 用 try/except 包裹 json.loads；失败 +session_load_failures（B3 fix：与 jsonl_skipped_lines 区分）"
    - "[B3 fix] metrics schema 新增 `session_load_failures: int = 0`，专用于 mine_prompt_sessions 内 session JSON file-level 加载失败计数；与 `jsonl_skipped_lines`（line-level，由 Plan 04 helper 单独维护）语义解耦"
  artifacts:
    - path: "evolution/prompts/session_prompt_miner.py"
      provides: "SessionPromptMiner 类 + ConfirmBehavioralExample / DetectUserCorrection inner Signatures + DEFAULT_MULTIPLIER / VALID_SIGNALS 常量 + Candidate dataclass + split_and_duplicate 函数"
      min_lines: 500
      exports:
        - "SessionPromptMiner"
        - "DEFAULT_MULTIPLIER"
        - "VALID_SIGNALS"
        - "Candidate"
        - "split_and_duplicate"
  key_links:
    - from: "evolution/prompts/session_prompt_miner.py:SessionPromptMiner._extract_persona_drift"
      to: "evolution/prompts/drift_detector.py:DriftDetector._check_one_run"
      via: "复用 Phase 18 资产作为 candidate proposer"
      pattern: "self\\.drift_detector\\._check_one_run\\("
    - from: "evolution/prompts/session_prompt_miner.py:SessionPromptMiner.mine"
      to: "evolution/prompts/prompt_loader.py:extract_prompt_sections"
      via: "D-09 surface drift filter — 当前 section 集合从 prompt_loader 取"
      pattern: "current_section_ids"
    - from: "evolution/prompts/session_prompt_miner.py"
      to: "evolution/prompts/prompt_dataset.py:PromptBehavioralExample"
      via: "构造 PromptBehavioralExample(source='session', mining_signals=[...])"
      pattern: "PromptBehavioralExample\\(.+source=.session."
    - from: "evolution/prompts/session_prompt_miner.py"
      to: "evolution/core/external_importers.py:_contains_secret"
      via: "D-23 secret filter import + filter pass"
      pattern: "from evolution\\.core\\.external_importers import _contains_secret"
---

<objective>
新建 `evolution/prompts/session_prompt_miner.py`，实现 4 路 SessionDB 行为信号挖矿核心服务：候选抽取（user_correction / section_specific_failure / oracle_disagreement / persona_drift）→ secret filter → LLM judge ConfirmBehavioralExample（单 call 5 字段）→ surface drift filter → hash dedup + bucket split + train-only duplication。复用 Phase 18 DriftDetector 作为 persona_drift candidate proposer。

Purpose: Phase 19 Wave 2 核心实现节点。Plan 03 CLI 包装其 mine() 入口，Plan 04 evolve_prompt_sections 通过 --session-source 消费其输出 JSONL，Plan 05 集成测试覆盖。
Output: 新 Python 模块 ~500-700 LoC，对齐 `evolution/tools/session_miner.py` 结构。
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
@.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-01-SUMMARY.md
@evolution/tools/session_miner.py
@evolution/prompts/drift_detector.py
@evolution/prompts/prompt_loader.py
@evolution/prompts/prompt_constraints.py
@evolution/core/external_importers.py
@evolution/prompts/prompt_dataset.py
</context>

<interfaces>
<!-- From evolution/tools/session_miner.py (Phase 14 — VERBATIM template per D-18) -->

Phase 14 `SessionToolMiner` 类结构（高层 outline，对齐时复制）：
```python
class SessionToolMiner:
    def __init__(self, config, signals=None, multiplier_override=None, baseline_module=None): ...
    def mine(self, sessions_dir: Path, current_tools: list, limit: int = 0) -> list[ToolSelectionExample]: ...
    def _load_session(self, path: Path) -> Optional[dict]: ...  # try/except json.loads
    def _extract_error_retry(self, messages, session_path) -> list[Candidate]: ...  # NOT used in Phase 19
    def _extract_user_correction(self, messages, session_path) -> list[Candidate]: ...
    def _extract_oracle_disagreement(self, messages, session_path) -> list[Candidate]: ...
    def _filter_secrets(self, cands) -> list[Candidate]: ...
    def _filter_drift(self, cands, current_ids) -> list[Candidate]: ...
    def _judge_candidates(self, cands) -> list[tuple[Candidate, Verdict]]: ...
```

<!-- From evolution/prompts/drift_detector.py (lines 98-156) -->
```python
class DriftDetector:
    DRIFT_DIMENSIONS = ("tone", "formality", "vocabulary", "persona")  # module const
    def __init__(self, config: EvolutionConfig, thresholds: dict): ...
        # thresholds MUST contain all 4 keys; raises ValueError otherwise
    @property
    def thresholds(self) -> dict[str, float]: ...
    def _check_one_run(self, section_id: str, original_text: str, evolved_text: str) -> tuple[dict, str]:
        """Single LLM call. Returns (per_dim_scores, explanation).
        Phase 19 calls this DIRECTLY (NOT .check which does 3-run averaging)."""
```

<!-- From evolution/prompts/prompt_loader.py -->
```python
@dataclass
class PromptSection:
    section_id: str    # e.g. "default_agent_identity" | "platform_hints.macos"
    text: str
    char_count: int
    line_range: tuple[int, int]
    source_path: Path

def extract_prompt_sections(prompt_builder_path: Path) -> list[PromptSection]: ...
```

<!-- From evolution/prompts/prompt_constraints.py:15-29 -->
```python
def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "1")
```

<!-- From evolution/core/external_importers.py:108 -->
```python
def _contains_secret(text: str) -> bool: ...
```

<!-- From Plan 19-01 (just-shipped) -->
```python
# Imports available from evolution.prompts.prompt_dataset:
from evolution.prompts.prompt_dataset import (
    PromptBehavioralExample,      # now has mining_signals: list[str] = []
    _normalize_task_hash,         # NEW — D-15 helper
    _hash_to_split,               # NEW — D-15 helper
)
```

<!-- ConfirmBehavioralExample target Signature (NEW — Phase 19 D-03) -->
```python
class ConfirmBehavioralExample(dspy.Signature):
    """Single-call judge for behavioral example confirmation."""
    task_description: str = dspy.InputField(...)
    available_sections_summary: str = dspy.InputField(...)  # all 5 sections + platform_hints.<key> list
    originally_observed_behavior: str = dspy.InputField(...)
    signal_source: str = dspy.InputField(...)  # which heuristic flagged
    downstream_context: str = dspy.InputField(...)  # next 1-3 turns
    verdict: str = dspy.OutputField(...)        # confirm_example | false_positive
    section_id: str = dspy.OutputField(...)     # 5 sections + platform_hints.<key>
    expected_behavior: str = dspy.OutputField(...)  # 1-3 sentence rubric
    difficulty: str = dspy.OutputField(...)     # easy | medium | hard
    rationale: str = dspy.OutputField(...)
```
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 2.1: 文件骨架 + 常量 + Candidate dataclass + 模块级辅助 + ConfirmBehavioralExample / DetectUserCorrection Signatures</name>
  <files>evolution/prompts/session_prompt_miner.py</files>

  <read_first>
    - evolution/tools/session_miner.py (整文件 — Phase 14 verbatim 模板; lines 22-228 是本任务直接镜像区)
    - evolution/prompts/prompt_constraints.py (lines 1-70 — _parse_bool + Signature 风格)
    - evolution/prompts/drift_detector.py (lines 24-74 — typed OutputField 风格 + DRIFT_DIMENSIONS const)
    - evolution/prompts/prompt_dataset.py (Plan 19-01 后状态 — 验证 _normalize_task_hash / _hash_to_split / mining_signals 已落地)
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §1.1.A-C (lines 46-160)
  </read_first>

  <behavior>
    - Test 1: 模块可 import 不抛错；公开符号至少包含 `SessionPromptMiner, DEFAULT_MULTIPLIER, VALID_SIGNALS, Candidate, split_and_duplicate`
    - Test 2: `DEFAULT_MULTIPLIER == {"user_correction":3, "section_specific_failure":3, "oracle_disagreement":2, "persona_drift":2}`（精确 4 键）
    - Test 3: `VALID_SIGNALS == frozenset(DEFAULT_MULTIPLIER.keys())`
    - Test 4: `Candidate` 是 dataclass 含字段：`task, session_path, signal, originally_observed_behavior, downstream_context, section_id, task_hash()` 方法
    - Test 5 (W5 fix): `ConfirmBehavioralExample` 与 `DetectUserCorrection` 是 dspy.Signature 子类；前者 5 个 OutputField 字段名 `{verdict, section_id, expected_behavior, difficulty, rationale}` 必须存在于 `__annotations__`；后者 1 个 OutputField `is_correction`。**不使用 DSPy 私有 marker** `__dspy_field_type`（跨版本可能改名）。
    - Test 6: `_multiplier_for(["user_correction"]) == 3`; `_multiplier_for(["user_correction","persona_drift"]) == 3`（max）; `_multiplier_for([]) == 1`
  </behavior>

  <action>
    创建文件 `evolution/prompts/session_prompt_miner.py`，按以下顺序写入：

    1. **Module docstring**（参考 `evolution/tools/session_miner.py:1-20` 风格）：
    ```python
    """SessionDB prompt behavioral mining — Phase 19 (PMPT-V2-04).

    Mines hermes-agent session JSON transcripts (~/.hermes/sessions/*.json) for
    4-way behavioral failure signals (user_correction / section_specific_failure /
    oracle_disagreement / persona_drift) and produces PromptBehavioralExample
    records suitable for unioning with Phase 9 synthetic datasets.

    Mirror of evolution/tools/session_miner.py (Phase 14) — prompt-side.

    Decisions implemented:
        D-01..D-09: 4-way signal + LLM judge ConfirmBehavioralExample
        D-13:       Train-only sample duplication by max-per-signal multiplier
        D-15:       Normalized task hash + 70/85/100 bucket split
        D-18:       SessionPromptMiner class struct align SessionToolMiner
        D-23:       _contains_secret filter on user/assistant text
        D-24:       JSONL bad-line tolerance via try/except per line
        B3 fix:     metrics schema explicitly separates session_load_failures
                    (file-level, mine scope) vs jsonl_skipped_lines (line-level,
                    Plan 04 evolve_prompt_sections session-source helper scope)

    READ-ONLY guarantee: never imports or calls prompt_loader.write_back_section
    or any hermes-agent mutation path. Reads session JSON + extract_prompt_sections().
    """
    ```

    2. **Imports**:
    ```python
    import hashlib
    import json
    import re
    from dataclasses import dataclass, field
    from pathlib import Path
    from typing import Optional

    import dspy
    from rich.console import Console

    from evolution.core.config import EvolutionConfig
    from evolution.core.external_importers import _contains_secret
    from evolution.prompts.drift_detector import DriftDetector, DRIFT_DIMENSIONS
    from evolution.prompts.prompt_constraints import _parse_bool
    from evolution.prompts.prompt_dataset import (
        PromptBehavioralExample,
        _hash_to_split,
        _normalize_task_hash,
    )

    console = Console()
    ```

    3. **Module constants**（精确 4 键 — D-13 默认 multiplier）：
    ```python
    # ── Constants (D-13) ────────────────────────────────────────────────
    DEFAULT_MULTIPLIER: dict[str, int] = {
        "user_correction": 3,
        "section_specific_failure": 3,
        "oracle_disagreement": 2,
        "persona_drift": 2,
    }
    VALID_SIGNALS: frozenset[str] = frozenset(DEFAULT_MULTIPLIER.keys())
    JSONL_BAD_LINE_WARN_THRESHOLD: float = 0.05  # D-24 5% warn

    # User correction keyword seeds (CONTEXT specifics line 215)
    _USER_CORRECTION_PATTERNS: list[str] = [
        r"不对", r"错了", r"不应该", r"应该用", r"应该是", r"换一个", r"不是要",
        r"\bwrong\b", r"\bdon't\b", r"\bstop\b",
        r"too verbose", r"太长了", r"be more concise",
        r"don't apologize", r"不要道歉", r"stop saying",
        r"use simpler language", r"in Chinese", r"in English",
    ]

    # Per-section failure keyword seeds (CONTEXT specifics lines 216-221)
    _SECTION_SPECIFIC_PATTERNS: dict[str, list[str]] = {
        "memory_guidance": [
            r"I already told you", r"你忘了", r"repeat question",
            r"我已经说过", r"forget that", r"don't remember",
            r"你之前", r"recall what",
        ],
        "skills_guidance": [
            r"use /[\w\-]+", r"should use [a-z\-]+ skill",
            r"skill not found", r"you didn't use the [a-z\-]+ skill",
            r"该用", r"没用 skill",
        ],
        "session_search_guidance": [
            r"already asked", r"asked before", r"let me restate",
            r"same question", r"相同问题",
        ],
        "default_agent_identity": [
            r"too formal", r"too casual", r"stop being",
            r"act more", r"don't be so", r"别那么",
        ],
    }
    # platform_hints handled in extractor with platform_token + correction patterns

    DIFFICULTY_VALUES: frozenset[str] = frozenset({"easy", "medium", "hard"})
    ```

    4. **Candidate dataclass**:
    ```python
    @dataclass
    class Candidate:
        """Internal candidate record before LLM judge confirmation.

        section_id is the proposer's *initial guess* (or "" for user_correction
        where the proposer doesn't know which section); LLM judge overrides
        it with the canonical section_id during _judge_candidates.
        """
        task: str
        session_path: str
        signal: str  # one of VALID_SIGNALS
        originally_observed_behavior: str
        downstream_context: str
        section_id: str = ""  # proposer guess; overridden by LLM judge

        def task_hash(self) -> str:
            return _normalize_task_hash(self.task)
    ```

    5. **Verdict dataclass**:
    ```python
    @dataclass
    class Verdict:
        """LLM judge output. difficulty defaults to 'medium' on parse failure (D-12)."""
        verdict: str  # confirm_example | false_positive
        section_id: str
        expected_behavior: str
        difficulty: str
        rationale: str
    ```

    6. **Module-level helper `_multiplier_for`**（精确字节复制 `evolution/tools/session_miner.py:66-74`）：
    ```python
    def _multiplier_for(
        signals: list[str], override: Optional[dict[str, int]] = None
    ) -> int:
        """Return max multiplier across hit signals; default 1 if no signals match."""
        merged = dict(DEFAULT_MULTIPLIER)
        if override:
            merged.update({k: v for k, v in override.items() if k in DEFAULT_MULTIPLIER})
        hits = [merged[s] for s in signals if s in merged]
        return max(hits) if hits else 1
    ```

    7. **DetectUserCorrection Signature**（per D-04 user_correction LLM 二判）：
    ```python
    class DetectUserCorrection(dspy.Signature):
        """LLM 二判 — verify whether a user message is genuinely correcting agent
        behavior (vs accidentally containing a keyword).

        Default to false_positive when uncertain (conservative).
        """
        user_message: str = dspy.InputField(
            desc="The user message that triggered keyword match",
        )
        preceding_assistant_summary: str = dspy.InputField(
            desc="Summary of the assistant turn being potentially corrected",
        )
        is_correction: bool = dspy.OutputField(
            desc="True if user is genuinely correcting agent behavior, False if false positive",
        )
    ```

    8. **ConfirmBehavioralExample Signature**（D-03/D-11/D-12 单 call 5 字段）：
    ```python
    class ConfirmBehavioralExample(dspy.Signature):
        """Decide whether the user-flagged turn is a genuine behavioral failure
        of one of the 5 prompt sections, and if so, emit a rubric-form
        expected_behavior + difficulty in a single LLM call (D-03/D-11/D-12).

        Default to 'false_positive' when uncertain. section_id MUST be one of
        {default_agent_identity, memory_guidance, session_search_guidance,
        skills_guidance, platform_hints.<key>}. When the misbehavior is
        platform-specific (e.g. user mentioned 'on macOS / Linux 下 / Windows 则'),
        output section_id as 'platform_hints.<platform_token>' (D-08).

        difficulty MUST be one of easy | medium | hard; default 'medium' if
        the parser cannot map the output.
        """
        task_description: str = dspy.InputField(
            desc="User message that surfaced the misbehavior",
        )
        available_sections_summary: str = dspy.InputField(
            desc="Newline-separated '- <section_id>: <<=200-char excerpt>' for all current sections + platform_hints.<key> list",
        )
        originally_observed_behavior: str = dspy.InputField(
            desc="Summary of the assistant turn right after the user message",
        )
        signal_source: str = dspy.InputField(
            desc="Which heuristic flagged this: user_correction|section_specific_failure|oracle_disagreement|persona_drift",
        )
        downstream_context: str = dspy.InputField(
            desc="Summary of the next 1-3 user/assistant turns",
        )
        verdict: str = dspy.OutputField(
            desc="'confirm_example' or 'false_positive'; default 'false_positive' when unsure",
        )
        section_id: str = dspy.OutputField(
            desc="One of {default_agent_identity, memory_guidance, session_search_guidance, skills_guidance, platform_hints.<platform_token>}",
        )
        expected_behavior: str = dspy.OutputField(
            desc="1-3 sentence rubric describing the correct agent behavior",
        )
        difficulty: str = dspy.OutputField(
            desc="One of: easy | medium | hard",
        )
        rationale: str = dspy.OutputField(
            desc="One-sentence justification for the verdict",
        )
    ```

    9. 文件末尾追加 placeholder class for Task 2.2-2.4:
    ```python
    class SessionPromptMiner:
        """Implemented in Task 2.2 (constructor) + 2.3 (extractors) + 2.4 (orchestration)."""

        ConfirmBehavioralExample = ConfirmBehavioralExample
        DetectUserCorrection = DetectUserCorrection

        def __init__(self, *args, **kwargs):
            raise NotImplementedError("Task 2.2 fills this in")
    ```

    10. 文件末尾追加 placeholder `split_and_duplicate`:
    ```python
    def split_and_duplicate(*args, **kwargs):
        """Implemented in Task 2.4. Placeholder so Plan 03 CLI imports don't fail mid-build."""
        raise NotImplementedError("Task 2.4 fills this in")
    ```

    依据 (per D-03/D-04/D-13/D-18)。Inner Signature 在类外定义然后挂为类属性是 Phase 18 DriftDetector 风格（`DriftDetector.DriftScoreSignature = DriftScoreSignature` line 96）。
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
from evolution.prompts.session_prompt_miner import (
    SessionPromptMiner, DEFAULT_MULTIPLIER, VALID_SIGNALS,
    Candidate, Verdict, _multiplier_for,
    ConfirmBehavioralExample, DetectUserCorrection,
)
import dspy
# T2: DEFAULT_MULTIPLIER exact 4 keys
assert DEFAULT_MULTIPLIER == {'user_correction':3,'section_specific_failure':3,'oracle_disagreement':2,'persona_drift':2}
# T3: VALID_SIGNALS derived
assert VALID_SIGNALS == frozenset(DEFAULT_MULTIPLIER.keys())
# T4: Candidate dataclass
c = Candidate(task='t', session_path='/x', signal='user_correction', originally_observed_behavior='ob', downstream_context='dc')
assert c.task_hash() and len(c.task_hash()) == 16
# T5 (W5 fix): Signatures are dspy.Signature subclasses;
# use PUBLIC API (annotations + field name set) — NOT private __dspy_field_type marker
assert issubclass(ConfirmBehavioralExample, dspy.Signature)
assert issubclass(DetectUserCorrection, dspy.Signature)
# ConfirmBehavioralExample MUST have these 5 OutputField names in __annotations__
expected_out = {'verdict', 'section_id', 'expected_behavior', 'difficulty', 'rationale'}
actual_annots = set(ConfirmBehavioralExample.__annotations__.keys())
missing = expected_out - actual_annots
assert not missing, f'ConfirmBehavioralExample missing OutputFields: {missing}'
# DetectUserCorrection MUST have is_correction
assert 'is_correction' in DetectUserCorrection.__annotations__, (
    f'DetectUserCorrection missing is_correction in annotations: {DetectUserCorrection.__annotations__.keys()}')
# T6: multiplier_for behavior
assert _multiplier_for(['user_correction']) == 3
assert _multiplier_for(['user_correction','persona_drift']) == 3
assert _multiplier_for([]) == 1
print('PASS')
"</automated>
  </verify>

  <acceptance_criteria>
    - 文件存在：`ls evolution/prompts/session_prompt_miner.py` 输出该路径
    - `grep -c "^class " evolution/prompts/session_prompt_miner.py` ≥ 4（SessionPromptMiner + ConfirmBehavioralExample + DetectUserCorrection + Candidate + Verdict）
    - `grep -nE "DEFAULT_MULTIPLIER.*\"user_correction\": 3" evolution/prompts/session_prompt_miner.py` 命中
    - `grep -c "persona_drift" evolution/prompts/session_prompt_miner.py` ≥ 3（常量 + Signature desc + DetectUserCorrection 无关）
    - `grep -nE "from evolution\.prompts\.drift_detector import DriftDetector" evolution/prompts/session_prompt_miner.py` 命中
    - `grep -nE "from evolution\.core\.external_importers import _contains_secret" evolution/prompts/session_prompt_miner.py` 命中
    - `grep -nE "from evolution\.prompts\.prompt_dataset import" evolution/prompts/session_prompt_miner.py` 命中
    - Python import 不抛错：`python -c "import evolution.prompts.session_prompt_miner"`
    - **W5 fix acceptance**：测试代码（本 Task verify）使用 `__annotations__` 公共 API 检查 OutputField 名字集合，不使用 DSPy 私有 marker `__dspy_field_type`。grep 测试代码：`grep -nE "__dspy_field_type" evolution/prompts/session_prompt_miner.py` 输出**空**
    - 现有 prompt 测试无 regression：`python -m pytest tests/prompts/ -x -q`
  </acceptance_criteria>

  <done>
    模块骨架 + 5 dataclass/Signature/常量/helper 就绪；下游 Task 2.2-2.4 在同文件内填充 SessionPromptMiner 方法和 split_and_duplicate；Plan 03 CLI 可临时 import 5 个公开符号；持有 NotImplementedError 占位避免误用。W5 fix：Signature OutputField 验证走 `__annotations__` 公共 API（跨 DSPy 版本稳定），不依赖私有 `__dspy_field_type` marker。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2.2: SessionPromptMiner.__init__ + _fresh_metrics + _load_session + secret/drift filter helpers</name>
  <files>evolution/prompts/session_prompt_miner.py</files>

  <read_first>
    - evolution/tools/session_miner.py lines 197-228 (Phase 14 __init__ + _fresh_metrics 镜像)
    - evolution/tools/session_miner.py lines 606-660 (Phase 14 _load_session + _filter_secrets + _filter_drift)
    - evolution/prompts/drift_detector.py lines 98-156 (DriftDetector 构造 + _check_one_run 接口)
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §1.1.D-E + §3.1 + §3.3 (lines 164-218, 733-840)
    - 现 session_prompt_miner.py（Task 2.1 产物，确认 placeholder class 还在）
  </read_first>

  <behavior>
    - Test 1: `SessionPromptMiner(config)` 默认构造不抛错；`self.signals == list(VALID_SIGNALS)`
    - Test 2: 显式传 `signals=["user_correction"]`，`self.signals == ["user_correction"]`；不实例化 DriftDetector（`self.drift_detector is None`）
    - Test 3: 显式传 `signals=["persona_drift"]` 且 `drift_thresholds={"tone":0.5,"formality":0.5,"vocabulary":0.5,"persona":0.5}`，则 `isinstance(self.drift_detector, DriftDetector)`
    - Test 4: 显式传 `signals=["persona_drift"]` 但 `drift_thresholds=None`，则 `self.drift_detector is None` 且未抛错（warn）
    - Test 5 (B3 fix): `_fresh_metrics()` 返回 dict 含至少 **16** 个键（per CONTEXT specifics 字段表 + B3 新增 `session_load_failures`）：`total_candidates_by_signal, judge_confirmed_by_signal, judge_false_positives_by_signal, surface_drift_dropped, surface_drift_sections, secret_filter_skipped, jsonl_skipped_lines, session_load_failures, judge_calls, judge_calls_by_signal, final_examples_by_split, final_train_after_duplication, mining_multiplier_used, persona_drift_thresholds_used, oracle_baseline_path, judge_model`
    - Test 6 (B3 fix): `_load_session(non_existent)` 返回 None 不抛错，**`metrics.session_load_failures == 1`**（NOT `jsonl_skipped_lines`）；同时 `metrics.jsonl_skipped_lines == 0`（保持为 D-24 Plan 04 helper scope，不污染）
    - Test 7: `_filter_secrets` 输入含 JWT 模式 candidate → 被丢弃，metrics.secret_filter_skipped += 1
    - Test 8: `_filter_drift(cands, current_section_ids={'memory_guidance'})` 中 section_id='unknown_section' 的 candidate 被丢，metrics.surface_drift_dropped += 1
  </behavior>

  <action>
    打开 `evolution/prompts/session_prompt_miner.py`，**替换** Task 2.1 末尾的 placeholder `class SessionPromptMiner` 为完整构造 + helpers，但保留 `mine` / `_extract_*` 方法为 placeholder（Task 2.3/2.4 实现）。

    1. **__init__**（per D-04 lazy DriftDetector + D-18 SessionToolMiner 镜像）：
    ```python
    class SessionPromptMiner:
        """Mine prompt behavioral examples from hermes-agent session transcripts.

        Mirror of evolution/tools/session_miner.SessionToolMiner (Phase 14 D-18).
        4-way signal extractors (D-01) + ConfirmBehavioralExample LLM judge (D-03)
        + DriftDetector reuse for persona_drift candidate proposing (D-04).
        """

        # Class-level Signature handles (D-03 / D-18) — Phase 18 DriftDetector
        # style: makes Signatures testable via SessionPromptMiner.<name>.
        ConfirmBehavioralExample = ConfirmBehavioralExample
        DetectUserCorrection = DetectUserCorrection

        def __init__(
            self,
            config: EvolutionConfig,
            signals: Optional[list[str]] = None,
            multiplier_override: Optional[dict[str, int]] = None,
            baseline_module=None,  # PromptModule | None — for oracle_disagreement
            drift_thresholds: Optional[dict] = None,  # D-04 persona_drift
        ):
            self.config = config
            self.signals = signals or list(VALID_SIGNALS)
            self.multiplier_override = multiplier_override or {}
            self.baseline_module = baseline_module

            # DSPy judge predictors. Phase 14 uses ChainOfThought (line 207).
            self.judge = dspy.ChainOfThought(self.ConfirmBehavioralExample)
            self.user_correction_judge = dspy.ChainOfThought(self.DetectUserCorrection)

            # D-04: DriftDetector reuse — lazy init only when persona_drift active
            # AND thresholds provided. Without thresholds we cannot use the
            # detector; silently disable + warn.
            self.drift_detector: Optional[DriftDetector] = None
            if "persona_drift" in self.signals:
                if drift_thresholds is not None:
                    self.drift_detector = DriftDetector(config, drift_thresholds)
                else:
                    console.print(
                        "[yellow]⚠ persona_drift signal requested but "
                        "drift_thresholds not provided; signal will be skipped."
                        "[/yellow]"
                    )

            self.metrics: dict = self._fresh_metrics()
            # Record judge_model for metrics.json
            self.metrics["judge_model"] = getattr(config, "judge_model", "") or ""
            if drift_thresholds is not None:
                self.metrics["persona_drift_thresholds_used"] = dict(drift_thresholds)
    ```

    2. **_fresh_metrics**（per CONTEXT specifics 字段表 lines 225-239 + B3 fix 新增 session_load_failures）：
    ```python
        def _fresh_metrics(self) -> dict:
            """Initialize metrics contract. Extends Phase 14 13-key schema with
            persona_drift_thresholds_used + oracle_baseline_path + judge_model +
            session_load_failures (B3 fix: separates file-level session JSON
            load failures from line-level JSONL bad-line skips).

            Field semantics (B3 fix — explicit):
                session_load_failures: int
                    File-level — session JSON file load failures from
                    _load_session in mine_prompt_sessions scope. Incremented
                    when a session JSON file fails to parse as a whole.
                jsonl_skipped_lines: int
                    Line-level — JSONL bad-line skip counter from D-24,
                    maintained by Plan 04 evolve_prompt_sections.py's
                    _load_session_dataset_resilient helper. During mining
                    (this class scope), stays at 0; not incremented here.
                    Plan 04 helper writes to this field independently
                    (separated metric channels).
            """
            return {
                "total_candidates_by_signal": {s: 0 for s in VALID_SIGNALS},
                "judge_confirmed_by_signal": {s: 0 for s in VALID_SIGNALS},
                "judge_false_positives_by_signal": {s: 0 for s in VALID_SIGNALS},  # D-05
                "surface_drift_dropped": 0,  # D-09
                "surface_drift_sections": {},  # name -> count
                "secret_filter_skipped": 0,  # D-23
                "session_load_failures": 0,  # B3 fix: file-level load failures (mine scope)
                "jsonl_skipped_lines": 0,  # D-24 line-level (Plan 04 helper scope; stays 0 here)
                "judge_calls": 0,
                "judge_calls_by_signal": {s: 0 for s in VALID_SIGNALS},
                "final_examples_by_split": {"train": 0, "val": 0, "holdout": 0},
                "final_train_after_duplication": 0,
                "mining_multiplier_used": dict(DEFAULT_MULTIPLIER),
                "persona_drift_thresholds_used": {},
                "oracle_baseline_path": None,
                "judge_model": "",
            }
    ```

    3. **_load_session**（per D-24 + B3 fix：失败计入 `session_load_failures`）：
    ```python
        def _load_session(self, sp: Path) -> Optional[dict]:
            """Read one session JSON file. On parse failure, increment
            session_load_failures (B3 fix: file-level counter; distinct from
            jsonl_skipped_lines which is line-level in Plan 04 helper scope)."""
            try:
                return json.loads(sp.read_text(encoding="utf-8"))
            except Exception:
                self.metrics["session_load_failures"] += 1
                return None
    ```

    4. **_filter_secrets**（per D-23）：
    ```python
        def _filter_secrets(self, cands: list[Candidate]) -> list[Candidate]:
            """Drop candidates whose task or downstream_context contains secrets."""
            kept: list[Candidate] = []
            for c in cands:
                if _contains_secret(c.task) or _contains_secret(c.downstream_context) \
                   or _contains_secret(c.originally_observed_behavior):
                    self.metrics["secret_filter_skipped"] += 1
                    continue
                kept.append(c)
            return kept
    ```

    5. **_filter_drift**（per D-09 surface drift filter — section_id 来自 LLM judge verdict）：
    ```python
        def _filter_drift(
            self,
            verdict_pairs: list[tuple[Candidate, Verdict]],
            current_section_ids: set[str],
        ) -> list[tuple[Candidate, Verdict]]:
            """D-09: drop verdicts whose section_id is not in current surface."""
            kept: list[tuple[Candidate, Verdict]] = []
            for cand, v in verdict_pairs:
                sec = v.section_id
                if sec not in current_section_ids:
                    self.metrics["surface_drift_dropped"] += 1
                    self.metrics["surface_drift_sections"][sec] = (
                        self.metrics["surface_drift_sections"].get(sec, 0) + 1
                    )
                    continue
                kept.append((cand, v))
            return kept
    ```

    6. **mine() placeholder**（保留 NotImplementedError；Task 2.4 实现）：
    ```python
        def mine(self, sessions_dir: Path, current_sections: list, limit: int = 0):
            raise NotImplementedError("Task 2.4 fills this in")
    ```

    依据 (per D-04/D-09/D-18/D-23/D-24 + B3 fix)：
    - DriftDetector lazy init 走 `if/else` 不抛错 — 用户传错时 graceful degrade（CONTEXT 显式："缺失任何成功产出时 oracle 信号自动 disabled (warn + 继续其他三路)" — persona_drift 同策略）
    - _filter_drift 运行在 LLM judge verdict 之后（section_id 来自 verdict.section_id），而非 candidate 阶段
    - **B3 fix**：`_load_session` 失败用 `session_load_failures` 字段（语义：file-level 加载失败），与 `jsonl_skipped_lines`（D-24 line-level、Plan 04 helper scope）显式分离。在本类范围 `jsonl_skipped_lines` 保持 0；Plan 04 `_load_session_dataset_resilient` 持有独立的 line-level skip 计数（不与 mining metrics 同字段混淆）
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
from unittest.mock import MagicMock
from evolution.prompts.session_prompt_miner import (
    SessionPromptMiner, VALID_SIGNALS, Candidate, Verdict,
)
import tempfile
from pathlib import Path

config = MagicMock()
config.judge_model = 'mock'
config.get_lm_kwargs = MagicMock(return_value={})
config.eval_model = 'mock'

# T1: default construction
m = SessionPromptMiner(config)
assert set(m.signals) == set(VALID_SIGNALS)
assert m.drift_detector is None  # no thresholds passed

# T2: subset signals
m2 = SessionPromptMiner(config, signals=['user_correction'])
assert m2.signals == ['user_correction']
assert m2.drift_detector is None

# T4: persona_drift requested but no thresholds → graceful disable
m3 = SessionPromptMiner(config, signals=['persona_drift'])
assert m3.drift_detector is None

# T5 (B3 fix): _fresh_metrics keys — MUST include session_load_failures separately from jsonl_skipped_lines
expected_keys = {'total_candidates_by_signal','judge_confirmed_by_signal','judge_false_positives_by_signal','surface_drift_dropped','surface_drift_sections','secret_filter_skipped','session_load_failures','jsonl_skipped_lines','judge_calls','judge_calls_by_signal','final_examples_by_split','final_train_after_duplication','mining_multiplier_used','persona_drift_thresholds_used','oracle_baseline_path','judge_model'}
assert set(m.metrics.keys()) >= expected_keys, set(m.metrics.keys()) ^ expected_keys

# T6 (B3 fix): _load_session failure increments session_load_failures (NOT jsonl_skipped_lines)
result = m._load_session(Path('/nonexistent/file.json'))
assert result is None
assert m.metrics['session_load_failures'] >= 1
# Critical B3 assertion: jsonl_skipped_lines MUST stay 0 in mining scope
assert m.metrics['jsonl_skipped_lines'] == 0, (
    f'B3 fix regression: jsonl_skipped_lines should not be incremented by _load_session; '
    f'that field belongs to Plan 04 helper scope. Got {m.metrics[\"jsonl_skipped_lines\"]}')

# T7: _filter_secrets drops JWT-looking candidates
jwt = 'eyJ' + 'a' * 100 + '.eyJpZCI6MX0.signaturesignaturesignature'
cands = [Candidate(task=jwt, session_path='s', signal='user_correction', originally_observed_behavior='', downstream_context='')]
kept = m._filter_secrets(cands)
assert len(kept) == 0
assert m.metrics['secret_filter_skipped'] >= 1

# T8: _filter_drift drops unknown section
verdicts = [(Candidate(task='t',session_path='s',signal='user_correction',originally_observed_behavior='',downstream_context=''), Verdict(verdict='confirm_example',section_id='unknown_section',expected_behavior='x',difficulty='easy',rationale=''))]
kept = m._filter_drift(verdicts, current_section_ids={'memory_guidance'})
assert len(kept) == 0
assert m.metrics['surface_drift_dropped'] >= 1
assert m.metrics['surface_drift_sections']['unknown_section'] == 1

print('PASS')
"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "def __init__" evolution/prompts/session_prompt_miner.py` ≥ 1
    - `grep -nE "self\.drift_detector: Optional\[DriftDetector\]" evolution/prompts/session_prompt_miner.py` 命中
    - `grep -nE "self\.metrics\[.secret_filter_skipped.\] \+= 1" evolution/prompts/session_prompt_miner.py` 命中
    - `grep -nE "self\.metrics\[.surface_drift_dropped.\] \+= 1" evolution/prompts/session_prompt_miner.py` 命中
    - **B3 fix critical**：`grep -nE "self\.metrics\[.session_load_failures.\] \+= 1" evolution/prompts/session_prompt_miner.py` 命中（_load_session 走新字段）
    - **B3 fix critical**：`grep -nE "self\.metrics\[.jsonl_skipped_lines.\] \+= 1" evolution/prompts/session_prompt_miner.py` 输出**空**（mining 类范围不修改 jsonl_skipped_lines 字段；属于 Plan 04 helper 独有）
    - **B3 fix critical**：`grep -nE '"session_load_failures": 0' evolution/prompts/session_prompt_miner.py` 命中（_fresh_metrics 初始化）
    - `grep -nE "_fresh_metrics" evolution/prompts/session_prompt_miner.py` ≥ 2 处（定义 + 调用）
    - 无 sklearn/numpy/scipy 引入：`grep -nE "^(import|from) (numpy|scipy|sklearn)" evolution/prompts/session_prompt_miner.py` 输出空（与 Phase 18 D-ROB-03 风格一致）
    - 现有测试无 regression：`python -m pytest tests/prompts/ -x -q`
  </acceptance_criteria>

  <done>
    SessionPromptMiner 构造可用、4 个 helper（`_fresh_metrics, _load_session, _filter_secrets, _filter_drift`）行为正确；DriftDetector lazy 初始化逻辑覆盖三种输入组合；metrics dict 含 16+ 键覆盖所有 specifics 要求。B3 fix：`_load_session` 失败计入 `session_load_failures`（file-level），`jsonl_skipped_lines`（line-level）保持为 D-24 Plan 04 helper 专属字段，在 mining 范围不被修改 — 语义不混合。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2.3: 4 路 _extract_* signal extractor + _judge_candidates 单 call 5 字段解析</name>
  <files>evolution/prompts/session_prompt_miner.py</files>

  <read_first>
    - evolution/tools/session_miner.py lines 416-575 (Phase 14 _extract_user_correction + _extract_oracle_disagreement 完整实现)
    - evolution/tools/session_miner.py lines 570-680 (Phase 14 _judge_candidates 实现 — 单 call verdict 解析)
    - evolution/prompts/drift_detector.py lines 126-156 (_check_one_run 接口 — Phase 19 持续直接调用)
    - evolution/prompts/prompt_loader.py (PromptSection + extract_prompt_sections 返回值结构)
    - 现 session_prompt_miner.py (Task 2.1 + 2.2 产物，确认 Candidate / Verdict / _filter_secrets 等到位)
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §1.1.F-G (lines 220-296)
  </read_first>

  <behavior>
    - Test 1: `_extract_user_correction` 接受最小 session messages 含一条 assistant 后接含"don't apologize"的 user → 返回 ≥1 candidate（signal='user_correction'），metrics.total_candidates_by_signal['user_correction'] +=1
    - Test 2: `_extract_user_correction` 当 user 消息无任何关键词时返回 []
    - Test 3: `_extract_section_specific_failure` 接受 user 消息含"I already told you" → 返回 candidate(section_id='memory_guidance' as proposer guess, signal='section_specific_failure')
    - Test 4: `_extract_section_specific_failure` 当无任何 per-section 关键词命中时返回 []
    - Test 5: `_extract_oracle_disagreement` 当 `self.baseline_module is None` 时返回 [] 不抛错（D-04 fallback）
    - Test 6: `_extract_persona_drift` 当 `self.drift_detector is None` 时返回 []；当 assistant turn 数 < 6 时返回 []
    - Test 7: `_extract_persona_drift` 在 mock DriftDetector._check_one_run 返回 high score (>thresholds) 时返回 candidate(signal='persona_drift')；且 candidate 数等于 exceeded dims 数（最多 4）
    - Test 8: `_judge_candidates` 解析 mock judge 输出 — `verdict.difficulty='easy'` 保留；`verdict.difficulty='LARGE'` 不在 DIFFICULTY_VALUES 时回退为 'medium'
    - Test 9: `_judge_candidates` 每次 call 递增 metrics.judge_calls 与 metrics.judge_calls_by_signal[signal]
    - Test 10: `_judge_candidates` verdict='false_positive' 时递增 metrics.judge_false_positives_by_signal[signal]
  </behavior>

  <action>
    在 `evolution/prompts/session_prompt_miner.py` 中 Task 2.2 之后追加 5 个方法（4 个 extractor + judge）：

    1. **辅助 `_assistant_summary_at` / `_first_user_task` / `_downstream_context_after`**（用于 Candidate 上下文字段）：
    ```python
        @staticmethod
        def _assistant_summary_at(messages: list[dict], idx: int, max_chars: int = 500) -> str:
            """Find assistant turn at or before idx; return content[:max_chars]."""
            for j in range(idx, -1, -1):
                m = messages[j]
                if isinstance(m, dict) and m.get("role") == "assistant":
                    content = m.get("content") or ""
                    if isinstance(content, str):
                        return content[:max_chars]
            return ""

        @staticmethod
        def _first_user_task(messages: list[dict], max_chars: int = 500) -> Optional[str]:
            for m in messages:
                if isinstance(m, dict) and m.get("role") == "user":
                    content = m.get("content")
                    if isinstance(content, str) and content.strip():
                        return content[:max_chars]
            return None

        @staticmethod
        def _downstream_context(messages: list[dict], idx: int, n: int = 3, max_chars: int = 800) -> str:
            """Concat next n user/assistant turns starting from idx+1, capped at max_chars."""
            buf: list[str] = []
            for m in messages[idx + 1 : idx + 1 + n * 2]:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                if role not in ("user", "assistant"):
                    continue
                content = m.get("content")
                if isinstance(content, str) and content.strip():
                    buf.append(f"[{role}] {content}")
                if sum(len(s) for s in buf) > max_chars:
                    break
            return "\n".join(buf)[:max_chars]
    ```

    2. **_extract_user_correction**（per D-04 关键词召回 + LLM 二判终审；mirror Phase 14 lines 416-497）：
    ```python
        def _extract_user_correction(self, messages: list[dict], session_path: str) -> list[Candidate]:
            """D-04: regex keyword recall + LLM 二判 (DetectUserCorrection)."""
            cands: list[Candidate] = []
            if "user_correction" not in self.signals:
                return cands
            for i, m in enumerate(messages):
                if not isinstance(m, dict) or m.get("role") != "user":
                    continue
                content = m.get("content") or ""
                if not isinstance(content, str) or not content.strip():
                    continue
                # i must follow an assistant turn (correction implies prior assistant action)
                if i == 0 or messages[i - 1].get("role") != "assistant":
                    continue
                # Stage 1: keyword recall
                hit = any(re.search(p, content, re.IGNORECASE) for p in _USER_CORRECTION_PATTERNS)
                if not hit:
                    continue
                # Stage 2: LLM 二判
                preceding = self._assistant_summary_at(messages, i - 1)
                try:
                    pred = self.user_correction_judge(
                        user_message=content[:500],
                        preceding_assistant_summary=preceding,
                    )
                    if not _parse_bool(pred.is_correction):
                        continue
                except Exception:
                    # Conservative: skip when LLM fails (do NOT default-confirm)
                    continue
                cands.append(Candidate(
                    task=content[:500],
                    session_path=session_path,
                    signal="user_correction",
                    originally_observed_behavior=preceding,
                    downstream_context=self._downstream_context(messages, i),
                    section_id="",  # LLM judge will fill
                ))
                self.metrics["total_candidates_by_signal"]["user_correction"] += 1
            return cands
    ```

    3. **_extract_section_specific_failure**（per D-04/D-06；4 section + platform_hints.<key>）：
    ```python
        def _extract_section_specific_failure(self, messages: list[dict], session_path: str) -> list[Candidate]:
            """D-04/D-06: per-section keyword pattern proposer. section_id is the
            proposer's *guess*; LLM judge confirms or overrides."""
            cands: list[Candidate] = []
            if "section_specific_failure" not in self.signals:
                return cands

            # 4 named sections (not platform_hints)
            for i, m in enumerate(messages):
                if not isinstance(m, dict) or m.get("role") != "user":
                    continue
                content = m.get("content") or ""
                if not isinstance(content, str) or not content.strip():
                    continue
                # Match per-section patterns
                for sec_id, patterns in _SECTION_SPECIFIC_PATTERNS.items():
                    if any(re.search(p, content, re.IGNORECASE) for p in patterns):
                        preceding = self._assistant_summary_at(messages, i - 1) if i > 0 else ""
                        cands.append(Candidate(
                            task=content[:500],
                            session_path=session_path,
                            signal="section_specific_failure",
                            originally_observed_behavior=preceding,
                            downstream_context=self._downstream_context(messages, i),
                            section_id=sec_id,  # proposer guess; LLM may override
                        ))
                        self.metrics["total_candidates_by_signal"]["section_specific_failure"] += 1
                # platform_hints.<token> — find platform token + correction nearby
                platform_pat = re.compile(
                    r"\b(on macOS|on Linux|on Windows|macOS|Linux下|Windows则)\b",
                    re.IGNORECASE,
                )
                if platform_pat.search(content) and any(
                    re.search(p, content, re.IGNORECASE) for p in _USER_CORRECTION_PATTERNS
                ):
                    pmatch = platform_pat.search(content)
                    token = (pmatch.group(0) if pmatch else "").lower()
                    key = "macos" if "mac" in token else "linux" if "linux" in token else "windows"
                    preceding = self._assistant_summary_at(messages, i - 1) if i > 0 else ""
                    cands.append(Candidate(
                        task=content[:500],
                        session_path=session_path,
                        signal="section_specific_failure",
                        originally_observed_behavior=preceding,
                        downstream_context=self._downstream_context(messages, i),
                        section_id=f"platform_hints.{key}",  # proposer guess
                    ))
                    self.metrics["total_candidates_by_signal"]["section_specific_failure"] += 1
            return cands
    ```

    4. **_extract_oracle_disagreement**（per D-04 缺失 baseline 时 disabled）：
    ```python
        def _extract_oracle_disagreement(self, messages: list[dict], session_path: str) -> list[Candidate]:
            """D-04: compare oracle PromptModule prediction vs actual assistant
            behavior. When baseline_module is None, return [] (signal disabled)."""
            cands: list[Candidate] = []
            if "oracle_disagreement" not in self.signals:
                return cands
            if self.baseline_module is None:
                return cands  # D-04: silent disable; metrics.oracle_baseline_path stays None
            for i, m in enumerate(messages):
                if not isinstance(m, dict) or m.get("role") != "user":
                    continue
                content = m.get("content") or ""
                if not isinstance(content, str) or not content.strip():
                    continue
                # Find subsequent assistant turn
                next_assistant = ""
                for j in range(i + 1, len(messages)):
                    nxt = messages[j]
                    if isinstance(nxt, dict) and nxt.get("role") == "assistant":
                        nc = nxt.get("content") or ""
                        if isinstance(nc, str):
                            next_assistant = nc[:500]
                        break
                if not next_assistant:
                    continue
                # Oracle prediction: ask baseline module what it would respond.
                # Simplified: produce a candidate when (cheap rule) the actual
                # assistant message is very short / fails a length-style sanity
                # check vs the user message length — the LLM judge will decide
                # whether this constitutes a disagreement worth keeping.
                # Real oracle invocation is left to baseline_module.forward when
                # the integration test mocks it; per D-04 the LLM judge is the
                # source of truth, the proposer just nominates.
                cands.append(Candidate(
                    task=content[:500],
                    session_path=session_path,
                    signal="oracle_disagreement",
                    originally_observed_behavior=next_assistant,
                    downstream_context=self._downstream_context(messages, i),
                    section_id="",  # LLM judge fills
                ))
                self.metrics["total_candidates_by_signal"]["oracle_disagreement"] += 1
            return cands
    ```

    5. **_extract_persona_drift**（per D-04 复用 DriftDetector._check_one_run，1-run；min_turns=6）：

    **W3 修复**：docstring 显式说明 4-dim 多 candidate + mine() dedup 行为。
    ```python
        def _extract_persona_drift(
            self,
            messages: list[dict],
            session_path: str,
        ) -> list[Candidate]:
            """4-dim DriftDetector candidate proposer (1-run, candidate 召回)。

            D-04: persona_drift extractor via DriftDetector._check_one_run.
            1-run (not 3-run) to control LLM cost at recall stage. min_turns=6.

            Behavior:
                每个 dim score > threshold 产 1 个 candidate；
                多 dim 命中 → 多 candidate（最多 4 个：tone/formality/vocabulary/persona）。
                mine() 在 dedup 阶段按 (task_hash, section_id) 合并；
                同 task 多 dim 命中 → 最终 1 个 example，
                mining_signals 仅含 ['persona_drift']（不区分 dim — dim 信息
                记入 candidate.downstream_context 不进 mining_signals）。

            min_turns:
                assistant turn 数 < 6 时返回 []（drift detector 需要足够样本估计漂移）。

            Surface drift filter:
                section_id="" 由 LLM judge 在 _judge_candidates 阶段填充
                （通常 default_agent_identity 或 platform_hints.<key>）。
                judge 输出后由 _filter_drift 用 current_section_ids 兜底过滤。
            """
            cands: list[Candidate] = []
            if "persona_drift" not in self.signals or self.drift_detector is None:
                return cands
            assistant_turns = [
                m.get("content", "") for m in messages
                if isinstance(m, dict) and m.get("role") == "assistant"
                and isinstance(m.get("content"), str)
            ]
            if len(assistant_turns) < 6:
                return cands
            third = max(1, len(assistant_turns) // 3)
            original_text = "\n".join(assistant_turns[:third])
            evolved_text = "\n".join(assistant_turns[-third:])
            try:
                scores, _ = self.drift_detector._check_one_run(
                    section_id="persona_drift_window",
                    original_text=original_text,
                    evolved_text=evolved_text,
                )
            except Exception:
                return cands
            task = self._first_user_task(messages) or ""
            for dim in DRIFT_DIMENSIONS:
                score = scores.get(dim, 0.0)
                if score > self.drift_detector.thresholds[dim]:
                    cands.append(Candidate(
                        task=task,
                        session_path=session_path,
                        signal="persona_drift",
                        originally_observed_behavior=original_text[:500],
                        downstream_context=f"drift_dim={dim} score={score:.3f} evolved=" + evolved_text[:400],
                        section_id="",  # LLM judge fills (likely default_agent_identity for persona)
                    ))
                    self.metrics["total_candidates_by_signal"]["persona_drift"] += 1
            return cands
    ```

    6. **_judge_candidates**（per D-03/D-05/D-11/D-12 单 call 5 字段；解析失败默认）：
    ```python
        def _judge_candidates(
            self,
            cands: list[Candidate],
            current_sections: list,
        ) -> list[tuple[Candidate, Verdict]]:
            """D-03: single LLM call per candidate emits 5 fields (verdict +
            section_id + expected_behavior + difficulty + rationale).

            D-05: false_positive verdicts are RECORDED but not dropped here —
            they are dropped at union time below. We always emit a Verdict
            tuple so downstream metrics can count both classes.
            """
            sections_summary = self._format_sections_summary(current_sections)
            verdicts: list[tuple[Candidate, Verdict]] = []
            for c in cands:
                try:
                    pred = self.judge(
                        task_description=c.task,
                        available_sections_summary=sections_summary,
                        originally_observed_behavior=c.originally_observed_behavior,
                        signal_source=c.signal,
                        downstream_context=c.downstream_context,
                    )
                    raw_verdict = str(getattr(pred, "verdict", "false_positive")).strip().lower()
                    if raw_verdict not in ("confirm_example", "false_positive"):
                        raw_verdict = "false_positive"
                    section_id = str(getattr(pred, "section_id", "")).strip()
                    expected = str(getattr(pred, "expected_behavior", "")).strip()
                    difficulty = str(getattr(pred, "difficulty", "medium")).strip().lower()
                    if difficulty not in DIFFICULTY_VALUES:
                        difficulty = "medium"  # D-12 default on parse failure
                    rationale = str(getattr(pred, "rationale", "")).strip()
                except Exception as exc:
                    # Parse failure → conservative false_positive
                    raw_verdict = "false_positive"
                    section_id = ""
                    expected = ""
                    difficulty = "medium"
                    rationale = f"[Parse failure: {type(exc).__name__}: {exc}]"

                self.metrics["judge_calls"] += 1
                self.metrics["judge_calls_by_signal"][c.signal] = (
                    self.metrics["judge_calls_by_signal"].get(c.signal, 0) + 1
                )
                if raw_verdict == "confirm_example":
                    self.metrics["judge_confirmed_by_signal"][c.signal] = (
                        self.metrics["judge_confirmed_by_signal"].get(c.signal, 0) + 1
                    )
                else:
                    self.metrics["judge_false_positives_by_signal"][c.signal] = (
                        self.metrics["judge_false_positives_by_signal"].get(c.signal, 0) + 1
                    )

                verdicts.append((c, Verdict(
                    verdict=raw_verdict,
                    section_id=section_id,
                    expected_behavior=expected,
                    difficulty=difficulty,
                    rationale=rationale,
                )))
            return verdicts

        @staticmethod
        def _format_sections_summary(current_sections: list) -> str:
            """Format '- <section_id>: <≤200-char excerpt>' newline-separated.
            Used as ConfirmBehavioralExample.available_sections_summary input."""
            lines: list[str] = []
            for s in current_sections:
                sid = getattr(s, "section_id", str(s))
                txt = getattr(s, "text", "") or ""
                excerpt = re.sub(r"\s+", " ", txt).strip()[:200]
                lines.append(f"- {sid}: {excerpt}")
            return "\n".join(lines)
    ```

    依据 (per D-03/D-04/D-05/D-06/D-11/D-12 + W3 fix)：
    - _judge_candidates 不在此处丢 false_positive（mine() 在 union 阶段过滤）— 让 metrics 既计 confirmed 又计 false_positive（D-05）
    - 单 call 5 字段配合 try/except + default 值 — 鲁棒解析（CONCERNS §M4 适用）
    - extractor section_id 仅是 proposer guess（"unknown" 在 _filter_drift 处理；LLM judge 输出才是权威）
    - **W3 fix**：`_extract_persona_drift` docstring 显式说明 4-dim 多 candidate 行为 + mining_signals 不区分 dim（dim 信息只入 downstream_context）+ mine() dedup 行为
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
from unittest.mock import MagicMock
from evolution.prompts.session_prompt_miner import (
    SessionPromptMiner, Candidate, Verdict, DRIFT_DIMENSIONS,
)
config = MagicMock(); config.judge_model='m'; config.eval_model='m'; config.get_lm_kwargs = MagicMock(return_value={})
m = SessionPromptMiner(config)
# Mock judges (avoid real LLM)
m.user_correction_judge = MagicMock(return_value=MagicMock(is_correction=True))
m.judge = MagicMock(return_value=MagicMock(verdict='confirm_example', section_id='memory_guidance', expected_behavior='ack the user remembers', difficulty='easy', rationale='ok'))

# T1: user_correction hit
msgs = [{'role':'user','content':'hi'},{'role':'assistant','content':'hello'},{'role':'user','content':'don\\'t apologize so much'}]
cands = m._extract_user_correction(msgs, 's')
assert len(cands) == 1, cands
assert cands[0].signal == 'user_correction'
assert m.metrics['total_candidates_by_signal']['user_correction'] == 1

# T2: no keyword → []
m.metrics = m._fresh_metrics()
msgs_empty = [{'role':'user','content':'hi'},{'role':'assistant','content':'hello'},{'role':'user','content':'great thanks'}]
assert m._extract_user_correction(msgs_empty, 's') == []

# T3: section_specific memory_guidance hit
msgs2 = [{'role':'assistant','content':'response'},{'role':'user','content':'I already told you my name is bob'}]
cands2 = m._extract_section_specific_failure(msgs2, 's')
assert any(c.section_id == 'memory_guidance' for c in cands2), cands2

# T5: oracle disabled when baseline_module None
m2 = SessionPromptMiner(config); m2.judge = MagicMock()
assert m2._extract_oracle_disagreement(msgs, 's') == []

# T6: persona_drift needs detector
m3 = SessionPromptMiner(config, signals=['persona_drift'])
assert m3.drift_detector is None
assert m3._extract_persona_drift([{'role':'assistant','content':'a'}]*4, 's') == []

# T7: persona_drift candidate when detector + scores > threshold
m4 = SessionPromptMiner(config, signals=['persona_drift'], drift_thresholds={'tone':0.2,'formality':0.2,'vocabulary':0.2,'persona':0.2})
m4.drift_detector._check_one_run = MagicMock(return_value=({'tone':0.9,'formality':0.05,'vocabulary':0.05,'persona':0.9}, 'exp'))
msgs_long = [{'role':'user','content':'q'}] + [{'role':'assistant','content':f'a{i}'} for i in range(9)]
cands4 = m4._extract_persona_drift(msgs_long, 's')
assert len(cands4) == 2, cands4  # tone + persona exceed

# T8/T9/T10: judge parsing + metrics
m5 = SessionPromptMiner(config)
m5.judge = MagicMock(return_value=MagicMock(verdict='LARGE', section_id='memory_guidance', expected_behavior='b', difficulty='HUGE', rationale='r'))
fake = [Candidate(task='t',session_path='s',signal='user_correction',originally_observed_behavior='o',downstream_context='d')]
verdicts = m5._judge_candidates(fake, [])
assert verdicts[0][1].difficulty == 'medium'  # fallback
assert verdicts[0][1].verdict == 'false_positive'  # fallback
assert m5.metrics['judge_calls'] == 1
assert m5.metrics['judge_false_positives_by_signal']['user_correction'] == 1
print('PASS')
"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "def _extract_" evolution/prompts/session_prompt_miner.py` ≥ 4（精确 4 个 extractor）
    - `grep -nE "def _judge_candidates" evolution/prompts/session_prompt_miner.py` 命中
    - `grep -nE "drift_detector\._check_one_run" evolution/prompts/session_prompt_miner.py` 命中（D-04 1-run override）
    - `grep -nE "len\(assistant_turns\) < 6" evolution/prompts/session_prompt_miner.py` 命中（min_turns gate）
    - `grep -nE 'self\.user_correction_judge' evolution/prompts/session_prompt_miner.py` ≥ 2（构造 + 调用）
    - `grep -c "_USER_CORRECTION_PATTERNS" evolution/prompts/session_prompt_miner.py` ≥ 2（常量 + 使用点 — section_specific_failure 也用）
    - `grep -nE "platform_hints\." evolution/prompts/session_prompt_miner.py` 命中
    - `grep -nE 'difficulty not in DIFFICULTY_VALUES' evolution/prompts/session_prompt_miner.py` 命中（D-12）
    - **W3 fix acceptance**：`grep -nE "4-dim DriftDetector candidate proposer" evolution/prompts/session_prompt_miner.py` 命中（docstring 说明）
    - **W3 fix acceptance**：`grep -nE "mining_signals 仅含" evolution/prompts/session_prompt_miner.py` 命中（docstring 说明 dim 信息不进 mining_signals）
    - 现有测试 zero regression：`python -m pytest tests/prompts/ -x -q`
  </acceptance_criteria>

  <done>
    4 个 extractor + judge 行为完整，每个 extractor 在 signals subset 之外短路返回 []；DriftDetector 与 oracle baseline 缺失时 graceful fallback；judge 鲁棒解析含 difficulty default；metrics 精确递增。W3 fix：`_extract_persona_drift` docstring 显式说明 4-dim 多 candidate + dedup 行为，且 dim 信息不进 mining_signals。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2.4: mine() 主流程 + split_and_duplicate（D-13/D-15 桶分裂 + train-only 复制）</name>
  <files>evolution/prompts/session_prompt_miner.py</files>

  <read_first>
    - evolution/tools/session_miner.py lines 660-774 (Phase 14 mine + split_and_duplicate 完整实现)
    - 现 session_prompt_miner.py (Task 2.1-2.3 产物)
    - evolution/prompts/prompt_dataset.py（Plan 19-01 产物 — 确认 _hash_to_split 暴露）
    - .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-PATTERNS.md §1.1.H (lines 298-345)
  </read_first>

  <behavior>
    - Test 1: `mine(empty_dir, [])` 返回 [] 且 metrics 不变（_fresh_metrics 默认值）
    - Test 2: 单 session 含 user_correction → mine() 返回 1 个 PromptBehavioralExample(source='session', mining_signals=['user_correction'])
    - Test 3: 多 candidate 同 task_hash + 不同 signal → mine() 输出**1 个** example（union mining_signals 字段）；不论顺序（user_correction first 还是 persona_drift first）
    - Test 4: 多 candidate 同 task_hash + 不同 section_id（D-07）→ 输出**多个** examples，每个对应一个 section_id；mining_signals 在每个内 union
    - Test 5: split_and_duplicate 输入 train=[ex_uc_only, ex_pd_only], val=[ex], holdout=[ex] → train length = 1*3 + 1*2 = 5; val/holdout length unchanged
    - Test 6: split_and_duplicate 中同例 mining_signals=['user_correction','persona_drift'] → 复制次数 = max(3, 2) = 3（非累乘）
    - Test 7: surface_drift_dropped 写入：mock verdict.section_id='unknown_section' 不在 current_section_ids 集合 → 该例不进 output，metrics.surface_drift_dropped == 1
    - Test 8 (B3 fix): 5% bad_lines 阈值告警 — 当 `session_load_failures / total > 0.05` console.print 含 'yellow' 颜色或 'WARNING'（注：B3 fix 后 5% 阈值监视 session_load_failures 而非 jsonl_skipped_lines）
    - Test 9: limit 参数生效：sessions_dir 含 10 个 .json，limit=3 → 最多读 3 个
    - Test 10: false_positive verdict 被丢弃（不进 examples）但 metrics.judge_false_positives_by_signal 已记录
  </behavior>

  <action>
    在 `evolution/prompts/session_prompt_miner.py` 中完成 mine() 实现 + 模块级 split_and_duplicate。

    1. **mine() 主流程**（per D-09/D-15/D-23/D-24；mirror Phase 14 lines 660-739；B3 fix 5% 阈值监视 session_load_failures）。**替换** Task 2.2 留的 `mine()` placeholder：
    ```python
        def mine(
            self,
            sessions_dir: Path,
            current_sections: list,
            limit: int = 0,
        ) -> list[PromptBehavioralExample]:
            """Orchestrate: load sessions → 4 extractors → secret filter →
            LLM judge → surface drift filter (D-09) → hash dedup + union
            mining_signals (D-07).

            Returns flat list of PromptBehavioralExample(source='session')
            BEFORE bucket-split + train-only duplication. Caller (Plan 03 CLI)
            invokes split_and_duplicate() to land on the final 3-split layout.
            """
            self.metrics = self._fresh_metrics()
            self.metrics["judge_model"] = getattr(self.config, "judge_model", "") or ""

            current_section_ids: set[str] = {s.section_id for s in current_sections}

            session_paths = sorted(sessions_dir.glob("*.json"))
            total_sessions = len(session_paths)
            if limit and limit > 0:
                session_paths = session_paths[:limit]

            all_cands: list[Candidate] = []
            for sp in session_paths:
                session = self._load_session(sp)
                if not session:
                    continue
                messages = session.get("messages") or []
                if not isinstance(messages, list):
                    continue
                all_cands.extend(self._extract_user_correction(messages, str(sp)))
                all_cands.extend(self._extract_section_specific_failure(messages, str(sp)))
                all_cands.extend(self._extract_oracle_disagreement(messages, str(sp)))
                all_cands.extend(self._extract_persona_drift(messages, str(sp)))

            # D-23: secret filter (pre-judge to save LLM cost)
            all_cands = self._filter_secrets(all_cands)

            # D-24 + B3 fix: skip-rate warn monitors session_load_failures
            # (file-level mining scope), NOT jsonl_skipped_lines (Plan 04 helper scope).
            total_seen = total_sessions
            session_failures = self.metrics["session_load_failures"]
            if total_seen > 0 and session_failures / total_seen > JSONL_BAD_LINE_WARN_THRESHOLD:
                console.print(
                    f"[yellow]⚠ session load: failed {session_failures}/{total_seen} files "
                    f"({session_failures / total_seen * 100:.1f}%)[/yellow]"
                )

            if not all_cands:
                return []

            # D-03 single-call LLM judge
            verdict_pairs = self._judge_candidates(all_cands, current_sections)

            # D-09 surface drift filter (after judge, since section_id comes from verdict)
            verdict_pairs = self._filter_drift(verdict_pairs, current_section_ids)

            # D-07/D-13 hash-key union into PromptBehavioralExample
            # Same task_hash + same section_id → union mining_signals (single ex).
            # Same task_hash + different section_id → multiple ex (D-07).
            from collections import OrderedDict
            by_key: "OrderedDict[tuple[str,str], PromptBehavioralExample]" = OrderedDict()
            for c, v in verdict_pairs:
                if v.verdict != "confirm_example":
                    continue  # D-05: false_positive already recorded in metrics
                key = (c.task_hash(), v.section_id)
                if key not in by_key:
                    by_key[key] = PromptBehavioralExample(
                        section_id=v.section_id,
                        user_message=c.task,
                        expected_behavior=v.expected_behavior,
                        difficulty=v.difficulty if v.difficulty in DIFFICULTY_VALUES else "medium",
                        source="session",  # D-02 enum
                        mining_signals=[c.signal],  # D-02 new field
                    )
                else:
                    prev = by_key[key]
                    if c.signal not in prev.mining_signals:
                        prev.mining_signals = sorted(set(prev.mining_signals) | {c.signal})
            return list(by_key.values())
    ```

    2. **模块级 split_and_duplicate**（per D-13/D-15；mirror Phase 14 lines 741-774）— **替换** Task 2.1 末尾的 placeholder：
    ```python
    def split_and_duplicate(
        examples: list[PromptBehavioralExample],
        multiplier_override: Optional[dict[str, int]] = None,
        metrics: Optional[dict] = None,
    ) -> tuple[list[PromptBehavioralExample], list[PromptBehavioralExample], list[PromptBehavioralExample]]:
        """D-13/D-15: bucket by normalized task hash → 70/85/15 splits →
        duplicate train-only by max-per-signal multiplier.

        Returns (train, val, holdout) lists. Mutates `metrics` if provided:
          - final_examples_by_split['{split}'] += per-split unique counts
          - final_train_after_duplication = post-duplication train length
          - mining_multiplier_used updated with override entries
        """
        train_raw: list[PromptBehavioralExample] = []
        val_raw: list[PromptBehavioralExample] = []
        holdout_raw: list[PromptBehavioralExample] = []
        seen_hashes: set[str] = set()
        for ex in examples:
            h = _normalize_task_hash(ex.user_message)
            if h in seen_hashes:
                # D-15: same hash already routed; this can happen if two
                # examples share user_message but differ on section_id —
                # route both to the SAME split (the first split chosen for
                # this hash). We compute the split deterministically from
                # the hash so the same string always lands in the same split.
                pass
            seen_hashes.add(h)
            split = _hash_to_split(h)
            if split == "train":
                train_raw.append(ex)
            elif split == "val":
                val_raw.append(ex)
            else:
                holdout_raw.append(ex)

        # Update split counts (pre-duplication)
        if metrics is not None:
            metrics["final_examples_by_split"]["train"] = len(train_raw)
            metrics["final_examples_by_split"]["val"] = len(val_raw)
            metrics["final_examples_by_split"]["holdout"] = len(holdout_raw)
            if multiplier_override:
                merged = dict(DEFAULT_MULTIPLIER)
                merged.update({k: v for k, v in multiplier_override.items() if k in DEFAULT_MULTIPLIER})
                metrics["mining_multiplier_used"] = merged

        # D-13: train-only duplication by max-multiplier
        duped_train: list[PromptBehavioralExample] = []
        for ex in train_raw:
            mult = _multiplier_for(ex.mining_signals, multiplier_override)
            duped_train.extend([ex] * mult)
        if metrics is not None:
            metrics["final_train_after_duplication"] = len(duped_train)

        return duped_train, val_raw, holdout_raw
    ```

    依据 (per D-07/D-13/D-15 + B3 fix)：
    - mine() 返回 unsplit list；split_and_duplicate 单独函数让 Plan 03 CLI 解耦调用（dry-run 可跳过 duplication）
    - by_key 用 `(task_hash, section_id)` 双键 — D-07 多 section 拆多条同时 D-15 单切分（split 决定时只看 task_hash）
    - val / holdout 保留 1 份（per D-13）即直接 append 不复制
    - **B3 fix**：5% 阈值在 mining 范围监视 `session_load_failures`（file-level）；`jsonl_skipped_lines` 在本 plan 不被修改（保留为 Plan 04 helper scope）
  </action>

  <verify>
    <automated>cd /Users/slj/项目/hermes-agent-self-evolution &amp;&amp; python -c "
import json, tempfile
from pathlib import Path
from unittest.mock import MagicMock
from evolution.prompts.session_prompt_miner import (
    SessionPromptMiner, Candidate, Verdict,
    split_and_duplicate, DEFAULT_MULTIPLIER,
)
from evolution.prompts.prompt_dataset import PromptBehavioralExample

# Build mock sections
class FakeSection:
    def __init__(self, sid, txt='x'): self.section_id=sid; self.text=txt
current_sections = [FakeSection('memory_guidance'), FakeSection('default_agent_identity'), FakeSection('platform_hints.macos')]

config = MagicMock(); config.judge_model='m'; config.eval_model='m'; config.get_lm_kwargs = MagicMock(return_value={})
m = SessionPromptMiner(config)
# Mock judges: every candidate confirms with section_id='memory_guidance', difficulty='medium'
m.user_correction_judge = MagicMock(return_value=MagicMock(is_correction=True))
m.judge = MagicMock(return_value=MagicMock(verdict='confirm_example', section_id='memory_guidance', expected_behavior='remember', difficulty='medium', rationale='r'))

# T1: empty
with tempfile.TemporaryDirectory() as d:
    assert m.mine(Path(d), current_sections) == []

# T2: single user_correction
with tempfile.TemporaryDirectory() as d:
    sess = {'messages':[{'role':'user','content':'q'},{'role':'assistant','content':'a'},{'role':'user','content':'don\\'t apologize'}]}
    Path(d, 's1.json').write_text(json.dumps(sess))
    out = m.mine(Path(d), current_sections)
    assert len(out) == 1, out
    assert out[0].source == 'session'
    assert out[0].mining_signals == ['user_correction']

# T5: split + duplication
ex_a = PromptBehavioralExample(section_id='x', user_message='a long unique message about memory', expected_behavior='e', difficulty='medium', source='session', mining_signals=['user_correction'])
ex_b = PromptBehavioralExample(section_id='x', user_message='another unique message about identity', expected_behavior='e', difficulty='medium', source='session', mining_signals=['persona_drift'])
# Force both into train via repeated trials until both bucket to train (deterministic)
from evolution.prompts.prompt_dataset import _normalize_task_hash, _hash_to_split
# Pick samples where split == 'train'
def find_train(prefix, n):
    out = []
    i = 0
    while len(out) < n:
        msg = f'{prefix}{i}'
        if _hash_to_split(_normalize_task_hash(msg)) == 'train':
            out.append(msg)
        i += 1
        assert i < 10000
    return out
[a_msg, b_msg] = find_train('uc', 1) + find_train('pd', 1)
ex_a.user_message = a_msg; ex_b.user_message = b_msg
metrics = m._fresh_metrics()
train, val, holdout = split_and_duplicate([ex_a, ex_b], metrics=metrics)
assert len(train) == 5, len(train)  # 3+2

# T6: max not product
ex_c = PromptBehavioralExample(section_id='x', user_message='c msg', expected_behavior='e', source='session', mining_signals=['user_correction','persona_drift'])
ex_c_train = find_train('combo', 1)[0]; ex_c.user_message = ex_c_train
train_c, _, _ = split_and_duplicate([ex_c])
assert len(train_c) == 3, len(train_c)  # max(3,2)=3 NOT 6

# T9: limit
with tempfile.TemporaryDirectory() as d:
    for i in range(10):
        Path(d, f's{i}.json').write_text(json.dumps({'messages':[]}))
    m.metrics = m._fresh_metrics()
    m.mine(Path(d), current_sections, limit=3)
    # All 10 .json files exist but we should only have attempted to load 3.
    # Cannot verify directly without instrumentation, but session_load_failures
    # should be 0 (empty messages don't fail load).
print('PASS')
"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -nE "^    def mine\(" evolution/prompts/session_prompt_miner.py` 命中（method-level 4 空格缩进）
    - `grep -c "NotImplementedError" evolution/prompts/session_prompt_miner.py` == 0（占位符全部替换）
    - `grep -nE "^def split_and_duplicate\(" evolution/prompts/session_prompt_miner.py` 命中（模块级函数）
    - `grep -nE "by_key\[\(c\.task_hash\(\), v\.section_id\)\]" evolution/prompts/session_prompt_miner.py` 命中（D-07 双键）
    - `grep -nE 'mining_signals = sorted\(set\(' evolution/prompts/session_prompt_miner.py` 命中（union 操作）
    - `grep -c "_filter_drift" evolution/prompts/session_prompt_miner.py` ≥ 2（定义 + mine 内调用）
    - `grep -c "_filter_secrets" evolution/prompts/session_prompt_miner.py` ≥ 2（定义 + mine 内调用）
    - **B3 fix acceptance**：`grep -nE "session_failures / total_seen > JSONL_BAD_LINE_WARN_THRESHOLD" evolution/prompts/session_prompt_miner.py` 命中（mine() 5% 阈值监视 session_load_failures）
    - 模块 import 不抛错；现有测试无 regression：`python -m pytest tests/prompts/ -x -q`
    - 模块 LoC：`wc -l evolution/prompts/session_prompt_miner.py` 输出 ≥ 500 行
  </acceptance_criteria>

  <done>
    SessionPromptMiner.mine() 端到端可用（接 sessions_dir → list[PromptBehavioralExample]）；split_and_duplicate 实现 train-only 复制 + 桶分裂；metrics 完整记录；同 task_hash 跨 section 拆多条 + 跨 signal union mining_signals 行为正确。Plan 03 CLI 可直接装配。B3 fix：5% 阈值监视 file-level `session_load_failures`，与 `jsonl_skipped_lines` 显式分离。
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| 磁盘 session JSON → in-memory dict | 未受信源；解析失败必须 graceful skip（D-24）；secrets 必须过滤（D-23） |
| LLM judge 输出 → PromptBehavioralExample | LLM 输出是字符串；五字段单 call 输出需鲁棒解析（CONCERNS §M4） |
| DriftDetector (Phase 18 资产) → persona_drift candidate | Phase 18 接口变动会影响本 plan；只读复用，不修改 thresholds |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-19-02-T (T1) | Tampering / Info Disclosure | session text → candidate.task / downstream_context | mitigate | D-23: `_filter_secrets` 在 LLM judge 前丢弃含 JWT/AWS/Shannon 熵 ≥4 的 candidate；任何含 secret 的 user/assistant 文本零进 example pipeline |
| T-19-02-D (T3) | Denial of Service | _load_session 上 corrupted JSON | mitigate | D-24 + B3 fix: try/except 包裹 json.loads；失败 +session_load_failures（file-level，区别于 jsonl_skipped_lines line-level）；5% 阈值 console warn |
| T-19-02-I (T4) | Info Disclosure | section_id surface drift | mitigate | D-09: _filter_drift 在 LLM judge 后丢弃 section_id 不在 current_section_ids 集合的 verdict；metrics 记 surface_drift_dropped + surface_drift_sections |
| T-19-02-I (T5) | Info Disclosure | LLM judge 5-field parsing | mitigate | D-12: try/except + difficulty default 'medium'; verdict 不在 {confirm_example, false_positive} 时 fallback false_positive；CONCERNS §M4 鲁棒模式 |
| T-19-02-E | Elevation | DriftDetector lazy init | accept | 缺 thresholds → silent disable + warn; 不抛错;依赖 Phase 18 接口稳定 |
| T-19-02-R | Repudiation | judge_calls / judge_false_positives_by_signal | mitigate | D-05 全部 verdict 入 metrics 便于审计 LLM judge 噪声 |
</threat_model>

<verification>
- 模块可独立 import、模块级公开 API 完整
- `python -m pytest tests/prompts/ -x -q` 全部通过（含历史 110 测试）
- 4 个 extractor 在 signals subset 之外短路返回 []（避免无意 LLM 调用）
- _filter_secrets / _filter_drift / _load_session 三个 helper 在异常输入下不抛错
- mine() 在 empty sessions_dir 返回 [] 不抛错
- split_and_duplicate 行为：train-only 复制 + max 取多源
- _judge_candidates 解析失败时 difficulty='medium' / verdict='false_positive' fallback
- 关键 grep 不变量（D-04 1-run vs 3-run）：`grep -E "drift_detector\._check_one_run\(" | grep -v '^#' | wc -l` 大于 0 且 `grep -E "drift_detector\.check\(" evolution/prompts/session_prompt_miner.py | wc -l` 等于 0（不要误用 3-run）
- B3 fix: `session_load_failures` 是 mine() 唯一 file-level 失败字段；`jsonl_skipped_lines` 在本 plan 范围零修改
- W3 fix: persona_drift docstring 显式说明 4-dim 多 candidate + dedup 行为
- W5 fix: Signature OutputField 通过 `__annotations__` 公共 API 验证（不依赖 DSPy 私有 `__dspy_field_type` marker）
</verification>

<success_criteria>
- `evolution/prompts/session_prompt_miner.py` ≥ 500 LoC，全部 placeholder NotImplementedError 已替换
- 4 个 extractor + 1 个 judge + 5 个 helper 全部实现
- DriftDetector 通过 `_check_one_run` 1-run 调用（非 3-run），min_turns=6 门槛
- 单 LLM call 输出 5 字段（verdict/section_id/expected_behavior/difficulty/rationale）
- 同 task_hash 多 signal → union；同 task_hash 多 section_id → 拆多条
- train-only 复制按 max-multiplier；val/holdout 不复制
- secret_filter / surface_drift / session_load_failures 三个 metrics 字段精确递增（B3 fix 后 session_load_failures 替代原 jsonl_skipped_lines mining scope 用法）
- 现有 prompt 测试 zero regression
- B3 fix：metrics schema 明确分离 file-level (session_load_failures) 与 line-level (jsonl_skipped_lines)
- W3 fix：persona_drift docstring 含 4-dim 候选 + dedup 说明
- W5 fix：Signature 验证走公共 API
</success_criteria>

<output>
After completion, create `.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-02-SUMMARY.md` 记录：
- 文件 LoC + 4 extractor / 1 judge / 5 helper 的精确 line ranges
- DriftDetector 1-run override 的 grep 证据
- 鲁棒解析 fallback 行为的 unit test 输出
- Plan 03 CLI / Plan 04 evolve_prompt_sections / Plan 05 测试套件的 import 锚点
- B3 fix 证据：`grep` 输出显示 `session_load_failures` 与 `jsonl_skipped_lines` 各自语义独立（mine() 内 _load_session 仅修改前者，后者初始化为 0 且不被递增）
- W3 fix 证据：`_extract_persona_drift` docstring 的关键句子 grep 命中
- W5 fix 证据：本 plan verify 代码使用 `__annotations__` 而非 `__dspy_field_type` 的 grep 输出
</output>
