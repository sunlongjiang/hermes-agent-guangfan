---
phase: 20-benchmark-gated-validation
plan: 03
type: execute
wave: 2
revised_at: 2026-05-19
depends_on:
  - 20-01-config-scaffolding-PLAN.md
files_modified:
  - evolution/benchmarks/benchmark_gate.py
  - evolution/prompts/prompt_loader.py
  - tests/benchmarks/test_benchmark_gate.py
autonomous: true
requirements:
  - PMPT-V2-03
requirements_addressed:
  - PMPT-V2-03
tags:
  - phase-20
  - benchmark
  - gate
  - virtual-overlay
must_haves:
  truths:
    - "evolution/benchmarks/benchmark_gate.py exposes class TBLiteBenchmarkGate with check(evolved_sections, *, cache_dir=None, use_cache=True) -> dict and check_all(original_sections, evolved_sections, *, ...) -> list[dict]"
    - "TBLiteBenchmarkGate constructor validates anchor schema (anchor_per_tier with all 4 tiers + dataset_revision_hash + hermes_agent_commit + stratified_subset_seed + calibration_timestamp) and raises ValueError on missing keys"
    - "TBLiteBenchmarkGate.check executes Virtual Prompt Overlay (snapshot -> os.replace -> 3-run TBLite -> ALWAYS restore in finally) per D-09"
    - "Risk_Score computed as sum(tier_weights[t] for t in tiers if breach[t]); default weights {easy:1.0, medium:1.5, hard:2.0, extreme:4.0}; REJECT when risk_score >= 4.0 (D-02)"
    - "Tier breach test = mean(3-run candidate) < max(anchor_mean, moving_avg) - 1.96 * candidate_stdev (D-01 Adaptive Sliding Window + CONFIDENCE_Z)"
    - "moving_avg falls back to anchor_mean when tblite_history.json absent or empty (D-01 first-run fallback)"
    - "Pre-flight _check_overlay_sanity verifies (a) hermes-agent prompt_builder.py write-access, (b) ~/.hermes/tmp + ~/.hermes/backups writable, (c) `git status --porcelain` empty (D-10)"
    - "Pre-flight _check_anchor_existence verifies anchor.hermes_agent_commit == git HEAD on hermes-agent (D-14 hard fail) and dataset_revision_hash mismatch is warn-only"
    - "Virtual Prompt Overlay uses os.replace when src/dst are on the same fs; falls back to shutil.copy2 when stat().st_dev differs (Risk Anchor 1 fs-boundary detection)"
    - "Cache hit: cache_dir/<artifact_hash>/result.json exists -> short-circuit; cache miss: write the file AFTER successful gate"
    - "evolution/prompts/prompt_loader.py write_back_section accepts optional dest: Path=None parameter (defaults to writing in-place to prompt_builder_path); when dest is provided, write to dest (used by Virtual Prompt Overlay to stage evolved copy)"
    - "tests/benchmarks/test_benchmark_gate.py contains TestTBLiteBenchmarkGate class with at least 12 tests covering Risk_Score / anchor staleness / dirty-git / fs-boundary / cache / moving_avg / infra_fail / threshold computation"
  artifacts:
    - path: evolution/benchmarks/benchmark_gate.py
      provides: "TBLiteBenchmarkGate class + Risk_Score algorithm + Virtual Prompt Overlay + Pre-flight checks + cache layer"
      contains: "class TBLiteBenchmarkGate"
      min_lines: 350
    - path: evolution/prompts/prompt_loader.py
      provides: "write_back_section accepts optional dest= parameter for Virtual Prompt Overlay staging"
      contains: "dest"
    - path: tests/benchmarks/test_benchmark_gate.py
      provides: "12+ unit tests with mocked TBLiteRunner.run + mocked subprocess (git status / git rev-parse)"
      contains: "class TestTBLiteBenchmarkGate"
      min_lines: 350
  key_links:
    - from: benchmark_gate.py
      to: evolution.benchmarks.tblite_runner.TBLiteRunner
      via: "self.runner = TBLiteRunner(config); self.runner.run(task_filter=..., output_dir=...)"
      pattern: "TBLiteRunner"
    - from: benchmark_gate.py
      to: hermes-agent/agent/prompt_builder.py (Virtual Prompt Overlay target)
      via: "os.replace(overlay_path, target) on same fs; shutil.copy2 fallback on cross fs"
      pattern: "os\\.replace|shutil\\.copy2"
    - from: benchmark_gate.py
      to: evolution.prompts.prompt_loader.write_back_section (with dest=)
      via: "write_back_section(prompt_builder_path=target, section=s, new_text=s.text, dest=overlay_path)"
      pattern: "write_back_section.*dest"
    - from: benchmark_gate.py
      to: cache_dir/<artifact_hash>/result.json
      via: "compute_artifact_hash(...) -> cache_dir / artifact_hash / 'result.json'"
      pattern: "compute_artifact_hash"
    - from: benchmark_gate.py
      to: tblite_history.json (moving_avg history)
      via: "json.loads(history_path.read_text()) -> running avg over last N=10 accepted runs"
      pattern: "moving_avg"
---

<objective>
Wave 2 (parallel with Plan 02) — Build `TBLiteBenchmarkGate`, the algorithm + orchestration core of Phase 20's final regression gate. Mirror Phase 18 `DriftDetector` class structure (PATTERNS §File 3 exact analog at `evolution/prompts/drift_detector.py:77-258`) but with 5 critical adaptations:

1. **No LLM judge** — TBLite is a binary subprocess signal, not a DSPy ChainOfThought. The constructor takes `anchor: dict` + `stratified_subset: dict` + optional `moving_avg_history: list[dict]` instead of `thresholds: dict`.
2. **Virtual Prompt Overlay** (D-09) — Phase 20 is the project's first deliberate write-restore path. `_run_overlay` snapshots `hermes-agent/agent/prompt_builder.py` → builds evolved copy at `~/.hermes/tmp/benchmark_<ts>/` → atomic `os.replace` (POSIX rename, same-fs) OR `shutil.copy2` fallback (cross-fs, Risk Anchor 1). `_restore_overlay` ALWAYS runs in `finally` so even SIGTERM-killed TBLite doesn't leave hermes-agent in a polluted state.
3. **Risk_Score algorithm** (D-02) — tier-weighted breach sum: `risk = Σ tier_weights[t] for t in tiers if breach[t]`. Default `{easy:1.0, medium:1.5, hard:2.0, extreme:4.0}`, reject at 4.0. Single extreme breach (4.0) reject by single point; cumulative easy+medium+hard breach (1+1.5+2=4.5) reject by accumulation.
4. **Pre-flight checks** (D-10 + D-14) — `_check_overlay_sanity` (write-access + git clean) and `_check_anchor_existence` (hermes_agent_commit match) raise `SystemExit(1)` with Rich-formatted error.
5. **Content-addressed cache** (D-15) — `cache_dir / artifact_hash / result.json` — short-circuit on hit; write on miss; the cache key uses `compute_artifact_hash` from Plan 02.

Also: extend `evolution/prompts/prompt_loader.py:write_back_section` to accept an optional `dest: Path = None` parameter so the Overlay can write the evolved copy to a staging path WITHOUT mutating `prompt_builder.py` in-place. This is the minimum-invasive contract extension PATTERNS §File 3 §_run_overlay recommends as path (a).

Output: 1 new file (`benchmark_gate.py` ~400 lines), 1 small modification (`prompt_loader.py` +5-10 lines), 1 new test file (~400 lines, 12+ tests).

Purpose: Plan 04 (`build_tblite_calibration`) needs `TBLiteBenchmarkGate._compute_risk_score` and `compute_artifact_hash` for its anchor builder; Plan 06 (`evolve_prompt_sections` step 10.5) instantiates `TBLiteBenchmarkGate` and calls `check_all(...)`.

This plan is parallel-safe with Plan 02 because both share NO files (Plan 02 = tblite_runner.py; Plan 03 = benchmark_gate.py + prompt_loader.py). The import dependency `benchmark_gate -> tblite_runner` is resolved at wave-end (both files committed before Wave 3 starts).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/20-benchmark-gated-validation/20-CONTEXT.md
@.planning/phases/20-benchmark-gated-validation/20-PATTERNS.md
@evolution/prompts/drift_detector.py
@evolution/prompts/prompt_loader.py
@evolution/core/constraints.py
@evolution/core/config.py
@tests/prompts/test_drift_detector.py
@./CLAUDE.md

<interfaces>
<!-- Wave 1 contracts (Plan 01 EvolutionConfig additions). -->
From evolution/core/config.py (after Plan 01):
```python
@dataclass
class EvolutionConfig:
    hermes_agent_path: Path
    benchmark_max_cost_usd: float = 50.0
    tblite_estimated_cost_per_task_usd: float = 0.4
    benchmark_runs: int = 3
    benchmark_heartbeat_seconds: int = 60
    # ... plus all existing fields
```

<!-- Wave 2 sibling contracts (Plan 02 — both plans race; integration verified at end). -->
From evolution/benchmarks/tblite_runner.py (Plan 02 — assumed present at integration time):
```python
TBLITE_RUNNER_VERSION: str = "1.0"

@dataclass
class TBLiteRunResult:
    per_task: list[dict]
    subprocess_runtime_seconds: float
    hang_count: int
    cost_breakdown: dict[str, float]
    samples_jsonl_path: Optional[Path]
    exit_code: int
    status: str
    jsonl_skipped_lines: int
    stderr_tail: list[str]

class TBLiteRunner:
    def __init__(self, config, *, heartbeat_seconds=None, max_hangs=3): ...
    def run(self, task_filter: list[str], output_dir: Path, *, runs: int = 1) -> TBLiteRunResult: ...

def compute_artifact_hash(evolved_sections, dataset_revision_hash: str, stratified_subset_seed: int, tblite_runner_version: str = TBLITE_RUNNER_VERSION) -> str: ...
```

<!-- Phase 18 analog (drift_detector.py:77-258 — class structure template). -->
From evolution/prompts/drift_detector.py:77-156 (DriftDetector class init + check_all):
```python
class DriftDetector:
    DriftScoreSignature = DriftScoreSignature

    def __init__(self, config: EvolutionConfig, thresholds: dict):
        missing = set(DRIFT_DIMENSIONS) - set(thresholds.keys())
        if missing:
            raise ValueError(f"thresholds missing dimensions: {sorted(missing)}")
        self.config = config
        self.thresholds = thresholds
        # ... DSPy LM setup ...

    def check_all(self, original_sections, evolved_sections) -> list:
        original_map = {s.section_id: s for s in original_sections}
        results = []
        for evolved in evolved_sections:
            original = original_map.get(evolved.section_id)
            if original is None:
                continue
            results.append(self.check(evolved.section_id, original.text, evolved.text))
        return results
```

<!-- Phase 7 contract (prompt_loader.py write_back_section — needs dest= extension). -->
From evolution/prompts/prompt_loader.py:142-182:
```python
def write_back_section(prompt_builder_path: Path, section: PromptSection, new_text: str) -> None:
    """Write evolved text back to prompt_builder.py, preserving format."""
    source = prompt_builder_path.read_text()
    lines = source.splitlines(keepends=True)
    start_line, end_line = section.line_range
    if section.section_id.startswith("platform_hints."):
        replacement = _format_dict_value_paren_concat(new_text, indent=8)
    else:
        var_name = section.section_id.upper()
        replacement = _format_paren_concat(var_name, new_text, indent=4)
    if not replacement.endswith("\n"):
        replacement += "\n"
    replacement_lines = replacement.splitlines(keepends=True)
    new_lines = lines[:start_line - 1] + replacement_lines + lines[end_line:]
    prompt_builder_path.write_text("".join(new_lines))
```

<!-- D-02 / D-01 / D-15 schemas from CONTEXT §Specifics. -->
Risk_Score: TIER_WEIGHTS = {"easy": 1.0, "medium": 1.5, "hard": 2.0, "extreme": 4.0}; REJECT_THRESHOLD = 4.0; CONFIDENCE_Z = 1.96
Stratified subset distribution: {"easy": 12, "medium": 8, "hard": 7, "extreme": 3} = 30 tasks
Watermark check: estimated = cost_per_task * num_tasks * num_runs; watermark = estimated * 3; if watermark > available -> SystemExit(1)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Extend evolution/prompts/prompt_loader.py write_back_section with optional dest: Path = None parameter</name>
  <files>evolution/prompts/prompt_loader.py</files>
  <read_first>
    - evolution/prompts/prompt_loader.py (entire file — confirm exact write_back_section signature and body at lines 142-182)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 3 §_run_overlay (3 options listed, recommendation = option (a) "extend write_back_section with dest")
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §D-09 step 2 + step 3 (overlay staging + atomic replace)
    - tests/prompts/ (sample test files — confirm no test exercises write_back_section's dest= parameter yet so backward-compat is preserved)
  </read_first>
  <action>
    Perform 1 surgical Edit on `evolution/prompts/prompt_loader.py` to add an optional `dest: Path = None` parameter to `write_back_section`. The default (`None`) preserves the current in-place behavior; when `dest` is supplied, the function reads `prompt_builder_path` for source content + line ranges and writes the result to `dest` instead. **Backward-compat is REQUIRED** — every existing call site (Phase 7-19) must continue to work without modification.

    **Edit 1 — Replace the `write_back_section` signature and final write line.** Locate the exact function body (lines 142-182). Replace the entire function with:

    ```python
    def write_back_section(
        prompt_builder_path: Path,
        section: PromptSection,
        new_text: str,
        *,
        dest: Path | None = None,
    ) -> None:
        """Write evolved text back to prompt_builder.py, preserving format.

        Reads the file, determines section type from section_id, formats the
        replacement text as parenthesized string concatenation, and replaces
        the lines at section.line_range.

        For batch writes, callers must process sections from bottom of file
        upward (highest line_range first) so earlier sections' line numbers
        remain valid.

        Args:
            prompt_builder_path: Path to prompt_builder.py — ALWAYS used as the
                SOURCE of original content + line range. Even when ``dest`` is
                provided, the function reads from this path to construct the
                replacement.
            section: The PromptSection to replace (provides line_range).
            new_text: The evolved text to write back.
            dest: Phase 20 D-09 Virtual Prompt Overlay extension. When None
                (the default), the rewritten content is written back in-place
                to ``prompt_builder_path`` — preserving the Phase 7-19
                contract. When non-None, the rewritten content is written to
                ``dest`` instead, leaving ``prompt_builder_path`` untouched.
                The Overlay uses dest=overlay_path to stage an evolved copy
                in ~/.hermes/tmp/benchmark_<ts>/, then atomically swaps it
                into hermes-agent via os.replace.
        """
        source = prompt_builder_path.read_text()
        lines = source.splitlines(keepends=True)

        start_line, end_line = section.line_range  # 1-based inclusive

        if section.section_id.startswith("platform_hints."):
            # Dict value: replace only the value's string content lines
            replacement = _format_dict_value_paren_concat(new_text, indent=8)
        else:
            # Top-level str assignment: replace entire assignment block
            var_name = section.section_id.upper()
            replacement = _format_paren_concat(var_name, new_text, indent=4)

        # Ensure replacement ends with newline
        if not replacement.endswith("\n"):
            replacement += "\n"

        # Line-level replacement (1-based inclusive -> 0-based slice)
        replacement_lines = replacement.splitlines(keepends=True)
        new_lines = lines[:start_line - 1] + replacement_lines + lines[end_line:]

        # D-09 Virtual Prompt Overlay: write to dest if provided, else in-place.
        # Both branches do an atomic-ish write — Path.write_text on POSIX is
        # write-to-temp + rename, but BenchmarkGate's caller can layer an
        # outer os.replace for cross-fs atomicity.
        output_path = dest if dest is not None else prompt_builder_path
        output_path.write_text("".join(new_lines))
    ```

    After editing, run `.venv/bin/python -c "from evolution.prompts.prompt_loader import write_back_section; import inspect; sig = inspect.signature(write_back_section); assert 'dest' in sig.parameters, 'dest param missing'; assert sig.parameters['dest'].default is None, 'dest default must be None'; print('OK')"` and `.venv/bin/pytest tests/prompts/ -q` to confirm zero regression on existing Phase 7-19 tests.

    Implements: PATTERNS §File 3 §_run_overlay option (a) "extend write_back_section with dest"; CONTEXT §D-09 step 2-3 Virtual Prompt Overlay staging path.
  </action>
  <verify>
    <automated>.venv/bin/python -c "from evolution.prompts.prompt_loader import write_back_section; import inspect; sig = inspect.signature(write_back_section); assert 'dest' in sig.parameters, 'dest param missing'; assert sig.parameters['dest'].default is None, f'dest default not None: {sig.parameters[\"dest\"].default!r}'; assert sig.parameters['dest'].kind.name in ('KEYWORD_ONLY','POSITIONAL_OR_KEYWORD'), 'dest must be keyword-able'; print('OK signature')" && .venv/bin/python -c "
import tempfile, pathlib
from evolution.prompts.prompt_loader import write_back_section, PromptSection

# round-trip on real prompt_builder via tmp file
src = pathlib.Path(tempfile.mkdtemp()) / 'pb.py'
src.write_text('MEMORY_GUIDANCE = (\n    \"old text\"\n)\n')
sec = PromptSection(section_id='memory_guidance', text='old text', char_count=8, line_range=(1, 3), source_path=src)
# dest=None -> in-place
write_back_section(src, sec, 'new text')
assert 'new text' in src.read_text(), 'in-place write failed'
# Reset and test dest=<other path>
src.write_text('MEMORY_GUIDANCE = (\n    \"old text\"\n)\n')
out = pathlib.Path(tempfile.mkdtemp()) / 'pb_overlay.py'
write_back_section(src, sec, 'overlay text', dest=out)
assert 'overlay text' in out.read_text(), 'dest write failed'
assert 'old text' in src.read_text(), 'source must NOT be modified when dest is provided'
print('OK round-trip both modes')
" && .venv/bin/pytest tests/prompts/ -q --tb=line 2>&1 | tail -3 | grep -E '[0-9]+ passed' || (echo "FAIL: tests/prompts/ regressed after prompt_loader.py edit"; exit 1)</automated>
  </verify>
  <acceptance_criteria>
    - `write_back_section` signature has a `dest: Path | None = None` keyword parameter.
    - Default behavior (no dest=) writes in-place to `prompt_builder_path` (backward-compat).
    - When `dest=<path>` is passed, the function writes to `dest` and leaves `prompt_builder_path` UNCHANGED.
    - All existing `pytest tests/prompts/` tests continue to PASS (no regression).
  </acceptance_criteria>
  <done>
    - prompt_loader.py write_back_section accepts dest= parameter
    - Phase 7-19 callers unaffected (no signature break)
    - Round-trip test confirms in-place + dest mode both work
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create evolution/benchmarks/benchmark_gate.py with TBLiteBenchmarkGate class (Risk_Score + Virtual Prompt Overlay + Pre-flight + Cache)</name>
  <files>evolution/benchmarks/benchmark_gate.py</files>
  <read_first>
    - evolution/prompts/drift_detector.py (entire file — class structure analog, 77-258)
    - evolution/benchmarks/tblite_runner.py (Plan 02 output — confirm public API)
    - evolution/prompts/prompt_loader.py (just-modified — confirm dest= parameter)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 3 (entire — Adaptation Delta 5 deviations + 3 sub-patterns)
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §D-01..D-04 (Risk_Score + Adaptive Sliding Window + 3-run + report schema) + §D-09 (Virtual Prompt Overlay 6-step flow) + §D-10 (Pre-flight overlay sanity) + §D-14 (anchor existence) + §D-15 (content-addressed cache) + §Specifics (tblite_report.json schema verbatim) + §Risk Anchors (fs-boundary detection + Modal infra failure + anchor staleness)
    - evolution/core/constraints.py (ConstraintResult import — return value schema)
  </read_first>
  <behavior>
    The unit test file in Task 3 will exercise these behaviors:
    1. Constructor with missing anchor keys raises ValueError.
    2. Constructor with anchor_per_tier missing one tier raises ValueError.
    3. _check_anchor_existence: anchor.hermes_agent_commit != current HEAD → SystemExit(1).
    4. _check_anchor_existence: dataset_revision_hash mismatch → warn only (no exit).
    5. _check_overlay_sanity: `git status --porcelain` non-empty → SystemExit(1).
    6. _check_overlay_sanity: hermes-agent dir not writable → SystemExit(1).
    7. _compute_risk_score: single extreme breach (weight 4.0) → risk_score == 4.0 → reject.
    8. _compute_risk_score: easy+medium+hard all breach (1+1.5+2 = 4.5) → risk_score >= 4.0 → reject.
    9. _compute_risk_score: only easy+medium breach (1+1.5 = 2.5) → risk_score < 4.0 → accept.
    10. _aggregate_per_tier with infra_fail rows: those rows excluded from denominator.
    11. moving_avg falls back to anchor when history empty (D-01 first-run).
    12. Cache hit short-circuits: pre-write `cache_dir/<hash>/result.json` → check returns cached dict, never calls runner.run.
    13. Cache miss writes file AFTER successful gate (not on reject).
    14. fs-boundary detection: when st_dev differs, shutil.copy2 fallback path is taken.
    15. _restore_overlay called even when TBLiteRunner.run raises (try/finally guarantee).
    16. Threshold computation: anchor mean=0.85, candidate stdev=0.01 → threshold = 0.85 - 1.96*0.01 = 0.8304 (within 1e-4 tolerance).
  </behavior>
  <action>
    Create `evolution/benchmarks/benchmark_gate.py` using the Write tool. Target ~400-450 lines.

    **Module docstring + imports:**

    ```python
    """TBLite benchmark-gated validation for evolved prompt sections (Phase 20).

    Final gate (NOT in GEPA loop — PITFALL #7 prevention #1 hard constraint).
    Compares evolved prompt sections against an anchor + moving-average
    baseline using TBLite stratified subset (~30 tasks) with 3-run averaging
    and tier-weighted Risk_Score. Risk_Score >= REJECT_THRESHOLD (default 4.0)
    -> reject.

    Phase 18 DriftDetector class structure analog (drift_detector.py:77-258).
    Five core deviations (per PATTERNS §File 3):
      1. No DSPy LLM judge — TBLite is binary subprocess signal.
      2. Constructor takes anchor + stratified_subset + moving_avg_history
         instead of thresholds dict.
      3. _check_one_run replaced by TBLiteRunner.run() (subprocess wrapper).
      4. Risk_Score = Σ tier_weights[t] for t in tiers if breach[t] (D-02).
      5. Virtual Prompt Overlay (D-09): file-level atomic replace of
         hermes-agent/agent/prompt_builder.py via os.replace + always-restore.

    Decision references:
      D-01 Adaptive Sliding Window: breach test uses
        candidate_mean < max(anchor_mean, moving_avg) - 1.96 * candidate_stdev
      D-02 tier-weighted Risk_Score with reject threshold 4.0
      D-03 3-run median-of-N
      D-04 tblite_report.json schema (returned by check())
      D-09 Virtual Prompt Overlay snapshot/replace/restore
      D-10 Pre-flight overlay sanity (git clean + path writable)
      D-14 Anchor existence + commit-match
      D-15 Content-addressed cache
    """

    from __future__ import annotations

    import json
    import os
    import shutil
    import statistics
    import subprocess
    import sys
    from datetime import datetime
    from pathlib import Path
    from typing import Optional

    from rich.console import Console

    from evolution.core.config import EvolutionConfig
    from evolution.core.constraints import ConstraintResult
    from evolution.benchmarks.tblite_runner import (
        TBLITE_RUNNER_VERSION,
        TBLiteRunResult,
        TBLiteRunner,
        compute_artifact_hash,
    )

    console = Console()
    ```

    **Module-level constants** (CONTEXT §Specifics verbatim):

    ```python
    # D-02 default tier weights. Each tier breaching its 1.96σ band adds its
    # weight to risk_score; the gate rejects when risk_score >= REJECT_THRESHOLD.
    # Semantics: a single extreme breach (4.0) is single-point fatal; cumulative
    # easy+medium+hard breach (1.0+1.5+2.0=4.5) is cumulative-fatal. Dual defense.
    TIER_WEIGHTS: dict[str, float] = {
        "easy": 1.0,
        "medium": 1.5,
        "hard": 2.0,
        "extreme": 4.0,
    }
    REJECT_THRESHOLD: float = 4.0

    # D-01: 1.96σ ≈ 95% one-sided confidence interval. Conservative —
    # candidate must be statistically WORSE than the band to count as a
    # breach. Lowering increases false-positive rejects; raising risks
    # silent regressions.
    CONFIDENCE_Z: float = 1.96

    # D-CAL-01 / D-05: the 4 tiers Phase 20 anchors against. Stratified
    # subset distribution lives in datasets/prompts/tblite_stratified_subset.json.
    TIERS: tuple[str, ...] = ("easy", "medium", "hard", "extreme")

    # Required keys in the anchor JSON (D-CAL-01 schema, validated in __init__).
    _ANCHOR_REQUIRED_KEYS = frozenset({
        "anchor_per_tier",
        "dataset_revision_hash",
        "hermes_agent_commit",
        "stratified_subset_seed",
        "calibration_timestamp",
    })

    # Per-tier anchor inner keys.
    _ANCHOR_TIER_KEYS = frozenset({"mean", "stdev", "n"})
    ```

    **TBLiteBenchmarkGate class:**

    ```python
    class TBLiteBenchmarkGate:
        """Phase 20 final regression gate over evolved prompt sections.

        Args:
            config: EvolutionConfig (uses hermes_agent_path, benchmark_runs,
                benchmark_max_cost_usd).
            anchor: Loaded contents of datasets/prompts/tblite_anchor.json.
                Required keys per D-CAL-01 (see _ANCHOR_REQUIRED_KEYS).
            stratified_subset: Loaded datasets/prompts/tblite_stratified_subset.json
                with task_filter (list[str]) + per_tier_counts + seed.
            moving_avg_history: List of past accepted tblite_history.json
                entries (most recent first, N <= 10). Empty list -> moving_avg
                falls back to anchor_mean per D-01.
            tier_weights: Override TIER_WEIGHTS (exposed for ops tuning).
            reject_threshold: Override REJECT_THRESHOLD.
            runs: D-03 3-run averaging count (defaults to config.benchmark_runs).
            confidence_z: D-01 1.96σ band (rarely tuned).

        Raises:
            ValueError: anchor or stratified_subset schema invalid.
        """

        def __init__(
            self,
            config: EvolutionConfig,
            anchor: dict,
            stratified_subset: dict,
            *,
            moving_avg_history: Optional[list] = None,
            tier_weights: Optional[dict] = None,
            reject_threshold: Optional[float] = None,
            runs: Optional[int] = None,
            confidence_z: float = CONFIDENCE_Z,
        ):
            # ── Anchor schema validation (D-CAL-01) ──
            missing_top = _ANCHOR_REQUIRED_KEYS - set(anchor.keys())
            if missing_top:
                raise ValueError(
                    f"anchor missing required top-level keys: {sorted(missing_top)}"
                )
            per_tier = anchor["anchor_per_tier"]
            missing_tiers = set(TIERS) - set(per_tier.keys())
            if missing_tiers:
                raise ValueError(
                    f"anchor.anchor_per_tier missing tiers: {sorted(missing_tiers)} "
                    f"(D-CAL-01 requires all 4: easy/medium/hard/extreme)"
                )
            for tier in TIERS:
                missing_inner = _ANCHOR_TIER_KEYS - set(per_tier[tier].keys())
                if missing_inner:
                    raise ValueError(
                        f"anchor.anchor_per_tier[{tier!r}] missing keys: "
                        f"{sorted(missing_inner)}"
                    )
            # ── Stratified subset validation ──
            if "task_filter" not in stratified_subset or not isinstance(
                stratified_subset["task_filter"], list
            ):
                raise ValueError("stratified_subset must have task_filter: list[str]")
            if not stratified_subset["task_filter"]:
                raise ValueError("stratified_subset.task_filter is empty")

            self.config = config
            self.anchor = anchor
            self.stratified_subset = stratified_subset
            self.moving_avg_history = list(moving_avg_history or [])
            self.tier_weights = dict(tier_weights or TIER_WEIGHTS)
            self.reject_threshold = (
                float(reject_threshold)
                if reject_threshold is not None
                else REJECT_THRESHOLD
            )
            self.runs = int(
                runs if runs is not None
                else getattr(config, "benchmark_runs", 3)
            )
            if self.runs < 1:
                raise ValueError(f"runs must be >= 1, got {self.runs}")
            self.confidence_z = float(confidence_z)

            self.runner = TBLiteRunner(config)
            self._target_path = (
                Path(config.hermes_agent_path) / "agent" / "prompt_builder.py"
            )

        # ── Pre-flight validators ──────────────────────────────────────────

        def _check_overlay_sanity(self) -> None:
            """D-10 Pre-flight: validate hermes-agent + tmp/backups paths.

            Raises SystemExit(1) with Rich-formatted error on any failure:
                - hermes-agent prompt_builder.py parent dir not writable
                - ~/.hermes/tmp or ~/.hermes/backups not creatable/writable
                - `git status --porcelain` (cwd=hermes_agent_path) non-empty
            """
            if not self._target_path.exists():
                console.print(
                    f"[red]hermes-agent prompt_builder.py not found at "
                    f"{self._target_path}[/red]"
                )
                sys.exit(1)
            if not os.access(self._target_path.parent, os.W_OK):
                console.print(
                    f"[red]hermes-agent path not writable: "
                    f"{self._target_path.parent}[/red]"
                )
                sys.exit(1)
            for p in (Path.home() / ".hermes" / "tmp",
                      Path.home() / ".hermes" / "backups"):
                try:
                    p.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    console.print(f"[red]Cannot create {p}: {e}[/red]")
                    sys.exit(1)
                if not os.access(p, os.W_OK):
                    console.print(f"[red]Not writable: {p}[/red]")
                    sys.exit(1)

            # git status --porcelain check (D-10 + CONCERNS §M6 mitigation).
            try:
                res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(self.config.hermes_agent_path),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                console.print(
                    f"[red]git status check failed: {type(e).__name__}: {e}[/red]"
                )
                sys.exit(1)
            if res.stdout.strip():
                console.print(
                    f"[red]hermes-agent has uncommitted changes — refusing "
                    f"overlay.\nStash or commit first:\n{res.stdout}[/red]"
                )
                sys.exit(1)

        def _check_anchor_existence(self) -> None:
            """D-14 Pre-flight: validate anchor freshness vs current hermes-agent HEAD.

            Two-level check (D-14 + W-5 revision 2026-05-19):
              hermes_agent_commit mismatch -> hard SystemExit(1) (anchor is
                  baseline-dependent; prompt baseline drift invalidates anchor).
              dataset_revision_hash mismatch -> Rich-formatted YELLOW warning,
                  NOT exit. Dataset upgrade is tolerable (cache key
                  invalidates correctly via TBLiteRunner cache fingerprint).
                  Live comparison uses _hf_dataset_revision (same fail-open
                  helper Plan 04 uses); if HF is unreachable we silently keep
                  the anchor's recorded hash and emit no warning — preserves
                  offline workflows.
            """
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(self.config.hermes_agent_path),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                console.print(
                    f"[red]git rev-parse failed: {type(e).__name__}: {e}[/red]"
                )
                sys.exit(1)
            current_commit = res.stdout.strip()
            anchor_commit = self.anchor.get("hermes_agent_commit", "")
            if current_commit != anchor_commit:
                console.print(
                    f"[red]Anchor stale: anchor hermes_agent_commit="
                    f"{anchor_commit[:8] or '<missing>'} but current="
                    f"{current_commit[:8] or '<missing>'}.\nRe-calibrate: "
                    f"python -m evolution.benchmarks.build_tblite_calibration[/red]"
                )
                sys.exit(1)

            # W-5 (D-14 warn-only branch): compare dataset_revision_hash.
            # Skip the live HF probe when the anchor itself is fail-open
            # ('unknown_v*' prefix) — there is nothing to compare against.
            anchor_revision = self.anchor.get("dataset_revision_hash", "")
            if anchor_revision and not anchor_revision.startswith("unknown_v"):
                try:
                    # Lazy-import the helper from Plan 04 to avoid a circular
                    # dependency at module load time. Plan 04 defines
                    # _hf_dataset_revision with fail-open semantics; if HF is
                    # unavailable it returns a literal 'unknown_v<runner>'
                    # string which we treat as "no probe possible" -> silent.
                    from evolution.benchmarks.build_tblite_calibration import (
                        _hf_dataset_revision as _probe_hf_revision,
                    )
                    live_revision = _probe_hf_revision()
                except Exception:
                    live_revision = ""
                if (
                    live_revision
                    and not live_revision.startswith("unknown_v")
                    and live_revision != anchor_revision
                ):
                    console.print(
                        f"[yellow]\u26a0 dataset_revision_hash mismatch: "
                        f"anchor={anchor_revision[:12]} but live HF="
                        f"{live_revision[:12]}. Dataset upgraded since "
                        f"calibration — cache will invalidate via "
                        f"compute_artifact_hash. Continuing.[/yellow]"
                    )

        # ── Virtual Prompt Overlay (D-09) ───────────────────────────────────

        def _run_overlay(self, evolved_sections: list) -> tuple[Path, Path]:
            """Snapshot + atomic replace prompt_builder.py with evolved copy.

            Returns (snapshot_path, overlay_path). Both live in
            ~/.hermes/tmp/benchmark_<ts>/.

            os.replace is atomic on POSIX when src and dst are on the same fs;
            on cross-fs (Risk Anchor 1) we fall back to shutil.copy2 which
            is NOT atomic but the window is sub-millisecond.
            """
            from evolution.prompts.prompt_loader import write_back_section

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            tmp_dir = Path.home() / ".hermes" / "tmp" / f"benchmark_{ts}"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            snapshot_path = tmp_dir / "prompt_builder.py.original"
            overlay_path = tmp_dir / "prompt_builder.py.evolved"

            # Step 1: snapshot original (D-09 step 1).
            shutil.copy2(self._target_path, snapshot_path)

            # Step 2: seed overlay with original, then write evolved sections
            # bottom-up so earlier section line ranges remain valid
            # (prompt_loader.py:153-155 docstring).
            shutil.copy2(self._target_path, overlay_path)
            sorted_evolved = sorted(
                evolved_sections,
                key=lambda s: s.line_range[0],
                reverse=True,
            )
            for sec in sorted_evolved:
                # Use prompt_builder_path=target as the SOURCE of line ranges
                # but write to dest=overlay_path so the original on disk is
                # untouched until step 3.
                write_back_section(
                    self._target_path,
                    sec,
                    sec.text,
                    dest=overlay_path,
                )

            # Step 3: atomic-or-fallback replace target with overlay
            # (Risk Anchor 1 fs-boundary detection).
            try:
                same_fs = (
                    self._target_path.parent.stat().st_dev
                    == overlay_path.parent.stat().st_dev
                )
            except OSError:
                same_fs = False
            if same_fs:
                os.replace(str(overlay_path), str(self._target_path))
                # I-1 (2026-05-19): post-replace shutil.copy2 removed —
                # overlay_path no longer needs to exist; snapshot_path is
                # the canonical original we rely on in _restore_overlay.
                # The previous "re-materialize overlay_path" was vestigial
                # and inflated the shutil.copy2 grep count to 3 without
                # adding a recovery guarantee.
            else:
                # RA1 fallback: non-atomic but bounded copy.
                shutil.copy2(str(overlay_path), str(self._target_path))

            return snapshot_path, overlay_path

        def _restore_overlay(self, snapshot_path: Path) -> None:
            """D-09 step 5: ALWAYS restore (even on subprocess hang/error)."""
            if not snapshot_path.exists():
                console.print(
                    f"[red]Snapshot missing during restore: {snapshot_path}. "
                    f"hermes-agent may be polluted — check {self._target_path}[/red]"
                )
                return
            try:
                same_fs = (
                    self._target_path.parent.stat().st_dev
                    == snapshot_path.parent.stat().st_dev
                )
            except OSError:
                same_fs = False
            if same_fs:
                os.replace(str(snapshot_path), str(self._target_path))
            else:
                shutil.copy2(str(snapshot_path), str(self._target_path))

        # ── Risk_Score algorithm (D-01 + D-02) ─────────────────────────────

        def _one_run_per_tier_pass_rate(
            self, run_result: TBLiteRunResult
        ) -> dict[str, float]:
            """Compute per-tier pass rate from one TBLiteRunResult.

            Per Risk Anchor 3, infra_fail rows are EXCLUDED from both
            numerator and denominator. Tier with zero valid samples maps
            to 0.0 (conservative — counts as worst-case).
            """
            by_tier: dict[str, list[bool]] = {t: [] for t in TIERS}
            for task in run_result.per_task:
                if task.get("infra_fail"):
                    continue
                tier = str(task.get("category", "")).strip().lower()
                if tier in by_tier:
                    by_tier[tier].append(bool(task.get("passed", False)))
            return {
                t: (sum(v) / len(v) if v else 0.0)
                for t, v in by_tier.items()
            }

        def _moving_avg_per_tier(self) -> dict[str, float]:
            """D-01: moving_avg = mean of last <=10 accepted runs per tier.

            Falls back to anchor_mean when history is empty (first-run).
            """
            if not self.moving_avg_history:
                return {
                    t: self.anchor["anchor_per_tier"][t]["mean"]
                    for t in TIERS
                }
            history = self.moving_avg_history[:10]  # recent 10
            ma: dict[str, float] = {}
            for tier in TIERS:
                vals = []
                for entry in history:
                    pt = (entry.get("per_tier") or {}).get(tier) or {}
                    v = pt.get("mean")
                    if isinstance(v, (int, float)):
                        vals.append(float(v))
                ma[tier] = (
                    statistics.mean(vals) if vals
                    else self.anchor["anchor_per_tier"][tier]["mean"]
                )
            return ma

        def _aggregate_per_tier(
            self, per_run_per_tier: list[dict[str, float]]
        ) -> dict[str, dict]:
            """Combine 3-run per-tier means into the tblite_report.json shape.

            For each tier:
                mean = statistics.mean([r1, r2, r3])
                stdev = statistics.stdev([r1, r2, r3]) (3 points -> defined)
                threshold = max(anchor_mean, moving_avg) - 1.96 * stdev
                breach = mean < threshold  (lower = worse for pass-rate metric)

            Returns the per-tier dict matching D-04 schema.
            """
            ma = self._moving_avg_per_tier()
            per_tier: dict[str, dict] = {}
            for tier in TIERS:
                scores = [run.get(tier, 0.0) for run in per_run_per_tier]
                if len(scores) >= 2:
                    cand_mean = statistics.mean(scores)
                    cand_stdev = statistics.stdev(scores)
                else:
                    cand_mean = scores[0] if scores else 0.0
                    cand_stdev = 0.0
                anchor_mean = self.anchor["anchor_per_tier"][tier]["mean"]
                moving_avg = ma[tier]
                baseline = max(anchor_mean, moving_avg)
                threshold = baseline - self.confidence_z * cand_stdev
                breach = cand_mean < threshold
                per_tier[tier] = {
                    "scores": [round(s, 4) for s in scores],
                    "mean": round(cand_mean, 4),
                    "stdev": round(cand_stdev, 4),
                    "threshold": round(threshold, 4),
                    "anchor": round(anchor_mean, 4),
                    "moving_avg": round(moving_avg, 4),
                    "breach": bool(breach),
                }
            return per_tier

        def _compute_risk_score(self, per_tier_report: dict) -> float:
            """D-02: sum tier weights for breached tiers."""
            risk = 0.0
            for tier, data in per_tier_report.items():
                if data.get("breach"):
                    risk += self.tier_weights.get(tier, 1.0)
            return risk

        # ── Main entrypoints ────────────────────────────────────────────────

        def check(
            self,
            evolved_sections: list,
            *,
            cache_dir: Optional[Path] = None,
            use_cache: bool = True,
            output_dir: Optional[Path] = None,
        ) -> dict:
            """Run the full Phase 20 gate over a single evolved set.

            Steps:
                1. Cache lookup (D-15) -> short-circuit on hit.
                2. Pre-flight checks (D-10 + D-14).
                3. Virtual Prompt Overlay snapshot+replace (D-09).
                4. 3-run TBLite subprocess (D-03).
                5. ALWAYS restore overlay (D-09 step 5, try/finally).
                6. Aggregate per-tier + Risk_Score (D-01 + D-02).
                7. Build tblite_report.json shape (D-04).
                8. Cache write on miss (D-15).

            Returns:
                Dict matching D-04 schema + nested constraint_result:
                {decision, risk_score, reject_threshold, tier_weights, per_tier,
                 samples_jsonl_path, subprocess_runtime_seconds, cost_breakdown,
                 dataset_revision_hash, cache_hit, async_full_verify_pending,
                 constraint_result, jsonl_skipped_lines_total}
            """
            # 1. Cache lookup
            cache_key = compute_artifact_hash(
                evolved_sections,
                self.anchor["dataset_revision_hash"],
                int(self.anchor.get("stratified_subset_seed", 42)),
                TBLITE_RUNNER_VERSION,
            )
            if use_cache and cache_dir is not None:
                cache_path = cache_dir / cache_key / "result.json"
                if cache_path.exists():
                    cached = json.loads(cache_path.read_text())
                    cached["cache_hit"] = True
                    # Constraint result not serializable -> rebuild from decision.
                    cached["constraint_result"] = ConstraintResult(
                        passed=(cached["decision"] == "accept"),
                        constraint_name="tblite_benchmark",
                        message=f"[cache] Risk_Score={cached['risk_score']:.2f}",
                        details=json.dumps(cached.get("per_tier", {}), sort_keys=True),
                    )
                    return cached

            # 2. Pre-flight
            self._check_anchor_existence()
            self._check_overlay_sanity()

            # 3. Overlay
            snapshot_path, overlay_path = self._run_overlay(evolved_sections)

            # 4. 3-run subprocess with always-restore (5)
            per_run_per_tier: list[dict[str, float]] = []
            samples_paths: list[Path] = []
            total_runtime = 0.0
            total_cost: dict[str, float] = {}
            jsonl_skipped_total = 0
            run_status_any_error = False
            stderr_tails: list[list[str]] = []
            try:
                base_out = (
                    Path(output_dir) if output_dir is not None
                    else Path("output") / "prompts" / "_benchmark_runs" /
                         datetime.now().strftime("%Y%m%d_%H%M%S")
                )
                base_out.mkdir(parents=True, exist_ok=True)
                for run_idx in range(self.runs):
                    run_dir = base_out / f"run_{run_idx}"
                    run_result = self.runner.run(
                        task_filter=list(self.stratified_subset["task_filter"]),
                        output_dir=run_dir,
                    )
                    per_run_per_tier.append(
                        self._one_run_per_tier_pass_rate(run_result)
                    )
                    if run_result.samples_jsonl_path:
                        samples_paths.append(run_result.samples_jsonl_path)
                    total_runtime += run_result.subprocess_runtime_seconds
                    for k, v in run_result.cost_breakdown.items():
                        total_cost[k] = total_cost.get(k, 0.0) + v
                    jsonl_skipped_total += run_result.jsonl_skipped_lines
                    if run_result.status != "ok":
                        run_status_any_error = True
                        stderr_tails.append(run_result.stderr_tail)
            finally:
                # 5. ALWAYS restore (D-09 step 5)
                self._restore_overlay(snapshot_path)

            # 6. + 7. Aggregate + report
            per_tier_report = self._aggregate_per_tier(per_run_per_tier)
            risk_score = self._compute_risk_score(per_tier_report)
            decision = "reject" if risk_score >= self.reject_threshold else "accept"
            # Subprocess-level failure overrides accept (Plan 06 reviews status field).
            if run_status_any_error and decision == "accept":
                decision = "reject"

            report = {
                "decision": decision,
                "risk_score": round(risk_score, 4),
                "reject_threshold": self.reject_threshold,
                "tier_weights": self.tier_weights,
                "per_tier": per_tier_report,
                "samples_jsonl_path": str(samples_paths[-1]) if samples_paths else None,
                "subprocess_runtime_seconds": round(total_runtime, 2),
                "cost_breakdown": total_cost,
                "dataset_revision_hash": self.anchor["dataset_revision_hash"],
                "cache_hit": False,
                "async_full_verify_pending": False,  # set True by Plan 06 after dispatch
                "jsonl_skipped_lines_total": jsonl_skipped_total,
                "stderr_tails": stderr_tails,
                "artifact_hash": cache_key,
            }
            reason = (
                f"Risk_Score {risk_score:.2f} "
                f"({'>=' if decision == 'reject' else '<'}) "
                f"reject_threshold {self.reject_threshold:.2f}"
            )
            report["constraint_result"] = ConstraintResult(
                passed=(decision == "accept"),
                constraint_name="tblite_benchmark",
                message=reason,
                details=json.dumps(per_tier_report, sort_keys=True),
            )

            # 8. Cache write — ONLY on accept (rejected runs are not cached so
            # the same evolved set re-runs deterministically if user re-tries).
            if use_cache and cache_dir is not None and decision == "accept":
                cache_path_dir = cache_dir / cache_key
                cache_path_dir.mkdir(parents=True, exist_ok=True)
                serializable = {
                    k: v for k, v in report.items()
                    if k != "constraint_result"
                }
                (cache_path_dir / "result.json").write_text(
                    json.dumps(serializable, indent=2, sort_keys=True)
                )

            return report

        def check_all(
            self,
            original_sections: list,
            evolved_sections: list,
            *,
            cache_dir: Optional[Path] = None,
            use_cache: bool = True,
            output_dir: Optional[Path] = None,
        ) -> list[dict]:
            """Phase 18 DriftDetector.check_all sibling — but ONE invocation
            per evolved batch.

            Phase 20 gate operates on the WHOLE evolved set (not per-section)
            because TBLite measures system-level task pass rate. Returns a
            single-element list to match the Phase 18 pipeline contract for
            drop-in by evolve_prompt_sections.py step 10.5.
            """
            return [self.check(
                evolved_sections,
                cache_dir=cache_dir,
                use_cache=use_cache,
                output_dir=output_dir,
            )]
    ```

    After writing, verify import: `.venv/bin/python -c "from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate, TIER_WEIGHTS, REJECT_THRESHOLD, CONFIDENCE_Z, TIERS; print('OK')"`.

    Implements: PATTERNS §File 3 (entire) — class structure, 5 deviations, Virtual Prompt Overlay, Pre-flight checks, Risk_Score; CONTEXT §D-01..D-04, §D-09, §D-10, §D-14, §D-15; tblite_report.json schema from §Specifics; Risk Anchors 1 (fs-boundary) and 3 (infra_fail).
  </action>
  <verify>
    <automated>.venv/bin/python -c "from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate, TIER_WEIGHTS, REJECT_THRESHOLD, CONFIDENCE_Z, TIERS; assert TIER_WEIGHTS == {'easy':1.0,'medium':1.5,'hard':2.0,'extreme':4.0}, f'TIER_WEIGHTS wrong: {TIER_WEIGHTS}'; assert REJECT_THRESHOLD == 4.0, f'REJECT_THRESHOLD wrong: {REJECT_THRESHOLD}'; assert CONFIDENCE_Z == 1.96, f'CONFIDENCE_Z wrong: {CONFIDENCE_Z}'; assert TIERS == ('easy','medium','hard','extreme'), f'TIERS wrong: {TIERS}'; print('OK constants')" && grep -c 'os\.replace' evolution/benchmarks/benchmark_gate.py | awk '{ if ($1 < 2) { print "FAIL: os.replace must be used at least twice (overlay + restore)"; exit 1 } else { print "OK os.replace appears " $1 " times" } }' && grep -c 'shutil\.copy2' evolution/benchmarks/benchmark_gate.py | awk '{ if ($1 < 2) { print "FAIL: shutil.copy2 needed for snapshot + cross-fs fallback (>=2 uses after I-1 cleanup)"; exit 1 } else { print "OK" } }' && grep -c 'try:' evolution/benchmarks/benchmark_gate.py | awk '{ if ($1 < 1) { print "FAIL: no try block found"; exit 1 } else { print "OK" } }' && grep -c 'finally:' evolution/benchmarks/benchmark_gate.py | awk '{ if ($1 < 1) { print "FAIL: D-09 step 5 ALWAYS restore requires try/finally"; exit 1 } else { print "OK try/finally for overlay restore" } }' && grep -c 'sys\.exit(1)' evolution/benchmarks/benchmark_gate.py | awk '{ if ($1 < 2) { print "FAIL: D-10 + D-14 must each sys.exit(1) on failure"; exit 1 } else { print "OK sys.exit gates" } }' && grep -c 'compute_artifact_hash' evolution/benchmarks/benchmark_gate.py | awk '{ if ($1 < 1) { print "FAIL: cache key not used"; exit 1 } else { print "OK" } }' && grep -c 'subprocess\.run' evolution/benchmarks/benchmark_gate.py | awk '{ if ($1 < 2) { print "FAIL: D-10 git status check + D-14 git rev-parse both use subprocess.run"; exit 1 } else { print "OK 2 subprocess.run calls (git checks)" } }'</automated>
  </verify>
  <acceptance_criteria>
    - `from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate, TIER_WEIGHTS, REJECT_THRESHOLD, CONFIDENCE_Z, TIERS` succeeds.
    - `TIER_WEIGHTS == {"easy":1.0,"medium":1.5,"hard":2.0,"extreme":4.0}`.
    - `REJECT_THRESHOLD == 4.0`.
    - `CONFIDENCE_Z == 1.96`.
    - `grep -c 'os\.replace' evolution/benchmarks/benchmark_gate.py` >= 2 (overlay + restore paths).
    - `grep -c 'shutil\.copy2' evolution/benchmarks/benchmark_gate.py` >= 2 (snapshot + cross-fs fallback; I-1 cleanup removed the post-replace re-materialize).
    - `grep -c 'finally:' evolution/benchmarks/benchmark_gate.py` >= 1 (D-09 step 5 always-restore).
    - `grep -c 'sys\.exit(1)' evolution/benchmarks/benchmark_gate.py` >= 2 (D-10 + D-14 hard fails).
    - `grep -c 'compute_artifact_hash' evolution/benchmarks/benchmark_gate.py` >= 1 (cache key).
    - File line count >= 350.
  </acceptance_criteria>
  <done>
    - benchmark_gate.py created with TBLiteBenchmarkGate class
    - Risk_Score algorithm computes correct values for D-02 default weights
    - Virtual Prompt Overlay wraps subprocess in try/finally for always-restore
    - Pre-flight checks (D-10 + D-14) raise SystemExit on failure
    - Content-addressed cache hit/miss paths implemented
    - check_all() returns single-elem list for pipeline drop-in
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Create tests/benchmarks/test_benchmark_gate.py with 12+ tests covering Risk_Score / Pre-flight / fs-boundary / cache / overlay restore</name>
  <files>tests/benchmarks/test_benchmark_gate.py</files>
  <read_first>
    - tests/prompts/test_drift_detector.py (helper patterns: _FakeSection, _make_detector, severity ladder testing)
    - tests/prompts/test_drift_calibration.py (CliRunner pattern for CLI tests in Plan 04)
    - evolution/benchmarks/benchmark_gate.py (just-written — confirm interface)
    - evolution/benchmarks/tblite_runner.py (Plan 02 output — TBLiteRunResult shape for mocked fixtures)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 13 (12 test scenarios)
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §Risk Anchors §"anchor / moving_avg 数值漂移" + §"TBLite Modal infra failure"
  </read_first>
  <behavior>
    Each test must use `unittest.mock.patch.object(gate, "runner")` (mock the runner instance) and `patch("evolution.benchmarks.benchmark_gate.subprocess.run")` for git invocations. NO real subprocess. NO real git invocations.

    Required test methods (>= 14):
    1. test_constructor_validates_anchor_top_level_keys
    2. test_constructor_validates_anchor_per_tier_tiers
    3. test_constructor_validates_stratified_subset_task_filter
    4. test_check_anchor_existence_stale_commit_fails
    5. test_check_overlay_sanity_dirty_git_fails
    6. test_check_overlay_sanity_unwritable_path_fails
    7. test_risk_score_extreme_single_breach_rejects
    8. test_risk_score_cumulative_low_tier_rejects
    9. test_risk_score_below_threshold_accepts
    10. test_threshold_uses_z_1_96_and_stdev
    11. test_moving_avg_falls_back_to_anchor_on_first_run
    12. test_infra_fail_skipped_in_pass_rate
    13. test_cache_hit_short_circuits_subprocess
    14. test_cache_miss_writes_result_only_on_accept
    15. test_fs_boundary_cross_fs_uses_copy2_fallback
    16. test_restore_overlay_called_on_subprocess_error
  </behavior>
  <action>
    Create `tests/benchmarks/test_benchmark_gate.py` using the Write tool. The file is ~400-500 lines because of helper factories + 14+ tests. Key skeleton (executor expands fully):

    ```python
    """Unit tests for evolution/benchmarks/benchmark_gate.py.

    All subprocess calls are mocked — both:
      (a) the git status / git rev-parse calls inside _check_overlay_sanity
          and _check_anchor_existence (patch
          evolution.benchmarks.benchmark_gate.subprocess.run)
      (b) the TBLiteRunner.run subprocess wrapper (patch.object on the
          gate.runner attribute)
    """

    import json
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    import pytest

    from evolution.core.config import EvolutionConfig
    from evolution.benchmarks.tblite_runner import TBLiteRunResult


    # ── Helpers ──────────────────────────────────────────────────────────────

    class _FakeSection:
        def __init__(self, section_id, text="orig", line_range=(1, 1),
                     source_path=Path("/tmp/pb.py")):
            self.section_id = section_id
            self.text = text
            self.line_range = line_range
            self.source_path = source_path


    def _make_anchor(easy=0.85, medium=0.70, hard=0.50, extreme=0.30, stdev=0.02,
                     hermes_commit="def456", revision_hash="abc123"):
        return {
            "anchor_per_tier": {
                "easy":    {"mean": easy,    "stdev": stdev, "n": 3, "scores": [easy]*3},
                "medium":  {"mean": medium,  "stdev": stdev, "n": 3, "scores": [medium]*3},
                "hard":    {"mean": hard,    "stdev": stdev, "n": 3, "scores": [hard]*3},
                "extreme": {"mean": extreme, "stdev": stdev, "n": 3, "scores": [extreme]*3},
            },
            "dataset_revision_hash": revision_hash,
            "hermes_agent_commit": hermes_commit,
            "stratified_subset_seed": 42,
            "tblite_estimated_cost_per_task_usd": 0.4,
            "calibration_timestamp": "2026-05-19T00:00:00Z",
            "calibration_model": "test/model",
            "tblite_runner_version": "1.0",
        }


    def _make_subset(tasks=None):
        return {
            "seed": 42,
            "per_tier_counts": {"easy": 1, "medium": 1, "hard": 1, "extreme": 1},
            "task_filter": tasks or ["t-easy", "t-medium", "t-hard", "t-extreme"],
            "source": "NousResearch/openthoughts-tblite",
            "generated_timestamp": "2026-05-19T00:00:00Z",
        }


    def _make_config(hermes_path: Path):
        config = EvolutionConfig.__new__(EvolutionConfig)
        config.hermes_agent_path = hermes_path
        config.benchmark_max_cost_usd = 50.0
        config.tblite_estimated_cost_per_task_usd = 0.4
        config.benchmark_runs = 3
        config.benchmark_heartbeat_seconds = 60
        return config


    def _make_gate(tmp_path, *, anchor=None, subset=None, moving_avg_history=None,
                   reject_threshold=4.0, runs=3):
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
        hermes = tmp_path / "hermes-agent"
        (hermes / "agent").mkdir(parents=True, exist_ok=True)
        (hermes / "agent" / "prompt_builder.py").write_text(
            "MEMORY_GUIDANCE = (\n    \"baseline\"\n)\n"
        )
        config = _make_config(hermes)
        return TBLiteBenchmarkGate(
            config,
            anchor=anchor or _make_anchor(),
            stratified_subset=subset or _make_subset(),
            moving_avg_history=moving_avg_history,
            reject_threshold=reject_threshold,
            runs=runs,
        )


    def _fake_run_result(per_tier_passed: dict[str, list[bool]], *, runtime=1.0):
        per_task = []
        for tier, results in per_tier_passed.items():
            for i, passed in enumerate(results):
                per_task.append({
                    "task_name": f"{tier}-{i}",
                    "category": tier,
                    "passed": passed,
                    "infra_fail": False,
                })
        return TBLiteRunResult(
            per_task=per_task,
            subprocess_runtime_seconds=runtime,
            hang_count=0,
            cost_breakdown={"modal_compute_usd": 1.0},
            samples_jsonl_path=Path("/tmp/fake_samples.jsonl"),
            exit_code=0,
            status="ok",
            jsonl_skipped_lines=0,
            stderr_tail=[],
        )


    # ── Tests ───────────────────────────────────────────────────────────────

    class TestTBLiteBenchmarkGate:

        def test_constructor_validates_anchor_top_level_keys(self, tmp_path):
            from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
            config = _make_config(tmp_path)
            bad_anchor = _make_anchor()
            bad_anchor.pop("dataset_revision_hash")
            with pytest.raises(ValueError, match="dataset_revision_hash"):
                TBLiteBenchmarkGate(config, bad_anchor, _make_subset())

        def test_constructor_validates_anchor_per_tier_tiers(self, tmp_path):
            from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
            config = _make_config(tmp_path)
            bad_anchor = _make_anchor()
            bad_anchor["anchor_per_tier"].pop("extreme")
            with pytest.raises(ValueError, match="extreme"):
                TBLiteBenchmarkGate(config, bad_anchor, _make_subset())

        def test_constructor_validates_stratified_subset_task_filter(self, tmp_path):
            from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
            config = _make_config(tmp_path)
            with pytest.raises(ValueError, match="task_filter"):
                TBLiteBenchmarkGate(
                    config, _make_anchor(), {"seed": 1, "per_tier_counts": {}},
                )

        def test_check_anchor_existence_stale_commit_fails(self, tmp_path):
            from evolution.benchmarks import benchmark_gate as mod
            gate = _make_gate(tmp_path, anchor=_make_anchor(hermes_commit="STALE111"))
            # Mock git rev-parse to return a DIFFERENT commit.
            with patch.object(mod, "subprocess") as mock_subp:
                mock_subp.run.return_value = MagicMock(stdout="CURRENT222\n")
                mock_subp.TimeoutExpired = Exception
                mock_subp.CalledProcessError = Exception
                with pytest.raises(SystemExit) as ei:
                    gate._check_anchor_existence()
                assert ei.value.code == 1

        def test_check_overlay_sanity_dirty_git_fails(self, tmp_path):
            from evolution.benchmarks import benchmark_gate as mod
            gate = _make_gate(tmp_path)
            with patch.object(mod, "subprocess") as mock_subp:
                mock_subp.run.return_value = MagicMock(stdout=" M agent/prompt_builder.py\n")
                mock_subp.TimeoutExpired = Exception
                with pytest.raises(SystemExit) as ei:
                    gate._check_overlay_sanity()
                assert ei.value.code == 1

        def test_check_overlay_sanity_unwritable_path_fails(self, tmp_path, monkeypatch):
            gate = _make_gate(tmp_path)
            # Force os.access to return False for prompt_builder.py's dir.
            real_access = __import__("os").access
            target_parent = gate._target_path.parent
            def fake_access(p, mode):
                if Path(p) == target_parent:
                    return False
                return real_access(p, mode)
            monkeypatch.setattr("os.access", fake_access)
            with pytest.raises(SystemExit) as ei:
                gate._check_overlay_sanity()
            assert ei.value.code == 1

        def test_risk_score_extreme_single_breach_rejects(self, tmp_path):
            gate = _make_gate(tmp_path)
            per_tier_report = {
                "easy":    {"breach": False},
                "medium":  {"breach": False},
                "hard":    {"breach": False},
                "extreme": {"breach": True},
            }
            risk = gate._compute_risk_score(per_tier_report)
            assert risk == 4.0, f"single extreme breach must give 4.0, got {risk}"
            assert risk >= gate.reject_threshold

        def test_risk_score_cumulative_low_tier_rejects(self, tmp_path):
            gate = _make_gate(tmp_path)
            per_tier_report = {
                "easy":    {"breach": True},
                "medium":  {"breach": True},
                "hard":    {"breach": True},
                "extreme": {"breach": False},
            }
            risk = gate._compute_risk_score(per_tier_report)
            assert risk == pytest.approx(4.5), f"cumulative breach must be 4.5, got {risk}"
            assert risk >= gate.reject_threshold

        def test_risk_score_below_threshold_accepts(self, tmp_path):
            gate = _make_gate(tmp_path)
            per_tier_report = {
                "easy":    {"breach": True},
                "medium":  {"breach": True},
                "hard":    {"breach": False},
                "extreme": {"breach": False},
            }
            risk = gate._compute_risk_score(per_tier_report)
            assert risk == pytest.approx(2.5), f"easy+medium breach must be 2.5, got {risk}"
            assert risk < gate.reject_threshold

        def test_threshold_uses_z_1_96_and_stdev(self, tmp_path):
            gate = _make_gate(tmp_path, anchor=_make_anchor(easy=0.85, stdev=0.02))
            # 3-run identical -> stdev=0; vary to get stdev=0.01.
            per_run = [
                {"easy": 0.85, "medium": 0.70, "hard": 0.50, "extreme": 0.30},
                {"easy": 0.86, "medium": 0.70, "hard": 0.50, "extreme": 0.30},
                {"easy": 0.84, "medium": 0.70, "hard": 0.50, "extreme": 0.30},
            ]
            per_tier = gate._aggregate_per_tier(per_run)
            # statistics.stdev([0.85, 0.86, 0.84]) ≈ 0.01
            expected_threshold = 0.85 - 1.96 * per_tier["easy"]["stdev"]
            assert abs(per_tier["easy"]["threshold"] - round(expected_threshold, 4)) < 1e-4, \
                f"threshold wrong: {per_tier['easy']['threshold']} expected {expected_threshold}"

        def test_moving_avg_falls_back_to_anchor_on_first_run(self, tmp_path):
            gate = _make_gate(tmp_path, anchor=_make_anchor(easy=0.85),
                              moving_avg_history=[])
            ma = gate._moving_avg_per_tier()
            assert ma["easy"] == 0.85
            assert ma["extreme"] == 0.30

        def test_infra_fail_skipped_in_pass_rate(self, tmp_path):
            gate = _make_gate(tmp_path)
            result = TBLiteRunResult(per_task=[
                {"task_name": "a", "category": "easy", "passed": True, "infra_fail": False},
                {"task_name": "b", "category": "easy", "passed": False, "infra_fail": True},
                {"task_name": "c", "category": "easy", "passed": True, "infra_fail": False},
            ])
            rate = gate._one_run_per_tier_pass_rate(result)
            # Without infra_fail: 2 valid (a passed, c passed) -> 1.0
            assert rate["easy"] == 1.0, f"infra_fail not excluded: {rate['easy']}"

        def test_cache_hit_short_circuits_subprocess(self, tmp_path):
            from evolution.benchmarks import benchmark_gate as mod
            gate = _make_gate(tmp_path)
            # Pre-write a cache entry.
            sections = [_FakeSection("memory_guidance", "evolved")]
            cache_dir = tmp_path / "cache"
            from evolution.benchmarks.tblite_runner import compute_artifact_hash, TBLITE_RUNNER_VERSION
            key = compute_artifact_hash(sections, gate.anchor["dataset_revision_hash"],
                                         gate.anchor["stratified_subset_seed"], TBLITE_RUNNER_VERSION)
            (cache_dir / key).mkdir(parents=True)
            cached_report = {
                "decision": "accept",
                "risk_score": 0.0,
                "per_tier": {"easy": {"mean": 0.85, "breach": False}},
            }
            (cache_dir / key / "result.json").write_text(json.dumps(cached_report))

            # Mock runner — must NOT be called.
            mock_runner = MagicMock()
            gate.runner = mock_runner

            report = gate.check(sections, cache_dir=cache_dir, use_cache=True)
            assert report["decision"] == "accept"
            assert report["cache_hit"] is True
            assert not mock_runner.run.called, "cache hit must NOT invoke runner.run"

        def test_cache_miss_writes_result_only_on_accept(self, tmp_path):
            from evolution.benchmarks import benchmark_gate as mod
            gate = _make_gate(tmp_path, runs=1)
            # No pre-existing cache. Mock pre-flight + runner.
            cache_dir = tmp_path / "cache"
            with patch.object(mod, "subprocess") as mock_subp, \
                 patch.object(gate.runner, "run") as mock_run, \
                 patch.object(gate, "_check_overlay_sanity"), \
                 patch.object(gate, "_check_anchor_existence"), \
                 patch.object(gate, "_run_overlay", return_value=(tmp_path / "snap", tmp_path / "ovl")), \
                 patch.object(gate, "_restore_overlay"):
                mock_subp.TimeoutExpired = Exception
                # All 4 tiers pass -> no breach -> accept.
                mock_run.return_value = _fake_run_result({
                    "easy":    [True] * 4,
                    "medium":  [True] * 4,
                    "hard":    [True] * 4,
                    "extreme": [True] * 4,
                })
                sections = [_FakeSection("memory_guidance", "evolved")]
                report = gate.check(sections, cache_dir=cache_dir, use_cache=True)
            assert report["decision"] == "accept"
            from evolution.benchmarks.tblite_runner import compute_artifact_hash, TBLITE_RUNNER_VERSION
            key = compute_artifact_hash(sections, gate.anchor["dataset_revision_hash"],
                                         gate.anchor["stratified_subset_seed"], TBLITE_RUNNER_VERSION)
            assert (cache_dir / key / "result.json").exists(), "accept path must write cache"

        def test_fs_boundary_cross_fs_uses_copy2_fallback(self, tmp_path, monkeypatch):
            """When st_dev differs, _run_overlay falls back to shutil.copy2 instead of os.replace."""
            gate = _make_gate(tmp_path)
            # Force stat().st_dev to differ between target and overlay dirs.
            real_stat = Path.stat
            def fake_stat(self, *args, **kwargs):
                s = real_stat(self, *args, **kwargs)
                # Return a new namedtuple-like with mutated st_dev for tmp dirs only.
                import os as _os
                class _S:
                    def __init__(self, base, dev): self._b = base; self.st_dev = dev
                    def __getattr__(self, name): return getattr(self._b, name)
                # ~/.hermes/tmp gets dev=999; everything else gets its real dev.
                if str(self).startswith(str(Path.home() / ".hermes")):
                    return _S(s, 999)
                return _S(s, 1)
            monkeypatch.setattr(Path, "stat", fake_stat)

            sections = [_FakeSection("memory_guidance", "evolved", (1, 3),
                                      gate._target_path)]
            with patch("evolution.benchmarks.benchmark_gate.shutil.copy2") as mock_copy:
                with patch("evolution.benchmarks.benchmark_gate.os.replace") as mock_replace:
                    gate._run_overlay(sections)
                    # Snapshot (always copy2) + cross-fs replace fallback (copy2)
                    # = at least 2 copy2 calls; os.replace NOT called for the
                    # target swap.
                    assert mock_copy.call_count >= 2, \
                        f"copy2 fallback not taken: {mock_copy.call_count}"
                    # os.replace should NOT replace the target file (cross-fs branch).
                    target_replace_calls = [
                        c for c in mock_replace.call_args_list
                        if str(c.args[1]) == str(gate._target_path)
                    ]
                    assert len(target_replace_calls) == 0, \
                        f"cross-fs path must NOT call os.replace on target: {target_replace_calls}"

        def test_restore_overlay_called_on_subprocess_error(self, tmp_path):
            """try/finally guarantee: even when runner.run raises, restore runs."""
            from evolution.benchmarks import benchmark_gate as mod
            gate = _make_gate(tmp_path, runs=1)
            cache_dir = tmp_path / "cache"
            sections = [_FakeSection("memory_guidance", "evolved")]
            snap = tmp_path / "snapshot"
            with patch.object(mod, "subprocess"), \
                 patch.object(gate, "_check_overlay_sanity"), \
                 patch.object(gate, "_check_anchor_existence"), \
                 patch.object(gate, "_run_overlay", return_value=(snap, tmp_path / "ovl")), \
                 patch.object(gate, "_restore_overlay") as mock_restore, \
                 patch.object(gate.runner, "run", side_effect=RuntimeError("boom")):
                with pytest.raises(RuntimeError, match="boom"):
                    gate.check(sections, cache_dir=cache_dir, use_cache=True)
            mock_restore.assert_called_once_with(snap)
    ```

    After writing, run `.venv/bin/pytest tests/benchmarks/test_benchmark_gate.py -v` and confirm all 14+ tests pass.

    Implements: PATTERNS §File 13 (test scaffold, expanded from 12 to 16 to cover all 5 deviation points from §File 3).
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/benchmarks/test_benchmark_gate.py -v --tb=short 2>&1 | tail -50 && .venv/bin/pytest tests/benchmarks/test_benchmark_gate.py -q 2>&1 | tail -3 | grep -E '[0-9]+ passed' || (echo "FAIL: tests/benchmarks/test_benchmark_gate.py did not all pass"; exit 1) && grep -c 'def test_' tests/benchmarks/test_benchmark_gate.py | awk '{ if ($1 < 14) { print "FAIL: only " $1 " tests, need >= 14"; exit 1 } else { print "OK: " $1 " tests" } }' && grep -c 'patch.object(gate, "runner")\|patch.object(gate.runner' tests/benchmarks/test_benchmark_gate.py | awk '{ if ($1 < 1) { print "FAIL: TBLiteRunner not mocked"; exit 1 } else { print "OK: runner mocked" } }' && grep -c 'pytest.raises(SystemExit)' tests/benchmarks/test_benchmark_gate.py | awk '{ if ($1 < 2) { print "FAIL: D-10 + D-14 must each have a SystemExit test"; exit 1 } else { print "OK: " $1 " SystemExit tests" } }'</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/benchmarks/test_benchmark_gate.py -v` exits 0 with all 14+ tests passing.
    - `grep -c 'def test_' tests/benchmarks/test_benchmark_gate.py` >= 14.
    - At least 2 tests use `pytest.raises(SystemExit)` (D-10 + D-14 hard fails).
    - At least 1 test patches the runner attribute (`patch.object(gate, "runner")` or `patch.object(gate.runner, "run")`).
    - `test_restore_overlay_called_on_subprocess_error` confirms `_restore_overlay` runs even after runner.run raises.
    - `test_cache_hit_short_circuits_subprocess` confirms runner is never called on cache hit.
  </acceptance_criteria>
  <done>
    - 14+ unit tests pass
    - All subprocess calls (git + TBLite) mocked
    - Risk_Score formula verified for all 3 algebraic cases (extreme single, cumulative low-tier, below-threshold)
    - Threshold formula `max(anchor, ma) - 1.96 * stdev` verified to 1e-4 tolerance
    - Cache hit/miss + accept/reject matrix covered
    - fs-boundary fallback path exercised
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| anchor JSON file → TBLiteBenchmarkGate constructor | Git-tracked artifact; trusted at the commit-review level. Constructor validates schema and raises ValueError on missing keys. Runtime mutation of in-memory dict is not protected (defense-in-depth at the IO layer). |
| stratified_subset JSON → task_filter for TBLiteRunner | Git-tracked; same trust model as anchor. `TBLiteRunner._validate_task_filter` (Plan 02) re-validates each task name against the strict whitelist, so even a poisoned subset cannot inject shell metachars. |
| hermes_agent_path/agent/prompt_builder.py → Virtual Prompt Overlay target | UNTRUSTED at IO level: user may have local edits not yet committed. `_check_overlay_sanity` uses `git status --porcelain` to block runs against a dirty tree (CONCERNS §M6 mitigation). Snapshot + try/finally restore is the transactional rollback. |
| evolved_sections list[PromptSection] → write_back_section(dest=overlay_path) | Trusted (output of GEPA + Phase 18 drift gate). Worst case: malformed text breaks Python syntax of overlay file, TBLite subprocess fails, gate rejects. No code injection because write_back_section uses _escape_str (prompt_loader.py:266-274) for string contents. |
| cache_dir/<artifact_hash>/result.json → cached report dict | UNTRUSTED at IO level: an attacker with filesystem write access could plant a fake "accept" result. Mitigation: cache key includes dataset_revision_hash (which Plan 04 fetches from HuggingFace) and TBLITE_RUNNER_VERSION; tampering is detectable via re-running with --no-benchmark-cache. |
| git status / git rev-parse subprocess → Pre-flight branch decisions | Trusted: git is the developer's local tool. `subprocess.run` with list args + cwd= + timeout=10 prevents argument injection. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-20-11 | T (Tampering) | hermes-agent prompt_builder.py during Overlay | mitigate | snapshot to `~/.hermes/tmp/benchmark_<ts>/prompt_builder.py.original` BEFORE replace. `try/finally` guarantees restore — verified by `test_restore_overlay_called_on_subprocess_error`. Pre-flight `git status --porcelain` blocks runs against dirty trees. |
| T-20-12 | E (Elevation of privilege) | git status --porcelain misses git stash content | accept | `_check_overlay_sanity` currently does NOT check `git stash list`. User MUST be aware that stashed changes are invisible — documented in Plan 04 CLI help text and runbook. Adding stash check is a Plan 06+ follow-up (out of scope this wave). |
| T-20-13 | T (Tampering) | anchor JSON corruption | mitigate | Schema validation in constructor (top-level keys + all 4 tiers + per-tier inner keys). Plan 04 writes anchor with `sort_keys=True` and includes `calibration_timestamp` + `hermes_agent_commit` + `dataset_revision_hash` so diffs surface manipulation. `_check_anchor_existence` re-verifies commit match at every gate run. |
| T-20-14 | S (Spoofing) | cache_dir hit short-circuit bypasses Pre-flight | mitigate | Cache key includes `dataset_revision_hash` + `TBLITE_RUNNER_VERSION` so a stale or fake cache entry from a different dataset / runner version is invalidated. Cache write happens AFTER successful gate (`decision=="accept"`) — rejected runs are NOT cached, so retries with the same evolved sections re-execute deterministically. |
| T-20-15 | T (Tampering) | os.replace cross-fs returns False (fallback to copy2) | accept | shutil.copy2 is NOT atomic but the window is sub-millisecond (single-file write inside same parent dir lock). For the worst-case crash mid-copy, snapshot is still on disk in `~/.hermes/tmp/` — manual recovery is trivial. Documented in `_run_overlay` docstring. |
| T-20-16 | D (Denial of Service) | _check_overlay_sanity git subprocess hangs | mitigate | `subprocess.run(timeout=10)` + `TimeoutExpired` handler → `sys.exit(1)`. No infinite waits. |
| T-20-17 | I (Information disclosure) | stderr_tails persisted in report (Plan 06 metrics.json) | mitigate | Plan 02 caps stderr_tail at 20 lines per run. Plan 06 will apply Phase 14 SECRET_PATTERNS filter before writing to disk. This plan (03) just collects them. |
</threat_model>

<verification>
- `from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate, TIER_WEIGHTS, REJECT_THRESHOLD, CONFIDENCE_Z, TIERS` succeeds.
- `pytest tests/prompts/ -q` exits 0 (no regression after prompt_loader.py edit).
- `pytest tests/benchmarks/test_benchmark_gate.py -v` exits 0 with all 14+ tests passing.
- `pytest tests/ --collect-only` succeeds (no global discovery break).
- `grep -c 'os\.replace' evolution/benchmarks/benchmark_gate.py` >= 2.
- `grep -c 'shutil\.copy2' evolution/benchmarks/benchmark_gate.py` >= 3.
- `grep -c 'finally:' evolution/benchmarks/benchmark_gate.py` >= 1.
- `grep -c 'sys\.exit(1)' evolution/benchmarks/benchmark_gate.py` >= 2.
- `grep -c 'compute_artifact_hash' evolution/benchmarks/benchmark_gate.py` >= 1.
</verification>

<success_criteria>
- ROADMAP SC #1 + SC #2 covered: tier-weighted Risk_Score + 1.96σ band + reject_threshold configurable via constructor.
- D-01 + D-02 + D-03 covered: Adaptive Sliding Window threshold formula + tier-weighted Risk_Score + 3-run aggregation all implemented and unit-tested.
- D-04 covered: `check()` returns dict matching tblite_report.json schema (decision/risk_score/reject_threshold/tier_weights/per_tier/samples_jsonl_path/...).
- D-09 covered: Virtual Prompt Overlay snapshot + atomic replace + ALWAYS-restore.
- D-10 + D-14 covered: Pre-flight overlay sanity (git clean + writable) + anchor existence (commit match).
- D-15 covered: Content-addressed cache hit short-circuits subprocess; cache write only on accept; cache key uses dataset_revision_hash + TBLITE_RUNNER_VERSION.
- Risk Anchor 1 covered: fs-boundary detection + shutil.copy2 fallback unit-tested.
- Risk Anchor 3 covered: infra_fail rows excluded from tier pass-rate denominators.
- T-20-11..T-20-17 mitigated.
</success_criteria>

<output>
After completion, create `.planning/phases/20-benchmark-gated-validation/20-03-benchmark-gate-SUMMARY.md` covering:
- Line counts: benchmark_gate.py ~400-450; prompt_loader.py +5-10 lines; test_benchmark_gate.py ~400-500.
- Grep evidence: os.replace count, shutil.copy2 count, try/finally count, sys.exit(1) count.
- pytest summary line for tests/benchmarks/test_benchmark_gate.py (expect 14+ passed).
- Confirmation that tests/prompts/ baseline unchanged (no regression from write_back_section edit).
- Confirmation that Plans 02 + 03 produce compatible interfaces (`import evolution.benchmarks.benchmark_gate` succeeds when both files present).
</output>
</content>
</invoke>

## Revision Log

- 2026-05-19 (W-5): `_check_anchor_existence` now actually compares `anchor.dataset_revision_hash` against a live HuggingFace probe (lazy-imported `_hf_dataset_revision` from Plan 04). Mismatch emits a yellow Rich warning and continues (D-14 warn-only contract). Probe is silent on fail-open paths (`unknown_v*` anchor OR HF unreachable) to preserve offline workflows.
- 2026-05-19 (I-1): Removed the post-replace `shutil.copy2(self._target_path, overlay_path)` re-materialize step from `_run_overlay` — it was vestigial and only served to keep a debugging artifact that snapshot_path already covers. Verify gate + acceptance criterion for `shutil.copy2` count lowered from ≥3 to ≥2 (snapshot + cross-fs fallback only).
