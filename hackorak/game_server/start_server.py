#!/usr/bin/env python3
"""
HackOrak Game Server Start Script
==================================
Wraps an ORAK MCP game server over SSE (Server-Sent Events) so it can be
deployed on Daytona and accessed by worker sandboxes.

Usage:
    python -u hackorak/game_server/start_server.py --game twenty_fourty_eight --port 8080
"""

import argparse
import asyncio
import os
import sys

# Ensure the repo root is on sys.path so that `mcp_game_servers` and
# `mcp.server.fastmcp` imports resolve correctly regardless of the
# working directory the script is launched from.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from mcp.server.fastmcp import FastMCP  # noqa: E402  (mcp<2, v1 API)

from mcp_game_servers.base_server import MCPGameServer  # noqa: E402


# Map CLI game names to their config.yaml paths inside the ORAK tree.
_GAME_CONFIG_DIR = os.path.join(_REPO_ROOT, "src", "mcp_game_servers")

GAME_CONFIGS = {
    "twenty_fourty_eight": os.path.join(
        _GAME_CONFIG_DIR, "twenty_fourty_eight", "config.yaml"
    ),
    # Register additional games here as they become available.
    # "pokemon_red": os.path.join(_GAME_CONFIG_DIR, "pokemon_red", "config.yaml"),
}


async def main():
    parser = argparse.ArgumentParser(
        description="HackOrak Game Server – SSE wrapper for ORAK MCP game servers"
    )
    parser.add_argument(
        "--game",
        type=str,
        default="twenty_fourty_eight",
        choices=list(GAME_CONFIGS.keys()),
        help="Game to serve (default: twenty_fourty_eight)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="TCP port for the SSE server (default: 8080)",
    )
    args = parser.parse_args()

    config_path = GAME_CONFIGS[args.game]

    if not os.path.isfile(config_path):
        print(
            f"ERROR: config file not found for game '{args.game}': {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build the FastMCP instance and wrap it in MCPGameServer.
    # MCPGameServer.__init__ registers all MCP tools on the FastMCP instance.
    mcp = FastMCP("game-server")
    _server = MCPGameServer(
        mcp_server=mcp,
        config_path=config_path,
        expand_log_path=False,
    )

    # Run over SSE instead of stdio so workers can reach it over the network.
    await mcp.run_sse_async(host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    asyncio.run(main())