---
name: ok:run
description: Run your app with monocle tracing enabled
argument-hint: [command...]
allowed-tools:
  - Read
  - Bash
  - Glob
  - AskUserQuestion
---

# ok:run [command...]

Smart runner for instrumented apps. Automatically determines how to run based on instrumentation approach.

## Smart Behavior

1. **Check instrumentation approach** from `.okahu/SESSION.md`
2. **Determine run command**:
   - If command provided → use it
   - If only one entry point detected → use it automatically
   - If multiple options → prompt user to choose
3. **Execute**:
   - Zero-code approach → wrap with `okahu-instrument`
   - Code-based approach → run directly

## Steps

### Step 1: Check Prerequisites

1. Read `.okahu/SESSION.md` for context on prior decisions
2. From SESSION.md determine:
   - Instrumentation approach (zero-code or code-based)
   - Entry points detected during scan
3. If no SESSION.md → tell user: "Run `/ok-instrument` first."

### Step 2: Check Okahu Credentials

**Check if credentials are configured:**

1. First check if `.env` exists in app folder and source it:
   ```bash
   if [ -f .env ]; then source .env; fi
   ```

2. Check current env vars:
   ```bash
   echo "OKAHU_INGESTION_ENDPOINT: ${OKAHU_INGESTION_ENDPOINT:-not set}"
   echo "OKAHU_API_KEY: ${OKAHU_API_KEY:+[configured]}"
   ```

**If EITHER is missing, USE AskUserQuestion:**

```json
{
  "questions": [{
    "question": "Okahu credentials needed for cloud tracing. How would you like to configure them?",
    "header": "Okahu Credentials",
    "multiSelect": false,
    "options": [
      {"label": "Enter credentials now", "description": "Save to .env and use for this session"},
      {"label": "Local-only tracing", "description": "Skip cloud - traces saved to .monocle/ folder only"},
      {"label": "Already set in environment", "description": "I've exported them in my shell"}
    ]
  }]
}
```

**If user selects "Enter credentials now":**

1. Ask for endpoint:
   ```
   Enter OKAHU_INGESTION_ENDPOINT (e.g., https://ingest.okahu.co):
   ```

2. Ask for API key:
   ```
   Enter OKAHU_API_KEY:
   ```

3. Save to `.env` file (create or append):
   ```bash
   # Check if .env exists
   touch .env

   # Remove old values if present
   grep -v "^OKAHU_INGESTION_ENDPOINT=" .env > .env.tmp && mv .env.tmp .env
   grep -v "^OKAHU_API_KEY=" .env > .env.tmp && mv .env.tmp .env

   # Append new values
   echo "OKAHU_INGESTION_ENDPOINT=<user-provided>" >> .env
   echo "OKAHU_API_KEY=<user-provided>" >> .env
   ```

4. Source and run:
   ```bash
   source .env
   # Then proceed to Step 4: Execute
   ```

5. Tell user: "Credentials saved to `.env`. They will be used automatically next time."

**If user selects "Local-only tracing":**
- Continue without setting credentials
- Traces will be saved to `.monocle/` folder only
- Tell user: "Traces will be saved locally to `.monocle/`. Use `/ok-local-trace` to view them."

**If user selects "Already set in environment":**
- Verify by checking env vars again
- If still not set, warn and ask again

### Step 3: Determine Run Command

**If command provided in arguments:**
- Use it directly

**If no command provided:**

1. Check `.okahu/entry_points.json` for detected entry points
2. **If exactly ONE entry point** → use it automatically, no prompt needed
3. **If MULTIPLE entry points or UNCLEAR** → **USE AskUserQuestion**:

```json
{
  "questions": [{
    "question": "How would you like to run your app?",
    "header": "Run",
    "multiSelect": false,
    "options": [
      {"label": "python main.py", "description": "CLI entry point (detected)"},
      {"label": "flask run -p 8080", "description": "Flask dev server"},
      {"label": "uvicorn app:app --reload", "description": "ASGI server"},
      {"label": "python -m myapp", "description": "Module execution"},
      {"label": "Enter custom command", "description": "Specify your own run command"},
      {"label": "Don't run - exit", "description": "Exit without running"}
    ]
  }]
}
```

Note: Build options dynamically from:
- Detected entry points (`.okahu/entry_points.json`)
- Common patterns based on detected frameworks (Flask, FastAPI, etc.)
- Always include "Enter custom command" and "Don't run - exit"

**If user selects "Don't run - exit":**
- Say "Okay, not running. You can run manually or use `/ok-run <command>` later."
- Exit without running anything

**If user selects "Enter custom command":**
- Ask: "Enter your run command (e.g., `flask run -p 8080`):"

### Step 4: Execute

**If Zero-code approach (okahu.yaml exists):**
```bash
python .claude/scripts/okahu_instrument.py <command>
```

**If Code-based approach (setup code injected):**
```bash
<command>
```
Run the command directly - tracing is already enabled via injected code.

### Step 5: Handle Long-Running Processes

For servers/workers that listen on ports:
- Run the command normally (it will block and listen)
- User can Ctrl+C to stop
- Traces are flushed on shutdown

**Important:** Do NOT use `run_in_background` for servers - they need to run in foreground so user can see output and Ctrl+C to stop.

### Step 6: Update SESSION.md

After running (or if user exits), **update `.okahu/SESSION.md`** — append to the "Run History" section:
```markdown
## Run History
_Updated by: /ok-run_
- YYYY-MM-DD HH:MM: `<command>` — <approach> — <status>
```

## Examples

```bash
# Explicit command
/ok-run python app.py
/ok-run flask run -p 8080
/ok-run uvicorn app:app --host 0.0.0.0 --port 8000
/ok-run celery -A myapp worker --loglevel=info

# Auto-detect (will prompt if multiple options)
/ok-run
```

## Environment Variables

These are passed through to the app:

```bash
MONOCLE_STRICT=true       # Fail if instrumentation breaks (default: false)
MONOCLE_SILENT=true       # Suppress warnings (default: false)
OKAHU_INGESTION_ENDPOINT  # Okahu cloud endpoint
OKAHU_API_KEY             # Okahu API key
```

## Related Commands

- `/ok-instrument` - Must run first to set up tracing
- `/ok-local-trace` - View traces after running
- `/ok-pause` - Save session before stopping work
- `/ok-resume` - Resume from saved session
