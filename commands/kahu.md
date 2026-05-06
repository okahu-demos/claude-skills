---
name: kahu
description: Query the Okahu SRE Agent API. Auto-detects which environment (prod/stage/dev) the OKAHU_API_KEY works with.
allowed-tools:
  - Bash
  - Read
  - Write
---

# /kahu {query}

Query the Okahu SRE Agent API.

## Usage

```
/kahu What applications are available?
/kahu --key okh_xxx_yyy What applications are available?
```

## API Key Resolution

Priority order:
1. **Inline key**: If `$ARGUMENTS` starts with `--key <key>`, use that key and strip it from the query.
2. **`.env` file**: Source `.env` and use `OKAHU_API_KEY`.

**IMPORTANT**: The API key is ONLY used in the `x-api-key` HTTP header. Never include the API key in the JSON body/payload sent to the API.

## Environment URLs

```
PROD:  https://sre-agent.okahu.co/api/v1/ask_agent
STAGE: https://sre-agent-stage.okahu.co/api/v1/ask_agent
DEV:   https://okahu-sre-agent-dev-cid.azurewebsites.net/api/v1/ask_agent
```

## Steps

### Step 1: Parse arguments

Extract from `$ARGUMENTS`:
- If it starts with `--key <value>`, extract the key and use the remainder as the query.
- Otherwise, the entire argument is the query. Source `.env` to get `OKAHU_API_KEY`.

### Step 2: Resolve the API URL

Check if a cached environment has already been validated in `.claude/state/kahu_env.json`.

- If the file exists, check that the `api_key_prefix` matches the first 12 chars of the current key.
  - If it matches, use the cached `url`. Skip to Step 4.
  - If it doesn't match (different key), proceed to Step 3.
- If the file does not exist, proceed to Step 3.

### Step 3: Validate the API key (one-time per key)

Test the key against each environment using the sessions endpoint (lightweight, no agent call):

```bash
curl -s -o /dev/null -w "%{http_code}" \
  https://sre-agent.okahu.co/api/v1/sessions \
  -H "x-api-key: $API_KEY"
```

Try in order: **prod**, **stage**, **dev**. The first one returning HTTP 200 wins.

Save the result to `.claude/state/kahu_env.json`:

```json
{
  "url": "https://sre-agent.okahu.co/api/v1/ask_agent",
  "env": "prod",
  "api_key_prefix": "okh_SzokcBME",
  "validated_at": "2026-04-14T12:00:00Z"
}
```

If none return 200, tell the user their API key is invalid for all environments.

### Step 4: Call the SRE Agent API

```bash
curl -s -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"query": "THE_QUERY_HERE"}'
```

Where `$URL` is the resolved URL, `$API_KEY` is the resolved key, and the query is from the parsed arguments.

**IMPORTANT**: The `-d` payload must ONLY contain `{"query": "..."}`. Do NOT include the API key in the JSON body.

### Step 5: Display the response

Parse the JSON response and display the `response` field to the user in a readable format.
If there are `tool_calls`, summarize what tools were used but don't dump the raw tool call data unless the user asks.
