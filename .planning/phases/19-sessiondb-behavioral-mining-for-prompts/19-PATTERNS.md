# Phase 19: SessionDB Behavioral Mining for Prompts — Pattern Map

**Mapped:** 2026-05-18
**Phase:** 19 — SessionDB Behavioral Mining for Prompts (PMPT-V2-04)
**Files analyzed:** 6 (2 new + 2 modified + 2+ read-only)
**Analogs found:** 6 / 6  (full coverage — all files have direct Phase 14 / Phase 18 templates)

> Phase 19 是 Phase 14 (SessionDB Mining for Tools) 的 prompt 镜像。CONTEXT.md 已显式锚定每个 new file → Phase 14 模板的对应关系；本文件为每个文件提取**具体代码片段**与**插入/替换锚点**，让 planner 在 PLAN.md 中直接引用。

---

## File Classification

| File | Status | Role | Data Flow | Closest Analog | Match Quality |
|------|--------|------|-----------|----------------|---------------|
| `evolution/prompts/session_prompt_miner.py` | **NEW** | service (mining + LLM judge) | batch + transform | `evolution/tools/session_miner.py` | exact (mirror template) |
| `evolution/prompts/mine_prompt_sessions.py` | **NEW** | CLI entry point | request-response | `evolution/tools/mine_tool_sessions.py` | exact (mirror template) |
| `evolution/prompts/prompt_dataset.py` (L33-66 + L85-122) | **MODIFY** | model + persistence | batch + serialization | self (existing class) | in-place extension |
| `evolution/prompts/evolve_prompt_sections.py` (CLI + step 8) | **MODIFY** | orchestration | request-response | self (existing pipeline) | in-place extension |
| `evolution/core/external_importers.py` L47-121 | **READ-ONLY** | utility | filter | already in production | direct reuse |
| `evolution/prompts/drift_detector.py` | **READ-ONLY** | service (LLM judge) | request-response | already in production | direct reuse |
| `evolution/prompts/prompt_loader.py` | **READ-ONLY** | model + AST extraction | request-response | already in production | direct reuse |
| `evolution/prompts/prompt_constraints.py` | **READ-ONLY** | LLM-as-judge style ref | request-response | analog reference | style template |

---

## 1. NEW FILES

### 1.1 `evolution/prompts/session_prompt_miner.py`

**Analog:** `evolution/tools/session_miner.py` (814 lines — direct template per D-18)
**Aux analogs:**
- `evolution/prompts/drift_detector.py` (persona_drift extractor calls DriftDetector)
- `evolution/prompts/prompt_constraints.py` (PromptRoleChecker — Signature style template for ConfirmBehavioralExample)

**Key methods/patterns the planner MUST call out in PLAN.md:**

1. `class SessionPromptMiner` — direct mirror of `SessionToolMiner`
2. `mine(sessions_dir, current_sections, limit=0) -> list[PromptBehavioralExample]` — top-level orchestration
3. Four `_extract_*` private methods (one per signal: user_correction, section_specific_failure, oracle_disagreement, persona_drift)
4. Inner `ConfirmBehavioralExample(dspy.Signature)` — 5 OutputFields in a single LLM call
5. `_judge_candidate()` + `_load_session()` + `split_and_duplicate()` (D-13 train-only duplication)
6. **NEW vs Phase 14:** `_extract_persona_drift` wraps Phase 18 `DriftDetector` as a candidate extractor (NOT as a constraint gate)

#### 1.1.A Imports + module constants pattern

**Copy from** `evolution/tools/session_miner.py` lines 22-46:

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
from evolution.prompts.prompt_constraints import _parse_bool  # D-04 user_correction LLM 二判
from evolution.prompts.prompt_dataset import PromptBehavioralExample
from evolution.prompts.drift_detector import DriftDetector, DRIFT_DIMENSIONS  # D-04 persona_drift

console = Console()

# ── Constants (D-13) ────────────────────────────────────────────────────
DEFAULT_MULTIPLIER: dict[str, int] = {
    "user_correction": 3,
    "section_specific_failure": 3,
    "oracle_disagreement": 2,
    "persona_drift": 2,
}
VALID_SIGNALS: frozenset[str] = frozenset(DEFAULT_MULTIPLIER.keys())
JSONL_BAD_LINE_WARN_THRESHOLD: float = 0.05  # D-24
```

**Key delta:** import `PromptBehavioralExample` (not `ToolSelectionExample`); import `DriftDetector` for persona_drift; `_parse_bool` lives in `prompt_constraints.py` (line 15).

#### 1.1.B Hash + bucket helpers (verbatim copy)

**Copy from** `evolution/tools/session_miner.py` lines 50-74:

```python
def _normalize_task_hash(task: str) -> str:
    """Return sha256(strip + lower + collapse_whitespace(task))[:16]."""
    norm = re.sub(r"\s+", " ", (task or "").lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _hash_to_split(h: str) -> str:
    """Bucket per D-15: <70 train / <85 val / else holdout."""
    bucket = int(h[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "val"
    return "holdout"


def _multiplier_for(signals: list[str], override: Optional[dict[str, int]] = None) -> int:
    """Return max multiplier across hit signals; default 1 if no signals match."""
    merged = dict(DEFAULT_MULTIPLIER)
    if override:
        merged.update({k: v for k, v in override.items() if k in DEFAULT_MULTIPLIER})
    hits = [merged[s] for s in signals if s in merged]
    return max(hits) if hits else 1
```

**No change needed** — verbatim copy works for prompt domain because both use `task_hash` as dedup key.

#### 1.1.C Inner DSPy Signature — ConfirmBehavioralExample (NEW shape, 5 OutputFields)

**Style template:** `evolution/tools/session_miner.py` lines 130-162 (`ConfirmMisselection`) + `evolution/prompts/drift_detector.py` lines 32-74 (`DriftScoreSignature` — typed OutputField pattern).

```python
class ConfirmBehavioralExample(dspy.Signature):
    """Decide whether the user-flagged turn is a genuine behavioral failure
    of one of the 5 prompt sections, and if so, emit a rubric-form
    expected_behavior + difficulty in a single LLM call (D-03/D-11/D-12).

    Default to 'false_positive' when uncertain. section_id MUST be one of
    {default_agent_identity, memory_guidance, session_search_guidance,
    skills_guidance, platform_hints.<key>}.
    """

    task_description: str = dspy.InputField(
        desc="User message that surfaced the misbehavior",
    )
    available_sections_summary: str = dspy.InputField(
        desc="Newline-separated '- <section_id>: <≤200-char excerpt>' for all current sections + platform_hints.<key> list",
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

**Risk anchor (CONCERNS §M4):** Phase 14 used `str` OutputField + `.strip().lower()` post-validation. For Phase 19, planner SHOULD add post-validation that `section_id` is in current `extract_prompt_sections()` set (D-09 surface drift drop) and `difficulty in {"easy","medium","hard"}` (default "medium" on parse failure).

#### 1.1.D Constructor pattern (mirror of `SessionToolMiner.__init__`)

**Copy from** `evolution/tools/session_miner.py` lines 197-228 (adapted):

```python
def __init__(
    self,
    config: EvolutionConfig,
    signals: Optional[list[str]] = None,
    multiplier_override: Optional[dict[str, int]] = None,
    baseline_module=None,  # PromptModule | None — for oracle_disagreement
    drift_thresholds: Optional[dict] = None,  # D-04 persona_drift; from drift_thresholds.json
):
    self.config = config
    self.signals = signals or list(VALID_SIGNALS)
    self.multiplier_override = multiplier_override or {}
    self.baseline_module = baseline_module
    self.judge = dspy.ChainOfThought(self.ConfirmBehavioralExample)
    self.user_correction_judge = dspy.ChainOfThought(self.DetectUserCorrection)
    # D-04: DriftDetector reuse — lazy-init only when persona_drift active.
    self.drift_detector: Optional[DriftDetector] = (
        DriftDetector(config, drift_thresholds)
        if "persona_drift" in self.signals and drift_thresholds is not None
        else None
    )
    self.metrics: dict = self._fresh_metrics()
```

**Key delta vs Phase 14:** add `drift_thresholds` parameter (loaded from `--drift-thresholds-path`) + lazy `DriftDetector` instantiation. `PromptModule` is optional baseline for oracle (D-04).

#### 1.1.E `_fresh_metrics` schema (metrics.json contract per specifics)

**Copy from** `evolution/tools/session_miner.py` lines 212-228 + extend per CONTEXT specifics:

```python
def _fresh_metrics(self) -> dict:
    """Initialize metrics contract. Extends Phase 14 13-key schema with
    persona_drift + oracle_baseline_path + drift_thresholds_used."""
    return {
        "total_candidates_by_signal": {s: 0 for s in VALID_SIGNALS},
        "judge_confirmed_by_signal": {s: 0 for s in VALID_SIGNALS},
        "judge_false_positives_by_signal": {s: 0 for s in VALID_SIGNALS},  # D-05
        "surface_drift_dropped": 0,  # D-09
        "surface_drift_sections": {},  # name -> count
        "secret_filter_skipped": 0,  # D-23
        "jsonl_skipped_lines": 0,  # D-24
        "judge_calls": 0,
        "judge_calls_by_signal": {s: 0 for s in VALID_SIGNALS},
        "final_examples_by_split": {"train": 0, "val": 0, "holdout": 0},
        "final_train_after_duplication": 0,
        "mining_multiplier_used": dict(DEFAULT_MULTIPLIER),
        # NEW Phase 19 fields per specifics block
        "persona_drift_thresholds_used": {},  # copy of thresholds.json
        "oracle_baseline_path": None,  # str or None when disabled
        "judge_model": "",
    }
```

#### 1.1.F `_extract_user_correction` pattern + LLM 二判

**Copy from** `evolution/tools/session_miner.py` lines 416-497 — same structure, replace keyword seeds with prompt-specific list per CONTEXT specifics (line 215):

```python
_USER_CORRECTION_PATTERNS: list[str] = [
    r"不对", r"错了", r"不应该", r"应该用", r"应该是", r"换一个", r"不是要",
    r"\bwrong\b", r"\bdon't\b", r"\bstop\b",
    r"too verbose", r"太长了", r"be more concise",
    r"don't apologize", r"不要道歉", r"stop saying",
    r"use simpler language", r"in Chinese", r"in English",
]

class DetectUserCorrection(dspy.Signature):
    """LLM 二判 — verify whether a user message is genuinely correcting
    agent behavior (vs accidentally containing a keyword).
    """
    user_message: str = dspy.InputField(desc="The user message")
    preceding_assistant_summary: str = dspy.InputField(
        desc="Summary of the assistant turn being potentially corrected"
    )
    is_correction: bool = dspy.OutputField(desc="True if user is correcting agent")
```

**Mining flow** (mirror of Phase 14 lines 444-497) — replace `_last_assistant_tool_call` lookup with `_last_assistant_content` (prompt domain has no tool_call structure).

#### 1.1.G `_extract_persona_drift` — NEW pattern unique to Phase 19

**Source primitives:**
- `evolution/prompts/drift_detector.py` lines 158-235 — `DriftDetector.check()` returns dict with `per_dim[dim]["mean"]` + `exceeded`
- CONTEXT specifics line 242: 取前 1/3 vs 后 1/3 assistant turns; 1-run (NOT 3-run, to control candidate count); min_turns=6

**Planner MUST implement** something like:

```python
def _extract_persona_drift(
    self,
    messages: list[dict],
    session_path: str,
    current_section_ids: set[str],
) -> list[Candidate]:
    """D-04 persona_drift extractor. Reuses Phase 18 DriftDetector as a
    candidate proposer (NOT as a constraint gate). 1-run averaging at
    this stage (3-run kept for Phase 18 final gate) to keep candidate
    count manageable."""
    if self.drift_detector is None:
        return []
    assistant_turns = [
        m.get("content", "") for m in messages
        if isinstance(m, dict) and m.get("role") == "assistant"
           and isinstance(m.get("content"), str)
    ]
    if len(assistant_turns) < 6:  # min_turns gate per specifics
        return []
    third = len(assistant_turns) // 3
    original_text = "\n".join(assistant_turns[:third])
    evolved_text = "\n".join(assistant_turns[-third:])
    # 1-run (override the 3-run loop in DriftDetector.check)
    scores, _ = self.drift_detector._check_one_run(
        section_id="persona_drift_window",
        original_text=original_text,
        evolved_text=evolved_text,
    )
    cands: list[Candidate] = []
    for dim, score in scores.items():
        if score > self.drift_detector.thresholds[dim]:
            cands.append(Candidate(
                task=self._first_user_task(messages) or "",
                session_path=session_path,
                signal="persona_drift",
                downstream_context=f"drift_dim={dim} score={score:.3f}",
                ...  # section_id resolved by LLM judge
            ))
    return cands
```

**Critical:** call `drift_detector._check_one_run()` directly (1-run) instead of `.check()` (3-run). Planner should document this as a deliberate departure per CONTEXT specifics line 242.

#### 1.1.H `_load_session` + `mine()` orchestration (verbatim shape from Phase 14)

**Copy from** `evolution/tools/session_miner.py` lines 606-739:

```python
def _load_session(self, sp: Path) -> Optional[dict]:
    try:
        return json.loads(sp.read_text())
    except Exception:
        self.metrics["jsonl_skipped_lines"] += 1
        return None

def mine(
    self,
    sessions_dir: Path,
    current_sections: list,  # list[PromptSection]
    limit: int = 0,
) -> list[PromptBehavioralExample]:
    """Orchestrate: load → 4 extractors → drift filter → secret filter
    → LLM judge → hash-dedup union signals."""
    self.metrics = self._fresh_metrics()
    current_section_ids: set[str] = {s.section_id for s in current_sections}
    session_paths = sorted(sessions_dir.glob("*.json"))
    if limit > 0:
        session_paths = session_paths[:limit]
    # ... (rest mirrors Phase 14 lines 680-739)
    # Build PromptBehavioralExample(s) from verdict tuples; union mining_signals on dup hash.
```

**Critical delta on dedup loop (mirror lines 716-738):**
```python
by_hash: dict[str, PromptBehavioralExample] = {}
for c, v in verdicts:
    h = c.task_hash()
    if h not in by_hash:
        by_hash[h] = PromptBehavioralExample(
            section_id=v.section_id,
            user_message=c.task,
            expected_behavior=v.expected_behavior,
            difficulty=v.difficulty,
            source="session",  # D-02 枚举扩展
            mining_signals=[c.signal],  # D-02 新字段
        )
    else:
        prev = by_hash[h]
        prev.mining_signals = sorted(set(prev.mining_signals) | {c.signal})
```

---

### 1.2 `evolution/prompts/mine_prompt_sessions.py`

**Analog:** `evolution/tools/mine_tool_sessions.py` (414 lines — direct template per D-17)

**Key methods/patterns the planner MUST call out in PLAN.md:**

1. 13 `@click.option` flags (12 from Phase 14 + 1 new `--drift-thresholds-path`)
2. `_parse_signals` + `_parse_multiplier_override` helpers (rename `misselection` → `behavioral`)
3. `mine()` orchestrator function (NOT a Click command — wraps `main`)
4. `--i-have-consent` hard gate (D-25)
5. Rich Table summary + `metrics.json` write
6. `FAILED_<ts>/` directory pattern for failure paths

#### 1.2.A Click flags — copy exactly 12 from Phase 14, add 1 NEW

**Copy from** `evolution/tools/mine_tool_sessions.py` lines 327-378. The exact 12 Phase 14 flags are listed in CONTEXT D-17; the new Phase 19 flag is `--drift-thresholds-path`.

```python
@click.command()
@click.option(
    "--sessions-dir", default=None, type=click.Path(),
    help="Directory containing session_*.json (default ~/.hermes/sessions)",
)
@click.option(
    "--output", default=None, type=click.Path(),
    help="Output directory (default datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/)",
)
@click.option("--limit", default=0, type=int, help="0 = scan all sessions")
@click.option(
    "--i-have-consent", is_flag=True,
    help="REQUIRED — explicit consent to read session data (Layer 3 privacy gate)",
)
@click.option(
    "--signals",
    default="user_correction,section_specific_failure,oracle_disagreement,persona_drift",
    help="Comma-separated subset of {user_correction, section_specific_failure, oracle_disagreement, persona_drift}",
)
@click.option(
    "--baseline-module", default=None, type=click.Path(),
    help="Path to a Phase 10/17/18 evolve_prompt_sections output dir for oracle (omit → skip oracle_disagreement)",
)
@click.option(
    "--judge-model", default=None,
    help="Override config.judge_model for ConfirmBehavioralExample LLM judge",
)
@click.option(
    "--behavioral-multiplier", default=None,
    help='Override D-13 defaults, e.g. "user_correction=3,section_specific_failure=3,oracle_disagreement=2,persona_drift=2"',
)
@click.option(
    "--hermes-repo", default=None,
    help="Path to hermes-agent repo (overrides HERMES_AGENT_REPO env)",
)
@click.option("--model", default=None, help="Override LLM model for non-judge calls")
@click.option("--api-base", default=None, help="Override API base URL")
@click.option(
    "--dry-run", is_flag=True,
    help="Skip LLM judge; enumerate candidates and exit",
)
# ── NEW Phase 19 flag (D-17) ───────────────────────────────────────────────
@click.option(
    "--drift-thresholds-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("datasets/prompts/drift_thresholds.json"),
    help="Path to drift_thresholds.json (Phase 18 D-BYPASS-02 mirror) for persona_drift signal.",
)
```

**Renames vs Phase 14:**
- `--misselection-multiplier` → `--behavioral-multiplier` (per D-14, prompt-domain naming)
- `--signals` default expands from 3 to 4 (adds `persona_drift`)
- Output default path: `datasets/tools/sessions/` → `datasets/prompts/sessions/`

#### 1.2.B `_parse_signals` + `_parse_multiplier_override`

**Copy from** `evolution/tools/mine_tool_sessions.py` lines 52-95 — only rename CLI option string in error messages:

```python
def _parse_signals(value: str) -> list[str]:
    """Parse '--signals' CSV into a deduped list. Unknown signals → UsageError."""
    items = [s.strip() for s in (value or "").split(",") if s.strip()]
    bad = [s for s in items if s not in VALID_SIGNALS]
    if bad:
        raise click.UsageError(
            f"--signals contains unknown signal(s): {bad}. Valid: {sorted(VALID_SIGNALS)}"
        )
    if not items:
        raise click.UsageError("--signals is empty after parsing")
    return list(dict.fromkeys(items))


def _parse_multiplier_override(value: Optional[str]) -> dict[str, int]:
    """Parse '--behavioral-multiplier' kv string into dict[str, int]."""
    if not value:
        return {}
    out: dict[str, int] = {}
    for part in value.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise click.UsageError(f"--behavioral-multiplier item {part!r} missing '='")
        k, v = part.split("=", 1)
        k = k.strip()
        if k not in VALID_SIGNALS:
            raise click.UsageError(
                f"--behavioral-multiplier unknown signal {k!r}; valid: {sorted(VALID_SIGNALS)}"
            )
        try:
            out[k] = int(v.strip())
        except ValueError:
            raise click.UsageError(
                f"--behavioral-multiplier value for {k!r} must be int, got {v!r}"
            )
    return out
```

#### 1.2.C Consent gate + main `mine()` body

**Copy from** `evolution/tools/mine_tool_sessions.py` lines 179-323. Key adapt points:

```python
def mine(
    sessions_dir, output, limit, i_have_consent, signals, baseline_module,
    judge_model, behavioral_multiplier, hermes_repo, model, api_base,
    dry_run, drift_thresholds_path,  # ← new arg
) -> int:
    # D-25 consent gate (line 194-201 in Phase 14)
    if not i_have_consent:
        click.echo(
            "--i-have-consent is REQUIRED — refusing to read session data "
            "from ~/.hermes/sessions/ without explicit consent.\n"
            "Pass --i-have-consent to proceed.",
            err=True,
        )
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config = EvolutionConfig.load(api_base=api_base, model=model, hermes_repo=hermes_repo)
    if judge_model:
        config.judge_model = judge_model

    sessions_path = (
        Path(sessions_dir).expanduser() if sessions_dir
        else (Path.home() / ".hermes" / "sessions")
    )
    out_dir = (
        Path(output) if output
        else Path("datasets") / "prompts" / "sessions" / timestamp  # ← prompts/ not tools/
    )

    # ── Load current prompt sections (replaces discover_tool_files) ──────
    from evolution.prompts.prompt_loader import extract_prompt_sections
    prompt_builder_path = config.hermes_agent_path / "src" / "hermes_agent" / "prompt_builder.py"
    current_sections = extract_prompt_sections(prompt_builder_path)
    if not current_sections:
        # FAILED_<ts>/ path (mirror lines 257-266)
        ...

    # ── Load drift thresholds for persona_drift (NEW) ────────────────────
    drift_thresholds = None
    if "persona_drift" in _parse_signals(signals):
        drift_thresholds = json.loads(Path(drift_thresholds_path).read_text())
        # Strip _meta key per evolve_prompt_sections.py line 510-514
        drift_thresholds = {d: drift_thresholds[d] for d in DRIFT_DIMENSIONS}

    miner = SessionPromptMiner(
        config=config, signals=signals_list,
        multiplier_override=multiplier_override,
        baseline_module=baseline_mod,
        drift_thresholds=drift_thresholds,  # ← new
    )
    # ... (rest mirrors lines 286-323)
```

**Key delta vs Phase 14:**
- Replace `discover_tool_files` + `extract_tool_descriptions` calls with single `extract_prompt_sections(prompt_builder_path)` from `evolution/prompts/prompt_loader.py` (see §3.3)
- Add drift_thresholds load (only when persona_drift signal active)
- `_load_baseline_module` reads `evolved_sections.json` (Phase 10/17/18 output schema) instead of `evolved_descriptions.json`

#### 1.2.D Rich Table summary

**Copy from** `evolution/tools/mine_tool_sessions.py` lines 143-175. Iterate 4 signals (add `persona_drift` row):

```python
def _print_summary_table(metrics: dict, total_examples: int) -> None:
    t = Table(title="SessionDB Behavioral Mining Summary", show_header=True, header_style="bold cyan")
    t.add_column("Signal", style="bold")
    t.add_column("Candidates", justify="right")
    t.add_column("Confirmed", justify="right")
    t.add_column("False Positives", justify="right")
    for s in ("user_correction", "section_specific_failure", "oracle_disagreement", "persona_drift"):
        t.add_row(s,
            str(metrics["total_candidates_by_signal"].get(s, 0)),
            str(metrics["judge_confirmed_by_signal"].get(s, 0)),
            str(metrics["judge_false_positives_by_signal"].get(s, 0)),
        )
    # ... TOTAL row + surface_drift + secret_filter + judge_calls (same as Phase 14)
```

---

## 2. MODIFIED FILES

### 2.1 `evolution/prompts/prompt_dataset.py`

**Existing file size:** 330 lines
**Modifications:** D-02 (add `mining_signals` field + extend `source` enum to allow `"session"`) — affects lines 33-66 ONLY. D-15/D-16 hash-based dedup is handled in `evolve_prompt_sections.py` (§2.2), NOT here.

#### 2.1.A Exact insertion point — `PromptBehavioralExample` dataclass (lines 33-66)

**Before** (lines 33-66 current code):
```python
@dataclass
class PromptBehavioralExample:
    """..."""
    section_id: str
    user_message: str
    expected_behavior: str
    difficulty: str = "medium"
    source: str = "synthetic"

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "user_message": self.user_message,
            "expected_behavior": self.expected_behavior,
            "difficulty": self.difficulty,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PromptBehavioralExample":
        """Deserialize from dict, ignoring unknown keys."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
```

**After D-02 changes:**
```python
@dataclass
class PromptBehavioralExample:
    """A single prompt behavioral evaluation example.

    Args:
        section_id: Which section this scenario tests.
        user_message: Simulated user input.
        expected_behavior: Rubric describing correct agent behavior.
        difficulty: One of 'easy', 'medium', 'hard'.
        source: Provenance: 'synthetic', 'golden', 'session' (Phase 19 extends).
        mining_signals: Which session-mining signal(s) produced this example;
            empty for synthetic/golden. Phase 19 D-02.
    """
    section_id: str
    user_message: str
    expected_behavior: str
    difficulty: str = "medium"
    source: str = "synthetic"
    mining_signals: list[str] = field(default_factory=list)  # ← NEW (D-02)

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "user_message": self.user_message,
            "expected_behavior": self.expected_behavior,
            "difficulty": self.difficulty,
            "source": self.source,
            "mining_signals": self.mining_signals,  # ← NEW
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PromptBehavioralExample":
        """Deserialize from dict, ignoring unknown keys.

        Backward compatible: pre-Phase-19 JSONL has no `mining_signals` key →
        defaults to []. The existing `cls.__dataclass_fields__` filter
        handles unknown keys, so historical Phase 9 datasets load unchanged.
        """
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
```

**Backward compat verified by:** existing `from_dict` filter at line 66 already drops unknown keys (CONTEXT line 173 confirms). Adding a new field with `field(default_factory=list)` makes historical JSONL load with `mining_signals=[]`.

#### 2.1.B `PromptBehavioralDataset.save/load` (lines 85-122) — NO CHANGES NEEDED

Existing save (lines 85-101) writes `ex.to_dict()` line-by-line → automatically picks up the new `mining_signals` key.
Existing load (lines 103-122) calls `PromptBehavioralExample.from_dict(json.loads(line))` → backward-compat path.

**Planner note:** Per D-24, the JSONL try/except-per-line resilience for `--session-source` load path lives in `evolve_prompt_sections.py` (§2.2), NOT here. CONTEXT explicitly says: "**不**重写 `PromptBehavioralDataset.load` (v2-STAB-01 独立清理范围)".

---

### 2.2 `evolution/prompts/evolve_prompt_sections.py`

**Existing file size:** 1071 lines
**Modifications:** Add `--session-source <path>` flag (D-21) + union session/synthetic datasets with hash dedup (D-16). DriftDetector wiring at step 8c is **already in place** (lines 508-617) — no changes to that block.

#### 2.2.A New Click option (insert near lines 1043-1053, after `--drift-thresholds-path`)

**Style template:** existing `--drift-thresholds-path` option block (lines 1043-1053):

```python
@click.option(
    "--session-source",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help=(
        "Phase 19 D-21. Path to a directory produced by "
        "`python -m evolution.prompts.mine_prompt_sessions` containing "
        "train.jsonl / val.jsonl / holdout.jsonl. When provided, the "
        "session-mined dataset is UNION-merged (hash dedup, session "
        "wins on collision) with the synthetic PromptDatasetBuilder "
        "output. Works in both --mode joint and --mode round-robin. "
        "Omitting this flag preserves pre-Phase-19 behavior."
    ),
)
```

#### 2.2.B `main()` and `evolve()` signature thread

**Existing `main` signature** (lines 1054-1055):
```python
def main(section, iterations, eval_source, hermes_repo, dry_run, model,
         api_base, mode, drift_thresholds_path):
```

**Modified:**
```python
def main(section, iterations, eval_source, hermes_repo, dry_run, model,
         api_base, mode, drift_thresholds_path, session_source):
    evolve(
        section=section, iterations=iterations, eval_source=eval_source,
        hermes_repo=hermes_repo, dry_run=dry_run, model=model, api_base=api_base,
        mode=mode, drift_thresholds_path=drift_thresholds_path,
        session_source=session_source,  # ← new
    )
```

**`evolve()` signature** (line 116): add `session_source: Optional[Path] = None` param.

#### 2.2.C Insertion point — Dataset union after PromptDatasetBuilder (around line 253)

**Existing block** (lines 251-271):
```python
if eval_source == "synthetic":
    builder = PromptDatasetBuilder(config)
    dataset = builder.generate(original_sections)
    save_path = Path("datasets") / "prompts"
    dataset.save(save_path)
    ...
elif eval_source == "load":
    dataset = PromptBehavioralDataset.load(dataset_path)
```

**Insert AFTER this block** (per D-16/D-21 union logic):

```python
# ── 5b. Phase 19 D-21: Union session-mined examples ────────────────────
if session_source:
    console.print(f"\n[bold]Loading session-mined dataset[/bold] from {session_source}")
    session_dataset = PromptBehavioralDataset.load(session_source)
    console.print(f"  Session split: {len(session_dataset.train)} train / "
                  f"{len(session_dataset.val)} val / {len(session_dataset.holdout)} holdout")
    # D-16 union: hash-dedup per split, session wins on collision
    from evolution.prompts.session_prompt_miner import _normalize_task_hash
    for split_name in ("train", "val", "holdout"):
        synth_split = getattr(dataset, split_name)
        sess_split = getattr(session_dataset, split_name)
        synth_by_hash = {_normalize_task_hash(ex.user_message): ex for ex in synth_split}
        sess_by_hash = {_normalize_task_hash(ex.user_message): ex for ex in sess_split}
        # Session wins (D-16): start with synth, overwrite with session
        merged = {**synth_by_hash, **sess_by_hash}
        setattr(dataset, split_name, list(merged.values()))
    console.print(f"  After union: {len(dataset.train)} train / "
                  f"{len(dataset.val)} val / {len(dataset.holdout)} holdout")
```

**Critical:** D-16 says "session 优先 (mining_signals 字段保留)" → use dict-update order where session overwrites synthetic. This block is **mode-agnostic** (D-21: works in both joint + round-robin) because it runs **before** mode forks at line 278.

#### 2.2.D Step 8c — NO CHANGES (DriftDetector wiring already exists)

Lines 508-617 are already implementing Phase 18 drift detection. Phase 19 makes **zero changes** to this block. (See §3.2 for read-only reference of the existing pattern.)

---

## 3. READ-ONLY ASSETS (for planner reference)

### 3.1 `evolution/core/external_importers.py` lines 47-121 — Secret filter

**Status:** Direct reuse per D-23. **No edits.**

**Imports for session_prompt_miner.py:**
```python
from evolution.core.external_importers import _contains_secret
```

**Behavior contract** (line 108-121):
- Layer 1: regex `SECRET_PATTERNS` covers `sk-ant-api`, `sk-or-v1-`, `ghp_`, JWT, AWS access keys, AWS-secret proximity, PEM, env-var names, `password=/secret=/token=` assignments
- Layer 2: Shannon entropy ≥ 4.0 on any 24+ char base64-ish substring → True
- Returns `bool` — callers do `if _contains_secret(text): skip_and_increment_metric`

**Callsite pattern** (mirror Phase 14 lines 658-665):
```python
def _filter_secrets(self, cands: list[Candidate]) -> list[Candidate]:
    kept: list[Candidate] = []
    for c in cands:
        if _contains_secret(c.task) or _contains_secret(c.downstream_context):
            self.metrics["secret_filter_skipped"] += 1
            continue
        kept.append(c)
    return kept
```

---

### 3.2 `evolution/prompts/drift_detector.py` — DriftDetector reuse

**Status:** Direct reuse per D-04 + D-22. **No edits.**

**Class constructor signature** (lines 98-124):
```python
def __init__(self, config: EvolutionConfig, thresholds: dict):
    # thresholds MUST contain keys matching DRIFT_DIMENSIONS = ("tone", "formality", "vocabulary", "persona")
    # raises ValueError if any dim missing
```

**Methods session_prompt_miner.py will call:**

| Method | Signature | Use case in Phase 19 |
|--------|-----------|----------------------|
| `_check_one_run(section_id, original, evolved) -> tuple[dict, str]` | Single LLM call, returns `(per_dim_scores, explanation)` | **`_extract_persona_drift` uses this (1-run mode per CONTEXT specifics line 242)** |
| `.thresholds` (attribute) | `dict[str, float]` | Compare 1-run score directly against per-dim threshold |
| `DRIFT_DIMENSIONS` (module const) | `("tone", "formality", "vocabulary", "persona")` | Iterate 4 dims |

**Thresholds loading pattern** (copy from evolve_prompt_sections.py lines 510-515):
```python
drift_thresholds_raw = json.loads(drift_thresholds_path.read_text())
drift_thresholds = {d: drift_thresholds_raw[d] for d in DRIFT_DIMENSIONS}  # strip _meta
drift_detector = DriftDetector(config, drift_thresholds)
```

**Critical:** `DriftDetector.check()` is 3-run averaged — Phase 19 candidate extraction needs **`_check_one_run()`** directly to avoid 1.5× × 3 = 4.5× LLM cost blowup. This is a deliberate Phase 19 decision (CONTEXT specifics line 242).

---

### 3.3 `evolution/prompts/prompt_loader.py` — Section extraction & surface drift truth source

**Status:** Direct reuse per D-08, D-09. **No edits.**

**Returns** `list[PromptSection]` where each `PromptSection` has:
```python
section_id: str          # "default_agent_identity" | "memory_guidance" | ... | "platform_hints.<key>"
text: str
char_count: int
line_range: tuple[int, int]
source_path: Path
```

**Section id taxonomy** (lines 27-32 + line 128):
- `default_agent_identity`
- `memory_guidance`
- `session_search_guidance`
- `skills_guidance`
- `platform_hints.<key>` — one per dict key (PLATFORM_HINTS expanded; 9 keys in current hermes-agent)

**D-08 LLM prompt guidance:** `ConfirmBehavioralExample.section_id` OutputField MUST output `platform_hints.<platform_token>` when misbehavior is platform-specific. `<platform_token>` extracted from candidate context (e.g., "on macOS / Linux 下 / Windows 则").

**D-09 surface drift filter** (mirror Phase 14 lines 641-656 — adapt names):
```python
def _filter_drift(self, cands: list[Candidate], current_section_ids: set[str]) -> list[Candidate]:
    kept: list[Candidate] = []
    for c in cands:
        # session-derived section_id (from LLM judge verdict) not in current surface → drop
        if c.section_id not in current_section_ids:
            self.metrics["surface_drift_dropped"] += 1
            self.metrics["surface_drift_sections"][c.section_id] = (
                self.metrics["surface_drift_sections"].get(c.section_id, 0) + 1
            )
            continue
        kept.append(c)
    return kept
```

**Note:** D-09 surface drift filter runs **after** LLM judge (since section_id comes from verdict, not heuristic). Place between judge confirm loop and dedup loop in `mine()`.

**Caller pattern for current_sections:**
```python
prompt_builder_path = config.hermes_agent_path / "src" / "hermes_agent" / "prompt_builder.py"
current_sections = extract_prompt_sections(prompt_builder_path)
current_section_ids = {s.section_id for s in current_sections}
```

---

### 3.4 `evolution/prompts/prompt_constraints.py` — LLM-as-judge Signature style template

**Status:** Style reference only. **No edits.**

**Pattern to mirror in `ConfirmBehavioralExample` Signature** (lines 44-66):
```python
class RoleCheckSignature(dspy.Signature):
    """<docstring describing the judgement task>"""
    section_id: str = dspy.InputField(desc="<purpose>")
    original_text: str = dspy.InputField(desc="<purpose>")
    evolved_text: str = dspy.InputField(desc="<purpose>")
    role_preserved: bool = dspy.OutputField(desc="<True/False rule>")
    explanation: str = dspy.OutputField(desc="<format expectation>")
```

**Also reuses:** `_parse_bool` helper (lines 15-29):
```python
def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "1")
```

Phase 19 imports this for `DetectUserCorrection.is_correction` parsing (mirror Phase 14 line 34 `from evolution.tools.tool_constraints import _parse_bool`).

---

## 4. SHARED PATTERNS

Cross-cutting patterns applied to multiple Phase 19 files.

### 4.1 Metrics.json schema

**Source:** `evolution/tools/session_miner.py` lines 212-228 (Phase 14 13-key schema)
**Applied to:** `session_prompt_miner.py` (defines schema) + `mine_prompt_sessions.py` (writes to disk)
**Phase 19 extension** (per CONTEXT specifics lines 225-239): add `persona_drift_thresholds_used: dict[str, float]`, `oracle_baseline_path: Optional[str]`, `judge_model: str`.

### 4.2 FAILED_<ts>/ failure path

**Source:** `evolution/tools/mine_tool_sessions.py` lines 239-247, 261-266, 303-309
**Applied to:** `mine_prompt_sessions.py` — same pattern, replace `tools/` with `prompts/`:

```python
failed = Path("datasets") / "prompts" / "sessions" / f"FAILED_{timestamp}"
failed.mkdir(parents=True, exist_ok=True)
(failed / "metrics.json").write_text(json.dumps({"error": "<error_key>"}, indent=2))
return 1
```

Three failure conditions (mirror Phase 14):
- `sessions_dir_missing` (lines 235-247)
- `no_sections_found` (mirror "no_tools_found" at lines 257-266)
- `no_examples_post_judge` (mirror lines 300-309)

### 4.3 Rich Panel + Table console output

**Source:** `evolution/tools/mine_tool_sessions.py` lines 143-175 (Table) + lines 226-233 (Panel)
**Applied to:** `mine_prompt_sessions.py` — same widget choices; 4 signal rows + TOTAL row.

### 4.4 JSONL bad-line tolerance (D-24)

**Source:** `evolution/tools/session_miner.py` lines 77-97 (`_load_jsonl_skip_bad`)
**Applied to:**
- `session_prompt_miner.py` — for miner output write side (already minimal — `json.dumps(...).write` is safe; the bad-line concern is on the READ side)
- `evolve_prompt_sections.py` `--session-source` load — wrap `PromptBehavioralDataset.load()` callsite with try/except per line, tracking via local counter (NOT modifying `PromptBehavioralDataset.load` per CONTEXT explicit guidance)

**Planner note:** CONTEXT line 93-94 says explicitly NOT to rewrite `PromptBehavioralDataset.load`. The skip-bad-line resilience for `--session-source` MUST live in evolve_prompt_sections.py at the call site, with metrics surfaced via Rich warn when skip rate > 5%.

---

## 5. NO ANALOG FOUND

None. All 6 files have direct templates or are explicitly read-only reuses.

---

## 6. Quick-Reference Anchors for Planner

| Concern | Anchor File | Lines | What to copy |
|---------|-------------|-------|--------------|
| SessionPromptMiner full structure | `session_miner.py` | 127-739 | Class shape + 3 extractors + judge + orchestration |
| ConfirmBehavioralExample Signature | `session_miner.py` 130-162 + `drift_detector.py` 32-74 | — | Signature shape; typed OutputFields |
| `_extract_user_correction` | `session_miner.py` | 416-497 | Keyword regex + LLM 二判 |
| `_extract_oracle_disagreement` | `session_miner.py` | 499-567 | baseline_module check |
| `_extract_persona_drift` (NEW) | `drift_detector.py` | 126-156 | `_check_one_run` direct call (1-run) |
| Hash dedup + bucket split | `session_miner.py` | 50-74, 716-738, 741-774 | Verbatim |
| Train-only duplication (D-13) | `session_miner.py` | 754-763 | Verbatim, replace multipliers |
| 13 Click flags | `mine_tool_sessions.py` | 327-378 | Copy + rename 3 (signals default, multiplier, output dir) |
| 1 NEW Click flag (drift thresholds) | `evolve_prompt_sections.py` | 1043-1053 | Style template |
| `_parse_signals` / `_parse_multiplier_override` | `mine_tool_sessions.py` | 52-95 | Rename `misselection` → `behavioral` |
| `--i-have-consent` gate | `mine_tool_sessions.py` | 194-201 | Verbatim, update path in message |
| Rich Table summary | `mine_tool_sessions.py` | 143-175 | Add `persona_drift` row |
| FAILED_<ts>/ pattern | `mine_tool_sessions.py` | 239-247, 261-266, 303-309 | Verbatim, replace tools/ → prompts/ |
| `PromptBehavioralExample` mining_signals field | `prompt_dataset.py` | 33-66 | In-place add + to_dict + from_dict |
| Dataset union after synthetic gen | `evolve_prompt_sections.py` | 246-276 | Insert new step 5b right after line 271 |
| Step 8c DriftDetector wiring | `evolve_prompt_sections.py` | 508-617 | **Already in place — do not touch** |
| SECRET_PATTERNS reuse | `external_importers.py` | 47-121 | Import only |
| extract_prompt_sections | `prompt_loader.py` | 80-137 | Call once per CLI run |
| `_parse_bool` for LLM 二判 | `prompt_constraints.py` | 15-29 | Import only |

---

## Metadata

**Analog search scope:** `evolution/tools/`, `evolution/prompts/`, `evolution/core/`
**Files read in full:**
- `evolution/tools/session_miner.py` (814 lines)
- `evolution/tools/mine_tool_sessions.py` (414 lines)
- `evolution/prompts/prompt_dataset.py` (330 lines)
- `evolution/prompts/drift_detector.py` (259 lines)
- `evolution/prompts/prompt_loader.py` (275 lines)
- `evolution/prompts/prompt_constraints.py` (120/147 lines — first 120 used)
- `evolution/prompts/evolve_prompt_sections.py` (targeted reads: 1-120, 240-329, 490-630, 1005-1072)
- `evolution/core/external_importers.py` (lines 40-170)
- `.planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-CONTEXT.md` (275 lines, full)
- `.planning/ROADMAP.md` (Phase 19 section + context)
- `.planning/REQUIREMENTS.md` (PMPT-V2-04 lookup)

**Pattern extraction date:** 2026-05-18
