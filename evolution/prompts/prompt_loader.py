"""Extract and write-back prompt sections from hermes-agent's prompt_builder.py.

Parses prompt_builder.py using Python's ast module to locate the 5 evolvable
prompt variables (4 str constants + 1 PLATFORM_HINTS dict). Each variable is
extracted as a PromptSection with metadata for format-preserving write-back.

The extraction covers:
- DEFAULT_AGENT_IDENTITY, MEMORY_GUIDANCE, SESSION_SEARCH_GUIDANCE, SKILLS_GUIDANCE
  (parenthesized string concatenation constants)
- PLATFORM_HINTS dict (each key expanded to an independent PromptSection)

Write-back replaces the source lines at the AST-provided line range, preserving
all surrounding code unchanged.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

console = Console()


# ── Target Variables ────────────────────────────────────────────────────────

TARGET_STR_VARS = {
    "DEFAULT_AGENT_IDENTITY": "default_agent_identity",
    "MEMORY_GUIDANCE": "memory_guidance",
    "SESSION_SEARCH_GUIDANCE": "session_search_guidance",
    "SKILLS_GUIDANCE": "skills_guidance",
}

TARGET_DICT_VAR = "PLATFORM_HINTS"


# ── Data Class ──────────────────────────────────────────────────────────────

@dataclass
class PromptSection:
    """An extracted prompt section with metadata for write-back.

    Args:
        section_id: Identifier like "default_agent_identity" or "platform_hints.whatsapp".
        text: The extracted plain text content.
        char_count: Character count (== len(text)).
        line_range: Source file line range (start, end), 1-based inclusive.
        source_path: Path to the source file.
    """
    section_id: str
    text: str
    char_count: int
    line_range: tuple[int, int]
    source_path: Path

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "section_id": self.section_id,
            "text": self.text,
            "char_count": self.char_count,
            "line_range": list(self.line_range),
            "source_path": str(self.source_path),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PromptSection":
        """Restore from serialized dict."""
        return cls(
            section_id=d["section_id"],
            text=d["text"],
            char_count=d["char_count"],
            line_range=tuple(d["line_range"]),
            source_path=Path(d["source_path"]),
        )


# ── Extraction ──────────────────────────────────────────────────────────────

def extract_prompt_sections(prompt_builder_path: Path) -> list[PromptSection]:
    """Extract all evolvable prompt sections from prompt_builder.py.

    Parses the source with ast.parse() and walks the AST to find target
    variable assignments. Returns PromptSection objects sorted by line number.

    Args:
        prompt_builder_path: Path to prompt_builder.py.

    Returns:
        List of PromptSection objects (4 str sections + N platform hint sections).
    """
    source = prompt_builder_path.read_text()
    tree = ast.parse(source)
    sections: list[PromptSection] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue

        var_name = target.id

        if var_name in TARGET_STR_VARS:
            # Parenthesized string concatenation -> single ast.Constant
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                text = node.value.value
                sections.append(PromptSection(
                    section_id=TARGET_STR_VARS[var_name],
                    text=text,
                    char_count=len(text),
                    line_range=(node.lineno, node.end_lineno),
                    source_path=prompt_builder_path,
                ))

        elif var_name == TARGET_DICT_VAR:
            # Dict -> expand each key to independent PromptSection
            if isinstance(node.value, ast.Dict):
                for key_node, val_node in zip(node.value.keys, node.value.values):
                    if (isinstance(key_node, ast.Constant)
                            and isinstance(val_node, ast.Constant)
                            and isinstance(val_node.value, str)):
                        key = key_node.value
                        text = val_node.value
                        # Use value node's line range (not Assign node's)
                        sections.append(PromptSection(
                            section_id=f"platform_hints.{key}",
                            text=text,
                            char_count=len(text),
                            line_range=(val_node.lineno, val_node.end_lineno),
                            source_path=prompt_builder_path,
                        ))

    # Sort by line number for deterministic order
    sections.sort(key=lambda s: s.line_range[0])
    return sections


# ── Write-Back ──────────────────────────────────────────────────────────────

def write_back_section(
    prompt_builder_path: Path,
    section: PromptSection,
    new_text: str,
) -> None:
    """Write evolved text back to prompt_builder.py, preserving format.

    Reads the file, determines section type from section_id, formats the
    replacement text as parenthesized string concatenation, and replaces
    the lines at section.line_range.

    For batch writes, callers must process sections from bottom of file
    upward (highest line_range first) so earlier sections' line numbers
    remain valid.

    Args:
        prompt_builder_path: Path to prompt_builder.py.
        section: The PromptSection to replace (provides line_range).
        new_text: The evolved text to write back.
    """
    source = prompt_builder_path.read_text()
    lines = source.splitlines(keepends=True)

    start_line, end_line = section.line_range  # 1-based inclusive

    if section.section_id.startswith("platform_hints."):
        # Dict value: replace only the value's string content lines
        replacement = _format_dict_value_paren_concat(new_text, indent=8)
    else:
        # Top-level str assignment: replace entire assignment block
        var_name = section.section_id.upper()
        replacement = _format_paren_concat(var_name, new_text, indent=4)

    # Ensure replacement ends with newline
    if not replacement.endswith("\n"):
        replacement += "\n"

    # Line-level replacement (1-based inclusive -> 0-based slice)
    replacement_lines = replacement.splitlines(keepends=True)
    new_lines = lines[:start_line - 1] + replacement_lines + lines[end_line:]
    prompt_builder_path.write_text("".join(new_lines))


# ── Formatting Helpers ──────────────────────────────────────────────────────

def _format_paren_concat(var_name: str, text: str, indent: int = 4) -> str:
    """Format text as a parenthesized concat str assignment.

    Output format:
        VAR_NAME = (
            "line1 "
            "line2"
        )

    Args:
        var_name: The Python variable name (e.g. "MEMORY_GUIDANCE").
        text: The plain text to format.
        indent: Number of spaces for string line indentation.

    Returns:
        Formatted assignment string (no trailing newline).
    """
    str_lines = _split_text_lines(text, max_width=70)
    pad = " " * indent
    parts = []
    for i, line in enumerate(str_lines):
        escaped = _escape_str(line)
        parts.append(f'{pad}"{escaped}"')

    return f"{var_name} = (\n" + "\n".join(parts) + "\n)"


def _format_dict_value_paren_concat(text: str, indent: int = 8) -> str:
    """Format text as parenthesized concat lines for a dict value.

    Replaces only the string content lines within a dict value.
    The key line (e.g. '"whatsapp": (') and closing '),' are
    preserved by the caller's line-range replacement.

    Output format (indented at 8 spaces for dict nesting):
            "line1 "
            "line2"

    Args:
        text: The plain text to format.
        indent: Number of spaces for indentation.

    Returns:
        Formatted string lines (no trailing newline).
    """
    str_lines = _split_text_lines(text, max_width=60)
    pad = " " * indent
    parts = []
    for line in str_lines:
        escaped = _escape_str(line)
        parts.append(f'{pad}"{escaped}"')

    return "\n".join(parts)


def _split_text_lines(text: str, max_width: int = 70) -> list[str]:
    """Split text into lines suitable for parenthesized concat format.

    Each line except the last gets a trailing space (for implicit concat).
    """
    if len(text) <= max_width:
        return [text]

    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > max_width:
            # Trailing space for implicit string concat
            lines.append(current + " ")
            current = word
        else:
            current = current + " " + word if current else word
    if current:
        lines.append(current)

    return lines


def _escape_str(text: str) -> str:
    """Escape text for use inside double-quoted Python string literals."""
    return (
        text
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
