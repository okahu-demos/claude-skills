---
name: ok:local-trace
description: View local traces from .monocle/ folder (natural language supported)
argument-hint: [query]
allowed-tools:
  - Read
  - Bash
  - AskUserQuestion
  - mcp__okahu-mcp-stage__get_traces
  - mcp__okahu-mcp-stage__get_trace_spans
---

# ok:local-trace [query]

View local traces from `.monocle/` folder. Accepts natural language queries.

## When to Use This vs Okahu MCP

| This skill (`/ok-local-trace`) | Okahu MCP |
|-------------------------------|-----------|
| Local `.monocle/` folder traces | Remote Okahu cloud traces |
| From `/ok-instrument` runs | From deployed apps with Okahu telemetry |
| Local dev/debugging | Production monitoring |

## Natural Language Query Examples

Users can say things like:
- "show me recent traces" → `--last 5m`
- "what errors happened?" → `--errors-only`
- "show the slowest trace" → read files, sort by duration
- "traces from the last hour" → `--last 60m`
- "find trace abc123" → `--trace-id abc123`
- "show everything" → `--all`
- "flat view without tree" → `--flat`

**Interpret the user's intent and map to appropriate script options.**

## Steps

1. Check if `.monocle/` folder exists in current directory, or in the app directory from `.okahu/SESSION.md`
2. If **NO local traces found**:
   - Tell user: "No local traces found in .monocle/"
   - **Suggest Okahu MCP**: "Would you like to check Okahu Cloud for remote traces instead?"
   - If user agrees, use `mcp__okahu-mcp-stage__get_traces` tool
3. If local traces exist:
   - Interpret the user's natural language query
   - **For interactive viewing**: Suggest the user run the interactive viewer directly:
     `! python .claude/scripts/trace_viewer.py [options]`
     (This launches a curses-based TUI with arrow-key navigation — must run via `!` prefix)
   - **For inline display**: Map to `trace_viewer.py --print` or `trace_minify.py` options
   - Run: `python .claude/scripts/trace_viewer.py --print [options]` for inline output
   - Run: `python .claude/scripts/trace_minify.py [options]` for compact debug output
4. Optionally update `.okahu/SESSION.md` if notable findings

## Interactive Viewer (trace_viewer.py)

A curses-based TUI for exploring traces with keyboard navigation.
**Must be launched by the user** with `!` prefix (needs a real TTY):

```bash
! python .claude/scripts/trace_viewer.py                     # Latest traces
! python .claude/scripts/trace_viewer.py --last 5m           # Recent traces
! python .claude/scripts/trace_viewer.py --trace-id abc123   # Specific trace
```

Keys:
- **↑/↓** or **j/k** — Navigate between spans
- **←/→** or **h/l** — Collapse/expand child spans
- **Enter/Space** — Toggle detail panel
- **t** — Cycle through loaded traces
- **q/Esc** — Quit

Features:
- Color-coded Gantt waterfall bars by span type (workflow, turn, inference, tool, agent, MCP)
- Collapsible span tree with depth indentation
- Detail panel with attributes, events, and token usage
- Multi-trace support with `t` to cycle
- Scrolling for large traces
- Falls back to `--print` mode automatically when no TTY is available

## Script Options Reference

### trace_viewer.py (interactive + print modes)

```
--dir, -d DIR      Path to .monocle dir OR parent folder containing .monocle/ (default: .monocle in pwd)
                   Examples: --dir .monocle, --dir /test/, --dir /test/.monocle (all work)
--last, -l TIME    Show traces from last N minutes (e.g., 5m, 1h)
--trace-id, -t ID  Filter by trace ID (partial match)
--limit, -n N      Max trace files to load (default: 20)
--print, -p        Non-interactive print mode (for use in Bash tool)
```

### trace_minify.py (compact debug output)

```
--dir, -d DIR      Path to .monocle dir OR parent folder containing .monocle/ (default: .monocle in pwd)
                   Examples: --dir .monocle, --dir /test/, --dir /test/.monocle (all work)
--last, -l TIME    Show traces from last N minutes (e.g., 5m, 1h)
--trace-id, -t ID  Filter by trace ID (partial match)
--all, -a          Show all matching traces
--flat, -f         Flat output (no call tree)
--limit, -n N      Max trace files to show (default: 10)
--errors-only, -e  Only show spans with errors
```

## Fallback to Okahu MCP

When no local traces exist, offer to query Okahu Cloud:

```json
{
  "questions": [{
    "question": "No local traces found. Would you like to check Okahu Cloud instead?",
    "header": "Data Source",
    "multiSelect": false,
    "options": [
      {"label": "Yes, check Okahu Cloud", "description": "Query remote traces from deployed apps"},
      {"label": "No, I'll run /ok-instrument first", "description": "Generate local traces first"}
    ]
  }]
}
```

If user chooses Okahu Cloud, ask for app/workflow name and use `mcp__okahu-mcp-stage__get_traces`.

## SESSION.md - UPDATE IF NOTABLE

Append to `.okahu/SESSION.md` if errors found or notable observations:

```markdown
## Local Trace Review (/ok-local-trace)
- **Query**: "show me errors from today"
- **Interpreted as**: --errors-only --last 1440m
- **Traces reviewed**: 3
- **Errors found**: 1
  - PaymentService.charge failed: "Connection timeout"
- **Observations**: Payment service needs retry logic
```

## Usage Examples

```bash
# Natural language (preferred)
/ok-local-trace show me recent errors
/ok-local-trace what happened in the last hour
/ok-local-trace find the slowest trace
/ok-local-trace show trace abc123

# Interactive viewer (user runs directly)
! python .claude/scripts/trace_viewer.py
! python .claude/scripts/trace_viewer.py --last 5m
! python .claude/scripts/trace_viewer.py --trace-id abc123

# Inline output (works in Bash tool)
/ok-local-trace --last 5m
/ok-local-trace --errors-only
```

## Related Commands

- `/ok-instrument` - Run app to generate local traces first
- Use Okahu MCP tools for production/cloud traces
- `/ok-pause` - Save session before stopping work
- `/ok-resume` - Resume from saved session
