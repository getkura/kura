"""Token count estimation for tool descriptions."""

import json
import statistics
from collections import defaultdict

from kura.models import BoilerplateResult, TokenResult, ToolDescriptor


def _get_token_counter():
    """Get a token counting function. Uses tiktoken if available, falls back to word-based estimate."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return lambda text: len(enc.encode(text))
    except Exception:
        # Fallback: ~1.3 tokens per word is a reasonable approximation for English
        return lambda text: int(len(text.split()) * 1.3)


def estimate_tokens(tools: list[ToolDescriptor]) -> list[TokenResult]:
    """Estimate token count for each tool's description + schema."""
    count_tokens = _get_token_counter()
    results = []

    for tool in tools:
        text = _tool_to_text(tool)
        count = count_tokens(text)
        results.append(TokenResult(tool=tool, token_count=count))

    # Mark outliers (>2x median)
    if results:
        counts = [r.token_count for r in results]
        median = statistics.median(counts)
        for r in results:
            r.is_outlier = r.token_count > median * 2

    return results


def _tool_to_text(tool: ToolDescriptor) -> str:
    """Convert a tool to its approximate text representation as seen by the model.

    This mimics how tool definitions are serialized in the context window.
    """
    parts = [f"Tool: {tool.name}", f"Description: {tool.description}"]

    if tool.parameters:
        schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        for p in tool.parameters:
            prop: dict = {}
            if p.type:
                prop["type"] = p.type
            if p.description:
                prop["description"] = p.description
            schema["properties"][p.name] = prop
            if p.required:
                schema["required"].append(p.name)

        parts.append(f"Parameters: {json.dumps(schema)}")

    return "\n".join(parts)


def detect_boilerplate(
    tools: list[ToolDescriptor],
    min_count: int = 3,
) -> list[BoilerplateResult]:
    """Detect repeated parameter descriptions across tools.

    Finds identical parameter descriptions used 3+ times
    within the same server and estimates wasted tokens.
    """
    count_tokens = _get_token_counter()

    # Group: (source, description_text) -> list of tool names
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for tool in tools:
        for param in tool.parameters:
            if not param.description:
                continue
            key = (tool.source, param.description.strip())
            groups[key].append(tool.qualified_name)

    results = []
    seen_descriptions: set[tuple[str, str]] = set()
    for (source, desc_text), tool_names in groups.items():
        if len(tool_names) < min_count:
            continue
        if (source, desc_text) in seen_descriptions:
            continue
        seen_descriptions.add((source, desc_text))

        tokens_per = count_tokens(desc_text)
        wasted = tokens_per * (len(tool_names) - 1)
        results.append(BoilerplateResult(
            source=source,
            description=desc_text,
            tool_names=tool_names,
            count=len(tool_names),
            wasted_tokens=wasted,
        ))

    results.sort(key=lambda r: r.wasted_tokens, reverse=True)
    return results
