---
name: ok:find
description: Find methods by search or exact name, then trace execution paths
argument-hint: [query or Class.method]
allowed-tools:
  - Read
  - Bash
  - Write
  - Glob
  - Grep
  - AskUserQuestion
---

# ok:find [query or Class.method]

Find methods and trace their execution paths. Supports two modes:

- **Search mode**: Natural language query → find matching methods → trace paths
- **Direct mode**: Exact `Class.method` name → skip search → trace paths directly

## Mode Detection

Automatically detect mode based on input:
- Contains `.` AND matches `ClassName.method_name` pattern → **Direct mode**
- Otherwise → **Search mode**

```
/ok-find payment flow           → Search mode (natural language)
/ok-find PaymentService.charge  → Direct mode (exact Class.method)
/ok-find db.UserRepo.save       → Direct mode (exact Class.method)
/ok-find database operations    → Search mode (natural language)
```

## SKIP PATTERNS - DO NOT INCLUDE

**NEVER include these:**
- `__init__.py` files - Package initializers, not business logic
- `__init__` methods - Constructor setup, not traceable operations
- `__str__`, `__repr__`, `__eq__`, etc. - Dunder/magic methods
- Methods from test files - Not production code

## Steps

### For Search Mode (natural language query):
1. If no query provided, **USE AskUserQuestion** to ask for description
2. Run `python .claude/scripts/ast_parser.py <path>` if not already done
3. Search class/method names, docstrings for matches
4. Rank by relevance to query
5. Present candidates in text output: "Found N matches..."
6. **USE AskUserQuestion** to select which methods to trace
7. Continue to path finding (step 10)

### For Direct Mode (exact Class.method):
8. Run ast_parser and call_graph if not already done
9. Verify the method exists in codebase
10. Find all callers (reverse call graph)
11. Trace back to entry points
12. Present all paths: "Found N paths to <method>..."
13. **USE AskUserQuestion** to select which path(s) to instrument
14. Save to `.okahu/choices.json`
15. **Write/update `.okahu/SESSION.md`** — update "Entry Points Selected", "Methods to Instrument", and "Methods Covered" sections (see ok-scan.md for full format)
17. Suggest `/ok-instrument`

## SESSION.md - ALWAYS UPDATE

Append to `.okahu/SESSION.md` after running:

```markdown
## Find Results (/ok-find)
- **Query**: "payment processing" (search mode) OR "PaymentService.charge" (direct mode)
- **Methods found**:
  - billing.Processor.charge
  - orders.Order.process_payment
- **Paths selected**:
  - Path A: main → cli.import_users → [target]
- **Next**: Run `/ok-instrument` to generate okahu.yaml
```

## Interactive Questions - USE AskUserQuestion TOOL

### Ask for query (if not provided):
```json
{
  "questions": [{
    "question": "What are you looking for? Enter a search term or exact Class.method name.",
    "header": "Find",
    "multiSelect": false,
    "options": [
      {"label": "Payment processing", "description": "Search for payment-related methods"},
      {"label": "Database operations", "description": "Search for CRUD, queries, transactions"},
      {"label": "User authentication", "description": "Search for login, tokens, sessions"},
      {"label": "Enter exact method name", "description": "e.g., PaymentService.charge"}
    ]
  }]
}
```

### Method selection (Search mode only):
```json
{
  "questions": [{
    "question": "Which methods should be traced?",
    "header": "Methods",
    "multiSelect": true,
    "options": [
      {"label": "billing.Processor.charge (Recommended)", "description": "Score: 0.95 - 'Process a payment charge'"},
      {"label": "orders.Order.process_payment", "description": "Score: 0.82 - 'Handle order payment'"},
      {"label": "checkout.Cart.finalize", "description": "Score: 0.71 - 'Complete checkout with payment'"},
      {"label": "All matches", "description": "Trace all methods matching the query"}
    ]
  }]
}
```

### Path selection (both modes):
```json
{
  "questions": [{
    "question": "Which execution path(s) should be instrumented?",
    "header": "Paths",
    "multiSelect": true,
    "options": [
      {"label": "Path A (Recommended)", "description": "main:main -> cli.import_users -> [target]"},
      {"label": "Path B", "description": "api.routes:create_user -> services.UserService.create -> [target]"},
      {"label": "Path C", "description": "api.routes:update_user -> services.UserService.update -> [target]"},
      {"label": "All paths", "description": "Instrument all execution paths to this method"}
    ]
  }]
}
```

## Usage Examples

```
# Search mode - find by description
/ok-find payment flow
/ok-find database operations
/ok-find user authentication
/ok-find error handling

# Direct mode - trace exact method
/ok-find PaymentService.charge
/ok-find db.UserRepo.save
/ok-find auth.TokenValidator.validate
```

## Related Commands

- `/ok-scan` - Full codebase analysis
- `/ok-instrument` - Add tracing (zero-code or code-based)
- `/ok-run` - Run app with tracing
- `/ok-pause` - Save session before stopping work
- `/ok-resume` - Resume from saved session
