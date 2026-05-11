"""Phase 15 Wave 2 tests for evolution/tools/think_metrics.py.

RED state in Wave 0: think_metrics module does not yet exist. Wave 2 will
implement the module and turn these tests GREEN. Wave 0 lays the test
contract so Wave 2 implementer has a concrete checklist.

Test groups (RESEARCH §10.2):
- TestAmbiguousFilter: D-13 子集过滤
- TestThreeGate: D-14 三重 AND 门 + D-16 small-sample skip
- TestDualAPI: D-15 + §5.1 函数式 / 类式 API 对称性
- TestSampler: D-17 latency / reasoning-token sampler
- TestGuard: Pitfall 12 守门 — think_metrics 不新增 GEPA metric
"""
import json
from unittest.mock import MagicMock

import pytest


pytest.importorskip("dspy")
import dspy

from evolution.tools.tool_dataset import ToolSelectionExample


# ── TestAmbiguousFilter ──────────────────────────────────────────────────

class TestAmbiguousFilter:
    def test_filter_correct(self):
        examples = [
            ToolSelectionExample(task_description="a", correct_tool="t1", confuser_tools=[]),
            ToolSelectionExample(task_description="b", correct_tool="t1", confuser_tools=["t2"]),
            ToolSelectionExample(task_description="c", correct_tool="t1", confuser_tools=["t2", "t3"]),
            ToolSelectionExample(task_description="d", correct_tool="t1", confuser_tools=["t2", "t3", "t4"]),
        ]
        ambiguous = [ex for ex in examples if len(ex.confuser_tools) >= 2]
        assert len(ambiguous) == 2
        assert ambiguous[0].task_description == "c"
        assert ambiguous[1].task_description == "d"


# ── TestThreeGate ────────────────────────────────────────────────────────

class TestThreeGate:
    """D-14 三重 AND 门 — full regression / ambiguous improvement / latency budget."""

    def test_full_regression_within(self):
        from evolution.tools.think_metrics import ThinkABGate
        gate = ThinkABGate()
        result = gate.check(
            think_on_holdout_score=0.748,
            think_off_holdout_score=0.745,
            ambiguous_think_on_score=0.643,
            ambiguous_think_off_score=0.571,
            ambiguous_sample_size=14,
            latency_p95_seconds=3.94,
        )
        assert result["gates"]["full_regression_gate_passed"] is True

    def test_full_regression_fails(self):
        from evolution.tools.think_metrics import ThinkABGate
        gate = ThinkABGate()
        result = gate.check(
            think_on_holdout_score=0.700,
            think_off_holdout_score=0.750,  # 差 -5pp,超 2pp tolerance
            ambiguous_think_on_score=0.643,
            ambiguous_think_off_score=0.571,
            ambiguous_sample_size=14,
            latency_p95_seconds=3.94,
        )
        assert result["gates"]["full_regression_gate_passed"] is False
        assert result["passed"] is False

    def test_ambiguous_improves(self):
        from evolution.tools.think_metrics import ThinkABGate
        gate = ThinkABGate()
        result = gate.check(
            think_on_holdout_score=0.748,
            think_off_holdout_score=0.745,
            ambiguous_think_on_score=0.643,
            ambiguous_think_off_score=0.571,  # +7.2pp,>3pp
            ambiguous_sample_size=14,
            latency_p95_seconds=3.94,
        )
        assert result["gates"]["ambiguous_gate_passed"] is True

    def test_ambiguous_below_3pp_fails(self):
        from evolution.tools.think_metrics import ThinkABGate
        gate = ThinkABGate()
        result = gate.check(
            think_on_holdout_score=0.748,
            think_off_holdout_score=0.745,
            ambiguous_think_on_score=0.580,
            ambiguous_think_off_score=0.560,  # +2pp,<3pp
            ambiguous_sample_size=14,
            latency_p95_seconds=3.94,
        )
        assert result["gates"]["ambiguous_gate_passed"] is False
        assert result["passed"] is False

    def test_latency_within(self):
        from evolution.tools.think_metrics import ThinkABGate
        gate = ThinkABGate()
        result = gate.check(
            think_on_holdout_score=0.748,
            think_off_holdout_score=0.745,
            ambiguous_think_on_score=0.643,
            ambiguous_think_off_score=0.571,
            ambiguous_sample_size=14,
            latency_p95_seconds=3.94,  # ≤5.0
        )
        assert result["gates"]["latency_gate_passed"] is True

    def test_latency_over_budget_fails(self):
        from evolution.tools.think_metrics import ThinkABGate
        gate = ThinkABGate()
        result = gate.check(
            think_on_holdout_score=0.748,
            think_off_holdout_score=0.745,
            ambiguous_think_on_score=0.643,
            ambiguous_think_off_score=0.571,
            ambiguous_sample_size=14,
            latency_p95_seconds=6.20,  # >5.0
        )
        assert result["gates"]["latency_gate_passed"] is False
        assert result["passed"] is False

    @pytest.mark.parametrize(
        "full_pass,ambig_pass,latency_pass,expected_overall",
        [
            (True, True, True, True),
            (False, True, True, False),
            (True, False, True, False),
            (True, True, False, False),
            (False, False, True, False),
            (True, False, False, False),
            (False, True, False, False),
            (False, False, False, False),
        ],
    )
    def test_three_and_logic(self, full_pass, ambig_pass, latency_pass, expected_overall):
        """Parametric 2^3 = 8 行 truth-table — 验证三 AND 逻辑。"""
        from evolution.tools.think_metrics import ThinkABGate
        gate = ThinkABGate()
        # Pick numbers that flip each gate
        full_on = 0.748 if full_pass else 0.700
        full_off = 0.745 if full_pass else 0.750
        ambig_on = 0.643 if ambig_pass else 0.580
        ambig_off = 0.571 if ambig_pass else 0.560
        latency = 3.94 if latency_pass else 6.20
        result = gate.check(
            think_on_holdout_score=full_on,
            think_off_holdout_score=full_off,
            ambiguous_think_on_score=ambig_on,
            ambiguous_think_off_score=ambig_off,
            ambiguous_sample_size=14,
            latency_p95_seconds=latency,
        )
        assert result["passed"] is expected_overall

    def test_small_sample_skip(self):
        """D-16: ambiguous_sample_size < 5 → 跳过 ambiguous 门,仍跑 full + latency。"""
        from evolution.tools.think_metrics import ThinkABGate
        gate = ThinkABGate()
        result = gate.check(
            think_on_holdout_score=0.748,
            think_off_holdout_score=0.745,
            ambiguous_think_on_score=0.580,
            ambiguous_think_off_score=0.560,  # 本应 fail ambiguous
            ambiguous_sample_size=3,           # <5 → skip
            latency_p95_seconds=3.94,
        )
        assert result["ambiguous_gate_skipped"] is True
        assert result["gates"]["ambiguous_gate_passed"] is True  # skip = pass
        assert result["passed"] is True


# ── TestDualAPI ──────────────────────────────────────────────────────────

class TestDualAPI:
    def test_function_returns_constraint_result(self):
        """check_think_ab_gate(...) 返回 ConstraintResult,details 是 sort_keys json。"""
        from evolution.tools.think_metrics import check_think_ab_gate
        from evolution.core.constraints import ConstraintResult
        result = check_think_ab_gate(
            think_on_holdout_score=0.748,
            think_off_holdout_score=0.745,
            ambiguous_think_on_score=0.643,
            ambiguous_think_off_score=0.571,
            ambiguous_sample_size=14,
            latency_p95_seconds=3.94,
        )
        assert isinstance(result, ConstraintResult)
        assert result.constraint_name == "think_ab_gate"
        assert result.passed is True
        details = json.loads(result.details)
        for key in (
            "full_regression_delta",
            "ambiguous_delta",
            "latency_p95_seconds",
            "ambiguous_sample_size",
            "ambiguous_gate_skipped",
            "gates",
        ):
            assert key in details

    def test_class_returns_dict(self):
        """ThinkABGate.check() 返回 dict(完整 metrics)。"""
        from evolution.tools.think_metrics import ThinkABGate
        gate = ThinkABGate()
        result = gate.check(
            think_on_holdout_score=0.748,
            think_off_holdout_score=0.745,
            ambiguous_think_on_score=0.643,
            ambiguous_think_off_score=0.571,
            ambiguous_sample_size=14,
            latency_p95_seconds=3.94,
        )
        assert isinstance(result, dict)
        for key in (
            "passed",
            "full_regression_delta",
            "ambiguous_delta",
            "ambiguous_sample_size",
            "ambiguous_gate_skipped",
            "latency_p95_seconds",
            "gates",
            "message",
        ):
            assert key in result


# ── TestSampler ──────────────────────────────────────────────────────────

class TestSampler:
    def test_emits_p50_p95_mean(self):
        """sample_latency_tokens 返回 stats 含 p50 / p95 / mean。"""
        from evolution.tools.think_metrics import sample_latency_tokens
        mock_module = MagicMock(return_value=dspy.Prediction(
            selected_tool="t1",
            selected_params="{}",
            reasoning="short reasoning",
            reasoning_tokens=20,
        ))
        examples = [
            ToolSelectionExample(task_description=f"t{i}", correct_tool="t1", confuser_tools=[])
            for i in range(10)
        ]
        mock_lm = MagicMock()
        result = sample_latency_tokens(mock_module, examples, mock_lm)
        assert "stats" in result
        for k in ("latency_p50", "latency_p95", "latency_mean",
                  "reasoning_token_p50", "reasoning_token_p95", "reasoning_token_mean"):
            assert k in result["stats"]
        assert len(result["latency_seconds"]) == 10

    def test_sampler_skips_failed_calls(self):
        """一个 example raise → sampler 不中断,latencies 长度比 input 少 1。"""
        from evolution.tools.think_metrics import sample_latency_tokens

        call_count = {"n": 0}

        def flaky_module(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 3:
                raise RuntimeError("flaky")
            return dspy.Prediction(
                selected_tool="t1",
                selected_params="{}",
                reasoning="ok",
                reasoning_tokens=10,
            )

        examples = [
            ToolSelectionExample(task_description=f"t{i}", correct_tool="t1", confuser_tools=[])
            for i in range(10)
        ]
        mock_lm = MagicMock()
        result = sample_latency_tokens(flaky_module, examples, mock_lm)
        assert len(result["latency_seconds"]) == 9


# ── TestGuard ────────────────────────────────────────────────────────────

def test_no_gepa_metric_added():
    """守 Pitfall 12: think_metrics.py 不新增 GEPA-bound metric(5-param signature)。

    GEPA metric 必须接受 (gold, pred, trace, pred_name, pred_trace) — 5 个位置参数。
    扫描 think_metrics 模块的所有 callable,断 NONE 拥有 5-param 签名(或更多)且
    包含 'metric' 字样的名字。
    """
    import inspect
    from evolution.tools import think_metrics

    for name in dir(think_metrics):
        if not name.startswith("_") and "metric" in name.lower():
            obj = getattr(think_metrics, name)
            if callable(obj) and not inspect.isclass(obj):
                sig = inspect.signature(obj)
                pos_params = [
                    p for p in sig.parameters.values()
                    if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                  inspect.Parameter.POSITIONAL_ONLY)
                ]
                assert len(pos_params) < 5, (
                    f"think_metrics.{name} has {len(pos_params)} positional params — "
                    "looks like a GEPA-bound metric. Phase 15 must NOT introduce new "
                    "GEPA metrics (RESEARCH §1.5)."
                )
