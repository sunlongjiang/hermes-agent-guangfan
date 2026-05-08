"""Minimal stub for evolve_tool_params (Phase 13 CLI shell).

Purpose (Phase 13 wave 3):
    Phase 13 plan 13-07 creates the v1 baseline hard-gate machinery in
    `evolution.tools.v1_baseline_gate`. The Wave 0 RED tests for that gate
    (`tests/tools/test_v1_baseline_gate.py`) reference the symbols
    `check_v1_baseline_gate` and `compute_v1_baseline` via the import path
    `evolution.tools.evolve_tool_params` (since 13-08 will eventually expose
    them through the CLI). To turn those Wave 0 tests GREEN at the end of
    13-07 -- without preempting 13-08's CLI scope -- this module re-exports
    the gate helpers from `evolution.tools.v1_baseline_gate`.

Phase 13 plan 13-08 will replace this module with the full Click CLI
(end-to-end pipeline including ToolModule, joint metric, ParamConsistency,
CostTracker, persist_per_tool_rates, V1BaselineGate, ABORTED/FAILED dirs).
The re-exports below MUST remain stable across 13-08 so existing tests
keep passing.

Phase 13 scope guard (CONTEXT.md): this module MUST NOT import or invoke
`evolution.tools.tool_loader.write_back_description`. Phase 13 only writes
to `output/tools/`; write-back is deferred to Phase 22.
"""

from evolution.tools.v1_baseline_gate import (
    V1BaselineGate,
    check_v1_baseline_gate,
    compute_v1_baseline,
)

__all__ = [
    "V1BaselineGate",
    "check_v1_baseline_gate",
    "compute_v1_baseline",
]
