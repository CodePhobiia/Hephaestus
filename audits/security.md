# Hephaestus Security Audit Report

**Date:** 2026-04-03  
**Auditor:** Automated Security Subagent (Butters)  
**Scope:** `src/hephaestus/`, `web/`, `scripts/`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `.env.docker`, `.gitignore`

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 5 |
| MEDIUM   | 7 |
| LOW      | 6 |
| INFO     | 5 |

No hardcoded live API keys were found in source code or git history (within the hephaestus-specific files). The codebase is generally well-structured. The most significant risks are in the web server configuration and subprocess usage.

---

## HIGH Severity

---

### HIGH-1 — Wildcard CORS in Production Web Server

**File:** `web/app.py`, line 56  
**Code:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Risk:** `allow_origins=["*"]` combined with `allow_credentials=True` is a dangerous combination. CORS with wildcard origin + credentials effectively allows any website to make authenticated requests to this API on behalf of a logged-in user. While browsers block this in practice (they reject `allow_credentials=True` with wildcard origin), this config is still a misconfiguration that could confuse security scanners and future maintainers.

Also, the `/api/invent` endpoint streams SSE responses that include full pipeline results. Any domain can trigger expensive LLM calls against the server's API keys.

**Fix:**
```python
ALLOWED_ORIGINS = os.environ.get("HEPH_ALLOWED_ORIGINS", "http://localhost:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # Only set True if you need cookies/auth
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

---

### HIGH-2 — No Rate Limiting on LLM Pipeline Endpoint

**File:** `web/app.py`, line 192+ (`/api/invent` endpoint)  
**Code:**
```python
@app.post("/api/invent", tags=["invention"])
async def invent_stream_endpoint(request_body: InventRequest) -> StreamingResponse:
    # ... calls genesis.invent_stream() which makes many LLM API calls
```

**Risk:** The `/api/invent` endpoint has no rate limiting, authentication, or API key validation. Any actor with network access to the server can trigger unlimited LLM API calls (at the operator's expense). A single automated attacker could exhaust Anthropic/OpenAI API budgets quickly. This is especially dangerous if combined with the open CORS policy (HIGH-1).

**Fix:** Add rate limiting (e.g., `slowapi` for FastAPI):
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/invent")
@limiter.limit("5/minute")  # Adjust as needed
async def invent_stream_endpoint(request: Request, request_body: InventRequest):
    ...
```

Or add a `HEPH_API_KEY` environment variable and require it as a Bearer token.

---

### HIGH-3 — OAT Token Prefix Leaked in Error Message

**File:** `src/hephaestus/deepforge/adapters/claude_max.py`, line 138  
**Code:**
```python
raise AuthenticationError(
    f"Token doesn't look like an OAT token (expected sk-ant-oat prefix): {token[:20]}..."
)
```

**Risk:** If the loaded token is a different credential (not an OAT token), its first 20 characters are included in the error message. Depending on how errors are surfaced (logs, API responses, monitoring), this could leak the beginning of a credential string. Even a 20-character prefix can sometimes be used to identify token ownership or narrow brute-force attacks.

**Fix:**
```python
raise AuthenticationError(
    "Token doesn't look like an OAT token (expected sk-ant-oat prefix). "
    "Check your auth-profiles.json."
)
```

---

### HIGH-4 — `.env.docker` Tracked in Git (Secrets File Template Exposure)

**File:** `.env.docker` (tracked in git)  
**Code:**
```
# Docker env file — copy and fill in your keys
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
```

**Risk:** `.env.docker` is tracked in git (verified via `git ls-files`). While the values are currently empty, this file is the template users are expected to fill in and potentially commit. If a user fills in real keys and commits the file (or if the CI/CD pipeline ever injects real keys here), secrets would be exposed in git history.

The `.gitignore` does NOT include `.env.docker` — only `.hephaestus/local.yaml` and session files are excluded.

**Fix:** Add `.env.docker` to `.gitignore` and rename the template:
```bash
# .gitignore additions:
.env.docker
.env
.env.*
!.env.docker.example
```

Rename `.env.docker` → `.env.docker.example` (tracking the example is fine).

---

### HIGH-5 — `read_file` Tool Has No Path Traversal Protection

**File:** `src/hephaestus/tools/file_ops.py`, line 8–19  
**Code:**
```python
def read_file(path: str, max_chars: int = 20_000) -> str:
    """Read a file and return its contents (truncated to *max_chars*)."""
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: path does not exist: {p}"
    if p.is_dir():
        return f"Error: path is a directory, use list_directory instead: {p}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
```

**Risk:** `read_file` resolves the path but performs no bounds check against a workspace root. When this tool is called by an LLM agent (via the tools registry), a prompt injection or misbehaving LLM could pass `../../../etc/passwd` or `/home/ubuntu/.openclaw/agents/main/agent/auth-profiles.json` as the path. This reads any file the process has access to.

Note: `write_file` correctly validates against `workspace_root`, but `read_file` does not.

**Fix:**
```python
def read_file(path: str, max_chars: int = 20_000, workspace_root: str | Path | None = None) -> str:
    p = Path(path).resolve()
    if workspace_root is not None:
        root = Path(workspace_root).resolve()
        try:
            p.relative_to(root)
        except ValueError:
            return f"Error: path {p} is outside workspace root {root}"
    ...
```

---

## MEDIUM Severity

---

### MEDIUM-1 — Subprocess Calls Use User-Controlled Working Directory

**File:** `src/hephaestus/workspace/scanner.py`, lines 239–269  
**File:** `src/hephaestus/workspace/repo_dossier.py`, lines 467–511  
**Code:**
```python
info.branch = subprocess.run(
    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
    capture_output=True, text=True, cwd=self.root, timeout=5,
).stdout.strip()
```

**Risk:** `self.root` is taken from user-controlled input (the workspace path passed to `WorkspaceScanner`). While the command itself is a static list (no shell injection), `cwd=self.root` means git operations run in whatever directory the user specifies. If the directory contains a malicious `.git` config (e.g., `core.fsmonitor`), it could trigger arbitrary code execution via git hooks.

This is low-exploitability in most deployment contexts but is a real supply-chain/LFI concern when Hephaestus is used as a coding assistant pointed at untrusted repos.

**Fix:** Validate that `self.root` is within allowed boundaries before passing it to subprocess. Consider adding `--no-config` or disabling hooks:
```python
subprocess.run(
    ["git", "-c", "core.fsmonitor=", "--no-optional-locks", "rev-parse", "--abbrev-ref", "HEAD"],
    capture_output=True, text=True, cwd=self.root, timeout=5,
)
```

---

### MEDIUM-2 — Claude CLI Called with `--permission-mode bypassPermissions`

**File:** `src/hephaestus/deepforge/adapters/claude_cli.py`, lines 148–155  
**Code:**
```python
cmd = [
    self._claude_bin,
    "--print",
    "--permission-mode", "bypassPermissions",
    "-p",
    full_prompt,
]
```

**Risk:** `--permission-mode bypassPermissions` tells Claude Code to execute any tool or file operation without asking for confirmation. This is passed on every call. If a prompt injection attack causes the underlying Claude Code CLI to execute a shell command or write a file, it will do so without any safety checks.

**Fix:** Remove `--permission-mode bypassPermissions` or replace with a more restrictive mode:
```python
cmd = [
    self._claude_bin,
    "--print",
    "--permission-mode", "readonly",  # or remove entirely
    "-p",
    full_prompt,
]
```

---

### MEDIUM-3 — Codex CLI Adapter Reads OAuth Auth File Without Validation

**File:** `src/hephaestus/deepforge/adapters/codex_cli.py`, lines 60–69  
**Code:**
```python
def _detect_codex_auth() -> bool:
    auth = Path.home() / ".codex" / "auth.json"
    if not auth.exists():
        return False
    try:
        data = json.loads(auth.read_text())
        return data.get("auth_mode") == "chatgpt" and bool(data.get("tokens", {}).get("id_token"))
    except Exception:
        return False
```

**Risk:** `auth.json` is read from a fixed world-readable path. The `id_token` (JWT) is not validated (no signature verification, no expiry check). An attacker who can write to `~/.codex/auth.json` can inject a crafted token. More importantly, if the token has expired, the adapter will still try to use it (possibly leaking it in an error response).

**Fix:** The `codex_oauth_bridge.mjs` does handle token refresh correctly. The `_detect_codex_auth()` Python check should validate token expiry:
```python
import time, base64, json as _json

def _decode_jwt_exp(token: str) -> float:
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        data = _json.loads(base64.urlsafe_b64decode(padded))
        return float(data.get("exp", 0))
    except Exception:
        return 0.0

def _detect_codex_auth() -> bool:
    ...
    exp = _decode_jwt_exp(data.get("tokens", {}).get("id_token", ""))
    if exp and time.time() > exp:
        return False  # Expired
    return True
```

---

### MEDIUM-4 — Dependency Versions Are Loose Ranges (No Lock File)

**File:** `pyproject.toml`, lines 20–30  
**Code:**
```toml
dependencies = [
    "anthropic>=0.40.0",
    "openai>=1.50.0",
    "click>=8.1.0",
    ...
]
```

**Risk:** All dependencies use `>=` (minimum version) with no upper bounds and no lock file (`requirements.txt` with pinned hashes). This means a `pip install` resolves to the latest available version, which could include a newly released version with a breaking change or a compromised package (supply chain attack). There is no reproducible build.

**Fix:** Generate a pinned requirements file:
```bash
pip-compile pyproject.toml --generate-hashes -o requirements.lock
```

Then use in Docker:
```dockerfile
COPY requirements.lock .
RUN pip install --require-hashes -r requirements.lock
```

---

### MEDIUM-5 — YAML Config Loaded with `yaml.safe_load` but Config Values Not Sanitized Before Use in System Calls

**File:** `src/hephaestus/config/layered.py`, lines 161–172  
**Code:**
```python
with open(path) as f:
    data = yaml.safe_load(f)
...
for key, value in data.items():
    if key in valid_fields:
        merged[key] = value
```

**Risk:** `yaml.safe_load` is correctly used (not `yaml.load`). However, config values like `backend`, `default_model`, `pantheon_athena_model` are strings loaded from user-controlled config files and used to select CLI backends, model names passed to external APIs, and subprocess paths. While downstream validation exists for some fields (e.g., `backend` is checked against `VALID_BACKENDS`), model name strings and some others are passed through without sanitization. A malicious config could inject model names with special characters that could cause issues with API calls.

**Fix:** Already has some validation (`_VALIDATORS`). Extend to model name fields:
```python
MODEL_NAME_RE = re.compile(r'^[a-zA-Z0-9._/:@-]{1,200}$')

def _validate_model_name(value: str, field: str) -> str:
    if not MODEL_NAME_RE.match(value):
        raise ConfigValidationError(f"Invalid model name for {field}: {value!r}")
    return value
```

---

### MEDIUM-6 — Web App SPA Catch-All Route Could Serve Sensitive Templates

**File:** `web/app.py`, lines 265–275  
**Code:**
```python
@app.get("/{path:path}", include_in_schema=False)
async def catch_all(path: str) -> HTMLResponse:
    """SPA catch-all — always serve index.html for unknown paths."""
    index_path = _TEMPLATES / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="Not found")
```

**Risk:** This catch-all matches any path, including paths like `/api/...` variants that might be added later. More importantly, if the template directory ever contains additional files (e.g., deployment configs, debug templates), they would not be served (since only `index.html` is served) but the catch-all might mask 404 responses that are useful for debugging security issues.

**Fix:** This is acceptable for an SPA pattern, but add a path check to exclude `api/` prefixes explicitly:
```python
@app.get("/{path:path}", include_in_schema=False)
async def catch_all(path: str) -> HTMLResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    ...
```

---

### MEDIUM-7 — Prompt Injection Weak Detection in Input Validation

**File:** `src/hephaestus/core/input_validation.py`, lines 22–28  
**Code:**
```python
_SUSPICIOUS_PATTERNS = [
    (r"<script", "Input contains HTML script tags"),
    (r"(?i)ignore\s+(?:previous|above|all)\s+instructions", "Input looks like a prompt injection"),
    (r"\{\{.*\}\}", "Input contains template variables"),
]
```

**Risk:** The prompt injection detection is only a warning (not a rejection) and is extremely limited. It only catches the most obvious "ignore previous instructions" pattern. Real prompt injection attacks use far more sophisticated phrasing. These inputs are sent directly to LLMs as problem descriptions, and through prefill mechanisms, could potentially influence the model's behavior in unintended ways.

**Fix:** The detection is better than nothing. Consider:
1. Increasing severity to a hard `errors.append(...)` for clear injection patterns (not just warning)
2. Adding more patterns: `"jailbreak"`, `"DAN"`, `"act as"`, `"you are now"`, etc.
3. Document that this is defense-in-depth only — the real defense is the LLM's own safety training.

---

## LOW Severity

---

### LOW-1 — Docker Container Runs as Non-Root (Good) but Dockerfile Image Copies Sensitive Structure

**File:** `Dockerfile`, lines 11–27  
**Code:**
```dockerfile
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY web/ ./web/
```

**Risk:** The non-root user (`heph`) is correctly configured — good hardening. However, if additional files are inadvertently added to the build context (e.g., `.env.docker` with real keys, `local.yaml`), they would be included in the image layer and accessible to anyone with image access. There is no `.dockerignore` file.

**Fix:** Add a `.dockerignore`:
```
.env.docker
.hephaestus/local.yaml
.venv/
.git/
*.pyc
__pycache__/
tests/
```

---

### LOW-2 — Error Messages May Leak Internal Paths and Stack Traces

**File:** `web/app.py`, lines 237–244  
**Code:**
```python
except Exception as exc:
    logger.exception("Unexpected error in invention stream")
    yield _sse_error(f"Server error: {exc}")
```

**Risk:** `str(exc)` on most Python exceptions includes the exception type and message, which often contains internal file paths, variable values, or other internal state. This is sent directly to the SSE client.

**Fix:**
```python
except Exception as exc:
    logger.exception("Unexpected error in invention stream")
    # Don't send internal details to client
    yield _sse_error("An internal server error occurred. Please try again.")
```

---

### LOW-3 — No Request Size Limit on SSE Endpoint

**File:** `web/app.py`, line 112 (InventRequest model)  
**Code:**
```python
class InventRequest(BaseModel):
    problem: str = Field(..., min_length=5, max_length=4000, ...)
    depth: int = Field(default=3, ge=1, le=10, ...)
    candidates: int = Field(default=8, ge=2, le=20, ...)
```

**Risk:** Pydantic validates input fields, which is good. However, `depth=10` and `candidates=20` could trigger extremely expensive LLM pipelines (many parallel calls). At max settings, this could exhaust API rate limits or billing limits quickly from a single request.

**Fix:** Consider tighter defaults for public-facing deployments, or require an API key for high-resource requests:
```python
candidates: int = Field(default=8, ge=2, le=12, ...)  # Cap lower for safety
```

---

### LOW-4 — SSH/Auth File Paths Hardcoded in Multiple Places

**Files:** `src/hephaestus/cli/config.py` line 243, `src/hephaestus/deepforge/adapters/claude_max.py` line 127  
**Code:**
```python
store_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
```

**Risk:** The path to OpenClaw's auth store is hardcoded in multiple places. If the path changes, all hardcoded references break silently. More importantly, reading from `~/.openclaw/agents/main/agent/auth-profiles.json` means Hephaestus always reads the main agent's auth (not a scoped credential). Consider what happens when the auth-profiles file is replaced or corrupted.

**Fix:** Centralize the path into a constant or environment variable:
```python
OPENCLAW_AUTH_PATH = Path(
    os.environ.get("OPENCLAW_AUTH_PROFILES", 
    str(Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"))
)
```

---

### LOW-5 — `proxy.mjs` Loads OAT Token and Logs It (Partial)

**File:** `proxy.mjs`, line 7  
**Code:**
```javascript
const token = store.profiles['anthropic:default'].token;
console.log('[proxy] Loaded token:', token.substring(0, 25) + '...');
```

**Risk:** The proxy script logs the first 25 characters of the OAT token to stdout. While truncated, this appears in process logs and could be captured by log aggregation tools.

**Fix:** Remove the token logging entirely or replace with a non-identifying message:
```javascript
console.log('[proxy] Token loaded successfully');
```

---

### LOW-6 — No `.gitignore` Entry for `.env` Files Beyond the Template

**File:** `.gitignore`  
**Risk:** `.gitignore` does not include `.env`, `.env.local`, or `.env.*` patterns. A developer might create a local `.env` file with real keys and accidentally commit it.

**Fix:** Add to `.gitignore`:
```
.env
.env.*
!.env.docker.example
```

---

## INFO

---

### INFO-1 — TLS/Certificate Validation

All HTTP client code (`httpx`, `anthropic` SDK, `openai` SDK) uses the default SSL configuration, which validates certificates. No `verify=False` or custom SSL contexts were found. **This is correct behavior.**

---

### INFO-2 — No `pickle.loads`, `eval`, or `exec` in Production Code

A full grep of `src/hephaestus/` and `web/` found no usage of `pickle.loads`, `eval()`, or `exec()` in any production code path. **This is correct — no dynamic code execution vulnerabilities found.**

---

### INFO-3 — Git History Clean of Real Secrets

Git history search across hephaestus source files (`src/`, `web/`, `scripts/`) found no hardcoded real API keys, tokens, or passwords. All occurrences of `api_key` patterns are either placeholder strings (e.g., `sk-ant-...`) or environment variable lookups. **No secrets leak in git history.**

---

### INFO-4 — Docker Image Runs as Non-Root User

The `Dockerfile` correctly creates a non-root user `heph` (UID 1000) and switches to it before running the application. **This is a good hardening practice.**

---

### INFO-5 — Dependency Count and Supply Chain Surface

The `.venv` contains a large number of packages including `sentence-transformers`, `transformers`, `torch`, `triton`, and related ML libraries. These are large, complex packages with significant supply-chain surface area. No CVE scanning was performed (would require `pip-audit` or `safety`). Recommend running:
```bash
pip install pip-audit
pip-audit
```
to check for known CVEs in the installed environment. The core web/API deps (anthropic 0.86.0, openai 2.30.0, httpx 0.28.1) are recent versions with no known critical CVEs at time of audit.

---

## Recommendations Priority Matrix

| Priority | Action |
|----------|--------|
| **Immediate** | Add rate limiting to `/api/invent` (HIGH-2) |
| **Immediate** | Fix CORS wildcard + credentials (HIGH-1) |
| **Short-term** | Add workspace root validation to `read_file` (HIGH-5) |
| **Short-term** | Remove token prefix from error messages (HIGH-3) |
| **Short-term** | Add `.env.docker` to `.gitignore` (HIGH-4) |
| **Before prod** | Remove `--permission-mode bypassPermissions` from CLI adapter (MEDIUM-2) |
| **Before prod** | Generate pinned `requirements.lock` (MEDIUM-4) |
| **Before prod** | Add `.dockerignore` (LOW-1) |
| **Ongoing** | Run `pip-audit` after each dependency update (INFO-5) |

---

*Audit completed: 2026-04-03 UTC*
