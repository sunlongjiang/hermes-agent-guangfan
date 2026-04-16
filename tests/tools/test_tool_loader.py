"""Tests for tool description extraction from hermes-agent tool files."""

import pytest
from pathlib import Path

from evolution.tools.tool_loader import (
    DescFormat,
    ToolParam,
    ToolDescription,
    discover_tool_files,
    extract_tool_descriptions,
)

# ── Sample tool file contents for testing 4 description formats ──

SAMPLE_SINGLE_LINE = '''
READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": "Read the contents of a file at the specified path.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The path to the file to read."
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to read."
            }
        },
        "required": ["file_path"],
    },
}
from tools.registry import registry
registry.register(name="read_file", schema=READ_FILE_SCHEMA, handler=lambda x: x)
'''

SAMPLE_PAREN_CONCAT = '''
MEMORY_SCHEMA = {
    "name": "memory",
    "description": (
        "Save durable information to persistent memory. "
        "Memory is injected into future turns."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "replace", "remove"],
                "description": "The action to perform."
            }
        },
        "required": ["action"],
    },
}
from tools.registry import registry
registry.register(name="memory", schema=MEMORY_SCHEMA, handler=lambda x: x)
'''

SAMPLE_TRIPLE_QUOTE = '''
CRON_SCHEMA = {
    "name": "cronjob",
    "description": """Schedule and manage cron jobs for recurring tasks.""",
    "parameters": {
        "type": "object",
        "properties": {
            "schedule": {
                "type": "string",
                "description": "Cron expression for scheduling."
            }
        },
        "required": ["schedule"],
    },
}
from tools.registry import registry
registry.register(name="cronjob", schema=CRON_SCHEMA, handler=lambda x: x)
'''

SAMPLE_VARIABLE_REF = '''
TERMINAL_TOOL_DESCRIPTION = (
    "Execute shell commands in the terminal. "
    "Use for file operations and system tasks."
)
TERMINAL_SCHEMA = {
    "name": "terminal",
    "description": TERMINAL_TOOL_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute."
            }
        },
        "required": ["command"],
    },
}
from tools.registry import registry
registry.register(name="terminal", schema=TERMINAL_SCHEMA, handler=lambda x: x)
'''

SAMPLE_LIST_SCHEMAS = '''
BROWSER_TOOL_SCHEMAS = [
    {
        "name": "browser_navigate",
        "description": "Navigate to a URL in the browser.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to navigate to."
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_click",
        "description": "Click an element on the page.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the element."
                }
            },
            "required": ["selector"],
        },
    },
]
from tools.registry import registry
for schema in BROWSER_TOOL_SCHEMAS:
    registry.register(name=schema["name"], schema=schema, handler=lambda x: x)
'''


class TestDescFormat:
    """Verify DescFormat enum has all 4 values."""

    def test_has_single_line(self):
        assert DescFormat.SINGLE_LINE.value == "single_line"

    def test_has_paren_concat(self):
        assert DescFormat.PAREN_CONCAT.value == "paren_concat"

    def test_has_triple_quote(self):
        assert DescFormat.TRIPLE_QUOTE.value == "triple_quote"

    def test_has_variable_ref(self):
        assert DescFormat.VARIABLE_REF.value == "variable_ref"


class TestToolParam:
    """Verify ToolParam dataclass fields and serialization."""

    def test_fields(self):
        p = ToolParam(
            name="action",
            type="string",
            required=True,
            enum=["add", "remove"],
            description="The action to perform.",
            desc_format=DescFormat.SINGLE_LINE,
            desc_line_offset=10,
        )
        assert p.name == "action"
        assert p.type == "string"
        assert p.required is True
        assert p.enum == ["add", "remove"]
        assert p.description == "The action to perform."
        assert p.desc_format == DescFormat.SINGLE_LINE
        assert p.desc_line_offset == 10

    def test_to_dict(self):
        p = ToolParam(name="cmd", type="string", required=True, description="A command.")
        d = p.to_dict()
        assert d["name"] == "cmd"
        assert d["type"] == "string"
        assert d["required"] is True
        assert d["description"] == "A command."
        # to_dict should include frozen + evolvable fields
        assert "name" in d
        assert "enum" in d

    def test_from_dict_roundtrip(self):
        original = ToolParam(
            name="target",
            type="string",
            required=False,
            enum=["memory", "user"],
            description="Which store.",
        )
        restored = ToolParam.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.type == original.type
        assert restored.required == original.required
        assert restored.enum == original.enum
        assert restored.description == original.description


class TestToolDescription:
    """Verify ToolDescription dataclass fields and serialization."""

    def test_fields(self):
        td = ToolDescription(
            name="memory",
            file_path=Path("/tmp/test.py"),
            description="Save info.",
            params=[ToolParam(name="action", type="string")],
            desc_format=DescFormat.PAREN_CONCAT,
            schema_var_name="MEMORY_SCHEMA",
            raw_source="source code",
        )
        assert td.name == "memory"
        assert td.file_path == Path("/tmp/test.py")
        assert td.description == "Save info."
        assert len(td.params) == 1
        assert td.desc_format == DescFormat.PAREN_CONCAT
        assert td.schema_var_name == "MEMORY_SCHEMA"

    def test_to_dict(self):
        td = ToolDescription(
            name="test",
            file_path=Path("/tmp/t.py"),
            description="Desc.",
            params=[ToolParam(name="x", type="string", description="X param.")],
        )
        d = td.to_dict()
        assert d["name"] == "test"
        assert d["file_path"] == "/tmp/t.py"
        assert d["description"] == "Desc."
        assert len(d["params"]) == 1
        assert d["params"][0]["name"] == "x"

    def test_from_dict_roundtrip(self):
        original = ToolDescription(
            name="memory",
            file_path=Path("/tmp/mem.py"),
            description="Save durable info.",
            params=[
                ToolParam(name="action", type="string", required=True, enum=["add"]),
                ToolParam(name="target", type="string", description="Which store."),
            ],
        )
        restored = ToolDescription.from_dict(original.to_dict())
        assert restored.name == original.name
        assert str(restored.file_path) == str(original.file_path)
        assert restored.description == original.description
        assert len(restored.params) == 2
        assert restored.params[0].name == "action"
        assert restored.params[1].description == "Which store."


class TestDiscoverToolFiles:
    """Verify discover_tool_files() filters correctly."""

    def test_returns_only_registry_files(self, tmp_path):
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        # File with registry.register -- should be included
        (tools_dir / "memory_tool.py").write_text(
            'SCHEMA = {"name": "memory"}\nregistry.register(name="memory", schema=SCHEMA)\n'
        )
        # File with registry.register -- should be included
        (tools_dir / "file_tools.py").write_text(
            'SCHEMA = {"name": "read"}\nregistry.register(name="read", schema=SCHEMA)\n'
        )
        # __init__.py -- should be excluded
        (tools_dir / "__init__.py").write_text("# init\n")
        # Helper without registry.register -- should be excluded
        (tools_dir / "debug_helpers.py").write_text("def helper(): pass\n")
        # registry.py itself -- no register call typically
        (tools_dir / "registry.py").write_text("class ToolRegistry: pass\n")

        files = discover_tool_files(tmp_path)
        names = [f.name for f in files]
        assert "memory_tool.py" in names
        assert "file_tools.py" in names
        assert "__init__.py" not in names
        assert "debug_helpers.py" not in names
        assert "registry.py" not in names

    def test_returns_sorted(self, tmp_path):
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        for name in ["z_tool.py", "a_tool.py", "m_tool.py"]:
            (tools_dir / name).write_text('registry.register(name="x", schema={})\n')
        files = discover_tool_files(tmp_path)
        assert files == sorted(files)


class TestExtract:
    """Test extract_tool_descriptions() for each description format."""

    def test_single_line_format(self, tmp_path):
        f = tmp_path / "tool.py"
        f.write_text(SAMPLE_SINGLE_LINE)
        tools = extract_tool_descriptions(f)
        assert len(tools) == 1
        t = tools[0]
        assert t.name == "read_file"
        assert t.description == "Read the contents of a file at the specified path."
        assert t.desc_format == DescFormat.SINGLE_LINE

    def test_paren_concat_format(self, tmp_path):
        f = tmp_path / "tool.py"
        f.write_text(SAMPLE_PAREN_CONCAT)
        tools = extract_tool_descriptions(f)
        assert len(tools) == 1
        t = tools[0]
        assert t.name == "memory"
        assert t.description == (
            "Save durable information to persistent memory. "
            "Memory is injected into future turns."
        )
        assert t.desc_format == DescFormat.PAREN_CONCAT

    def test_triple_quote_format(self, tmp_path):
        f = tmp_path / "tool.py"
        f.write_text(SAMPLE_TRIPLE_QUOTE)
        tools = extract_tool_descriptions(f)
        assert len(tools) == 1
        t = tools[0]
        assert t.name == "cronjob"
        assert t.description == "Schedule and manage cron jobs for recurring tasks."
        assert t.desc_format == DescFormat.TRIPLE_QUOTE

    def test_variable_ref_format(self, tmp_path):
        f = tmp_path / "tool.py"
        f.write_text(SAMPLE_VARIABLE_REF)
        tools = extract_tool_descriptions(f)
        assert len(tools) == 1
        t = tools[0]
        assert t.name == "terminal"
        assert t.description == (
            "Execute shell commands in the terminal. "
            "Use for file operations and system tasks."
        )
        assert t.desc_format == DescFormat.VARIABLE_REF


class TestExtractParams:
    """Verify frozen fields (type, required, enum) are correctly extracted."""

    def test_param_type_and_required(self, tmp_path):
        f = tmp_path / "tool.py"
        f.write_text(SAMPLE_SINGLE_LINE)
        tools = extract_tool_descriptions(f)
        t = tools[0]
        assert len(t.params) == 2

        fp = next(p for p in t.params if p.name == "file_path")
        assert fp.type == "string"
        assert fp.required is True
        assert fp.description == "The path to the file to read."

        ml = next(p for p in t.params if p.name == "max_lines")
        assert ml.type == "integer"
        assert ml.required is False

    def test_param_enum(self, tmp_path):
        f = tmp_path / "tool.py"
        f.write_text(SAMPLE_PAREN_CONCAT)
        tools = extract_tool_descriptions(f)
        t = tools[0]
        action = next(p for p in t.params if p.name == "action")
        assert action.enum == ["add", "replace", "remove"]
        assert action.required is True


class TestExtractListSchemas:
    """Verify list-of-schemas pattern (browser_tool.py style)."""

    def test_extracts_multiple_tools(self, tmp_path):
        f = tmp_path / "tool.py"
        f.write_text(SAMPLE_LIST_SCHEMAS)
        tools = extract_tool_descriptions(f)
        assert len(tools) == 2

        nav = next(t for t in tools if t.name == "browser_navigate")
        assert nav.description == "Navigate to a URL in the browser."
        assert len(nav.params) == 1
        assert nav.params[0].name == "url"

        click = next(t for t in tools if t.name == "browser_click")
        assert click.description == "Click an element on the page."
        assert len(click.params) == 1
        assert click.params[0].name == "selector"


class TestExtractEdgeCases:
    """Edge cases: non-existent files, files without schemas."""

    def test_nonexistent_file_returns_empty(self):
        tools = extract_tool_descriptions(Path("/nonexistent/file.py"))
        assert tools == []

    def test_no_schema_returns_empty(self, tmp_path):
        f = tmp_path / "helper.py"
        f.write_text("def helper(): pass\n")
        tools = extract_tool_descriptions(f)
        assert tools == []

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        tools = extract_tool_descriptions(f)
        assert tools == []
