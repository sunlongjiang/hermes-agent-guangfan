---
phase: 20-benchmark-gated-validation
plan: 01
type: execute
wave: 1
depends_on: []
revised_at: 2026-05-19
files_modified:
  - evolution/core/config.py
  - evolution/benchmarks/__init__.py
  - datasets/prompts/tblite_stratified_subset.json
  - .gitignore
autonomous: true
requirements:
  - PMPT-V2-03
requirements_addressed:
  - PMPT-V2-03
tags:
  - phase-20
  - benchmark
  - config
must_haves:
  truths:
    - "EvolutionConfig has 4 new fields: benchmark_max_cost_usd (default 50.0), tblite_estimated_cost_per_task_usd (default 0.4), benchmark_runs (default 3), benchmark_heartbeat_seconds (default 60)"
    - "All 4 new config fields obey YAML < env < CLI override chain (Phase 13 max_cost_usd pattern 1:1)"
    - "evolution/benchmarks/ package exists with docstring-only __init__.py (lazy import guard per D-Discretion-1)"
    - "datasets/prompts/tblite_stratified_subset.json exists with per_tier_counts {easy:12, medium:8, hard:7, extreme:3} totaling 30 tasks, seed=42, source='NousResearch/openthoughts-tblite', AND task_filter is a list of {name, tier} OBJECTS (W-7 revision: tier-explicit schema replaces flat-list-with-implicit-ordering)"
    - ".gitignore exempts datasets/prompts/tblite_anchor.json + datasets/prompts/tblite_stratified_subset.json from datasets/**/*.json ignore (D-CAL-02 mirror)"
    - ".gitignore adds logs/ ignore (D-08 Soft-Rollback audit log target)"
  artifacts:
    - path: evolution/core/config.py
      provides: "4 new fields with full YAML/env/CLI override chain"
      contains: "benchmark_max_cost_usd"
    - path: evolution/benchmarks/__init__.py
      provides: "Package marker with lazy-import-guard docstring; submodules NOT eager-imported"
      contains: "Phase 20"
    - path: datasets/prompts/tblite_stratified_subset.json
      provides: "30-task whitelist with tier-explicit per-element objects + per_tier_counts + seed=42 for deterministic re-runs"
      contains: "task_filter"
    - path: .gitignore
      provides: "tblite_anchor.json + tblite_stratified_subset.json exceptions; logs/ ignore"
      contains: "!datasets/prompts/tblite_anchor.json"
  key_links:
    - from: evolution/core/config.py
      to: evolution.yaml
      via: "data.get('benchmark_max_cost_usd') / data.get('tblite_estimated_cost_per_task_usd') / data.get('benchmark_runs') / data.get('benchmark_heartbeat_seconds')"
      pattern: "benchmark_max_cost_usd"
    - from: evolution/core/config.py
      to: environment variables
      via: "EVOLUTION_BENCHMARK_MAX_COST_USD / EVOLUTION_TBLITE_COST_PER_TASK_USD / EVOLUTION_BENCHMARK_RUNS / EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS"
      pattern: "EVOLUTION_BENCHMARK_MAX_COST_USD"
    - from: evolution/core/config.py
      to: CLI overrides dict
      via: "overrides.get('benchmark_max_cost_usd') / overrides.get('tblite_estimated_cost_per_task_usd') / overrides.get('benchmark_runs') / overrides.get('benchmark_heartbeat_seconds')"
      pattern: "overrides.get..benchmark_max_cost_usd"
---

<objective>
Wave 1 — 为 Phase 20 奠定 config + 包脚手架基础设施。

- 在 `EvolutionConfig` 上新增 4 个 dataclass 字段（D-16/D-17/D-03/D-11），并按 Phase 13 `max_cost_usd` 的 1:1 模板补齐 YAML/env/CLI 三层 override 链。
- 创建 `evolution/benchmarks/` 包目录，`__init__.py` 仅含 docstring（lazy-import-guard，D-Discretion-1）— 不 eager-import 任何子模块，确保 `--benchmark=none` 路径在 hermes-agent 不可达时仍可跑。
- 生成 `datasets/prompts/tblite_stratified_subset.json` 30-task 白名单（per_tier_counts {easy:12, medium:8, hard:7, extreme:3}, seed=42, D-05）。**W-7 revision (2026-05-19)**: `task_filter` 改为 list of `{name: str, tier: str}` OBJECTS 而非 flat string list。这消除了 `--benchmark-tier` 切片对 "task_filter 按 tier 顺序排序" 隐式契约的依赖。Wave 1 落初版 placeholder（同样以 object 形式），Wave 4 calibration 跑通后由 ops 用真实 TBLite task names 覆盖（CONTEXT §Discretion 第 5 项）。
- 扩展 `.gitignore`：为 `tblite_anchor.json` + `tblite_stratified_subset.json` 加 git-track exception（D-CAL-02 模板），新增 `logs/` ignore（D-08 Soft-Rollback 审计日志根目录）。

Purpose: Wave 2 (`TBLiteRunner`) + Wave 2 (`TBLiteBenchmarkGate`) 都依赖 `EvolutionConfig.benchmark_*` 字段读取；Wave 3 (`build_tblite_calibration`) 直接读 stratified subset。`.gitignore` 不先准备好会导致 Wave 3 写入 anchor JSON 时被默认规则忽略，无法 commit。

Output: 4 个文件，0 行新外部依赖，全部基于 stdlib + 已有 pyyaml。
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
@evolution/core/config.py
@.gitignore
@./CLAUDE.md

<interfaces>
<!-- Phase 13 max_cost_usd field + override chain (1:1 template for Phase 20). -->

From evolution/core/config.py lines 57-59 (field declaration):
```python
# Cost cap for GEPA compile + eval (D-13 / folded todo 2026-05-07-max-cost-usd-and-reflection-model.md)
# USD; enforced by evolution/core/cost_tracker.py. Set <= 0 to disable (not recommended).
max_cost_usd: float = 20.0
```

From evolution/core/config.py lines 122-134 (YAML override pattern):
```python
# Phase 13: max_cost_usd is a top-level yaml key
if data.get("max_cost_usd") is not None:
    try:
        config.max_cost_usd = float(data["max_cost_usd"])
    except (TypeError, ValueError):
        sys.stderr.write(
            f"⚠️  evolution.yaml max_cost_usd="
            f"{data['max_cost_usd']!r} is not a number; "
            f"falling back to default {config.max_cost_usd}.\n"
        )
```

From evolution/core/config.py lines 151-161 (env override pattern):
```python
env_cost = os.getenv("EVOLUTION_MAX_COST_USD")
if env_cost:
    try:
        config.max_cost_usd = float(env_cost)
    except ValueError:
        sys.stderr.write(
            f"⚠️  EVOLUTION_MAX_COST_USD={env_cost!r} is not a "
            f"number; keeping previous value "
            f"{config.max_cost_usd}.\n"
        )
```

From evolution/core/config.py lines 179-190 (CLI override pattern):
```python
if overrides.get("max_cost_usd") is not None:
    try:
        config.max_cost_usd = float(overrides["max_cost_usd"])
    except (TypeError, ValueError):
        sys.stderr.write(
            f"⚠️  max_cost_usd override="
            f"{overrides['max_cost_usd']!r} is not a number; "
            f"keeping previous value {config.max_cost_usd}.\n"
        )
```

From .gitignore lines 16-23 (Phase 18 git exception pattern):
```gitignore
# Generated eval datasets (local, not shared)
datasets/**/*.jsonl
datasets/**/*.json
!datasets/.gitkeep
# Phase 18: drift calibration assets are stable evaluation artifacts (golden-set-like),
# tracked in git so threshold derivation is reproducible across machines / recals.
!datasets/prompts/drift_calibration.jsonl
!datasets/prompts/drift_thresholds.json
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add 4 benchmark config fields + YAML/env/CLI override chain in evolution/core/config.py</name>
  <files>evolution/core/config.py</files>
  <read_first>
    - evolution/core/config.py (lines 1-220 entire file — to understand the full override-chain anchoring and the existing 4-block pattern for max_cost_usd at lines 57-59, 122-134, 151-161, 179-190)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 6 "evolution/core/config.py (MODIFY)" — Adaptation Delta lists exact field set
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §D-16 (dual-track budget) + §D-17 (per-task cost estimate) + §D-03 (3-run) + §D-11 (heartbeat) — decision sources
    - ./CLAUDE.md — naming conventions (snake_case fields, indent 4 spaces, no formatter; project-specific Python style)
  </read_first>
  <action>
    Perform 4 surgical Edit operations on `evolution/core/config.py`. Each new field follows the exact 4-block structure of `max_cost_usd` (declaration / YAML / env / CLI). After each edit verify with `.venv/bin/python -c "from evolution.core.config import EvolutionConfig; c = EvolutionConfig(); print(c.benchmark_max_cost_usd)"`.

    **Edit 1 — Add 4 dataclass field declarations.** Locate the `max_cost_usd: float = 20.0` line (~line 59). INSERT after the trailing comment block / blank line, BEFORE the next field group `# Eval dataset`. Use 4-space indent (dataclass field level):

    ```python
        # Phase 20 D-16: dual-track benchmark cost cap (independent from GEPA max_cost_usd).
        # Enforced by a SECOND CostTracker instance in evolve_prompt_sections step 10.5
        # and build_tblite_calibration; NOT shared with optimization tracker (D-16 explicit).
        benchmark_max_cost_usd: float = 50.0

        # Phase 20 D-17: per-task LLM/Modal cost estimate for Pre-flight Watermark check.
        # build_tblite_calibration measures this on first run and persists into
        # datasets/prompts/tblite_anchor.json as the source-of-truth value;
        # the EvolutionConfig default is the bootstrap fallback.
        tblite_estimated_cost_per_task_usd: float = 0.4

        # Phase 20 D-03: TBLite 3-run median-of-N for the benchmark gate.
        # ONLY at the final gate (out of GEPA loop). Lowering to 1 disables
        # the conservative stdev rule and is intended for fast local debugging
        # only — production calibration / production gates must keep 3.
        benchmark_runs: int = 3

        # Phase 20 D-11: subprocess heartbeat detection — seconds without new
        # stdout line before TBLiteRunner increments hang_count. hang_count >= 3
        # triggers SIGTERM. Lower for short-task benchmarks; raise for Modal cold
        # starts. Refer to PATTERNS §File 2 Async Stream Pipe pattern.
        benchmark_heartbeat_seconds: int = 60
    ```

    **Edit 2 — Add 4 YAML override blocks.** Locate the YAML block for `max_cost_usd` (lines ~122-134). INSERT AFTER its closing `)` line (the `sys.stderr.write(...)` line that ends the except branch), BEFORE the next ` # ── Environment variable overrides ─────` separator comment. Indent must MATCH the surrounding YAML override block (8 spaces relative to function body — i.e. inside the `if yaml_path.exists():` body):

    ```python
            # Phase 20 D-16: benchmark_max_cost_usd top-level yaml key
            if data.get("benchmark_max_cost_usd") is not None:
                try:
                    config.benchmark_max_cost_usd = float(data["benchmark_max_cost_usd"])
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  evolution.yaml benchmark_max_cost_usd="
                        f"{data['benchmark_max_cost_usd']!r} is not a number; "
                        f"falling back to default {config.benchmark_max_cost_usd}.\n"
                    )
            # Phase 20 D-17: tblite_estimated_cost_per_task_usd top-level yaml key
            if data.get("tblite_estimated_cost_per_task_usd") is not None:
                try:
                    config.tblite_estimated_cost_per_task_usd = float(
                        data["tblite_estimated_cost_per_task_usd"]
                    )
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  evolution.yaml tblite_estimated_cost_per_task_usd="
                        f"{data['tblite_estimated_cost_per_task_usd']!r} is not a number; "
                        f"falling back to default {config.tblite_estimated_cost_per_task_usd}.\n"
                    )
            # Phase 20 D-03: benchmark_runs top-level yaml key
            if data.get("benchmark_runs") is not None:
                try:
                    config.benchmark_runs = int(data["benchmark_runs"])
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  evolution.yaml benchmark_runs="
                        f"{data['benchmark_runs']!r} is not an int; "
                        f"falling back to default {config.benchmark_runs}.\n"
                    )
            # Phase 20 D-11: benchmark_heartbeat_seconds top-level yaml key
            if data.get("benchmark_heartbeat_seconds") is not None:
                try:
                    config.benchmark_heartbeat_seconds = int(
                        data["benchmark_heartbeat_seconds"]
                    )
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  evolution.yaml benchmark_heartbeat_seconds="
                        f"{data['benchmark_heartbeat_seconds']!r} is not an int; "
                        f"falling back to default {config.benchmark_heartbeat_seconds}.\n"
                    )
    ```

    **Edit 3 — Add 4 env override blocks.** Locate `env_cost = os.getenv("EVOLUTION_MAX_COST_USD")` (~line 151) and its `try/except` block (ends ~line 161). INSERT AFTER the end of that try/except, BEFORE the next ` # ── CLI overrides ───` separator comment. Indent at 8 spaces (inside `load()` function body):

    ```python
            # Phase 20 D-16: EVOLUTION_BENCHMARK_MAX_COST_USD env override
            env_bench_cost = os.getenv("EVOLUTION_BENCHMARK_MAX_COST_USD")
            if env_bench_cost:
                try:
                    config.benchmark_max_cost_usd = float(env_bench_cost)
                except ValueError:
                    sys.stderr.write(
                        f"⚠️  EVOLUTION_BENCHMARK_MAX_COST_USD={env_bench_cost!r} is not a "
                        f"number; keeping previous value "
                        f"{config.benchmark_max_cost_usd}.\n"
                    )
            # Phase 20 D-17: EVOLUTION_TBLITE_COST_PER_TASK_USD env override
            env_tblite_cost = os.getenv("EVOLUTION_TBLITE_COST_PER_TASK_USD")
            if env_tblite_cost:
                try:
                    config.tblite_estimated_cost_per_task_usd = float(env_tblite_cost)
                except ValueError:
                    sys.stderr.write(
                        f"⚠️  EVOLUTION_TBLITE_COST_PER_TASK_USD={env_tblite_cost!r} is "
                        f"not a number; keeping previous value "
                        f"{config.tblite_estimated_cost_per_task_usd}.\n"
                    )
            # Phase 20 D-03: EVOLUTION_BENCHMARK_RUNS env override
            env_runs = os.getenv("EVOLUTION_BENCHMARK_RUNS")
            if env_runs:
                try:
                    config.benchmark_runs = int(env_runs)
                except ValueError:
                    sys.stderr.write(
                        f"⚠️  EVOLUTION_BENCHMARK_RUNS={env_runs!r} is not an int; "
                        f"keeping previous value {config.benchmark_runs}.\n"
                    )
            # Phase 20 D-11: EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS env override
            env_hb = os.getenv("EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS")
            if env_hb:
                try:
                    config.benchmark_heartbeat_seconds = int(env_hb)
                except ValueError:
                    sys.stderr.write(
                        f"⚠️  EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS={env_hb!r} is not an "
                        f"int; keeping previous value "
                        f"{config.benchmark_heartbeat_seconds}.\n"
                    )
    ```

    **Edit 4 — Add 4 CLI override blocks.** Locate the existing `max_cost_usd` CLI override (~line 179-190). INSERT AFTER its closing `)` line, BEFORE the ` # ── Literal-key warning ───` separator (or whatever block currently follows). Indent at 8 spaces:

    ```python
            # Phase 20 D-16: benchmark_max_cost_usd CLI override
            if overrides.get("benchmark_max_cost_usd") is not None:
                try:
                    config.benchmark_max_cost_usd = float(overrides["benchmark_max_cost_usd"])
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  benchmark_max_cost_usd override="
                        f"{overrides['benchmark_max_cost_usd']!r} is not a number; "
                        f"keeping previous value {config.benchmark_max_cost_usd}.\n"
                    )
            # Phase 20 D-17: tblite_estimated_cost_per_task_usd CLI override
            if overrides.get("tblite_estimated_cost_per_task_usd") is not None:
                try:
                    config.tblite_estimated_cost_per_task_usd = float(
                        overrides["tblite_estimated_cost_per_task_usd"]
                    )
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  tblite_estimated_cost_per_task_usd override="
                        f"{overrides['tblite_estimated_cost_per_task_usd']!r} is not a "
                        f"number; keeping previous value "
                        f"{config.tblite_estimated_cost_per_task_usd}.\n"
                    )
            # Phase 20 D-03: benchmark_runs CLI override
            if overrides.get("benchmark_runs") is not None:
                try:
                    config.benchmark_runs = int(overrides["benchmark_runs"])
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  benchmark_runs override={overrides['benchmark_runs']!r} is "
                        f"not an int; keeping previous value {config.benchmark_runs}.\n"
                    )
            # Phase 20 D-11: benchmark_heartbeat_seconds CLI override
            if overrides.get("benchmark_heartbeat_seconds") is not None:
                try:
                    config.benchmark_heartbeat_seconds = int(
                        overrides["benchmark_heartbeat_seconds"]
                    )
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  benchmark_heartbeat_seconds override="
                        f"{overrides['benchmark_heartbeat_seconds']!r} is not an int; "
                        f"keeping previous value {config.benchmark_heartbeat_seconds}.\n"
                    )
    ```

    Implements: D-16 (dual-track budget), D-17 (Watermark cost estimate), D-03 (3-run averaging), D-11 (heartbeat). Per PATTERNS §File 6, the Phase 13 `max_cost_usd` 4-block structure is the exact 1:1 template — only the field names and env-var prefixes change.
  </action>
  <verify>
    <automated>.venv/bin/python -c "from evolution.core.config import EvolutionConfig; c = EvolutionConfig(); assert c.benchmark_max_cost_usd == 50.0, f'benchmark_max_cost_usd default wrong: {c.benchmark_max_cost_usd}'; assert c.tblite_estimated_cost_per_task_usd == 0.4, f'tblite_estimated_cost_per_task_usd default wrong: {c.tblite_estimated_cost_per_task_usd}'; assert c.benchmark_runs == 3, f'benchmark_runs default wrong: {c.benchmark_runs}'; assert c.benchmark_heartbeat_seconds == 60, f'benchmark_heartbeat_seconds default wrong: {c.benchmark_heartbeat_seconds}'; print('OK defaults')" && EVOLUTION_BENCHMARK_MAX_COST_USD=99.5 .venv/bin/python -c "from evolution.core.config import EvolutionConfig; c = EvolutionConfig.load(); assert c.benchmark_max_cost_usd == 99.5, f'env override failed: {c.benchmark_max_cost_usd}'; print('OK env override')" && .venv/bin/python -c "from evolution.core.config import EvolutionConfig; c = EvolutionConfig.load(benchmark_runs=5, tblite_estimated_cost_per_task_usd=0.7); assert c.benchmark_runs == 5 and abs(c.tblite_estimated_cost_per_task_usd - 0.7) < 1e-9, f'CLI override failed: runs={c.benchmark_runs} cost={c.tblite_estimated_cost_per_task_usd}'; print('OK CLI override')" && grep -v '^#' evolution/core/config.py | grep -c 'benchmark_max_cost_usd' | awk '{ if ($1 < 4) { print "FAIL: benchmark_max_cost_usd appears only " $1 " times (need >=4: declaration + YAML + env + CLI)"; exit 1 } else { print "OK: 4-block override chain present" } }' && grep -v '^#' evolution/core/config.py | grep -c 'tblite_estimated_cost_per_task_usd' | awk '{ if ($1 < 4) { print "FAIL: tblite_estimated_cost_per_task_usd appears only " $1 " times"; exit 1 } else { print "OK" } }' && grep -v '^#' evolution/core/config.py | grep -c 'benchmark_runs' | awk '{ if ($1 < 4) { print "FAIL: benchmark_runs appears only " $1 " times"; exit 1 } else { print "OK" } }' && grep -v '^#' evolution/core/config.py | grep -c 'benchmark_heartbeat_seconds' | awk '{ if ($1 < 4) { print "FAIL: benchmark_heartbeat_seconds appears only " $1 " times"; exit 1 } else { print "OK" } }'</automated>
  </verify>
  <acceptance_criteria>
    - `EvolutionConfig()` constructed with no args has `benchmark_max_cost_usd == 50.0`, `tblite_estimated_cost_per_task_usd == 0.4`, `benchmark_runs == 3`, `benchmark_heartbeat_seconds == 60`.
    - `EVOLUTION_BENCHMARK_MAX_COST_USD=99.5 python -c "EvolutionConfig.load()"` returns `benchmark_max_cost_usd == 99.5` (env override works).
    - `EvolutionConfig.load(benchmark_runs=5)` returns `benchmark_runs == 5` (CLI override works).
    - `grep -v '^#' evolution/core/config.py | grep -c 'benchmark_max_cost_usd'` >= 4 (declaration + YAML + env + CLI references; comments excluded to avoid self-invalidating grep gate).
    - `grep -v '^#' evolution/core/config.py | grep -c 'tblite_estimated_cost_per_task_usd'` >= 4.
    - `grep -c 'EVOLUTION_BENCHMARK_MAX_COST_USD' evolution/core/config.py` >= 1.
    - `grep -c 'EVOLUTION_TBLITE_COST_PER_TASK_USD' evolution/core/config.py` >= 1.
    - `grep -c 'EVOLUTION_BENCHMARK_RUNS' evolution/core/config.py` >= 1.
    - `grep -c 'EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS' evolution/core/config.py` >= 1.
  </acceptance_criteria>
  <done>
    - 4 new dataclass fields added with correct defaults
    - YAML override block exists for all 4 fields
    - env override block exists for all 4 fields with EVOLUTION_BENCHMARK_* prefix
    - CLI override block exists for all 4 fields
    - All overrides emit `⚠️` warnings on malformed input (matching `max_cost_usd` pattern)
    - `.venv/bin/python -c "from evolution.core.config import EvolutionConfig; EvolutionConfig.load()"` exits 0
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Create evolution/benchmarks/ package with lazy-import-guard __init__.py</name>
  <files>evolution/benchmarks/__init__.py</files>
  <read_first>
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 1 (entire section — content + Adaptation Delta forbidding eager submodule imports)
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §Decisions/Claude's Discretion item 1 (lazy import guard rationale: hermes-agent or huggingface_hub unreachable → --benchmark=none path must still work)
    - evolution/prompts/__init__.py (existing sibling package init for indent + docstring style reference)
  </read_first>
  <action>
    Create the directory `evolution/benchmarks/` (if not present) and write `evolution/benchmarks/__init__.py` with ONLY a module docstring — NO eager submodule imports.

    Exact file contents (verbatim):

    ```python
    """Phase 20: Benchmark-gated validation for evolved prompt artifacts.

    Lazy-import guard (Phase 20 D-Discretion-1): submodules
    (tblite_runner / benchmark_gate / build_tblite_calibration) are NOT
    auto-imported here. Callers must explicitly:

        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
        from evolution.benchmarks.tblite_runner import TBLiteRunner

    Rationale: hermes-agent or huggingface_hub may be unreachable on a
    given dev machine; `evolve_prompt_sections --benchmark=none` (the
    default) MUST keep working without surfacing ImportError from the
    evolution package's __init__ chain. Eager imports here would cascade
    failure into every CLI entrypoint that touches evolution.*.
    """
    ```

    Use the Write tool to create the file. Do NOT add any `from .X import Y` statements. Do NOT add `__all__`. Do NOT add `__version__`.

    Implements: PATTERNS §File 1 — sibling of `evolution/code/__init__.py` and `evolution/monitor/__init__.py` (Phase 21/22 placeholder packages) but with a docstring documenting the lazy-import decision. CONTEXT §Discretion item 1.
  </action>
  <verify>
    <automated>test -f evolution/benchmarks/__init__.py || (echo "FAIL: file not created"; exit 1) && .venv/bin/python -c "import evolution.benchmarks; print('OK import')" && .venv/bin/python -c "import evolution.benchmarks; assert evolution.benchmarks.__doc__ is not None, 'docstring missing'; assert 'Lazy-import guard' in evolution.benchmarks.__doc__, 'docstring lacks lazy-import-guard mention'; print('OK docstring')" && grep -cE '^from \.' evolution/benchmarks/__init__.py | awk '{ if ($1 != 0) { print "FAIL: __init__.py has " $1 " eager submodule imports (D-Discretion-1 violation — must be 0)"; exit 1 } else { print "OK: no eager submodule imports" } }' && grep -cE '^import evolution\.benchmarks\.' evolution/benchmarks/__init__.py | awk '{ if ($1 != 0) { print "FAIL: __init__.py has eager evolution.benchmarks.* import"; exit 1 } else { print "OK" } }'</automated>
  </verify>
  <acceptance_criteria>
    - File `evolution/benchmarks/__init__.py` exists.
    - `python -c "import evolution.benchmarks"` exits 0.
    - `evolution.benchmarks.__doc__` is non-None and contains the literal substring "Lazy-import guard".
    - `grep -cE '^from \.' evolution/benchmarks/__init__.py` returns 0 (no eager relative imports).
    - `grep -cE '^import evolution\.benchmarks\.' evolution/benchmarks/__init__.py` returns 0.
    - File size is small (< 1 KB; pure docstring).
  </acceptance_criteria>
  <done>
    - evolution/benchmarks/ directory exists and is importable
    - __init__.py contains only a docstring documenting lazy-import policy
    - No eager submodule imports (verified by grep)
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Create datasets/prompts/tblite_stratified_subset.json placeholder (tier-explicit object schema) + extend .gitignore for tblite + logs/</name>
  <files>
    - datasets/prompts/tblite_stratified_subset.json
    - .gitignore
  </files>
  <read_first>
    - .gitignore (entire file — see existing Phase 18 `!datasets/prompts/drift_*` exception block at lines 16-23 + `output/` pattern at line 30)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 9 (tblite_stratified_subset.json schema) + §File 10 (.gitignore mod with exact insert deltas)
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §D-05 (stratified_30 distribution easy:12/medium:8/hard:7/extreme:3=30) + §Specifics (STRATIFIED_30 dict + seed=42 convention) + §D-08 (logs/regression.jsonl target)
  </read_first>
  <action>
    Two file mutations. Both must complete; the order is: (a) create stratified subset JSON, (b) modify .gitignore. After both, run `git status` to confirm the new JSON appears as tracked.

    **W-7 revision (2026-05-19)**: `task_filter` is now a list of `{"name": str, "tier": str}` OBJECTS, NOT a flat string list. This eliminates the brittle "tasks are sorted easy→medium→hard→extreme by convention" contract that Plan 06's `--benchmark-tier` slicing previously relied on. Every consumer (Plan 02 `_validate_task_filter`, Plan 04 calibration, Plan 06 tier filter) reads `item.tier` directly. The `per_tier_counts` dict remains for fast schema validation but is derived from `task_filter` membership, not the source of truth.

    **Step A — Create `datasets/prompts/tblite_stratified_subset.json`.** Use the Write tool. Exact content (Wave-1 PLACEHOLDER — Wave 4 calibration overwrites `task_filter` with real TBLite task names; schema is final):

    ```json
    {
      "seed": 42,
      "per_tier_counts": {
        "easy": 12,
        "medium": 8,
        "hard": 7,
        "extreme": 3
      },
      "task_filter": [
        {"name": "tblite-easy-01", "tier": "easy"},
        {"name": "tblite-easy-02", "tier": "easy"},
        {"name": "tblite-easy-03", "tier": "easy"},
        {"name": "tblite-easy-04", "tier": "easy"},
        {"name": "tblite-easy-05", "tier": "easy"},
        {"name": "tblite-easy-06", "tier": "easy"},
        {"name": "tblite-easy-07", "tier": "easy"},
        {"name": "tblite-easy-08", "tier": "easy"},
        {"name": "tblite-easy-09", "tier": "easy"},
        {"name": "tblite-easy-10", "tier": "easy"},
        {"name": "tblite-easy-11", "tier": "easy"},
        {"name": "tblite-easy-12", "tier": "easy"},
        {"name": "tblite-medium-01", "tier": "medium"},
        {"name": "tblite-medium-02", "tier": "medium"},
        {"name": "tblite-medium-03", "tier": "medium"},
        {"name": "tblite-medium-04", "tier": "medium"},
        {"name": "tblite-medium-05", "tier": "medium"},
        {"name": "tblite-medium-06", "tier": "medium"},
        {"name": "tblite-medium-07", "tier": "medium"},
        {"name": "tblite-medium-08", "tier": "medium"},
        {"name": "tblite-hard-01", "tier": "hard"},
        {"name": "tblite-hard-02", "tier": "hard"},
        {"name": "tblite-hard-03", "tier": "hard"},
        {"name": "tblite-hard-04", "tier": "hard"},
        {"name": "tblite-hard-05", "tier": "hard"},
        {"name": "tblite-hard-06", "tier": "hard"},
        {"name": "tblite-hard-07", "tier": "hard"},
        {"name": "tblite-extreme-01", "tier": "extreme"},
        {"name": "tblite-extreme-02", "tier": "extreme"},
        {"name": "tblite-extreme-03", "tier": "extreme"}
      ],
      "source": "NousResearch/openthoughts-tblite",
      "generated_timestamp": "2026-05-19T00:00:00Z",
      "_meta": {
        "phase": "20",
        "wave": 1,
        "placeholder": true,
        "schema_version": "2",
        "schema_note": "task_filter is list of {name, tier} objects (W-7 revision 2026-05-19). Consumers select tasks by tier field, NOT by per_tier_counts index slice.",
        "note": "Wave 1 placeholder task names. Wave 4 (build_tblite_calibration) overwrites task_filter[].name with real TBLite task names sampled per-tier from the HuggingFace dataset; tier field stays as the per-row label. Schema is final; only string contents change."
      }
    }
    ```

    Verify: `python -c "import json; d = json.load(open('datasets/prompts/tblite_stratified_subset.json')); assert d['seed']==42; assert sum(d['per_tier_counts'].values())==30; assert len(d['task_filter'])==30; assert all(isinstance(t, dict) and 'name' in t and 'tier' in t for t in d['task_filter']), 'W-7: every task_filter item must be {name, tier} dict'; tier_count = {}; [tier_count.setdefault(t['tier'], 0) or tier_count.update({t['tier']: tier_count.get(t['tier'], 0)+1}) for t in d['task_filter']]; assert tier_count == d['per_tier_counts'], f'tier counts mismatch: {tier_count} vs {d[\"per_tier_counts\"]}'; print('OK')"`

    **Step B — Modify `.gitignore`** (use the Edit tool — read it first to confirm exact line numbers, then 2 Edit operations):

    **Edit B-1:** Locate line `!datasets/prompts/drift_thresholds.json` (~line 23). Insert AFTER it (BEFORE the blank line that separates from `# Evolution snapshots`):

    ```gitignore
    # Phase 20: TBLite benchmark anchor + stratified subset (golden-set-like, git-tracked).
    # Same rationale as Phase 18 drift artifacts: stable evaluation references must be
    # reproducible across machines / re-calibrations.
    !datasets/prompts/tblite_anchor.json
    !datasets/prompts/tblite_stratified_subset.json
    ```

    **Edit B-2:** Append to the very END of `.gitignore` (after the last existing line `*.swo`):

    ```gitignore

    # Phase 20 D-08: Soft-Rollback regression audit log. Lives at project root,
    # never committed. Each row is one async-full-verify regression event.
    logs/
    ```

    Verify ordering — the `.gitignore` is order-sensitive: `!` exception lines MUST appear AFTER the `datasets/**/*.json` ignore pattern at line 18 (already true since we insert at ~line 24).

    Implements: PATTERNS §File 9 (schema; W-7 revision tier-explicit object form) + §File 10 (gitignore deltas). CONTEXT §D-05 (stratified subset distribution) + §D-08 (logs/ target) + §D-CAL-02 mirror (Phase 18 git exception pattern).
  </action>
  <verify>
    <automated>test -f datasets/prompts/tblite_stratified_subset.json || (echo "FAIL: subset JSON not created"; exit 1) && .venv/bin/python -c "import json; d=json.load(open('datasets/prompts/tblite_stratified_subset.json')); assert d['seed']==42, f'seed wrong: {d[\"seed\"]}'; assert d['per_tier_counts']=={'easy':12,'medium':8,'hard':7,'extreme':3}, f'per_tier_counts wrong: {d[\"per_tier_counts\"]}'; assert sum(d['per_tier_counts'].values())==30, 'tier counts must sum to 30'; assert len(d['task_filter'])==30, f'task_filter len wrong: {len(d[\"task_filter\"])}'; assert all(isinstance(t, dict) and 'name' in t and 'tier' in t for t in d['task_filter']), 'W-7 schema: every item must be {name, tier} dict'; tc = {}; \nfor t in d['task_filter']: tc[t['tier']] = tc.get(t['tier'], 0) + 1\nassert tc == d['per_tier_counts'], f'tier-count consistency fail: {tc} vs {d[\"per_tier_counts\"]}'; assert d['source']=='NousResearch/openthoughts-tblite'; print('OK JSON schema W-7 tier-explicit')" && grep -c '!datasets/prompts/tblite_anchor.json' .gitignore | awk '{ if ($1 < 1) { print "FAIL: tblite_anchor.json git exception missing"; exit 1 } else { print "OK: anchor exception present" } }' && grep -c '!datasets/prompts/tblite_stratified_subset.json' .gitignore | awk '{ if ($1 < 1) { print "FAIL: tblite_stratified_subset.json git exception missing"; exit 1 } else { print "OK: subset exception present" } }' && grep -nE '^logs/$' .gitignore | wc -l | awk '{ if ($1 < 1) { print "FAIL: logs/ ignore missing"; exit 1 } else { print "OK: logs/ ignore present" } }' && grep -nE '^!datasets/prompts/tblite_' .gitignore | awk -F: '{ print $1 }' | sort -n | head -1 | awk '{ if ($1 < 24) { print "FAIL: tblite exceptions appear at line " $1 " — must be AFTER datasets/**/*.json at line ~18"; exit 1 } else { print "OK: ordering correct (lines >= 24)" } }' && git check-ignore -v datasets/prompts/tblite_stratified_subset.json 2>&1 | grep -q '!datasets/prompts/tblite_stratified_subset.json' && echo "OK: stratified subset is git-trackable" || (git check-ignore datasets/prompts/tblite_stratified_subset.json && echo "FAIL: stratified subset is still being ignored" && exit 1 || echo "OK: file not ignored (good)")</automated>
  </verify>
  <acceptance_criteria>
    - `datasets/prompts/tblite_stratified_subset.json` exists and is valid JSON with `seed=42`, `per_tier_counts={easy:12,medium:8,hard:7,extreme:3}` summing to 30, `task_filter` array of length 30 where EVERY element is a `{name: str, tier: str}` dict, `source="NousResearch/openthoughts-tblite"`.
    - Tier counts derived from `task_filter[].tier` match `per_tier_counts` exactly.
    - `_meta.schema_version == "2"` (W-7 revision marker).
    - `.gitignore` contains `!datasets/prompts/tblite_anchor.json` exception.
    - `.gitignore` contains `!datasets/prompts/tblite_stratified_subset.json` exception.
    - `.gitignore` contains a `logs/` line (D-08 audit log dir).
    - The tblite exception lines appear AFTER the `datasets/**/*.json` rule (order matters for gitignore).
    - `git check-ignore datasets/prompts/tblite_stratified_subset.json` does NOT match (file is trackable).
  </acceptance_criteria>
  <done>
    - tblite_stratified_subset.json created with W-7 tier-explicit object schema, 30 placeholders, `_meta.placeholder: true`, `_meta.schema_version: "2"`
    - .gitignore has 2 new !datasets/prompts/tblite_* exceptions in the right order
    - .gitignore has logs/ ignore
    - `git status` shows the new JSON as a tracked addition
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| evolution.yaml → EvolutionConfig | User-writable YAML on local disk. Already covered by Phase 13 literal-key warning at line ~196 of config.py. Phase 20 fields inherit the same trust posture — float/int coercion with `⚠️` fallback prevents corrupt values from silently disabling cost gates. |
| Environment variables → EvolutionConfig | Process env; trusted at the user-shell level. EVOLUTION_* keys are read-only; no command construction or eval. |
| CLI overrides dict → EvolutionConfig | Passed programmatically by callers; Click already validates types at parse time. |
| datasets/prompts/tblite_stratified_subset.json → BenchmarkGate (Wave 2) | Git-tracked, normally append-only. Wave 2 will validate `per_tier_counts` schema + W-7 tier-explicit object items on load. |
| .gitignore changes → repo hygiene | Local change; no remote interaction. Phase 20 audit log path (`logs/`) deliberately untracked to prevent secret leakage from regression rationales. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-20-01 | T (Tampering) | evolution.yaml benchmark_max_cost_usd field | mitigate | Same `try/except (TypeError, ValueError)` + `⚠️` warn pattern Phase 13 already uses for max_cost_usd. Malformed value (e.g. "1000.0; rm -rf /") triggers float() ValueError → keep default 50.0 + warn. No string-format interpolation into shell. |
| T-20-02 | I (Information disclosure) | logs/regression.jsonl (Soft-Rollback audit) | mitigate | `logs/` added to .gitignore in this task. Wave 5 will apply Phase 14 SECRET_PATTERNS filter from external_importers.py:47-119 BEFORE appending each row. Wave 1 just establishes the directory ignore. |
| T-20-03 | T (Tampering) | datasets/prompts/tblite_stratified_subset.json | accept | Git-tracked; corruption visible in diff review. `_meta.placeholder: true` field signals Wave 4 that current content is bootstrap-only. No runtime trust impact in Wave 1 (Wave 2 BenchmarkGate validates schema at load time). W-7 tier-explicit schema makes per-row tier explicit so corruption affecting tier-count consistency is detected by Plan 02/03 schema validators. |
| T-20-04 | D (Denial of service) | EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS = 0 (or negative) | accept | int() coercion succeeds for "0", "-1" — would disable heartbeat detection. Wave 2 TBLiteRunner constructor must clamp to `max(1, value)` (deferred to that task's threat model). Wave 1 only stores the int. |
</threat_model>

<verification>
- 4 new fields exist on `EvolutionConfig` with correct defaults: `benchmark_max_cost_usd=50.0`, `tblite_estimated_cost_per_task_usd=0.4`, `benchmark_runs=3`, `benchmark_heartbeat_seconds=60`.
- YAML/env/CLI override chain works (verified by `EVOLUTION_BENCHMARK_MAX_COST_USD=99.5 python -c ...`).
- `import evolution.benchmarks` succeeds with no eager submodule import.
- `datasets/prompts/tblite_stratified_subset.json` parses with 30 tier-explicit objects across 4 tiers per D-05 (W-7 schema).
- `.gitignore` exempts both new artifacts AND adds `logs/` ignore.
- `pytest tests/ --collect-only` still succeeds (no test regressions from config field additions).
</verification>

<success_criteria>
- ROADMAP SC #1 (`--benchmark` flag) partially covered: config plumbing prerequisite met.
- ROADMAP SC #2 (configurable pass threshold): `benchmark_runs` + `benchmark_max_cost_usd` + `benchmark_heartbeat_seconds` are now user-configurable via 3-tier override chain.
- D-16 covered: dual-track budget config field exists and is independent of `max_cost_usd`.
- D-17 covered: per-task cost estimate config field exists; Wave 4 calibration will measure-and-write the real value.
- D-03 + D-11 covered: runs/heartbeat are no longer hardcoded.
- D-08 + D-CAL-02 + Discretion-1 covered: `.gitignore` exemptions ready for Wave 4 anchor JSON, `evolution/benchmarks/` is a lazy-import-guarded package.
- W-7 covered: tier-explicit `task_filter` schema removes the "implicit order" contract that Plan 06's CSV filter previously depended on.
- `pytest tests/ --collect-only` exits 0; no existing test regressions.
</success_criteria>

<output>
After completion, create `.planning/phases/20-benchmark-gated-validation/20-01-config-scaffolding-SUMMARY.md` covering:
- Diff stats: lines added per file (config.py +~140, __init__.py +~16, stratified_subset.json +~70 (W-7 expanded), .gitignore +~9).
- Confirmation that all 4 fields appear at least 4 times (comment-excluded) in config.py (declaration + YAML + env + CLI).
- Confirmation that `git check-ignore datasets/prompts/tblite_stratified_subset.json` does NOT match.
- Confirmation that `.venv/bin/python -c "import evolution.benchmarks"` exits 0.
- Confirmation that `task_filter` is a list of `{name, tier}` objects and tier-count consistency holds.
</output>

## Revision Log

- 2026-05-19 (W-7): `task_filter` schema changed from flat `list[str]` to `list[{name, tier}]` objects to eliminate Plan 06's brittle "tasks sorted easy→medium→hard→extreme" implicit contract. Added `_meta.schema_version: "2"` marker. Updated verify block, acceptance criteria, must_haves truths, and Plan 02/04/06 must read `item['tier']` rather than index-slicing.
- 2026-05-19 (I-2 partial / self-invalidating-grep prevention): `verify` grep counts for the 4 benchmark fields now use `grep -v '^#' | grep -c` to exclude comment hits — required by planner rule against self-invalidating gates triggered by header prose.
