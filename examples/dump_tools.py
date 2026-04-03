#!/usr/bin/env python3
"""Dump tool definitions from MCP servers configured in Claude Desktop.

Usage:
    # Dump all servers from Claude Desktop config
    python dump_tools.py

    # Dump a specific server
    python dump_tools.py --server github

    # Custom config path
    python dump_tools.py --config /path/to/claude_desktop_config.json

    # Save to file (for use with kura scan)
    python dump_tools.py > my_tools.json

Requires: pip install mcp
"""

import asyncio
import json
import os
import sys
from pathlib import Path

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("Error: install the MCP SDK first: pip install mcp", file=sys.stderr)
    sys.exit(1)


def find_config() -> Path:
    """Find Claude Desktop config file."""
    candidates = [
        # macOS
        Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        # Linux
        Path.home() / ".config" / "claude" / "claude_desktop_config.json",
        # Windows
        Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


async def dump_server(name: str, server_config: dict) -> dict:
    """Connect to an MCP server and dump its tool definitions."""
    command = server_config.get("command")
    args = server_config.get("args", [])
    env_vars = server_config.get("env", {})

    # Merge environment
    env = {**os.environ, **env_vars}

    params = StdioServerParameters(command=command, args=args, env=env)

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = []
                for tool in result.tools:
                    tool_dict = {
                        "name": tool.name,
                        "description": tool.description or "",
                    }
                    if tool.inputSchema:
                        tool_dict["inputSchema"] = tool.inputSchema
                    tools.append(tool_dict)
                return {"server": name, "tools": tools}
    except Exception as e:
        return {"server": name, "error": str(e), "tools": []}


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Dump MCP tool definitions")
    parser.add_argument("--config", type=str, help="Path to Claude Desktop config")
    parser.add_argument("--server", type=str, help="Only dump a specific server")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per server (seconds)")
    args = parser.parse_args()

    # Find config
    if args.config:
        config_path = Path(args.config)
    else:
        config_path = find_config()

    if not config_path or not config_path.exists():
        print("Error: Claude Desktop config not found.", file=sys.stderr)
        print("Searched:", file=sys.stderr)
        print("  macOS: ~/Library/Application Support/Claude/claude_desktop_config.json", file=sys.stderr)
        print("  Linux: ~/.config/claude/claude_desktop_config.json", file=sys.stderr)
        print("  Or specify: --config /path/to/config.json", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    servers = config.get("mcpServers", {})
    if not servers:
        print("Error: no MCP servers found in config", file=sys.stderr)
        sys.exit(1)

    if args.server:
        if args.server not in servers:
            print(f"Error: server '{args.server}' not found. Available: {', '.join(servers.keys())}", file=sys.stderr)
            sys.exit(1)
        servers = {args.server: servers[args.server]}

    # Dump each server
    all_tools = []
    for name, server_config in servers.items():
        print(f"Connecting to {name}...", file=sys.stderr)
        try:
            result = await asyncio.wait_for(
                dump_server(name, server_config),
                timeout=args.timeout,
            )
            if result.get("error"):
                print(f"  Error: {result['error']}", file=sys.stderr)
            else:
                print(f"  Found {len(result['tools'])} tools", file=sys.stderr)
                # Tag each tool with its server source
                for tool in result["tools"]:
                    tool["_source"] = name
                all_tools.extend(result["tools"])
        except asyncio.TimeoutError:
            print(f"  Timeout after {args.timeout}s", file=sys.stderr)

    # Output combined tool list (pipe-friendly)
    output = {"tools": all_tools}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
