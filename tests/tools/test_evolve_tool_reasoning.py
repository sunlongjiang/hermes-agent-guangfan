"""Phase 15 Wave 3 integration tests for evolution/tools/evolve_tool_reasoning.py.

RED state in Wave 0: evolve_tool_reasoning module does not yet exist. Wave 3
implements the CLI; Wave 4 fills the e2e smoke. Wave 0 lays the test contract.

Tests modeled on test_evolve_tool_params_cli.py — Click CliRunner + patch on
internal seams (_load_tool_descriptions, _load_dataset, dspy.GEPA, dspy.LM,
V1BaselineGate.check, ThinkABGate.check, etc.).
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip("dspy")
import dspy
from click.testing import CliRunner

from evolution.tools.tool_loader import ToolDescription, ToolParam
from evolution.tools.tool_dataset import ToolSelectionExample


# ── Shared fake fixtures ────────────────────────────────────────────────

def _fake_tool() -> ToolDescription:
    return ToolDescription(
        name="search",
        file_path=Path("/fake/search.py"),
        description="Search for stuff",
        params=[ToolParam(name="q", type="string", required=True, description="query")],
    )


def _fake_examples(n: int = 8) -> list:
    """Returns MagicMock-shaped objects for mock holdout dataset."""
    out = []
    for i in range(n):
        ex = MagicMock()
        ex.task_description = f"task_{i}"
        ex.correct_tool = "search"
        ex.correct_params = "{}"
        # half ambiguous (len(confuser_tools) >= 2)
        ex.confuser_tools = ["other_a", "other_b"] if i % 2 == 0 else []
        out.append(ex)
    return out


# ── TEST: Phase 16 Wave 0 — raw_predictions wiring ──────────────────────


def test_metrics_includes_per_tool_and_raw(mock_reasoning_module, monkeypatch):
    """Phase 16 Wave 0 (D-12): evolve_tool_reasoning metrics.json gains
    per_tool_*_rates + raw_predictions; raw_predictions populated from
    think-on path via _score_with_predictions.

    BLOCKER 4: exercises real _score_with_predictions helper (the new wiring
    code) + real persist_per_tool_rates / persist_raw_predictions. Mirrors
    the inline CLI wiring at evolve_tool_reasoning.py:470-471 + :563-567.
    """
    pytest.importorskip("dspy")
    import dspy

    from evolution.tools.evolve_tool_reasoning import _score_with_predictions
    from evolution.tools.tool_metric import (
        CrossToolRegressionChecker,
        persist_per_tool_rates,
        persist_raw_predictions,
    )

    # Build a small holdout fixture with difficulty + confuser_tools
    holdout = []
    for i in range(4):
        ex = dspy.Example(
            task_description=f"task {i}",
            correct_tool="search",
            confuser_tools=["read_file", "browse"],
            difficulty="easy" if i < 2 else "hard",
        ).with_inputs("task_description")
        holdout.append(ex)

    mock_lm = MagicMock()

    # _score_with_predictions uses dspy.context(lm=lm); patch it to no-op
    with patch("evolution.tools.evolve_tool_reasoning.dspy.context") as mock_ctx:
        mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        # think-off and think-on share the mock module (selector returns search)
        th_off, tool_pairs_off, _ = _score_with_predictions(mock_reasoning_module, holdout, mock_lm)
        th_on, tool_pairs_on, raw_preds_on = _score_with_predictions(mock_reasoning_module, holdout, mock_lm)

    # Helper assertions — real wiring exercised
    assert th_on == 1.0  # mock returns "search" === correct_tool every time
    assert len(tool_pairs_off) == 4
    assert len(tool_pairs_on) == 4
    assert len(raw_preds_on) == 4

    # Replicate CLI wiring at evolve_tool_reasoning.py:563-567
    regression_checker = CrossToolRegressionChecker()
    baseline_rates = regression_checker.compute_per_tool_rates(tool_pairs_off)
    evolved_rates = regression_checker.compute_per_tool_rates(tool_pairs_on)
    metrics = {
        "timestamp": "test",
        "status": "SUCCESS",
        "think_ab_gate": {"passed": True},  # Phase 15 既有字段未被破坏
    }
    metrics = persist_per_tool_rates(metrics, baseline_rates, evolved_rates)
    metrics = persist_raw_predictions(metrics, raw_preds_on)

    # Phase 16 D-12 schema assertions
    assert "per_tool_baseline_rates" in metrics
    assert "per_tool_evolved_rates" in metrics
    assert "raw_predictions" in metrics
    assert "think_ab_gate" in metrics  # Phase 15 既有字段保留
    assert isinstance(metrics["raw_predictions"], list)
    assert len(metrics["raw_predictions"]) == 4
    if metrics["raw_predictions"]:
        first = metrics["raw_predictions"][0]
        assert set(first.keys()) == {"correct_tool", "selected_tool", "difficulty", "num_available_tools"}
        # num_available_tools = len(confuser_tools) + 1 = 2 + 1 = 3
        assert first["num_available_tools"] == 3
        assert first["difficulty"] in {"easy", "hard"}


# ── TEST 1: dry-run schema ──────────────────────────────────────────────

def test_dry_run_emits_setup(tmp_path):
    """--dry-run 退出 0 + echo Phase 15 dry-run schema 字段(RESEARCH §6.4)."""
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)
    assert evolve is not None, "evolve_tool_reasoning must expose Click `evolve` or `main`"

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))):
        runner = CliRunner()
        result = runner.invoke(evolve, ["--dry-run", "--iterations", "1"], catch_exceptions=False)

    assert result.exit_code == 0, f"dry-run should exit 0; got {result.exit_code}\n{result.output}"
    output = result.output
    assert "ambiguous_subset_size=" in output
    assert "ambiguous_gate_skipped=" in output
    assert "reasoning_tokens_cap=200" in output
    assert "latency_p95_budget_sec=5.0" in output
    assert "ambiguous_improvement_pp=3.0" in output
    assert "full_regression_tolerance_pp=2.0" in output
    assert "max_metric_calls_estimate=" in output
    assert "DRY RUN" in output


# ── TEST 2: baseline/evolved module constructor split ───────────────────

def test_baseline_module_off_evolved_on_constructed():
    """patch ToolModule.__init__ → CLI 构造 2 个 ToolModule:第 1 个 enable_reasoning=False,第 2 个 True."""
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)

    init_calls = []

    def capture_init(self, tool_descriptions, *, enable_reasoning=False):
        init_calls.append(enable_reasoning)
        self.tools = {}
        self._frozen_tool_desc = {}
        self._frozen_tools = {}
        self._tool_names = []
        self.selector = MagicMock()
        self.reasoner = None if not enable_reasoning else MagicMock()

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))), \
         patch("evolution.tools.evolve_tool_reasoning.ToolModule.__init__", capture_init), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM"):
        mock_gepa.return_value.compile.return_value = MagicMock()
        runner = CliRunner()
        runner.invoke(evolve, ["--iterations", "1", "--max-cost-usd", "5.0"], catch_exceptions=True)

    # First call must be enable_reasoning=False, second True.
    assert init_calls.count(False) >= 1
    assert init_calls.count(True) >= 1


# ── TEST 3: V1BaselineGate called twice ─────────────────────────────────

def test_dual_v1_baseline_calls():
    """V1BaselineGate.check 被调 2 次:think-off 与 think-on 各一次."""
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM"), \
         patch("evolution.tools.evolve_tool_reasoning.V1BaselineGate") as mock_v1_cls:
        mock_gepa.return_value.compile.return_value = MagicMock()
        mock_v1_inst = MagicMock()
        mock_v1_inst.check.return_value = {"passed": True, "v1_baseline_holdout": 0.731, "delta": 0.02}
        mock_v1_cls.return_value = mock_v1_inst
        runner = CliRunner()
        runner.invoke(evolve, ["--iterations", "1", "--max-cost-usd", "5.0"], catch_exceptions=True)
        assert mock_v1_inst.check.call_count == 2


# ── TEST 4: ThinkABGate failure → FAILED_ dir ───────────────────────────

def test_think_ab_gate_failure_writes_failed(tmp_path, monkeypatch):
    """ThinkABGate.check returns passed=False → output/tools_reasoning/FAILED_<ts>/ + exit 1."""
    monkeypatch.chdir(tmp_path)
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM"), \
         patch("evolution.tools.evolve_tool_reasoning.ThinkABGate") as mock_gate_cls:
        mock_gepa.return_value.compile.return_value = MagicMock()
        mock_gate = MagicMock()
        mock_gate.check.return_value = {
            "passed": False,
            "full_regression_delta": 0.001,
            "ambiguous_delta": -0.05,
            "latency_p95_seconds": 3.94,
            "ambiguous_sample_size": 4,
            "ambiguous_gate_skipped": False,
            "gates": {
                "full_regression_gate_passed": True,
                "ambiguous_gate_passed": False,
                "latency_gate_passed": True,
            },
            "message": "ambiguous gate failed",
        }
        mock_gate_cls.return_value = mock_gate

        runner = CliRunner()
        result = runner.invoke(evolve, ["--iterations", "1", "--max-cost-usd", "5.0"], catch_exceptions=True)

    assert result.exit_code == 1, f"Expected exit 1 on think_ab failure, got {result.exit_code}\n{result.output}"
    failed_dirs = list((tmp_path / "output" / "tools_reasoning").glob("FAILED_*"))
    assert len(failed_dirs) == 1
    metrics_path = failed_dirs[0] / "metrics.json"
    assert metrics_path.exists()
    metrics = json.loads(metrics_path.read_text())
    assert "FAILED" in metrics.get("status", "").upper() or "THINK_AB" in metrics.get("status", "").upper()


# ── TEST 5: v1 gate fail on think-on → FAILED_ dir ──────────────────────

def test_v1_failed_think_on_writes_failed_dir(tmp_path, monkeypatch):
    """V1BaselineGate.check think-on FAILED → FAILED_<ts>/."""
    monkeypatch.chdir(tmp_path)
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)

    call_n = {"n": 0}

    def v1_check_side(**kwargs):
        call_n["n"] += 1
        # First call (think-off) passes; second call (think-on) fails
        return {
            "passed": call_n["n"] == 1,
            "v1_baseline_holdout": 0.731,
            "delta": -0.05 if call_n["n"] == 2 else 0.02,
            "message": "v1 gate FAILED" if call_n["n"] == 2 else "v1 gate OK",
        }

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM"), \
         patch("evolution.tools.evolve_tool_reasoning.V1BaselineGate") as mock_v1_cls:
        mock_gepa.return_value.compile.return_value = MagicMock()
        mock_v1_inst = MagicMock()
        mock_v1_inst.check.side_effect = v1_check_side
        mock_v1_cls.return_value = mock_v1_inst

        runner = CliRunner()
        result = runner.invoke(evolve, ["--iterations", "1", "--max-cost-usd", "5.0"], catch_exceptions=True)

    assert result.exit_code == 1
    failed_dirs = list((tmp_path / "output" / "tools_reasoning").glob("FAILED_*"))
    assert len(failed_dirs) == 1


# ── TEST 6: metrics.json schema ─────────────────────────────────────────

def test_metrics_json_schema(tmp_path, monkeypatch):
    """成功路径 — metrics.json 含全部 Phase 15 schema 字段(RESEARCH §6.2)."""
    monkeypatch.chdir(tmp_path)
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM"):
        mock_gepa.return_value.compile.return_value = MagicMock()

        runner = CliRunner()
        runner.invoke(evolve, ["--iterations", "1", "--max-cost-usd", "5.0"], catch_exceptions=True)

    success_dirs = [
        d for d in (tmp_path / "output" / "tools_reasoning").glob("*")
        if d.is_dir() and not d.name.startswith(("FAILED_", "ABORTED_"))
    ]
    assert len(success_dirs) >= 1, "expected SUCCESS output dir"
    metrics_path = success_dirs[0] / "metrics.json"
    assert metrics_path.exists()
    metrics = json.loads(metrics_path.read_text())
    required_keys = (
        "think_on_score", "think_off_score",
        "ambiguous_think_on", "ambiguous_think_off",
        "reasoning_token_stats", "latency_stats",
        "think_ab_gate", "v1_gate_passed",
        "ambiguous_subset_size", "ambiguous_gate_skipped",
        "iterations", "eval_model",
    )
    for k in required_keys:
        assert k in metrics, f"metrics.json missing key: {k}"


# ── TEST 7: reasoning_prompt.txt + diff.txt ─────────────────────────────

def test_reasoning_prompt_files(tmp_path, monkeypatch):
    """reasoning_prompt.txt 是 evolved instructions plain string;diff.txt 是 unified diff."""
    monkeypatch.chdir(tmp_path)
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM"):
        mock_gepa.return_value.compile.return_value = MagicMock()
        runner = CliRunner()
        runner.invoke(evolve, ["--iterations", "1", "--max-cost-usd", "5.0"], catch_exceptions=True)

    success_dirs = [
        d for d in (tmp_path / "output" / "tools_reasoning").glob("*")
        if d.is_dir() and not d.name.startswith(("FAILED_", "ABORTED_"))
    ]
    assert (success_dirs[0] / "reasoning_prompt.txt").exists()
    assert (success_dirs[0] / "diff.txt").exists()
    diff_content = (success_dirs[0] / "diff.txt").read_text()
    assert "---" in diff_content or "+++" in diff_content or "@@" in diff_content, \
        "diff.txt should be unified diff format"


# ── TEST 8: ab_comparison.json schema ───────────────────────────────────

def test_ab_comparison_schema(tmp_path, monkeypatch):
    """ab_comparison.json 是 JSON array,每条含 task_id / selected_off / selected_on / etc."""
    monkeypatch.chdir(tmp_path)
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM"):
        mock_gepa.return_value.compile.return_value = MagicMock()
        runner = CliRunner()
        runner.invoke(evolve, ["--iterations", "1", "--max-cost-usd", "5.0"], catch_exceptions=True)

    success_dirs = [
        d for d in (tmp_path / "output" / "tools_reasoning").glob("*")
        if d.is_dir() and not d.name.startswith(("FAILED_", "ABORTED_"))
    ]
    ab_path = success_dirs[0] / "ab_comparison.json"
    assert ab_path.exists()
    data = json.loads(ab_path.read_text())
    assert isinstance(data, list)
    assert len(data) >= 1
    sample = data[0]
    required = (
        "task_id", "task_description", "correct_tool",
        "selected_off", "selected_on",
        "is_correct_off", "is_correct_on",
        "is_ambiguous", "confuser_tools",
        "reasoning_text_on", "reasoning_tokens_on",
        "latency_seconds_off", "latency_seconds_on",
    )
    for k in required:
        assert k in sample, f"ab_comparison row missing key: {k}"


# ── TEST 9: output dir isolation ────────────────────────────────────────

def test_output_isolated_directory(tmp_path, monkeypatch):
    """所有写盘 path 以 output/tools_reasoning/ 起头,不触达 output/tools/."""
    monkeypatch.chdir(tmp_path)
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM"):
        mock_gepa.return_value.compile.return_value = MagicMock()
        runner = CliRunner()
        runner.invoke(evolve, ["--iterations", "1", "--max-cost-usd", "5.0"], catch_exceptions=True)

    # output/tools_reasoning/ 必有内容
    tr_root = tmp_path / "output" / "tools_reasoning"
    assert tr_root.exists() and any(tr_root.iterdir())
    # output/tools/ 必须不存在或为空(被 Phase 15 触碰即违规)
    tools_root = tmp_path / "output" / "tools"
    if tools_root.exists():
        assert not any(tools_root.iterdir()), (
            f"Phase 15 must not write to output/tools/ — found: {list(tools_root.iterdir())}"
        )


# ── TEST 10: cost cap → ABORTED_ ─────────────────────────────────────────

def test_cost_cap_aborts(tmp_path, monkeypatch):
    """cost > max_cost_usd → ABORTED_<ts>/aborted.json,exit 2."""
    monkeypatch.chdir(tmp_path)
    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)

    from evolution.core.cost_tracker import CostBudgetExceeded

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=[_fake_tool()]), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(_fake_examples(8), _fake_examples(4), _fake_examples(8))), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM"):
        mock_gepa.return_value.compile.side_effect = CostBudgetExceeded("cost exceeded $5.00")
        runner = CliRunner()
        result = runner.invoke(evolve, ["--iterations", "1", "--max-cost-usd", "5.0"], catch_exceptions=True)

    assert result.exit_code == 2, f"expected exit 2 on cost cap, got {result.exit_code}\n{result.output}"
    aborted_dirs = list((tmp_path / "output" / "tools_reasoning").glob("ABORTED_*"))
    assert len(aborted_dirs) == 1
    aborted_json = aborted_dirs[0] / "aborted.json"
    assert aborted_json.exists()


# ── TEST 11: e2e mock pipeline (Wave 4 — Plan 15-05) ────────────────────

def test_e2e_mock_pipeline(tmp_path, monkeypatch):
    """End-to-end mock LM pipeline smoke (Plan 05 Wave 4).

    Mocks LM + GEPA + ToolModule.forward externally but runs REAL
    V1BaselineGate / ThinkABGate / sample_latency_tokens / _build_ab_comparison /
    _write_* to verify the full 16-step pipeline wires end-to-end without
    crashes, writes all 4 output files, and produces metrics.json with the
    complete Phase 15 schema.
    """
    monkeypatch.chdir(tmp_path)

    evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_reasoning")
    evolve_cmd = getattr(evolve_mod, "evolve", None) or getattr(evolve_mod, "main", None)
    assert evolve_cmd is not None

    # Build 10 mock holdout examples — 5 ambiguous (confuser len >= 2), 5 non-ambiguous
    def _mock_example(i: int):
        ex = MagicMock()
        ex.task_description = f"task_{i}: find or read a file"
        ex.correct_tool = "search" if i % 2 == 0 else "read_file"
        ex.correct_params = '{"q": "foo"}'
        ex.confuser_tools = ["read_file", "ls"] if i < 5 else ["ls"]
        return ex

    fake_holdout = [_mock_example(i) for i in range(10)]
    fake_train = [_mock_example(i + 100) for i in range(20)]
    fake_val = [_mock_example(i + 200) for i in range(10)]

    # 3 fake tools (search / read_file / ls)
    fake_tools = [
        ToolDescription(
            name=n,
            file_path=Path(f"/fake/{n}.py"),
            description=f"Tool {n} for fake use",
            params=[ToolParam(name="q", type="string", required=True, description="query")],
        )
        for n in ("search", "read_file", "ls")
    ]

    # ToolModule.forward canned predictions — reasoning_tokens > 0 when reasoner set
    def _fwd_patched(self, task_description):
        has_reasoner = getattr(self, "reasoner", None) is not None
        return dspy.Prediction(
            selected_tool="search",
            selected_params='{"q": "x"}',
            reasoning=(
                "search fits better than read_file for query-shaped tasks"
                if has_reasoner else ""
            ),
            reasoning_tokens=(14 if has_reasoner else 0),
        )

    # GEPA.compile returns the student module as-is (no-op optimization)
    def _gepa_compile(student, trainset=None, valset=None):
        return student

    with patch("evolution.tools.evolve_tool_reasoning._load_tool_descriptions",
               return_value=fake_tools), \
         patch("evolution.tools.evolve_tool_reasoning._load_dataset",
               return_value=(fake_train, fake_val, fake_holdout)), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.LM",
               return_value=MagicMock()), \
         patch("evolution.tools.evolve_tool_reasoning.dspy.GEPA") as mock_gepa, \
         patch("evolution.tools.tool_module.ToolModule.forward", _fwd_patched):
        mock_gepa.return_value.compile.side_effect = _gepa_compile

        runner = CliRunner()
        result = runner.invoke(
            evolve_cmd,
            ["--iterations", "1", "--max-cost-usd", "5.0", "--eval-source", "load"],
            catch_exceptions=False,
        )

    # Pipeline did not crash — SUCCESS (0) or gate FAILED (1) both acceptable
    assert result.exit_code in (0, 1), (
        f"unexpected exit code {result.exit_code}\n"
        f"Output:\n{result.output}"
    )

    # Output dir structure
    tr_root = tmp_path / "output" / "tools_reasoning"
    assert tr_root.exists(), f"output/tools_reasoning/ must exist; got:\n{result.output}"
    all_dirs = [d for d in tr_root.iterdir() if d.is_dir()]
    assert len(all_dirs) >= 1, f"expected >= 1 output dir; got {all_dirs}"
    out_dir = all_dirs[0]

    # 4 output files present
    for fname in ("metrics.json", "reasoning_prompt.txt", "diff.txt", "ab_comparison.json"):
        assert (out_dir / fname).exists(), f"missing {fname} in {out_dir}"

    # metrics.json schema — RESEARCH §6.2 required keys
    metrics = json.loads((out_dir / "metrics.json").read_text())
    for key in (
        "think_on_score", "think_off_score",
        "ambiguous_think_on", "ambiguous_think_off",
        "reasoning_token_stats", "latency_stats",
        "think_ab_gate", "v1_gate_passed",
        "ambiguous_subset_size", "ambiguous_gate_skipped",
        "iterations", "eval_model", "status", "timestamp",
    ):
        assert key in metrics, (
            f"metrics.json missing key: {key}\nAvailable: {sorted(metrics.keys())}"
        )

    # Deterministic: exactly 5 ambiguous examples in fake_holdout (i < 5)
    assert metrics["ambiguous_subset_size"] == 5, (
        f"ambiguous_subset_size mismatch: expected 5, got {metrics['ambiguous_subset_size']}"
    )

    # ab_comparison.json is JSON array with required keys
    ab_data = json.loads((out_dir / "ab_comparison.json").read_text())
    assert isinstance(ab_data, list)
    assert len(ab_data) >= 1
    required_keys = {
        "task_id", "task_description", "correct_tool",
        "selected_off", "selected_on",
        "is_correct_off", "is_correct_on",
        "is_ambiguous", "confuser_tools",
        "reasoning_text_on", "reasoning_tokens_on",
        "latency_seconds_off", "latency_seconds_on",
    }
    missing = required_keys - set(ab_data[0].keys())
    assert not missing, f"ab_comparison[0] missing keys: {missing}"

    # Physical isolation: output/tools/ must be absent or empty (D-11)
    tools_dir = tmp_path / "output" / "tools"
    if tools_dir.exists():
        assert not any(tools_dir.iterdir()), (
            f"Phase 15 must NOT write to output/tools/; found: {list(tools_dir.iterdir())}"
        )


# ── Wave 5 (gap closure) tests ────────────────────────────────────────────


def test_score_with_predictions_uses_joint_metric():
    """16-05-G5 (CR-03) — _score_with_predictions uses joint_tool_param_metric,
    same as _safe_score path. Tool name comparison must be case-insensitive
    (.strip().lower()), proving the gate is now apples-to-apples.
    """
    import dspy
    from evolution.tools.evolve_tool_reasoning import _score_with_predictions
    from evolution.tools.tool_metric import joint_tool_param_metric

    # Build 2 examples; one has case-mismatched correct_tool to prove normalization
    ex1 = dspy.Example(
        task_description="read a file",
        correct_tool="Read_File",  # uppercase
        correct_params={},
        confuser_tools=["edit_file"],
        difficulty="easy",
    ).with_inputs("task_description")
    ex2 = dspy.Example(
        task_description="search code",
        correct_tool="search_files",
        correct_params={},
        confuser_tools=["read_file", "list_files"],
        difficulty="medium",
    ).with_inputs("task_description")

    class FakeModule:
        def __init__(self):
            self.calls = []

        def __call__(self, task_description):
            # Return prediction whose selected_tool matches correct_tool (lowercased)
            self.calls.append(task_description)
            if "read a file" in task_description:
                return dspy.Prediction(selected_tool="read_file", selected_params="{}")
            return dspy.Prediction(selected_tool="search_files", selected_params="{}")

    module = FakeModule()
    score, tool_pairs, raw_preds = _score_with_predictions(
        module, [ex1, ex2], lm=None
    )
    # Both should score 1.0 if metric is case-insensitive (joint_tool_param_metric)
    assert score == pytest.approx(1.0), (
        f"case-insensitive joint metric should score 1.0 on Read_File->read_file; "
        f"got {score} — CR-03 not fixed"
    )
    assert len(raw_preds) == 2
    # raw_preds preserves original case (not normalized)
    assert raw_preds[0]["correct_tool"] == "Read_File"


def test_score_with_predictions_logs_per_example_error(capsys):
    """16-05-G6 (WR-07) — per-example exception emits yellow log; partial result returned."""
    import dspy
    from evolution.tools.evolve_tool_reasoning import _score_with_predictions

    ex1 = dspy.Example(
        task_description="will fail",
        correct_tool="x",
        correct_params={},
        confuser_tools=[],
        difficulty="easy",
    ).with_inputs("task_description")
    ex2 = dspy.Example(
        task_description="will succeed",
        correct_tool="y",
        correct_params={},
        confuser_tools=[],
        difficulty="easy",
    ).with_inputs("task_description")

    class FlakyModule:
        def __call__(self, task_description):
            if "fail" in task_description:
                raise RuntimeError("simulated LM failure")
            return dspy.Prediction(selected_tool="y", selected_params="{}")

    score, tool_pairs, raw_preds = _score_with_predictions(
        FlakyModule(), [ex1, ex2], lm=None
    )
    # Only the second example contributes
    assert len(raw_preds) == 1
    assert raw_preds[0]["correct_tool"] == "y"
    # Yellow log captured — Rich console outputs to stdout in test context
    captured = capsys.readouterr()
    assert "holdout example skipped" in captured.out, (
        f"expected per-example yellow log; got stdout: {captured.out!r}"
    )
