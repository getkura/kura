"""Tests for similarity detection and token estimation."""

import pytest

from kura.models import ParamDescriptor, ToolDescriptor
from kura.analyzers.tokens import estimate_tokens


def _make_tool(name: str, description: str, source: str = "test") -> ToolDescriptor:
    return ToolDescriptor(
        name=name,
        source=source,
        source_type="mcp",
        description=description,
    )


class TestTokenEstimation:
    def test_basic_estimation(self):
        tools = [_make_tool("search", "Search for files.")]
        results = estimate_tokens(tools)
        assert len(results) == 1
        assert results[0].token_count > 0

    def test_longer_description_more_tokens(self):
        short = _make_tool("a", "Search files.")
        long = _make_tool("b", "Search for files in the filesystem using glob patterns, "
                          "regex matching, and content-based search with configurable depth.")
        results = estimate_tokens([short, long])
        assert results[1].token_count > results[0].token_count

    def test_outlier_detection(self):
        tools = [
            _make_tool("small1", "Do thing A."),
            _make_tool("small2", "Do thing B."),
            _make_tool("small3", "Do thing C."),
            _make_tool("huge", "This is a very long description. " * 50),
        ]
        results = estimate_tokens(tools)
        outliers = [r for r in results if r.is_outlier]
        assert len(outliers) >= 1
        assert outliers[0].tool.name == "huge"

    def test_params_add_tokens(self):
        no_params = _make_tool("a", "Search files.")
        with_params = ToolDescriptor(
            name="b",
            source="test",
            source_type="mcp",
            description="Search files.",
            parameters=[
                ParamDescriptor(name="query", description="Search query string", type="string", required=True),
                ParamDescriptor(name="path", description="Directory to search in", type="string", required=False),
            ],
        )
        r1 = estimate_tokens([no_params])
        r2 = estimate_tokens([with_params])
        assert r2[0].token_count > r1[0].token_count

    def test_empty_list(self):
        results = estimate_tokens([])
        assert results == []


class TestSimilarity:
    """Tests for similarity detector.

    These tests are skipped if sentence-transformers is not installed.
    Run with: pip install kura-mcp[analysis] && pytest
    """

    @pytest.fixture(autouse=True)
    def skip_without_analysis(self):
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            pytest.skip("sentence-transformers not installed")

    def test_similar_tools_detected(self):
        from kura.analyzers.similarity import find_conflicts

        tools = [
            _make_tool("create_issue", "Create a new issue with title and description.", source="github"),
            _make_tool("create_ticket", "Create a new ticket with title and description.", source="jira"),
        ]
        conflicts = find_conflicts(tools, threshold=0.65)
        assert len(conflicts) >= 1
        assert conflicts[0].score > 0.65

    def test_different_tools_not_flagged(self):
        from kura.analyzers.similarity import find_conflicts

        tools = [
            _make_tool("search_web", "Search the web for information using keywords."),
            _make_tool("delete_file", "Delete a file from the filesystem permanently."),
        ]
        conflicts = find_conflicts(tools, threshold=0.85)
        assert len(conflicts) == 0

    def test_single_tool_no_conflicts(self):
        from kura.analyzers.similarity import find_conflicts

        tools = [_make_tool("only_one", "The only tool.")]
        conflicts = find_conflicts(tools)
        assert len(conflicts) == 0

    def test_threshold_adjustment(self):
        from kura.analyzers.similarity import find_conflicts

        tools = [
            _make_tool("search_files", "Search for files in a directory."),
            _make_tool("find_files", "Find files matching a pattern."),
        ]
        # Low threshold should find more conflicts
        low = find_conflicts(tools, threshold=0.5)
        high = find_conflicts(tools, threshold=0.95)
        assert len(low) >= len(high)
