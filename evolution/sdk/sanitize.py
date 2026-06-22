"""Strip GEPA reflection metadata from optimizer candidates.

GEPA's reflection LM sometimes inlines its internal feedback notes —
training trace scores ("得分为 0.342", "Score: 0.461"), reflection tags
("反馈:", "feedback:"), case-study sections ("## 示例与反馈"), and
execute-style code fences ("<execute>...</execute>") — directly into the
candidate prompt. If a candidate like this lands on disk, the agent
sees the feedback text at runtime.

This module exposes:

    sanitize_candidate(text: str) -> tuple[str, list[str]]

Returns (cleaned_text, removed_markers). When markers are removed but
the leak is bounded to a known trailing section, the section is trimmed
in place. When the leak is interleaved with the prompt body, the
function refuses to sanitize and returns the original text + markers
so the caller can reject the candidate.

Conservative by design: prefer to leave the candidate untouched (and let
gate_1_forbidden reject it) over a destructive surgical edit.
"""
from __future__ import annotations

import re

# Markers that indicate GEPA reflection metadata. Match Chinese + English.
LEAK_PATTERNS = [
    r"得分为\s*\d+\.\d+",
    r"该轨迹",
    r"反馈[:：]\s*\S",
    r"<execute>",
    r"</execute>",
    r"Score:\s*\d+\.\d+",
    r"feedback[:：]\s*\d",
    r"示例与反馈解读",
    r"实际案例反馈",
    r"通过这些反馈",
    r"This trajectory got a score",
]

# H2/H3 headings GEPA tends to use as the leakage container. Used to find
# a clean trim point — we only delete the heading + everything after it
# if the body actually contains a leak marker.
_SUSPECT_HEADING_RE = re.compile(
    r"^#{2,3}\s+(?:.*(?:示例|反馈|案例|feedback|example).*)$",
    re.MULTILINE | re.IGNORECASE,
)


def find_leak_markers(text: str) -> list[str]:
    """Return the list of leak patterns that match anywhere in `text`."""
    return [p for p in LEAK_PATTERNS if re.search(p, text)]


def sanitize_candidate(text: str) -> tuple[str, list[str]]:
    """Return (sanitized_text, removed_markers_or_residual).

    - If no leak markers are present, returns (text, []).
    - If markers are confined to a trailing suspect H2/H3 section, trims
      the section. Returns (cleaned, removed_markers).
    - If markers exist but cannot be safely localized, returns (text,
      markers) — caller should reject the candidate.
    """
    initial_markers = find_leak_markers(text)
    if not initial_markers:
        return text, []

    # Try each suspect heading from latest to earliest; trim at the
    # first one whose body covers all current leak markers.
    headings = list(_SUSPECT_HEADING_RE.finditer(text))
    for h in reversed(headings):
        before = text[: h.start()].rstrip()
        after = text[h.start():]
        if find_leak_markers(after) and not find_leak_markers(before):
            return before + "\n", initial_markers

    # Fallback: trim at the paragraph boundary before the first leak.
    first_pat = next(p for p in LEAK_PATTERNS if re.search(p, text))
    first_match = re.search(first_pat, text)
    pre = text[: first_match.start()].rstrip()
    last_blank = pre.rfind("\n\n")
    if last_blank > 0:
        candidate_cleaned = pre[: last_blank].rstrip() + "\n"
        if not find_leak_markers(candidate_cleaned):
            return candidate_cleaned, initial_markers

    # Could not safely localise. Return original + markers for the caller.
    return text, initial_markers
