# MCP server verification

Endpoint: `https://8000-sroctl2mczggwcck.daytonaproxy01.eu/sse`

Verified with the Python MCP SSE client from this repository's virtual environment.

## Status

- SSE connection: successful
- MCP initialize: successful
- Protocol version: `2024-11-05`
- Server: `orak-2048-game-server` version `1.6.0`
- Capabilities: prompts, resources, tools

## Available game

The server is hosting a 2048 game (`TwentyFourtyEightEnv`). Calling `load-obs` returned the current board and task description: merge tiles to make a tile with the value of 2048.

## Available tools

1. `load-obs` — Load observation and game info from the server. No arguments.
2. `send-action-set` — Send an action set to the server. Required argument: `action_set` array.
3. `get-current-state` — Get the current state of the game. No arguments. Note: invocation returned an internal server error: `'TwentyFourtyEightEnv' object has no attribute '_receive_state'`.
4. `dispatch-final-action` — Dispatch a client final action to the server and return score and termination flag. Required argument: `action_str` string.
