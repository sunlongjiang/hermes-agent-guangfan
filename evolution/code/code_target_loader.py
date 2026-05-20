"""Code target loader for Phase 21 darwinian code evolution.

Discovers a hermes-agent code component (PoC: tools/ansi_strip.py), statically
parses its test file via `ast.parse` to enumerate test functions, then performs
a stratified 20/10 train/holdout split by ANSI escape category (CSI/SGR/OSC/other).

Design decisions (see .planning/phases/21-darwinian-code-evolution/21-CONTEXT.md):

- **D-06**: PoC target = `tools/ansi_strip.py` (44 lines, 30 native pytests).
- **D-07**: Stratify by CSI/SGR/OSC/other; seed=42; holdout per bucket
  {csi:4, sgr:3, osc:2, other:1} = 10 total.
- **D-08**: Test discovery uses `ast.parse` (NEVER `exec` / `importlib`) — a
  candidate's test file is untrusted code; we extract structure, not behavior.
- **T-21-RECURSE (D-08 extension)**: `find_target` hard-rejects `evolution/`
  prefixes (recursive self-evolution) and known security-sensitive paths
  (`agent/redact.py`, `agent/credential_*`, `agent/auth*`) — `raise ValueError`
  before any filesystem touch.

Public surface:
    - `CodeTarget` — dataclass holding component metadata + original source.
    - `find_target(component, hermes_repo) -> CodeTarget`
    - `find_target_tests(target) -> list[dict]` — test manifest (JSON-serializable).
    - `stratify_tests(manifest, seed=42) -> dict[train_ids, holdout_ids]`

Module is `import openevolve`-free by design (D-03 single import surface).
"""

import ast
import random
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ────────────────────────────────────────────────────────────────────
# D-08 / T-21-RECURSE — Forbidden component path prefixes.
# Any `find_target(component, ...)` whose `component` string begins with
# one of these prefixes raises `ValueError` before filesystem access.
# ────────────────────────────────────────────────────────────────────
_FORBIDDEN_PATH_PREFIXES: list[str] = [
    "evolution/",          # T-21-RECURSE: refuse to evolve our own evolver.
    "agent/redact.py",     # Security-sensitive: secret redaction.
    "agent/credential_",   # Security-sensitive: credential handling.
    "agent/auth",          # Security-sensitive: authentication paths.
]


# ────────────────────────────────────────────────────────────────────
# D-07 — Stratified split configuration.
# Buckets are derived from ANSI escape sequence families covered by
# the hermes-agent ansi_strip test suite (CSI, SGR, OSC) + a catch-all
# "other" bucket for tests that don't match the keyword heuristics.
# ────────────────────────────────────────────────────────────────────
STRATIFY_BUCKETS: list[str] = ["csi", "sgr", "osc", "other"]
HOLDOUT_PER_BUCKET: dict[str, int] = {"csi": 4, "sgr": 3, "osc": 2, "other": 1}  # sum = 10

# Keyword → bucket mapping (lowercased substring match against test function name).
# Order matters: longer/more specific keywords first so "color" doesn't shadow "csi".
_BUCKET_KEYWORDS: list[tuple[str, str]] = [
    # SGR (Select Graphic Rendition) — colors, weights, styles.
    ("sgr", "sgr"),
    ("color", "sgr"),
    ("bold", "sgr"),
    ("blink", "sgr"),
    ("dim", "sgr"),
    ("reverse", "sgr"),
    ("underline", "sgr"),
    ("truecolor", "sgr"),
    ("reset", "sgr"),          # CSI 0m falls under SGR semantics.
    ("stacked", "sgr"),
    # OSC (Operating System Command) — window title, hyperlinks, palette.
    ("osc", "osc"),
    ("title", "osc"),
    ("hyperlink", "osc"),
    ("bel", "osc"),            # BEL terminator marks OSC end.
    ("st_terminator", "osc"),
    # CSI (Control Sequence Introducer) — cursor, screen, mode.
    ("csi", "csi"),
    ("cursor", "csi"),
    ("move", "csi"),
    ("arrow", "csi"),
    ("alt_screen", "csi"),
    ("bracketed_paste", "csi"),
    ("save_restore", "csi"),
    ("keypad", "csi"),
    ("reverse_index", "csi"),
    ("reset_terminal", "csi"),
    ("index_and_newline", "csi"),
    ("charset", "csi"),
    ("dcs", "csi"),
    ("8bit", "csi"),
]


@dataclass
class CodeTarget:
    """Metadata container for a hermes-agent code component under evolution.

    Fields:
        component_path: Absolute path to the component file inside hermes-agent.
        test_file_path: Absolute path to its sibling pytest file in hermes-agent.
        baseline_size_bytes: `component_path.stat().st_size` at load time.
        original_source: Full text of the component (read once, cached for diff).
        schema_version: Manifest format version (bumped if `to_dict` shape changes).
        hermes_agent_commit: Short git SHA of hermes-agent at load time (`""` if
            git unavailable). Used as a risk anchor — re-baseline on commit drift.
    """

    component_path: Path
    test_file_path: Path
    baseline_size_bytes: int
    original_source: str
    schema_version: str = "1.0"
    hermes_agent_commit: str = ""

    def to_dict(self) -> dict:
        """JSON-serializable representation (Path → str).

        Note: `original_source` may be large; callers that need a compact
        manifest should strip this field after serialization.
        """
        return {
            "component_path": str(self.component_path),
            "test_file_path": str(self.test_file_path),
            "baseline_size_bytes": self.baseline_size_bytes,
            "original_source": self.original_source,
            "schema_version": self.schema_version,
            "hermes_agent_commit": self.hermes_agent_commit,
        }


def _infer_test_file_path(component: str, hermes_repo: Path) -> Path:
    """Infer pytest file path for a component file.

    Convention (hermes-agent layout):
        tools/ansi_strip.py        → tests/tools/test_ansi_strip.py
        tools/sub/foo.py           → tests/tools/sub/test_foo.py
        agent/whatever.py          → tests/agent/test_whatever.py

    Strategy: replace the leaf filename with `test_<leaf>` and prepend `tests/`
    to the top-level package segment.
    """
    parts = Path(component).parts
    if not parts:
        raise ValueError(f"Empty component path: {component!r}")

    leaf = parts[-1]
    # Prepend test_ to the filename.
    test_leaf = f"test_{leaf}"
    # Rebuild path under tests/ root.
    test_parts = ("tests",) + parts[:-1] + (test_leaf,)
    return hermes_repo / Path(*test_parts)


def _git_short_sha(repo: Path) -> str:
    """Best-effort short HEAD SHA of `repo`. Returns "" on any failure.

    Silent failure is intentional — git availability is a risk anchor, not a
    blocker. The empty string is recorded in the manifest so a downstream
    reviewer can spot un-anchored evolution runs.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return ""


def find_target(component: str, hermes_repo: Path) -> CodeTarget:
    """Locate a hermes-agent component for evolution.

    Args:
        component: Relative path inside hermes-agent (e.g. "tools/ansi_strip.py").
            Must NOT begin with `evolution/` (T-21-RECURSE) or any known
            security-sensitive prefix.
        hermes_repo: Absolute path to the hermes-agent checkout.

    Returns:
        A `CodeTarget` with `component_path`, inferred `test_file_path`,
        baseline size, original source, and (best-effort) git commit SHA.

    Raises:
        ValueError: If `component` matches `_FORBIDDEN_PATH_PREFIXES`.
        FileNotFoundError: If the component file does not exist in `hermes_repo`.
    """
    # ── 1. Path guard — fail FAST before touching the filesystem.
    # T-21-RECURSE: refuse to evolve evolution/ itself.
    if component.startswith("evolution/"):
        raise ValueError(
            f"Refusing to evolve evolution/ itself: {component!r}. "
            "Recursive self-evolution is an anti-feature (see PROJECT.md)."
        )
    # Security-sensitive paths: refuse even at PoC stage (FEATURES anti-feature).
    for forbidden in _FORBIDDEN_PATH_PREFIXES[1:]:  # skip the evolution/ guard already handled
        if component.startswith(forbidden):
            raise ValueError(
                f"Refusing to evolve security-sensitive path: {component!r}. "
                "auth/credential/redaction components are out of scope for code evolution."
            )

    # ── 2. Resolve component path.
    component_path = hermes_repo / component
    if not component_path.exists():
        raise FileNotFoundError(
            f"Component not found in hermes-agent: {component_path}. "
            f"Verify HERMES_AGENT_REPO points to a valid checkout."
        )

    # ── 3. Infer and validate test file path (test file may be missing for newly added components;
    #       caller can detect via target.test_file_path.exists() after construction).
    test_file_path = _infer_test_file_path(component, hermes_repo)

    # ── 4. Build target.
    baseline_size = component_path.stat().st_size
    original_source = component_path.read_text(encoding="utf-8")
    commit = _git_short_sha(hermes_repo)

    return CodeTarget(
        component_path=component_path,
        test_file_path=test_file_path,
        baseline_size_bytes=baseline_size,
        original_source=original_source,
        hermes_agent_commit=commit,
    )


def _bucket_for_test_name(test_name: str) -> str:
    """Classify a test function name into one of STRATIFY_BUCKETS.

    Keyword matching is lowercased substring (longest-specific first).
    Falls through to "other" if no keyword matches.
    """
    lowered = test_name.lower()
    for keyword, bucket in _BUCKET_KEYWORDS:
        if keyword in lowered:
            return bucket
    return "other"


def _extract_parametrize_count(decorators: list[ast.expr]) -> int:
    """Return the number of parametrize values, or 1 if not parametrized.

    Looks for `@pytest.mark.parametrize("name", [...])` and counts the list
    literal's elements. If the values are not an `ast.List`, returns 1 (we
    cannot statically determine the count).
    """
    for deco in decorators:
        # Decorator must be a Call node.
        if not isinstance(deco, ast.Call):
            continue
        # Match @pytest.mark.parametrize via attribute chain.
        func = deco.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "parametrize":
            continue
        # `parametrize(name, values, ...)`
        if len(deco.args) < 2:
            continue
        values = deco.args[1]
        if isinstance(values, ast.List):
            return len(values.elts)
        # Could not statically determine length.
        return 1
    return 1


def find_target_tests(target: CodeTarget) -> list[dict]:
    """Statically enumerate pytest functions in `target.test_file_path`.

    Uses `ast.parse` exclusively — no `exec` or `importlib.import_module`,
    because the test file is untrusted (D-08).

    Walks both module-level and class-nested function definitions, including
    `async def`. Methods whose name does NOT start with `test_` are skipped.

    Args:
        target: A `CodeTarget` returned by `find_target`.

    Returns:
        A list of dicts, each:
            {
                "test_id": str,           # function name (no class prefix)
                "bucket": str,            # one of STRATIFY_BUCKETS
                "parametrize_count": int, # 1 if not parametrized
                "schema_version": str,    # "1.0"
                "hermes_agent_commit": str,  # from target
            }

    Raises:
        FileNotFoundError: If `target.test_file_path` does not exist.
        SyntaxError: If the test file is not valid Python (re-raised from ast.parse).
    """
    if not target.test_file_path.exists():
        raise FileNotFoundError(
            f"Test file not found: {target.test_file_path}. "
            f"Expected hermes-agent layout `tests/<package>/test_<leaf>.py`."
        )

    source = target.test_file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(target.test_file_path))

    manifest: list[dict] = []

    def _record(node) -> None:
        """Append a manifest entry for a FunctionDef/AsyncFunctionDef whose
        name starts with `test_`."""
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        if not node.name.startswith("test_"):
            return
        manifest.append({
            "test_id": node.name,
            "bucket": _bucket_for_test_name(node.name),
            "parametrize_count": _extract_parametrize_count(node.decorator_list),
            "schema_version": "1.0",
            "hermes_agent_commit": target.hermes_agent_commit,
        })

    # Walk top-level + class-nested test functions. We intentionally do NOT
    # recurse into function bodies (a test_*'s helper closure is not a test).
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _record(node)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                _record(child)

    return manifest


def stratify_tests(manifest: list[dict], seed: int = 42) -> dict:
    """Split a test manifest into train/holdout by bucket.

    Algorithm (D-07):
      1. Group manifest entries by `bucket`.
      2. Per-bucket: `random.seed(seed)` then `random.shuffle` (deterministic).
      3. Take `HOLDOUT_PER_BUCKET[bucket]` entries from the front of each bucket
         as holdout; the rest become train.
      4. If a bucket is undersized, round-robin top up from the largest remaining
         bucket so the holdout total reaches `sum(HOLDOUT_PER_BUCKET.values())`.

    Args:
        manifest: Output of `find_target_tests`.
        seed: PRNG seed (default 42, matches D-07 anchor).

    Returns:
        {"train_ids": [test_id, ...], "holdout_ids": [test_id, ...]} —
        disjoint sets whose union equals the input set of test IDs.
    """
    # Single Random instance keeps shuffles deterministic across buckets.
    rng = random.Random(seed)

    # Group by bucket, preserving manifest order before shuffle.
    by_bucket: dict[str, list[str]] = {b: [] for b in STRATIFY_BUCKETS}
    for entry in manifest:
        bucket = entry.get("bucket", "other")
        if bucket not in by_bucket:
            bucket = "other"
        by_bucket[bucket].append(entry["test_id"])

    # Deterministic shuffle per bucket.
    for bucket in STRATIFY_BUCKETS:
        rng.shuffle(by_bucket[bucket])

    holdout_ids: list[str] = []
    # First pass: take quota from each bucket.
    for bucket in STRATIFY_BUCKETS:
        quota = HOLDOUT_PER_BUCKET[bucket]
        available = by_bucket[bucket]
        take = min(quota, len(available))
        holdout_ids.extend(available[:take])
        # Trim taken entries from bucket so they don't appear in train.
        by_bucket[bucket] = available[take:]

    # Round-robin top-up: if total holdout < sum(HOLDOUT_PER_BUCKET), pull from
    # whichever bucket still has the most remaining items, one at a time.
    target_total = sum(HOLDOUT_PER_BUCKET.values())
    while len(holdout_ids) < target_total:
        # Find bucket with most remaining entries.
        candidates = [(len(by_bucket[b]), b) for b in STRATIFY_BUCKETS if by_bucket[b]]
        if not candidates:
            break  # nothing left to pull from anywhere — manifest is too small.
        candidates.sort(reverse=True)  # largest bucket first.
        _, donor = candidates[0]
        holdout_ids.append(by_bucket[donor].pop(0))

    # Train = everything still left in the buckets.
    train_ids: list[str] = []
    for bucket in STRATIFY_BUCKETS:
        train_ids.extend(by_bucket[bucket])

    return {"train_ids": train_ids, "holdout_ids": holdout_ids}
