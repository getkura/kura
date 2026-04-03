"""Rich terminal output for scan reports."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kura.models import ScanReport

console = Console()

SEVERITY_STYLE = {
    "error": "red",
    "warning": "yellow",
    "info": "dim",
}


def report_terminal(
    report: ScanReport, min_quality: int = 0,
) -> None:
    """Print a formatted scan report to the terminal."""

    # Header
    health = report.overall_health
    health_color = (
        "green" if health >= 70
        else "yellow" if health >= 50
        else "red"
    )
    console.print()
    console.print(Panel.fit(
        f"[bold]Kura — Tool Quality Report[/bold]\n\n"
        f"Scanned: [cyan]{len(report.tools)}[/cyan] tools\n"
        f"Overall catalog health: "
        f"[bold {health_color}]{health}/100"
        f"[/bold {health_color}]",
        border_style="blue",
    ))

    _print_all_tools(report)
    _print_similarity(report)
    _print_quality_issues(report, min_quality)
    _print_token_budget(report)

    console.print()


def _print_all_tools(report: ScanReport) -> None:
    """Show a table of every tool with score and tokens."""
    if not report.quality_results:
        return

    token_map = {
        t.tool.qualified_name: t
        for t in report.token_results
    }

    table = Table(
        title="All Tools",
        show_header=True,
        header_style="bold",
        padding=(0, 1),
    )
    table.add_column("Tool", style="bold", no_wrap=True)
    table.add_column("Quality", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Issues", justify="right")

    rows = sorted(
        report.quality_results,
        key=lambda q: q.score,
    )

    for qr in rows:
        name = qr.tool.qualified_name
        score = qr.score

        if score >= 80:
            score_str = f"[green]{score}[/green]"
        elif score >= 50:
            score_str = f"[yellow]{score}[/yellow]"
        else:
            score_str = f"[red]{score}[/red]"

        tr = token_map.get(name)
        if tr:
            tok_str = f"{tr.token_count:,}"
            if tr.is_outlier:
                tok_str = f"[yellow]{tok_str}[/yellow]"
        else:
            tok_str = "-"

        issue_count = len(qr.issues)
        issue_str = (
            f"[red]{issue_count}[/red]" if issue_count
            else "[green]0[/green]"
        )

        table.add_row(name, score_str, tok_str, issue_str)

    console.print()
    console.print(table)


def _print_similarity(report: ScanReport) -> None:
    """Show similarity analysis results."""

    # Cross-server conflicts
    if report.similarities is not None:
        console.print()
        if report.similarities:
            console.print(
                "[bold red]── CROSS-SERVER CONFLICTS "
                "───────────────────[/bold red]"
            )
            _print_conflict_list(report.similarities)
        else:
            console.print(
                "[bold green]── CROSS-SERVER SIMILARITY "
                "──────────────────[/bold green]"
            )
            console.print()
            console.print(
                "  [green]No cross-server conflicts "
                "detected.[/green]"
            )

    # Intra-server overlaps
    if report.intra_similarities is not None:
        console.print()
        if report.intra_similarities:
            console.print(
                "[bold yellow]── INTRA-SERVER OVERLAPS "
                "────────────────────[/bold yellow]"
            )
            _print_conflict_list(report.intra_similarities)
        else:
            console.print(
                "[bold green]── INTRA-SERVER SIMILARITY "
                "──────────────────[/bold green]"
            )
            console.print()
            console.print(
                "  [green]No intra-server overlaps "
                "detected.[/green]"
            )


def _print_conflict_list(similarities) -> None:
    for sim in similarities:
        console.print()
        console.print(
            f"  [yellow]![/yellow] "
            f"[bold]{sim.tool_a.qualified_name}[/bold]"
            f" <-> "
            f"[bold]{sim.tool_b.qualified_name}[/bold]  "
            f"[dim](similarity: {sim.score:.2f})[/dim]"
        )
        if sim.explanation:
            console.print(f"    {sim.explanation}")


def _print_quality_issues(
    report: ScanReport, min_quality: int,
) -> None:
    """Show detailed quality issues, grouped by severity."""
    cutoff = min_quality if min_quality else 100
    with_issues = [
        q for q in report.quality_results
        if q.issues and q.score <= cutoff
    ]
    if not with_issues:
        return

    with_issues.sort(key=lambda q: q.score)

    console.print()
    console.print(
        "[bold yellow]── QUALITY ISSUES "
        "──────────────────────────────[/bold yellow]"
    )
    for qr in with_issues:
        console.print()
        color = "red" if qr.score < 40 else "yellow"
        console.print(
            f"  [{color}]x[/{color}] "
            f"[bold]{qr.tool.qualified_name}[/bold]  "
            f"[dim](quality: {qr.score}/100)[/dim]"
        )
        for issue in qr.issues:
            style = SEVERITY_STYLE.get(
                issue.severity, "yellow",
            )
            console.print(
                f"    [{style}]-[/{style}] "
                f"{issue.message}"
            )
            if issue.suggestion:
                console.print(
                    f"      [dim]> {issue.suggestion}[/dim]"
                )


def _print_token_budget(report: ScanReport) -> None:
    """Show token usage summary with boilerplate analysis."""
    if not report.token_results:
        return

    console.print()
    console.print(
        "[bold blue]── TOKEN BUDGET "
        "────────────────────────────────[/bold blue]"
    )
    console.print()
    console.print(
        f"  Total catalog: "
        f"[bold]{report.total_tokens:,}[/bold] tokens"
    )

    outliers = [
        t for t in report.token_results if t.is_outlier
    ]
    if outliers:
        outliers.sort(
            key=lambda t: t.token_count, reverse=True,
        )
        for t in outliers[:3]:
            console.print(
                f"  [yellow]![/yellow] "
                f"{t.tool.qualified_name}: "
                f"[bold]{t.token_count:,}[/bold] tokens "
                f"[dim](outlier)[/dim]"
            )

    # Boilerplate
    if report.boilerplate:
        console.print()
        console.print("  [bold]Boilerplate parameters:[/bold]")
        total_wasted = 0
        for bp in report.boilerplate[:5]:
            short_desc = bp.description[:60]
            if len(bp.description) > 60:
                short_desc += "..."
            console.print(
                f"  [yellow]![/yellow] "
                f"\"{short_desc}\" "
                f"[dim]repeated {bp.count}x in "
                f"{bp.source} "
                f"(~{bp.wasted_tokens:,} wasted tokens)"
                f"[/dim]"
            )
            total_wasted += bp.wasted_tokens
        if total_wasted:
            console.print(
                f"  Total boilerplate waste: "
                f"[yellow]{total_wasted:,}[/yellow] tokens"
            )

    if report.estimated_optimized_tokens < report.total_tokens:
        savings = (
            report.total_tokens
            - report.estimated_optimized_tokens
        )
        pct = round(savings / report.total_tokens * 100)
        console.print(
            f"  Estimated after optimization: "
            f"[green]~{report.estimated_optimized_tokens:,}"
            f"[/green] tokens [dim](-{pct}%)[/dim]"
        )
