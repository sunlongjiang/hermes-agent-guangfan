"""Extract tool descriptions from hermes-agent tool files.

Parses Python source files in hermes-agent/tools/ to extract tool schema
descriptions (top-level and per-parameter). Supports 4 description formats:
single-line strings, parenthesized string concatenation, triple-quoted strings,
and variable references.

Format-preserving write-back (Plan 02) will reuse the desc_format and positional
metadata captured here.
"""

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


# ── Description Format Enum ──────────────────────────────────────────────────

class DescFormat(Enum):
    """Description field format in source code."""
    SINGLE_LINE = "single_line"       # "description": "text"
    PAREN_CONCAT = "paren_concat"     # "description": ("a " "b ")
    TRIPLE_QUOTE = "triple_quote"     # "description": """text"""
    VARIABLE_REF = "variable_ref"     # "description": VAR_NAME


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class ToolParam:
    """A tool parameter -- frozen schema fields + evolvable description.

    Frozen fields (name, type, required, enum) are never modified by evolution.
    Only the description text is evolvable.
    """
    # Frozen fields (never modified by optimization)
    name: str
    type: str
    required: bool = False
    enum: Optional[list[str]] = None
    # Evolvable field
    description: str = ""
    # Source tracking for write-back
    desc_format: DescFormat = DescFormat.SINGLE_LINE
    desc_line_offset: int = 0

    def to_dict(self) -> dict:
        """Serialize to dict (frozen + evolvable fields)."""
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "enum": self.enum,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolParam":
        """Restore from serialized dict."""
        return cls(
            name=d["name"],
            type=d["type"],
            required=d.get("required", False),
            enum=d.get("enum"),
            description=d.get("description", ""),
        )


@dataclass
class ToolDescription:
    """A tool's full description -- top-level + parameters.

    Args:
        name: Tool name from schema (e.g. "memory", "terminal")
        file_path: Path to the source .py file
        description: Top-level description text (evolvable)
        params: List of ToolParam instances
        desc_format: Format of the top-level description in source
        schema_var_name: Variable name in source (e.g. "MEMORY_SCHEMA")
        raw_source: Original file content for write-back
    """
    name: str
    file_path: Path
    description: str
    params: list[ToolParam] = field(default_factory=list)
    # Source tracking for write-back
    desc_format: DescFormat = DescFormat.SINGLE_LINE
    schema_var_name: str = ""
    raw_source: str = ""

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "name": self.name,
            "file_path": str(self.file_path),
            "description": self.description,
            "params": [p.to_dict() for p in self.params],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolDescription":
        """Restore from serialized dict."""
        return cls(
            name=d["name"],
            file_path=Path(d["file_path"]),
            description=d["description"],
            params=[ToolParam.from_dict(p) for p in d.get("params", [])],
        )


# ── File Discovery ───────────────────────────────────────────────────────────

def discover_tool_files(hermes_agent_path: Path) -> list[Path]:
    """Find *.py files containing tool schemas in hermes-agent/tools/.

    Returns sorted list of .py files that contain ``registry.register(``
    calls, which indicates they define tool schemas.

    Args:
        hermes_agent_path: Root path of the hermes-agent repository.

    Returns:
        Sorted list of Path objects for tool definition files.
    """
    tools_dir = hermes_agent_path / "tools"
    if not tools_dir.exists():
        return []

    result = []
    for py_file in sorted(tools_dir.glob("*.py")):
        try:
            content = py_file.read_text()
        except Exception:
            continue
        if "registry.register(" in content:
            result.append(py_file)
    return result


# ── Schema Constant Discovery ────────────────────────────────────────────────

# Matches named schema constants: XXX_SCHEMA = { or XXX_SCHEMAS = [
_SCHEMA_VAR_PATTERN = re.compile(
    r'^([A-Z][A-Z0-9_]*(?:_SCHEMA|_SCHEMAS))\s*=\s*([\[{])',
    re.MULTILINE,
)


# ── Core Extraction ──────────────────────────────────────────────────────────

def extract_tool_descriptions(file_path: Path) -> list[ToolDescription]:
    """Extract tool descriptions from a Python source file.

    Parses schema dict constants (e.g. MEMORY_SCHEMA = {...}) and list
    constants (e.g. BROWSER_TOOL_SCHEMAS = [...]) to extract tool names,
    descriptions, and parameter metadata.

    Args:
        file_path: Path to a Python source file in hermes-agent/tools/.

    Returns:
        List of ToolDescription instances. Empty list if file doesn't exist
        or contains no schema definitions.
    """
    try:
        source = file_path.read_text()
    except (FileNotFoundError, OSError):
        return []

    results = []

    for match in _SCHEMA_VAR_PATTERN.finditer(source):
        var_name = match.group(1)
        bracket = match.group(2)
        start = match.start()

        try:
            if bracket == "[":
                # List of schemas (e.g. BROWSER_TOOL_SCHEMAS = [...])
                list_start = source.index("[", start)
                list_end = _find_matching_bracket(source, list_start, "[", "]")
                if list_end < 0:
                    continue
                list_text = source[list_start:list_end + 1]
                # Extract individual schema dicts from within the list
                tools = _extract_schemas_from_list(
                    list_text, var_name, file_path, source,
                )
                results.extend(tools)
            else:
                # Single schema dict (e.g. MEMORY_SCHEMA = {...})
                dict_start = source.index("{", start)
                dict_end = _find_matching_bracket(source, dict_start, "{", "}")
                if dict_end < 0:
                    continue
                dict_text = source[dict_start:dict_end + 1]
                tool = _extract_single_schema(
                    dict_text, var_name, file_path, source,
                )
                if tool:
                    results.append(tool)
        except Exception as e:
            console.print(f"[yellow]Warning: failed to parse {var_name} in {file_path.name}: {e}[/yellow]")
            continue

    return results


# ── Internal Helpers ─────────────────────────────────────────────────────────

def _find_matching_bracket(source: str, start: int, open_char: str, close_char: str) -> int:
    """Find the position of the matching closing bracket.

    Handles nested brackets and skips content inside string literals.

    Args:
        source: Full source text.
        start: Position of the opening bracket.
        open_char: Opening bracket character ('{' or '[').
        close_char: Closing bracket character ('}' or ']').

    Returns:
        Position of the matching close bracket, or -1 if not found.
    """
    depth = 0
    i = start
    length = len(source)

    while i < length:
        ch = source[i]

        # Skip string literals
        if ch in ('"', "'"):
            # Check for triple-quote
            if source[i:i+3] in ('"""', "'''"):
                quote = source[i:i+3]
                i += 3
                while i < length - 2:
                    if source[i:i+3] == quote:
                        i += 3
                        break
                    i += 1
                else:
                    return -1
                continue
            else:
                quote = ch
                i += 1
                while i < length:
                    if source[i] == '\\':
                        i += 2
                        continue
                    if source[i] == quote:
                        i += 1
                        break
                    i += 1
                continue

        # Skip comments
        if ch == '#':
            while i < length and source[i] != '\n':
                i += 1
            continue

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return i

        i += 1

    return -1


def _extract_description_at(source: str, pos: int, file_source: str = "") -> tuple[str, DescFormat, int, int]:
    """Extract a description value starting after '"description":'.

    Args:
        source: Text to search in (may be the schema block or full file).
        pos: Position right after the colon in '"description":'.
        file_source: Full file source for resolving variable references.

    Returns:
        Tuple of (text, format, start_offset, end_offset).
    """
    # Skip whitespace
    while pos < len(source) and source[pos] in ' \t\n\r':
        pos += 1

    if pos >= len(source):
        return ("", DescFormat.SINGLE_LINE, pos, pos)

    char = source[pos]

    # Parenthesized string concatenation: ("a " "b ")
    if char == '(':
        paren_end = _find_matching_bracket(source, pos, '(', ')')
        if paren_end < 0:
            return ("", DescFormat.PAREN_CONCAT, pos, pos)
        raw = source[pos:paren_end + 1]
        try:
            text = ast.literal_eval(raw)
        except Exception:
            # Fallback: extract strings manually
            text = _extract_concat_strings(raw)
        return (text, DescFormat.PAREN_CONCAT, pos, paren_end + 1)

    # Triple-quoted string
    if source[pos:pos+3] in ('"""', "'''"):
        quote = source[pos:pos+3]
        end = source.find(quote, pos + 3)
        if end < 0:
            return ("", DescFormat.TRIPLE_QUOTE, pos, pos)
        raw = source[pos:end + 3]
        try:
            text = ast.literal_eval(raw)
        except Exception:
            text = raw[3:-3]
        return (text, DescFormat.TRIPLE_QUOTE, pos, end + 3)

    # Single-line string
    if char in ('"', "'"):
        # Find the end of the string, handling escapes
        quote = char
        i = pos + 1
        while i < len(source):
            if source[i] == '\\':
                i += 2
                continue
            if source[i] == quote:
                raw = source[pos:i + 1]
                try:
                    text = ast.literal_eval(raw)
                except Exception:
                    text = raw[1:-1]
                return (text, DescFormat.SINGLE_LINE, pos, i + 1)
            i += 1
        return ("", DescFormat.SINGLE_LINE, pos, pos)

    # Variable reference: UPPER_CASE_NAME
    if char.isupper() or char == '_':
        var_match = re.match(r'[A-Z_][A-Z0-9_]*', source[pos:])
        if var_match:
            var_name = var_match.group()
            end_pos = pos + len(var_name)
            # Resolve variable from file source
            text = _resolve_variable(var_name, file_source or source)
            return (text, DescFormat.VARIABLE_REF, pos, end_pos)

    return ("", DescFormat.SINGLE_LINE, pos, pos)


def _extract_concat_strings(raw: str) -> str:
    """Fallback string concatenation extractor using regex."""
    strings = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', raw)
    if not strings:
        strings = re.findall(r"'([^'\\]*(?:\\.[^'\\]*)*)'", raw)
    return "".join(strings)


def _resolve_variable(var_name: str, source: str) -> str:
    """Resolve a variable reference by finding its definition in the source.

    Handles patterns like:
        VAR_NAME = "text"
        VAR_NAME = ("text " "more text")
        VAR_NAME = \"\"\"text\"\"\"
    """
    # Pattern: VAR_NAME = <value>
    pattern = re.compile(
        rf'^{re.escape(var_name)}\s*=\s*',
        re.MULTILINE,
    )
    match = pattern.search(source)
    if not match:
        return ""

    value_start = match.end()
    text, _, _, _ = _extract_description_at(source, value_start, source)
    return text


def _extract_single_schema(
    dict_text: str,
    var_name: str,
    file_path: Path,
    file_source: str,
) -> Optional[ToolDescription]:
    """Extract a ToolDescription from a single schema dict text block."""
    # Extract name
    name_match = re.search(r'"name"\s*:\s*"([^"]+)"', dict_text)
    if not name_match:
        return None
    name = name_match.group(1)

    # Extract top-level description
    desc_text, desc_format = "", DescFormat.SINGLE_LINE
    desc_match = re.search(r'"description"\s*:\s*', dict_text)
    if desc_match:
        # Find the description that's at the top level of the schema dict
        # (before "parameters" key)
        params_pos = dict_text.find('"parameters"')
        if params_pos < 0:
            params_pos = len(dict_text)

        if desc_match.start() < params_pos:
            desc_text, desc_format, _, _ = _extract_description_at(
                dict_text, desc_match.end(), file_source,
            )

    # Extract parameters
    params = _extract_properties(dict_text, file_source)

    return ToolDescription(
        name=name,
        file_path=file_path,
        description=desc_text,
        params=params,
        desc_format=desc_format,
        schema_var_name=var_name,
        raw_source=file_source,
    )


def _extract_schemas_from_list(
    list_text: str,
    var_name: str,
    file_path: Path,
    file_source: str,
) -> list[ToolDescription]:
    """Extract multiple ToolDescriptions from a list of schema dicts."""
    results = []

    # Find each top-level dict in the list by matching { ... }
    i = 1  # Skip the opening [
    while i < len(list_text):
        if list_text[i] == '{':
            end = _find_matching_bracket(list_text, i, '{', '}')
            if end < 0:
                break
            dict_text = list_text[i:end + 1]
            tool = _extract_single_schema(dict_text, var_name, file_path, file_source)
            if tool:
                results.append(tool)
            i = end + 1
        else:
            i += 1

    return results


def _extract_properties(dict_text: str, file_source: str) -> list[ToolParam]:
    """Extract parameters from the 'properties' block of a schema dict.

    Args:
        dict_text: The full schema dict text.
        file_source: Full file source for variable resolution.

    Returns:
        List of ToolParam instances.
    """
    params = []

    # Find "properties" block
    props_match = re.search(r'"properties"\s*:\s*\{', dict_text)
    if not props_match:
        return params

    props_start = dict_text.index('{', props_match.start() + len('"properties"'))
    props_end = _find_matching_bracket(dict_text, props_start, '{', '}')
    if props_end < 0:
        return params

    properties_block = dict_text[props_start + 1:props_end]

    # Extract required fields list
    required_list = _extract_required_list(dict_text)

    # Find each property: "param_name": { ... }
    prop_pattern = re.compile(r'"([^"]+)"\s*:\s*\{')
    pos = 0
    while pos < len(properties_block):
        prop_match = prop_pattern.search(properties_block, pos)
        if not prop_match:
            break

        param_name = prop_match.group(1)
        brace_start = properties_block.index('{', prop_match.start())
        brace_end = _find_matching_bracket(properties_block, brace_start, '{', '}')
        if brace_end < 0:
            break

        prop_text = properties_block[brace_start:brace_end + 1]
        param = _parse_param(param_name, prop_text, required_list, file_source)
        params.append(param)

        pos = brace_end + 1

    return params


def _extract_required_list(dict_text: str) -> list[str]:
    """Extract the 'required' list from a schema dict."""
    req_match = re.search(r'"required"\s*:\s*\[([^\]]*)\]', dict_text)
    if not req_match:
        return []
    req_text = req_match.group(1)
    return re.findall(r'"([^"]+)"', req_text)


# ── Write-Back ──────────────────────────────────────────────────────────────


def write_back_description(
    file_path: Path,
    tool: ToolDescription,
    new_description: str,
    param_name: Optional[str] = None,
) -> None:
    """Replace a description in the source file, preserving format.

    Reads the file, locates the target description within the schema variable,
    replaces it with new_description formatted to match the original format,
    and writes the file back.

    Args:
        file_path: Path to the tool .py file.
        tool: ToolDescription from extract_tool_descriptions().
        new_description: The evolved description text.
        param_name: If set, replace this param's description instead of top-level.
    """
    source = file_path.read_text()

    if param_name:
        target_param = next(p for p in tool.params if p.name == param_name)
        old_desc = target_param.description
        fmt = target_param.desc_format
    else:
        old_desc = tool.description
        fmt = tool.desc_format

    if fmt == DescFormat.VARIABLE_REF:
        source = _write_back_variable_ref(source, tool, new_description)
    else:
        # Locate the schema variable in the source
        schema_start, schema_end = _find_schema_range(source, tool.schema_var_name)
        if schema_start < 0:
            raise ValueError(f"Cannot find schema variable {tool.schema_var_name} in {file_path}")

        schema_text = source[schema_start:schema_end + 1]

        if param_name:
            # Find the param's description within the properties block
            start, end = _find_param_desc_position(schema_text, param_name)
        else:
            # Find the top-level description (before "parameters" key)
            start, end = _find_top_level_desc_position(schema_text)

        if start < 0:
            raise ValueError(f"Cannot locate description position in {file_path}")

        # Build replacement string in the original format
        replacement = _format_description(new_description, fmt)

        # Apply the replacement in the schema text, then splice back into source
        new_schema = schema_text[:start] + replacement + schema_text[end:]
        source = source[:schema_start] + new_schema + source[schema_end + 1:]

    file_path.write_text(source)


def _find_schema_range(source: str, schema_var_name: str) -> tuple[int, int]:
    """Find the start and end positions of a schema variable definition.

    Returns:
        Tuple of (start, end) positions. start is the opening bracket,
        end is the closing bracket. Returns (-1, -1) if not found.
    """
    pattern = re.compile(
        rf'^{re.escape(schema_var_name)}\s*=\s*([\[{{])',
        re.MULTILINE,
    )
    match = pattern.search(source)
    if not match:
        return (-1, -1)

    bracket = match.group(1)
    bracket_start = match.start(1)
    open_char = bracket
    close_char = '}' if bracket == '{' else ']'
    bracket_end = _find_matching_bracket(source, bracket_start, open_char, close_char)
    return (bracket_start, bracket_end)


def _find_top_level_desc_position(schema_text: str) -> tuple[int, int]:
    """Find start/end of the top-level description value in schema text.

    Only matches "description" keys that appear before "parameters".

    Returns:
        (start, end) offsets within schema_text for the value portion.
    """
    params_pos = schema_text.find('"parameters"')
    if params_pos < 0:
        params_pos = len(schema_text)

    desc_match = re.search(r'"description"\s*:\s*', schema_text)
    if not desc_match or desc_match.start() >= params_pos:
        return (-1, -1)

    value_start = desc_match.end()
    _, _, start, end = _extract_description_at(schema_text, value_start, schema_text)
    return (start, end)


def _find_param_desc_position(schema_text: str, param_name: str) -> tuple[int, int]:
    """Find start/end of a specific parameter's description value.

    Locates the "properties" block, finds the named parameter within it,
    then finds its "description" key.

    Returns:
        (start, end) offsets within schema_text for the value portion.
    """
    # Find "properties" block
    props_match = re.search(r'"properties"\s*:\s*\{', schema_text)
    if not props_match:
        return (-1, -1)

    props_brace = schema_text.index('{', props_match.start() + len('"properties"'))
    props_end = _find_matching_bracket(schema_text, props_brace, '{', '}')
    if props_end < 0:
        return (-1, -1)

    # Find the named parameter block within properties
    param_pattern = re.compile(rf'"{re.escape(param_name)}"\s*:\s*\{{')
    param_match = param_pattern.search(schema_text, props_brace, props_end)
    if not param_match:
        return (-1, -1)

    param_brace = schema_text.index('{', param_match.start() + len(f'"{param_name}"'))
    param_end = _find_matching_bracket(schema_text, param_brace, '{', '}')
    if param_end < 0:
        return (-1, -1)

    # Find "description" within this param block
    param_text = schema_text[param_brace:param_end + 1]
    desc_match = re.search(r'"description"\s*:\s*', param_text)
    if not desc_match:
        return (-1, -1)

    value_start = desc_match.end()
    _, _, rel_start, rel_end = _extract_description_at(param_text, value_start, schema_text)
    # Convert offsets relative to param_text back to schema_text offsets
    abs_start = param_brace + rel_start
    abs_end = param_brace + rel_end
    return (abs_start, abs_end)


def _write_back_variable_ref(source: str, tool: ToolDescription, new_description: str) -> str:
    """Write back by replacing the variable definition's value.

    For VARIABLE_REF format, the schema has "description": VAR_NAME,
    so we find the VAR_NAME = ... definition and replace its value.
    """
    # Find which variable is referenced in the schema
    schema_start, schema_end = _find_schema_range(source, tool.schema_var_name)
    if schema_start < 0:
        raise ValueError(f"Cannot find schema variable {tool.schema_var_name}")

    schema_text = source[schema_start:schema_end + 1]

    # Find "description": VAR_NAME in the schema
    desc_match = re.search(r'"description"\s*:\s*([A-Z_][A-Z0-9_]*)', schema_text)
    if not desc_match:
        raise ValueError("Cannot find variable reference in schema description")

    var_name = desc_match.group(1)

    # Find the variable definition: VAR_NAME = <value>
    var_pattern = re.compile(
        rf'^{re.escape(var_name)}\s*=\s*',
        re.MULTILINE,
    )
    var_match = var_pattern.search(source)
    if not var_match:
        raise ValueError(f"Cannot find variable definition for {var_name}")

    value_start = var_match.end()
    _, orig_fmt, start, end = _extract_description_at(source, value_start, source)

    # Format the replacement using the variable's original format
    replacement = _format_description(new_description, orig_fmt)
    return source[:start] + replacement + source[end:]


def _format_description(text: str, fmt: DescFormat) -> str:
    """Format a description string according to the original format type.

    Args:
        text: The new description text (plain string).
        fmt: The format to use for encoding.

    Returns:
        Formatted string ready to splice into source code.
    """
    if fmt == DescFormat.SINGLE_LINE:
        escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'

    elif fmt == DescFormat.PAREN_CONCAT:
        if len(text) <= 80 and '\n' not in text:
            escaped = text.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        # Split into lines for multi-line paren concat
        return _format_paren_concat(text)

    elif fmt == DescFormat.TRIPLE_QUOTE:
        safe = text.replace('"""', '\\"""')
        return f'"""{safe}"""'

    else:
        # Default fallback: single-line
        escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'


def _format_paren_concat(text: str) -> str:
    """Format text as parenthesized string concatenation.

    Splits text into ~70-char lines wrapped in parentheses.
    Handles embedded newlines by keeping them as \\n within strings.
    """
    # Split on explicit newlines first
    segments = text.split('\n')
    lines = []
    for seg in segments:
        # If segment is short enough, keep as one piece
        if len(seg) <= 70:
            lines.append(seg + '\n' if seg != segments[-1] else seg)
        else:
            # Split at word boundaries around 70 chars
            words = seg.split(' ')
            current = ""
            for word in words:
                if current and len(current) + 1 + len(word) > 70:
                    lines.append(current + ' ')
                    current = word
                else:
                    current = current + ' ' + word if current else word
            if current:
                if seg != segments[-1]:
                    lines.append(current + '\n')
                else:
                    lines.append(current)

    parts = []
    for line in lines:
        escaped = line.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        parts.append(f'        "{escaped}"')

    return '(\n' + '\n'.join(parts) + '\n    )'


def _parse_param(
    name: str,
    prop_text: str,
    required_list: list[str],
    file_source: str,
) -> ToolParam:
    """Parse a single parameter from its property dict text."""
    # Extract type
    type_match = re.search(r'"type"\s*:\s*"([^"]+)"', prop_text)
    param_type = type_match.group(1) if type_match else "string"

    # Extract enum
    enum_match = re.search(r'"enum"\s*:\s*\[([^\]]*)\]', prop_text)
    param_enum = None
    if enum_match:
        param_enum = re.findall(r'"([^"]+)"', enum_match.group(1))

    # Extract description
    desc_text = ""
    desc_format = DescFormat.SINGLE_LINE
    desc_match = re.search(r'"description"\s*:\s*', prop_text)
    if desc_match:
        desc_text, desc_format, _, _ = _extract_description_at(
            prop_text, desc_match.end(), file_source,
        )

    return ToolParam(
        name=name,
        type=param_type,
        required=name in required_list,
        enum=param_enum,
        description=desc_text,
        desc_format=desc_format,
    )
