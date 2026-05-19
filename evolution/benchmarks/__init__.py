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
