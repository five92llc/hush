"""Phone remote: a small relay between "screens" (a TV or computer showing Hush) and "remotes" (a phone).

Protocol, JSON over one WebSocket (/api/remote/ws):
  everyone  -> {"type": "hello", "role": "screen" | "remote", "id": "...", "name": "Living room"}
  screen    -> {"type": "state", "state": {...}}              what is playing, position, volume...
  remote    -> {"type": "cmd", "to": "<screen id>", "cmd": "playpause", "args": {...}}
  server    -> remote: {"type": "screens", "screens": [{"id", "name", "state"}]}
               remote: {"type": "state", "id": "...", "state": {...}}
               screen: {"type": "cmd", "cmd": "...", "args": {...}}
It carries no media, only small control messages, so any client (a native app too) can use it.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid

from fastapi import WebSocket

COMMANDS = {"key", "playpause", "play", "pause", "seek", "seekto", "next", "prev", "channel", "digits", "volume", "mute",
            "filter", "stop", "home", "guide", "mini", "open", "nav", "tv", "fullscreen", "text"}
MAX_STATE_BYTES = 4096
_ID = re.compile(r"[^A-Za-z0-9_-]")


class RemoteHub:
    def __init__(self):
        self.screens: dict[str, dict] = {}          # id -> {name, ws, state}
        self.remotes: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @staticmethod
    def clean_id(value) -> str:
        return _ID.sub("", str(value or ""))[:40] or uuid.uuid4().hex[:12]

    def listing(self) -> list[dict]:
        return [{"id": i, "name": s["name"], "state": s["state"]} for i, s in self.screens.items()]

    async def _send(self, ws: WebSocket, payload: dict) -> bool:
        try:
            await ws.send_json(payload)
            return True
        except Exception:  # noqa: BLE001 - a client that went away
            return False

    async def _to_remotes(self, payload: dict) -> None:
        for ws in list(self.remotes):
            if not await self._send(ws, payload):
                self.remotes.discard(ws)

    async def add_screen(self, sid: str, name: str, ws: WebSocket) -> None:
        async with self._lock:
            old = self.screens.get(sid)
            self.screens[sid] = {"name": name[:40] or "Screen", "ws": ws, "state": old["state"] if old else {}}
        await self._to_remotes({"type": "screens", "screens": self.listing()})

    async def add_remote(self, ws: WebSocket) -> None:
        self.remotes.add(ws)
        await self._send(ws, {"type": "screens", "screens": self.listing()})

    async def update_state(self, sid: str, state: dict) -> None:
        if sid not in self.screens or len(json.dumps(state)) > MAX_STATE_BYTES:
            return
        self.screens[sid]["state"] = state
        await self._to_remotes({"type": "state", "id": sid, "state": state})

    async def send_cmd(self, to: str, cmd: str, args: dict) -> bool:
        if cmd not in COMMANDS or not isinstance(args, dict) or len(json.dumps(args)) > MAX_STATE_BYTES:
            return False
        screen = self.screens.get(to)
        return bool(screen) and await self._send(screen["ws"], {"type": "cmd", "cmd": cmd, "args": args})

    async def remove(self, ws: WebSocket, role: str | None, sid: str | None) -> None:
        self.remotes.discard(ws)
        if role == "screen" and sid and self.screens.get(sid, {}).get("ws") is ws:
            self.screens.pop(sid, None)
            await self._to_remotes({"type": "screens", "screens": self.listing()})
