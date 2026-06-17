"""GEPA → MIPROv2 fallback + three-gate filtering + run_summary writer.

Designed to be a short-lived process: cron / GH Actions invokes
`python -m evolution.sdk.optimizer --agent <name>`. State is filesystem;
no in-memory persistence between runs.
"""

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.trace_sink import _evolution_home
from evolution.sdk.agent_module import build_composite_metric

log = logging.getLogger("evolution.sdk.optimizer")


# Reuse hermes' SECRET_PATTERNS to detect leaked credentials in optimized
# candidates.
try:
    from evolution.core.external_importers import SECRET_PATTERNS
except Exception:  # pragma: no cover — defensive
    SECRET_PATTERNS = re.compile(r"sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]+")


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@dataclass
class OptimizationBudget:
    """USD budget for one optimization run."""
    max_cost_usd: float
    spent_usd: float = 0.0

    def remaining(self) -> float:
        return max(0.0, self.max_cost_usd - self.spent_usd)

    def can_afford(self, estimate: float) -> bool:
        return self.remaining() >= estimate

    def spend(self, amount: float) -> None:
        self.spent_usd += amount


@dataclass
class GateResult:
    passed: bool
    failed_gate: str = ""
    reason: str = ""


class GateFailure(Exception):
    """Internal signal that a candidate failed a gate."""


@dataclass
class OptimizationOutcome:
    artifact_id: str
    status: str  # improved | rejected | budget_skipped | baseline_kept | error
    baseline_score: Optional[float] = None
    optimized_score: Optional[float] = None
    holdout_score: Optional[float] = None
    rejection_reason: Optional[str] = None
    cost_usd: float = 0.0
    candidate_text: Optional[str] = None  # populated on status == "improved"


# ── Three gates ─────────────────────────────────────────────────────────


def apply_gates(
    *,
    artifact: EvolvableArtifact,
    candidate_text: str,
    baseline_score: float,
    candidate_holdout_score: float,
    regression_tolerance: float = 0.02,
) -> GateResult:
    """Run all three gates against a candidate. Returns first failure or pass."""
    # ── Gate 1: structure + size + growth + secrets + placeholders ──
    constraints = artifact.constraints
    max_chars = constraints.get("max_chars")
    if max_chars is not None and len(candidate_text) > max_chars:
        return GateResult(False, "gate_1_size",
                          f"size {len(candidate_text)} > max_chars {max_chars}")

    max_growth = constraints.get("max_growth")
    if max_growth is not None:
        baseline_len = max(1, len(artifact.baseline_text))
        growth = (len(candidate_text) - baseline_len) / baseline_len
        if growth > max_growth:
            return GateResult(False, "gate_1_growth",
                              f"growth {growth:+.1%} > max {max_growth:+.1%}")

    if not candidate_text.strip():
        return GateResult(False, "gate_1_empty", "candidate text is empty")

    if SECRET_PATTERNS.search(candidate_text):
        return GateResult(False, "gate_1_secret",
                          "candidate contains a SECRET_PATTERNS match")

    if artifact.kind == "tool":
        baseline_placeholders = set(_PLACEHOLDER_RE.findall(artifact.baseline_text))
        candidate_placeholders = set(_PLACEHOLDER_RE.findall(candidate_text))
        missing = baseline_placeholders - candidate_placeholders
        if missing:
            return GateResult(False, "gate_1_placeholder",
                              f"tool kind lost placeholder(s): {sorted(missing)}")

    forbidden = constraints.get("forbidden_patterns") or []
    for pat in forbidden:
        if re.search(pat, candidate_text):
            return GateResult(False, "gate_1_forbidden",
                              f"candidate matched forbidden pattern: {pat!r}")

    # ── Gate 2: holdout regression ──
    threshold = baseline_score * (1 - regression_tolerance)
    if candidate_holdout_score < threshold:
        return GateResult(False, "gate_2_holdout_regression",
                          f"holdout {candidate_holdout_score:.3f} < {threshold:.3f}")

    # ── Gate 3: regression smoke for prompt kind ──
    # (Implementation note: P0 implements gate 3 as a no-op stub since it
    # requires running the agent against historical traces with the new
    # prompt — see spec §6.4 line "回归冒烟". The optimizer hook below
    # invokes it; P1 wires the actual smoke run.)

    return GateResult(True)


# ── Output writers ──────────────────────────────────────────────────────


def write_optimized_file(
    *,
    artifact: EvolvableArtifact,
    agent_version: str,
    optimized_text: str,
    optimization_metadata: dict,
) -> Path:
    """Atomically write ~/.evolution/optimized/<agent>/<artifact_id>.json."""
    base = _evolution_home() / "optimized" / artifact.agent_name
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{artifact.artifact_id}.json"
    tmp = path.with_suffix(".tmp")
    payload = {
        "agent": artifact.agent_name,
        "agent_version": agent_version,
        "artifact_id": artifact.artifact_id,
        "kind": artifact.kind,
        "baseline_hash": artifact.baseline_hash,
        "optimized_text": optimized_text,
        "optimization": optimization_metadata,
    }
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)
    return path


def write_run_summary(
    *,
    agent_name: str,
    trigger: str,
    outcomes: list[OptimizationOutcome],
    dataset_path: Path,
    total_cost_usd: float,
    duration_seconds: int,
) -> Path:
    """Write output/sdk/<agent>/<ts>/run_summary.json (under cwd, not home)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path("output") / "sdk" / agent_name / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "run_summary.json"
    payload = {
        "agent": agent_name,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trigger": trigger,
        "artifacts": [asdict(o) for o in outcomes],
        "dataset_path": str(dataset_path),
        "total_cost_usd": total_cost_usd,
        "duration_seconds": duration_seconds,
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


# ── Optimize a single artifact ──────────────────────────────────────────


def optimize_artifact(
    *,
    artifact: EvolvableArtifact,
    train_examples: list,
    val_examples: list,
    holdout_examples: list,
    metric: Callable,
    optimizer_model: str,
    budget: OptimizationBudget,
    judge_dimensions: tuple[str, ...],
    regression_tolerance: float = 0.02,
    max_metric_calls: int = 50,
) -> OptimizationOutcome:
    """Run GEPA → MIPROv2 fallback for one artifact + apply gates."""
    from evolution.sdk.agent_module import AgentModule
    import dspy

    start_cost = budget.spent_usd

    # Build module + baseline evaluation.
    module = AgentModule(artifact, judge_dimensions=judge_dimensions)
    baseline_scores = [metric(ex, module.forward(**_kwargs_from_example(ex)))
                       for ex in val_examples] or [0.5]
    baseline_score = sum(baseline_scores) / len(baseline_scores)

    if not budget.can_afford(0.5):
        return OptimizationOutcome(
            artifact_id=artifact.artifact_id,
            status="budget_skipped",
            baseline_score=baseline_score,
            cost_usd=budget.spent_usd - start_cost,
        )

    # GEPA → MIPROv2 fallback.
    optimized_module = None
    try:
        # Reuse the already-configured global LM so api_base/api_key reach
        # GEPA's reflection LM. A bare `dspy.LM(optimizer_model)` would
        # default to OpenAI's endpoint and 404 on non-OpenAI models.
        lm = dspy.settings.lm
        # dspy.GEPA asserts exactly one of (max_metric_calls, max_full_evals,
        # auto). We pass max_metric_calls so the caller can bound API spend
        # — leave `auto` unset.
        gepa = dspy.GEPA(
            metric=metric,
            max_metric_calls=max_metric_calls,
            reflection_lm=lm,
            track_stats=True,
        )
        optimized_module = gepa.compile(module, trainset=train_examples)
    except Exception as e:  # noqa: BLE001
        log.warning("GEPA failed (%s); falling back to MIPROv2", e)
        try:
            mipro = dspy.MIPROv2(metric=metric, auto="light")
            optimized_module = mipro.compile(module, trainset=train_examples)
        except Exception as e2:  # noqa: BLE001
            log.error("MIPROv2 also failed: %s", e2)
            return OptimizationOutcome(
                artifact_id=artifact.artifact_id,
                status="error",
                baseline_score=baseline_score,
                rejection_reason=f"both optimizers failed: {e2}",
                cost_usd=budget.spent_usd - start_cost,
            )

    candidate_text = getattr(optimized_module, "current_text", artifact.baseline_text)

    # Evaluate candidate on holdout.
    optimized_module.set_text(candidate_text)
    holdout_scores = [metric(ex, optimized_module.forward(**_kwargs_from_example(ex)))
                      for ex in holdout_examples] or [baseline_score]
    holdout_score = sum(holdout_scores) / len(holdout_scores)

    # Apply gates.
    gate_result = apply_gates(
        artifact=artifact,
        candidate_text=candidate_text,
        baseline_score=baseline_score,
        candidate_holdout_score=holdout_score,
        regression_tolerance=regression_tolerance,
    )
    if not gate_result.passed:
        return OptimizationOutcome(
            artifact_id=artifact.artifact_id,
            status="rejected",
            baseline_score=baseline_score,
            optimized_score=None,
            holdout_score=holdout_score,
            rejection_reason=f"{gate_result.failed_gate}: {gate_result.reason}",
            cost_usd=budget.spent_usd - start_cost,
        )

    return OptimizationOutcome(
        artifact_id=artifact.artifact_id,
        status="improved",
        baseline_score=baseline_score,
        optimized_score=sum(metric(ex, optimized_module.forward(**_kwargs_from_example(ex)))
                            for ex in val_examples) / max(1, len(val_examples)),
        holdout_score=holdout_score,
        rejection_reason=None,
        cost_usd=budget.spent_usd - start_cost,
        candidate_text=candidate_text,
    )


def _kwargs_from_example(example) -> dict:
    """Extract DSPy Example kwargs for forward(). Best effort."""
    if hasattr(example, "user_input"):
        return {"user_input": example.user_input}
    if hasattr(example, "user_intent"):
        return {"user_intent": example.user_intent}
    return {"user_input": str(getattr(example, "input", ""))}


# ── CLI entry point ─────────────────────────────────────────────────────


def main() -> int:
    """`python -m evolution.sdk.optimizer --agent <name>` entry.

    Returns process exit code (0=success or SKIPPED, 1=FAILED, 2=PARTIAL).
    """
    import argparse
    from evolution.sdk import registry
    from evolution.sdk.trace_sink import LocalJsonlSink
    from evolution.sdk.signals import annotate_traces_with_signals
    from datetime import timedelta

    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-llm", action="store_true",
                        help="Test mode: use a predictable mock LLM (no API calls).")
    args = parser.parse_args()

    # Load registry from disk.
    registry.load_from_file()
    reg = registry.get_agent(args.agent)
    if reg is None:
        # Try to import the agent module directly (registry empty).
        import sys as _sys
        _sys.stderr.write(f"EVOLUTION_FATAL: agent {args.agent!r} not in registry\n")
        return 1

    # Acquire lock.
    lock_dir = _evolution_home() / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{args.agent}.lock"
    try:
        import fcntl
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.warning("another optimizer is running for %s; exiting cleanly", args.agent)
            return 0
    except ImportError:
        lock_fd = None  # Windows fallback

    start = time.time()
    sink = LocalJsonlSink()
    since = datetime.now(timezone.utc) - timedelta(days=90)
    raw_traces = list(sink.read(args.agent, since=since))

    if len(raw_traces) < reg.min_samples:
        # SKIPPED path
        _write_skipped(args.agent, len(raw_traces), reg.min_samples)
        return 0

    traces = annotate_traces_with_signals(raw_traces)

    # P0: build dataset + run optimization per artifact.
    # (Detailed dataset construction is implemented via core/dataset_builder.py
    # which expects (input, expected_output) pairs; for SDK MVP we pass a
    # minimal mapping. Task 13 end-to-end exercises this with mock LLM.)
    outcomes = []
    budget = OptimizationBudget(max_cost_usd=reg.max_cost_usd)
    for artifact in reg.artifacts:
        if budget.remaining() < 0.5:
            outcomes.append(OptimizationOutcome(
                artifact_id=artifact.artifact_id,
                status="budget_skipped", cost_usd=0.0,
            ))
            continue
        # In dry_run or mock_llm modes, return a deterministic stub.
        if args.dry_run:
            outcomes.append(OptimizationOutcome(
                artifact_id=artifact.artifact_id,
                status="baseline_kept",
                baseline_score=0.5, cost_usd=0.0,
            ))
            continue
        try:
            outcome = _run_one_artifact(
                artifact, traces, reg, budget, mock_llm=args.mock_llm,
            )
        except Exception as e:  # noqa: BLE001
            log.error("artifact %s failed: %s", artifact.artifact_id, e)
            outcome = OptimizationOutcome(
                artifact_id=artifact.artifact_id, status="error",
                rejection_reason=str(e), cost_usd=0.0,
            )
        outcomes.append(outcome)

        if outcome.status == "improved":
            write_optimized_file(
                artifact=artifact,
                agent_version=reg.version,
                optimized_text=outcome.candidate_text or artifact.baseline_text,
                optimization_metadata={
                    "run_id": str(uuid.uuid4()),
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "optimizer": "GEPA",
                    "baseline_score": outcome.baseline_score,
                    "optimized_score": outcome.optimized_score,
                    "holdout_score": outcome.holdout_score,
                    "dataset_size": len(traces),
                    "cost_usd": outcome.cost_usd,
                },
            )

    duration = int(time.time() - start)
    total_cost = sum(o.cost_usd for o in outcomes)
    write_run_summary(
        agent_name=args.agent,
        trigger=os.getenv("EVOLUTION_TRIGGER", "manual"),
        outcomes=outcomes,
        dataset_path=_evolution_home() / "datasets" / args.agent,
        total_cost_usd=total_cost,
        duration_seconds=duration,
    )
    return 0


def _write_skipped(agent: str, count: int, required: int) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path("output") / "sdk" / agent / f"SKIPPED_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reason.txt").write_text(
        f"traces={count} < min_samples={required}\n"
    )


def _run_one_artifact(artifact, traces, reg, budget, *, mock_llm: bool):
    """Wire one artifact through GEPA optimization (P1 + dogfood).

    Build train/val/holdout from real traces, configure dspy.LM from
    evolution.yaml, call optimize_artifact(). Mock mode returns baseline_kept
    (no LLM calls) so Task 13 end-to-end keeps working.
    """
    if mock_llm:
        return OptimizationOutcome(
            artifact_id=artifact.artifact_id,
            status="baseline_kept",
            baseline_score=0.5,
            cost_usd=0.0,
        )

    import dspy
    from evolution.core.config import EvolutionConfig
    from evolution.sdk.agent_module import JudgeConfig
    from evolution.sdk.signals import compute_signal_score

    # Configure LM from evolution.yaml (or env overrides).
    cfg = EvolutionConfig.load()
    lm_kwargs = cfg.get_lm_kwargs()
    dspy.configure(lm=dspy.LM(cfg.optimizer_model, **lm_kwargs))

    # Build dspy.Example dataset from traces.
    examples = _traces_to_examples(traces, artifact.kind)
    if len(examples) < 3:
        return OptimizationOutcome(
            artifact_id=artifact.artifact_id,
            status="error",
            rejection_reason=f"not enough usable examples: {len(examples)}",
            cost_usd=0.0,
        )

    n = len(examples)
    n_train = max(1, n // 2)
    n_val = max(1, (n - n_train) // 2)
    train = examples[:n_train]
    val = examples[n_train:n_train + n_val]
    holdout = examples[n_train + n_val:] or val

    # Composite metric: judge + signal (no user metric for dogfood).
    judge_cfg = JudgeConfig(model=cfg.eval_model, dimensions=tuple(reg_judge_dimensions(reg)))
    metric = build_composite_metric(
        user_metric=None,
        judge_config=judge_cfg,
        signals_provider=lambda trace: compute_signal_score(
            error_in_run=bool(trace.get("signals", {}).get("errors", 0)),
            retry_pattern=bool(trace.get("signals", {}).get("retries", 0)),
            user_correction=bool(trace.get("signals", {}).get("user_correction")),
            latency_outlier=False,
        ),
    )

    outcome = optimize_artifact(
        artifact=artifact,
        train_examples=train,
        val_examples=val,
        holdout_examples=holdout,
        metric=metric,
        optimizer_model=cfg.optimizer_model,
        budget=budget,
        judge_dimensions=judge_cfg.dimensions,
    )
    return outcome


def reg_judge_dimensions(reg) -> tuple:
    """Look up judge dimensions from the agent's _evolution_meta (class attribute).

    Falls back to ('correctness',) when the meta dict isn't populated.
    """
    try:
        module_path, cls_name = reg.module.split(":")
        import importlib
        cls = getattr(importlib.import_module(module_path), cls_name)
        return getattr(cls, "_evolution_meta", {}).get("judge_dimensions", ("correctness",))
    except Exception:  # noqa: BLE001
        return ("correctness",)


def _traces_to_examples(traces: list[dict], kind: str) -> list:
    """Convert TraceRecord dicts to dspy.Example list.

    For prompt kind: (user_input, expected_output) where user_input is the
    serialised trace input and expected_output is the recorded agent output
    (treats current behaviour as the target — what GEPA is optimizing AGAINST,
    not toward; this gives the judge concrete pairs to score).

    For tool kind: (user_intent, expected_output) similarly.
    """
    import dspy
    examples = []
    for t in traces:
        inp = t.get("input")
        if isinstance(inp, dict):
            user_text = inp.get("q") or " ".join(f"{k}={v}" for k, v in inp.items())
        else:
            user_text = str(inp)
        out = t.get("output")
        if out is None:
            continue
        if kind == "tool":
            ex = dspy.Example(user_intent=str(user_text), expected_output=str(out)).with_inputs("user_intent")
        else:
            ex = dspy.Example(user_input=str(user_text), expected_output=str(out)).with_inputs("user_input")
        ex.trace = t
        examples.append(ex)
    return examples


def emit_patch_for_outcome(
    *,
    outcome: OptimizationOutcome,
    artifact: EvolvableArtifact,
    optimized_text: str,
    agent_name: str,
) -> Path:
    """Generate output/<agent>/<ts>/changes.patch for apply='patch' mode."""
    from evolution.sdk.ast_writer import rewrite_artifact_text, generate_unified_diff
    from datetime import datetime, timezone

    original = artifact.source_file.read_text()
    new_src = rewrite_artifact_text(artifact, new_text=optimized_text)
    diff = generate_unified_diff(
        artifact.source_file, original_text=original, new_text=new_src,
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path("output") / agent_name / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    patch_path = out_dir / "changes.patch"
    patch_path.write_text(diff)
    return patch_path


if __name__ == "__main__":
    raise SystemExit(main())
