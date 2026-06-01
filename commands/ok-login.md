---
name: ok:login
description: Authenticate with Okahu Cloud via Auth0 + GitHub
argument-hint: [--force] [stage|prod]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# /ok-login [--force] [stage|prod]

Authenticate with Okahu Cloud using Auth0 Authorization Code + PKCE flow. Opens browser to Auth0 login (forced to GitHub via `connection=github`). A localhost HTTP server catches the redirect. Same flow as the Okahu VS Code extension.

## Argument Parsing

Parse `$ARGUMENTS` for:
- `--force` — skip the "already authenticated" check, go straight to auth flow
- `stage` or `prod` — explicit environment selection

Examples: `/ok-login stage`, `/ok-login --force prod`, `/ok-login --force`, `/ok-login`

## Environment Configuration

| Env | API host | MGMT host (tenant creation only) | Ingestion endpoint | SRE Agent URL |
|-----|----------|----------------------------------|-------------------|---------------|
| **stage** | `api-stage.okahu.co` | `provisioning-stage.okahu.co` | `https://ingest-stage.okahu.co/api/v1/trace/ingest` | `https://sre-agent-stage.okahu.co/api/v1/ask_agent` |
| **prod** | `api.okahu.co` | `management.okahu.co` | `https://ingest.okahu.co/api/v1/trace/ingest` | `https://sre-agent.okahu.co/api/v1/ask_agent` |

## Auth0 Configuration (hardcoded — public PKCE client, not secrets)

- `AUTH0_DOMAIN` = `dev-x8tv172wqki41sla.us.auth0.com`
- `AUTH0_CLIENT_ID` = `mxQbS6NjgsFOPMPLZgT7nj2BZki1eGnF`
- `AUTH0_API_AUDIENCE` = `https://api.stage.okahu.ai/`

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

## Step 2: Auth0 Authorization Code + PKCE Flow

Use the hardcoded Auth0 values from the configuration above. Do NOT read them from `.env`.

### 2a. Start localhost callback server and open browser

Run a single Python script that:
1. Generates PKCE `code_verifier` (32 random bytes, base64url) and `code_challenge` (SHA256 of verifier, base64url)
2. Generates random `state` (16 random bytes, base64url)
3. Starts an HTTP server on `localhost:18292` (fixed port — registered in Auth0 allowed callbacks)
4. Builds the Auth0 authorize URL with these params:
   - `response_type=code`
   - `client_id={AUTH0_LOGIN_APP_CLIENTID}`
   - `redirect_uri=http://localhost:18292/callback`
   - `scope=openid profile email offline_access`
   - `state={STATE}`
   - `code_challenge={CODE_CHALLENGE}`
   - `code_challenge_method=S256`
   - `audience={AUTH0_API_AUDIENCE}`
   - `connection=github` ← forces GitHub as auth provider
5. Opens the browser to the authorize URL
6. Waits for a single request to `/callback`
7. Validates `state`, extracts `code`
8. Exchanges the code for tokens via `POST https://{AUTH0_DOMAIN}/oauth/token`:
   ```json
   {
     "grant_type": "authorization_code",
     "client_id": "{AUTH0_LOGIN_APP_CLIENTID}",
     "code": "{CODE}",
     "redirect_uri": "http://localhost:18292/callback",
     "code_verifier": "{CODE_VERIFIER}"
   }
   ```
   Note: No `client_secret` needed — this is a public/native client using PKCE.
9. Returns JSON to stdout: `{"access_token": "eyJ...", "id_token": "eyJ...", "refresh_token": "..."}`
10. Shows a success page in the browser: "Authentication successful! You can close this tab."

**CRITICAL**: Output the login prompt as **direct text** before running the script:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Okahu Cloud — GitHub Authentication

  Opening browser for Auth0 login...
  (Uses GitHub as auth provider)

  Waiting for authorization...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Here is the Python script to run via Bash. Pass Auth0 vars as environment:

```bash
python3 -c '
import hashlib, base64, os, json, sys, webbrowser, urllib.request, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

domain = "dev-x8tv172wqki41sla.us.auth0.com"
client_id = "mxQbS6NjgsFOPMPLZgT7nj2BZki1eGnF"
audience = "https://api.stage.okahu.ai/"

verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()

result = {}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        nonlocal result
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if params.get("state", [None])[0] != state:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"State mismatch")
            result = {"error": "state_mismatch"}
            return
        if "error" in params:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(params["error_description"][0].encode() if "error_description" in params else b"Auth error")
            result = {"error": params["error"][0], "error_description": params.get("error_description", [""])[0]}
            return
        code = params.get("code", [None])[0]
        if not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code received")
            result = {"error": "no_code"}
            return

        token_data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }).encode()
        req = urllib.request.Request(
            f"https://{domain}/oauth/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            resp = urllib.request.urlopen(req)
            result = json.loads(resp.read())
        except Exception as e:
            result = {"error": "token_exchange_failed", "error_description": str(e)}

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if "error" in result:
            self.wfile.write(b"<h2>Authentication failed</h2><p>Check the terminal for details.</p>")
        else:
            self.wfile.write(b"<h2>Authentication successful!</h2><p>You can close this tab.</p>")

    def log_message(self, *args):
        pass

server = HTTPServer(("localhost", 18292), Handler)
redirect_uri = "http://localhost:18292/callback"

params = urllib.parse.urlencode({
    "response_type": "code",
    "client_id": client_id,
    "redirect_uri": redirect_uri,
    "scope": "openid profile email offline_access",
    "state": state,
    "code_challenge": challenge,
    "code_challenge_method": "S256",
    "audience": audience,
    "connection": "github",
})
auth_url = f"https://{domain}/authorize?{params}"

webbrowser.open(auth_url)
server.handle_request()
server.server_close()
print(json.dumps(result))
'
```

Parse the JSON output. If it contains `"error"`, show the error and stop. Otherwise extract `access_token`, `id_token`, and optionally `refresh_token`.

### 2b. Extract user info from JWT

Decode the `id_token` payload (or fall back to `access_token`) to get user claims:

```bash
echo "$ID_TOKEN" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null
```

Extract:
- `email` — user's email
- `name` or `nickname` — display name  
- `sub` — Auth0 user ID (e.g. `github|12345`)

If `id_token` is missing, call the Auth0 userinfo endpoint:
```bash
curl -s "https://${AUTH0_DOMAIN}/userinfo" -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

## Step 3: Resolve tenant and generate API key

Use the Auth0 JWT (`access_token`) as a Bearer token. The VS Code extension uses:
- `API_HOST` for tenant fetch and key generation
- `MGMT_HOST` for tenant creation (new users only)

### 3a. Fetch tenant info

```bash
TENANT_RESPONSE=$(curl -s -w "\n%{http_code}" \
  "https://${API_HOST}/api/v1/tenant" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json")
HTTP_CODE=$(echo "$TENANT_RESPONSE" | tail -1)
BODY=$(echo "$TENANT_RESPONSE" | sed '$d')
```

- **HTTP 200**: Extract `tenant_id` from JSON response (check fields: `tenant_id`, `id`, or `tenantId`)
- **MISSING_TENANT_CLAIM error or 404**: New user — proceed to Step 3b to create tenant
- **Other error**: Show error and stop

### 3b. Create tenant (new users only)

**Note**: Tenant creation uses `MGMT_HOST`, not `API_HOST` (matches VS Code extension `createTenantWithAccessToken`).

```bash
CREATE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "https://${MGMT_HOST}/api/v1/tenant" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"display_name\": \"${EMAIL}\", \"provisioning_source\": \"Claude Code CLI\"}")
HTTP_CODE=$(echo "$CREATE_RESPONSE" | tail -1)
BODY=$(echo "$CREATE_RESPONSE" | sed '$d')
```

Extract `tenant_id` from the response. If creation fails, show error and stop.

After tenant creation, the access token may need refreshing (it won't have the tenant claim yet). If a `refresh_token` was obtained in Step 2, refresh now:

```bash
REFRESH_RESPONSE=$(curl -s -X POST "https://${AUTH0_DOMAIN}/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token&client_id=${AUTH0_LOGIN_APP_CLIENTID}&refresh_token=${REFRESH_TOKEN}")
```

Extract the new `access_token` from the response and use it for Step 3c.

### 3c. Generate API key

```bash
KEY_NAME="claude-code-key-$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
KEY_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "https://${API_HOST}/api/v1/tenants/${TENANT_ID}/keys" \
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
> "Authenticated as **{name}** ({email}).
> API key auto-generation not yet available for {env}.
> Get your API key from the Okahu dashboard and add to `.env`:
> `export OKAHU_API_KEY=okh_...`"

Then skip to Step 4 to save what we have (without the API key).

## Step 4: Save credentials

### 4a. Back up existing API key

Before overwriting `OKAHU_API_KEY` in `.env`, check if one already exists. If it does, comment it out with a timestamp so the user can recover it:

```
# Backed up by /ok-login on 2026-05-21T10:30:00Z
# export OKAHU_API_KEY="okh_TvXJNYyn_PLj0x0qXRcyafFXRydgA"
export OKAHU_API_KEY="okh_newkey..."
```

Similarly for `OKAHU_INGESTION_ENDPOINT` if it changes.

### 4b. Update .env

1. Read existing `.env`
2. For each key being updated (`OKAHU_API_KEY`, `OKAHU_INGESTION_ENDPOINT`):
   - If the line exists and the value is **different**: comment out the old line with backup header, add new line below
   - If the line exists and the value is the **same**: leave unchanged
   - If the line does not exist: append it
3. Write back (preserving all other content)

### 4c. Save auth metadata

Save to `.claude/state/okahu_auth.json`:

```json
{
  "environment": "stage",
  "auth0_sub": "github|12345",
  "email": "hoc@okahu.ai",
  "name": "hocokahu",
  "tenant_id": "{tenant_id}",
  "api_key_name": "claude-code-key-{timestamp}",
  "authenticated_at": "2026-05-21T10:30:00Z",
  "method": "auth0_pkce"
}
```

Print success summary:

```
Authenticated as {name} ({email})
Environment: {env}
Tenant: {tenant_id}
API key saved to .env (previous key backed up)
```

## Error Handling

- All errors are non-fatal — print a clear message and stop
- Never expose full tokens in output (show first 8 chars + `...`)
- If browser fails to open, print the URL so user can copy/paste
- The localhost server has a 120-second timeout — if no callback received, stop with "Authentication timed out"
