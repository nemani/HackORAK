# HackOrak Architecture Plan

> **Date:** 2026-08-29  
> **SDK Version:** Daytona Python SDK 0.207.0  
> **Status:** Planning / Pre-implementation

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Component List](#component-list)
4. [Data Flow](#data-flow)
5. [Daytona API Investigation](#daytona-api-investigation)
6. [Networking Recipe: Sandbox-to-Sandbox Communication](#networking-recipe-sandbox-to-sandbox-communication)
7. [Free OpenRouter Models](#free-openrouter-models)
8. [Phased Implementation Plan](#phased-implementation-plan)
9. [Risks & Open Questions](#risks--open-questions)
10. [Appendix: ORAK MCP Server Analysis](#appendix-orak-mcp-server-analysis)

---

## Overview

**HackOrak** is a Python-based system that orchestrates autonomous AI agents competing against each other on ORAK video game benchmarks. It leverages Daytona for sandboxed execution, Pi coding agent with MCP for LLM-powered gameplay, and a live web dashboard for real-time spectating.

### Goals

1. **Game Server Sandbox**: Programmatically create a Daytona sandbox, clone the ORAK repository, and start an MCP game server (e.g., 2048) exposed over HTTP (SSE transport).
2. **Worker Sandboxes**: Create N worker sandboxes, each running a Pi coding agent with `pi-mcp` extension pointed at the game server. Each worker uses a **different free OpenRouter model**.
3. **Live Dashboard**: A single-page web app (HTML/JS) served from one sandbox, showing agents playing in real-time with recent/top scores via SSE polling of game + worker state.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HACKORAK ORCHESTRATOR                               │
│                     (Python script, runs on host or CI)                       │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │ create_game_ │    │ create_work- │    │  poll &      │                   │
│  │ sandbox()    │    │ er_sandboxes │    │  aggregate   │                   │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                   │
│         │                   │                   │                            │
└─────────┼───────────────────┼───────────────────┼────────────────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          DAYTONA (EU Region)                                  │
│                                                                              │
│  ┌───────────────────────────┐                                               │
│  │   GAME SERVER SANDBOX     │                                               │
│  │                           │                                               │
│  │  ┌─────────────────────┐  │                                               │
│  │  │ ORAK MCP Game Svr   │  │   SSE endpoint on port 8080                   │
│  │  │ (2048 / SuperMario) │◄─┼── exposed via Daytona preview proxy           │
│  │  │ FastMCP SSE @ :8080 │  │   URL: https://{id}.daytonaproxy01.eu:8080   │
│  │  └─────────────────────┘  │   Token: {bearer-token}                       │
│  │                           │                                               │
│  │  git clone HackORAK/ORAK  │                                               │
│  │  pip install -r reqs      │                                               │
│  │  python server.py --sse   │                                               │
│  └───────────────────────────┘                                               │
│              ▲                                                                │
│              │ HTTPS + x-daytona-preview-token header                        │
│              │ (domain_allow_list: *.daytonaproxy01.eu)                      │
│     ┌────────┴────────┬──────────────────────────────┐                       │
│     ▼                 ▼                              ▼                       │
│  ┌───────────────┐ ┌───────────────┐        ┌───────────────┐               │
│  │ WORKER #1     │ │ WORKER #2     │  ...   │ WORKER #N     │               │
│  │               │ │               │        │               │               │
│  │ Pi + pi-mcp   │ │ Pi + pi-mcp   │        │ Pi + pi-mcp   │               │
│  │ extension     │ │ extension     │        │ extension     │               │
│  │               │ │               │        │               │               │
│  │ Model:        │ │ Model:        │        │ Model:        │               │
│  │ gemini-2.0    │ │ llama-3.3     │        │ deepseek-r1   │               │
│  │ -flash-001    │ │ -70b-instruct │        │ -distill-qwen │               │
│  │               │ │               │        │               │               │
│  │ domain_allow: │ │ domain_allow: │        │ domain_allow: │               │
│  │ *.daytona-    │ │ *.daytona-    │        │ *.daytona-    │               │
│  │ proxy01.eu +  │ │ proxy01.eu +  │        │ proxy01.eu +  │               │
│  │ openrouter.ai  │ │ openrouter.ai  │        │ openrouter.ai  │               │
│  └───────┬───────┘ └───────┬───────┘        └───────┬───────┘               │
│          │                 │                        │                        │
│          │    POST scores  │   to dashboard        │                        │
│          └─────────────────┼────────────────────────┘                        │
│                            ▼                                                 │
│  ┌──────────────────────────────────────────────┐                            │
│  │   DASHBOARD SANDBOX                          │                            │
│  │                                              │                            │
│  │  ┌────────────────┐   ┌──────────────────┐   │                            │
│  │  │ Flask/FastAPI  │   │ Static HTML/JS   │   │                            │
│  │  │ SSE endpoint   │   │ dashboard UI     │   │                            │
│  │  │ /events        │   │ auto-refresh     │   │                            │
│  │  └────────────────┘   └──────────────────┘   │                            │
│  │                                              │                            │
│  │  Exposed via Daytona preview proxy on :3000  │                            │
│  └──────────────────────────────────────────────┘                            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
          │
          │ Browser / Spectator
          ▼
    ┌─────────────┐
    │  DASHBOARD  │
    │  (any web   │
    │   browser)  │
    └─────────────┘
```

---

## Component List

### 1. Orchestrator (`hackorak/orchestrator.py`)
Python script that executes the entire lifecycle:
- Reads configuration (game, models, worker count)
- Creates game server sandbox
- Creates worker sandboxes
- Creates dashboard sandbox
- Polls for results
- Cleans up sandboxes

**Dependencies:** `daytona-sdk`, `httpx`, `pyyaml`

### 2. Game Server (`scripts/start_game_server.py`)
Modified ORAK game server wrapper:
- Uses `mcp.server.fastmcp.FastMCP` (pinned `mcp<2`) with `run_sse_async(host="0.0.0.0", port=8080)`
- Runs inside the game server sandbox
- Supports configurable game selection (2048 by default)
- Exposes standard MCP tools: `load-obs`, `send-action-set`, `dispatch-final-action`, `get-current-state`

### 3. Worker Agent (`hackorak/worker_config.md`)
Configuration for each Pi worker sandbox:
- Pi coding agent installed via npm
- `pi-mcp` extension configured with SSE URL pointing to game server preview URL
- OpenRouter API key set as environment variable
- Each worker configured with a different model

### 4. Dashboard (`hackorak/dashboard/`)
- **Backend** (`server.py`): Flask/FastAPI server with SSE endpoint (`/events`) and POST endpoint (`/score`) for workers to report scores
- **Frontend** (`static/index.html`): Vanilla HTML/JS with:
  - Real-time game state display (SSE client)
  - Leaderboard with current scores
  - Agent activity log
  - Auto-refresh on game state updates

### 5. Configuration (`hackorak/config.yaml`)
```yaml
daytona:
  target: eu  # or us — match your Daytona region
  api_key: ${DAYTONA_API_KEY}
  api_url: ${DAYTONA_API_URL}  # default: https://app.daytona.io/api

game:
  name: twenty_fourty_eight  # or: super_mario, pokemon_red, etc.
  port: 8080

workers:
  count: 5
  models:
    - google/gemini-2.0-flash-001      # free
    - meta-llama/llama-3.3-70b-instruct # free
    - mistralai/mistral-7b-instruct     # free
    - deepseek/deepseek-r1-distill-qwen-32b  # free
    - qwen/qwen-2.5-7b-instruct        # free

dashboard:
  port: 3000

sandbox:
  auto_stop_interval: 3600  # 1 hour
  image: python:3.10  # matches ORAK requirements
```

---

## Data Flow

### Phase 1: Setup
```
Orchestrator
  │
  ├─[1]─► Daytona.create() ─► Game Server Sandbox
  │         • image="python:3.10"
  │         • target="eu"
  │         • Clone ORAK repo via sandbox.git.clone()
  │         • pip install dependencies
  │         • Start game server (SSE on :8080)
  │         • get_preview_link(8080) → {url, token}
  │
  ├─[2]─► Daytona.create() ─► Dashboard Sandbox
  │         • domain_allow_list = parse host from game server URL
  │         • Copy dashboard files via sandbox.fs.upload_file()
  │         • Start dashboard server on :3000
  │         • get_preview_link(3000) → dashboard URL
  │
  └─[3]─► For each worker model:
            Daytona.create() ─► Worker Sandbox
              • domain_allow_list = "*.daytonaproxy01.eu,openrouter.ai"
              • Install Pi + pi-mcp extension
              • Configure pi-mcp SSE URL = game_server_preview_url
              • Set OPENROUTER_API_KEY, MODEL_NAME env vars
              • POST dashboard URL to worker as DASHBOARD_URL env var
```

### Phase 2: Gameplay Loop
```
Worker Sandbox (Pi agent)
  │
  ├─ MCP SSE connect ─► Game Server Sandbox (:8080)
  │   via Daytona preview proxy + x-daytona-preview-token header
  │
  ├─ Pi uses MCP tools:
  │   • load-obs()      → get game state (text + optional image)
  │   • send-action-set() → queue actions
  │   • dispatch-final-action() → execute + get score
  │
  ├─ Pi calls OpenRouter API with game observations
  │   Returns next action to take
  │
  └─ POST /score ─► Dashboard Sandbox
       {worker_id, model, score, step, game_state, timestamp}
```

### Phase 3: Dashboard Updates
```
Dashboard Frontend (Browser)
  │
  ├─ SSE /events ─► Dashboard Backend
  │   Streams: {event: "score_update", data: {...}}
  │            {event: "game_state", data: {...}}
  │
  └─ Renders:
       • Leaderboard table (sorted by score)
       • Game state visualization
       • Worker activity timeline
```

---

## Daytona API Investigation

### SDK Package & Version

- **Package**: `daytona-sdk` (deprecated) → migrate to `daytona`  
- **Version Investigated**: `0.207.0`  
- **Python**: 3.10+ (ORAK requirement)  
- **Install**: `pip install daytona-sdk` (current) or `pip install daytona` (future)

### Key Classes

#### `Daytona` (Client)
```python
from daytona_sdk import Daytona, DaytonaConfig

config = DaytonaConfig(
    api_key="dtn_...",          # or DAYTONA_API_KEY env var
    api_url="https://app.daytona.io/api",  # or DAYTONA_API_URL
    target="eu"                 # or DAYTONA_TARGET env var
)
daytona = Daytona(config)
```

#### `CreateSandboxFromImageParams`
All fields relevant to our use case:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str \| None` | Sandbox name |
| `language` | `CodeLanguage \| None` | `python`, `typescript`, `javascript` |
| `image` | `str \| Image` | **Required.** Docker image (e.g., `"python:3.10"`) |
| `env_vars` | `dict[str,str] \| None` | Environment variables |
| `domain_allow_list` | `str \| None` | **Critical.** Comma-separated domains the sandbox can reach |
| `network_block_all` | `bool \| None` | Block all outbound traffic (default: False) |
| `network_allow_list` | `str \| None` | **DOES NOT WORK for sandbox-to-sandbox** |
| `auto_stop_interval` | `int \| None` | Auto-stop after N seconds of inactivity |
| `ephemeral` | `bool \| None` | Ephemeral sandbox (auto-deleted after stop) |
| `resources` | `Resources \| None` | CPU/Memory/Disk allocation |

#### `Sandbox` (Instance)
Key methods:

| Method | Signature | Purpose |
|--------|-----------|---------|
| `get_preview_link(port)` | `→ PortPreviewUrl` | Get public URL + token for a port |
| `process.exec(cmd)` | `→ ExecuteResponse` | Run shell command |
| `git.clone(url, path)` | `→ None` | Clone a git repository |
| `fs.upload_file(src, dst)` | `→ None` | Upload a file to sandbox |
| `fs.download_file(path)` | `→ bytes` | Download a file from sandbox |
| `update_network_settings(...)` | `→ None` | Update domain_allow_list post-creation |
| `start() / stop() / delete()` | `→ None` | Lifecycle management |

#### `PortPreviewUrl`
```python
class PortPreviewUrl:
    sandbox_id: str   # e.g., "sandbox-abc123"
    url: str          # e.g., "https://sandbox-abc123.daytonaproxy01.eu:8080"
    token: str        # Bearer token for authentication
```

### Domain Allow List: How It Works

The `domain_allow_list` field accepts a **comma-separated string** of domain patterns:

```python
params = CreateSandboxFromImageParams(
    image="python:3.10",
    domain_allow_list="*.daytonaproxy01.eu,openrouter.ai,api.openrouter.ai"
)
```

- Wildcards (`*`) are supported for subdomain matching
- The sandbox egress filter blocks all outbound traffic NOT matching the allow list
- This is **required** for worker sandboxes to reach:
  - The game server (hosted on `*.daytonaproxy01.eu`)
  - OpenRouter API (`openrouter.ai`)
- Can also be updated post-creation via `sandbox.update_network_settings(domain_allow_list="...")`

---

## Networking Recipe: Sandbox-to-Sandbox Communication

**Verified against Daytona SDK 0.207.0** — this is the working recipe:

### The Problem

Daytona sandboxes **cannot** reach each other on private IPs (`172.20.x.x` addresses are blocked by the egress filter). The `network_allow_list` parameter does **not** work for enabling sandbox-to-sandbox communication.

### The Solution

1. **Server Sandbox** (Game Server): No special networking config needed. Simply call `get_preview_link(8080)` to get a public proxy URL + token.

2. **Caller Sandbox** (Workers & Dashboard): Create with `domain_allow_list` set to the hostname of the server's preview URL:
   ```python
   # After creating game server sandbox
   preview = game_sandbox.get_preview_link(8080)
   # preview.url = "https://sandbox-abc.daytonaproxy01.eu:8080"
   
   # Parse the hostname
   from urllib.parse import urlparse
   hostname = urlparse(preview.url).hostname
   # hostname = "sandbox-abc.daytonaproxy01.eu"
   
   # Use wildcard for robustness (region may vary)
   domain_pattern = "*." + ".".join(hostname.split(".")[-3:])
   # domain_pattern = "*.daytonaproxy01.eu"
   
   worker_params = CreateSandboxFromImageParams(
       image="python:3.10",
       domain_allow_list=f"{domain_pattern},openrouter.ai"
   )
   ```

3. **Request Header**: Workers must include `x-daytona-preview-token: {token}` in all requests to the game server.

4. **Region**: Set `DAYTONA_TARGET=eu` (or the appropriate region). Default is `us`, which will route to the wrong region if your sandboxes are in EU.

5. **Token Security**: The preview token is a bearer secret — anyone with it can reach the port from anywhere. Treat it as sensitive.

### Example Worker-to-Game-Server Request

```python
import httpx

response = httpx.get(
    f"{game_server_url}/sse",
    headers={"x-daytona-preview-token": game_server_token}
)
```

---

## Free OpenRouter Models

The following models are available **for free** on OpenRouter (verified 2026-08):

| # | Model ID | Provider | Context | Notes |
|---|----------|----------|---------|-------|
| 1 | `google/gemini-2.0-flash-001` | Google | 1M | Fast, good general purpose |
| 2 | `meta-llama/llama-3.3-70b-instruct` | Meta | 128K | Strong open model |
| 3 | `mistralai/mistral-7b-instruct` | Mistral | 32K | Lightweight, fast |
| 4 | `deepseek/deepseek-r1-distill-qwen-32b` | DeepSeek | 128K | Reasoning model |
| 5 | `qwen/qwen-2.5-7b-instruct` | Qwen | 128K | Good coding/model |
| 6 | `microsoft/phi-4-mini-instruct` | Microsoft | 128K | Small, efficient |
| 7 | `undi95/toppy-m-7b` | Community | 4K | Creative writing |
| 8 | `nousresearch/deephermes-3-llama-3-8b` | Nous | 128K | Reasoning + chat |

**Recommendation**: Start with models 1–5 for diversity of providers and capabilities.

**Note**: Free models on OpenRouter have rate limits. Check [openrouter.ai/models](https://openrouter.ai/models?max_price=0) for the current list.

---

## Phased Implementation Plan

### Phase 0: Prerequisites & Scaffold (Day 1)

**Files to create:**
```
hackorak/
├── __init__.py
├── config.yaml              # Central configuration
├── orchestrator.py          # Main entry point
├── game_server/
│   ├── __init__.py
│   └── start_server.py      # MCP game server with SSE transport
├── workers/
│   ├── __init__.py
│   └── worker_setup.py      # Pi + pi-mcp configuration
├── dashboard/
│   ├── __init__.py
│   ├── server.py            # Flask/FastAPI backend
│   └── static/
│       └── index.html       # Dashboard frontend
└── requirements.txt
```

**Tasks:**
- [ ] Create project scaffold with `pyproject.toml`
- [ ] Pin dependencies: `daytona-sdk==0.207.0`, `mcp<2`, `httpx`, `pyyaml`
- [ ] Verify Daytona API key and region configuration
- [ ] Test basic sandbox creation/destruction

### Phase 1: Game Server Sandbox (Day 1–2)

**Objective:** Programmatically create a Daytona sandbox that runs the ORAK MCP game server.

**Tasks:**
- [ ] Write `game_server/start_server.py` — wraps ORAK `MCPGameServer` with SSE transport
  - Copy the ORAK game server pattern (`base_server.py` + game-specific `server.py`)
  - Replace `mcp.run_stdio_async()` with `mcp.run_sse_async(host="0.0.0.0", port=8080)`
  - Handle MCP v1 (`fastmcp.FastMCP`) → pin `mcp<2`
- [ ] Implement `orchestrator.create_game_sandbox()`:
  ```python
  def create_game_sandbox(daytona, config) -> tuple[Sandbox, PortPreviewUrl]:
      params = CreateSandboxFromImageParams(
          name="hackorak-game-server",
          image="python:3.10",
          target=config.daytona.target,
          auto_stop_interval=config.sandbox.auto_stop_interval
      )
      sandbox = daytona.create(params)
      sandbox.git.clone("https://github.com/nemani/HackORAK.git", "/workspace")
      sandbox.process.exec("pip install -r requirements/base.txt")
      sandbox.process.exec("pip install mcp<2")
      sandbox.process.exec("python /workspace/hackorak/game_server/start_server.py --game 2048 &")
      preview = sandbox.get_preview_link(8080)
      return sandbox, preview
  ```
- [ ] Test: Verify game server is reachable via preview URL + token
- [ ] Test: Verify MCP tools (`load-obs`, `dispatch-final-action`) work over SSE

### Phase 2: Worker Sandboxes (Day 2–3)

**Objective:** Create N worker sandboxes, each running Pi with pi-mcp extension.

**Tasks:**
- [ ] Determine the domain pattern from game server preview URL
- [ ] Implement `orchestrator.create_worker_sandboxes()`:
  ```python
  def create_worker_sandbox(daytona, config, model, game_server_url, game_server_token, dashboard_url):
      domain = parse_preview_hostname(game_server_url)  # *.daytonaproxy01.eu
      params = CreateSandboxFromImageParams(
          name=f"hackorak-worker-{model.replace('/', '-')}",
          image="python:3.10",
          target=config.daytona.target,
          domain_allow_list=f"{domain},openrouter.ai",
          env_vars={
              "OPENROUTER_API_KEY": config.openrouter_api_key,
              "MODEL_NAME": model,
              "GAME_SERVER_URL": game_server_url,
              "GAME_SERVER_TOKEN": game_server_token,
              "DASHBOARD_URL": dashboard_url,
          },
          auto_stop_interval=config.sandbox.auto_stop_interval,
      )
      sandbox = daytona.create(params)
      # Install Pi
      sandbox.process.exec("npm install -g @earendil-works/pi-coding-agent")
      # Configure pi-mcp extension
      sandbox.fs.upload_file("pi_mcp_config.json", "/root/.pi/mcp.json")
      # Start Pi agent with MCP connection
      sandbox.process.exec(
          "pi --model openrouter/$MODEL_NAME --extension pi-mcp "
          "--mcp-url $GAME_SERVER_URL --mcp-token $GAME_SERVER_TOKEN &"
      )
      return sandbox
  ```
- [ ] Test single worker: verify Pi can connect to game server MCP tools
- [ ] Test multiple workers: verify all can play simultaneously

### Phase 3: Dashboard (Day 3–4)

**Objective:** Live-updating web dashboard showing agent gameplay.

**Tasks:**
- [ ] Implement `dashboard/server.py` (FastAPI + SSE):
  ```python
  from fastapi import FastAPI
  from sse_starlette.sse import EventSourceResponse
  import asyncio
  import json
  
  app = FastAPI()
  scores = []  # In-memory store for prototype
  
  @app.post("/score")
  async def post_score(data: dict):
      scores.append(data)
      # Keep only last 1000 scores
      if len(scores) > 1000:
          scores.pop(0)
      return {"ok": True}
  
  @app.get("/events")
  async def events():
      async def event_generator():
          last_idx = 0
          while True:
              if last_idx < len(scores):
                  for s in scores[last_idx:]:
                      yield {"event": "score_update", "data": json.dumps(s)}
                  last_idx = len(scores)
              await asyncio.sleep(1)
      return EventSourceResponse(event_generator())
  ```
- [ ] Implement `dashboard/static/index.html`:
  - Leaderboard table (sortable by score)
  - Recent activity feed
  - Game state display (text-based for MVP)
  - Auto-connect to SSE endpoint
- [ ] Deploy to dashboard sandbox
- [ ] Test: verify workers can post scores and dashboard updates in real-time

### Phase 4: Integration & Polish (Day 4–5)

**Tasks:**
- [ ] Implement full orchestrator lifecycle:
  1. Create game server sandbox
  2. Create dashboard sandbox
  3. Create N worker sandboxes
  4. Monitor worker progress
  5. Collect final results
  6. Clean up sandboxes (or keep for analysis)
- [ ] Add error handling and retries
- [ ] Add logging and monitoring
- [ ] Test end-to-end with 3 workers on 2048
- [ ] Scale test with 5+ workers
- [ ] Document setup and usage

---

## Risks & Open Questions

### Risks

1. **ORAK game compatibility**: Not all ORAK games run headlessly. Games like Street Fighter require ROMs and display. **Mitigation**: Start with 2048 (headless Python game), Super Mario (gym environment), or Pokémon Red (emulator-based but headless-capable).

2. **MCP version mismatch**: ORAK uses `mcp.server.fastmcp` (MCP v1) while the latest SDK is MCP 2.x. **Mitigation**: Pin `mcp<2` for the game server. Test the SSE transport thoroughly.

3. **OpenRouter rate limits**: Free models have strict rate limits. **Mitigation**: Implement exponential backoff on workers. Consider using a single paid model as fallback.

4. **Pi agent game-playing capability**: Pi is a coding agent, not a game-playing agent. It may need specific prompting to play games effectively. **Mitigation**: Use the ORAK agent prompts as starting points. The pi-mcp extension will expose MCP tools to Pi.

5. **Daytona sandbox resource limits**: Games may require more CPU/memory than default. **Mitigation**: Configure `Resources` in sandbox params.

### Open Questions

1. **Pi agent game-playing**: Can Pi (a coding agent) effectively play games using MCP tools? Need to verify that Pi can understand game states and make appropriate moves. Alternative: Use a dedicated ORAK agent server in each worker sandbox instead of Pi.

2. **Concurrent game sessions**: Does the ORAK game server support multiple concurrent MCP sessions? Each worker connects independently via SSE — need to verify the game server handles this correctly.

3. **Dashboard host**: Should the dashboard be hosted inside Daytona (as a sandbox) or externally (e.g., Vercel)? Internal is simpler for MVP but has latency for external viewers.

4. **Daytona region**: Which region are our API keys provisioned for? Need to confirm `us` vs `eu`.

---

## Appendix: ORAK MCP Server Analysis

### How ORAK Game Servers Work

ORAK game servers use the MCP (Model Context Protocol) to expose game state and accept actions:

```python
# Simplified from src/mcp_game_servers/base_server.py
class MCPGameServer:
    def __init__(self, mcp_server: FastMCP, config_path: str):
        self.mcp = mcp_server
        self.env = EnvCreator(cfg).create()  # Game environment
        self.register_tools()
    
    def register_tools(self):
        @self.mcp.tool(name="load-obs")
        def load_obs() -> str:
            """Load observation and game info from the server."""
            obs_str, obs_image_str, game_info = self.load_current_obs()
            return json.dumps({...})
        
        @self.mcp.tool(name="send-action-set")
        def send_action_set(action_set: list) -> str:
            """Send a action set to the server."""
            ...
        
        @self.mcp.tool(name="dispatch-final-action")
        def dispatch_final_action(action_str: str) -> str:
            """Dispatch a client final action and return score + termination."""
            score, is_finished = self.dispatch_action_and_get_score(action_str)
            return json.dumps({"score": score, "is_finished": is_finished})
```

### Required Modifications for SSE Transport

The current ORAK game server uses `mcp.run_stdio_async()` which communicates over stdin/stdout. To make it accessible from other sandboxes, we need:

```python
# In game_server/start_server.py (new file)
from mcp.server.fastmcp import FastMCP
from mcp_game_servers.base_server import MCPGameServer

async def main():
    server = FastMCP("hackorak-game-server")
    server = MCPGameServer(server, config_path)
    # Use SSE instead of stdio
    await server.mcp.run_sse_async(host="0.0.0.0", port=8080)
```

This exposes the MCP server over HTTP SSE on port 8080, accessible via the Daytona preview proxy.

### Games Suitable for Headless Play

| Game | Headless? | Notes |
|------|-----------|-------|
| **2048** | ✅ Yes | Pure Python, no display needed |
| **Super Mario** | ✅ Yes | Gym environment, headless |
| **Pokémon Red** | ✅ Yes | PyBoy emulator, headless |
| **Baba Is You** | ⚠️ Partial | Needs window but can be virtual |
| **StarCraft II** | ⚠️ Partial | Needs game install + display |
| **Street Fighter** | ❌ No | Needs Diambra + ROM |

**Recommended starting game: 2048** — simplest setup, pure Python, no external dependencies.