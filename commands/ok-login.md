---
name: ok:login
description: Authenticate with Okahu Cloud via GitHub Device Flow
argument-hint: [--force] [stage|prod]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# /ok-login [--force] [stage|prod]

Authenticate with Okahu Cloud using GitHub Device Flow. Opens browser to github.com/login/device where user enters a code. No localhost server needed.

## Argument Parsing

Parse `$ARGUMENTS` for:
- `--force` — skip the "already authenticated" check, go straight to auth flow
- `stage` or `prod` — explicit environment selection

Examples: `/ok-login stage`, `/ok-login --force prod`, `/ok-login --force`, `/ok-login`

## Environment Configuration

| Env | GitHub OAuth App client_id | API host | Ingestion endpoint | SRE Agent URL |
|-----|---------------------------|----------|-------------------|---------------|
| **stage** | `Ov23liSuSur0n7NZwn78` | `https://api-stage.okahu.co` | `https://ingest-stage.okahu.co/api/v1/trace/ingest` | `https://sre-agent-stage.okahu.co/api/v1/ask_agent` |
| **prod** | `Ov23liUr1RINNngYy8Tp` | `https://api.okahu.co` | `https://ingest.okahu.co/api/v1/trace/ingest` | `https://sre-agent.okahu.co/api/v1/ask_agent` |

## Step 1: Determine environment

**If `$ARGUMENTS` specifies `stage` or `prod`**, use that environment directly.

**If no argument**, detect from current `.env`:

1. Source `.env` and check `OKAHU_API_KEY`
2. If set, test against both environments:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" \
     https://sre-agent.okahu.co/api/v1/sessions \
     -H "x-api-key: $OKAHU_API_KEY"
   ```
   - HTTP 200 from prod URL → current env is **prod**
   - HTTP 200 from stage URL → current env is **stage**
3. If key exists and is valid:
   - If `--force` was passed → skip prompt, proceed to Step 2
   - Otherwise → tell user: "Already authenticated to **{env}**. Run `/ok-login --force` to re-authenticate." Then stop.
4. If no key or invalid → check `OKAHU_INGESTION_ENDPOINT` for "stage" substring to infer env
5. If still ambiguous → default to **stage**

Store the resolved environment for all subsequent steps.

## Step 2: GitHub Device Flow

### 2a. Request device code

```bash
RESPONSE=$(curl -s -X POST "https://github.com/login/device/code" \
  -H "Accept: application/json" \
  -d "client_id=${CLIENT_ID}&scope=user:email")
```

Parse the JSON response to extract:
- `device_code` — used for polling
- `user_code` — shown to the user (e.g., `933F-EF84`)
- `verification_uri` — `https://github.com/login/device`
- `expires_in` — seconds until code expires (typically 899)
- `interval` — minimum polling interval in seconds (typically 5)

If the response contains `"error"`, show it and stop.

### 2b. Show code and open browser

**CRITICAL**: Bash tool output is NOT visible to the user in Claude CLI. You MUST output the code as **direct text** (markdown outside any tool call) so the user can see it. Then open the browser with a separate Bash call.

Do this in TWO parts:

1. **First, output this as plain text** (NOT inside a Bash call — just write it as your response text):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Okahu Cloud — GitHub Authentication

  URL:  https://github.com/login/device
  Code: {USER_CODE}

  Enter the code above in your browser.
  Waiting for authorization...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

2. **Then open the browser** with a Bash call:

```bash
open "https://github.com/login/device"
```

The text output appears immediately in the CLI. The user sees the code while the browser opens.

### 2c. Poll for authorization

Poll GitHub every `interval` seconds until authorized or expired. Use a bash loop:

```bash
while true; do
  TOKEN_RESPONSE=$(curl -s -X POST "https://github.com/login/oauth/access_token" \
    -H "Accept: application/json" \
    -d "client_id=${CLIENT_ID}&device_code=${DEVICE_CODE}&grant_type=urn:ietf:params:oauth:grant-type:device_code")
  # check response...
  sleep $INTERVAL
done
```

Handle poll responses:
- `"error": "authorization_pending"` — keep polling
- `"error": "slow_down"` — increase interval by 5 seconds, keep polling
- `"error": "expired_token"` — code expired, tell user to run `/ok-login` again
- `"error": "access_denied"` — user cancelled, stop
- `"access_token": "gho_xxx"` — success! Proceed to Step 3

Print a dot every poll cycle so the user knows it's waiting.

### 2d. Fetch user info

Once we have the GitHub access token, fetch user details:

```bash
USER=$(curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" -H "Accept: application/json" https://api.github.com/user)
EMAILS=$(curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" -H "Accept: application/json" https://api.github.com/user/emails)
```

Extract `username` and primary `email`.

## Step 3: Resolve tenant and generate API key

Use the GitHub access token as a Bearer token to resolve the user's tenant and auto-generate an API key (same flow as the Okahu VS Code extension).

### 3a. Fetch tenant info

```bash
TENANT_RESPONSE=$(curl -s -w "\n%{http_code}" \
  "${API_HOST}/api/v1/tenant" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json")
HTTP_CODE=$(echo "$TENANT_RESPONSE" | tail -1)
BODY=$(echo "$TENANT_RESPONSE" | sed '$d')
```

- **HTTP 200**: Extract `tenant_id` from JSON response (check fields: `tenant_id`, `id`, or `tenantId`)
- **MISSING_TENANT_CLAIM error or 404**: New user — proceed to Step 3b to create tenant
- **Other error**: Show error and stop

### 3b. Create tenant (new users only)

```bash
CREATE_RESPONSE=$(curl -s -X POST "${API_HOST}/api/v1/tenants" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"${EMAIL}\"}")
```

Extract `tenant_id` from the response. If creation fails, show error and stop.

### 3c. Generate API key

```bash
KEY_NAME="claude-code-key-$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
KEY_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "${API_HOST}/api/v1/tenants/${TENANT_ID}/keys" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"${KEY_NAME}\"}")
HTTP_CODE=$(echo "$KEY_RESPONSE" | tail -1)
BODY=$(echo "$KEY_RESPONSE" | sed '$d')
```

- **HTTP 200/201**: Extract `key` from the JSON response — this is the `OKAHU_API_KEY`
- **HTTP 400**: Max 8 keys per tenant — tell user to delete old keys from the Okahu dashboard
- **HTTP 409**: Key name conflict (unlikely with timestamp) — retry with new timestamp
- **Other error**: Show error and stop

**If the API returns 404 on any of these endpoints** (not yet deployed), fall back gracefully:
> "Authenticated with GitHub as **{username}** ({email}).
> API key auto-generation not yet available for {env}.
> Get your API key from the Okahu dashboard and add to `.env`:
> `export OKAHU_API_KEY=okh_...`"

Then skip to Step 4 to save what we have (without the API key).

## Step 4: Save credentials

Update `.env` with the resolved environment settings:

1. Read existing `.env`
2. Update or add these lines (preserving other content):
   - `OKAHU_API_KEY={value}` (if obtained from exchange)
   - `OKAHU_INGESTION_ENDPOINT={endpoint for env}`
3. Write back

Save auth metadata to `.claude/state/okahu_auth.json`:

```json
{
  "environment": "stage",
  "github_username": "{username}",
  "github_email": "{email}",
  "tenant_id": "{tenant_id}",
  "api_key_name": "claude-code-key-{timestamp}",
  "authenticated_at": "2026-04-30T12:00:00Z",
  "method": "device_flow",
  "client_id": "Ov23liSuSur0n7NZwn78"
}
```

Print success summary:

```
Authenticated as {username} ({email})
Environment: stage
```

## Error Handling

- All errors are non-fatal — print a clear message and stop
- Never expose full tokens in output (show first 8 chars + `...`)
- If browser fails to open, print the URL so user can copy/paste
- If device code expires, tell user to run `/ok-login` again
