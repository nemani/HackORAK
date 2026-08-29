# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## HackOrak architecture

- Full architecture plan: `docs/hackorak/architecture_plan.md`
- Daytona API investigation: `docs/hackorak/daytona_api_investigation.md`
- ORAK MCP game servers use `mcp.server.fastmcp.FastMCP` (MCP v1, pin `mcp<2`)
- MCP 2.x renamed FastMCP → MCPServer (from `mcp.server.mcpserver`)
- Game server SSE transport: `mcp.run_sse_async(host="0.0.0.0", port=8080)`
- Daytona sandbox networking: use preview URLs + `domain_allow_list`, NOT `network_allow_list`
- Worker→game-server requests need `x-daytona-preview-token` header

## ORAK project structure

- `src/mcp_game_servers/` — MCP game server implementations (12 games)
- `src/mcp_agent_servers/` — Agent module implementations
- `src/mcp_agent_client/` — Client that orchestrates game+agent servers
- `scripts/mcp_play_game.py` — Entry point for MCP version gameplay
- Game configs in `src/mcp_agent_client/configs/{game}/`
- Python 3.10 required; `uv` for dependency management; `pyproject.toml` at root

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
