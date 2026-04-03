"""Kura CLI — Tool intelligence for AI agents."""

import asyncio
import json
import sys
from pathlib import Path

import click

from kura import __version__
from kura.models import ScanReport


@click.group()
@click.version_option(__version__, prog_name="kura")
def main():
    """🔍 Kura — Tool intelligence for AI agents.

    Analyze, optimize, and harmonize MCP tool descriptions and OpenClaw skills.
    """


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--format", "output_format", type=click.Choice(["terminal", "json"]), default="terminal")
@click.option("--threshold", type=float, default=0.85, help="Similarity threshold for conflict detection.")
@click.option("--min-quality", type=int, default=0, help="Only show tools below this quality score.")
@click.option("--suggest", is_flag=True, help="Use LLM to generate rewrite suggestions.")
@click.option("--model", type=click.Choice(["anthropic", "openai"]), default="anthropic", help="LLM provider for suggestions.")
def scan(path: str, output_format: str, threshold: float, min_quality: int, suggest: bool, model: str):
    """Scan MCP tools or OpenClaw skills for quality issues.

    PATH can be an MCP config JSON file, a tools list JSON, or an OpenClaw skills directory.
    """
    target = Path(path)

    # Parse tools from input
    from kura.parsers import parse_path
    tools = parse_path(target)

    if not tools:
        click.echo("No tools found. Check your input path.", err=True)
        sys.exit(1)

    # Run quality analysis
    from kura.analyzers.quality import score_tools
    quality_results = score_tools(tools)

    # Run token analysis + boilerplate detection
    from kura.analyzers.tokens import detect_boilerplate, estimate_tokens
    token_results = estimate_tokens(tools)
    boilerplate = detect_boilerplate(tools)

    # Run similarity analysis (requires optional dependency)
    similarities = None  # None = skipped
    intra_similarities = None
    try:
        from kura.analyzers.similarity import find_conflicts
        if output_format == "terminal":
            from rich.console import Console
            with Console(stderr=True).status(
                "Running similarity analysis...",
            ):
                similarities = find_conflicts(
                    tools, threshold=threshold,
                    scope="cross_server",
                )
                intra_threshold = max(0.75, threshold - 0.1)
                intra_similarities = find_conflicts(
                    tools, threshold=intra_threshold,
                    scope="intra_server",
                )
        else:
            similarities = find_conflicts(
                tools, threshold=threshold,
                scope="cross_server",
            )
            intra_threshold = max(0.75, threshold - 0.1)
            intra_similarities = find_conflicts(
                tools, threshold=intra_threshold,
                scope="intra_server",
            )
    except ImportError:
        if output_format == "terminal":
            click.echo(
                "Note: similarity analysis skipped "
                "(missing dependency).\n"
                "Install with: pip install kura-mcp[analysis]",
                err=True,
            )

    # Build report
    total_tokens = sum(t.token_count for t in token_results)
    boilerplate_savings = sum(
        b.wasted_tokens for b in boilerplate
    )
    estimated = max(
        total_tokens - boilerplate_savings,
        int(total_tokens * 0.6),
    )
    report = ScanReport(
        tools=tools,
        similarities=similarities,
        quality_results=quality_results,
        token_results=token_results,
        total_tokens=total_tokens,
        estimated_optimized_tokens=estimated,
        boilerplate=boilerplate,
        intra_similarities=intra_similarities,
    )

    # Output
    if output_format == "json":
        from kura.reporters.json_out import report_json
        click.echo(report_json(report))
    else:
        from kura.reporters.terminal import report_terminal
        report_terminal(report, min_quality=min_quality)


@main.command()
@click.option(
    "--config", "config_path", type=click.Path(exists=True),
    help="Path to MCP config file.",
)
@click.option(
    "--server", "-s", multiple=True,
    help="Server(s) to dump. Can be repeated. Default: all.",
)
@click.option(
    "--interactive", "-i", is_flag=True,
    help="Prompt before connecting to each server.",
)
@click.option(
    "--timeout", type=int, default=30,
    help="Timeout per server in seconds.",
)
@click.option(
    "--output", "-o", type=click.Path(), default=None,
    help="Write output to file instead of stdout.",
)
@click.option(
    "--list", "list_servers", is_flag=True,
    help="List available servers and exit.",
)
def dump(
    config_path: str | None,
    server: tuple[str, ...],
    interactive: bool,
    timeout: int,
    output: str | None,
    list_servers: bool,
):
    """Dump tool definitions from running MCP servers.

    Auto-detects configs from Claude Desktop and Cursor, connects to each
    server, and outputs a combined tools JSON compatible with kura scan.

    \b
    Examples:
        kura dump                          # auto-detect, dump all
        kura dump --list                   # show available servers
        kura dump -s github -s slack       # dump specific servers
        kura dump -i                       # ask before each server
        kura dump -o tools.json            # save to file
    """
    try:
        from kura.dump import (
            _detect_transport,
            dump_tools,
            find_configs,
            load_servers,
        )
    except ImportError:
        click.echo(
            "Error: install the MCP SDK first: "
            "pip install kura-mcp[dump]", err=True,
        )
        sys.exit(1)

    if config_path:
        configs = [("custom", Path(config_path))]
    else:
        configs = find_configs()

    if not configs:
        click.echo("No MCP configs found. Searched:", err=True)
        click.echo("  Claude Desktop:", err=True)
        click.echo(
            "    macOS:   ~/Library/Application Support/Claude/"
            "claude_desktop_config.json", err=True,
        )
        click.echo(
            "    Linux:   ~/.config/claude/"
            "claude_desktop_config.json", err=True,
        )
        click.echo(
            "    Windows: %APPDATA%/Claude/"
            "claude_desktop_config.json", err=True,
        )
        click.echo("  Cursor:", err=True)
        click.echo("    ~/.cursor/mcp.json", err=True)
        click.echo(
            "Use --config to specify a path.", err=True,
        )
        sys.exit(1)

    for app_name, path in configs:
        click.echo(
            f"Found {app_name} config: {path}", err=True,
        )

    # --list: show servers and exit
    if list_servers:
        for _app, path in configs:
            for name, cfg in load_servers(path).items():
                transport = _detect_transport(cfg)
                url = cfg.get("url", cfg.get("command", ""))
                click.echo(f"  {name}  ({transport})  {url}")
        sys.exit(0)

    # Build skip callback for --interactive
    should_skip = None
    if interactive:
        def should_skip(name: str, transport: str) -> bool:
            return not click.confirm(
                f"  Connect to {name} ({transport})?",
                default=True, err=True,
            )

    result = asyncio.run(dump_tools(
        configs,
        server_filter=set(server) if server else None,
        timeout=timeout,
        on_progress=lambda msg: click.echo(msg, err=True),
        should_skip=should_skip,
    ))

    tool_count = len(result["tools"])
    error_count = len(result.get("errors", []))

    if tool_count == 0 and error_count > 0:
        click.echo("All servers failed to connect.", err=True)
        sys.exit(1)

    json_output = json.dumps(result, indent=2)

    if output:
        Path(output).write_text(json_output)
        click.echo(f"Wrote {tool_count} tools to {output}", err=True)
    else:
        click.echo(json_output)

    if error_count:
        click.echo(f"\n{error_count} server(s) had errors (see above).", err=True)


@main.group()
def auth():
    """Manage OAuth authentication for MCP servers."""


@auth.command("status")
def auth_status():
    """Show stored OAuth tokens for MCP servers."""
    from kura.auth import get_stored_servers, get_token_status

    servers = get_stored_servers()
    if not servers:
        click.echo("No OAuth tokens stored.")
        click.echo(
            "Tokens are saved automatically when "
            "kura dump connects to an OAuth server."
        )
        return

    from rich.console import Console
    from rich.table import Table

    table = Table(title="OAuth Tokens (~/.kura/oauth/)")
    table.add_column("Server", style="bold")
    table.add_column("Tokens")
    table.add_column("Client ID")

    for name, path in servers:
        info = get_token_status(path)
        token_status = (
            "[green]stored[/green]" if info["has_tokens"]
            else "[dim]none[/dim]"
        )
        client_id = info.get("client_id") or ""
        if client_id and len(client_id) > 20:
            client_id = client_id[:20] + "..."
        table.add_row(name, token_status, client_id)

    Console(stderr=True).print(table)


@auth.command("logout")
@click.argument("server")
@click.option(
    "--full", is_flag=True,
    help="Also remove client registration (forces re-register).",
)
def auth_logout(server: str, full: bool):
    """Remove stored OAuth tokens for SERVER.

    Use --full to also remove the client registration,
    which forces a new dynamic client registration on next login.
    """
    from kura.auth import FileTokenStorage

    storage = FileTokenStorage(server)
    if not storage.path.exists():
        click.echo(f"No stored data for '{server}'.")
        sys.exit(1)

    if full:
        storage.clear_all()
        click.echo(
            f"Removed all OAuth data for '{server}' "
            f"(tokens + client registration)."
        )
    else:
        storage.clear_tokens()
        click.echo(
            f"Removed tokens for '{server}'. "
            f"Client registration preserved."
        )


@auth.command("login")
@click.argument("server")
@click.option(
    "--url", required=True,
    help="MCP server URL to authenticate with.",
)
def auth_login(server: str, url: str):
    """Pre-authenticate with an MCP server.

    Runs the OAuth flow and stores tokens for later use
    with kura dump.
    """
    try:
        from kura.auth import build_oauth_auth
    except ImportError:
        click.echo(
            "Error: pip install kura-mcp[dump]", err=True,
        )
        sys.exit(1)

    import httpx

    async def _login():
        def progress(msg):
            click.echo(msg, err=True)
        auth_provider, cleanup = await build_oauth_auth(
            server, url, on_progress=progress,
        )
        try:
            # Make a request to trigger the OAuth flow
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(30, read=300),
                follow_redirects=True,
                auth=auth_provider,
            )
            async with client:
                # A simple GET to the server URL triggers auth
                await client.get(url)
            click.echo(
                f"Authenticated with '{server}'. "
                f"Tokens stored for future use."
            )
        finally:
            await cleanup()

    asyncio.run(_login())


if __name__ == "__main__":
    main()
