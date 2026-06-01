---
name: ok:imagegen
description: Generate visual assets using Codex CLI with gpt-image-2
argument-hint: <prompt> [--out-dir DIR] [--count N]
allowed-tools:
  - Read
  - Bash
  - Glob
  - Write
  - AskUserQuestion
---

# ok:imagegen <prompt> [--out-dir DIR] [--count N]

Generate visual assets (logos, palettes, illustrations, brand boards) using Codex CLI's `gpt-image-2` integration.

## Prerequisites

- **Codex CLI** installed: `npm install -g @openai/codex`
- **OPENAI_API_KEY** set in environment

## Steps

### Step 1: Check Prerequisites

```bash
# Load .env if present (never hardcode keys)
if [ -f .env ]; then
  set -a; source .env; set +a
fi
CODEX_BIN=$(which codex 2>/dev/null || echo "")
[ -z "$CODEX_BIN" ] && echo "CODEX_NOT_FOUND" || echo "CODEX_FOUND: $CODEX_BIN"
echo "OPENAI_API_KEY=${OPENAI_API_KEY:+set}"
```

If `CODEX_NOT_FOUND`:
> Codex CLI not found. Install it: `npm install -g @openai/codex`

If `OPENAI_API_KEY` is not set after loading `.env`:
> `OPENAI_API_KEY` is not set. Add it to `.env` or run: `! export OPENAI_API_KEY=sk-...`

Stop if either prerequisite is missing.

### Step 2: Parse Arguments

Parse the user's input:
- **prompt**: The image generation description (required). Everything before `--` flags.
- **--out-dir DIR**: Output directory (default: `generated-assets/`)
- **--count N**: Number of images to generate (default: 1, max: 7)

If no prompt provided, ask the user what they want to generate using `AskUserQuestion`:

> What visual assets would you like to generate?
>
> A) Logo concepts — icon-focused brand mark explorations
> B) Brand board — palette, typography, patterns, and application mockup
> C) Product illustrations — feature diagrams, hero images, marketing visuals
> D) Custom — I'll describe what I want

For options A-C, construct an appropriate detailed prompt. For D, ask for their description.

### Step 3: Prepare Output Directory

```bash
OUT_DIR="${OUT_DIR:-generated-assets}"
mkdir -p "$OUT_DIR"
```

### Step 4: Generate Assets

Run Codex with `gpt-image-2` via `danger-full-access` sandbox so it can save files:

```bash
codex exec "<constructed_prompt>" \
  -C "$(pwd)" \
  -s danger-full-access \
  -c 'model_reasoning_effort="xhigh"' \
  --enable web_search_cached \
  --json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        obj = json.loads(line)
        t = obj.get('type','')
        if t == 'item.completed' and 'item' in obj:
            item = obj['item']
            itype = item.get('type','')
            text = item.get('text','')
            if itype == 'reasoning' and text:
                print(f'[codex thinking] {text}')
                print()
            elif itype == 'agent_message' and text:
                print(text)
            elif itype == 'command_execution':
                cmd = item.get('command','')
                if cmd: print(f'[codex ran] {cmd}')
        elif t == 'turn.completed':
            usage = obj.get('usage',{})
            tokens = usage.get('input_tokens',0) + usage.get('output_tokens',0)
            if tokens: print(f'\ntokens used: {tokens}')
    except: pass
"
```

The constructed prompt should instruct Codex to:
1. Use the `imagegen` skill with `gpt-image-2` model
2. Generate the requested number of images
3. Save all PNG outputs to the specified output directory
4. Validate outputs exist and report dimensions

### Step 5: Verify Outputs

```bash
find "$OUT_DIR" -name "*.png" -type f | sort
```

Count the generated PNGs and report:

```
Generated N assets in $OUT_DIR/:
  - filename1.png (WxH)
  - filename2.png (WxH)
  ...
```

If no PNGs were generated, report the failure and suggest checking the Codex output for errors.

### Step 6: Open Preview

Offer to open the generated assets:

```bash
open "$OUT_DIR"
```

## Prompt Construction Guidelines

When building the prompt for Codex, follow these principles:

- **Logo concepts**: Request icon-focused designs without text (image models distort wordmarks). Specify the brand colors, style (minimal/geometric/organic), and metaphor.
- **Brand boards**: Request palette swatches, typography specimens, pattern tiles, and an application mockup in a single composed image at 2048px wide.
- **Product illustrations**: Describe the feature or concept, specify isometric/flat/3D style, and include brand colors.
- **Always include**: Target dimensions (1024x1024 for logos, 2048x1024 for boards), output format (PNG), and the output directory path.

## Examples

```
/ok-imagegen logo concepts for a cloud monitoring SaaS, minimal geometric style, blue-green palette
/ok-imagegen brand board for okahu.ai --out-dir branding/assets --count 4
/ok-imagegen product illustration showing AI agent trace visualization, isometric style
```
