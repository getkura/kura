"""Tests for quality scoring rules."""

from kura.analyzers.quality import score_tools, _score_tool
from kura.models import ParamDescriptor, ToolDescriptor


def _make_tool(
    name: str = "test_tool",
    description: str = "",
    params: list[ParamDescriptor] | None = None,
) -> ToolDescriptor:
    return ToolDescriptor(
        name=name,
        source="test",
        source_type="mcp",
        description=description,
        parameters=params or [],
    )


class TestQualityScoring:
    def test_no_description_scores_zero(self):
        tool = _make_tool(description="")
        result = _score_tool(tool)
        assert result.score == 0
        assert any(i.code == "NO_DESCRIPTION" for i in result.issues)

    def test_excellent_description(self):
        tool = _make_tool(
            description="Create a new issue in a GitHub repository with title, body, labels, and assignees.",
            params=[
                ParamDescriptor(name="owner", description="Repository owner", type="string", required=True),
                ParamDescriptor(name="repo", description="Repository name", type="string", required=True),
                ParamDescriptor(name="title", description="Issue title", type="string", required=True),
            ],
        )
        result = _score_tool(tool)
        assert result.score >= 80

    def test_vague_description_penalized(self):
        tool = _make_tool(description="Handle various data processing tasks.")
        result = _score_tool(tool)
        assert any(i.code == "VAGUE_DESCRIPTION" for i in result.issues)

    def test_short_description_penalized(self):
        tool = _make_tool(description="Search files.")
        result = _score_tool(tool)
        assert any(i.code == "TOO_SHORT" for i in result.issues)

    def test_long_description_penalized(self):
        long_desc = "This particular tool does something rather specific. " * 50  # ~350 words
        tool = _make_tool(description=long_desc)
        result = _score_tool(tool)
        assert any(i.code == "TOO_LONG" for i in result.issues)

    def test_no_action_verb_penalized(self):
        tool = _make_tool(description="The user can use this tool to look up information about things.")
        result = _score_tool(tool)
        assert any(i.code == "NO_ACTION_VERB" for i in result.issues)

    def test_action_verb_detected(self):
        tool = _make_tool(description="Search for files matching a pattern in the repository.")
        result = _score_tool(tool)
        assert not any(i.code == "NO_ACTION_VERB" for i in result.issues)

    def test_missing_param_descriptions(self):
        tool = _make_tool(
            description="Send a message to a Slack channel.",
            params=[
                ParamDescriptor(name="channel", description=None, type="string"),
                ParamDescriptor(name="text", description="Message content", type="string"),
            ],
        )
        result = _score_tool(tool)
        assert any(i.code == "MISSING_PARAM_DESC" for i in result.issues)

    def test_no_required_marking(self):
        tool = _make_tool(
            description="Get a user by their unique identifier from the database.",
            params=[
                ParamDescriptor(name="user_id", description="User ID", type="string", required=False),
            ],
        )
        result = _score_tool(tool)
        assert any(i.code == "NO_REQUIRED_MARKING" for i in result.issues)

    def test_score_tools_batch(self):
        tools = [
            _make_tool(name="good", description="Create a new GitHub issue in a repository."),
            _make_tool(name="bad", description=""),
        ]
        results = score_tools(tools)
        assert len(results) == 2
        assert results[0].score > results[1].score

    def test_score_capped_at_100(self):
        tool = _make_tool(
            description="Create a new issue in a GitHub repository with title, body, and labels.",
            params=[
                ParamDescriptor(
                    name="title",
                    description="Issue title, e.g. 'Fix login bug'",
                    type="string",
                    required=True,
                ),
            ],
        )
        result = _score_tool(tool)
        assert result.score <= 100
