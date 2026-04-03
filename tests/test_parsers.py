"""Tests for MCP and skill parsers."""

import json
import tempfile
from pathlib import Path

import pytest

from kura.parsers.mcp import parse_mcp_file
from kura.parsers.skills import parse_skills_directory


class TestMcpParser:
    def test_parse_tool_list(self, tmp_path):
        data = {
            "tools": [
                {
                    "name": "get_user",
                    "description": "Get a user by ID.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "string",
                                "description": "The user's unique identifier",
                            }
                        },
                        "required": ["user_id"],
                    },
                }
            ]
        }
        path = tmp_path / "tools.json"
        path.write_text(json.dumps(data))

        tools = parse_mcp_file(path)
        assert len(tools) == 1
        assert tools[0].name == "get_user"
        assert tools[0].description == "Get a user by ID."
        assert tools[0].source_type == "mcp"
        assert len(tools[0].parameters) == 1
        assert tools[0].parameters[0].name == "user_id"
        assert tools[0].parameters[0].required is True

    def test_parse_bare_list(self, tmp_path):
        data = [
            {"name": "tool_a", "description": "Does A."},
            {"name": "tool_b", "description": "Does B."},
        ]
        path = tmp_path / "bare.json"
        path.write_text(json.dumps(data))

        tools = parse_mcp_file(path)
        assert len(tools) == 2
        assert tools[0].name == "tool_a"
        assert tools[1].name == "tool_b"

    def test_parse_claude_desktop_config_no_tools(self, tmp_path):
        data = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                },
                "slack": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-slack"],
                },
            }
        }
        path = tmp_path / "claude_desktop_config.json"
        path.write_text(json.dumps(data))

        tools = parse_mcp_file(path)
        # Should create placeholder entries for each server
        assert len(tools) == 2
        assert tools[0].source == "github"
        assert tools[1].source == "slack"

    def test_parse_claude_desktop_config_with_tools(self, tmp_path):
        data = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": [],
                    "tools": [
                        {"name": "create_issue", "description": "Create an issue."},
                        {"name": "list_repos", "description": "List repos."},
                    ],
                }
            }
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(data))

        tools = parse_mcp_file(path)
        assert len(tools) == 2
        assert tools[0].source == "github"
        assert tools[0].name == "create_issue"

    def test_parse_empty_tools(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"tools": []}))

        tools = parse_mcp_file(path)
        assert len(tools) == 0

    def test_parse_invalid_format(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"something": "else"}))

        with pytest.raises(ValueError, match="Unrecognized JSON format"):
            parse_mcp_file(path)

    def test_parse_missing_fields(self, tmp_path):
        """Tools with missing optional fields should still parse."""
        data = {"tools": [{"name": "minimal"}]}
        path = tmp_path / "minimal.json"
        path.write_text(json.dumps(data))

        tools = parse_mcp_file(path)
        assert len(tools) == 1
        assert tools[0].name == "minimal"
        assert tools[0].description == ""
        assert tools[0].parameters == []


class TestSkillsParser:
    def test_parse_skill_with_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: web-search\n"
            "description: Search the web using Tavily API.\n"
            "tags: [search, web]\n"
            "---\n"
            "\n"
            "# Web Search Skill\n"
            "\n"
            "This skill provides web search capabilities.\n"
        )

        tools = parse_skills_directory(tmp_path)
        assert len(tools) == 1
        assert tools[0].name == "web-search"
        assert tools[0].description == "Search the web using Tavily API."
        assert tools[0].source_type == "skill"

    def test_parse_skill_no_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# Code Review\n"
            "\n"
            "Analyzes code for bugs and style issues.\n"
            "\n"
            "## Usage\n"
            "Ask the agent to review your code.\n"
        )

        tools = parse_skills_directory(tmp_path)
        assert len(tools) == 1
        assert tools[0].name == "code-review"
        assert "Analyzes code" in tools[0].description

    def test_parse_nested_skills(self, tmp_path):
        (tmp_path / "author1" / "skill-a").mkdir(parents=True)
        (tmp_path / "author1" / "skill-a" / "SKILL.md").write_text(
            "---\nname: skill-a\ndescription: First skill.\n---\n"
        )
        (tmp_path / "author2" / "skill-b").mkdir(parents=True)
        (tmp_path / "author2" / "skill-b" / "SKILL.md").write_text(
            "---\nname: skill-b\ndescription: Second skill.\n---\n"
        )

        tools = parse_skills_directory(tmp_path)
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"skill-a", "skill-b"}

    def test_parse_empty_directory(self, tmp_path):
        tools = parse_skills_directory(tmp_path)
        assert len(tools) == 0
