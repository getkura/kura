"""JSON output for CI/CD integration."""

import json
from datetime import datetime, timezone

from kura import __version__
from kura.models import ScanReport


def _format_similarities(sims):
    if sims is None:
        return None
    return [
        {
            "tool_a": s.tool_a.qualified_name,
            "tool_b": s.tool_b.qualified_name,
            "similarity": round(s.score, 4),
            "explanation": s.explanation,
        }
        for s in sims
    ]


def report_json(report: ScanReport) -> str:
    """Serialize scan report to JSON."""
    data = {
        "meta": {
            "version": __version__,
            "timestamp": datetime.now(
                timezone.utc,
            ).isoformat(),
            "tool_count": len(report.tools),
            "overall_health": report.overall_health,
        },
        "conflicts": {
            "cross_server": _format_similarities(
                report.similarities,
            ),
            "intra_server": _format_similarities(
                report.intra_similarities,
            ),
        },
        "quality": [
            {
                "tool": q.tool.qualified_name,
                "score": q.score,
                "issues": [
                    {
                        "code": i.code,
                        "message": i.message,
                        "suggestion": i.suggestion,
                        "severity": i.severity,
                    }
                    for i in q.issues
                ],
            }
            for q in report.quality_results
        ],
        "tokens": {
            "total": report.total_tokens,
            "estimated_optimized":
                report.estimated_optimized_tokens,
            "per_tool": [
                {
                    "tool": t.tool.qualified_name,
                    "tokens": t.token_count,
                    "outlier": t.is_outlier,
                }
                for t in sorted(
                    report.token_results,
                    key=lambda t: t.token_count,
                    reverse=True,
                )
            ],
            "boilerplate": [
                {
                    "source": b.source,
                    "description": b.description[:100],
                    "count": b.count,
                    "wasted_tokens": b.wasted_tokens,
                }
                for b in report.boilerplate
            ],
        },
    }
    return json.dumps(data, indent=2)
