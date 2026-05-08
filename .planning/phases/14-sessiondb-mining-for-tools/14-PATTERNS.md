# Phase 14: SessionDB Mining for Tools — Pattern Map

**Mapped:** 2026-05-08
**Files analyzed:** 19 (2 NEW source + 4 MODIFIED source + 9 NEW test + 7 NEW fixture, but fixtures share one class of analog so collapsed in the per-file table)
**Analogs found:** 19 / 19 (100%; every new artifact has a 1:1 or 1:N close analog already in the repo)

## File Classification

| New File or Modified | Role | Data Flow | Closest Analog | Match Quality |
|----------------------|------|-----------|----------------|---------------|
| `evolution/tools/session_miner.py` (NEW) | service | batch transform (session JSON → ToolSelectionExample[]) | `evolution/tools/tool_dataset.py::ToolDatasetBuilder` (init+inner Signature+generate) AND `evolution/tools/tool_constraints.py::ParamConsistencyChecker` (per-candidate LLM judge inner Signature) | exact (composite role match) |
| `evolution/tools/mine_tool_sessions.py` (NEW) | controller (CLI entry) | request-response (CLI args → orchestration → metrics.json) | `evolution/tools/evolve_tool_descriptions.py` Click command + module-level `console = Console()` + metrics.json + Rich Table summary; FAILED_/ABORTED_ dir convention from `evolve_tool_params.py` | exact |
| `evolution/tools/tool_dataset.py` (MODIFIED, D-02) | model (dataclass) | CRUD (dataclass field add) | self — `ToolSelectionExample.from_dict` already filters unknown keys (line 71) | exact (in-place extension) |
| `evolution/core/external_importers.py` (MODIFIED, D-15) | utility (regex + entropy) | transform (str → bool) | self — `SECRET_PATTERNS` (lines 45-70) + `_contains_secret` (78-80) extended in place | exact (in-place extension) |
| `evolution/tools/evolve_tool_descriptions.py` (MODIFIED, D-09) | controller (CLI) | request-response (add `--session-source` flag + load+union branch) | self — existing Click signature (lines 400-417) | exact (in-place extension) |
| `evolution/tools/evolve_tool_params.py` (MODIFIED, D-09) | controller (CLI) | request-response (add `--session-source` flag + load+union branch) | self — existing Click signature (lines 509-540) | exact (in-place extension) |
| `tests/tools/test_session_signal_extract.py` (NEW) | test | event-driven (fixture session JSON → extractor calls) | `tests/conftest.py::mock_lm_with_usage` (lines 7-38) for A signal LLM 二判 mock | role-match (existing test pattern but new file) |
| `tests/tools/test_session_judge.py` (NEW) | test | request-response (mock LM in, verdict out) | `tests/conftest.py::mock_lm_with_usage` (lines 7-38) — direct reuse | exact |
| `tests/tools/test_session_split.py` (NEW) | test | transform (str → split bucket) | no direct analog — pure unit test of new helper functions | partial (no analog needed) |
| `tests/tools/test_session_miner.py` (NEW) | test | batch transform (end-to-end mine() with mock LM) | `tests/conftest.py::mock_lm_with_usage` + Phase 13 integration tests (referenced via RESEARCH lines 762-784) | role-match |
| `tests/tools/test_secret_patterns_v2.py` (NEW) | test | transform (str → bool) | existing `tests/test_external_importers.py` SECRET_PATTERN tests (subset reuse for v1 regression — RESEARCH line 504) | role-match |
| `tests/tools/test_jsonl_skip_bad.py` (NEW) | test | streaming I/O (file → list[dict]) | no direct analog (pure helper test) | partial |
| `tests/tools/test_surface_drift.py` (NEW) | test | transform (tool name set → drop/keep) | partial — list filter pattern | partial |
| `tests/tools/test_mine_cli.py` (NEW) | test | request-response (CliRunner) | existing CLI tests for `evolve_tool_*` use `click.testing.CliRunner` | role-match |
| `tests/tools/test_evolve_with_session_source.py` (NEW) | test (integration) | batch transform (synthetic + session → union dataset → mock GEPA) | existing `tests/tools/` evolve_tool_* integration tests | role-match |
| `tests/fixtures/sessions/{error_retry_b,user_correction_a,oracle_disagreement_c,malformed_msg,multi_signal,surface_drift,secret_in_user_msg}.json` (7 NEW) | fixture | data | real `~/.hermes/sessions/session_*.json` schema (RESEARCH §Pitfall 1 实测 sample, lines 348-378) | exact |

---

## Pattern Assignments

### `evolution/tools/session_miner.py` (NEW — service, batch transform)

**Composite analog:** `tool_dataset.py::ToolDatasetBuilder` (skeleton) + `tool_constraints.py::ParamConsistencyChecker` (per-candidate LLM judge).

#### Imports pattern (replicate `tool_dataset.py:13-26`)

```python
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import dspy
from rich.console import Console

from evolution.core.config import EvolutionConfig

console = Console()
```

#### Class skeleton + inner Signature + ChainOfThought (replicate `tool_dataset.py:154-211`)

```python
class ToolDatasetBuilder:
    """Two-step synthetic dataset builder for tool selection evaluation.
    ...
    """

    class AnalyzeToolSimilarity(dspy.Signature):
        """Identify pairs of tools with overlapping functionality.
        ..."""
        tool_summaries: str = dspy.InputField(desc="All tools as '- name: description' list")
        confuser_pairs: str = dspy.OutputField(
            desc="JSON array of {\"tools\": [...], \"overlap\": ...}"
        )

    class GenerateToolTasks(dspy.Signature):
        """Generate realistic user tasks that require a specific tool. ..."""
        tool_name: str = dspy.InputField(desc="Name of the target tool")
        ...

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.similarity_cot = dspy.ChainOfThought(self.AnalyzeToolSimilarity)
        self.tool_tasks_cot = dspy.ChainOfThought(self.GenerateToolTasks)
```

**What to replicate:** identical `class SessionToolMiner` shape — accepts `EvolutionConfig`, holds one `dspy.ChainOfThought(self.ConfirmMisselection)` instance (and a second one for user_correction LLM 二判 if needed), inner Signature classes for *all* DSPy contracts (mining-time judge — **not** in `tool_constraints.py` since it's not a deploy gate; RESEARCH line 322).

**What to diverge:**
- Extractor methods are **`_extract_error_retry` / `_extract_user_correction` / `_extract_oracle_disagreement`** (private, snake_case + underscore prefix per CLAUDE.md naming).
- `mine(sessions_dir, current_tools)` returns `list[ToolSelectionExample]` not `ToolSelectionDataset` — split happens after dedup union (D-13 hash bucket).
- No `random.shuffle` (deterministic hash splitting, RESEARCH Pattern 2).

#### Per-candidate LLM judge call site (replicate `tool_constraints.py:222-281`, fail-closed pattern)

```python
# Source: evolution/tools/tool_constraints.py:222-262 (excerpt of ParamConsistencyChecker.check)
def check(
    self,
    tool_name: str,
    frozen_desc: str,
    param_descs: dict,
) -> ConstraintResult:
    import json as _json
    lm = dspy.LM(self.config.eval_model, **self.config.get_lm_kwargs())
    params_json = _json.dumps(param_descs or {}, ensure_ascii=False, sort_keys=True)
    try:
        with dspy.context(lm=lm):
            result = self.checker(
                tool_name=tool_name,
                frozen_tool_description=frozen_desc or "",
                evolved_param_descriptions=params_json,
            )
    except Exception as e:
        # Conservative: any LM / parsing failure rejects the candidate.
        return ConstraintResult(
            passed=False,
            constraint_name="param_consistency",
            message=f"Consistency check failed for '{tool_name}' (LLM error)",
            details=str(e),
        )

    # Polarity inversion: is_consistent True -> passed True.
    # _parse_bool returns False on anything ambiguous -> fails CLOSED.
    is_consistent = _parse_bool(getattr(result, "is_consistent", None))
```

**What to replicate (verbatim shape):**
1. Local `lm = dspy.LM(self.config.judge_model, **self.config.get_lm_kwargs())` — use **`config.judge_model`** not `eval_model` (D-07).
2. `with dspy.context(lm=lm):` block wrapping `self.judge(...)` call.
3. `try/except Exception` around the call → on any failure return `verdict="false_positive"` (drop candidate). RESEARCH lines 220-235 give the explicit `Verdict(label="false_positive", ...)` shape.
4. `getattr(result, "verdict", None)` + normalization to lowercase string + fallback to `"false_positive"` for unknown labels (M4 in CONCERNS).

**What to diverge:** return a local `Verdict` namedtuple/dataclass (not `ConstraintResult` — this is a mining decision, not a constraint gate).

#### `_parse_bool` reuse (replicate `tool_constraints.py:15-29`)

```python
def _parse_bool(value) -> bool:
    """Parse a boolean value from various LLM output formats.

    Conservative strategy: only explicit truthy values return True.
    Everything else (including unrecognized text) returns False.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "1")
```

**What to replicate:** **import** this helper from `tool_constraints` (do not re-implement); use it on any future bool OutputField that gets added to `ConfirmMisselection` (e.g. if `verdict` is replaced with `is_misselection: bool`).

#### Tool surface obtain (replicate `tool_loader.py:158-175`)

```python
def extract_tool_descriptions(file_path: Path) -> list[ToolDescription]:
    """Extract tool descriptions from a Python source file.

    Parses schema dict constants (e.g. MEMORY_SCHEMA = {...}) and list
    constants (e.g. BROWSER_TOOL_SCHEMAS = [...]) to extract tool names,
    descriptions, and parameter metadata.

    Args:
        file_path: Path to a Python source file in hermes-agent/tools/.

    Returns:
        List of ToolDescription instances. Empty list if file doesn't exist
        or contains no schema definitions.
    """
```

**What to replicate:** call sequence is `discover_tool_files(hermes_agent_path)` → for each `extract_tool_descriptions(p)` (per-file; loops at the CLI level — see how `evolve_tool_descriptions.py:25` imports it and walks). For Phase 14 the SessionToolMiner builds `current_tool_names: set[str]` from this output for the surface drift filter (D-17).

**What to diverge:** Phase 14 only needs `tool.name` (not `params` / `description`); convert immediately to `set[str]` after extraction.

#### Oracle (C signal) reuse (replicate `tool_module.py:162-184`)

```python
def forward(self, task_description: str) -> dspy.Prediction:
    """Select the best tool AND its parameters for a given task.

    Returns:
        dspy.Prediction with:
            - selected_tool (str)
            - selected_params (str, JSON-encoded dict; may be '{}')
    """
    available_tools = self._format_available_tools()
    result = self.selector(
        task_description=task_description,
        available_tools=available_tools,
    )
    ...
    return dspy.Prediction(
        selected_tool=result.selected_tool,
        selected_params=selected_params,
    )
```

**What to replicate:** `module(task_description=task)` → access `.selected_tool` for the oracle prediction; compare to `assistant.tool_calls[i].function.name` from session JSON (RESEARCH Pitfall 4).

**What to diverge:** wrap in `try/except Exception` (oracle baseline can raise on malformed task — fail-closed = skip candidate, do NOT mark misselection).

---

### `evolution/tools/mine_tool_sessions.py` (NEW — controller, request-response)

**Analog:** `evolution/tools/evolve_tool_descriptions.py` lines 1-31 (imports + console) + lines 400-417 (Click command).

#### Imports + module-level console (replicate `evolve_tool_descriptions.py:9-31`)

```python
import json
import sys
import time
import difflib
from pathlib import Path
from datetime import datetime
from typing import Optional

import click
import dspy
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.config import EvolutionConfig, get_hermes_agent_path
from evolution.core.constraints import ConstraintValidator
from evolution.tools.tool_loader import discover_tool_files, extract_tool_descriptions, ToolDescription
from evolution.tools.tool_module import ToolModule
from evolution.tools.tool_dataset import ToolDatasetBuilder, ToolSelectionDataset
from evolution.tools.tool_metric import tool_selection_metric, CrossToolRegressionChecker
from evolution.tools.tool_constraints import ToolFactualChecker

console = Console()
```

**What to replicate:** module-level `console = Console()` (CLAUDE.md convention); imports grouped stdlib → 3rd party → local; Rich Console + Panel + Table imported even if Panel unused at start (consistency).

**What to diverge:**
- Drop `ToolFactualChecker` / `CrossToolRegressionChecker` / `ConstraintValidator` imports (no constraint gate in mining).
- Add `from evolution.tools.session_miner import SessionToolMiner`.
- Add `from evolution.tools.tool_dataset import ToolSelectionExample` (write JSONL directly).

#### Click command shape (replicate `evolve_tool_descriptions.py:400-417`)

```python
@click.command()
@click.option("--iterations", default=10, help="Number of GEPA iterations")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "load"]),
              help="Source for evaluation dataset")
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo")
@click.option("--dry-run", is_flag=True, help="Validate setup without running optimization")
@click.option("--model", default=None, help="Override model for all LLM calls (e.g. openai/qwen-plus)")
@click.option("--api-base", default=None, help="Override API base URL (e.g. https://dashscope.aliyuncs.com/compatible-mode/v1)")
def main(iterations, eval_source, hermes_repo, dry_run, model, api_base):
    """Evolve hermes-agent tool descriptions using DSPy + GEPA optimization."""
    evolve(...)


if __name__ == "__main__":
    main()
```

**What to replicate (verbatim):** `--hermes-repo` / `--model` / `--api-base` / `--dry-run` flag names, defaults, and help text — identical to Phase 5 (CONTEXT D-07).

**What to diverge (Phase 14 new flags from CONTEXT D-07; replicate Click `is_flag` / `type=click.Path()` / `default=None` styling from existing flags):**
- `--sessions-dir` (default None → `Path.home() / ".hermes" / "sessions"`)
- `--output` (default None → `datasets/tools/sessions/<ts>/`)
- `--limit` (`type=int, default=0`)
- `--i-have-consent` (`is_flag=True`) — **REQUIRED** consent gate (D-16). When False, `click.echo(... err=True)` then `sys.exit(1)`.
- `--signals` (`default="error_retry,user_correction,oracle_disagreement"`)
- `--baseline-module` (`type=click.Path(), default=None`)
- `--judge-model` (`default=None`)
- `--misselection-multiplier` (`default=None`, parsed as `"key=int,..."`)

Drop `--iterations` and `--eval-source` (mining is not iterative GEPA).

#### Output dir + metrics.json convention (replicate `evolve_tool_descriptions.py:351-379`)

```python
# ── 11. Save results ─────────────────────────────────────────────────
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_dir = Path("output") / "tools" / timestamp
output_dir.mkdir(parents=True, exist_ok=True)

# Save evolved descriptions as JSON
evolved_data = [
    {"name": t.name, "description": t.description}
    for t in evolved_tools
]
(output_dir / "evolved_descriptions.json").write_text(
    json.dumps(evolved_data, indent=2)
)

# Save metrics
metrics = {
    "timestamp": timestamp,
    "iterations": iterations,
    "eval_model": config.eval_model,
    "baseline_score": baseline_score,
    "evolved_score": evolved_score,
    ...
    "elapsed_seconds": elapsed,
    "constraints_passed": True,
}
(output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
```

**What to replicate:** `datetime.now().strftime("%Y%m%d_%H%M%S")` timestamp; output dir `Path` / `mkdir(parents=True, exist_ok=True)`; `metrics.json` written via `(output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))`.

**What to diverge:**
- Output root is `datasets/tools/sessions/<ts>/` (not `output/tools/<ts>/`) — CONTEXT D-08.
- Files written: `train.jsonl`, `val.jsonl`, `holdout.jsonl`, `metrics.json`, `miner_log.jsonl` (no `evolved_descriptions.json`, no `diff.txt`).
- `metrics.json` schema (CONTEXT specifics lines 180-191):
  ```python
  metrics = {
      "timestamp": ...,
      "total_candidates_by_signal": {...},
      "judge_confirmed_by_signal": {...},
      "judge_false_positives_by_signal": {...},
      "surface_drift_dropped": int,
      "surface_drift_tools": [...],
      "final_examples_by_split": {"train": ..., "val": ..., "holdout": ...},
      "final_train_after_duplication": int,
      "multiplier_used": {...},
      "secret_filter_skipped": int,
      "jsonl_skipped_lines": int,
      # Phase 13 alignment for Phase 16 dashboard:
      "cost_usd_spent": 0.0,        # placeholder unless cost_tracker enabled
      "judge_calls": int,
      "judge_calls_by_signal": {...},
  }
  ```

#### Cost-tracker field naming (Phase 13 reference — `cost_tracker.py:54-67` + `evolve_tool_params.py:828-856`)

```python
# Source: evolution/core/cost_tracker.py:54-67
class CostBudgetExceeded(Exception):
    """Raised by CLI when CostTracker.exceeded() is True.
    ...
    """
    def __init__(self, spent_usd: float, max_usd: float):
        self.spent_usd = spent_usd
        self.max_usd = max_usd
        super().__init__(
            f"Cost budget exceeded: spent ${spent_usd:.4f} > cap ${max_usd:.4f}"
        )

# Source: evolution/tools/evolve_tool_params.py:830-840 — metrics.json field naming
metrics: dict[str, Any] = {
    "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
    "started_at": started_at_iso,
    ...
    "cost_usd_spent": float(round(final_spent_usd, 6)),
    "cost_usd_cap": float(config.max_cost_usd),
    ...
}
```

**What to replicate (NAMING ONLY, not behavior — Phase 14 does not strictly enforce a budget):**
- Field name `cost_usd_spent` (use `0.0` placeholder if no cost tracker run).
- Field name `judge_calls` (Phase 14 fills this from per-candidate counter).
- Field name `*_by_signal` style for dictionaries keyed by signal source.

**What to diverge:** **DO NOT** import `CostTracker` / `CostBudgetExceeded` — CONTEXT canonical_refs explicitly says cost cap is not enforced this phase (just align field names for Phase 16 dashboard).

#### FAILED_/ABORTED_ dir convention (replicate `evolve_tool_params.py:30-34` docstring + impl line 820)

```python
# Source: evolve_tool_params.py:30-34 (docstring contract)
# Failure branching:
#     - Constraint fail        → output/tools/FAILED_<ts>/
#     - Regression fail        → output/tools/FAILED_<ts>/
#     - V1 baseline fail       → output/tools/FAILED_<ts>/
#     - Cost cap exceeded      → output/tools/ABORTED_<ts>/
```

**What to replicate:** when `--i-have-consent` missing or sessions_dir empty or zero candidates → write any partial state (e.g. discovered candidate count, empty metrics.json) to `datasets/tools/sessions/FAILED_<ts>/` then `sys.exit(1)`. When `--limit` reached early or user Ctrl+C → `ABORTED_<ts>/`.

**What to diverge:** path root is `datasets/tools/sessions/` (not `output/tools/`).

#### Rich Table summary (replicate `evolve_tool_descriptions.py` Table import; example pattern from `tool_dataset.py:304-308`)

```python
console.print("[bold cyan]Step 1:[/] Analyzing tool similarity...")
sim_result = self.similarity_cot(tool_summaries=tool_summaries)
confuser_pairs = self._parse_json_array(sim_result.confuser_pairs)
console.print(f"  Found {len(confuser_pairs)} confuser pair(s)")
```

**What to replicate:** Rich markup colors (`[bold cyan]` step headers, `[yellow]⚠` warnings, `[bold green]` success); `console.print(f"  ...")` 2-space indent for sub-step lines.

**What to diverge:** at end, build `rich.table.Table` with columns `Signal | Candidates | Confirmed | False Positives | Train Final` (one row per signal source) — RESEARCH §Pitfall 8 caps to top-10 surface-drift entries on screen but writes full dict to metrics.json.

---

### `evolution/tools/tool_dataset.py` (MODIFIED — model, CRUD)

**Analog:** self — extend the existing `ToolSelectionExample` dataclass (lines 32-71) in place.

#### Existing `ToolSelectionExample` shape (lines 32-71 — extend without breaking)

```python
@dataclass
class ToolSelectionExample:
    """A single tool selection evaluation example.
    ...
    """
    task_description: str
    correct_tool: str
    correct_params: dict = field(default_factory=dict)
    difficulty: str = "medium"  # easy, medium, hard
    confuser_tools: list[str] = field(default_factory=list)
    reason: str = ""
    source: str = "synthetic"

    def to_dict(self) -> dict:
        """Serialize all fields to a dict."""
        return {
            "task_description": self.task_description,
            "correct_tool": self.correct_tool,
            "correct_params": self.correct_params,
            "difficulty": self.difficulty,
            "confuser_tools": self.confuser_tools,
            "reason": self.reason,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolSelectionExample":
        """Deserialize from dict, ignoring unknown keys."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
```

**What to replicate (the surrounding shape stays identical):** `@dataclass` + `field(default_factory=...)` for mutable defaults; `to_dict` lists every field explicitly; `from_dict` filters via `cls.__dataclass_fields__` (line 71 — this **already** auto-handles new fields with default values for old JSONL).

**What to diverge / what to add (D-02):**
- Add field after `source`: `misselection_signals: list[str] = field(default_factory=list)`.
- Add to `to_dict`: `"misselection_signals": self.misselection_signals`.
- **Do NOT touch `from_dict`** — line 71 already filters unknown keys, so Phase 4 JSONL with no `misselection_signals` deserializes with `[]` default automatically.

#### Optional in-place enhancement to `ToolSelectionDataset.load` (D-18 minimal subset)

```python
# Source: tool_dataset.py:108-128 (current load)
@classmethod
def load(cls, path: Path) -> "ToolSelectionDataset":
    dataset = cls()
    for split_name in ["train", "val", "holdout"]:
        split_file = path / f"{split_name}.jsonl"
        if split_file.exists():
            examples = []
            with open(split_file) as f:
                for line in f:
                    if line.strip():
                        examples.append(ToolSelectionExample.from_dict(json.loads(line)))
            setattr(dataset, split_name, examples)
    return dataset
```

**What to replicate:** the existing per-line iteration with `if line.strip()` skip-blank pattern.

**What to diverge:** CONTEXT D-18 explicitly says **do NOT** modify `ToolSelectionDataset.load` itself — JSONL bad-line tolerance lives only in the new `_load_jsonl_skip_bad` helper used by session_miner output and `--session-source` load paths. **Touching `ToolSelectionDataset.load` here is out of scope and will be rejected.**

---

### `evolution/core/external_importers.py` (MODIFIED — utility, transform)

**Analog:** self — extend `SECRET_PATTERNS` (lines 45-70) and `_contains_secret` (78-80) in place.

#### Existing SECRET_PATTERNS (lines 45-70)

```python
SECRET_PATTERNS = re.compile(
    r'('
    r'sk-ant-api\S+'           # Anthropic API keys
    r'|sk-or-v1-\S+'          # OpenRouter API keys
    r'|sk-\S{20,}'            # Generic OpenAI-style keys (20+ chars after sk-)
    r'|ghp_\S+'               # GitHub personal access tokens
    r'|ghu_\S+'               # GitHub user tokens
    r'|xoxb-\S+'              # Slack bot tokens
    r'|xapp-\S+'              # Slack app tokens
    r'|ntn_\S+'               # Notion integration tokens
    r'|AKIA[0-9A-Z]{16}'      # AWS access key IDs
    r'|Bearer\s+\S{20,}'      # Bearer auth headers (20+ char tokens)
    r'|-----BEGIN\s+(RSA\s+)?PRIVATE\sKEY-----'  # PEM private keys
    r'|ANTHROPIC_API_KEY'      # Known env var names (exact match)
    r'|OPENAI_API_KEY'
    r'|OPENROUTER_API_KEY'
    r'|SLACK_BOT_TOKEN'
    r'|GITHUB_TOKEN'
    r'|AWS_SECRET_ACCESS_KEY'
    r'|DATABASE_URL'
    r'|\bpassword\s*[=:]\s*\S+' # password assignments
    r'|\bsecret\s*[=:]\s*\S+'   # secret assignments
    r'|\btoken\s*[=:]\s*\S{10,}' # token assignments with 10+ char values
    r')',
    re.IGNORECASE,
)


def _contains_secret(text: str) -> bool:
    """Check if text contains potential API keys or tokens."""
    return bool(SECRET_PATTERNS.search(text))
```

**What to replicate:** alternation-list within single `re.compile(r'(...|...|...)', re.IGNORECASE)` block; explicit `# comment` per alternative; `_contains_secret` returns `bool(SECRET_PATTERNS.search(text))`.

**What to diverge / add (D-15):**
- **Insert two new alternatives between current line 56 (`Bearer\s+\S{20,}`) and line 57 (`-----BEGIN`):**
  - `r'|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'  # JWT tokens`
  - `r'|(?:aws[_-]?(?:access|secret)|AKIA)[\s\S]{0,40}[A-Za-z0-9/+=]{32,}'  # AWS-secret proximity`
- **Add new helper function above `_contains_secret`:**
  ```python
  def _shannon_entropy(s: str) -> float:
      """Compute Shannon entropy in bits. Empty/single-char → 0.0."""
      if len(s) < 2:
          return 0.0
      from collections import Counter
      import math
      counts = Counter(s)
      n = len(s)
      return -sum((c / n) * math.log2(c / n) for c in counts.values())
  ```
- **Modify `_contains_secret` to add entropy branch (D-15):**
  ```python
  def _contains_secret(text: str) -> bool:
      """Check if text contains potential API keys or tokens.

      Layer 1 (pattern match) + entropy heuristic for ≥24-char base64-like
      tokens (Phase 14 D-15). Threshold 4.0 may be calibrated per RESEARCH A2.
      """
      if SECRET_PATTERNS.search(text):
          return True
      # High-entropy token heuristic — only on long base64-ish runs
      for tok in re.findall(r'[A-Za-z0-9_/+=-]{24,}', text):
          if _shannon_entropy(tok) > 4.0:
              return True
      return False
  ```

**Critical regression guard (RESEARCH Pitfall 6):** any change to `_contains_secret` MUST be tested against the existing v1 test suite (`tests/test_external_importers.py`) + new `tests/tools/test_secret_patterns_v2.py` low-entropy negative fixtures (CJK prose, MD5/SHA256 hex). Threshold 4.0 may need calibration to 4.2-4.5.

---

### `evolution/tools/evolve_tool_descriptions.py` (MODIFIED — controller; D-09 add `--session-source`)

**Analog:** self — append one Click option to the existing decorator stack (lines 400-407).

#### Existing decorator stack (lines 400-407)

```python
@click.command()
@click.option("--iterations", default=10, help="Number of GEPA iterations")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "load"]),
              help="Source for evaluation dataset")
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo")
@click.option("--dry-run", is_flag=True, help="Validate setup without running optimization")
@click.option("--model", default=None, help="Override model for all LLM calls (e.g. openai/qwen-plus)")
@click.option("--api-base", default=None, help="Override API base URL (e.g. https://dashscope.aliyuncs.com/compatible-mode/v1)")
def main(iterations, eval_source, hermes_repo, dry_run, model, api_base):
    """Evolve hermes-agent tool descriptions using DSPy + GEPA optimization."""
    evolve(
        iterations=iterations,
        eval_source=eval_source,
        hermes_repo=hermes_repo,
        dry_run=dry_run,
        model=model,
        api_base=api_base,
    )
```

**What to replicate:** add the new option as `@click.option("--session-source", default=None, type=click.Path(exists=True, file_okay=False, dir_okay=True), help="Directory containing train/val/holdout.jsonl from mine_tool_sessions; union with synthetic dataset")`.

**What to diverge (D-09 / D-14):**
- Thread `session_source` through `main` → `evolve(...)`.
- Inside `evolve`, after building synthetic dataset, if `session_source` is not None:
  1. `from evolution.tools.session_miner import _load_jsonl_skip_bad` (helper from session_miner module).
  2. For each split, call `_load_jsonl_skip_bad(Path(session_source) / f"{split}.jsonl")` → list of dicts → `[ToolSelectionExample.from_dict(d) for d in rows]`.
  3. Union per split using `dict[hash, ToolSelectionExample]`: synthetic enters first, session enters second (so session overrides on hash collision — RESEARCH Pitfall 10).
  4. **Do NOT** re-duplicate train (session_miner pre-duplicated; RESEARCH Pitfall 5).
- `metrics.json` (existing) gains a new field: `"session_source": str(path) or None` for traceability.

---

### `evolution/tools/evolve_tool_params.py` (MODIFIED — controller; D-09 add `--session-source`)

**Analog:** self — append one Click option to the existing decorator stack (lines 509-540).

#### Existing decorator stack (lines 509-540)

```python
@click.command()
@click.option("--iterations", default=10, type=int,
              help="GEPA iterations (affects max_metric_calls; overridden by --auto)")
@click.option("--eval-source", default="load",
              type=click.Choice(["synthetic", "load"]),
              help="Default load — reuse Phase 4 dataset (D-16)")
@click.option("--hermes-repo", default=None,
              help="Path to hermes-agent repo (overrides HERMES_AGENT_REPO env var)")
@click.option("--dry-run", is_flag=True,
              help="Show setup + discovered param count, no optimization")
@click.option("--model", default=None, help="Override all LLM model names")
@click.option("--api-base", default=None, help="Override API base URL")
@click.option("--tools", "tools", default=None,
              help="Comma-separated subset of tool names; empty = all")
@click.option("--max-cost-usd", default=None, type=float,
              help="USD cost cap (overrides EVOLUTION_MAX_COST_USD); default 20.0")
@click.option("--reflection-model", default=None,
              help="Separate model for GEPA reflection_lm; defaults to optimizer_model")
@click.option("--param-group-size", default=None, type=int,
              help="(NO-OP in Phase 13 — emits warning when set; ...)")
@click.option("--baseline-run", default=None,
              help="Path to a Phase 5 output dir with metrics.json; ...")
@click.option("--allow-miprov2-fallback", is_flag=True, ...)
@click.option("--component-selector", default="round_robin", ...)
@click.option("--auto", default=None, type=click.Choice(["light", "medium", "heavy"]), ...)
def evolve(...) -> None:
```

**What to replicate (identical semantics to Phase 5 / D-09):** add `@click.option("--session-source", default=None, type=click.Path(exists=True, file_okay=False, dir_okay=True), help="...")` — **exact same flag name, type, and help text** as Phase 5's variant.

**What to diverge:**
- Wire `session_source` through `evolve(...)` → `_evolve_impl(...)` (note Phase 13 has the public `evolve` Click + private `_evolve_impl` worker — see lines 593-617).
- The union-load branch lives in `_evolve_impl` after dataset load (parallel to where `_load_dataset` is currently invoked).
- Update `__all__` if needed (line 85-96 currently re-exports `_load_dataset`; no change needed if `_load_jsonl_skip_bad` is imported, not re-exported).

---

### `tests/tools/test_session_*.py` (NEW × 9) + `tests/fixtures/sessions/*.json` (NEW × 7)

**Analog (test fixture):** `tests/conftest.py` lines 7-38 — **direct reuse**, no new fixture file.

#### Reusable mock LM fixture (replicate `tests/conftest.py:7-38` — IMPORT, do not duplicate)

```python
@pytest.fixture
def mock_lm_with_usage():
    """Returns a callable that mimics a dspy.LM whose Prediction carries usage.

    Usage:
        def test_foo(mock_lm_with_usage):
            lm = mock_lm_with_usage(
                response_text='{"selected_tool":"x","selected_params":"{}"}',
                prompt_tokens=100,
                completion_tokens=20,
                model_name="openai/gpt-4.1-mini",
            )
            # Pass `lm` wherever dspy.configure(lm=...) is expected.
    """
    def factory(*, response_text: str = "", prompt_tokens: int = 100,
                completion_tokens: int = 20, model_name: str = "openai/gpt-4.1-mini"):
        lm = MagicMock(name=f"mock_lm[{model_name}]")
        lm.model = model_name
        lm.return_value = [response_text]
        lm._usage_records = [{
            "model": model_name,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }]
        return lm
    return factory
```

**What to replicate:** in `test_session_judge.py`, declare `def test_verdict_round_trip(mock_lm_with_usage):` — pytest will find the fixture from the root `tests/conftest.py` automatically (no import needed). Use it for ConfirmMisselection round-trip and the user_correction LLM 二判 test.

**What to diverge:** `response_text` carries verdict JSON (e.g. `'{"verdict":"confirm_misselection","correct_tool":"terminal","rationale":"..."}'`).

#### Fixture session JSON shape (replicate real session — RESEARCH lines 348-378)

```python
# Reference shape (real ~/.hermes/sessions/session_*.json structure)
{
  "session_id": "...",
  "messages": [
    {"role": "user", "content": "..."},
    {
      "role": "assistant",
      "content": "...",
      "tool_calls": [
        {
          "id": "toolu_bdrk_01YR...",
          "type": "function",
          "function": {"name": "terminal", "arguments": "{\"command\":\"pwd\"}"}
        }
      ]
    },
    {
      "role": "tool",
      "content": "{\"output\":\"/Users/...\",\"exit_code\":0,\"error\":null}",
      "tool_call_id": "toolu_bdrk_01YR..."
    }
  ],
  "tools": [
    {"type": "function", "function": {"name": "terminal", "description": "...", "parameters": {...}}}
  ]
}
```

**What to replicate (verbatim across all 7 fixtures):**
- Top-level keys: `session_id` + `messages` + `tools`.
- `assistant` may carry both `content` and `tool_calls` simultaneously (RESEARCH Pitfall 1).
- `tool_calls[i].function.name` is the canonical tool-name source — not `tool[j].name` (실측 = `None`).
- `tool` message `content` is JSON-encoded string with `exit_code` / `error` fields (Pitfall 2).
- Cross-reference via `tool_call_id` (assistant.tool_calls[i].id == tool.tool_call_id).

**What to diverge per fixture:**
- `error_retry_b.json` — first tool message has `exit_code: 1` or non-null `error` string; subsequent assistant turn invokes a *different* `function.name` whose tool message succeeds (Pitfall 2 / 3).
- `user_correction_a.json` — user message after assistant tool_call contains 中英 corrective keyword (e.g. "不对，应该用 search_files").
- `oracle_disagreement_c.json` — single successful tool call where the test's mocked baseline ToolModule returns a *different* `selected_tool` than session.
- `malformed_msg.json` — one message missing `role`, one message with `tool_calls` set to non-list (str/None) — extractor must skip both, not crash.
- `multi_signal.json` — same task hits both B and A signals → `misselection_signals = ["error_retry","user_correction"]` → multiplier = max(3,3) = 3 train copies.
- `surface_drift.json` — assistant calls `function.name = "legacy_tool_v0"` not in mocked `extract_tool_descriptions` output → entire example dropped + counted in `surface_drift_dropped`.
- `secret_in_user_msg.json` — user message contains literal `eyJabcdefg...A.B.C` (JWT) and a 64-char SHA256 hex string — exactly one (the JWT) should be filtered, the SHA256 must NOT (entropy threshold calibration; RESEARCH A2).

---

## Shared Patterns

### Pattern A: Module-level Rich Console + colored markup
**Source:** `evolution/tools/evolve_tool_params.py:99` + `evolution/tools/tool_dataset.py:26` + `evolution/core/external_importers.py:38`
**Apply to:** `session_miner.py`, `mine_tool_sessions.py`

```python
from rich.console import Console
console = Console()

# Throughout module:
console.print("[bold cyan]Step 1:[/] Mining error_retry signal...")
console.print(f"  Found {n} candidates")
console.print(f"[yellow]⚠ {skipped}/{total} bad JSONL lines ({skipped/total*100:.1f}%)[/yellow]")
console.print(f"[bold green]Mining complete: {final} examples written[/bold green]")
```

**What to replicate:** module-level `console = Console()` (NOT inside functions/classes), Rich BBCode-style markup for all output, 2-space indent for sub-step lines, never use bare `print()` (CLAUDE.md convention).

---

### Pattern B: Inner-Signature DSPy mining-time judge
**Source:** `evolution/tools/tool_constraints.py:43-65, 180-216` (FactualCheckSignature, ConsistencySignature)
**Apply to:** `session_miner.py::ConfirmMisselection`, optional `session_miner.py::DetectUserCorrection` (A 信号 LLM 二判)

```python
class FactualCheckSignature(dspy.Signature):
    """Compare original and evolved tool descriptions to detect false claims.

    Determine whether the evolved description claims capabilities that
    are NOT present in the original description. ...
    """
    tool_name: str = dspy.InputField(
        desc="Name of the tool being checked",
    )
    original_description: str = dspy.InputField(
        desc="The original tool description before evolution",
    )
    evolved_description: str = dspy.InputField(
        desc="The evolved tool description to check for false claims",
    )
    has_false_claims: bool = dspy.OutputField(
        desc="True if evolved description claims capabilities NOT in original",
    )
    explanation: str = dspy.OutputField(
        desc="Explanation of what false claims were found, or why none were found",
    )
```

**What to replicate:** inner class within service class (NOT top-level); docstring describes contract first sentence + multi-paragraph rationale; each Field has `desc=` keyword arg with full prose hint; bool fields use `dspy.OutputField(desc=..., type=bool)` style.

---

### Pattern C: Fail-closed try/except → conservative default
**Source:** `evolution/tools/tool_constraints.py:248-262` (ParamConsistencyChecker.check)
**Apply to:** `session_miner.py::SessionToolMiner._judge_candidate`, A-signal `_extract_user_correction` LLM 二判, C-signal oracle ToolModule call

```python
try:
    with dspy.context(lm=lm):
        result = self.checker(
            tool_name=tool_name,
            frozen_tool_description=frozen_desc or "",
            evolved_param_descriptions=params_json,
        )
except Exception as e:
    # Conservative: any LM / parsing failure rejects the candidate.
    return ConstraintResult(
        passed=False,
        constraint_name="param_consistency",
        message=f"Consistency check failed for '{tool_name}' (LLM error)",
        details=str(e),
    )

# Polarity inversion: is_consistent True -> passed True.
# _parse_bool returns False on anything ambiguous -> fails CLOSED.
is_consistent = _parse_bool(getattr(result, "is_consistent", None))
```

**What to replicate:** bare `except Exception as e:` (do NOT catch specific DSPy types — they vary across versions); on failure return the conservative default (Phase 14 = `verdict="false_positive"`, drops candidate); use `getattr(result, "verdict", None)` not `result.verdict` (LLM may not produce the field).

---

### Pattern D: JSONL bad-line skip helper (D-18 minimal subset)
**Source:** `evolution/core/external_importers.py:185-188` (ClaudeCodeImporter inner-loop pattern)
**Apply to:** `session_miner.py::_load_jsonl_skip_bad` (NEW helper) used by session_miner output AND evolve `--session-source` load paths

```python
# Source: external_importers.py:185-188 (existing tolerance pattern in v1 importers)
for line in f:
    if not line.strip():
        continue
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        continue
```

**What to replicate:** the **exact** per-line `if not line.strip(): continue` + `try: json.loads / except json.JSONDecodeError: continue` shape. RESEARCH Pattern 3 fully spells out the `_load_jsonl_skip_bad` helper signature with skip counter + 5% threshold warn.

**Scope guard:** RESEARCH explicitly carves this OUT of `EvalDataset.load` and `GoldenDatasetLoader.load` — those are owned by v2-STAB-01.

---

### Pattern E: Dataclass + `to_dict` + filtered `from_dict`
**Source:** `evolution/tools/tool_dataset.py:32-71` (ToolSelectionExample) + `evolution/tools/tool_loader.py:36-115` (ToolParam, ToolDescription)
**Apply to:** any new dataclass in session_miner.py (e.g. internal `Candidate`, `Verdict` if persisted to `miner_log.jsonl`)

```python
@dataclass
class ToolSelectionExample:
    task_description: str
    correct_tool: str
    correct_params: dict = field(default_factory=dict)
    difficulty: str = "medium"
    confuser_tools: list[str] = field(default_factory=list)
    reason: str = ""
    source: str = "synthetic"

    def to_dict(self) -> dict:
        return {...}  # explicit field-by-field

    @classmethod
    def from_dict(cls, d: dict) -> "ToolSelectionExample":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
```

**What to replicate:** explicit `to_dict` (no `asdict` — keeps key ordering + lets future evolve), filtered `from_dict` for forward-compat across schema versions.

---

## No Analog Found

None — every Phase 14 file has a close analog. The novel pieces (3 signal extractors, hash bucket, Shannon entropy) are pure helper functions following the codebase's existing snake_case + private-prefix convention.

---

## Conventions Summary

These conventions cut across every new/modified file in Phase 14. The planner should reference this section in each plan's "Action" instructions to avoid repeating per-file.

| Convention | Source of Truth | Phase 14 Application |
|------------|-----------------|----------------------|
| `@dataclass` + `field(default_factory=list)` for mutable defaults | `tool_dataset.py:32-54`, `tool_loader.py:36-96` | New `Candidate`, `Verdict` dataclasses; `ToolSelectionExample.misselection_signals` |
| Explicit `to_dict()` listing all fields + `from_dict()` filtering via `cls.__dataclass_fields__` | `tool_dataset.py:56-71` | D-02 `ToolSelectionExample` extension; backward-compat for Phase 4 JSONL |
| `snake_case` functions; private helpers prefixed `_` | `external_importers.py:_contains_secret`, `tool_constraints.py:_parse_bool`, `tool_dataset.py:_parse_json_array` | `_extract_error_retry`, `_extract_user_correction`, `_extract_oracle_disagreement`, `_normalize_task_hash`, `_hash_to_split`, `_load_jsonl_skip_bad`, `_shannon_entropy`, `_load_baseline_module` |
| Click + Rich + module-level `console = Console()` + `metrics.json` indent=2 + `if __name__ == "__main__": main()` guard | `evolve_tool_descriptions.py:31, 400-417, 420-421` | `mine_tool_sessions.py` CLI; `--session-source` flag added to existing CLIs |
| Inner Signature class (NOT top-level) for DSPy contracts; one `dspy.ChainOfThought` instance per Signature held on the consuming class | `tool_constraints.py:43-65, 180-216`, `tool_dataset.py:164-205` | `SessionToolMiner.ConfirmMisselection`, optional `SessionToolMiner.DetectUserCorrection` |
| Fail-closed `try: ... except Exception as e: return <conservative_default>` around all LLM calls; `getattr(result, "field", None)` for output access; `_parse_bool` from `tool_constraints` for unknown→False | `tool_constraints.py:248-262` | All session_miner LLM calls; oracle `ToolModule.forward` call |
| Type hints: `list[X]`, `dict[str, int]`, `Optional[X]` (modern, Python ≥3.10) | All listed files | Every new function signature |
| Sentinel string for confidence: `"true"|"yes"|"1"` only — everything else False | `tool_constraints.py:_parse_bool` (15-29) | Verdict label parsing in ConfirmMisselection |
| Output dir naming: `<datetime.strftime("%Y%m%d_%H%M%S")>` for success; `FAILED_<ts>` / `ABORTED_<ts>` prefixes for failure paths | `evolve_tool_descriptions.py:351-353`, `evolve_tool_params.py:30-34 docstring` | mine_tool_sessions output: `datasets/tools/sessions/<ts>/`; failure: `FAILED_<ts>/` / `ABORTED_<ts>/` |
| Test fixture reuse: import `mock_lm_with_usage` from root `tests/conftest.py` — pytest auto-discovery, no `pytest_plugins` needed | `tests/conftest.py:7-38` | All `test_session_judge.py`, `test_session_signal_extract.py` (A 信号 mock), `test_session_miner.py`, `test_evolve_with_session_source.py` |
| Read-only on hermes-agent: never import `tool_loader.write_back_description` | `evolve_tool_params.py:36-38` (docstring scope guard) | session_miner / mine_tool_sessions / both evolve CLIs in their `--session-source` branch |

---

## Metadata

**Analog search scope:**
- `evolution/tools/` (all files; `tool_dataset.py`, `tool_constraints.py`, `tool_module.py`, `tool_loader.py`, `evolve_tool_descriptions.py`, `evolve_tool_params.py`)
- `evolution/core/` (`external_importers.py`, `cost_tracker.py`, `config.py`)
- `tests/conftest.py`

**Files scanned:** 9 source + 1 test root config + cross-references to RESEARCH §Analog Code table (15 entries already line-pinned).

**Pattern extraction date:** 2026-05-08

---

## PATTERN MAPPING COMPLETE

**Phase:** 14 - SessionDB Mining for Tools
**Files classified:** 19 (collapsing 7 fixtures as one row)
**Analogs found:** 19 / 19

### Coverage
- Files with exact analog: 11 (session_miner via composite, mine_tool_sessions, in-place modifications × 4, fixtures, mock LM tests, miner test)
- Files with role-match analog: 6 (test_session_signal_extract, test_session_split, test_secret_patterns_v2, test_jsonl_skip_bad, test_surface_drift, test_mine_cli, test_evolve_with_session_source)
- Files with no analog: 0

### Key Patterns Identified
- **Inner-Signature + ChainOfThought + fail-closed try/except** — the universal LLM judge template across `tool_constraints.py` and `tool_dataset.py`; Phase 14 `ConfirmMisselection` follows it verbatim.
- **Click CLI + module-level Rich console + `metrics.json` (indent=2) + FAILED_/ABORTED_ output dirs** — the universal CLI template Phase 14 inherits from `evolve_tool_descriptions.py` / `evolve_tool_params.py`.
- **Dataclass + filtered `from_dict`** — auto-handles backward compat for D-02 `misselection_signals` field; no migration needed for Phase 4 JSONL.
- **JSONL bad-line tolerance is a NEW helper, NOT a modification of `EvalDataset.load`** — D-18 scope guard; the pattern itself comes from `external_importers.py:185-188` (already in v1 importers).
- **Layer 1 secret pattern extension is in-place to existing `SECRET_PATTERNS` block** — entropy branch added in `_contains_secret`, regression-tested against existing v1 fixtures.

### File Created
`.planning/phases/14-sessiondb-mining-for-tools/14-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns + line ranges directly in each PLAN.md action section. All 19 files have at least one concrete code excerpt with file:line pinpoint.
