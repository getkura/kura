"""Parse MCP server configurations and tool definitions."""

import json
from pathlib import Path

from kura.models import ParamDescriptor, ToolDescriptor


def parse_mcp_file(path: Path) -> list[ToolDescriptor]:
    """Parse a JSON file containing MCP tools.

    Supports two formats:
    1. Claude Desktop config (has "mcpServers" key)
    2. Direct tool list (has "tools" key or is a list of tool objects)
    """
    with open(path) as f:
        data = json.load(f)

    if isinstance(data, dict) and "mcpServers" in data:
        return _parse_claude_desktop_config(data)
    elif isinstance(data, dict) and "tools" in data:
        return _parse_tool_list(data["tools"], source=path.stem)
    elif isinstance(data, list):
        return _parse_tool_list(data, source=path.stem)
    else:
        raise ValueError(
            f"Unrecognized JSON format in {path}. "
            "Expected 'mcpServers' (Claude Desktop config) or 'tools' (tool list)."
        )


def _parse_claude_desktop_config(data: dict) -> list[ToolDescriptor]:
    """Parse Claude Desktop config format.

    This format only contains server connection info, not tool definitions.
    We extract server names and note that live connection would be needed
    for full tool analysis.
    """
    tools = []
    servers = data.get("mcpServers", {})

    for server_name, server_config in servers.items():
        # Claude Desktop config doesn't include tool definitions inline.
        # Check if there's an embedded tools list (some extended formats have this)
        if "tools" in server_config:
            tools.extend(_parse_tool_list(server_config["tools"], source=server_name))
        else:
            # Create a placeholder noting this server needs live connection
            tools.append(ToolDescriptor(
                name=f"[{server_name}]",
                source=server_name,
                source_type="mcp",
                description=f"Server '{server_name}' found but tool definitions require live "
                            f"connection. Run: kura dump --server {server_name}",
                raw_config=server_config,
            ))

    return tools


def _parse_tool_list(tools_data: list[dict], source: str = "unknown") -> list[ToolDescriptor]:
    """Parse a list of MCP tool definitions."""
    tools = []

    for tool_data in tools_data:
        name = tool_data.get("name", "unnamed")
        description = tool_data.get("description", "")
        tool_source = tool_data.get("_source", source)

        # Parse input schema parameters
        params = []
        schema = tool_data.get("inputSchema", {})
        properties = schema.get("properties", {})
        required_params = set(schema.get("required", []))

        for param_name, param_schema in properties.items():
            params.append(ParamDescriptor(
                name=param_name,
                description=param_schema.get("description"),
                type=param_schema.get("type"),
                required=param_name in required_params,
                has_enum="enum" in param_schema,
                has_default="default" in param_schema,
            ))

        tools.append(ToolDescriptor(
            name=name,
            source=tool_source,
            source_type="mcp",
            description=description,
            parameters=params,
            raw_config=tool_data,
        ))

    return tools
