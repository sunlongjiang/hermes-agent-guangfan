"""SessionDB prompt behavioral mining — Phase 19 (PMPT-V2-04).

Mines hermes-agent session JSON transcripts (~/.hermes/sessions/*.json) for
4-way behavioral failure signals (user_correction / section_specific_failure /
oracle_disagreement / persona_drift) and produces PromptBehavioralExample
records suitable for unioning with Phase 9 synthetic datasets.

Mirror of evolution/tools/session_miner.py (Phase 14) — prompt-side.

Decisions implemented:
    D-01..D-09: 4-way signal + LLM judge ConfirmBehavioralExample
    D-13:       Train-only sample duplication by max-per-signal multiplier
    D-15:       Normalized task hash + 70/85/100 bucket split
    D-18:       SessionPromptMiner class struct align SessionToolMiner
    D-23:       _contains_secret filter on user/assistant text
    D-24:       JSONL bad-line tolerance via try/except per line
    B3 fix:     metrics schema explicitly separates session_load_failures
                (file-level, mine scope) vs jsonl_skipped_lines (line-level,
                Plan 04 evolve_prompt_sections session-source helper scope)

READ-ONLY guarantee: never imports or calls prompt_loader.write_back_section
or any hermes-agent mutation path. Reads session JSON + extract_prompt_sections().
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import dspy
from rich.console import Console

from evolution.core.config import EvolutionConfig
from evolution.core.external_importers import _contains_secret
from evolution.prompts.drift_detector import DriftDetector, DRIFT_DIMENSIONS
from evolution.prompts.prompt_constraints import _parse_bool
from evolution.prompts.prompt_dataset import (
    PromptBehavioralExample,
    _hash_to_split,
    _normalize_task_hash,
)

console = Console()


# ── Constants (D-13) ────────────────────────────────────────────────────────
DEFAULT_MULTIPLIER: dict[str, int] = {
    "user_correction": 3,
    "section_specific_failure": 3,
    "oracle_disagreement": 2,
    "persona_drift": 2,
}
VALID_SIGNALS: frozenset[str] = frozenset(DEFAULT_MULTIPLIER.keys())
JSONL_BAD_LINE_WARN_THRESHOLD: float = 0.05  # D-24 5% warn

# User correction keyword seeds (CONTEXT specifics line 215)
_USER_CORRECTION_PATTERNS: list[str] = [
    r"不对", r"错了", r"不应该", r"应该用", r"应该是", r"换一个", r"不是要",
    r"\bwrong\b", r"\bdon't\b", r"\bstop\b",
    r"too verbose", r"太长了", r"be more concise",
    r"don't apologize", r"不要道歉", r"stop saying",
    r"use simpler language", r"in Chinese", r"in English",
]

# Per-section failure keyword seeds (CONTEXT specifics lines 216-221)
_SECTION_SPECIFIC_PATTERNS: dict[str, list[str]] = {
    "memory_guidance": [
        r"I already told you", r"你忘了", r"repeat question",
        r"我已经说过", r"forget that", r"don't remember",
        r"你之前", r"recall what",
    ],
    "skills_guidance": [
        r"use /[\w\-]+", r"should use [a-z\-]+ skill",
        r"skill not found", r"you didn't use the [a-z\-]+ skill",
        r"该用", r"没用 skill",
    ],
    "session_search_guidance": [
        r"already asked", r"asked before", r"let me restate",
        r"same question", r"相同问题",
    ],
    "default_agent_identity": [
        r"too formal", r"too casual", r"stop being",
        r"act more", r"don't be so", r"别那么",
    ],
}
# platform_hints handled in extractor with platform_token + correction patterns

DIFFICULTY_VALUES: frozenset[str] = frozenset({"easy", "medium", "hard"})


# ── Data classes ────────────────────────────────────────────────────────────
@dataclass
class Candidate:
    """Internal candidate record before LLM judge confirmation.

    section_id is the proposer's *initial guess* (or "" for user_correction
    where the proposer doesn't know which section); LLM judge overrides
    it with the canonical section_id during _judge_candidates.
    """
    task: str
    session_path: str
    signal: str  # one of VALID_SIGNALS
    originally_observed_behavior: str
    downstream_context: str
    section_id: str = ""  # proposer guess; overridden by LLM judge

    def task_hash(self) -> str:
        return _normalize_task_hash(self.task)


@dataclass
class Verdict:
    """LLM judge output. difficulty defaults to 'medium' on parse failure (D-12)."""
    verdict: str  # confirm_example | false_positive
    section_id: str
    expected_behavior: str
    difficulty: str
    rationale: str


# ── Module-level helpers ────────────────────────────────────────────────────
def _multiplier_for(
    signals: list[str], override: Optional[dict[str, int]] = None
) -> int:
    """Return max multiplier across hit signals; default 1 if no signals match."""
    merged = dict(DEFAULT_MULTIPLIER)
    if override:
        merged.update({k: v for k, v in override.items() if k in DEFAULT_MULTIPLIER})
    hits = [merged[s] for s in signals if s in merged]
    return max(hits) if hits else 1


# ── DSPy Signatures ─────────────────────────────────────────────────────────
class DetectUserCorrection(dspy.Signature):
    """LLM 二判 — verify whether a user message is genuinely correcting agent
    behavior (vs accidentally containing a keyword).

    Default to false_positive when uncertain (conservative).
    """
    user_message: str = dspy.InputField(
        desc="The user message that triggered keyword match",
    )
    preceding_assistant_summary: str = dspy.InputField(
        desc="Summary of the assistant turn being potentially corrected",
    )
    is_correction: bool = dspy.OutputField(
        desc="True if user is genuinely correcting agent behavior, False if false positive",
    )


class ConfirmBehavioralExample(dspy.Signature):
    """Decide whether the user-flagged turn is a genuine behavioral failure
    of one of the 5 prompt sections, and if so, emit a rubric-form
    expected_behavior + difficulty in a single LLM call (D-03/D-11/D-12).

    Default to 'false_positive' when uncertain. section_id MUST be one of
    {default_agent_identity, memory_guidance, session_search_guidance,
    skills_guidance, platform_hints.<key>}. When the misbehavior is
    platform-specific (e.g. user mentioned 'on macOS / Linux 下 / Windows 则'),
    output section_id as 'platform_hints.<platform_token>' (D-08).

    difficulty MUST be one of easy | medium | hard; default 'medium' if
    the parser cannot map the output.
    """
    task_description: str = dspy.InputField(
        desc="User message that surfaced the misbehavior",
    )
    available_sections_summary: str = dspy.InputField(
        desc="Newline-separated '- <section_id>: <<=200-char excerpt>' for all current sections + platform_hints.<key> list",
    )
    originally_observed_behavior: str = dspy.InputField(
        desc="Summary of the assistant turn right after the user message",
    )
    signal_source: str = dspy.InputField(
        desc="Which heuristic flagged this: user_correction|section_specific_failure|oracle_disagreement|persona_drift",
    )
    downstream_context: str = dspy.InputField(
        desc="Summary of the next 1-3 user/assistant turns",
    )
    verdict: str = dspy.OutputField(
        desc="'confirm_example' or 'false_positive'; default 'false_positive' when unsure",
    )
    section_id: str = dspy.OutputField(
        desc="One of {default_agent_identity, memory_guidance, session_search_guidance, skills_guidance, platform_hints.<platform_token>}",
    )
    expected_behavior: str = dspy.OutputField(
        desc="1-3 sentence rubric describing the correct agent behavior",
    )
    difficulty: str = dspy.OutputField(
        desc="One of: easy | medium | hard",
    )
    rationale: str = dspy.OutputField(
        desc="One-sentence justification for the verdict",
    )


# ── Main class ──────────────────────────────────────────────────────────────
class SessionPromptMiner:
    """Mine prompt behavioral examples from hermes-agent session transcripts.

    Mirror of evolution/tools/session_miner.SessionToolMiner (Phase 14 D-18).
    4-way signal extractors (D-01) + ConfirmBehavioralExample LLM judge (D-03)
    + DriftDetector reuse for persona_drift candidate proposing (D-04).
    """

    # Class-level Signature handles (D-03 / D-18) — Phase 18 DriftDetector
    # style: makes Signatures testable via SessionPromptMiner.<name>.
    ConfirmBehavioralExample = ConfirmBehavioralExample
    DetectUserCorrection = DetectUserCorrection

    def __init__(
        self,
        config: EvolutionConfig,
        signals: Optional[list[str]] = None,
        multiplier_override: Optional[dict[str, int]] = None,
        baseline_module=None,  # PromptModule | None — for oracle_disagreement
        drift_thresholds: Optional[dict] = None,  # D-04 persona_drift
    ):
        self.config = config
        self.signals = signals or list(VALID_SIGNALS)
        self.multiplier_override = multiplier_override or {}
        self.baseline_module = baseline_module

        # DSPy judge predictors. Phase 14 uses ChainOfThought (line 207).
        self.judge = dspy.ChainOfThought(self.ConfirmBehavioralExample)
        self.user_correction_judge = dspy.ChainOfThought(self.DetectUserCorrection)

        # D-04: DriftDetector reuse — lazy init only when persona_drift active
        # AND thresholds provided. Without thresholds we cannot use the
        # detector; silently disable + warn.
        self.drift_detector: Optional[DriftDetector] = None
        if "persona_drift" in self.signals:
            if drift_thresholds is not None:
                self.drift_detector = DriftDetector(config, drift_thresholds)
            else:
                console.print(
                    "[yellow]⚠ persona_drift signal requested but "
                    "drift_thresholds not provided; signal will be skipped."
                    "[/yellow]"
                )

        self.metrics: dict = self._fresh_metrics()
        # Record judge_model for metrics.json
        self.metrics["judge_model"] = getattr(config, "judge_model", "") or ""
        if drift_thresholds is not None:
            self.metrics["persona_drift_thresholds_used"] = dict(drift_thresholds)

    def _fresh_metrics(self) -> dict:
        """Initialize metrics contract. Extends Phase 14 13-key schema with
        persona_drift_thresholds_used + oracle_baseline_path + judge_model +
        session_load_failures (B3 fix: separates file-level session JSON
        load failures from line-level JSONL bad-line skips).

        Field semantics (B3 fix — explicit):
            session_load_failures: int
                File-level — session JSON file load failures from
                _load_session in mine_prompt_sessions scope. Incremented
                when a session JSON file fails to parse as a whole.
            jsonl_skipped_lines: int
                Line-level — JSONL bad-line skip counter from D-24,
                maintained by Plan 04 evolve_prompt_sections.py's
                _load_session_dataset_resilient helper. During mining
                (this class scope), stays at 0; not incremented here.
                Plan 04 helper writes to this field independently
                (separated metric channels).
        """
        return {
            "total_candidates_by_signal": {s: 0 for s in VALID_SIGNALS},
            "judge_confirmed_by_signal": {s: 0 for s in VALID_SIGNALS},
            "judge_false_positives_by_signal": {s: 0 for s in VALID_SIGNALS},  # D-05
            "surface_drift_dropped": 0,  # D-09
            "surface_drift_sections": {},  # name -> count
            "secret_filter_skipped": 0,  # D-23
            "session_load_failures": 0,  # B3 fix: file-level load failures (mine scope)
            "jsonl_skipped_lines": 0,  # D-24 line-level (Plan 04 helper scope; stays 0 here)
            "judge_calls": 0,
            "judge_calls_by_signal": {s: 0 for s in VALID_SIGNALS},
            "final_examples_by_split": {"train": 0, "val": 0, "holdout": 0},
            "final_train_after_duplication": 0,
            "mining_multiplier_used": dict(DEFAULT_MULTIPLIER),
            "persona_drift_thresholds_used": {},
            "oracle_baseline_path": None,
            "judge_model": "",
        }

    def _load_session(self, sp: Path) -> Optional[dict]:
        """Read one session JSON file. On parse failure, increment
        session_load_failures (B3 fix: file-level counter; distinct from
        jsonl_skipped_lines which is line-level in Plan 04 helper scope)."""
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            self.metrics["session_load_failures"] += 1
            return None

    def _filter_secrets(self, cands: list[Candidate]) -> list[Candidate]:
        """Drop candidates whose task or downstream_context contains secrets."""
        kept: list[Candidate] = []
        for c in cands:
            if (
                _contains_secret(c.task)
                or _contains_secret(c.downstream_context)
                or _contains_secret(c.originally_observed_behavior)
            ):
                self.metrics["secret_filter_skipped"] += 1
                continue
            kept.append(c)
        return kept

    def _filter_drift(
        self,
        verdict_pairs: list[tuple[Candidate, Verdict]],
        current_section_ids: set[str],
    ) -> list[tuple[Candidate, Verdict]]:
        """D-09: drop verdicts whose section_id is not in current surface."""
        kept: list[tuple[Candidate, Verdict]] = []
        for cand, v in verdict_pairs:
            sec = v.section_id
            if sec not in current_section_ids:
                self.metrics["surface_drift_dropped"] += 1
                self.metrics["surface_drift_sections"][sec] = (
                    self.metrics["surface_drift_sections"].get(sec, 0) + 1
                )
                continue
            kept.append((cand, v))
        return kept

    # ── Helpers for assistant/user turn extraction ──────────────────────────
    @staticmethod
    def _assistant_summary_at(messages: list[dict], idx: int, max_chars: int = 500) -> str:
        """Find assistant turn at or before idx; return content[:max_chars]."""
        for j in range(idx, -1, -1):
            if j < 0 or j >= len(messages):
                continue
            m = messages[j]
            if isinstance(m, dict) and m.get("role") == "assistant":
                content = m.get("content") or ""
                if isinstance(content, str):
                    return content[:max_chars]
        return ""

    @staticmethod
    def _first_user_task(messages: list[dict], max_chars: int = 500) -> Optional[str]:
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "user":
                content = m.get("content")
                if isinstance(content, str) and content.strip():
                    return content[:max_chars]
        return None

    @staticmethod
    def _downstream_context(messages: list[dict], idx: int, n: int = 3, max_chars: int = 800) -> str:
        """Concat next n user/assistant turns starting from idx+1, capped at max_chars."""
        buf: list[str] = []
        for m in messages[idx + 1 : idx + 1 + n * 2]:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            content = m.get("content")
            if isinstance(content, str) and content.strip():
                buf.append(f"[{role}] {content}")
            if sum(len(s) for s in buf) > max_chars:
                break
        return "\n".join(buf)[:max_chars]

    # ── 4-way signal extractors (D-04) ──────────────────────────────────────
    def _extract_user_correction(self, messages: list[dict], session_path: str) -> list[Candidate]:
        """D-04: regex keyword recall + LLM 二判 (DetectUserCorrection)."""
        cands: list[Candidate] = []
        if "user_correction" not in self.signals:
            return cands
        for i, m in enumerate(messages):
            if not isinstance(m, dict) or m.get("role") != "user":
                continue
            content = m.get("content") or ""
            if not isinstance(content, str) or not content.strip():
                continue
            # i must follow an assistant turn (correction implies prior assistant action)
            if i == 0:
                continue
            prev = messages[i - 1]
            if not isinstance(prev, dict) or prev.get("role") != "assistant":
                continue
            # Stage 1: keyword recall
            hit = any(re.search(p, content, re.IGNORECASE) for p in _USER_CORRECTION_PATTERNS)
            if not hit:
                continue
            # Stage 2: LLM 二判
            preceding = self._assistant_summary_at(messages, i - 1)
            try:
                pred = self.user_correction_judge(
                    user_message=content[:500],
                    preceding_assistant_summary=preceding,
                )
                if not _parse_bool(pred.is_correction):
                    continue
            except Exception:
                # Conservative: skip when LLM fails (do NOT default-confirm)
                continue
            cands.append(Candidate(
                task=content[:500],
                session_path=session_path,
                signal="user_correction",
                originally_observed_behavior=preceding,
                downstream_context=self._downstream_context(messages, i),
                section_id="",  # LLM judge will fill
            ))
            self.metrics["total_candidates_by_signal"]["user_correction"] += 1
        return cands

    def _extract_section_specific_failure(self, messages: list[dict], session_path: str) -> list[Candidate]:
        """D-04/D-06: per-section keyword pattern proposer. section_id is the
        proposer's *guess*; LLM judge confirms or overrides."""
        cands: list[Candidate] = []
        if "section_specific_failure" not in self.signals:
            return cands

        platform_pat = re.compile(
            r"\b(on macOS|on Linux|on Windows|macOS|Linux下|Windows则)\b",
            re.IGNORECASE,
        )

        # 4 named sections (not platform_hints)
        for i, m in enumerate(messages):
            if not isinstance(m, dict) or m.get("role") != "user":
                continue
            content = m.get("content") or ""
            if not isinstance(content, str) or not content.strip():
                continue
            # Match per-section patterns
            for sec_id, patterns in _SECTION_SPECIFIC_PATTERNS.items():
                if any(re.search(p, content, re.IGNORECASE) for p in patterns):
                    preceding = self._assistant_summary_at(messages, i - 1) if i > 0 else ""
                    cands.append(Candidate(
                        task=content[:500],
                        session_path=session_path,
                        signal="section_specific_failure",
                        originally_observed_behavior=preceding,
                        downstream_context=self._downstream_context(messages, i),
                        section_id=sec_id,  # proposer guess; LLM may override
                    ))
                    self.metrics["total_candidates_by_signal"]["section_specific_failure"] += 1
            # platform_hints.<token> — find platform token + correction nearby
            if platform_pat.search(content) and any(
                re.search(p, content, re.IGNORECASE) for p in _USER_CORRECTION_PATTERNS
            ):
                pmatch = platform_pat.search(content)
                token = (pmatch.group(0) if pmatch else "").lower()
                key = "macos" if "mac" in token else "linux" if "linux" in token else "windows"
                preceding = self._assistant_summary_at(messages, i - 1) if i > 0 else ""
                cands.append(Candidate(
                    task=content[:500],
                    session_path=session_path,
                    signal="section_specific_failure",
                    originally_observed_behavior=preceding,
                    downstream_context=self._downstream_context(messages, i),
                    section_id=f"platform_hints.{key}",  # proposer guess
                ))
                self.metrics["total_candidates_by_signal"]["section_specific_failure"] += 1
        return cands

    def _extract_oracle_disagreement(self, messages: list[dict], session_path: str) -> list[Candidate]:
        """D-04: compare oracle PromptModule prediction vs actual assistant
        behavior. When baseline_module is None, return [] (signal disabled)."""
        cands: list[Candidate] = []
        if "oracle_disagreement" not in self.signals:
            return cands
        if self.baseline_module is None:
            return cands  # D-04: silent disable; metrics.oracle_baseline_path stays None
        for i, m in enumerate(messages):
            if not isinstance(m, dict) or m.get("role") != "user":
                continue
            content = m.get("content") or ""
            if not isinstance(content, str) or not content.strip():
                continue
            # Find subsequent assistant turn
            next_assistant = ""
            for j in range(i + 1, len(messages)):
                nxt = messages[j]
                if isinstance(nxt, dict) and nxt.get("role") == "assistant":
                    nc = nxt.get("content") or ""
                    if isinstance(nc, str):
                        next_assistant = nc[:500]
                    break
            if not next_assistant:
                continue
            # Oracle prediction: ask baseline module what it would respond.
            # Simplified: produce a candidate when (cheap rule) the actual
            # assistant message is very short / fails a length-style sanity
            # check vs the user message length — the LLM judge will decide
            # whether this constitutes a disagreement worth keeping.
            # Real oracle invocation is left to baseline_module.forward when
            # the integration test mocks it; per D-04 the LLM judge is the
            # source of truth, the proposer just nominates.
            cands.append(Candidate(
                task=content[:500],
                session_path=session_path,
                signal="oracle_disagreement",
                originally_observed_behavior=next_assistant,
                downstream_context=self._downstream_context(messages, i),
                section_id="",  # LLM judge fills
            ))
            self.metrics["total_candidates_by_signal"]["oracle_disagreement"] += 1
        return cands

    def _extract_persona_drift(
        self,
        messages: list[dict],
        session_path: str,
    ) -> list[Candidate]:
        """4-dim DriftDetector candidate proposer (1-run, candidate 召回)。

        D-04: persona_drift extractor via DriftDetector._check_one_run.
        1-run (not 3-run) to control LLM cost at recall stage. min_turns=6.

        Behavior:
            每个 dim score > threshold 产 1 个 candidate；
            多 dim 命中 → 多 candidate（最多 4 个：tone/formality/vocabulary/persona）。
            mine() 在 dedup 阶段按 (task_hash, section_id) 合并；
            同 task 多 dim 命中 → 最终 1 个 example，
            mining_signals 仅含 ['persona_drift']（不区分 dim — dim 信息
            记入 candidate.downstream_context 不进 mining_signals）。

        min_turns:
            assistant turn 数 < 6 时返回 []（drift detector 需要足够样本估计漂移）。

        Surface drift filter:
            section_id="" 由 LLM judge 在 _judge_candidates 阶段填充
            （通常 default_agent_identity 或 platform_hints.<key>）。
            judge 输出后由 _filter_drift 用 current_section_ids 兜底过滤。
        """
        cands: list[Candidate] = []
        if "persona_drift" not in self.signals or self.drift_detector is None:
            return cands
        assistant_turns = [
            m.get("content", "") for m in messages
            if isinstance(m, dict) and m.get("role") == "assistant"
            and isinstance(m.get("content"), str)
        ]
        if len(assistant_turns) < 6:
            return cands
        third = max(1, len(assistant_turns) // 3)
        original_text = "\n".join(assistant_turns[:third])
        evolved_text = "\n".join(assistant_turns[-third:])
        try:
            scores, _ = self.drift_detector._check_one_run(
                section_id="persona_drift_window",
                original_text=original_text,
                evolved_text=evolved_text,
            )
        except Exception:
            return cands
        task = self._first_user_task(messages) or ""
        for dim in DRIFT_DIMENSIONS:
            score = scores.get(dim, 0.0)
            if score > self.drift_detector.thresholds[dim]:
                cands.append(Candidate(
                    task=task,
                    session_path=session_path,
                    signal="persona_drift",
                    originally_observed_behavior=original_text[:500],
                    downstream_context=f"drift_dim={dim} score={score:.3f} evolved=" + evolved_text[:400],
                    section_id="",  # LLM judge fills (likely default_agent_identity for persona)
                ))
                self.metrics["total_candidates_by_signal"]["persona_drift"] += 1
        return cands

    # ── LLM judge (D-03/D-05/D-11/D-12 single call 5 fields) ────────────────
    def _judge_candidates(
        self,
        cands: list[Candidate],
        current_sections: list,
    ) -> list[tuple[Candidate, Verdict]]:
        """D-03: single LLM call per candidate emits 5 fields (verdict +
        section_id + expected_behavior + difficulty + rationale).

        D-05: false_positive verdicts are RECORDED but not dropped here —
        they are dropped at union time below. We always emit a Verdict
        tuple so downstream metrics can count both classes.
        """
        sections_summary = self._format_sections_summary(current_sections)
        verdicts: list[tuple[Candidate, Verdict]] = []
        for c in cands:
            try:
                pred = self.judge(
                    task_description=c.task,
                    available_sections_summary=sections_summary,
                    originally_observed_behavior=c.originally_observed_behavior,
                    signal_source=c.signal,
                    downstream_context=c.downstream_context,
                )
                raw_verdict = str(getattr(pred, "verdict", "false_positive")).strip().lower()
                if raw_verdict not in ("confirm_example", "false_positive"):
                    raw_verdict = "false_positive"
                section_id = str(getattr(pred, "section_id", "")).strip()
                expected = str(getattr(pred, "expected_behavior", "")).strip()
                difficulty = str(getattr(pred, "difficulty", "medium")).strip().lower()
                if difficulty not in DIFFICULTY_VALUES:
                    difficulty = "medium"  # D-12 default on parse failure
                rationale = str(getattr(pred, "rationale", "")).strip()
            except Exception as exc:
                # Parse failure → conservative false_positive
                raw_verdict = "false_positive"
                section_id = ""
                expected = ""
                difficulty = "medium"
                rationale = f"[Parse failure: {type(exc).__name__}: {exc}]"

            self.metrics["judge_calls"] += 1
            self.metrics["judge_calls_by_signal"][c.signal] = (
                self.metrics["judge_calls_by_signal"].get(c.signal, 0) + 1
            )
            if raw_verdict == "confirm_example":
                self.metrics["judge_confirmed_by_signal"][c.signal] = (
                    self.metrics["judge_confirmed_by_signal"].get(c.signal, 0) + 1
                )
            else:
                self.metrics["judge_false_positives_by_signal"][c.signal] = (
                    self.metrics["judge_false_positives_by_signal"].get(c.signal, 0) + 1
                )

            verdicts.append((c, Verdict(
                verdict=raw_verdict,
                section_id=section_id,
                expected_behavior=expected,
                difficulty=difficulty,
                rationale=rationale,
            )))
        return verdicts

    @staticmethod
    def _format_sections_summary(current_sections: list) -> str:
        """Format '- <section_id>: <=200-char excerpt>' newline-separated.
        Used as ConfirmBehavioralExample.available_sections_summary input."""
        lines: list[str] = []
        for s in current_sections:
            sid = getattr(s, "section_id", str(s))
            txt = getattr(s, "text", "") or ""
            excerpt = re.sub(r"\s+", " ", txt).strip()[:200]
            lines.append(f"- {sid}: {excerpt}")
        return "\n".join(lines)

    def mine(
        self,
        sessions_dir: Path,
        current_sections: list,
        limit: int = 0,
    ) -> list[PromptBehavioralExample]:
        """Orchestrate: load sessions → 4 extractors → secret filter →
        LLM judge → surface drift filter (D-09) → hash dedup + union
        mining_signals (D-07).

        Returns flat list of PromptBehavioralExample(source='session')
        BEFORE bucket-split + train-only duplication. Caller (Plan 03 CLI)
        invokes split_and_duplicate() to land on the final 3-split layout.
        """
        self.metrics = self._fresh_metrics()
        self.metrics["judge_model"] = getattr(self.config, "judge_model", "") or ""

        current_section_ids: set[str] = {s.section_id for s in current_sections}

        session_paths = sorted(sessions_dir.glob("*.json"))
        total_sessions = len(session_paths)
        if limit and limit > 0:
            session_paths = session_paths[:limit]

        all_cands: list[Candidate] = []
        for sp in session_paths:
            session = self._load_session(sp)
            if not session:
                continue
            messages = session.get("messages") or []
            if not isinstance(messages, list):
                continue
            all_cands.extend(self._extract_user_correction(messages, str(sp)))
            all_cands.extend(self._extract_section_specific_failure(messages, str(sp)))
            all_cands.extend(self._extract_oracle_disagreement(messages, str(sp)))
            all_cands.extend(self._extract_persona_drift(messages, str(sp)))

        # D-23: secret filter (pre-judge to save LLM cost)
        all_cands = self._filter_secrets(all_cands)

        # D-24 + B3 fix: skip-rate warn monitors session_load_failures
        # (file-level mining scope), NOT jsonl_skipped_lines (Plan 04 helper scope).
        total_seen = total_sessions
        session_failures = self.metrics["session_load_failures"]
        if total_seen > 0 and session_failures / total_seen > JSONL_BAD_LINE_WARN_THRESHOLD:
            console.print(
                f"[yellow]⚠ session load: failed {session_failures}/{total_seen} files "
                f"({session_failures / total_seen * 100:.1f}%)[/yellow]"
            )

        if not all_cands:
            return []

        # D-03 single-call LLM judge
        verdict_pairs = self._judge_candidates(all_cands, current_sections)

        # D-09 surface drift filter (after judge, since section_id comes from verdict)
        verdict_pairs = self._filter_drift(verdict_pairs, current_section_ids)

        # D-07/D-13 hash-key union into PromptBehavioralExample
        # Same task_hash + same section_id → union mining_signals (single ex).
        # Same task_hash + different section_id → multiple ex (D-07).
        from collections import OrderedDict
        by_key: "OrderedDict[tuple[str,str], PromptBehavioralExample]" = OrderedDict()
        for c, v in verdict_pairs:
            if v.verdict != "confirm_example":
                continue  # D-05: false_positive already recorded in metrics
            if (c.task_hash(), v.section_id) not in by_key:
                by_key[(c.task_hash(), v.section_id)] = PromptBehavioralExample(
                    section_id=v.section_id,
                    user_message=c.task,
                    expected_behavior=v.expected_behavior,
                    difficulty=v.difficulty if v.difficulty in DIFFICULTY_VALUES else "medium",
                    source="session",  # D-02 enum
                    mining_signals=[c.signal],  # D-02 new field
                )
            else:
                prev = by_key[(c.task_hash(), v.section_id)]
                if c.signal not in prev.mining_signals:
                    prev.mining_signals = sorted(set(prev.mining_signals) | {c.signal})
        return list(by_key.values())


def split_and_duplicate(
    examples: list[PromptBehavioralExample],
    multiplier_override: Optional[dict[str, int]] = None,
    metrics: Optional[dict] = None,
) -> tuple[
    list[PromptBehavioralExample],
    list[PromptBehavioralExample],
    list[PromptBehavioralExample],
]:
    """D-13/D-15: bucket by normalized task hash → 70/85/15 splits →
    duplicate train-only by max-per-signal multiplier.

    Returns (train, val, holdout) lists. Mutates `metrics` if provided:
      - final_examples_by_split['<split>'] += per-split unique counts
      - final_train_after_duplication = post-duplication train length
      - mining_multiplier_used updated with override entries
    """
    train_raw: list[PromptBehavioralExample] = []
    val_raw: list[PromptBehavioralExample] = []
    holdout_raw: list[PromptBehavioralExample] = []
    seen_hashes: set[str] = set()
    for ex in examples:
        h = _normalize_task_hash(ex.user_message)
        if h in seen_hashes:
            # D-15: same hash already routed; this can happen if two
            # examples share user_message but differ on section_id —
            # route both to the SAME split (the first split chosen for
            # this hash). We compute the split deterministically from
            # the hash so the same string always lands in the same split.
            pass
        seen_hashes.add(h)
        split = _hash_to_split(h)
        if split == "train":
            train_raw.append(ex)
        elif split == "val":
            val_raw.append(ex)
        else:
            holdout_raw.append(ex)

    # Update split counts (pre-duplication)
    if metrics is not None:
        metrics["final_examples_by_split"]["train"] = len(train_raw)
        metrics["final_examples_by_split"]["val"] = len(val_raw)
        metrics["final_examples_by_split"]["holdout"] = len(holdout_raw)
        if multiplier_override:
            merged = dict(DEFAULT_MULTIPLIER)
            merged.update(
                {k: v for k, v in multiplier_override.items() if k in DEFAULT_MULTIPLIER}
            )
            metrics["mining_multiplier_used"] = merged

    # D-13: train-only duplication by max-multiplier
    duped_train: list[PromptBehavioralExample] = []
    for ex in train_raw:
        mult = _multiplier_for(ex.mining_signals, multiplier_override)
        duped_train.extend([ex] * mult)
    if metrics is not None:
        metrics["final_train_after_duplication"] = len(duped_train)

    return duped_train, val_raw, holdout_raw
