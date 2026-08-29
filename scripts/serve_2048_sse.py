import argparse
import asyncio
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from mcp.server.fastmcp import FastMCP

from mcp_game_servers.base_server import MCPGameServer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    ROOT / "src" / "mcp_game_servers" / "twenty_fourty_eight" / "config.yaml"
)


def parse_args():
    parser = argparse.ArgumentParser(description="Serve ORAK 2048 over MCP SSE.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    return parser.parse_args()


async def main():
    args = parse_args()
    server = FastMCP("orak-2048-game-server", host=args.host, port=args.port)
    MCPGameServer(server, args.config)
    await server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(main())
