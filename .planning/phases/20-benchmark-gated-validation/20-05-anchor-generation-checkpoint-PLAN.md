---
phase: 20-benchmark-gated-validation
plan: 05
type: execute
wave: 4
revised_at: 2026-05-19
depends_on:
  - 20-04-build-calibration-cli-PLAN.md
files_modified:
  - datasets/prompts/tblite_stratified_subset.json
  - datasets/prompts/tblite_anchor.json
autonomous: false
requirements:
  - PMPT-V2-03
requirements_addressed:
  - PMPT-V2-03
tags:
  - phase-20
  - benchmark
  - calibration
  - blocking
  - checkpoint
must_haves:
  truths:
    - "datasets/prompts/tblite_stratified_subset.json contains REAL TBLite task names (per_tier_counts unchanged: easy:12/medium:8/hard:7/extreme:3 = 30 tasks, source='NousResearch/openthoughts-tblite', _meta.placeholder set to false, task_filter items remain {name, tier} objects per Plan 01 W-7 schema)"
    - "datasets/prompts/tblite_anchor.json is the output of a LIVE `python -m evolution.benchmarks.build_tblite_calibration` run (NOT a hand-crafted mock — D-13 mandates calibration; 'placeholder' is explicitly forbidden)"
    - "anchor.hermes_agent_commit matches `git rev-parse HEAD` in the current hermes-agent checkout"
    - "anchor.anchor_per_tier has all 4 tiers (easy/medium/hard/extreme) with n>=3 and numeric mean/stdev derived from real subprocess runs"
    - "anchor.dataset_revision_hash is either a hex sha (from HuggingFace) OR 'unknown_v1.0' (documented fail-open per Plan 04 RA5 — acceptable when HF API is transiently unreachable, but NOT a substitute for live calibration)"
    - "anchor.tblite_estimated_cost_per_task_usd is the MEASURED value from the live run (likely 0.3-0.6)"
    - "If live calibration is INFEASIBLE at execution time (no Modal access / no OpenRouter / no $36 budget), the executor HALTS Phase 20 via the 'anchor-blocked' resume signal — DOES NOT commit a mock fallback. Phase 20 cannot ship without a real anchor (B-1 enforcement)."
  artifacts:
    - path: datasets/prompts/tblite_stratified_subset.json
      provides: "30 real TBLite task names sampled per-tier from HuggingFace dataset (W-7 schema: {name, tier} objects)"
      contains: "task_filter"
    - path: datasets/prompts/tblite_anchor.json
      provides: "Per-tier baseline mean+stdev from a LIVE calibration run — REQUIRED before BenchmarkGate is usable; NO mock fallback permitted (B-1 / D-13)"
      contains: "anchor_per_tier"
      min_lines: 30
  key_links:
    - from: datasets/prompts/tblite_anchor.json
      to: evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate
      via: "json.loads(path.read_text()) -> constructor validates schema; _check_anchor_existence verifies hermes_agent_commit match"
      pattern: "anchor_per_tier"
    - from: datasets/prompts/tblite_stratified_subset.json
      to: TBLiteRunner.run(task_filter=...)
      via: "Plan 04 / Plan 06 extract [item['name'] for item in subset['task_filter']] BEFORE passing to TBLiteRunner.run; _validate_task_filter still accepts list[str] (W-7 schema)"
      pattern: "task_filter"
---

<objective>
Wave 4 — **BLOCKING** human-supervised step that produces the LIVE anchor and real task whitelist via Plan 04's calibration CLI.

**B-1 enforcement (2026-05-19 revision):** Earlier drafts of this plan offered a Path B "mock anchor with audit trail" alternative. That option is REMOVED. CONTEXT D-13 mandates that "Phase 20 工期内必须完成 calibration (同 Phase 18 D-CAL-05 思路, 不允许 placeholder)" — a mock anchor IS a placeholder, regardless of `_meta.tier="mock"` honesty markers. Live calibration via `python -m evolution.benchmarks.build_tblite_calibration` is the ONLY shippable execution path.

Plan 04 ships the calibration CLI; this plan invokes it against a real hermes-agent + Modal + OpenRouter to produce `datasets/prompts/tblite_anchor.json`. Per D-13 + D-CAL-05 sibling rule, this is **mandatory before Phase 21** — `TBLiteBenchmarkGate._check_anchor_existence` raises `SystemExit(1)` when the anchor is missing or stale, and Plan 06's CLI integration depends on a working anchor for end-to-end smoke validation.

Execution flow (single live path):
1. **Checkpoint A** — Confirm calibration prerequisites are ready: OPENROUTER_API_KEY + MODAL_TOKEN_ID env vars set, clean hermes-agent tree, ~$36 budget approved. If prerequisites are missing → resume-signal "anchor-blocked" → HALT Phase 20.
2. **Checkpoint B** — Replace the Wave-1 placeholder `task_filter` (currently 30 synthetic `tblite-easy-01…` names in `{name, tier}` object form per Plan 01 W-7 schema) with 30 real task names sampled per-tier from the live TBLite dataset.
3. **Checkpoint C** — Run `python -m evolution.benchmarks.build_tblite_calibration --runs 3 --benchmark-max-cost 50.0` against a clean hermes-agent checkout with valid OPENROUTER_API_KEY + MODAL_TOKEN_ID. Spot-check spot anchors (10/30 task IDs valid in HF dataset; per-tier means in plausible Claude Haiku 4.5 reference range).
4. **Task 4** — Schema validation + TBLiteBenchmarkGate constructor smoke + git status verification.

No defensive degraded path exists in this plan. Mock-anchor defensive logging in Plan 06 step 10.5 (yellow warning if `_meta.tier == "mock"` is somehow encountered later, e.g. from a stale archive) is RETAINED as a runtime guard against historical artifacts — but this plan must NOT produce such an artifact under any circumstance.

Output: 2 committed JSON files. NO tracking todo (the "mock anchor → re-calibrate later" obligation no longer exists; live calibration is unconditional).

Purpose: Plan 06's integration tests (`evolve_prompt_sections --benchmark=tblite` end-to-end smoke) need a real anchor. Without this plan, Phase 20 ships an unusable feature OR ships behind a "mock anchor" that silently degrades the gate to a no-op — both unacceptable per D-13.
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
@.planning/phases/18-personality-drift-detection/18-03-SUMMARY.md
@./CLAUDE.md

<interfaces>
<!-- Wave 1 schema (Plan 01 W-7 revision). -->
From datasets/prompts/tblite_stratified_subset.json (Wave 1 placeholder, W-7 tier-explicit schema):
```json
{
  "seed": 42,
  "per_tier_counts": {"easy": 12, "medium": 8, "hard": 7, "extreme": 3},
  "task_filter": [
    {"name": "tblite-easy-01", "tier": "easy"},
    ...
    {"name": "tblite-extreme-03", "tier": "extreme"}
  ],
  "source": "NousResearch/openthoughts-tblite",
  "_meta": {"phase": "20", "wave": 1, "placeholder": true, "schema_version": "2", ...}
}
```

<!-- Wave 3 CLI being invoked here. -->
From evolution/benchmarks/build_tblite_calibration.py:
```bash
python -m evolution.benchmarks.build_tblite_calibration \
    --hermes-repo ~/.hermes/hermes-agent \
    --seed 42 \
    --runs 3 \
    --output-json datasets/prompts/tblite_anchor.json \
    --benchmark-max-cost 50.0
```

<!-- Expected anchor schema (D-CAL-01) -->
```json
{
  "anchor_per_tier": {"easy": {"mean": 0.85, "stdev": 0.02, "n": 3, "scores": [...]}, ...},
  "dataset_revision_hash": "<hf sha or unknown_v1.0>",
  "hermes_agent_commit": "<git HEAD>",
  "stratified_subset_seed": 42,
  "tblite_estimated_cost_per_task_usd": <measured>,
  "calibration_timestamp": "<ISO8601>",
  "calibration_model": "<model name>",
  "tblite_runner_version": "1.0"
}
```

<!-- TBLite reference pass rates from CONTEXT canonical_refs §README -->
TBLite README difficulty distribution (Claude Haiku 4.5 baseline, used only for sanity spot-check; NOT for hand-crafting an anchor):
  Easy:    40 tasks total, ~85% baseline pass rate
  Medium:  26 tasks total, ~70% baseline pass rate
  Hard:    26 tasks total, ~50% baseline pass rate
  Extreme:  8 tasks total, ~30% baseline pass rate
</interfaces>
</context>

<tasks>

<task type="checkpoint:human-action" gate="blocking">
  <name>Checkpoint A: Confirm calibration prerequisites are ready</name>
  <what-built>
    Single-path live calibration requires three operational prerequisites to be present at execution time. This checkpoint asks the developer to verify them BEFORE generating real task names + running the costly subprocess. If any prerequisite is missing, the developer types "anchor-blocked" and Phase 20 HALTS — the planner / orchestrator will surface the gap to the user, who decides whether to acquire budget/credentials or pause Phase 20.

    Prerequisites:
    1. **OPENROUTER_API_KEY env var set + funded.** TBLite invokes OpenRouter for the inference LM (default `openai/gpt-4.1` or `anthropic/claude-opus-4.6` per default.yaml).
    2. **MODAL_TOKEN_ID + MODAL_TOKEN_SECRET env vars set + Modal account active.** TBLite Modal backend runs the per-task sandboxes; without it the subprocess errors out at sandbox boot.
    3. **Budget ~$36 (worst-case) approved.** 30 tasks × 3 runs × ~$0.4/task ≈ $36. The `--benchmark-max-cost 50.0` default leaves $14 headroom.
  </what-built>
  <how-to-verify>
    Run the following from the project root and confirm each line:

    ```bash
    # 1. OPENROUTER
    test -n "$OPENROUTER_API_KEY" && echo "OK: OPENROUTER_API_KEY set (${OPENROUTER_API_KEY:0:6}…)" || echo "MISSING: OPENROUTER_API_KEY"

    # 2. MODAL
    test -n "$MODAL_TOKEN_ID" && test -n "$MODAL_TOKEN_SECRET" && echo "OK: MODAL credentials set" || echo "MISSING: MODAL_TOKEN_ID and/or MODAL_TOKEN_SECRET"

    # 3. hermes-agent clean
    cd ~/.hermes/hermes-agent 2>/dev/null && git status --porcelain | head -5
    # expect empty output

    # 4. Confirm Plan 01 W-7 stratified subset is in place
    cd "$OLDPWD" && python -c "
    import json
    d = json.load(open('datasets/prompts/tblite_stratified_subset.json'))
    assert len(d['task_filter']) == 30
    assert all(isinstance(t, dict) and 'name' in t and 'tier' in t for t in d['task_filter']), 'W-7 schema violation'
    print(f'OK: W-7 subset schema; placeholder={d[\"_meta\"][\"placeholder\"]}')
    "
    ```

    If ALL four prints succeed → type "ready" and proceed to Checkpoint B.
    If ANY prerequisite is MISSING (OPENROUTER unavailable / MODAL unavailable / hermes-agent dirty / budget not approved) → type "anchor-blocked" and HALT.
  </how-to-verify>
  <action>Human verifies all 4 prerequisites listed in how-to-verify. On full success type "ready"; on any missing prerequisite type "anchor-blocked" and HALT (no fallback path exists in this plan per B-1 enforcement).</action>
  <verify>All 4 prerequisite checks print OK before the user types the resume signal.</verify>
  <done>Resume signal received; ready to proceed to live calibration steps.</done>
  <resume-signal>Type "ready" when all 4 prerequisites verified. Type "anchor-blocked" if ANY prerequisite cannot be met (HALTS Phase 20; no mock fallback exists).</resume-signal>
</task>

<task type="checkpoint:human-action" gate="blocking">
  <name>Checkpoint B: Generate real TBLite task names for the stratified subset (W-7 object schema preserved)</name>
  <what-built>The Wave 1 placeholder `task_filter` in `datasets/prompts/tblite_stratified_subset.json` contains 30 synthetic names (`tblite-easy-01`...`tblite-extreme-03`) in W-7 `{name, tier}` object form. This step replaces the `name` field of every object with real TBLite task names sampled per-tier; the `tier` field stays as the per-row label.</what-built>
  <how-to-verify>
    Two ways to obtain real task names — pick one:

    **Method 1 (preferred, via HuggingFace dataset):**
    1. `ls ~/.hermes/hermes-agent/environments/benchmarks/tblite/` to confirm TBLite is checked out.
    2. Open a Python shell and sample deterministically (seed=42 already in the subset JSON):
       ```python
       import json
       import random
       from datasets import load_dataset
       ds = load_dataset("NousResearch/openthoughts-tblite", split="train")
       by_tier = {}
       for row in ds:
           tier = (row.get("category") or row.get("difficulty") or "unknown").lower()
           by_tier.setdefault(tier, []).append(row["task_name"])
       rng = random.Random(42)
       sampled = {}
       for tier, count in [("easy", 12), ("medium", 8), ("hard", 7), ("extreme", 3)]:
           pool = sorted(by_tier[tier])  # determinism
           sampled[tier] = rng.sample(pool, count)
       # Build W-7 tier-explicit task_filter
       task_filter = []
       for tier in ("easy", "medium", "hard", "extreme"):
           for name in sampled[tier]:
               task_filter.append({"name": name, "tier": tier})
       d = json.load(open("datasets/prompts/tblite_stratified_subset.json"))
       d["task_filter"] = task_filter
       d["_meta"]["placeholder"] = False
       d["_meta"]["task_source_method"] = "load_dataset(HF) + random.sample(seed=42)"
       open("datasets/prompts/tblite_stratified_subset.json", "w").write(json.dumps(d, indent=2))
       print("OK: wrote real task names (W-7 schema preserved)")
       ```

    **Method 2 (no HF access, via repo manifest):**
    1. Open `~/.hermes/hermes-agent/environments/benchmarks/tblite/README.md` and locate the task list (or a manifest file inside the repo).
    2. Manually pick 12 easy / 8 medium / 7 hard / 3 extreme task names that look representative (avoid duplicates).
    3. Write the JSON with the same W-7 `{name, tier}` object structure; set `_meta.placeholder` to `false` + add `_meta.task_source_method = "manual_sample_from_README"`.

    **Validation:**
    ```bash
    python -c "
    import json
    d = json.load(open('datasets/prompts/tblite_stratified_subset.json'))
    assert len(d['task_filter']) == 30, f'len={len(d[\"task_filter\"])}'
    assert d['per_tier_counts'] == {'easy': 12, 'medium': 8, 'hard': 7, 'extreme': 3}
    assert all(isinstance(t, dict) and 'name' in t and 'tier' in t for t in d['task_filter']), 'W-7 schema violation'
    tc = {}
    for t in d['task_filter']: tc[t['tier']] = tc.get(t['tier'], 0) + 1
    assert tc == d['per_tier_counts'], f'tier count mismatch: {tc} vs {d[\"per_tier_counts\"]}'
    assert d['_meta']['placeholder'] is False, 'placeholder flag not cleared'
    # Sanity: no Wave-1 synthetic names should remain (unless user explicitly accepted a coincidence)
    synthetic = [t for t in d['task_filter'] if t['name'].startswith(('tblite-easy-', 'tblite-medium-', 'tblite-hard-', 'tblite-extreme-')) and len(t['name']) <= 18]
    if synthetic:
        print(f'WARN: {len(synthetic)} look-like-placeholder names remain — confirm these are real TBLite tasks')
    print('OK validation')
    "
    ```

    Also run the Plan 02 task-name sanitization smoke test:
    ```python
    from evolution.benchmarks.tblite_runner import _validate_task_filter
    import json
    d = json.load(open('datasets/prompts/tblite_stratified_subset.json'))
    names = [t['name'] for t in d['task_filter']]
    _validate_task_filter(names)  # raises on shell-metachar; should NOT raise
    print('OK whitelist')
    ```
  </how-to-verify>
  <action>Human follows Method 1 or Method 2 in the how-to-verify block to replace the Wave-1 placeholder task NAMES in datasets/prompts/tblite_stratified_subset.json with real TBLite task names. The `{name, tier}` object structure (W-7 schema) MUST be preserved. After editing, run the validation Python snippet (W-7 schema + tier-count + _validate_task_filter smoke) and type the resume signal.</action>
  <verify>The validation Python snippet in how-to-verify exits 0: len(task_filter)==30, _meta.placeholder is False, every item is a {name, tier} dict, tier-counts derived from task_filter match per_tier_counts, _validate_task_filter accepts all 30 names without raising.</verify>
  <done>datasets/prompts/tblite_stratified_subset.json contains 30 real TBLite task names in W-7 {name, tier} object form; _meta.placeholder is false; task_source_method documents how names were chosen.</done>
  <files>datasets/prompts/tblite_stratified_subset.json</files>
  <resume-signal>Type "subset-updated" when datasets/prompts/tblite_stratified_subset.json has real task names + W-7 schema preserved + _meta.placeholder is false. Type "subset-blocked" if Methods 1 and 2 both fail (HALTS Phase 20).</resume-signal>
</task>

<task type="checkpoint:human-action" gate="blocking">
  <name>Checkpoint C: Generate datasets/prompts/tblite_anchor.json via LIVE calibration (single path — no mock fallback)</name>
  <what-built>
    Run `python -m evolution.benchmarks.build_tblite_calibration` against the now-real subset to produce `datasets/prompts/tblite_anchor.json` with measured per-tier mean+stdev.

    **B-1 enforcement reminder:** No Path B / mock-anchor alternative exists in this plan. If live calibration fails (Modal outage, OpenRouter rate limit, budget exceeded mid-run), the executor MUST NOT hand-craft a fallback anchor. Retry the live run, or type "anchor-blocked" to HALT Phase 20.
  </what-built>
  <how-to-verify>
    Step 1 — Verify pre-flight readiness (these were confirmed in Checkpoint A, but re-confirm immediately before the multi-dollar subprocess):

    ```bash
    # hermes-agent is a clean tree
    cd ~/.hermes/hermes-agent && git status --porcelain  # expect empty
    cd ~/.hermes/hermes-agent && git rev-parse HEAD       # note this sha
    cd <project root>
    # env vars set
    test -n "$OPENROUTER_API_KEY" && test -n "$MODAL_TOKEN_ID" && echo "OK creds" || (echo "FAIL: missing creds — return to Checkpoint A or HALT"; exit 1)
    ```

    Step 2 — Adapter: convert W-7 task_filter into the CSV form `TBLiteRunner` expects. The Plan 04 CLI handles the conversion internally (see Plan 04 Task 1 — `_one_run_per_tier_pass_rate` and the subprocess construction), but if the CLI is invoked outside the planner-expected flow, ensure `[item['name'] for item in subset['task_filter']]` is what the runner sees.

    Step 3 — Run the CLI:
    ```bash
    python -m evolution.benchmarks.build_tblite_calibration \
      --seed 42 \
      --runs 3 \
      --output-json datasets/prompts/tblite_anchor.json \
      --benchmark-max-cost 50.0
    ```
    Expect 30-90 min wall time. The CLI prints `[bold]Run 1/3[/bold]` ... `[bold]Run 3/3[/bold]` plus per-task `[PASS]/[FAIL]` markers.

    Step 4 — On success, the CLI emits `Wrote datasets/prompts/tblite_anchor.json (cost $X.XX, measured $Y.YYYY/task)` and `Next: commit ...`.

    Step 5 — Validate the anchor:
    ```bash
    python -c "
    import json
    a = json.load(open('datasets/prompts/tblite_anchor.json'))
    for k in ('anchor_per_tier','dataset_revision_hash','hermes_agent_commit','stratified_subset_seed','tblite_estimated_cost_per_task_usd','calibration_timestamp','calibration_model','tblite_runner_version'):
        assert k in a, f'missing {k}'
    for t in ('easy','medium','hard','extreme'):
        assert t in a['anchor_per_tier'], f'missing tier {t}'
        assert a['anchor_per_tier'][t]['n'] >= 3, f'{t} n < 3'
        assert 0 <= a['anchor_per_tier'][t]['mean'] <= 1
    # B-1 sanity: NO _meta.tier='mock' marker — this is a LIVE anchor
    assert a.get('_meta', {}).get('tier') != 'mock', 'B-1 violation: mock anchor must NOT ship in Phase 20'
    print('OK schema (live anchor)')
    "
    ```

    Step 6 — Spot-check sanity:
    - Easy tier mean is ~0.6-0.95 (Claude Haiku 4.5 reference 0.85; allow some drift across models)
    - Extreme tier mean is ~0.10-0.40 (reference 0.30)
    - stdev across 3 runs is ~0.02-0.15 (variability is expected for small N)
    - `anchor.tblite_estimated_cost_per_task_usd` is non-default measured value (NOT exactly 0.4; if it equals 0.4 the CostTracker likely didn't observe any LM usage — investigate before committing)

    Step 7 — If any check fails, do NOT commit a partial / suspect anchor. Diagnose (Modal failures, model rate-limits, anchor schema bug) and re-run. Do NOT switch to a hand-crafted fallback.
  </how-to-verify>
  <action>Run `python -m evolution.benchmarks.build_tblite_calibration --runs 3 --benchmark-max-cost 50.0 --output-json datasets/prompts/tblite_anchor.json` against a clean hermes-agent with valid Modal + OpenRouter credentials. After the live anchor exists, run the validation Python snippet (key + tier checks + B-1 mock-marker sanity) and type the resume signal.</action>
  <verify>datasets/prompts/tblite_anchor.json exists and parses; all 8 D-CAL-01 keys present; all 4 tiers have n>=3 + numeric mean/stdev; NO `_meta.tier=="mock"` marker.</verify>
  <done>Live tblite_anchor.json committable; NO mock-anchor tracking todo created (mock path was removed per B-1).</done>
  <files>datasets/prompts/tblite_anchor.json</files>
  <resume-signal>Type "anchor-live" when Path A calibration succeeded and the validation snippet passes. Type "anchor-blocked" if live calibration is infeasible at execution time (Modal outage, OpenRouter exhausted, budget rejected) — HALTS Phase 20 with no mock fallback.</resume-signal>
</task>

<task type="auto" tdd="false">
  <name>Task 4: Verify final state — schema validation + TBLiteBenchmarkGate constructor smoke + git status</name>
  <files>
    - datasets/prompts/tblite_stratified_subset.json
    - datasets/prompts/tblite_anchor.json
  </files>
  <read_first>
    - datasets/prompts/tblite_stratified_subset.json (current state after Checkpoint B)
    - datasets/prompts/tblite_anchor.json (current state after Checkpoint C)
    - evolution/benchmarks/benchmark_gate.py (constructor schema validation logic)
    - .gitignore (verify exceptions still active)
  </read_first>
  <action>
    Run a sequence of read-only validation commands to confirm the two artifacts are coherent and committable. No file modifications in this task — only verification + commit prep.

    1. Schema validation via TBLiteBenchmarkGate constructor (must pass without raising):
       ```bash
       .venv/bin/python -c "
       import json
       from pathlib import Path
       from evolution.core.config import EvolutionConfig
       from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate

       anchor = json.loads(Path('datasets/prompts/tblite_anchor.json').read_text())
       subset = json.loads(Path('datasets/prompts/tblite_stratified_subset.json').read_text())

       # Schema validation only — constructor will raise on missing keys
       config = EvolutionConfig.__new__(EvolutionConfig)
       config.hermes_agent_path = Path('.')
       config.benchmark_runs = 3
       config.benchmark_heartbeat_seconds = 60
       config.benchmark_max_cost_usd = 50.0
       config.tblite_estimated_cost_per_task_usd = 0.4

       try:
           gate = TBLiteBenchmarkGate(config, anchor, subset)
           print(f'OK constructor: anchor commit {anchor[\"hermes_agent_commit\"][:8]}, '
                 f'{len(subset[\"task_filter\"])} tasks, {anchor[\"anchor_per_tier\"][\"easy\"][\"n\"]}-run anchor')
       except ValueError as e:
           print(f'SCHEMA FAIL: {e}')
           raise SystemExit(1)
       "
       ```

    2. Subset content sanity (W-7 schema):
       ```bash
       .venv/bin/python -c "
       import json
       d = json.load(open('datasets/prompts/tblite_stratified_subset.json'))
       assert len(d['task_filter']) == 30, f'task_filter len wrong: {len(d[\"task_filter\"])}'
       assert all(isinstance(t, dict) and 'name' in t and 'tier' in t for t in d['task_filter']), 'W-7 schema violation'
       tc = {}
       for t in d['task_filter']: tc[t['tier']] = tc.get(t['tier'], 0) + 1
       assert tc == d['per_tier_counts'], f'tier-count mismatch: {tc} vs {d[\"per_tier_counts\"]}'
       meta_placeholder = d.get('_meta', {}).get('placeholder', True)
       assert meta_placeholder is False, 'WAIT: _meta.placeholder still true — Checkpoint B did not clear it.'
       print('OK subset content (W-7 schema, real names)')
       "
       ```

    3. Anchor content sanity — B-1 enforces LIVE only:
       ```bash
       .venv/bin/python -c "
       import json
       a = json.load(open('datasets/prompts/tblite_anchor.json'))
       # B-1: no mock marker permitted
       assert a.get('_meta', {}).get('tier') != 'mock', 'B-1 violation: mock anchor present'
       print(f'  Anchor tier: live')
       print(f'  hermes_agent_commit: {a[\"hermes_agent_commit\"]}')
       print(f'  dataset_revision_hash: {a[\"dataset_revision_hash\"]}')
       print(f'  calibration_timestamp: {a[\"calibration_timestamp\"]}')
       for tier in ('easy','medium','hard','extreme'):
           pt = a['anchor_per_tier'][tier]
           print(f'  {tier}: mean={pt[\"mean\"]:.3f} stdev={pt[\"stdev\"]:.3f} n={pt[\"n\"]}')
       print(f'  measured cost_per_task: {a[\"tblite_estimated_cost_per_task_usd\"]:.4f}')
       "
       ```

    4. Git-trackability:
       ```bash
       git check-ignore datasets/prompts/tblite_anchor.json datasets/prompts/tblite_stratified_subset.json 2>&1 || echo 'OK: both files NOT ignored (good)'
       git status --short datasets/prompts/ | head -5
       ```

    5. Final go/no-go: if every check above prints OK, the artifacts are ready for commit. Report this in the SUMMARY but do NOT auto-commit — the user/orchestrator decides the commit step.

    Implements: D-14 commit-match + B-1 enforcement (live anchor only, no audit-trail mock). Mirrors Phase 18 build_drift_calibration final commit step.
  </action>
  <verify>
    <automated>test -f datasets/prompts/tblite_anchor.json || (echo "FAIL: tblite_anchor.json missing"; exit 1) && test -f datasets/prompts/tblite_stratified_subset.json || (echo "FAIL: tblite_stratified_subset.json missing"; exit 1) && .venv/bin/python -c "
import json
from pathlib import Path
from evolution.core.config import EvolutionConfig
from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
anchor = json.loads(Path('datasets/prompts/tblite_anchor.json').read_text())
subset = json.loads(Path('datasets/prompts/tblite_stratified_subset.json').read_text())
# B-1: mock marker forbidden in Phase 20
assert anchor.get('_meta', {}).get('tier') != 'mock', 'B-1 violation: mock anchor must NOT ship'
config = EvolutionConfig.__new__(EvolutionConfig)
config.hermes_agent_path = Path('.')
config.benchmark_runs = 3
config.benchmark_heartbeat_seconds = 60
config.benchmark_max_cost_usd = 50.0
config.tblite_estimated_cost_per_task_usd = 0.4
gate = TBLiteBenchmarkGate(config, anchor, subset)
print('OK schema-valid for TBLiteBenchmarkGate (live anchor)')
" && .venv/bin/python -c "
import json
a = json.load(open('datasets/prompts/tblite_anchor.json'))
required = {'anchor_per_tier','dataset_revision_hash','hermes_agent_commit','stratified_subset_seed','tblite_estimated_cost_per_task_usd','calibration_timestamp','calibration_model','tblite_runner_version'}
missing = required - set(a.keys())
assert not missing, f'missing keys: {missing}'
for t in ('easy','medium','hard','extreme'):
    assert t in a['anchor_per_tier'], f'missing tier {t}'
    assert a['anchor_per_tier'][t]['n'] >= 3, f'{t} n < 3'
    assert 0 <= a['anchor_per_tier'][t]['mean'] <= 1, f'{t} mean out of [0,1]'
print('OK anchor schema complete (live)')
" && .venv/bin/python -c "
import json
d = json.load(open('datasets/prompts/tblite_stratified_subset.json'))
assert len(d['task_filter']) == 30, f'task_filter len {len(d[\"task_filter\"])}'
assert all(isinstance(t, dict) and 'name' in t and 'tier' in t for t in d['task_filter']), 'W-7 schema violation'
tc = {}
for t in d['task_filter']: tc[t['tier']] = tc.get(t['tier'], 0) + 1
assert tc == d['per_tier_counts'], f'tier-count mismatch: {tc} vs {d[\"per_tier_counts\"]}'
assert d.get('_meta', {}).get('placeholder') is not True, 'Wave-1 placeholder flag still true — Checkpoint B was skipped'
print('OK subset 30 tasks, W-7 schema, _meta.placeholder cleared')
" && git check-ignore datasets/prompts/tblite_anchor.json datasets/prompts/tblite_stratified_subset.json 2>&1 | grep -E '!datasets/prompts/tblite_' > /dev/null && echo "OK: files are git-trackable (matched the ! exception rule)" || (git check-ignore datasets/prompts/tblite_anchor.json datasets/prompts/tblite_stratified_subset.json; echo "Result of check-ignore (no output above means files are not ignored — also good)")</automated>
  </verify>
  <acceptance_criteria>
    - `datasets/prompts/tblite_anchor.json` exists and parses as JSON.
    - `datasets/prompts/tblite_stratified_subset.json` has 30 task names in W-7 `{name, tier}` object form and `_meta.placeholder` is NOT true.
    - Tier-counts derived from `task_filter[].tier` match `per_tier_counts` exactly.
    - `TBLiteBenchmarkGate(config, anchor, subset)` constructs without raising (schema valid).
    - Anchor has all 8 required top-level keys per D-CAL-01.
    - Each of the 4 tiers has `mean` in [0, 1], `n >= 3`, numeric `stdev`.
    - Anchor does NOT have `_meta.tier == "mock"` (B-1 enforcement).
    - Both files appear in `git status --short` (NOT ignored).
  </acceptance_criteria>
  <done>
    - Both JSON files validate against TBLiteBenchmarkGate constructor
    - Subset has 30 real task names in W-7 schema
    - Anchor has all required schema keys + LIVE measured values (no mock marker)
    - User/orchestrator can now `git add` the two files and commit
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Live TBLite subprocess → samples_*.jsonl → anchor JSON | Plan 02/03/04 mitigations all in play (Popen + sanitized args + per-line JSON parse + infra_fail flagging). |
| huggingface_hub probe → live revision hash for anchor | Network IO; Plan 04's `_hf_dataset_revision` already handles fail-open to `unknown_v<runner>`. |
| OPENROUTER_API_KEY + MODAL_TOKEN_ID in process env | Inherited transparently by the calibration CLI; never written to anchor or logs. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-20-24 | E (Elevation of privilege) | Mock anchor accepted as production baseline | **MITIGATED BY ELIMINATION (B-1, 2026-05-19)** | Plan 05 no longer produces mock anchors. The previous mitigation chain (`_meta.tier="mock"` + tracking todo + Phase 21 prerequisite check) is replaced by an unconditional ban: no mock anchor ships at all. Plan 06 step 10.5 retains its `_meta.tier=="mock"` runtime warning ONLY as a guard against historical archive artifacts, not as a sanctioned authoring path. |
| T-20-25 | T (Tampering) | Live calibration partial run committed | accept | If TBLite subprocess fails mid-run, Plan 04 raises click.ClickException and DOES NOT write anchor JSON. The user must explicitly retry; no partial state ships unless the user manually edits and lies about it (not a software-layer threat). |
| T-20-26 | I (Information disclosure) | OPENROUTER_API_KEY in subprocess env during live calibration | accept | os.environ.copy() passes the key transparently to TBLite which forwards to OpenRouter HTTPS endpoint. Key never appears in samples.jsonl or anchor JSON. CONCERNS §M3-style risk is unchanged from Phase 13/14/15. |
| T-20-27 | D (Denial of service) | Modal / OpenRouter rate limits during 30-90 min run | mitigate | Plan 02 TBLiteRunner heartbeat detection + Plan 04 CostTracker enforcement. Worst case: SystemExit(1) mid-run, no partial anchor written, user retries. |
| T-20-28 | T (Tampering) | git status --porcelain misses uncommitted stash content | accept | Same as T-20-12 (Plan 03) / T-20-23 (Plan 04). Documented limitation; deferred to Phase 22+ `enforce-readonly-hermes-agent` todo. |
| T-20-36 | A (Availability) | `--accept-stale-anchor` flag in Plan 04 + this plan's single-path | accept | Plan 04 retains `--accept-stale-anchor` as `[unsafe]` for debug runs writing to `/tmp/anchor.json`. The production path here uses default `--output-json datasets/prompts/tblite_anchor.json` and does NOT pass `--accept-stale-anchor`. B-1's "no placeholder" rule covers in-tree shippable anchors; ops debugging outside the tree is unaffected. |
</threat_model>

<verification>
- `datasets/prompts/tblite_anchor.json` parses as valid JSON with all 8 D-CAL-01 keys.
- `datasets/prompts/tblite_anchor.json` does NOT contain `_meta.tier == "mock"` (B-1 enforcement).
- `datasets/prompts/tblite_stratified_subset.json` has 30 task names in W-7 `{name, tier}` object form, `_meta.placeholder` is false, and tier-counts match `per_tier_counts`.
- `TBLiteBenchmarkGate(config, anchor, subset)` constructs without ValueError (cross-plan integration test).
- `anchor["dataset_revision_hash"]` is either a hex sha (live HF) or `unknown_v1.0` (acceptable fail-open on HF outage during live run; NOT a substitute for live calibration itself).
- `anchor["tblite_estimated_cost_per_task_usd"]` reflects the measured value from the live subprocess (likely non-default 0.3-0.6 range).
- `git status` shows both JSON files as new/modified (not ignored).
</verification>

<success_criteria>
- ROADMAP SC #1 + SC #2: live anchor enables `evolve_prompt_sections --benchmark=tblite` to function in Plan 06 without `_check_anchor_existence` SystemExit AND without silent degradation to a mock-anchor no-op.
- D-13 covered (in spirit and in letter): anchor exists as a git-tracked artifact with full metadata AND is the output of a real calibration run, not a placeholder.
- B-1 enforced: no mock-anchor path exists in this plan. Phase 20 ships a usable gate or HALTS.
- TBLiteBenchmarkGate constructor accepts both files end-to-end.
- T-20-24 mitigated by elimination (mock anchor cannot be produced by Plan 05).
- Phase 20 is no longer abstract — there is now a real measured baseline file the rest of the pipeline reads at every gate invocation.
</success_criteria>

<output>
After completion, create `.planning/phases/20-benchmark-gated-validation/20-05-anchor-generation-checkpoint-SUMMARY.md` covering:
- Confirmation of single-path execution: live calibration completed.
- File sizes of the two JSON artifacts.
- TBLiteBenchmarkGate constructor smoke output.
- Actual measured cost ($ spent), wall time, per-tier means.
- Confirmation that NO mock-anchor tracking todo was created (B-1: no such todo exists in this plan path).
- Any deviations / partial run incidents (must list every retry attempt; no silent fallbacks permitted).
</output>

## Revision Log

- 2026-05-19 (B-1): Eliminated "Path B — mock anchor with audit trail" entirely. CONTEXT D-13 mandates "Phase 20 工期内必须完成 calibration...不允许 placeholder"; a `_meta.tier="mock"` honesty marker is still a placeholder. Plan 05 now offers ONLY the live calibration path. Checkpoint A reshaped from "choose path A vs B" to "confirm prerequisites are ready"; resume signal `anchor-blocked` HALTS Phase 20 (no fallback) instead of routing to mock. Checkpoint C resume signal `anchor-mock` removed; only `anchor-live` and `anchor-blocked` remain. Threat T-20-24 disposition flipped from "mitigate via audit trail" to "mitigate by elimination". Mock-anchor runtime warning in Plan 06 step 10.5 retained as guard against historical archives, but no longer endorsed as authoring path.
- 2026-05-19 (W-7 propagation): Updated all references to `task_filter` schema — Checkpoint B Method 1 + Method 2 now write tier-explicit `{name, tier}` objects; validation snippets check `item['tier']` presence + tier-count consistency; Plan 04 / Plan 06 consumers extract `[item['name'] for item in subset['task_filter']]` before passing to `TBLiteRunner._validate_task_filter`.
