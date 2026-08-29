# Daytona API Investigation for HackOrak

> **SDK Version:** 0.207.0 (Python `daytona-sdk`)  
> **Date:** 2026-08-29  
> **Note:** The `daytona_sdk` package is deprecated; future code should `import daytona` after `pip install daytona`.

## 1. Sandbox Creation Endpoints

The Python SDK provides **two** parameter classes for creating sandboxes:

### `CreateSandboxFromImageParams` — Docker image-based creation

```python
from daytona_sdk import CreateSandboxFromImageParams, CodeLanguage

params = CreateSandboxFromImageParams(
    name="my-sandbox",                  # Optional: sandbox name
    image="python:3.10",                # Required: Docker image
    language=CodeLanguage.PYTHON,       # Optional: default language
    env_vars={"KEY": "value"},          # Optional: environment variables
    labels={"project": "hackorak"},     # Optional: labels for filtering
    domain_allow_list="openrouter.ai",   # CRITICAL: egress domain filter
    auto_stop_interval=3600,            # Optional: auto-stop after inactivity (secs)
    ephemeral=True,                     # Optional: auto-delete after stop
    resources=Resources(cpu=2, memory=4, disk=10),  # Optional
)
```

### `CreateSandboxFromSnapshotParams` — Snapshot-based creation

```python
from daytona_sdk import CreateSandboxFromSnapshotParams

params = CreateSandboxFromSnapshotParams(
    snapshot="my-snapshot",             # Optional: snapshot name/ID
    # ... same base fields as above
)
```

### `CreateSandboxBaseParams` — All common fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str \| None` | `None` | Sandbox name |
| `language` | `CodeLanguage \| None` | `None` | `python`, `typescript`, `javascript` |
| `os_user` | `str \| None` | `None` | OS user for the sandbox |
| `env_vars` | `dict[str,str] \| None` | `None` | Environment variables |
| `labels` | `dict[str,str] \| None` | `None` | Labels for filtering |
| `public` | `bool \| None` | `None` | Make sandbox public |
| `auto_stop_interval` | `int \| None` | `None` | Auto-stop after N seconds |
| `auto_pause_interval` | `int \| None` | `None` | Auto-pause after N seconds |
| `auto_archive_interval` | `int \| None` | `None` | Auto-archive after N seconds |
| `auto_delete_interval` | `int \| None` | `None` | Auto-delete after N seconds |
| `ttl_minutes` | `int \| None` | `None` | Time-to-live in minutes |
| `volumes` | `list[VolumeMount] \| None` | `None` | Volume mounts |
| `secrets` | `dict[str,str] \| None` | `None` | Secrets |
| `network_block_all` | `bool \| None` | `None` | Block all outbound traffic |
| `network_allow_list` | `str \| None` | `None` | **DOES NOT WORK for sandbox-to-sandbox** |
| `domain_allow_list` | `str \| None` | `None` | **Comma-separated domain patterns (supports `*` wildcard)** |
| `outbound_proxy_url` | `str \| None` | `None` | Outbound proxy URL |
| `otel_endpoint_override` | `str \| None` | `None` | OpenTelemetry endpoint |
| `ephemeral` | `bool \| None` | `None` | Auto-delete after stop |
| `spot` | `bool \| None` | `None` | Use spot instances |
| `linked_sandbox` | `str \| None` | `None` | Link to another sandbox |

## 2. Domain Allow List: Complete Reference

### Syntax
The `domain_allow_list` field is a **comma-separated string** of domain patterns:

```python
# Single domain
domain_allow_list = "openrouter.ai"

# Multiple domains
domain_allow_list = "openrouter.ai,api.openrouter.ai,*.daytonaproxy01.eu"

# Wildcard subdomain
domain_allow_list = "*.example.com"  # matches foo.example.com, bar.example.com
```

### How It Works
- Acts as an **egress filter** on the sandbox network
- Only outbound traffic to **matching domains** is allowed
- All other outbound traffic is **blocked**
- Can be updated post-creation via `sandbox.update_network_settings(domain_allow_list="...")`
- **`network_allow_list` does NOT work for sandbox-to-sandbox communication** — use `domain_allow_list` + preview URLs

### Important Limitation
The `network_allow_list` is intended for IP/CIDR allowlisting but **does not work for inter-sandbox communication** because sandbox private IPs (172.20.x.x) are blocked at a lower level.

## 3. Sandbox-to-Sandbox Networking (Verified Recipe)

### The Verified Pattern

```python
# Step 1: Create server sandbox (no special networking)
server = daytona.create(CreateSandboxFromImageParams(
    name="game-server",
    image="python:3.10",
    target="eu"
))
# Start server on port 8080
server.process.exec("python -m http.server 8080 &")
# Get preview URL + token
preview = server.get_preview_link(8080)
# preview.url   = "https://sandbox-abc123.daytonaproxy01.eu:8080"
# preview.token = "dtn_preview_..."

# Step 2: Parse the hostname
from urllib.parse import urlparse
hostname = urlparse(preview.url).hostname
# hostname = "sandbox-abc123.daytonaproxy01.eu"
domain_pattern = "*." + ".".join(hostname.split(".")[-3:])
# domain_pattern = "*.daytonaproxy01.eu"

# Step 3: Create caller sandbox with domain_allow_list
worker = daytona.create(CreateSandboxFromImageParams(
    name="worker-1",
    image="python:3.10",
    target="eu",
    domain_allow_list=f"{domain_pattern},openrouter.ai"  # CRITICAL
))

# Step 4: Call from worker to server
worker.process.exec(
    f'curl -H "x-daytona-preview-token: {preview.token}" {preview.url}'
)
```

### Key Gotchas
1. **`DAYTONA_TARGET` must match**: If server is in `eu`, worker must also be in `eu`, and `DAYTONA_TARGET=eu`
2. **Token is a bearer secret**: Anyone with the token can reach the port from anywhere
3. **Private IPs blocked**: `172.20.x.x` addresses are blocked — only preview URLs work
4. **Parse hostname dynamically**: Don't hardcode `*.daytonaproxy01.eu` — parse from server's preview URL in case region differs

## 4. Sandbox API Methods (Key Operations)

### Daytona Client Methods

```python
daytona = Daytona(config)

# Create
sandbox = daytona.create(params, timeout=60)

# List (returns iterator)
for sb in daytona.list():
    print(sb.name, sb.state)

# Get by ID or name
sb = daytona.get("sandbox-id-or-name")

# Remove
daytona.delete("sandbox-id", timeout=60)
```

### Sandbox Instance Methods

```python
# Process execution
result = sandbox.process.exec("ls -la")
print(result.exit_code, result.result)

# Session execution (stateful, multi-command)
sandbox.process.create_session("my-session")
session_req = SessionExecuteRequest(command="cd /workspace && python server.py")
result = sandbox.process.execute_session_command("my-session", session_req)

# Git operations
sandbox.git.clone("https://github.com/user/repo.git", "/workspace", branch="main")
sandbox.git.configure_user("name", "email")

# File operations
sandbox.fs.upload_file("/local/path/file.py", "/workspace/file.py")
sandbox.fs.download_file("/workspace/output.txt")
sandbox.fs.create_folder("/workspace/data")

# Networking
preview = sandbox.get_preview_link(8080)
sandbox.update_network_settings(domain_allow_list="newdomain.com")

# Lifecycle
sandbox.start()     # Start stopped sandbox
sandbox.stop()      # Stop running sandbox
sandbox.delete()    # Delete sandbox
sandbox.pause()     # Pause sandbox
sandbox.set_autostop_interval(3600)  # Auto-stop after 1hr
```

## 5. Preview URL System

### `get_preview_link(port: int) -> PortPreviewUrl`

```python
class PortPreviewUrl:
    sandbox_id: str   # e.g., "sandbox-abc123"
    url: str          # e.g., "https://sandbox-abc123.daytonaproxy01.eu:8080"
    token: str        # Bearer token for auth
```

### Usage Pattern
```python
# Get preview for an HTTP server running on port 3000
preview = sandbox.get_preview_link(3000)
# Access at: preview.url + header "x-daytona-preview-token: preview.token"
```

### Security Model
- For **private sandboxes**, the token is required for access
- For **public sandboxes**, the URL is accessible without the token
- The token is a **bearer secret** — protect it accordingly

## 6. Environment & Configuration

### DaytonaConfig

```python
config = DaytonaConfig(
    api_key="dtn_...",          # API key (or DAYTONA_API_KEY env)
    api_url="https://...",      # API URL (or DAYTONA_API_URL env)
    target="eu",                # Region: "us" or "eu" (or DAYTONA_TARGET env)
    organization_id="...",      # Org ID (or DAYTONA_ORGANIZATION_ID env)
)
```

### Environment Variables
| Variable | Purpose | Required |
|----------|---------|----------|
| `DAYTONA_API_KEY` | API key for authentication | Yes* |
| `DAYTONA_API_URL` | API endpoint URL | No (defaults to `https://app.daytona.io/api`) |
| `DAYTONA_TARGET` | Target region (`us` or `eu`) | No (uses org default) |
| `DAYTONA_JWT_TOKEN` | JWT alternative to API key | Alternative |
| `DAYTONA_ORGANIZATION_ID` | Organization ID (needed with JWT) | With JWT only |

\* Either API key or JWT + org ID is required.

## 7. Error Handling

The SDK provides typed exceptions:

```python
from daytona_sdk import (
    DaytonaError,
    DaytonaAuthenticationError,
    DaytonaNotFoundError,
    DaytonaTimeoutError,
    DaytonaRateLimitError,
    DaytonaConnectionError,
    DaytonaValidationError,
    DaytonaConflictError,
    # ... more
)

try:
    sandbox = daytona.create(params)
except DaytonaRateLimitError:
    # Wait and retry
except DaytonaTimeoutError:
    # Handle timeout
except DaytonaError as e:
    # General error
```

## 8. Quick Start Template

```python
#!/usr/bin/env python3
"""Minimal Daytona sandbox creation with domain_allow_list."""

import os
from daytona_sdk import Daytona, DaytonaConfig, CreateSandboxFromImageParams

def main():
    config = DaytonaConfig(
        api_key=os.environ["DAYTONA_API_KEY"],
        target="eu"
    )
    daytona = Daytona(config)
    
    # Create sandbox with domain allow list
    params = CreateSandboxFromImageParams(
        name="hackorak-test",
        image="python:3.10",
        domain_allow_list="openrouter.ai,*.daytonaproxy01.eu",
        auto_stop_interval=3600,
        ephemeral=True,
    )
    
    sandbox = daytona.create(params, timeout=120)
    print(f"Created sandbox: {sandbox.id}")
    
    # Run a command
    result = sandbox.process.exec("python --version")
    print(f"Python: {result.result}")
    
    # Get preview link for port 8080
    preview = sandbox.get_preview_link(8080)
    print(f"Preview URL: {preview.url}")
    print(f"Token: {preview.token}")
    
    # Cleanup
    sandbox.delete()
    print("Deleted sandbox")

if __name__ == "__main__":
    main()
```