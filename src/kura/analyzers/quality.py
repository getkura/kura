"""Rule-based tool description quality scoring.

Each rule is a function: (ToolDescriptor) -> tuple[int, list[QualityIssue]]
returning (points_earned, issues_found).
"""

import re

from kura.models import QualityIssue, QualityResult, ToolDescriptor

# --- Constants ---

ACTION_VERBS = {
    "add", "analyze", "append", "approve", "archive", "assign", "attach",
    "authenticate", "authorize", "browse", "calculate", "cancel", "check",
    "close", "compare", "configure", "connect", "convert", "copy", "count",
    "create", "debug", "delete", "deploy", "detach", "disable", "disconnect",
    "display", "download", "enable", "execute", "export", "extract", "fetch",
    "filter", "find", "format", "generate", "get", "group", "hide", "import",
    "insert", "install", "invoke", "link", "list", "log", "lookup", "merge",
    "monitor", "move", "navigate", "notify", "open", "parse", "provision",
    "publish", "query", "read", "reject", "remove", "rename", "render",
    "replace", "resolve", "restore", "review", "revoke", "run", "schedule",
    "search", "select", "send", "set", "show", "sort", "split", "start",
    "stop", "submit", "subscribe", "summarize", "sync", "test", "toggle",
    "transform", "transition", "translate", "trigger", "uninstall", "update",
    "upload", "validate", "write",
}

VAGUE_WORDS = {
    "manage", "handle", "process", "deal with", "work with",
    "do", "perform", "stuff", "things", "various", "general",
    "misc", "utility", "helper", "operate on", "interact with",
}

KNOWN_SERVICES = {
    "aws", "azure", "gcp", "github", "gitlab", "bitbucket",
    "jira", "confluence", "atlassian", "slack", "discord", "teams",
    "postgresql", "postgres", "mysql", "mongodb", "redis", "dynamodb",
    "elasticsearch", "docker", "kubernetes", "k8s",
    "stripe", "twilio", "sendgrid", "datadog", "sentry",
    "salesforce", "hubspot", "zendesk", "linear", "notion",
    "vercel", "netlify", "heroku", "railway", "supabase",
    "openai", "anthropic", "google", "firebase",
    "s3", "lambda", "cloudflare", "terraform",
}

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "and",
    "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more",
    "most", "other", "some", "such", "no", "only", "own", "same",
    "than", "too", "very", "just", "about", "above", "below",
    "between", "up", "down", "out", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "what", "which", "who", "whom",
    "this", "that", "these", "those", "it", "its",
}


# --- Public API ---

def score_tools(
    tools: list[ToolDescriptor],
) -> list[QualityResult]:
    """Score all tools for description quality."""
    return [_score_tool(tool) for tool in tools]


def _score_tool(tool: ToolDescriptor) -> QualityResult:
    """Score a single tool description. Returns 0-100."""
    desc = tool.description.strip()
    if not desc:
        return QualityResult(
            tool=tool, score=0,
            issues=[QualityIssue(
                code="NO_DESCRIPTION",
                message="Tool has no description.",
                suggestion="Add a 1-2 sentence description "
                "starting with an action verb.",
                severity="error",
            )],
        )

    total = 0
    issues: list[QualityIssue] = []
    for rule in _RULES:
        pts, rule_issues = rule(tool)
        total += pts
        issues.extend(rule_issues)

    return QualityResult(
        tool=tool,
        score=min(total, 100),
        issues=issues,
    )


# --- Rule implementations ---

def _rule_description_length(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 2: Description length. Max 15 points."""
    words = tool.description.strip().split()
    wc = len(words)

    if wc < 5:
        return 0, [QualityIssue(
            code="TOO_SHORT",
            message=f"Description is only {wc} words.",
            suggestion="Add what the tool does, what system "
            "it operates on, and what it returns.",
            severity="warning",
        )]
    elif wc <= 8:
        return 8, [QualityIssue(
            code="TOO_SHORT",
            message=f"Description is {wc} words. "
            "Aim for 10-50 for best results.",
            suggestion="Add what system it operates on "
            "and what it returns.",
            severity="info",
        )]
    elif wc <= 15:
        return 12, []
    elif wc <= 50:
        return 15, []
    elif wc <= 100:
        return 10, []
    elif wc <= 200:
        return 7, [QualityIssue(
            code="TOO_LONG",
            message=f"Description is {wc} words. "
            "Consider trimming to under 50.",
            suggestion="Move details to parameter "
            "descriptions.",
            severity="info",
        )]
    else:
        return 3, [QualityIssue(
            code="TOO_LONG",
            message=f"Description is {wc} words. "
            "Much too long for a tool description.",
            suggestion="Keep the top-level description "
            "concise. Move usage details to parameter "
            "descriptions.",
            severity="warning",
        )]


def _rule_action_verb(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 3: Starts with action verb. Max 8 points."""
    words = tool.description.strip().split()
    if not words:
        return 0, []

    # Check the first word, and if it's not a verb,
    # scan the first 5 words (handles "Use this tool to..."
    # and "ALWAYS use this tool..." patterns)
    for word in words[:5]:
        if _is_action_verb(word):
            return 8, []

    return 0, [QualityIssue(
        code="NO_ACTION_VERB",
        message="Description doesn't start with an "
        f"action verb (starts with '{words[0]}').",
        suggestion="Start with a verb like 'Create', "
        "'Search', 'Get', 'List', etc.",
        severity="info",
    )]


def _is_action_verb(word: str) -> bool:
    """Check if a word is an action verb, with simple stemming."""
    w = word.lower().rstrip(",.:;")
    candidates = {w}
    if w.endswith("s") and len(w) > 2:
        candidates.add(w[:-1])
    if w.endswith("es") and len(w) > 3:
        candidates.add(w[:-2])
    if w.endswith("ing") and len(w) > 4:
        candidates.add(w[:-3])
        candidates.add(w[:-3] + "e")
    return bool(candidates & ACTION_VERBS)


def _rule_system_context(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 4: Specifies system/service context. Max 7 points."""
    desc = tool.description
    desc_lower = desc.lower()

    # Check for known service names in description
    for svc in KNOWN_SERVICES:
        if re.search(rf"\b{re.escape(svc)}\b", desc_lower):
            return 7, []

    # Check for capitalized words mid-sentence (proper nouns)
    # Skip the first word (always capitalized)
    words = desc.split()
    for word in words[1:]:
        cleaned = word.strip(",.;:()\"'")
        if (
            cleaned
            and cleaned[0].isupper()
            and not cleaned.isupper()
            and len(cleaned) > 1
        ):
            return 7, []

    # Check tool.source for known service names
    source_lower = tool.source.lower()
    for svc in KNOWN_SERVICES:
        if svc in source_lower:
            return 4, []  # partial credit

    return 0, [QualityIssue(
        code="NO_CONTEXT",
        message="Description doesn't specify which "
        "system or service this tool operates on.",
        suggestion="Add context like 'in GitHub', "
        "'from Jira', 'on Slack', etc.",
        severity="info",
    )]


def _rule_param_descriptions(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 5: Parameters have descriptions. Max 15 points."""
    if not tool.parameters:
        return 10, []  # no params is fine for some tools

    params_with_desc = sum(
        1 for p in tool.parameters if p.description
    )
    total = len(tool.parameters)
    issues = []

    if params_with_desc < total:
        missing = total - params_with_desc
        missing_names = [
            p.name for p in tool.parameters
            if not p.description
        ]
        issues.append(QualityIssue(
            code="MISSING_PARAM_DESC",
            message=f"{missing} of {total} parameters "
            f"lack descriptions: "
            f"{', '.join(missing_names)}",
            suggestion="Add a description to each parameter "
            "explaining expected format and valid values.",
            severity="warning",
        ))

    pts = int(15 * (params_with_desc / total))
    return pts, issues


def _rule_required_params(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 6: Required parameters are marked. Max 5 points."""
    if not tool.parameters:
        return 5, []  # N/A

    has_required = any(p.required for p in tool.parameters)
    # Check if schema explicitly declares required: []
    schema = tool.raw_config.get("inputSchema", {})
    explicit_required = schema.get("required")

    if has_required:
        return 5, []

    # All optional is valid if explicitly declared
    if explicit_required is not None and len(explicit_required) == 0:
        return 5, []

    return 0, [QualityIssue(
        code="NO_REQUIRED_MARKING",
        message="No parameters are marked as required.",
        suggestion="Mark parameters as required/optional "
        "to help agents construct valid calls.",
        severity="info",
    )]


def _rule_no_vague_words(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 7: No vague words. Max 8 points."""
    desc_lower = tool.description.lower()
    found = []
    for word in VAGUE_WORDS:
        if " " in word:
            # Multi-word phrase: simple substring
            if word in desc_lower:
                found.append(word)
        else:
            # Single word: word-boundary match
            if re.search(rf"\b{re.escape(word)}\b", desc_lower):
                found.append(word)

    if not found:
        return 8, []

    return 0, [QualityIssue(
        code="VAGUE_DESCRIPTION",
        message="Description uses vague terms: "
        f"{', '.join(found)}",
        suggestion="Replace generic terms with specific "
        "actions and objects.",
        severity="warning",
    )]


def _rule_schema_richness(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 8: Schema richness (enum, default, examples). Max 7."""
    if not tool.parameters:
        return 3, []  # partial credit for no-param tools

    rich_count = 0
    for p in tool.parameters:
        if p.has_enum or p.has_default:
            rich_count += 1
        elif p.description and re.search(
            r"(e\.g\.|for example|format:|like |such as)",
            p.description, re.IGNORECASE,
        ):
            rich_count += 1

    if rich_count == 0:
        return 0, []

    ratio = rich_count / len(tool.parameters)
    return min(int(ratio * 7) + 1, 7), []


def _rule_no_behavioral_override(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 9: No behavioral override directives. Max 5."""
    desc = tool.description
    pattern = (
        r"\b(ALWAYS|MUST|NEVER)\s+(use|call|prefer)"
        r"|instead\s+of\s+(using|calling)"
        r"|do\s+not\s+use\s+(any\s+other|another)"
    )
    if re.search(pattern, desc, re.IGNORECASE):
        return 0, [QualityIssue(
            code="BEHAVIORAL_OVERRIDE",
            message="Description contains behavioral "
            "directives that try to influence agent "
            "tool selection.",
            suggestion="Describe what the tool does, not "
            "when the agent should use it. Let the "
            "agent decide based on the description.",
            severity="warning",
        )]
    return 5, []


def _rule_description_adds_info(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 10: Description adds info beyond tool name. Max 5."""
    name_tokens = _split_name(tool.name)
    if not name_tokens:
        return 5, []

    desc_words = tool.description.strip().lower().split()
    content_words = [
        w.strip(",.;:()\"'") for w in desc_words
        if w.strip(",.;:()\"'") not in STOP_WORDS
    ]
    content_words = [w for w in content_words if w]

    if not content_words:
        return 0, [QualityIssue(
            code="NAME_RESTATES_DESC",
            message="Description adds no information "
            "beyond the tool name.",
            suggestion="Explain what system it operates on, "
            "what input it expects, and what it returns.",
            severity="warning",
        )]

    # Check if all content words are just name tokens
    overlap = sum(
        1 for w in content_words if w in name_tokens
    )
    if len(content_words) <= 4 and overlap >= len(content_words):
        return 0, [QualityIssue(
            code="NAME_RESTATES_DESC",
            message="Description merely restates the "
            "tool name.",
            suggestion="Add what system it operates on, "
            "what the parameters control, and what is "
            "returned.",
            severity="warning",
        )]

    return 5, []


def _split_name(name: str) -> set[str]:
    """Split a tool name into lowercase tokens.

    Handles both snake_case and camelCase.
    """
    # Split on underscores
    parts = name.split("_")
    tokens = set()
    for part in parts:
        # Split camelCase
        camel = re.findall(
            r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)",
            part,
        )
        if camel:
            tokens.update(w.lower() for w in camel)
        elif part:
            tokens.add(part.lower())
    return tokens


def _rule_no_opaque_objects(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 11: No opaque object parameters. Max 5."""
    schema = tool.raw_config.get("inputSchema", {})
    properties = schema.get("properties", {})
    if not properties:
        return 5, []

    # Build lookup of param descriptions
    param_descs = {
        p.name: p.description for p in tool.parameters
    }

    opaque = []
    for pname, pschema in properties.items():
        if not isinstance(pschema, dict):
            continue
        ptype = pschema.get("type")
        if ptype != "object":
            continue
        has_props = "properties" in pschema
        has_desc = bool(param_descs.get(pname))
        # Open schema with no description
        if not has_props and not has_desc:
            opaque.append(pname)

    if not opaque:
        return 5, []

    return 0, [QualityIssue(
        code="OPAQUE_OBJECT_PARAM",
        message="Parameters with opaque object type "
        f"(no schema or description): "
        f"{', '.join(opaque)}",
        suggestion="Add a description explaining expected "
        "structure, or define properties in the schema.",
        severity="warning",
    )]


def _rule_return_value(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 12: Return value documented. Max 5."""
    desc = tool.description
    if re.search(
        r"\b(returns?|results?\b|outputs?|produces?"
        r"|yields?|responds?\s+with|including)",
        desc, re.IGNORECASE,
    ):
        return 5, []

    return 0, [QualityIssue(
        code="NO_RETURN_VALUE",
        message="Description does not mention what "
        "the tool returns.",
        suggestion="Add what the tool returns, e.g. "
        "'Returns a list of issues' or "
        "'Returns the created page ID'.",
        severity="info",
    )]


def _rule_has_description(
    tool: ToolDescriptor,
) -> tuple[int, list[QualityIssue]]:
    """Rule 1: Has non-trivial description. Max 15 points.

    +5 for any text, +10 more if it adds info beyond the name.
    Combined with rule 10 (name restates), but here we check
    at a basic level.
    """
    desc = tool.description.strip()
    if not desc:
        return 0, []  # handled by early return in _score_tool

    name_tokens = _split_name(tool.name)
    desc_words = [
        w.strip(",.;:()\"'").lower()
        for w in desc.split()
        if w.strip(",.;:()\"'").lower() not in STOP_WORDS
    ]
    desc_words = [w for w in desc_words if w]

    # Any text at all: +5
    # Adds info beyond name: +10 more
    if not desc_words:
        return 5, []

    new_info = sum(
        1 for w in desc_words if w not in name_tokens
    )
    if new_info > 0:
        return 15, []

    return 5, []


# --- Rule registry ---

_RULES = [
    _rule_has_description,       # max 15
    _rule_description_length,    # max 15
    _rule_action_verb,           # max 8
    _rule_system_context,        # max 7
    _rule_param_descriptions,    # max 15
    _rule_required_params,       # max 5
    _rule_no_vague_words,        # max 8
    _rule_schema_richness,       # max 7
    _rule_no_behavioral_override,  # max 5
    _rule_description_adds_info,   # max 5
    _rule_no_opaque_objects,       # max 5
    _rule_return_value,            # max 5
]
# Total: 100
