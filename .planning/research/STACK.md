# Technology Stack: v2.0 Milestone Additions

**Project:** hermes-agent-self-evolution
**Researched:** 2026-04-23 (v2 milestone)
**Confidence:** MEDIUM-HIGH (verified via filesystem inspection + PyPI; Context7 / WebSearch unavailable in this session)

## v1 Baseline (already in place — see pyproject.toml)

The v1 stack is documented in `.planning/codebase/STACK.md` and pinned in `pyproject.toml`. It is NOT re-researched here. For reference, the load-bearing v1 dependencies are:

- `dspy>=3.0.0` — Module/Signature/ChainOfThought/GEPA/MIPROv2/LM/Example/Prediction
- `openai>=1.0.0` — wired through `dspy.LM`
- `pyyaml>=6.0`, `click>=8.0`, `rich>=13.0`
- `pytest>=7.0`, `pytest-asyncio>=0.21` (dev extra)
- `darwinian-evolver` (declared in `[darwinian]` extra — see warning under Phase 21 below; package name does not currently resolve on PyPI)
- `reportlab` (used by `generate_report.py`, not yet declared)
- Python `>=3.10`; `.venv` is CPython 3.13.3
- No lockfile (no `requirements.txt`, `poetry.lock`, `uv.lock`)

The v1 stack is sufficient for everything the v1 pipelines do. The v2 work below ADDS to it; nothing in v1 needs to be removed or upgraded.

## Executive Summary of v2 Additions

The v2 milestone adds capabilities in five orthogonal axes (SessionDB mining, per-parameter optimization, think-augmented selection, dashboards, drift detection, benchmark gating, and code evolution). Most of these reuse the existing DSPy + Click + Rich stack. Only THREE new runtime dependencies are recommended, and one of them is conditional:

1. **`sqlalchemy>=2.0` is NOT recommended** — use stdlib `sqlite3`. The hermes `state.db` is a small, read-only SQLite file with FTS5 already configured; an ORM adds friction with no payoff (no schema we control, no migrations).
2. **No new dashboard library** — Rich `Table` + `Live` covers Phase 16. Optionally add `plotly>=5.24` ONLY if the user asks for HTML export later (deferred to a follow-up).
3. **`sentence-transformers` is NOT recommended for Phase 18 drift detection** — reuse the existing `LLMJudge` pattern. Sentence-transformers brings PyTorch (~700MB) for marginal benefit on a 5-section comparison job.
4. **TBLite (Phase 20) does NOT need a new dependency** — it is already a Python module inside hermes-agent at `environments/benchmarks/tblite/tblite_env.py`. Drive it via `subprocess` against `python -m environments.benchmarks.tblite.tblite_env evaluate`.
5. **Phase 21 (Darwinian code evolution) is BLOCKED** — `darwinian-evolver` does not resolve on PyPI (verified 2026-04-23). The closest live packages are `openevolve` (0.2.27, Apache-2.0) and `darwinian` (0.0.5.4). Decision required before Phase 21 can be planned.

The total net additions for v2 are: optionally `plotly`, possibly `openevolve` (replacing `darwinian-evolver`), and one new internal subpackage `evolution/sessiondb/` that wraps `sqlite3`.

## Recommended Stack (additions only)

### Core Additions

| Technology | Version | Purpose | Phase | Why Recommended |
|------------|---------|---------|-------|-----------------|
| `sqlite3` (stdlib) | bundled with Python 3.13 | Query hermes `~/.hermes/state.db` (FTS5-indexed) for tool-call ground truth and behavioral patterns | 14, 19 | Already present — no new dep. WAL-mode safe for concurrent reads while hermes is running. FTS5 enables fast keyword search of `messages.content`. |
| Existing JSONL readers | n/a | Continue mining `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` (current Claude Code format) and `~/.copilot/session-state/*/events.jsonl` | 14, 19 | Existing `external_importers.py` already does this; needs an UPDATE because `~/.claude/history.jsonl` is the legacy path — modern Claude Code (v2.x) uses per-project JSONL files. |
| `rich.live.Live` + `rich.table.Table` | rich >=13.0 (already pinned) | Per-tool regression dashboard with live-updating table | 16 | No new dep. Matches the existing console-output convention used everywhere in the codebase. |

### Optional / Conditional

| Technology | Version | Purpose | Phase | Decision Trigger |
|------------|---------|---------|-------|------------------|
| `plotly` | >=5.24,<7 | HTML export of per-tool regression dashboard | 16 (follow-up) | Only add IF the user asks for shareable artifact beyond terminal output. Default: don't add. |
| `openevolve` | >=0.2.27 | Code-level evolution of hermes-agent components | 21 | Add IF Phase 21 is greenlit AND `darwinian-evolver` is confirmed absent. See "Phase 21 BLOCKER" section. Apache-2.0 license — no AGPL boundary concern. |
| `darwinian` | 0.0.5.4 | Alternate, much smaller GA library | 21 | Only if `openevolve` is rejected and a roll-your-own GA is unwanted. Note: 0.0.x versioning, single contributor — high risk for production use. |
| `reportlab` | declared dep, install on demand | PDF reporting (already used in `generate_report.py`) | n/a | Add to `[reporting]` extra to make explicit; no functional change. |

### Explicitly NOT Adding

| Technology | Why Rejected | Use Instead |
|------------|--------------|-------------|
| `sqlalchemy` (any version) | We do not own the schema, do not run migrations, are read-only. ORM adds boilerplate with zero payoff for ad-hoc analytical queries. | `sqlite3` stdlib + parameterized queries + `dataclasses` for row mapping. |
| `pandas` | Would only be used to format dashboards; Rich `Table` is sufficient and matches house style. Adds ~50MB and a numpy dep. | `rich.table.Table` + plain dicts. |
| `textual` | Full TUI framework. Phase 16 needs a single live-updating panel, not an interactive app. Adds an event loop, async runtime, and learning curve. | `rich.live.Live` (already in rich >=13.0). |
| `sentence-transformers` | Pulls PyTorch (~700MB), needs a model download, gives a single-number similarity score. Drift detection benefits from a structured rubric (tone, formality, persona) which an LLM judge produces with explanations. | New `PersonalityDriftChecker` class following the existing `LLMJudge` pattern in `evolution/core/fitness.py`. |
| `tblite` (PyPI package) | The PyPI package named `tblite` is a quantum-chemistry library (xTB tight-binding) — wrong domain. Hermes' TBLite is an internal benchmark module inside hermes-agent. | `subprocess.run(["python", "-m", "environments.benchmarks.tblite.tblite_env", "evaluate", ...], cwd=hermes_repo)`. |
| `mlflow`, `wandb`, `tensorboard` | Heavy experiment-tracking infra for what is currently a local-output JSON file. Would invert the "independent pipeline" architecture decision. | Continue writing `metrics.json` files into `output/<phase>/<timestamp>/` like Phase 1-11 already do. |
| New optimizer libraries (e.g., `gepa`, `optuna`) | DSPy 3.x already provides `dspy.GEPA`. Phase 1-11 are validated against it. | `dspy.GEPA` with custom `component_selector`. |

## Per-Phase Integration Plan

Each row tells the planner which `evolution/` submodule to touch and which dependency to use.

| Phase | Capability | New module(s) | Dependency | Notes |
|-------|------------|---------------|------------|-------|
| 13 | Per-parameter description optimization | Extend `evolution/tools/tool_module.py` to expose each `(tool, param)` pair as a separately optimizable string; extend `tool_constraints.py` for per-param size check (already at 200 chars in `EvolutionConfig`). | None (DSPy only) | The existing `ToolModule` wraps tool-level descriptions. v2 turns the parameter-description set into a flat dict-of-strings keyed by `tool.param`, optimized jointly with the tool description in the same GEPA run. |
| 14 | SessionDB mining for tools | NEW `evolution/sessiondb/hermes_db.py` (SQLite reader for `~/.hermes/state.db`); extend `evolution/tools/tool_dataset.py` to accept `--source sessiondb` and weight misselection examples higher. | `sqlite3` (stdlib) | Hermes `messages` table has `tool_calls` (JSON), `tool_name`, and FTS5 `messages_fts`. Misselection signal = a tool call followed by a corrective user message in the same session. |
| 15 | Think-augmented tool selection | Extend `tool_module.py` to wrap `dspy.ChainOfThought` (instead of `dspy.Predict`) for the selector; add a separate `reasoning_prompt` parameter exposed to GEPA. | None (DSPy only) | DSPy already supports CoT optimization; the "thinking step" prompt becomes another component for `seed_candidate`. |
| 16 | Per-tool regression dashboard | NEW `evolution/monitor/dashboard.py` using `rich.live.Live` + `rich.table.Table`; persist per-tool metrics history to `output/tools/<run>/per_tool_metrics.jsonl`. | rich (already pinned) | Existing `CrossToolRegressionChecker` already produces per-tool deltas. This phase adds the visualization layer + JSONL history file. |
| 17 | Joint section optimization | Extend `prompt_module.py` to expose all 5 sections in one DSPy module call with `component_selector="all"` instead of round-robin. | None | The infrastructure exists; this is a wiring change, not a new dependency. |
| 18 | Personality drift detection | NEW `evolution/prompts/personality_drift.py` defining a `PersonalityDriftChecker` (LLM-as-judge with tone/formality/persona rubric), wired into `prompt_constraints.py`. | None (uses existing `dspy.LM`) | Reuse the LLMJudge pattern from `evolution/core/fitness.py`. Returns a 3-axis score + textual feedback so GEPA can act on it. |
| 19 | SessionDB behavioral mining for prompts | Extend `evolution/sessiondb/hermes_db.py` (built in Phase 14) with `extract_behavioral_examples()`; extend `prompt_dataset.py` to accept `--source sessiondb`. | `sqlite3` (stdlib) | Pair `system_prompt` from `sessions` with the resulting message thread; identify which section likely drove a behavior via keyword/heuristic match. |
| 20 | Benchmark-gated validation | NEW `evolution/benchmarks/tblite_runner.py` — wrapper that shells out to `python -m environments.benchmarks.tblite.tblite_env evaluate --env.task_filter ...` inside `HERMES_AGENT_REPO`, parses the resulting metrics file, returns pass/fail. | `subprocess` (stdlib) | TBLite is already inside hermes-agent. Wrapper handles cwd, env, timeout, output parsing. The gate is opt-in via `--benchmark` CLI flag. |
| 21 | Darwinian code evolution | NEW `evolution/code/code_evolver.py` — adapter to whichever evolutionary library is chosen. | **BLOCKED — see below** | Requires resolution of the `darwinian-evolver` package mystery. |

## Phase 21 BLOCKER: `darwinian-evolver` does not exist on PyPI

**Verification performed 2026-04-23:**

```
$ pip index versions darwinian-evolver
ERROR: No matching distribution found for darwinian-evolver
```

`pyproject.toml` declares it under `[project.optional-dependencies] darwinian = ["darwinian-evolver"]`, and `CLAUDE.md` documents it as "AGPL v3 licensed" — but the package is not installable. Closest matches on PyPI:

| Package | Version | License | Active | Fit |
|---------|---------|---------|--------|-----|
| `openevolve` | 0.2.27 (frequent releases) | Apache-2.0 | Yes | LLM-driven code evolution. Most likely intended target — the API surface (population, mutation, fitness, archive) maps directly onto what Phase 21 needs. |
| `darwinian` | 0.0.5.4 | unverified | Stale (small contributor base) | Generic GA library — too low-level; would require building the LLM-mutation loop from scratch. |
| Roll-your-own | n/a | n/a | n/a | DSPy + GEPA already provides reflective text mutation. For code evolution, write a thin loop that samples patches, runs `pytest`, and uses GEPA-style reflection. ~300 LOC. |

**Recommendation for the roadmapper:**

1. Before planning Phase 21, decide which of the three options above is the actual target.
2. If `openevolve` (Apache-2.0): no AGPL boundary concerns; can be a regular dependency in the `[code]` extra. Update `pyproject.toml` and `CLAUDE.md` accordingly.
3. If a real `darwinian-evolver` package exists in a private index or a fork the user has in mind, the roadmapper must ask the user for the source URL.
4. If "AGPL v3" is a real constraint (some unpublished package the user knows about), then it MUST be isolated behind a subprocess boundary (separate process, communicate via JSON over stdin/stdout) to keep the AGPL copyleft from infecting the main MIT-licensed pipeline. This means: a thin CLI shim in `evolution/code/_agpl_runner.py` that imports the AGPL package, run it via `subprocess.run`, never `import` it from the main package. Ship the AGPL shim as a separately-licensed sub-distribution if it ever ships at all.

**Until this is resolved, Phase 21 cannot be designed.** Suggest the roadmapper open a question to the user as the first step of Phase 21 planning.

## AGPL Boundary Concerns (general guidance)

The hermes-agent self-evolution project is MIT-licensed. AGPL v3 is strong copyleft: importing AGPL code into the same Python process puts the entire process under AGPL when distributed or made available over a network.

**Hard rules if any AGPL dependency is ever added:**

1. **No `import` from the AGPL package in the main `evolution/` package.** Place all AGPL-touching code in a clearly-marked separate package (e.g., `evolution_agpl/`) with its own `LICENSE` file.
2. **Process isolation:** the main pipeline calls the AGPL shim via `subprocess.run()`. Data crosses the boundary as JSON / files, never as Python objects.
3. **Distribution:** the AGPL shim is a separate optional-extra (`[code-agpl]`), NOT in the default install.
4. **README / docs:** clearly mark which features require the AGPL extra.
5. **Network use:** if hermes-agent itself becomes a service that users access remotely, AGPL § 13 forces source disclosure for the entire combined work — process isolation alone does not save you. Network deployment of an AGPL-touching system requires legal review.

For Phase 21 specifically: prefer Apache-2.0 (`openevolve`) to sidestep all of this.

## Installation

```bash
# v1 baseline (already done — no change)
pip install -e .

# Phase 14/19 SessionDB mining: nothing to install (stdlib sqlite3)

# Phase 16 dashboard: nothing new (uses pinned rich >=13.0)
# OPTIONAL HTML export later:
pip install "plotly>=5.24,<7"

# Phase 18 drift detection: nothing new (uses pinned dspy + openai)

# Phase 20 TBLite gate: nothing on this side (subprocess into hermes-agent)
# Hermes-side prerequisite (verify on the hermes repo, not here):
#   - Docker daemon running for TBLite tasks
#   - HuggingFace `datasets` accessible (NousResearch/openthoughts-tblite)

# Phase 21 code evolution: BLOCKED — see "Phase 21 BLOCKER" section.
# IF the user confirms openevolve is the target:
pip install "openevolve>=0.2.27"
```

**Suggested `pyproject.toml` patch** once decisions are made:

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-asyncio>=0.21"]
reporting = ["reportlab>=4.0"]                 # NEW: declare what generate_report.py uses
dashboard = ["plotly>=5.24,<7"]                # NEW (optional): HTML export
code = ["openevolve>=0.2.27"]                  # NEW (replaces "darwinian"); pending decision
# REMOVE the "darwinian" extra unless the package is found
```

## Version Compatibility Matrix

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `dspy>=3.0.0` | Python 3.10+ | Already validated; no change needed for v2. |
| `sqlite3` stdlib | Python 3.10+ | FTS5 requires SQLite >= 3.20. Python 3.13.3 ships SQLite 3.45+ on macOS — verified by inspecting `~/.hermes/state.db` which uses FTS5 successfully. |
| Hermes `state.db` schema | hermes-agent v0.5.x current | Schema observed 2026-04-23: `sessions(id, source, system_prompt, ...)`, `messages(role, content, tool_calls, tool_name, ...)`, `messages_fts` (FTS5 over `messages.content`). If hermes-agent migrates the schema, the importer breaks loudly — schema_version table exists for future-proofing. |
| `rich>=13.0` (live) | Terminal with ANSI support | All target dev environments; CI logs may show flicker — disable `Live` when `not sys.stdout.isatty()`. |
| `openevolve>=0.2.27` | Python 3.10+, needs `OPENAI_API_KEY` or compatible | Apache-2.0; releases roughly weekly. Pin to `>=0.2.27,<0.3` until evaluated. |
| `plotly>=5.24` | Python 3.10+ | Pinned `<7` because plotly 6.x is current and 7.x not yet released; revisit later. |

## What NOT To Do (v2-specific)

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Building a separate session-DB schema in this project | We are read-only consumers of hermes data; introducing our own DB = sync drift, broken invariants, no value. | `sqlite3.connect(..., uri=True)` with `mode=ro` against `~/.hermes/state.db` directly. |
| Running TBLite in-process | TBLite spawns Docker containers, downloads HF datasets, and runs for tens of minutes. In-process means a crash takes the optimizer with it. | `subprocess.run([..., "--timeout", "1200", ...])` with output parsed from a known metrics file. |
| Wrapping personality drift in a numeric similarity score (cosine of embeddings) | Loses the "why" — GEPA can't act on a number, but it can act on "evolved text shifted from professional to casual". | LLM rubric returning `{tone: float, formality: float, persona: float, explanation: str}`. |
| Using `~/.claude/history.jsonl` for Claude Code mining | Modern Claude Code (verified 2026-04-23, current version 2.1.84) writes per-project JSONL files at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` instead. The legacy file may be empty or absent. | UPDATE `ClaudeCodeImporter` in `external_importers.py` to scan `~/.claude/projects/*/` recursively. Keep the legacy path as a fallback for users on older versions. |
| Per-iteration TBLite gating | Each TBLite run is 20+ minutes per task, $50-200 per full sweep — already documented as out of scope in REQUIREMENTS.md. | Use TBLite as a final acceptance gate AFTER the cheap proxy metrics already accept the candidate. |
| Joint optimization of all prompt sections without a fallback | Search space is 5x larger than round-robin; if it diverges, no recovery. | Keep round-robin in `prompt_module.py`; make joint mode an opt-in flag (`--joint-sections`). |

## Stack Patterns by Variant

**If the user accepts `openevolve` for Phase 21:**
- Add `[code]` extra with `openevolve`
- Place adapter in `evolution/code/code_evolver.py`
- Reuse existing `ConstraintValidator` for code-output constraints
- Fitness function = pytest pass rate + a static-analysis quality signal

**If the user insists on AGPL `darwinian-evolver` (and provides a source URL):**
- Create separate `evolution_agpl/` package with own LICENSE
- Wire via subprocess only, never import
- Add a clear runtime error message if the AGPL extra is missing

**If the user defers Phase 21 entirely:**
- Drop `[darwinian]` extra from `pyproject.toml`
- Mark Phase 21 as deferred in ROADMAP.md
- v2 milestone still ships Phases 13-20 with no new runtime deps

## Confidence Assessment

| Area | Confidence | Verification Method |
|------|------------|---------------------|
| Hermes `state.db` is SQLite with FTS5 (Phase 14, 19) | HIGH | Direct file inspection: `sqlite3 ~/.hermes/state.db .schema` returned the full schema with FTS5 triggers. |
| Claude Code modern session location is `~/.claude/projects/.../*.jsonl` (Phase 14, 19) | HIGH | Direct inspection of `~/.claude/projects/-Users-slj----MiroFish/<uuid>.jsonl` — file exists, format is JSONL with `sessionId`, `cwd`, `version: 2.1.84` per record. |
| TBLite is a hermes-internal subprocess target (Phase 20) | HIGH | Read `/Users/slj/.hermes/hermes-agent/environments/benchmarks/tblite/tblite_env.py` and its README — confirms `python module + CLI entry point`, default 20-minute timeout, HuggingFace dataset loader. |
| `darwinian-evolver` does NOT exist on PyPI (Phase 21 blocker) | HIGH | `pip index versions darwinian-evolver` returns "No matching distribution found"; `pip index versions darwinian` returns 0.0.5.4 (different package). |
| `openevolve` is the most plausible substitute (Phase 21) | MEDIUM | PyPI returns `openevolve 0.2.27` with active release cadence; could not fetch the project README in this session (WebFetch denied). User confirmation needed. |
| `sqlite3` stdlib > `sqlalchemy` for our read-only access pattern (Phase 14, 19) | HIGH | We do not own the schema, do not need migrations, and run only ad-hoc analytical queries. ORM provides no value here. |
| `rich.live.Live` > `textual` / `plotly` for Phase 16 | HIGH | Phase 16 explicitly requires "Rich console dashboard" per ROADMAP.md success criterion. No interactive UI needed. |
| LLM-as-judge > sentence-transformers for drift detection (Phase 18) | MEDIUM | Reasoning is sound (structured feedback for GEPA, no PyTorch dep), but no concrete benchmark performed. If A/B testing later shows LLM judge is too slow or expensive, sentence-transformers could be added back. |
| Hermes `state.db` schema is stable | LOW | Only one snapshot observed (2026-04-23). The `schema_version` table suggests anticipated migration. The Phase 14/19 importer must check `schema_version.version` and fail loudly on mismatch. |
| AGPL boundary advice for Phase 21 | MEDIUM | General GPL/AGPL legal principles are well-established, but specific applicability depends on the actual package and its terms — legal review still recommended if AGPL is chosen. |

## Open Questions for Roadmapper

1. **Phase 21 dependency name:** Is `darwinian-evolver` a typo for `openevolve`, a private-fork name, or a yet-unpublished package? Phase 21 cannot proceed without an answer.
2. **Hermes `state.db` access mode:** can the v2 pipeline assume read-write-during-hermes-operation, or must we copy the DB to a temp file first? (Recommend: open in `mode=ro` URI to be safe with WAL.)
3. **Claude Code session importer:** should the modernized `~/.claude/projects/` path REPLACE the legacy `~/.claude/history.jsonl` reader, or live alongside it as a fallback? (Recommend: alongside, with a deprecation note.)
4. **Phase 16 output format:** terminal-only (Rich `Live`) for the milestone, with HTML export deferred? (Recommend: yes, defer plotly until requested.)
5. **TBLite Docker requirement:** does the dev/CI environment have Docker? Phase 20 cannot run without it.

## Sources

- File inspection: `sqlite3 ~/.hermes/state.db .schema` (2026-04-23) — confirms FTS5-indexed messages table with `tool_calls`, `tool_name`, `system_prompt` fields suitable for mining.
- File inspection: `~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl` — confirms current Claude Code session storage location and format.
- File read: `/Users/slj/.hermes/hermes-agent/environments/benchmarks/tblite/tblite_env.py` and `README.md` — confirms TBLite invocation pattern, timeout, dataset source.
- PyPI index lookups: `darwinian-evolver` (not found), `darwinian` (0.0.5.4), `openevolve` (0.2.27), `sentence-transformers` (5.4.1), `textual` (8.2.4), `plotly` (6.7.0), `sqlalchemy` (2.0.49) — verifies current pinnable versions.
- Project files read: `pyproject.toml`, `evolution/core/external_importers.py`, `evolution/core/constraints.py`, `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` — verifies current architecture and v1 patterns to be preserved.
- Confidence-LOW items (Context7 / WebFetch / WebSearch were unavailable in this session): `openevolve` API surface, exact compatibility of TBLite with current hermes-agent v0.5.x branch, and the long-term stability of the hermes `state.db` schema. These items are flagged in the Confidence Assessment table.

---
*Stack additions for v2.0 milestone of hermes-agent-self-evolution*
*Researched: 2026-04-23*
