"""Parse OpenClaw SKILL.md files from directories."""

import re
from pathlib import Path

import yaml

from kura.models import ToolDescriptor


def parse_skills_directory(path: Path) -> list[ToolDescriptor]:
    """Scan a directory tree for SKILL.md files and parse them."""
    tools = []

    # Find all SKILL.md files (case-insensitive)
    skill_files = list(path.rglob("[Ss][Kk][Ii][Ll][Ll].[Mm][Dd]"))

    if not skill_files:
        # Also try looking for any .md files with YAML frontmatter
        skill_files = list(path.rglob("*.md"))

    for skill_path in skill_files:
        tool = _parse_skill_file(skill_path, root=path)
        if tool:
            tools.append(tool)

    return tools


def _parse_skill_file(path: Path, root: Path) -> ToolDescriptor | None:
    """Parse a single SKILL.md file."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    # Extract YAML frontmatter
    frontmatter = {}
    body = content
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if fm_match:
        try:
            frontmatter = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        body = fm_match.group(2)

    # Extract name from frontmatter or directory name
    name = frontmatter.get("name", "")
    if not name:
        # Use parent directory name as skill name
        rel = path.relative_to(root)
        name = rel.parent.name if rel.parent != Path(".") else path.stem

    # Extract description from frontmatter or first paragraph of body
    description = frontmatter.get("description", "")
    if not description:
        description = _extract_first_paragraph(body)

    # Build relative source path
    try:
        source = str(path.relative_to(root).parent)
    except ValueError:
        source = str(path.parent)

    return ToolDescriptor(
        name=name,
        source=source,
        source_type="skill",
        description=description,
        raw_config=frontmatter,
    )


def _extract_first_paragraph(markdown: str) -> str:
    """Extract the first non-empty, non-heading paragraph from markdown."""
    lines = markdown.strip().split("\n")
    paragraph_lines = []

    for line in lines:
        stripped = line.strip()
        # Skip headings and empty lines before first paragraph
        if not paragraph_lines:
            if not stripped or stripped.startswith("#"):
                continue
        # End paragraph at empty line or heading
        if paragraph_lines and (not stripped or stripped.startswith("#")):
            break
        paragraph_lines.append(stripped)

    return " ".join(paragraph_lines)[:500]  # Cap at 500 chars
