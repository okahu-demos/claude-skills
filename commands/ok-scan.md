---
name: ok:scan
description: Full codebase scan to recommend what to trace
allowed-tools:
  - Read
  - Bash
  - Write
  - Glob
  - Grep
  - AskUserQuestion
---

# ok:scan

Full codebase analysis to recommend what to trace.

## IMPORTANT: Framework Detection First

**ALWAYS run framework detection FIRST.** If monocle-supported frameworks are found, prioritize using monocle's built-in auto-instrumentation. Do NOT reinvent the wheel.

### Monocle Built-in Support

| Category | Frameworks | Instrumentation |
|----------|------------|-----------------|
| LLM Inference | OpenAI, Anthropic, Azure AI, Bedrock, Gemini, LiteLLM, Mistral, HuggingFace | Auto |
| Agent Frameworks | LangChain, LlamaIndex, LangGraph, CrewAI, Haystack, OpenAI Agents, AutoGen | Auto |
| HTTP Frameworks | Flask, FastAPI, AIOHTTP | Auto + decorators |
| Cloud Functions | Azure Functions, AWS Lambda | Decorators required |
| MCP | FastMCP, MCP SDK | Auto |

If ALL code uses supported frameworks → just use `setup_monocle_telemetry()`, no custom YAML needed.

## SKIP PATTERNS - DO NOT INSTRUMENT

**NEVER instrument these:**
- `__init__.py` files - These are package initializers, not business logic
- `__init__` methods - Constructor setup, not traceable operations
- `__str__`, `__repr__`, `__eq__`, etc. - Dunder/magic methods
- Files in `tests/`, `test_*.py`, `*_test.py` - Test files
- Files in `migrations/`, `alembic/` - Database migrations
- Files in `.venv/`, `venv/`, `site-packages/` - Virtual environments

## Steps

1. Ask user for the app folder path (use AskUserQuestion if not provided in arguments)
2. **FIRST: Run framework detection** - `python .claude/scripts/monocle_detector.py <path>`
3. **Check for existing instrumentation** - Search for `setup_monocle_telemetry` in the codebase:
   - Run: `grep -r "setup_monocle_telemetry" <path> --include="*.py" -l`
   - If found, note which files already have monocle setup
4. If supported frameworks found:
   - Show what's auto-instrumented vs needs decorators
   - **If existing instrumentation found**: Show which files already have setup and what's covered
   - **USE AskUserQuestion** with appropriate options (see "Existing Instrumentation" section below)
   - If user chooses "keep as-is" → show next steps and exit
   - If user chooses auto-instrumentation → suggest setup code and skip to step 12
5. Run `python .claude/scripts/ast_parser.py <path> -o <path>/.okahu/ast_data.json --pretty`
6. Run `python .claude/scripts/entry_detector.py <path>/.okahu/ast_data.json`
7. **USE AskUserQuestion** to ask which entry points to analyze (see example below)
8. Run `python .claude/scripts/call_graph.py <path>/.okahu/ast_data.json`
9. Run `python .claude/scripts/relevance_scorer.py .okahu/call_graph.json --entry <selected>`
10. **USE AskUserQuestion** to ask about medium-relevance modules (multiSelect: true)
11. Run `python .claude/scripts/arg_analyzer.py <path>/.okahu/ast_data.json`
12. **USE AskUserQuestion** to ask how to handle large args for each flagged method
13. **Compute minimal instrumentation set** - Avoid overlap by only instrumenting entry points:
    - Run: `python .claude/scripts/call_graph.py <path>/.okahu/call_graph.json --minimize <path>/.okahu/choices.json -o <path>/.okahu/minimal.json`
    - This removes methods that are already covered by parent calls
    - Example: if `A.method1() -> B.method2()` and both selected, only instrument A
14. Save choices to `<path>/.okahu/choices.json` with format:
    ```json
    {
      "selected": ["module:Class.method", ...],
      "instrument": ["entry points only"],
      "covered": ["reachable from entry points"],
      "removed": ["methods covered by parents"],
      "arg_handling": { ... }
    }
    ```
15. **Write/update `<path>/.okahu/SESSION.md`** — the single source of truth (see format below)
16. Suggest running `/ok-instrument` to generate YAML

## SESSION.md Format - ALWAYS UPDATE

After each /ok- command, write/append to `.okahu/SESSION.md`.

**This file must be self-contained.** After `/clear` or a new session, Claude reads only this file to understand what happened. Include enough detail that no other file needs to be read to resume work.

```markdown
# Okahu Instrumentation Session

## Last Updated
YYYY-MM-DD HH:MM

## App
- **Path**: /absolute/path/to/app/folder
- **Run command**: `python my_app.py` (or `flask run`, `uvicorn app:app`, etc.)

## Scan Results (/ok-scan)
- **Existing instrumentation**: serve.py (or "None")
- **Entry point selected**: my_app:main (my_app.py:15, CLI via __main__)
- **Frameworks detected**: Flask, OpenAI (auto-instrumented) (or "None")

### Methods to Instrument
| # | Module | Method | Args |
|---|--------|--------|------|
| 1 | my_app | main() | — |
| 2 | billing.processor | PaymentProcessor.charge() | amount: int, card_token: str |

### Methods Covered (traced as child spans, no separate config needed)
- `billing.gateway.Gateway.submit` — called by PaymentProcessor.charge

### Arg Handling (only if large args flagged)
- PaymentProcessor.charge.metadata → excluded
- UserService.create.user_data → truncate 100

## Instrumentation Applied
_Updated by: /ok-instrument_
- **Approach**: Zero-code / Code-based
- **Config file**: okahu.yaml (or entry point file modified)
- **Methods instrumented**: 5

## Framework Support Added
_Updated by: /ok-add-framework_
- **Framework**: <name> (<package>)
- **Entity types**: Agent, Tool, Inference
- **Methods file**: metamodel/<framework>/methods.py
- **Handler**: <framework>_handler (custom) / default

## Run History
_Updated by: /ok-run_
- YYYY-MM-DD HH:MM: `flask run -p 8080` — zero-code — completed
- YYYY-MM-DD HH:MM: `python main.py` — code-based — error

## Analysis Files
All in `<app_path>/.okahu/`:
- `ast_data.json` — parsed classes, methods, args
- `call_graph.json` — caller→callee edges
- `entry_points.json` — detected entry points
- `relevance.json` — module relevance scores
- `arg_analysis.json` — large arg flags
- `choices.json` — user selections (methods, arg handling)

## Next Steps

### If existing instrumentation retained:
- [x] Setup already in place (serve.py)
- [ ] Run `/ok-run <command>` to execute with tracing
- [ ] Run `/ok-local-trace` to check traces

### If new instrumentation needed:
- [ ] Run `/ok-instrument` to add tracing (zero-code or code-based)
- [ ] Run `/ok-run <command>` to execute with tracing
- [ ] Run `/ok-local-trace` to check traces
```

This file persists across `/clear` and session exits.

## Interactive Questions - USE AskUserQuestion TOOL

### Existing instrumentation found:
When `setup_monocle_telemetry` is already in the codebase, use this question:
```json
{
  "questions": [{
    "question": "Monocle instrumentation already exists. How would you like to proceed?",
    "header": "Existing",
    "multiSelect": false,
    "options": [
      {"label": "Keep as-is (Recommended)", "description": "Current setup covers frameworks - just run your app"},
      {"label": "Scan for gaps", "description": "Check if custom code paths need additional tracing"},
      {"label": "Show current coverage", "description": "Display what's currently instrumented vs what's not"}
    ]
  }]
}
```

When user selects "Keep as-is":
- Show which files have `setup_monocle_telemetry`
- List what frameworks are auto-traced
- Suggest next steps: `/ok-run` and `/ok-local-trace`
- Update SESSION.md with "Existing instrumentation retained"

When user selects "Scan for gaps":
- Continue with full scan (step 5+)
- Focus on custom code not covered by auto-instrumentation
- In SESSION.md, note which entry points already have setup

### Framework detection (no existing instrumentation):
```json
{
  "questions": [{
    "question": "Supported frameworks detected. How would you like to proceed?",
    "header": "Frameworks",
    "multiSelect": false,
    "options": [
      {"label": "Use auto-instrumentation (Recommended)", "description": "Just add setup_monocle_telemetry() - no custom YAML needed"},
      {"label": "Continue with full scan", "description": "Also trace custom code alongside frameworks"},
      {"label": "Show setup code", "description": "Display the setup code to add to your app"}
    ]
  }]
}
```

### Entry point selection:
```json
{
  "questions": [{
    "question": "Which entry point should I analyze for tracing?",
    "header": "Entry Point",
    "multiSelect": false,
    "options": [
      {"label": "main.py:main (Recommended)", "description": "CLI entry - reaches 45 methods"},
      {"label": "api/app.py:create_app", "description": "Flask app - reaches 120 methods"},
      {"label": "All entry points", "description": "Analyze all detected entry points"}
    ]
  }]
}
```

### Module relevance — show top 10 ranked list

**DO NOT ask a generic open-ended question about modules.** Instead:

1. Read `relevance.json` and rank ALL medium-relevance modules by call count
2. Take the top 10 (or fewer if less exist)
3. For each module, show: rank, module path, call count, callers, and a **concrete example** of what a trace span would look like if instrumented
4. Present as a multiSelect with scroll — user picks which to include

```json
{
  "questions": [{
    "question": "Select which modules to include in tracing (top 10 by usage):",
    "header": "Intermediate Modules",
    "multiSelect": true,
    "options": [
      {"label": "1. utils/validation.py", "description": "Called 12x by 5 modules → span: validate_input(amount=500, currency='USD') → OK 2ms"},
      {"label": "2. helpers/cache.py", "description": "Called 9x by 4 modules → span: cache_lookup(key='user:123') → HIT 0.3ms"},
      {"label": "3. db/connection.py", "description": "Called 8x by 6 modules → span: get_connection(pool='main') → connected 15ms"},
      {"label": "4. auth/token.py", "description": "Called 7x by 3 modules → span: verify_token(token='eyJ...') → valid 5ms"},
      {"label": "5. helpers/formatting.py", "description": "Called 5x by 2 modules → span: format_response(data={...}) → formatted 1ms"},
      {"label": "── Select none ──", "description": "Only trace high-relevance entry points (recommended for minimal overhead)"}
    ]
  }]
}
```

**How to generate the example spans:**
- Read the module's AST data to find the primary method and its arguments
- Show a realistic call with sample argument values and a plausible duration
- Format as: `method_name(arg1=val1, arg2=val2) → result duration`
- This helps users judge whether the span is worth the overhead

### Large argument handling:
```json
{
  "questions": [{
    "question": "How should large arguments be handled for PaymentProcessor.charge()?",
    "header": "Arg Handling",
    "multiSelect": false,
    "options": [
      {"label": "Include full value", "description": "Capture entire argument (may be large)"},
      {"label": "Exclude entirely", "description": "Don't capture this argument"},
      {"label": "Extract specific keys", "description": "Only capture certain keys from dict/object"},
      {"label": "Truncate to 100 chars", "description": "Capture first 100 characters only"}
    ]
  }]
}
```

## SESSION.md — ALL /ok-* Commands Must Read and Update

**Every `/ok-*` command MUST:**
1. **Read** `<path>/.okahu/SESSION.md` at the start (if it exists) for context on prior decisions
2. **Update** its own sections after completing work

**Rules:**
- Create the file on first `/ok-scan` or `/ok-find` run
- Each command updates ONLY its own sections (don't overwrite other sections)
- Always update the "Last updated" line with current timestamp and command name
- If a section doesn't exist yet, append it

## Scripts Location

Helper scripts are in `.claude/scripts/`:
- `ast_parser.py` - Extract classes, methods, args from Python code
- `call_graph.py` - Build caller->callee relationships
- `entry_detector.py` - Find main, routes, workers
- `relevance_scorer.py` - Score module importance
- `arg_analyzer.py` - Flag large/useless arguments

Analysis output goes to `.okahu/` folder in the target directory.

## Related Commands

- `/ok-instrument` - Generate okahu.yaml from scan results
- `/ok-pause` - Save session before stopping work
- `/ok-resume` - Resume from saved session
