"""Parsers for MCP configs and OpenClaw skills."""

from pathlib import Path

from kura.models import ToolDescriptor


def parse_path(path: Path) -> list[ToolDescriptor]:
    """Auto-detect input type and parse tools.

    Supports:
    - JSON files: MCP config or tool list
    - Directories: OpenClaw skills
    """
    if path.is_dir():
        from kura.parsers.skills import parse_skills_directory
        return parse_skills_directory(path)
    elif path.suffix == ".json":
        from kura.parsers.mcp import parse_mcp_file
        return parse_mcp_file(path)
    else:
        raise ValueError(f"Unsupported input: {path}. Expected .json file or directory.")
