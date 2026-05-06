---
name: ok:instrument
description: Add tracing to your app (zero-code or code-based)
argument-hint: [app_folder]
allowed-tools:
  - Read
  - Bash
  - Write
  - Edit
  - Glob
  - AskUserQuestion
---

# ok:instrument

Add monocle tracing to your application. Supports two approaches.

## Prerequisites Check

**FIRST, check if scan/find was run:**
1. Look for `.okahu/choices.json` or `.okahu/ast_data.json`
2. If NOT found → tell user: "No analysis found. Run `/ok-scan` or `/ok-find` first."
3. If found → **read `.okahu/SESSION.md`** (if it exists) for context on prior decisions
4. Continue

## Step 1: Ask User Which Approach

**USE AskUserQuestion** to ask which instrumentation approach:

```json
{
  "questions": [{
    "question": "How would you like to add tracing?",
    "header": "Approach",
    "multiSelect": false,
    "options": [
      {"label": "Zero-code (Recommended)", "description": "Generate okahu.yaml config. No code changes. Run via okahu-instrument CLI."},
      {"label": "Code-based", "description": "Add setup_monocle_telemetry() to your entry point. Works with any run method."}
    ]
  }]
}
```

## Step 2A: Zero-code Instrumentation

If user selects **Zero-code**:

1. Read `.okahu/choices.json` and analysis files
2. **Use the `instrument` field, NOT `selected`** - This contains only entry points to avoid overlap
   - If A calls B, and both were selected, only A is in `instrument`
   - B is still traced as a child span when A runs
3. Generate `okahu.yaml` with:
   - Methods from `instrument` field (minimal set)
   - Arg filters (include/exclude/truncate)
   - Output extractors
   - **Skip orchestrator-only methods** (like `main()`) that have no meaningful inputs or outputs. The `workflow_name` already creates a root span for grouping. Only instrument methods that capture useful data (args, return values).
3. **Print the full YAML as regular text output** so the user can see it in the terminal. Use a fenced code block with `yaml` syntax highlighting. Do NOT put the YAML in the `preview` field of AskUserQuestion — it doesn't render in the CLI.
4. **THEN USE AskUserQuestion** to confirm or request edits (no preview field needed — the YAML is already visible above)
5. Write `okahu.yaml` to app folder
6. **Update `.okahu/SESSION.md`** — update the "Instrumentation Applied" section:
   ```markdown
   ## Instrumentation Applied
   _Updated by: /ok-instrument_
   - **Approach**: Zero-code
   - **Config file**: okahu.yaml
   - **Methods instrumented**: 5
   ```
8. Tell user: "Run `/ok-run <your command>` to execute with tracing"

## Step 2B: Code-based Instrumentation

If user selects **Code-based**:

1. Read `.okahu/choices.json` - use `instrument` field (minimal set, no overlap)
2. Detect entry point file from `.okahu/entry_points.json`
3. **USE AskUserQuestion** to confirm which file to modify:
   ```json
   {
     "questions": [{
       "question": "Which file should I add the setup code to?",
       "header": "Entry Point",
       "multiSelect": false,
       "options": [
         {"label": "main.py (Recommended)", "description": "Detected as CLI entry point"},
         {"label": "app.py", "description": "Flask/FastAPI application"},
         {"label": "Other", "description": "Specify a different file"}
       ]
     }]
   }
   ```
4. Generate and inject setup code at top of file:
   ```python
   # Monocle instrumentation setup
   from monocle_apptrace import setup_monocle_telemetry
   setup_monocle_telemetry(
       workflow_name="my_app",
       # wrapper_methods configured for selected methods
   )
   ```
5. **Check requirements.txt** - ensure `monocle_apptrace` is listed, add if missing
6. **Update `.okahu/SESSION.md`** — update the "Instrumentation Applied" section:
   ```markdown
   ## Instrumentation Applied
   _Updated by: /ok-instrument_
   - **Approach**: Code-based
   - **File modified**: main.py
   - **Setup code added**: Lines 1-15
   ```
8. Tell user: "Setup code added. Run your app normally - tracing is enabled."

## Generated okahu.yaml Format (Zero-code)

```yaml
workflow_name: my_app

instrument:
  - package: billing.processor
    class: PaymentProcessor
    method: charge
    span_name: payment.charge

    inputs:
      include: [amount, card_token]
      exclude: [metadata, logger]
      truncate:
        card_token: 4

    output:
      extract: [transaction_id, status]
```

## Overlap Avoidance

The `instrument` field in choices.json contains only **entry points** - methods that aren't called by other selected methods. This avoids redundant instrumentation:

```
Selected: A.run(), B.process(), C.save()
Call graph: A.run() → B.process() → C.save()
Instrument: A.run() only (B and C are covered as child spans)
```

If you need to override this, use the `selected` field instead, but expect duplicate spans.

## Final Output — Show Full Trace Examples

**DO NOT use a compact boxed summary at the end.** The box gets cut off in the terminal.

Instead, after instrumentation is complete, print a **full-screen output** showing concrete examples of what the user will get. Use plain text, no boxes:

```
Instrumentation complete. Here's what your traces will look like:


EXAMPLE 1: PaymentProcessor.charge()
─────────────────────────────────────
When you call PaymentProcessor.charge(amount=500, currency="USD"):

  payment.charge                              ├── 245ms
    ├─ gateway.submit(amount=500)             │   ├── 180ms
    │   └─ http.post(url="/api/charge")       │   │   └── 165ms
    └─ ledger.record(tx_id="tx_abc123")       │   └── 12ms

  Captured inputs:  amount=500, currency="USD"
  Captured outputs: transaction_id="tx_abc123", status="success"
  Excluded args:    metadata (configured)


EXAMPLE 2: UserService.create()
───────────────────────────────
When you call UserService.create(email="user@example.com"):

  user.create                                 ├── 89ms
    ├─ validator.check(email="user@exam...")   │   ├── 3ms
    └─ repo.save(user_id="u_789")             │   └── 45ms

  Captured inputs:  email="user@exam..." (truncated to 100)
  Captured outputs: user_id="u_789"


Next steps:
  /ok-run <your command>     Run your app with tracing enabled
  /ok-local-trace            View traces after running
```

**Rules for the final output:**
- Show one example per instrumented entry point (up to 5)
- Include the child spans that will appear (from the call graph)
- Show realistic argument values based on the method signatures
- Show which args are captured, excluded, or truncated per the config
- Use plain markdown with horizontal rules — NO box-drawing characters that might wrap
- Let the output breathe — full width, no cramming into a box

## SKIP PATTERNS - DO NOT INCLUDE

**NEVER include these in instrumentation:**
- `__init__.py` files - Package initializers
- `__init__` methods - Constructors (filtered at AST parse stage)
- `__str__`, `__repr__`, `__eq__`, etc. - Dunder methods (filtered at AST parse stage)
- Methods from test files

## Related Commands

- `/ok-scan` or `/ok-find` - Run first to analyze codebase
- `/ok-run` - Execute app with tracing (zero-code approach)
- `/ok-local-trace` - View traces after running
- `/ok-pause` - Save session before stopping work
- `/ok-resume` - Resume from saved session
