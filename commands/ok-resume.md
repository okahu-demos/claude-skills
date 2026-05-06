---
name: ok:resume
description: Resume an instrumentation session from saved context
argument-hint: [app_folder]
allowed-tools:
  - Read
  - Bash
  - Glob
  - AskUserQuestion
---

# ok:resume [app_folder]

Resume an instrumentation session by loading `.okahu/SESSION.md` and restoring full context.

**Use this when:**
- Starting a new Claude session
- After `/clear`
- Returning to a project after a break
- Picking up where `/ok-pause` left off

## Process

### Step 1: Find Session

```bash
# Search for SESSION.md files
find . -name "SESSION.md" -path "*/.okahu/*" 2>/dev/null
```

If app_folder provided, look in `{app_folder}/.okahu/SESSION.md`.

If multiple found, **USE AskUserQuestion**:
```json
{
  "questions": [{
    "question": "Multiple instrumentation sessions found. Which one to resume?",
    "header": "Session",
    "multiSelect": false,
    "options": [
      {"label": "examples/.okahu/SESSION.md", "description": "Last updated: 2024-03-16 - my_app scanning"},
      {"label": "src/.okahu/SESSION.md", "description": "Last updated: 2024-03-15 - payment service"},
      {"label": "Start new session", "description": "Run /ok-scan on a new folder"}
    ]
  }]
}
```

### Step 2: Load Full Context

1. **Read `.okahu/SESSION.md`** - get conversation history and decisions
2. **Read `.okahu/entry_points.json`** - if exists, load detected entry points
3. **Read `.okahu/monocle_support.json`** - if exists, load framework detection
4. **Read `.okahu/choices.json`** - if exists, load user choices
5. **Check analysis files**:
   ```bash
   ls -la .okahu/*.json 2>/dev/null
   ```

### Step 3: Parse Last Session Block

From SESSION.md, extract the most recent session block:
- **Position**: Current stage (scan/instrument/run/trace)
- **Completed work**: What's been done
- **Decisions made**: Choices that should carry forward
- **Next steps**: Where to continue
- **Context notes**: Mental state and approach

### Step 4: Display Status

```
=== Monocle Session Restored ===

📁 App folder: {app_folder}
📅 Last session: {timestamp from last session block}

🎯 Current Position:
  - Stage: {scan|instrument|run|trace}
  - Entry point: {entry_point or "not identified"}
  - Framework: {framework or "none detected"}

✅ Completed:
  - {from Completed This Session}
  - {from Completed This Session}

📝 Key Decisions:
  - {decision}: {rationale}

⏳ Next Steps:
  1. {from Next Steps}
  2. {from Next Steps}

📊 Analysis Files:
  - .okahu/entry_points.json ({size})
  - .okahu/call_graph.json ({size})
  - .okahu/monocle_support.json ({size})

💭 Context: {context notes summary}
```

### Step 5: Prompt for Action

**USE AskUserQuestion**:
```json
{
  "questions": [{
    "question": "What would you like to do?",
    "header": "Next Step",
    "multiSelect": false,
    "options": [
      {"label": "Continue from next steps", "description": "{first next step from SESSION.md}"},
      {"label": "/ok-scan", "description": "Re-run or continue codebase scan"},
      {"label": "/ok-instrument", "description": "Add tracing configuration"},
      {"label": "/ok-run", "description": "Execute app with tracing"},
      {"label": "/ok-local-trace", "description": "View collected traces"},
      {"label": "View full SESSION.md", "description": "Show complete session history"}
    ]
  }]
}
```

## No Session Found

If no SESSION.md exists:

```
No saved session found in {searched_locations}.

To start a new session:
  /ok-scan {app_folder}    - Scan codebase for entry points
  /ok-instrument           - Add tracing to existing project
```

## Usage Examples

```
/ok-resume                    # Auto-find and resume session
/ok-resume examples/          # Resume session in examples folder
/ok-resume src/               # Resume session in src folder
```

## Related Commands

- `/ok-pause` - Save current session before stopping
- `/ok-scan` - Start new codebase analysis
- `/ok-instrument` - Add tracing configuration
- `/ok-run` - Execute with tracing enabled
