"""Tests for prompt section extraction and write-back."""

from pathlib import Path

import pytest

from evolution.prompts.prompt_loader import (
    PromptSection,
    extract_prompt_sections,
    write_back_section,
)


# ── Fixture: realistic prompt_builder.py structure ──────────────────────────

SAMPLE_PROMPT_BUILDER = '''\
"""Prompt builder for hermes-agent."""

import os


# Non-target variable -- should NOT be extracted
TOOL_USE_ENFORCEMENT_GUIDANCE = (
    "Always use the appropriate tool when available. "
    "Never fabricate tool responses."
)

DEFAULT_AGENT_IDENTITY = (
    "You are Hermes, a helpful AI assistant. "
    "You help users with a variety of tasks "
    "including messaging, scheduling, and more."
)

MEMORY_GUIDANCE = (
    "When recalling information, search your memory first. "
    "Use exact phrases from the user when searching."
)

SESSION_SEARCH_GUIDANCE = (
    "Search previous sessions for relevant context. "
    "Prioritize recent sessions over older ones."
)

SKILLS_GUIDANCE = (
    "Follow skill instructions precisely. "
    "Report errors clearly if a skill step fails."
)

PLATFORM_HINTS = {
    "whatsapp": (
        "You are on WhatsApp. Keep messages concise. "
        "Use emoji sparingly. No markdown formatting."
    ),
    "telegram": (
        "You are on Telegram. Markdown is supported. "
        "You can use bold, italic, and code blocks."
    ),
    "discord": (
        "You are on Discord. Use Discord markdown. "
        "Keep responses under 2000 characters."
    ),
    "slack": (
        "You are on Slack. Use Slack mrkdwn format. "
        "Thread long conversations."
    ),
    "signal": (
        "You are on Signal. Keep messages simple. "
        "No rich formatting is available."
    ),
    "email": (
        "You are responding via email. Use proper "
        "email formatting with greeting and sign-off."
    ),
    "cron": (
        "You are running as a scheduled task. "
        "Be concise and action-oriented."
    ),
    "cli": (
        "You are in CLI mode. Be direct."
    ),
    "sms": (
        "You are on SMS. Keep messages under "
        "160 characters when possible."
    ),
}


def build_system_prompt(platform: str) -> str:
    """Build the full system prompt."""
    return DEFAULT_AGENT_IDENTITY + PLATFORM_HINTS.get(platform, "")
'''


class TestExtractAllSections:
    """Test extract_prompt_sections returns all 13 sections."""

    def test_extract_all_sections(self, tmp_path):
        src = tmp_path / "prompt_builder.py"
        src.write_text(SAMPLE_PROMPT_BUILDER)

        sections = extract_prompt_sections(src)
        assert len(sections) == 13, f"Expected 13 sections, got {len(sections)}"

    def test_section_metadata(self, tmp_path):
        src = tmp_path / "prompt_builder.py"
        src.write_text(SAMPLE_PROMPT_BUILDER)

        sections = extract_prompt_sections(src)
        for s in sections:
            # section_id is a non-empty string
            assert isinstance(s.section_id, str) and s.section_id
            # char_count matches len(text)
            assert s.char_count == len(s.text), (
                f"{s.section_id}: char_count={s.char_count} != len(text)={len(s.text)}"
            )
            # line_range is a tuple of two ints
            assert isinstance(s.line_range, tuple) and len(s.line_range) == 2
            assert isinstance(s.line_range[0], int) and isinstance(s.line_range[1], int)
            assert s.line_range[0] <= s.line_range[1]
            # source_path matches input
            assert s.source_path == src

    def test_str_section_ids(self, tmp_path):
        src = tmp_path / "prompt_builder.py"
        src.write_text(SAMPLE_PROMPT_BUILDER)

        sections = extract_prompt_sections(src)
        str_ids = {s.section_id for s in sections if not s.section_id.startswith("platform_hints.")}
        expected = {"default_agent_identity", "memory_guidance", "session_search_guidance", "skills_guidance"}
        assert str_ids == expected, f"Expected {expected}, got {str_ids}"

    def test_platform_hints_expansion(self, tmp_path):
        src = tmp_path / "prompt_builder.py"
        src.write_text(SAMPLE_PROMPT_BUILDER)

        sections = extract_prompt_sections(src)
        hint_ids = {s.section_id for s in sections if s.section_id.startswith("platform_hints.")}
        expected = {
            "platform_hints.whatsapp",
            "platform_hints.telegram",
            "platform_hints.discord",
            "platform_hints.slack",
            "platform_hints.signal",
            "platform_hints.email",
            "platform_hints.cron",
            "platform_hints.cli",
            "platform_hints.sms",
        }
        assert hint_ids == expected, f"Expected {expected}, got {hint_ids}"


# ── Write-back tests ───────────────────────────────────────────────────────

class TestWriteBack:
    """Test write_back_section round-trip for str and dict value sections."""

    def test_round_trip_str(self, tmp_path):
        """Extract -> modify str section -> write back -> re-extract."""
        src = tmp_path / "prompt_builder.py"
        src.write_text(SAMPLE_PROMPT_BUILDER)

        sections = extract_prompt_sections(src)
        original = {s.section_id: s.text for s in sections}

        target = next(s for s in sections if s.section_id == "memory_guidance")
        new_text = "EVOLVED: " + target.text

        write_back_section(src, target, new_text)

        sections2 = extract_prompt_sections(src)
        result = {s.section_id: s.text for s in sections2}

        assert result["memory_guidance"] == new_text
        # Other sections unchanged
        for sid in original:
            if sid != "memory_guidance":
                assert result[sid] == original[sid], f"{sid} changed unexpectedly"

    def test_round_trip_platform_hint(self, tmp_path):
        """Extract -> modify platform hint -> write back -> re-extract."""
        src = tmp_path / "prompt_builder.py"
        src.write_text(SAMPLE_PROMPT_BUILDER)

        sections = extract_prompt_sections(src)
        original = {s.section_id: s.text for s in sections}

        target = next(s for s in sections if s.section_id == "platform_hints.whatsapp")
        new_text = "EVOLVED: " + target.text

        write_back_section(src, target, new_text)

        sections2 = extract_prompt_sections(src)
        result = {s.section_id: s.text for s in sections2}

        assert result["platform_hints.whatsapp"] == new_text
        for sid in original:
            if sid != "platform_hints.whatsapp":
                assert result[sid] == original[sid], f"{sid} changed unexpectedly"

    def test_write_back_syntax_valid(self, tmp_path):
        """After write-back, py_compile succeeds."""
        import py_compile

        src = tmp_path / "prompt_builder.py"
        src.write_text(SAMPLE_PROMPT_BUILDER)

        sections = extract_prompt_sections(src)
        target = next(s for s in sections if s.section_id == "memory_guidance")

        write_back_section(src, target, "New guidance text for memory.")

        # Must not raise
        py_compile.compile(str(src), doraise=True)

    def test_write_back_isolation(self, tmp_path):
        """Modifying section A leaves section B byte-for-byte identical."""
        src = tmp_path / "prompt_builder.py"
        src.write_text(SAMPLE_PROMPT_BUILDER)

        sections = extract_prompt_sections(src)
        original = {s.section_id: s.text for s in sections}

        target = next(s for s in sections if s.section_id == "skills_guidance")
        write_back_section(src, target, "Evolved skills guidance.")

        sections2 = extract_prompt_sections(src)
        for s in sections2:
            if s.section_id != "skills_guidance":
                assert s.text == original[s.section_id], (
                    f"{s.section_id}: text changed after modifying skills_guidance"
                )

    def test_multiple_write_backs(self, tmp_path):
        """Write back two sections (bottom-to-top), both survive."""
        src = tmp_path / "prompt_builder.py"
        src.write_text(SAMPLE_PROMPT_BUILDER)

        sections = extract_prompt_sections(src)

        # Pick two sections: one str, one platform hint
        str_section = next(s for s in sections if s.section_id == "default_agent_identity")
        hint_section = next(s for s in sections if s.section_id == "platform_hints.sms")

        new_str_text = "EVOLVED identity text."
        new_hint_text = "EVOLVED SMS hint."

        # Process from bottom of file upward (per Pitfall 4)
        targets = sorted(
            [(hint_section, new_hint_text), (str_section, new_str_text)],
            key=lambda t: t[0].line_range[0],
            reverse=True,
        )
        for section, text in targets:
            write_back_section(src, section, text)

        sections2 = extract_prompt_sections(src)
        result = {s.section_id: s.text for s in sections2}

        assert result["default_agent_identity"] == new_str_text
        assert result["platform_hints.sms"] == new_hint_text
