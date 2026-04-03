"""Connect to MCP servers and dump their tool definitions.

Requires: pip install kura-mcp[dump]
"""

import asyncio
import json
import os
from pathlib import Path


def find_configs() -> list[tuple[str, Path]]:
    """Auto-detect MCP config files from known applications."""
    found = []

    # Claude Desktop
    for p in _claude_desktop_paths():
        if p.exists():
            found.append(("Claude Desktop", p))
            break

    # Cursor
    for p in _cursor_paths():
        if p.exists():
            found.append(("Cursor", p))
            break

    return found


def _claude_desktop_paths() -> list[Path]:
    paths = [
        # macOS
        Path.home() / "Library" / "Application Support" / "Claude"
        / "claude_desktop_config.json",
        # Linux
        Path.home() / ".config" / "claude" / "claude_desktop_config.json",
    ]
    # Windows
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(
            Path(appdata) / "Claude" / "claude_desktop_config.json"
        )
    return paths


def _cursor_paths() -> list[Path]:
    return [
        Path.home() / ".cursor" / "mcp.json",
    ]


def load_servers(config_path: Path) -> dict[str, dict]:
    """Load mcpServers from a config file."""
    with open(config_path) as f:
        data = json.load(f)
    return data.get("mcpServers", {})


def _detect_transport(server_config: dict) -> str:
    """Detect server transport type from config.

    Returns "http", "sse", or "stdio".
    """
    explicit = server_config.get("type", "").lower()
    if explicit in ("http", "streamable-http", "streamable_http"):
        return "http"
    if explicit == "sse":
        return "sse"
    if explicit == "stdio" or server_config.get("command"):
        return "stdio"
    # Has a URL but no explicit type — try streamable HTTP first
    if server_config.get("url"):
        return "http"
    return "stdio"


def _extract_tools(result) -> list[dict]:
    """Convert MCP list_tools result to serializable dicts."""
    tools = []
    for tool in result.tools:
        tool_dict = {
            "name": tool.name,
            "description": tool.description or "",
        }
        if tool.inputSchema:
            tool_dict["inputSchema"] = tool.inputSchema
        tools.append(tool_dict)
    return tools


async def _connect_stdio(name: str, server_config: dict) -> dict:
    """Connect to a local MCP server via stdio."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command = server_config.get("command")
    args = server_config.get("args", [])
    env_vars = server_config.get("env", {})

    env = {**os.environ, **env_vars}
    params = StdioServerParameters(command=command, args=args, env=env)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return {"server": name, "tools": _extract_tools(result)}


async def _connect_http(
    name: str, server_config: dict, on_progress=None,
) -> dict:
    """Connect to a remote MCP server via streamable HTTP."""
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    url = server_config["url"]
    headers = server_config.get("headers", {})

    auth = None
    cleanup = None
    if not headers:
        try:
            from kura.auth import build_oauth_auth
            auth, cleanup = await build_oauth_auth(
                name, url, on_progress=on_progress,
            )
        except Exception:
            pass

    client = httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(30, read=300),
        follow_redirects=True,
        auth=auth,
    )
    try:
        async with client:
            async with streamable_http_client(
                url=url, http_client=client,
            ) as (read, write, _session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return {
                        "server": name,
                        "tools": _extract_tools(result),
                    }
    finally:
        if cleanup:
            await cleanup()


async def _connect_sse(
    name: str, server_config: dict, on_progress=None,
) -> dict:
    """Connect to a remote MCP server via SSE (legacy)."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    url = server_config["url"]
    headers = server_config.get("headers", {})

    sse_kwargs: dict = {"url": url, "headers": headers}
    cleanup = None
    if not headers:
        try:
            from kura.auth import build_oauth_auth
            auth, cleanup = await build_oauth_auth(
                name, url, on_progress=on_progress,
            )
            sse_kwargs["auth"] = auth
        except Exception:
            pass

    try:
        async with sse_client(**sse_kwargs) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return {
                    "server": name,
                    "tools": _extract_tools(result),
                }
    finally:
        if cleanup:
            await cleanup()


async def _connect_and_list(
    name: str, server_config: dict, on_progress=None,
) -> dict:
    """Connect to an MCP server using the appropriate transport."""
    transport = _detect_transport(server_config)
    if transport == "http":
        return await _connect_http(name, server_config, on_progress)
    elif transport == "sse":
        return await _connect_sse(name, server_config, on_progress)
    else:
        return await _connect_stdio(name, server_config)


async def dump_tools(
    configs: list[tuple[str, Path]],
    server_filter: set[str] | None = None,
    timeout: int = 30,
    on_progress: object = None,
    should_skip: object = None,
) -> dict:
    """Dump tools from all configured MCP servers.

    Args:
        configs: List of (app_name, config_path) tuples.
        server_filter: If set, only dump servers whose names are in this set.
        timeout: Per-server connection timeout in seconds.
        on_progress: Callback(msg: str) for status messages.
        should_skip: Callback(name: str, transport: str) -> bool.
            Called before connecting. Return True to skip.

    Returns {"tools": [...]} dict compatible with kura scan.
    """
    all_tools: list[dict] = []
    errors: list[dict] = []

    for app_name, config_path in configs:
        servers = load_servers(config_path)

        if server_filter:
            servers = {
                k: v for k, v in servers.items()
                if k in server_filter
            }

        for name, server_config in servers.items():
            transport = _detect_transport(server_config)

            if should_skip and should_skip(name, transport):
                if on_progress:
                    on_progress(f"  Skipped {name}")
                continue

            if on_progress:
                on_progress(
                    f"Connecting to {name} ({app_name}, "
                    f"{transport})..."
                )
            # Remote servers may need OAuth (browser interaction),
            # so use a longer timeout than local stdio servers.
            effective_timeout = timeout
            if transport in ("http", "sse"):
                effective_timeout = max(timeout, 300)
            try:
                result = await asyncio.wait_for(
                    _connect_and_list(
                        name, server_config, on_progress,
                    ),
                    timeout=effective_timeout,
                )
                if on_progress:
                    on_progress(
                        f"  Found {len(result['tools'])} tools"
                    )
                for tool in result["tools"]:
                    tool["_source"] = name
                all_tools.extend(result["tools"])
            except asyncio.TimeoutError:
                msg = f"Timeout after {effective_timeout}s"
                errors.append({"server": name, "error": msg})
                if on_progress:
                    on_progress(f"  Error: {msg}")
            except Exception as e:
                errors.append({"server": name, "error": str(e)})
                if on_progress:
                    on_progress(f"  Error: {e}")

    output = {"tools": all_tools}
    if errors:
        output["errors"] = errors
    return output
