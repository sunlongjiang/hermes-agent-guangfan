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

# ── Module-level constants ───────────────────────────────────────────────────

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


# ── TBLiteBenchmarkGate ──────────────────────────────────────────────────────

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

    # ── Pre-flight validators ──────────────────────────────────────────────

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
                    f"[yellow]⚠ dataset_revision_hash mismatch: "
                    f"anchor={anchor_revision[:12]} but live HF="
                    f"{live_revision[:12]}. Dataset upgraded since "
                    f"calibration — cache will invalidate via "
                    f"compute_artifact_hash. Continuing.[/yellow]"
                )

    # ── Virtual Prompt Overlay (D-09) ────────────────────────────────────────

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
        #
        # CR-01 fix (2026-05-19): chain the edits through overlay_path so
        # each iteration preserves the prior iteration's evolved section.
        # write_back_section ALWAYS reads from its first arg and writes
        # full file body to dest, so passing the target as the source
        # would overwrite earlier evolved sections each loop iteration.
        # Using overlay_path as BOTH source and dest threads edits
        # cumulatively.
        shutil.copy2(self._target_path, overlay_path)
        sorted_evolved = sorted(
            evolved_sections,
            key=lambda s: s.line_range[0],
            reverse=True,
        )
        for sec in sorted_evolved:
            write_back_section(
                overlay_path,
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

    # ── Risk_Score algorithm (D-01 + D-02) ───────────────────────────────────

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

    # ── Main entrypoints ──────────────────────────────────────────────────────

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
