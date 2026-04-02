"""Shared packet definitions and wire helpers.

Every packet is a single JSON line terminated by ``\\n``.  This module
provides the canonical packet constructors and a line-based I/O helper
so that both server and client share one source of truth.
"""

from __future__ import annotations

import json
import socket
from typing import Any

# ── Packet type constants ────────────────────────────────────────────

# Handshake
T_CONNECT = "connect"
T_ACCEPT = "accept"
T_ERROR = "error"

# Session
T_PLAYER_JOINED = "player_joined"
T_PLAYER_LEFT = "player_left"

# Game state
T_MOVE_INPUT = "move_input"        # client → server: raw input
T_PLAYER_UPDATE = "player_update"  # server → client: authoritative pos
T_CLICK_MOVE = "click_move"        # client → server: right-click move-to
T_PREY_SYNC = "prey_sync"          # host → server → clients: prey world state

# Chat
T_CHAT = "chat"
T_TYPING_START = "typing_start"
T_TYPING_STOP = "typing_stop"

# Utility
T_PING = "ping"
T_PONG = "pong"
T_USERNAME_CHANGE = "username_change"
T_PROFILE_UPDATE = "profile_update"
T_CLIENT_STATUS = "client_status"
T_MEMBER_ACTION = "member_action"


# ── Wire I/O ─────────────────────────────────────────────────────────

def send_packet(conn: socket.socket, data: dict, *, lock=None) -> None:
    """Serialize *data* as a JSON line and send it.  Thread-safe if *lock* given."""
    raw = (json.dumps(data, separators=(",", ":")) + "\n").encode("utf-8")
    if lock is not None:
        with lock:
            conn.sendall(raw)
    else:
        conn.sendall(raw)


class LineReader:
    """Buffered reader that yields complete ``\\n``-delimited JSON objects."""

    def __init__(self) -> None:
        self._buf = ""

    def read_line(self, sock: socket.socket, timeout: float | None = None) -> dict:
        """Block until one JSON line is available.

        Raises ``TimeoutError`` if *timeout* elapses, ``ConnectionError``
        if the remote side closes the connection, and ``json.JSONDecodeError``
        on malformed data.
        """
        old = sock.gettimeout()
        sock.settimeout(timeout)
        try:
            while True:
                if "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        return json.loads(line)
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Remote side closed the connection")
                self._buf += chunk.decode("utf-8")
        finally:
            sock.settimeout(old)

    def feed(self, data: str) -> list[dict]:
        """Feed raw string data and return any complete packets."""
        self._buf += data
        packets: list[dict] = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if line:
                packets.append(json.loads(line))
        return packets

    def reset(self) -> None:
        self._buf = ""


# ── Packet constructors ──────────────────────────────────────────────

def make_connect(username: str, password: str = "",
                 display_name: str = "", bio: str = "") -> dict:
    return {
        "type": T_CONNECT,
        "username": username,
        "password": password,
        "display_name": display_name,
        "bio": bio,
    }


def make_accept(player_id: int, players: list[dict], accepted_username: str = "") -> dict:
    return {"type": T_ACCEPT, "id": player_id, "username": accepted_username, "players": players}


def make_error(message: str) -> dict:
    return {"type": T_ERROR, "message": message}


def make_player_joined(player_id: int, username: str,
                       x: float = 0, y: float = 0, z: float = 0,
                       display_name: str = "", bio: str = "") -> dict:
    return {
        "type": T_PLAYER_JOINED, "id": player_id,
        "username": username, "display_name": display_name,
        "x": x, "y": y, "z": z,
        "state": "idle", "bio": bio,
    }


def make_player_left(player_id: int, username: str) -> dict:
    return {"type": T_PLAYER_LEFT, "id": player_id, "username": username}


def make_move_input(keys: dict) -> dict:
    """Client sends raw movement keys — **not** final position.

    *keys* should contain booleans: ``up``, ``down``, ``left``, ``right``,
    ``sprint``, ``jump``, ``dash_charge``, ``dash_release``.
    """
    return {"type": T_MOVE_INPUT, **keys}


def make_click_move(target_x: float, target_y: float) -> dict:
    """Client requests a smooth move toward a world-space target."""
    return {"type": T_CLICK_MOVE, "target_x": target_x, "target_y": target_y}


def make_player_update(player_id: int, x: float, y: float, z: float,
                       state: str = "idle", username: str = "",
                       display_name: str = "", bio: str = "",
                       ping_ms: float | None = None) -> dict:
    """Server-authoritative state broadcast."""
    pkt = {
        "type": T_PLAYER_UPDATE, "id": player_id,
        "x": x, "y": y, "z": z,
        "state": state, "username": username, "display_name": display_name,
        "bio": bio,
    }
    if ping_ms is not None:
        pkt["ping_ms"] = ping_ms
    return pkt


def make_chat(player_id: int, username: str, display_name: str, message: str) -> dict:
    return {
        "type": T_CHAT, "id": player_id,
        "username": username, "display_name": display_name,
        "message": message,
    }


def make_ping(player_id: int | None = None) -> dict:
    pkt: dict[str, Any] = {"type": T_PING}
    if player_id is not None:
        pkt["id"] = player_id
    return pkt


def make_pong(player_id: int | None = None) -> dict:
    pkt: dict[str, Any] = {"type": T_PONG}
    if player_id is not None:
        pkt["id"] = player_id
    return pkt


def make_profile_update(player_id: int | None, display_name: str, bio: str) -> dict:
    pkt: dict[str, Any] = {
        "type": T_PROFILE_UPDATE,
        "display_name": display_name,
        "bio": bio,
    }
    if player_id is not None:
        pkt["id"] = player_id
    return pkt


def make_client_status(player_id: int | None, ping_ms: float | None = None) -> dict:
    pkt: dict[str, Any] = {"type": T_CLIENT_STATUS}
    if player_id is not None:
        pkt["id"] = player_id
    if ping_ms is not None:
        pkt["ping_ms"] = ping_ms
    return pkt


def make_member_action(action: str, target_id: int, reason: str = "") -> dict:
    return {
        "type": T_MEMBER_ACTION,
        "action": action,
        "target_id": target_id,
        "reason": reason,
    }


def make_username_change(player_id: int | None, new_username: str) -> dict:
    pkt: dict[str, Any] = {
        "type": T_USERNAME_CHANGE,
        "new_username": new_username,
    }
    if player_id is not None:
        pkt["id"] = player_id
    return pkt


def make_prey_sync(prey_list: list[dict]) -> dict:
    return {"type": T_PREY_SYNC, "prey": prey_list}
