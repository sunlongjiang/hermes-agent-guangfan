"""SessionDB tool mining — Phase 14 (TOOL-V2-01).

Mines hermes-agent session JSON transcripts (~/.hermes/sessions/*.json) for
tool misselection patterns and produces ToolSelectionExample records suitable
for unioning with synthetic Phase 4 datasets.

Decisions implemented:
    D-01..D-05: 三路信号 (error_retry / user_correction / oracle_disagreement)
                + LLM judge ConfirmMisselection
    D-06:       SessionToolMiner class (struct align ToolDatasetBuilder)
    D-11:       Train-only sample duplication by max-per-signal multiplier
    D-13:       Normalized task hash + 70/85/100 bucket split (deterministic)
    D-17:       Surface drift filter (drop tools not in current hermes)
    D-18:       JSONL bad-line tolerance (helper only — does NOT modify
                EvalDataset.load / GoldenDatasetLoader.load / ToolSelectionDataset.load).

READ-ONLY guarantee: this module never imports or calls
evolution.tools.tool_loader.write_back_description or any hermes-agent
mutation path. It only reads session JSON + extract_tool_descriptions().
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
from evolution.tools.tool_constraints import _parse_bool
from evolution.tools.tool_dataset import ToolSelectionExample

console = Console()

# ── Constants (D-11/D-12) ────────────────────────────────────────────────
DEFAULT_MULTIPLIER: dict[str, int] = {
    "error_retry": 3,
    "user_correction": 3,
    "oracle_disagreement": 2,
}
VALID_SIGNALS: frozenset[str] = frozenset(DEFAULT_MULTIPLIER.keys())
JSONL_BAD_LINE_WARN_THRESHOLD: float = 0.05  # D-18 5%


# ── Helpers (Task 4.1) ───────────────────────────────────────────────────
def _normalize_task_hash(task: str) -> str:
    """Return sha256(strip + lower + collapse_whitespace(task))[:16]."""
    norm = re.sub(r"\s+", " ", (task or "").lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _hash_to_split(h: str) -> str:
    """Bucket per CONTEXT D-13: <70 train / <85 val / else holdout."""
    bucket = int(h[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "val"
    return "holdout"


def _multiplier_for(
    signals: list[str], override: Optional[dict[str, int]] = None
) -> int:
    """Return max multiplier across hit signals; default 1 if no signals match."""
    merged = dict(DEFAULT_MULTIPLIER)
    if override:
        merged.update({k: v for k, v in override.items() if k in DEFAULT_MULTIPLIER})
    hits = [merged[s] for s in signals if s in merged]
    return max(hits) if hits else 1


def _load_jsonl_skip_bad(path: Path) -> tuple[list[dict], int]:
    """Read JSONL line-by-line; return (rows, skipped_count). D-18 minimal subset."""
    rows: list[dict] = []
    skipped = 0
    if not path.exists():
        return rows, 0
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    total = len(rows) + skipped
    if total and skipped / total > JSONL_BAD_LINE_WARN_THRESHOLD:
        console.print(
            f"[yellow]⚠ {path.name}: skipped {skipped}/{total} bad JSONL "
            f"lines ({skipped / total * 100:.1f}%)[/yellow]"
        )
    return rows, skipped


# ── Data classes (Task 4.2) ──────────────────────────────────────────────
@dataclass
class Candidate:
    """Internal representation of a misselection-candidate before LLM judge."""

    task: str
    session_path: str
    originally_used_tool: str
    available_tools: list[str]
    tool_call_id: str
    signal: str
    downstream_context: str

    def task_hash(self) -> str:
        return _normalize_task_hash(self.task)


@dataclass
class Verdict:
    """LLM judge output. label='false_positive' is the conservative default."""

    label: str  # "confirm_misselection" | "false_positive"
    correct_tool: str
    rationale: str


# ── Main class (Task 4.2) ────────────────────────────────────────────────
class SessionToolMiner:
    """Mine hermes-agent session JSON transcripts for tool misselection."""

    class ConfirmMisselection(dspy.Signature):
        """Decide whether the originally used tool was a misselection.

        Given the user's task, the available tools, and the downstream context
        after the tool call, decide verdict (confirm_misselection|false_positive),
        the better tool name, and a one-sentence rationale. Default to
        'false_positive' when uncertain.
        """

        task_description: str = dspy.InputField(
            desc="The user task that triggered the assistant tool call",
        )
        available_tools_summary: str = dspy.InputField(
            desc="Newline-separated list of '- name: description' for all current tools",
        )
        originally_used_tool: str = dspy.InputField(
            desc="Name of the tool the assistant actually called",
        )
        signal_source: str = dspy.InputField(
            desc="Which heuristic flagged this: error_retry|user_correction|oracle_disagreement",
        )
        downstream_context: str = dspy.InputField(
            desc="Summary of the next 1-3 messages after the tool call",
        )
        verdict: str = dspy.OutputField(
            desc="'confirm_misselection' or 'false_positive'; default 'false_positive' when unsure",
        )
        correct_tool: str = dspy.OutputField(
            desc="When confirm_misselection: name of the better tool from available_tools_summary",
        )
        rationale: str = dspy.OutputField(
            desc="One-sentence justification for the verdict",
        )

    class DetectUserCorrection(dspy.Signature):
        """LLM 二判 for A signal: decide whether a user message is genuinely
        correcting tool choice. Keyword regex pre-filter has already matched;
        this judge resolves false-positives where the keyword appears in
        unrelated context.
        """

        user_message: str = dspy.InputField(
            desc="The user message that followed the tool_call"
        )
        preceding_tool_call: str = dspy.InputField(
            desc="Name + args of the tool call being potentially corrected"
        )
        is_correction: bool = dspy.OutputField(
            desc="True if user is correcting the tool choice"
        )

    # User-correction keyword seeds (CONTEXT specifics + Open Questions resolution)
    _USER_CORRECTION_PATTERNS: list[str] = [
        r"不对",
        r"错了",
        r"不应该",
        r"应该用",
        r"应该是",
        r"换一个",
        r"换工具",
        r"不是要",
        r"\bwrong tool\b",
        r"\bshould have used\b",
        r"\buse \w+ instead\b",
        r"\bthat'?s not right\b",
    ]

    def __init__(
        self,
        config: EvolutionConfig,
        signals: Optional[list[str]] = None,
        multiplier_override: Optional[dict[str, int]] = None,
        baseline_module=None,  # ToolModule | None
    ):
        self.config = config
        self.signals = signals or list(VALID_SIGNALS)
        self.multiplier_override = multiplier_override or {}
        self.baseline_module = baseline_module
        self.judge = dspy.ChainOfThought(self.ConfirmMisselection)
        self.user_correction_judge = dspy.ChainOfThought(self.DetectUserCorrection)
        self.metrics: dict = self._fresh_metrics()

    def _fresh_metrics(self) -> dict:
        """Initialize 13-key metrics contract (B2 — dry-run and wet-run share schema)."""
        return {
            "total_candidates_by_signal": {s: 0 for s in VALID_SIGNALS},
            "judge_confirmed_by_signal": {s: 0 for s in VALID_SIGNALS},
            "judge_false_positives_by_signal": {s: 0 for s in VALID_SIGNALS},
            "surface_drift_dropped": 0,
            "surface_drift_tools": {},  # name -> count (PATTERNS §Pitfall 8 + W2)
            "secret_filter_skipped": 0,
            "jsonl_skipped_lines": 0,
            "judge_calls": 0,
            "judge_calls_by_signal": {s: 0 for s in VALID_SIGNALS},
            "cost_usd_spent": 0.0,
            "final_examples_by_split": {"train": 0, "val": 0, "holdout": 0},
            "final_train_after_duplication": 0,
            "multiplier_used": dict(DEFAULT_MULTIPLIER),
        }

    # ── parser helpers (schema-tolerant per Pitfall 1) ─────────────────────

    @staticmethod
    def _parse_tool_content(raw: str):
        """Best-effort json.loads of tool message content. Returns dict or None."""
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _is_tool_error(parsed_content, raw: str) -> bool:
        """B signal helper: tolerate three forms of tool error (Pitfall 2)."""
        if isinstance(parsed_content, dict):
            ec = parsed_content.get("exit_code")
            if isinstance(ec, int) and ec != 0:
                return True
            err = parsed_content.get("error")
            if isinstance(err, str) and err.strip() and err.strip().lower() != "null":
                return True
            return False
        return any(
            kw in (raw or "")
            for kw in ("Traceback", "Exception:", "Error:", '"error":')
        )

    @staticmethod
    def _find_tool_message_by_id(
        messages: list[dict], start: int, tc_id: str
    ) -> Optional[dict]:
        """Search forward for tool message with matching tool_call_id. Returns None if not found."""
        for j in range(start, len(messages)):
            m = messages[j]
            if not isinstance(m, dict):
                continue
            if m.get("role") == "tool" and m.get("tool_call_id") == tc_id:
                return m
            # stop at next user message (chunk boundary; Pitfall 3)
            if m.get("role") == "user":
                return None
        return None

    def _find_recovery_tool_call(
        self,
        messages: list[dict],
        start: int,
        failed_tool: str,
        current_tool_names: set[str],
    ) -> Optional[int]:
        """After a tool error, find next assistant tool_call whose name != failed_tool
        and whose tool result shows success (or at least no error). Returns the
        index of that assistant message, or None. Stops at next user message.
        """
        for j in range(start, len(messages)):
            m = messages[j]
            if not isinstance(m, dict):
                continue
            if m.get("role") == "user":
                return None
            if m.get("role") != "assistant":
                continue
            tool_calls = m.get("tool_calls")
            if not isinstance(tool_calls, list):
                continue
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                name = fn.get("name")
                tc_id = tc.get("id")
                if not name or name == failed_tool or not tc_id:
                    continue
                tool_msg = self._find_tool_message_by_id(messages, j + 1, tc_id)
                if tool_msg is None:
                    continue
                parsed = self._parse_tool_content(tool_msg.get("content", ""))
                if not self._is_tool_error(parsed, tool_msg.get("content", "")):
                    return j
        return None

    @staticmethod
    def _summarize_context(
        messages: list[dict], idx: int, recovery_idx: Optional[int] = None
    ) -> str:
        """Collect a ≤500-char summary of the next 1-3 turns after `idx`."""
        end = min(len(messages), idx + 4)
        if recovery_idx is not None:
            end = max(end, recovery_idx + 2)
            end = min(end, len(messages))
        parts: list[str] = []
        for j in range(idx + 1, end):
            m = messages[j]
            if not isinstance(m, dict):
                continue
            role = m.get("role", "?")
            content = m.get("content")
            if isinstance(content, str):
                parts.append(f"[{role}] {content[:120]}")
            else:
                tool_calls = m.get("tool_calls") or []
                names = []
                if isinstance(tool_calls, list):
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            fn = tc.get("function") or {}
                            n = fn.get("name")
                            if n:
                                names.append(n)
                if names:
                    parts.append(f"[{role}] tool_calls={names}")
        return " | ".join(parts)[:500]

    # ── B extractor: error_retry ──────────────────────────────────────────
    def _extract_error_retry(
        self,
        messages: list[dict],
        session_path: str,
        current_tool_names: set[str],
    ) -> list[Candidate]:
        """Extract B signal candidates: assistant tool_call → tool error →
        next assistant tool_call (different name) → success. Chunk boundary
        is the next user message (Pitfall 3).
        """
        cands: list[Candidate] = []
        current_user_task = ""
        i = 0
        while i < len(messages):
            m = messages[i] if isinstance(messages[i], dict) else {}
            role = m.get("role")
            if role == "user":
                current_user_task = (m.get("content") or "").strip()
                i += 1
                continue
            if role == "assistant":
                tool_calls = m.get("tool_calls")
                if not isinstance(tool_calls, list) or not tool_calls:
                    i += 1
                    continue
                for tc in tool_calls:
                    try:
                        if not isinstance(tc, dict):
                            continue
                        tc_id = tc.get("id") or ""
                        fn = tc.get("function") or {}
                        tool_name = fn.get("name")
                        if not tool_name or tc_id == "":
                            continue
                        tool_msg = self._find_tool_message_by_id(
                            messages, i + 1, tc_id
                        )
                        if tool_msg is None:
                            continue
                        parsed_content = self._parse_tool_content(
                            tool_msg.get("content", "")
                        )
                        if not self._is_tool_error(
                            parsed_content, tool_msg.get("content", "")
                        ):
                            continue
                        recovery = self._find_recovery_tool_call(
                            messages, i + 1, tool_name, current_tool_names
                        )
                        if recovery is None:
                            continue
                        cands.append(
                            Candidate(
                                task=current_user_task,
                                session_path=session_path,
                                originally_used_tool=tool_name,
                                available_tools=sorted(current_tool_names),
                                tool_call_id=tc_id,
                                signal="error_retry",
                                downstream_context=self._summarize_context(
                                    messages, i, recovery_idx=recovery
                                ),
                            )
                        )
                        break  # only first error→success switch per assistant turn
                    except Exception:
                        continue
            i += 1
        return cands

    # ── A extractor: user_correction ──────────────────────────────────────
    def _last_assistant_tool_call(
        self, messages: list[dict], before_idx: int
    ) -> tuple[Optional[str], Optional[str]]:
        """Return (tool_name, args_str) of last assistant tool_call before `before_idx`."""
        for j in range(before_idx - 1, -1, -1):
            m = messages[j] if isinstance(messages[j], dict) else {}
            if m.get("role") != "assistant":
                continue
            tcs = m.get("tool_calls")
            if not isinstance(tcs, list) or not tcs:
                continue
            last = tcs[-1] if isinstance(tcs[-1], dict) else None
            if last is None:
                continue
            fn = last.get("function") or {}
            return fn.get("name"), fn.get("arguments", "")
        return None, None

    def _user_message_matches_correction(self, text: str) -> bool:
        for pat in self._USER_CORRECTION_PATTERNS:
            try:
                if re.search(pat, text):
                    return True
            except re.error:
                continue
        return False

    def _extract_user_correction(
        self,
        messages: list[dict],
        session_path: str,
        current_tool_names: set[str],
    ) -> list[Candidate]:
        """Extract A signal candidates: user message after assistant tool_call
        contains a correction keyword, confirmed by LLM 二判 (DetectUserCorrection).
        """
        cands: list[Candidate] = []
        # task = most recent user message BEFORE the correction turn
        last_task: str = ""
        i = 0
        while i < len(messages):
            m = messages[i] if isinstance(messages[i], dict) else {}
            role = m.get("role")
            content = m.get("content")
            if role == "user" and isinstance(content, str):
                # If this user message matches correction pattern AND there is a
                # preceding assistant tool_call, it's an A candidate.
                if self._user_message_matches_correction(content):
                    tool_name, args_str = self._last_assistant_tool_call(messages, i)
                    if tool_name:
                        try:
                            lm = dspy.LM(
                                self.config.judge_model, **self.config.get_lm_kwargs()
                            )
                            with dspy.context(lm=lm):
                                result = self.user_correction_judge(
                                    user_message=content,
                                    preceding_tool_call=f"{tool_name}({args_str or ''})",
                                )
                            is_corr = _parse_bool(
                                getattr(result, "is_correction", False)
                            )
                        except Exception:
                            is_corr = False
                        if is_corr:
                            cands.append(
                                Candidate(
                                    task=last_task or content,
                                    session_path=session_path,
                                    originally_used_tool=tool_name,
                                    available_tools=sorted(current_tool_names),
                                    tool_call_id="",
                                    signal="user_correction",
                                    downstream_context=self._summarize_context(
                                        messages, i
                                    ),
                                )
                            )
                last_task = content.strip()
            i += 1
        return cands

    # ── C extractor: oracle_disagreement ──────────────────────────────────
    def _extract_oracle_disagreement(
        self,
        messages: list[dict],
        session_path: str,
        current_tool_names: set[str],
    ) -> list[Candidate]:
        """C signal: for each successful tool_call, ask the baseline ToolModule
        which tool it would pick; if different from what the session used,
        emit a candidate.
        """
        if self.baseline_module is None:
            return []
        cands: list[Candidate] = []
        current_user_task = ""
        i = 0
        while i < len(messages):
            m = messages[i] if isinstance(messages[i], dict) else {}
            role = m.get("role")
            if role == "user":
                current_user_task = (m.get("content") or "").strip()
                i += 1
                continue
            if role == "assistant":
                tool_calls = m.get("tool_calls")
                if isinstance(tool_calls, list):
                    for tc in tool_calls:
                        if not isinstance(tc, dict):
                            continue
                        tc_id = tc.get("id") or ""
                        fn = tc.get("function") or {}
                        tool_name = fn.get("name")
                        if not tool_name or not tc_id or not current_user_task:
                            continue
                        tool_msg = self._find_tool_message_by_id(
                            messages, i + 1, tc_id
                        )
                        if tool_msg is None:
                            continue
                        parsed = self._parse_tool_content(
                            tool_msg.get("content", "")
                        )
                        if self._is_tool_error(
                            parsed, tool_msg.get("content", "")
                        ):
                            continue  # only successful calls
                        try:
                            pred = self.baseline_module(
                                task_description=current_user_task
                            )
                            oracle_tool = getattr(pred, "selected_tool", None)
                        except Exception:
                            continue
                        if oracle_tool and oracle_tool != tool_name:
                            cands.append(
                                Candidate(
                                    task=current_user_task,
                                    session_path=session_path,
                                    originally_used_tool=tool_name,
                                    available_tools=sorted(current_tool_names),
                                    tool_call_id=tc_id,
                                    signal="oracle_disagreement",
                                    downstream_context=self._summarize_context(
                                        messages, i
                                    ),
                                )
                            )
            i += 1
        return cands

    # ── LLM judge (T-14-01 owns fail-closed) ──────────────────────────────
    def _judge_candidate(self, cand: Candidate) -> Verdict:
        """LLM judge per candidate. Fail-closed → false_positive on any error."""
        self.metrics["judge_calls"] += 1
        self.metrics["judge_calls_by_signal"][cand.signal] = (
            self.metrics["judge_calls_by_signal"].get(cand.signal, 0) + 1
        )
        lm = dspy.LM(self.config.judge_model, **self.config.get_lm_kwargs())
        tools_summary = "\n".join(f"- {n}" for n in cand.available_tools)
        try:
            with dspy.context(lm=lm):
                result = self.judge(
                    task_description=cand.task,
                    available_tools_summary=tools_summary,
                    originally_used_tool=cand.originally_used_tool,
                    signal_source=cand.signal,
                    downstream_context=cand.downstream_context,
                )
        except Exception as e:
            return Verdict(
                label="false_positive",
                correct_tool="",
                rationale=f"judge_error: {e}",
            )
        label = (str(getattr(result, "verdict", "")) or "").strip().lower()
        if label not in ("confirm_misselection", "false_positive"):
            label = "false_positive"
        correct = str(getattr(result, "correct_tool", "") or "").strip()
        rationale = str(getattr(result, "rationale", "") or "").strip()
        if (
            label == "confirm_misselection"
            and correct not in cand.available_tools
        ):
            label = "false_positive"
        return Verdict(label=label, correct_tool=correct, rationale=rationale)

    # ── orchestration ─────────────────────────────────────────────────────
    def _load_session(self, sp: Path) -> Optional[dict]:
        try:
            return json.loads(sp.read_text())
        except Exception:
            self.metrics["jsonl_skipped_lines"] += 1
            return None

    def _run_extractors(
        self,
        messages: list[dict],
        session_path: str,
        current_tool_names: set[str],
    ) -> list[Candidate]:
        cands: list[Candidate] = []
        if "error_retry" in self.signals:
            cands.extend(
                self._extract_error_retry(messages, session_path, current_tool_names)
            )
        if "user_correction" in self.signals:
            cands.extend(
                self._extract_user_correction(
                    messages, session_path, current_tool_names
                )
            )
        if (
            "oracle_disagreement" in self.signals
            and self.baseline_module is not None
        ):
            cands.extend(
                self._extract_oracle_disagreement(
                    messages, session_path, current_tool_names
                )
            )
        return cands

    def _filter_drift(
        self, cands: list[Candidate], current_tool_names: set[str]
    ) -> list[Candidate]:
        kept: list[Candidate] = []
        for c in cands:
            if c.originally_used_tool not in current_tool_names:
                self.metrics["surface_drift_dropped"] += 1
                self.metrics["surface_drift_tools"][c.originally_used_tool] = (
                    self.metrics["surface_drift_tools"].get(
                        c.originally_used_tool, 0
                    )
                    + 1
                )
                continue
            kept.append(c)
        return kept

    def _filter_secrets(self, cands: list[Candidate]) -> list[Candidate]:
        kept: list[Candidate] = []
        for c in cands:
            if _contains_secret(c.task) or _contains_secret(c.downstream_context):
                self.metrics["secret_filter_skipped"] += 1
                continue
            kept.append(c)
        return kept

    def mine(
        self,
        sessions_dir: Path,
        current_tools: list,
        limit: int = 0,
    ) -> list[ToolSelectionExample]:
        """Orchestrate end-to-end mining; returns deduped pre-split list."""
        self.metrics = self._fresh_metrics()
        current_tool_names: set[str] = {t.name for t in current_tools}
        session_paths = sorted(sessions_dir.glob("*.json"))
        if limit > 0:
            session_paths = session_paths[:limit]

        all_cands: list[Candidate] = []
        for sp in session_paths:
            data = self._load_session(sp)
            if data is None:
                continue
            messages = data.get("messages") or []
            if not isinstance(messages, list):
                continue
            all_cands.extend(
                self._run_extractors(messages, str(sp), current_tool_names)
            )

        for c in all_cands:
            self.metrics["total_candidates_by_signal"][c.signal] = (
                self.metrics["total_candidates_by_signal"].get(c.signal, 0) + 1
            )

        kept = self._filter_drift(all_cands, current_tool_names)
        kept2 = self._filter_secrets(kept)

        verdicts: list[tuple[Candidate, Verdict]] = []
        for c in kept2:
            v = self._judge_candidate(c)
            if v.label == "confirm_misselection":
                self.metrics["judge_confirmed_by_signal"][c.signal] = (
                    self.metrics["judge_confirmed_by_signal"].get(c.signal, 0) + 1
                )
                verdicts.append((c, v))
            else:
                self.metrics["judge_false_positives_by_signal"][c.signal] = (
                    self.metrics["judge_false_positives_by_signal"].get(
                        c.signal, 0
                    )
                    + 1
                )

        # Reduce by hash → union signals (D-02 末尾 + Pitfall 9)
        by_hash: dict[str, ToolSelectionExample] = {}
        for c, v in verdicts:
            h = c.task_hash()
            if h not in by_hash:
                by_hash[h] = ToolSelectionExample(
                    task_description=c.task,
                    correct_tool=v.correct_tool,
                    correct_params={},
                    difficulty="medium",
                    confuser_tools=[c.originally_used_tool],
                    reason=v.rationale,
                    source="session",
                    misselection_signals=[c.signal],
                )
            else:
                prev = by_hash[h]
                prev.misselection_signals = sorted(
                    set(prev.misselection_signals) | {c.signal}
                )
                prev.confuser_tools = sorted(
                    set(prev.confuser_tools) | {c.originally_used_tool}
                )
        return list(by_hash.values())

    def split_and_duplicate(
        self, examples: list[ToolSelectionExample]
    ) -> dict[str, list[ToolSelectionExample]]:
        """Bucket-split (D-13) then duplicate train-only by max multiplier (D-11)."""
        split: dict[str, list[ToolSelectionExample]] = {
            "train": [],
            "val": [],
            "holdout": [],
        }
        for ex in examples:
            h = _normalize_task_hash(ex.task_description)
            bucket = _hash_to_split(h)
            split[bucket].append(ex)
        # Train-only duplication (Pitfall 5)
        pre_dup_train_count = len(split["train"])
        duplicated_train: list[ToolSelectionExample] = []
        for ex in split["train"]:
            n = _multiplier_for(
                ex.misselection_signals, self.multiplier_override
            )
            duplicated_train.extend([ex] * n)
        split["train"] = duplicated_train

        self.metrics["final_examples_by_split"] = {
            "train": pre_dup_train_count,
            "val": len(split["val"]),
            "holdout": len(split["holdout"]),
        }
        self.metrics["final_train_after_duplication"] = len(duplicated_train)
        self.metrics["multiplier_used"] = {
            k: self.multiplier_override.get(k, DEFAULT_MULTIPLIER[k])
            for k in DEFAULT_MULTIPLIER
        }
        return split

    def enumerate_candidates(
        self,
        sessions_dir: Path,
        current_tools: list,
        limit: int = 0,
    ) -> list[Candidate]:
        """Public dry-run API (W4): runs 3 extractors + drift + secret filter,
        but **skips the LLM judge**. Plan 05 dry-run path uses this.
        """
        self.metrics = self._fresh_metrics()
        current_tool_names: set[str] = {t.name for t in current_tools}
        session_paths = sorted(sessions_dir.glob("*.json"))
        if limit > 0:
            session_paths = session_paths[:limit]
        all_cands: list[Candidate] = []
        for sp in session_paths:
            data = self._load_session(sp)
            if data is None:
                continue
            messages = data.get("messages") or []
            if not isinstance(messages, list):
                continue
            all_cands.extend(
                self._run_extractors(messages, str(sp), current_tool_names)
            )
        for c in all_cands:
            self.metrics["total_candidates_by_signal"][c.signal] = (
                self.metrics["total_candidates_by_signal"].get(c.signal, 0) + 1
            )
        kept = self._filter_drift(all_cands, current_tool_names)
        kept2 = self._filter_secrets(kept)
        return kept2

    def top_n_drift_tools(self, n: int = 10) -> list[tuple[str, int]]:
        """Return top-N surface-drift tool (name, count) sorted by count desc."""
        items = list(self.metrics.get("surface_drift_tools", {}).items())
        items.sort(key=lambda kv: (-kv[1], kv[0]))
        return items[:n]
