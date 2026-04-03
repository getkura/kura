"""Core data models for Kura."""

from dataclasses import dataclass, field


@dataclass
class ParamDescriptor:
    """A single parameter of a tool."""

    name: str
    description: str | None = None
    type: str | None = None
    required: bool = False
    has_enum: bool = False
    has_default: bool = False


@dataclass
class ToolDescriptor:
    """Normalized representation of an MCP tool or OpenClaw skill."""

    name: str
    source: str  # Server name or skill path
    source_type: str  # "mcp" or "skill"
    description: str = ""
    parameters: list[ParamDescriptor] = field(default_factory=list)
    raw_config: dict = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        """Full name including source, e.g. 'github/create_issue'."""
        return f"{self.source}/{self.name}"


@dataclass
class SimilarityResult:
    """A pair of tools with high semantic similarity."""

    tool_a: ToolDescriptor
    tool_b: ToolDescriptor
    score: float
    explanation: str = ""
    scope: str = "cross_server"  # "cross_server" | "intra_server"


@dataclass
class QualityIssue:
    """A specific quality problem with a tool description."""

    code: str  # e.g. "VAGUE", "NO_PARAMS", "TOO_LONG"
    message: str
    suggestion: str = ""
    severity: str = "warning"  # "error" | "warning" | "info"


@dataclass
class QualityResult:
    """Quality analysis for a single tool."""

    tool: ToolDescriptor
    score: int  # 0-100
    issues: list[QualityIssue] = field(default_factory=list)


@dataclass
class TokenResult:
    """Token usage analysis for a single tool."""

    tool: ToolDescriptor
    token_count: int
    is_outlier: bool = False


@dataclass
class BoilerplateResult:
    """Repeated parameter description across tools in a server."""

    source: str
    description: str
    tool_names: list[str]
    count: int
    wasted_tokens: int


@dataclass
class ScanReport:
    """Complete analysis report from kura scan."""

    tools: list[ToolDescriptor]
    similarities: list[SimilarityResult] | None  # None = skipped
    quality_results: list[QualityResult]
    token_results: list[TokenResult]
    total_tokens: int = 0
    estimated_optimized_tokens: int = 0
    boilerplate: list[BoilerplateResult] = field(
        default_factory=list,
    )
    intra_similarities: list[SimilarityResult] | None = None

    @property
    def overall_health(self) -> int:
        """Overall catalog health score 0-100."""
        if not self.quality_results:
            return 0
        return round(
            sum(q.score for q in self.quality_results)
            / len(self.quality_results)
        )

    @property
    def high_conflicts(self) -> list[SimilarityResult]:
        """Similarity pairs above 0.85 threshold."""
        if self.similarities is None:
            return []
        return [
            s for s in self.similarities if s.score >= 0.85
        ]
