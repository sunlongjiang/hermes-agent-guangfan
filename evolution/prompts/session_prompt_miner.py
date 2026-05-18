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


# ── Main class (placeholder — Tasks 2.2-2.4 fill methods) ───────────────────
class SessionPromptMiner:
    """Implemented in Task 2.2 (constructor) + 2.3 (extractors) + 2.4 (orchestration)."""

    # Class-level Signature handles (D-03 / D-18) — Phase 18 DriftDetector style
    ConfirmBehavioralExample = ConfirmBehavioralExample
    DetectUserCorrection = DetectUserCorrection

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Task 2.2 fills this in")


def split_and_duplicate(*args, **kwargs):
    """Implemented in Task 2.4. Placeholder so Plan 03 CLI imports don't fail mid-build."""
    raise NotImplementedError("Task 2.4 fills this in")
