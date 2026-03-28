# 🔍 Kura

**Tool intelligence for AI agents.** Analyze, optimize, and harmonize MCP tool descriptions and OpenClaw skills.

Your agents connect to dozens of MCP tools and skills. Their descriptions are inconsistent, conflicting, and unoptimized. The result: wrong tool selection, wasted tokens, unreliable agent behavior.

Kura fixes this.

```bash
pip install kura-mcp
kura scan path/to/mcp-config.json
```

## What it does

**Detects conflicts** — finds tools with overlapping descriptions that confuse your agent's tool selection.

**Scores quality** — rates every tool description 0-100 and tells you exactly what to fix.

**Estimates token waste** — shows how much of your token budget goes to tool descriptions and where to cut.

**Suggests improvements** — optionally uses an LLM to rewrite vague descriptions into precise ones.

## Example

```
$ kura scan ~/.config/claude/claude_desktop_config.json

  🔍 Kura — Tool Quality Report

  Scanned: 47 tools across 8 MCP servers
  Overall catalog health: 64/100

  ── HIGH CONFLICTS ──────────────────────────────────

  ⚠ github/create_issue ↔ jira/create_ticket  (0.92)
    Both describe creating issues/tickets with title and description.

  ⚠ filesystem/search ↔ browser/find  (0.87)
    Both describe searching/finding with patterns.

  ── QUALITY ISSUES ──────────────────────────────────

  ✗ filesystem/search  (23/100)
    • Description too vague: "Search for files"
    • No parameter descriptions

  ── TOKEN BUDGET ────────────────────────────────────

  Total catalog: 18,400 tokens
  Estimated after optimization: ~7,200 tokens (-61%)
```

## Install

```bash
# Core (quality scoring + token estimation)
pip install kura-mcp

# With semantic similarity detection (pulls sentence-transformers)
pip install kura-mcp[analysis]

# With LLM-powered rewrite suggestions
pip install kura-mcp[suggest]

# Everything
pip install kura-mcp[all]
```

## Usage

```bash
# Scan an MCP config file
kura scan mcp-config.json

# Scan an OpenClaw skills directory
kura scan ~/.openclaw/skills/

# JSON output for CI/CD
kura scan mcp-config.json --format json

# Custom similarity threshold
kura scan mcp-config.json --threshold 0.80

# Generate rewrite suggestions via LLM
kura scan mcp-config.json --suggest --model anthropic
```

## Supported formats

- **Claude Desktop** config (`claude_desktop_config.json`)
- **OpenClaw** skill directories (`SKILL.md` files)
- **Generic MCP** tool list JSON (any `tools/list` output)
- More coming soon

## Why "Kura"?

Kura means "curate" — because tool quality is a curation problem, not a configuration problem. Your agents are only as good as the tools they can find.

## Roadmap

- [x] CLI quality scanner
- [ ] Semantic conflict detection across servers
- [ ] OpenClaw skill directory scanning
- [ ] CI/CD integration (GitHub Action)
- [ ] LLM-powered rewrite suggestions

See [issues](https://github.com/getkura/kura/issues) for what's next.

## License

MIT
