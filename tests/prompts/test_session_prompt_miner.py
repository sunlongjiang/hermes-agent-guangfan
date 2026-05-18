"""Tests for evolution/prompts/session_prompt_miner.py — Phase 19 Wave 2.

Covers:
    Task 2.1: skeleton (constants + Candidate + Verdict + Signatures + helpers)
    Task 2.2: __init__ + _fresh_metrics + _load_session + _filter_secrets + _filter_drift
    Task 2.3: 4 _extract_* signal extractors + _judge_candidates
    Task 2.4: mine() orchestration + split_and_duplicate
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import dspy
import pytest


# ── Task 2.1 — Skeleton + Signatures ──────────────────────────────────────────


class TestSkeletonExports:
    """Module-level public API surface check."""

    def test_imports_all_public_symbols(self):
        from evolution.prompts.session_prompt_miner import (
            SessionPromptMiner,
            DEFAULT_MULTIPLIER,
            VALID_SIGNALS,
            Candidate,
            Verdict,
            _multiplier_for,
            ConfirmBehavioralExample,
            DetectUserCorrection,
            split_and_duplicate,
        )

    def test_default_multiplier_exact_four_keys(self):
        from evolution.prompts.session_prompt_miner import DEFAULT_MULTIPLIER
        assert DEFAULT_MULTIPLIER == {
            "user_correction": 3,
            "section_specific_failure": 3,
            "oracle_disagreement": 2,
            "persona_drift": 2,
        }

    def test_valid_signals_derived_from_multiplier(self):
        from evolution.prompts.session_prompt_miner import (
            DEFAULT_MULTIPLIER,
            VALID_SIGNALS,
        )
        assert VALID_SIGNALS == frozenset(DEFAULT_MULTIPLIER.keys())

    def test_candidate_dataclass_fields(self):
        from evolution.prompts.session_prompt_miner import Candidate
        c = Candidate(
            task="t",
            session_path="/x",
            signal="user_correction",
            originally_observed_behavior="ob",
            downstream_context="dc",
        )
        assert c.section_id == ""  # default
        assert callable(c.task_hash)
        h = c.task_hash()
        assert isinstance(h, str) and len(h) == 16

    def test_signatures_subclass_of_dspy_signature(self):
        from evolution.prompts.session_prompt_miner import (
            ConfirmBehavioralExample,
            DetectUserCorrection,
        )
        assert issubclass(ConfirmBehavioralExample, dspy.Signature)
        assert issubclass(DetectUserCorrection, dspy.Signature)

    def test_confirm_behavioral_example_has_five_output_fields(self):
        """W5 fix: validate via __annotations__ public API, NOT __dspy_field_type."""
        from evolution.prompts.session_prompt_miner import ConfirmBehavioralExample
        expected_out = {"verdict", "section_id", "expected_behavior", "difficulty", "rationale"}
        actual_annots = set(ConfirmBehavioralExample.__annotations__.keys())
        missing = expected_out - actual_annots
        assert not missing, f"missing OutputFields: {missing}"

    def test_detect_user_correction_has_is_correction(self):
        from evolution.prompts.session_prompt_miner import DetectUserCorrection
        assert "is_correction" in DetectUserCorrection.__annotations__

    def test_multiplier_for_single_signal(self):
        from evolution.prompts.session_prompt_miner import _multiplier_for
        assert _multiplier_for(["user_correction"]) == 3

    def test_multiplier_for_max_across_signals(self):
        from evolution.prompts.session_prompt_miner import _multiplier_for
        assert _multiplier_for(["user_correction", "persona_drift"]) == 3
        assert _multiplier_for(["oracle_disagreement", "persona_drift"]) == 2

    def test_multiplier_for_empty(self):
        from evolution.prompts.session_prompt_miner import _multiplier_for
        assert _multiplier_for([]) == 1

    def test_multiplier_for_override(self):
        from evolution.prompts.session_prompt_miner import _multiplier_for
        assert _multiplier_for(["user_correction"], {"user_correction": 5}) == 5


# ── Task 2.2 — __init__ + helpers ─────────────────────────────────────────────


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.judge_model = "mock-judge"
    cfg.eval_model = "mock-eval"
    cfg.get_lm_kwargs = MagicMock(return_value={})
    return cfg


class TestConstructorAndHelpers:
    def test_default_construction(self, mock_config):
        from evolution.prompts.session_prompt_miner import (
            SessionPromptMiner,
            VALID_SIGNALS,
        )
        m = SessionPromptMiner(mock_config)
        assert set(m.signals) == set(VALID_SIGNALS)
        assert m.drift_detector is None

    def test_subset_signals(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config, signals=["user_correction"])
        assert m.signals == ["user_correction"]
        assert m.drift_detector is None

    def test_persona_drift_with_thresholds_inits_detector(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        from evolution.prompts.drift_detector import DriftDetector
        m = SessionPromptMiner(
            mock_config,
            signals=["persona_drift"],
            drift_thresholds={"tone": 0.5, "formality": 0.5, "vocabulary": 0.5, "persona": 0.5},
        )
        assert isinstance(m.drift_detector, DriftDetector)

    def test_persona_drift_without_thresholds_graceful_disable(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config, signals=["persona_drift"])
        assert m.drift_detector is None

    def test_fresh_metrics_required_keys(self, mock_config):
        """B3 fix: session_load_failures and jsonl_skipped_lines must both be present and separate."""
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        expected = {
            "total_candidates_by_signal",
            "judge_confirmed_by_signal",
            "judge_false_positives_by_signal",
            "surface_drift_dropped",
            "surface_drift_sections",
            "secret_filter_skipped",
            "session_load_failures",
            "jsonl_skipped_lines",
            "judge_calls",
            "judge_calls_by_signal",
            "final_examples_by_split",
            "final_train_after_duplication",
            "mining_multiplier_used",
            "persona_drift_thresholds_used",
            "oracle_baseline_path",
            "judge_model",
        }
        assert set(m.metrics.keys()) >= expected, expected - set(m.metrics.keys())

    def test_load_session_failure_increments_session_load_failures(self, mock_config):
        """B3 fix critical: file-level load failure → session_load_failures, NOT jsonl_skipped_lines."""
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        result = m._load_session(Path("/nonexistent/file.json"))
        assert result is None
        assert m.metrics["session_load_failures"] == 1
        assert m.metrics["jsonl_skipped_lines"] == 0, (
            "B3 fix regression: _load_session must NOT touch jsonl_skipped_lines"
        )

    def test_load_session_success(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "s.json"
            sp.write_text(json.dumps({"messages": []}))
            result = m._load_session(sp)
            assert result == {"messages": []}
            assert m.metrics["session_load_failures"] == 0

    def test_filter_secrets_drops_jwt(self, mock_config):
        from evolution.prompts.session_prompt_miner import (
            SessionPromptMiner,
            Candidate,
        )
        m = SessionPromptMiner(mock_config)
        jwt = "eyJ" + "a" * 100 + ".eyJpZCI6MX0.signaturesignaturesignature"
        cands = [
            Candidate(
                task=jwt,
                session_path="s",
                signal="user_correction",
                originally_observed_behavior="",
                downstream_context="",
            )
        ]
        kept = m._filter_secrets(cands)
        assert len(kept) == 0
        assert m.metrics["secret_filter_skipped"] >= 1

    def test_filter_drift_drops_unknown_section(self, mock_config):
        from evolution.prompts.session_prompt_miner import (
            SessionPromptMiner,
            Candidate,
            Verdict,
        )
        m = SessionPromptMiner(mock_config)
        c = Candidate(
            task="t",
            session_path="s",
            signal="user_correction",
            originally_observed_behavior="",
            downstream_context="",
        )
        v = Verdict(
            verdict="confirm_example",
            section_id="unknown_section",
            expected_behavior="x",
            difficulty="easy",
            rationale="",
        )
        kept = m._filter_drift([(c, v)], current_section_ids={"memory_guidance"})
        assert len(kept) == 0
        assert m.metrics["surface_drift_dropped"] == 1
        assert m.metrics["surface_drift_sections"]["unknown_section"] == 1

    def test_filter_drift_keeps_known_section(self, mock_config):
        from evolution.prompts.session_prompt_miner import (
            SessionPromptMiner,
            Candidate,
            Verdict,
        )
        m = SessionPromptMiner(mock_config)
        c = Candidate(
            task="t",
            session_path="s",
            signal="user_correction",
            originally_observed_behavior="",
            downstream_context="",
        )
        v = Verdict(
            verdict="confirm_example",
            section_id="memory_guidance",
            expected_behavior="x",
            difficulty="easy",
            rationale="",
        )
        kept = m._filter_drift([(c, v)], current_section_ids={"memory_guidance"})
        assert len(kept) == 1


# ── Task 2.3 — Extractors + Judge ──────────────────────────────────────────────


class TestExtractors:
    def test_user_correction_keyword_hit(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        m.user_correction_judge = MagicMock(return_value=MagicMock(is_correction=True))
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "don't apologize so much"},
        ]
        cands = m._extract_user_correction(msgs, "s")
        assert len(cands) == 1
        assert cands[0].signal == "user_correction"
        assert m.metrics["total_candidates_by_signal"]["user_correction"] == 1

    def test_user_correction_no_keyword(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "great thanks"},
        ]
        assert m._extract_user_correction(msgs, "s") == []

    def test_user_correction_llm_rejects(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        # LLM 二判 returns False → discard despite keyword hit
        m.user_correction_judge = MagicMock(return_value=MagicMock(is_correction=False))
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "don't apologize"},
        ]
        assert m._extract_user_correction(msgs, "s") == []

    def test_section_specific_failure_memory_guidance(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        msgs = [
            {"role": "assistant", "content": "response"},
            {"role": "user", "content": "I already told you my name is bob"},
        ]
        cands = m._extract_section_specific_failure(msgs, "s")
        assert any(c.section_id == "memory_guidance" for c in cands)

    def test_section_specific_failure_none(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        msgs = [{"role": "user", "content": "completely unrelated talk"}]
        assert m._extract_section_specific_failure(msgs, "s") == []

    def test_oracle_disagreement_disabled_without_baseline(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        msgs = [{"role": "user", "content": "do thing"}, {"role": "assistant", "content": "ok"}]
        assert m._extract_oracle_disagreement(msgs, "s") == []

    def test_persona_drift_disabled_without_detector(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config, signals=["persona_drift"])
        assert m.drift_detector is None
        msgs = [{"role": "assistant", "content": f"a{i}"} for i in range(10)]
        assert m._extract_persona_drift(msgs, "s") == []

    def test_persona_drift_min_turns_gate(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(
            mock_config,
            signals=["persona_drift"],
            drift_thresholds={"tone": 0.5, "formality": 0.5, "vocabulary": 0.5, "persona": 0.5},
        )
        # < 6 assistant turns → empty
        msgs = [{"role": "assistant", "content": "a"}] * 4
        assert m._extract_persona_drift(msgs, "s") == []

    def test_persona_drift_multi_dim_candidates(self, mock_config):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(
            mock_config,
            signals=["persona_drift"],
            drift_thresholds={"tone": 0.2, "formality": 0.2, "vocabulary": 0.2, "persona": 0.2},
        )
        m.drift_detector._check_one_run = MagicMock(
            return_value=(
                {"tone": 0.9, "formality": 0.05, "vocabulary": 0.05, "persona": 0.9},
                "exp",
            )
        )
        msgs = [{"role": "user", "content": "q"}] + [
            {"role": "assistant", "content": f"a{i}"} for i in range(9)
        ]
        cands = m._extract_persona_drift(msgs, "s")
        assert len(cands) == 2  # tone + persona exceed

    def test_judge_difficulty_fallback(self, mock_config):
        from evolution.prompts.session_prompt_miner import (
            SessionPromptMiner,
            Candidate,
        )
        m = SessionPromptMiner(mock_config)
        # LLM emits bogus difficulty → fallback to 'medium'
        m.judge = MagicMock(
            return_value=MagicMock(
                verdict="LARGE",
                section_id="memory_guidance",
                expected_behavior="b",
                difficulty="HUGE",
                rationale="r",
            )
        )
        fake = [
            Candidate(
                task="t",
                session_path="s",
                signal="user_correction",
                originally_observed_behavior="o",
                downstream_context="d",
            )
        ]
        verdicts = m._judge_candidates(fake, [])
        assert verdicts[0][1].difficulty == "medium"
        assert verdicts[0][1].verdict == "false_positive"
        assert m.metrics["judge_calls"] == 1
        assert m.metrics["judge_false_positives_by_signal"]["user_correction"] == 1

    def test_judge_confirm_records_metrics(self, mock_config):
        from evolution.prompts.session_prompt_miner import (
            SessionPromptMiner,
            Candidate,
        )
        m = SessionPromptMiner(mock_config)
        m.judge = MagicMock(
            return_value=MagicMock(
                verdict="confirm_example",
                section_id="memory_guidance",
                expected_behavior="remember the user",
                difficulty="easy",
                rationale="ok",
            )
        )
        fake = [
            Candidate(
                task="t",
                session_path="s",
                signal="user_correction",
                originally_observed_behavior="o",
                downstream_context="d",
            )
        ]
        verdicts = m._judge_candidates(fake, [])
        assert verdicts[0][1].verdict == "confirm_example"
        assert verdicts[0][1].difficulty == "easy"
        assert m.metrics["judge_confirmed_by_signal"]["user_correction"] == 1
        assert m.metrics["judge_calls_by_signal"]["user_correction"] == 1


# ── Task 2.4 — mine() + split_and_duplicate ───────────────────────────────────


class FakeSection:
    def __init__(self, sid, text="x"):
        self.section_id = sid
        self.text = text


@pytest.fixture
def current_sections():
    return [
        FakeSection("memory_guidance"),
        FakeSection("default_agent_identity"),
        FakeSection("session_search_guidance"),
        FakeSection("skills_guidance"),
        FakeSection("platform_hints.macos"),
    ]


class TestMine:
    def test_empty_sessions_dir_returns_empty(self, mock_config, current_sections):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        with tempfile.TemporaryDirectory() as d:
            assert m.mine(Path(d), current_sections) == []

    def test_single_user_correction_produces_one_example(self, mock_config, current_sections):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        m.user_correction_judge = MagicMock(return_value=MagicMock(is_correction=True))
        m.judge = MagicMock(
            return_value=MagicMock(
                verdict="confirm_example",
                section_id="memory_guidance",
                expected_behavior="remember",
                difficulty="medium",
                rationale="r",
            )
        )
        with tempfile.TemporaryDirectory() as d:
            sess = {
                "messages": [
                    {"role": "user", "content": "q"},
                    {"role": "assistant", "content": "a"},
                    {"role": "user", "content": "don't apologize"},
                ]
            }
            Path(d, "s1.json").write_text(json.dumps(sess))
            out = m.mine(Path(d), current_sections)
            assert len(out) == 1
            assert out[0].source == "session"
            assert out[0].mining_signals == ["user_correction"]
            assert out[0].section_id == "memory_guidance"

    def test_false_positive_dropped_but_recorded(self, mock_config, current_sections):
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        m.user_correction_judge = MagicMock(return_value=MagicMock(is_correction=True))
        m.judge = MagicMock(
            return_value=MagicMock(
                verdict="false_positive",
                section_id="memory_guidance",
                expected_behavior="",
                difficulty="medium",
                rationale="not real",
            )
        )
        with tempfile.TemporaryDirectory() as d:
            sess = {
                "messages": [
                    {"role": "user", "content": "q"},
                    {"role": "assistant", "content": "a"},
                    {"role": "user", "content": "don't apologize"},
                ]
            }
            Path(d, "s1.json").write_text(json.dumps(sess))
            out = m.mine(Path(d), current_sections)
            assert len(out) == 0
            assert m.metrics["judge_false_positives_by_signal"]["user_correction"] == 1

    def test_split_and_duplicate_train_only_multiplied(self):
        from evolution.prompts.session_prompt_miner import split_and_duplicate
        from evolution.prompts.prompt_dataset import (
            PromptBehavioralExample,
            _hash_to_split,
            _normalize_task_hash,
        )

        def find_for_split(prefix, target_split, n=1):
            out = []
            i = 0
            while len(out) < n:
                msg = f"{prefix}{i}"
                if _hash_to_split(_normalize_task_hash(msg)) == target_split:
                    out.append(msg)
                i += 1
                assert i < 20000
            return out

        [a_msg] = find_for_split("uc-msg-", "train")
        [b_msg] = find_for_split("pd-msg-", "train")
        ex_a = PromptBehavioralExample(
            section_id="memory_guidance",
            user_message=a_msg,
            expected_behavior="e",
            difficulty="medium",
            source="session",
            mining_signals=["user_correction"],
        )
        ex_b = PromptBehavioralExample(
            section_id="default_agent_identity",
            user_message=b_msg,
            expected_behavior="e",
            difficulty="medium",
            source="session",
            mining_signals=["persona_drift"],
        )
        train, val, holdout = split_and_duplicate([ex_a, ex_b])
        assert len(train) == 3 + 2  # uc=3x, pd=2x

    def test_split_and_duplicate_max_not_product(self):
        from evolution.prompts.session_prompt_miner import split_and_duplicate
        from evolution.prompts.prompt_dataset import (
            PromptBehavioralExample,
            _hash_to_split,
            _normalize_task_hash,
        )

        def find_train(prefix, n=1):
            out = []
            i = 0
            while len(out) < n:
                msg = f"{prefix}{i}"
                if _hash_to_split(_normalize_task_hash(msg)) == "train":
                    out.append(msg)
                i += 1
                assert i < 20000
            return out

        [m] = find_train("combo-")
        ex = PromptBehavioralExample(
            section_id="memory_guidance",
            user_message=m,
            expected_behavior="e",
            source="session",
            mining_signals=["user_correction", "persona_drift"],
        )
        train, val, holdout = split_and_duplicate([ex])
        assert len(train) == 3  # max(3, 2) NOT 6

    def test_split_and_duplicate_val_holdout_not_duplicated(self):
        from evolution.prompts.session_prompt_miner import split_and_duplicate
        from evolution.prompts.prompt_dataset import (
            PromptBehavioralExample,
            _hash_to_split,
            _normalize_task_hash,
        )

        def find_for_split(prefix, target):
            i = 0
            while True:
                msg = f"{prefix}{i}"
                if _hash_to_split(_normalize_task_hash(msg)) == target:
                    return msg
                i += 1
                assert i < 20000

        v = find_for_split("val-", "val")
        h = find_for_split("hold-", "holdout")
        ex_v = PromptBehavioralExample(
            section_id="memory_guidance",
            user_message=v,
            expected_behavior="e",
            source="session",
            mining_signals=["user_correction"],
        )
        ex_h = PromptBehavioralExample(
            section_id="memory_guidance",
            user_message=h,
            expected_behavior="e",
            source="session",
            mining_signals=["user_correction"],
        )
        train, val, holdout = split_and_duplicate([ex_v, ex_h])
        assert len(train) == 0
        assert len(val) == 1
        assert len(holdout) == 1

    def test_mine_dedup_unions_signals_same_task_same_section(
        self, mock_config, current_sections
    ):
        """Same task_hash + same section_id → 1 example, mining_signals unioned."""
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(
            mock_config,
            signals=["user_correction", "section_specific_failure"],
        )
        m.user_correction_judge = MagicMock(return_value=MagicMock(is_correction=True))
        # judge returns same section_id memory_guidance regardless of signal
        m.judge = MagicMock(
            return_value=MagicMock(
                verdict="confirm_example",
                section_id="memory_guidance",
                expected_behavior="remember",
                difficulty="medium",
                rationale="ok",
            )
        )
        with tempfile.TemporaryDirectory() as d:
            # Use a message that triggers BOTH user_correction (don't apologize)
            # AND memory section_specific_failure (I already told you)
            sess = {
                "messages": [
                    {"role": "user", "content": "q"},
                    {"role": "assistant", "content": "a"},
                    {"role": "user", "content": "don't apologize, I already told you"},
                ]
            }
            Path(d, "s1.json").write_text(json.dumps(sess))
            out = m.mine(Path(d), current_sections)
            # Single example, but mining_signals contains both
            assert len(out) == 1
            assert set(out[0].mining_signals) == {
                "user_correction",
                "section_specific_failure",
            }

    def test_session_load_failures_warns_at_threshold(
        self, mock_config, current_sections, capsys
    ):
        """B3 fix: 5% threshold monitors session_load_failures (file-level)."""
        from evolution.prompts.session_prompt_miner import SessionPromptMiner
        m = SessionPromptMiner(mock_config)
        with tempfile.TemporaryDirectory() as d:
            # 1 good, 19 bad → 5%+ failure
            Path(d, "good.json").write_text(json.dumps({"messages": []}))
            for i in range(19):
                Path(d, f"bad{i}.json").write_text("not json {{")
            m.mine(Path(d), current_sections)
            assert m.metrics["session_load_failures"] == 19
            assert m.metrics["jsonl_skipped_lines"] == 0  # NOT incremented
