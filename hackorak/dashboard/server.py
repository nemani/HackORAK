"""
HackOrak Live Dashboard — FastAPI server with SSE and static frontend.

POST /score  — accept score updates from agents
GET  /events — SSE stream of score_updates for connected browsers
Static files served from hackorak/dashboard/static/
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class ScoreEntry(BaseModel):
    worker_id: str
    model: str
    score: float
    step: int
    game_state: str = ""
    timestamp: str = ""


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

class Store:
    """Thread-safe-ish in-memory store; single process, async-safe."""

    def __init__(self):
        self._scores: dict[str, ScoreEntry] = {}  # worker_id -> latest entry
        self._feed: list[ScoreEntry] = []          # recent activity (last 50)
        self._subscribers: list[asyncio.Queue] = []

    def upsert(self, entry: ScoreEntry) -> ScoreEntry:
        self._scores[entry.worker_id] = entry
        self._feed.append(entry)
        if len(self._feed) > 50:
            self._feed = self._feed[-50:]
        return entry

    @property
    def scores(self) -> list[ScoreEntry]:
        return sorted(self._scores.values(), key=lambda e: e.score, reverse=True)

    @property
    def feed(self) -> list[ScoreEntry]:
        return list(reversed(self._feed[-20:]))

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def publish(self, entry: ScoreEntry) -> None:
        payload = json.dumps(entry.model_dump())
        dead: list[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)


store = Store()

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="HackOrak Live Dashboard")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the dashboard SPA."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "index.html not found")
    return HTMLResponse(index_path.read_text())


@app.post("/score")
async def post_score(entry: ScoreEntry):
    """Accept a score update from an agent."""
    if not entry.timestamp:
        entry.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry = store.upsert(entry)
    await store.publish(entry)
    return {"status": "ok", "top": len(store.scores)}


@app.get("/events")
async def sse_events(request: Request):
    """SSE endpoint — streams score_updates to connected browsers."""

    async def event_stream():
        q = store.subscribe()
        try:
            # Send initial full state as a "sync" event
            initial = {
                "scores": [e.model_dump() for e in store.scores],
                "feed": [e.model_dump() for e in store.feed],
            }
            yield f"event: sync\ndata: {json.dumps(initial)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"event: score_update\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        finally:
            store.unsubscribe(q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")