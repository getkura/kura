"""Embedding-based semantic similarity detection between tools.

Requires optional dependency: pip install kura-mcp[analysis]
"""

from kura.models import SimilarityResult, ToolDescriptor


def find_conflicts(
    tools: list[ToolDescriptor],
    threshold: float = 0.85,
    scope: str = "all",
) -> list[SimilarityResult]:
    """Find semantically similar tool pairs that may confuse agent selection.

    Uses sentence-transformers for local embedding computation (no API key needed).

    Args:
        scope: "all" (every pair), "cross_server" (different sources only),
               "intra_server" (same source only).
    """
    # These imports will fail if sentence-transformers is not installed
    import numpy as np
    from sentence_transformers import SentenceTransformer

    if len(tools) < 2:
        return []

    # Build description texts for embedding
    texts = [_tool_text_for_embedding(t) for t in tools]

    # Compute embeddings
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(
        texts, normalize_embeddings=True, show_progress_bar=False,
    )

    # Pairwise cosine similarity (normalized → dot product = cosine)
    sim_matrix = np.dot(embeddings, embeddings.T)

    # Find pairs above threshold, filtered by scope
    results = []
    for i in range(len(tools)):
        for j in range(i + 1, len(tools)):
            same_source = tools[i].source == tools[j].source
            if scope == "cross_server" and same_source:
                continue
            if scope == "intra_server" and not same_source:
                continue

            score = float(sim_matrix[i, j])
            if score >= threshold:
                results.append(SimilarityResult(
                    tool_a=tools[i],
                    tool_b=tools[j],
                    score=score,
                    explanation=_explain_similarity(
                        tools[i], tools[j], score,
                    ),
                    scope=scope if scope != "all" else (
                        "intra_server" if same_source
                        else "cross_server"
                    ),
                ))

    # Sort by similarity score descending
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def _tool_text_for_embedding(tool: ToolDescriptor) -> str:
    """Create a text representation of a tool optimized for embedding comparison."""
    parts = [tool.name.replace("_", " "), tool.description]
    # Include parameter names for additional context
    if tool.parameters:
        param_names = ", ".join(p.name.replace("_", " ") for p in tool.parameters[:10])
        parts.append(f"Parameters: {param_names}")
    return " | ".join(parts)


def _explain_similarity(tool_a: ToolDescriptor, tool_b: ToolDescriptor, score: float) -> str:
    """Generate a human-readable explanation of why two tools are similar."""
    a_words = set(tool_a.description.lower().split())
    b_words = set(tool_b.description.lower().split())
    stop = {
        "the", "a", "an", "is", "to", "and", "or",
        "for", "in", "on", "with", "of",
    }
    common = a_words & b_words - stop

    if common:
        shared = ", ".join(sorted(common)[:5])
        return f"Both descriptions share key terms: {shared}"
    else:
        return "Descriptions are semantically similar despite different wording."
