"""Multiplayer client.

Design decisions
----------------
* ``connect()`` performs a synchronous handshake (5-second timeout).
* Background threads for receiving and heartbeat — both are daemon threads.
* The client only sends *input intent* (``move_input``, ``click_move``, ``chat``).
  It **never** sends its own position — the server is authoritative.
* ``other_players`` is keyed by integer player id and contains the last
  server-authoritative snapshot **plus** smooth-interpolation targets
  (``tx``, ``ty``, ``tz``).
* All shared state is protected by ``lock``; sends use a separate ``send_lock``.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap: SDK/network/client.py -> SDK -> project root
# Makes 'core' importable from Main/ and 'network' importable from SDK/
# ---------------------------------------------------------------------------
import os, sys as _sys  # noqa: E401  (needed before other imports)
_SDK  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # SDK/
_ROOT = os.path.dirname(_SDK)                                         # project root
_MAIN = os.path.join(_ROOT, "Main")
for _p in (_MAIN, _SDK):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from core.constants import DEFAULT_PORT, HEARTBEAT_INTERVAL, REMOTE_LERP_XY, REMOTE_LERP_Z
from network.packets import (
    LineReader, send_packet,
    make_connect, make_ping, make_chat, make_click_move,
    make_profile_update, make_client_status, make_prey_sync,
    make_member_action, make_username_change,
    T_ACCEPT, T_ERROR, T_PLAYER_JOINED, T_PLAYER_LEFT,
    T_PLAYER_UPDATE, T_CHAT, T_TYPING_START, T_TYPING_STOP,
    T_USERNAME_CHANGE, T_PROFILE_UPDATE, T_CLIENT_STATUS, T_PREY_SYNC, T_PONG,
)

from game.prey import Prey

logger = logging.getLogger(__name__)


class NetworkClient:
    """Client-side multiplayer session handler."""

    def __init__(self) -> None:
        self.socket: socket.socket | None = None
        self.connected: bool = False
        self.client_id: int | None = None

        self.username: str = "Player"
        self.display_name: str = ""

        # Shared state — always access under ``lock``
        self.other_players: dict[int, dict] = {}
        self.other_typing: dict[int, bool] = {}
        self.chat_messages: list[dict[str, Any]] = []
        self.remote_prey: list[Prey] = []
        self.self_player_snapshot: dict[str, Any] | None = None
        self.lock = threading.Lock()

        # Send serialisation
        self.send_lock = threading.Lock()

        # Background threads
        self._recv_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_running = False
        self._last_ping_sent: float | None = None
        self.ping_ms: float | None = None

        self._reader = LineReader()
        self._status_msg: str = ""   # last connect/error message for UI

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self, ip: str, port: int | str = DEFAULT_PORT,
            username: str = "Player", password: str = "",
            display_name: str = "", bio: str = "") -> tuple[bool, str]:
        self.disconnect()
        self.username = username
        self.display_name = display_name

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((ip, int(port)))
            self.socket = sock
            self._reader.reset()

            # Synchronous handshake
            send_packet(sock, make_connect(username, password, display_name, bio), lock=self.send_lock)
            response = self._reader.read_line(sock, timeout=5.0)

            if response.get("type") == T_ERROR:
                raise ConnectionError(response.get("message", "Rejected"))
            if response.get("type") != T_ACCEPT:
                raise ConnectionError(f"Unexpected handshake: {response.get('type')}")

            self.client_id = int(response["id"])
            # Use the server-accepted username (may have been truncated)
            accepted_name = response.get("username", "")
            if accepted_name:
                self.username = accepted_name
            self.display_name = response.get("display_name", self.display_name)
            with self.lock:
                self._hydrate_players(response.get("players", []))
                self._hydrate_prey(response.get("prey", []))

            self.connected = True
            sock.settimeout(0.5)
            self._status_msg = "Connected"
            logger.info("Connected as player id=%d", self.client_id)

            self._recv_thread = threading.Thread(
                target=self._receive_loop, daemon=True, name="mp-recv",
            )
            try:
                self._recv_thread.start()
            except RuntimeError as exc:
                logger.error("Failed to start recv thread: %s", exc)
                raise ConnectionError("Could not start background thread") from exc

            self._heartbeat_running = True
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, daemon=True, name="mp-hb",
            )
            try:
                self._heartbeat_thread.start()
            except RuntimeError as exc:
                logger.error("Failed to start heartbeat thread: %s", exc)
                self._heartbeat_running = False

            return True, "Connected"

        except Exception as exc:
            msg = str(exc)
            self._status_msg = f"Connection failed: {msg}"
            logger.error("Connection failed: %s", exc)
            self.disconnect()
            return False, msg

    def disconnect(self) -> None:
        self.connected = False
        self._heartbeat_running = False
        self.client_id = None
        self._last_ping_sent = None
        self.ping_ms = None
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        self._reader.reset()
        with self.lock:
            self.other_players.clear()
            self.other_typing.clear()
            self.remote_prey.clear()
            self.self_player_snapshot = None

    @property
    def status(self) -> str:
        return self._status_msg

    # ------------------------------------------------------------------
    # Sending input / chat — client NEVER sends position
    # ------------------------------------------------------------------

    def send_input(self, up: bool, down: bool, left: bool, right: bool,
                   sprint: bool = False, jump: bool = False,
                   dash_charge: bool = False, dash_release: bool = False) -> None:
        """Send raw key-state to the server as a ``move_input`` packet."""
        self._send({
            "type": "move_input",
            "up": up, "down": down, "left": left, "right": right,
            "sprint": sprint, "jump": jump,
            "dash_charge": dash_charge, "dash_release": dash_release,
        })

    def send_click_move(self, world_x: float, world_y: float) -> None:
        """Ask the server to smoothly move this player to ``(world_x, world_y)``."""
        self._send(make_click_move(world_x, world_y))

    def send_chat(self, message: str, display_name: str | None = None) -> None:
        if self.client_id is not None:
            if display_name is not None:
                self.display_name = display_name
            self._send(make_chat(self.client_id, self.username,
                                 self.display_name or self.username, message))

    def send_typing(self, is_typing: bool) -> None:
        self._send({"type": "typing_start" if is_typing else "typing_stop",
                    "id": self.client_id})

    def send_username_change(self, new_name: str) -> None:
        self.username = new_name
        self._send(make_username_change(self.client_id, new_name))

    def send_profile_update(self, display_name: str, bio: str) -> None:
        self.display_name = display_name
        self._send(make_profile_update(self.client_id, display_name, bio))

    def send_client_status(self) -> None:
        self._send(make_client_status(self.client_id, self.ping_ms))

    def send_prey_sync(self, prey_list: list) -> None:
        payload = []
        for prey in prey_list:
            payload.append({
                "x": getattr(prey, "x", 0.0),
                "y": getattr(prey, "y", 0.0),
                "state": getattr(prey, "state", "idle"),
                "alpha": getattr(prey, "alpha", 255),
                "bob_timer": getattr(prey, "bob_timer", 0.0),
                "name": getattr(prey, "name", "Mouse"),
            })
        self._send(make_prey_sync(payload))

    def send_member_action(self, action: str, target_id: int, reason: str = "") -> None:
        self._send(make_member_action(action, target_id, reason))

    def _send(self, pkt: dict) -> None:
        if not self.connected or not self.socket:
            return
        try:
            send_packet(self.socket, pkt, lock=self.send_lock)
        except Exception as exc:
            logger.error("Send error: %s", exc)
            self.disconnect()

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        while self._heartbeat_running:
            if not self.connected:
                break
            # Sleep in small increments so disconnect() takes effect within ~100 ms
            for _ in range(int(HEARTBEAT_INTERVAL * 10)):
                if not self._heartbeat_running or not self.connected:
                    return
                time.sleep(0.1)
            if self.connected and self.client_id is not None:
                self._last_ping_sent = time.time()
                self._send(make_ping(self.client_id))

    def _receive_loop(self) -> None:
        while self.connected and self.socket:
            try:
                pkt = self._reader.read_line(self.socket, timeout=0.5)
                with self.lock:
                    self._handle_message(pkt)
            except socket.timeout:
                continue
            except (TimeoutError, OSError):
                continue
            except json.JSONDecodeError as exc:
                logger.debug("JSON error: %s", exc)
            except ConnectionError as exc:
                if self.connected:
                    logger.warning("Receive loop closed: %s", exc)
                break
            except Exception as exc:
                if self.connected:
                    logger.error("Receive loop error: %s", exc)
                break
        self.disconnect()

    # ------------------------------------------------------------------
    # Message dispatch (called with self.lock held)
    # ------------------------------------------------------------------

    def _handle_message(self, msg: dict) -> None:
        t = msg.get("type")

        if t == T_PLAYER_UPDATE:
            pid = self._pid(msg.get("id"))
            if pid == self.client_id:
                self.self_player_snapshot = {
                    "x": float(msg.get("x", 0.0)),
                    "y": float(msg.get("y", 0.0)),
                    "z": float(msg.get("z", 0.0)),
                    "state": msg.get("state", "idle"),
                }
            else:
                self._upsert_player(msg)

        elif t == T_PLAYER_JOINED:
            pid = self._pid(msg.get("id"))
            if pid is not None and pid != self.client_id:
                entry = {
                    "username": msg.get("username", "Player"),
                    "display_name": msg.get("display_name", ""),
                    "x": float(msg.get("x", 0)),
                    "y": float(msg.get("y", 0)),
                    "z": float(msg.get("z", 0)),
                    "tx": float(msg.get("x", 0)),
                    "ty": float(msg.get("y", 0)),
                    "tz": float(msg.get("z", 0)),
                    "state": msg.get("state", "idle"),
                    "bio": msg.get("bio", ""),
                    "ping_ms": msg.get("ping_ms"),
                    "player_message": "",
                    "message_time": 0.0,
                }
                self.other_players[pid] = entry
                self._append_chat_message({
                    "kind": "system",
                    "time": time.time(),
                    "text": f"{entry['display_name'] or entry['username']} joined the game",
                })

        elif t == T_PLAYER_LEFT:
            pid = self._pid(msg.get("id"))
            if pid is not None:
                p = self.other_players.pop(pid, {})
                self.other_typing.pop(pid, None)
                username = p.get("username", f"Player {pid}")
                self._append_chat_message({
                    "kind": "system",
                    "time": time.time(),
                    "text": f"{p.get('display_name') or username} left the game",
                })

        elif t == T_CHAT:
            pid = self._pid(msg.get("id"))
            sender = msg.get("username") or "?"
            display_name = msg.get("display_name", "") or sender
            text = msg.get("message", "")
            self._append_chat_message({
                "kind": "chat",
                "time": time.time(),
                "username": sender,
                "display_name": display_name,
                "message": text,
            })
            if pid is not None and pid in self.other_players:
                self.other_players[pid]["player_message"] = text
                self.other_players[pid]["message_time"] = time.time()

        elif t == T_TYPING_START:
            pid = self._pid(msg.get("id"))
            if pid is not None:
                self.other_typing[pid] = True

        elif t == T_TYPING_STOP:
            pid = self._pid(msg.get("id"))
            if pid is not None:
                self.other_typing[pid] = False

        elif t == T_USERNAME_CHANGE:
            pid = self._pid(msg.get("id"))
            if pid is not None and pid in self.other_players:
                self.other_players[pid]["username"] = msg.get("new_username", self.other_players[pid].get("username", "Player"))

        elif t == T_PROFILE_UPDATE:
            pid = self._pid(msg.get("id"))
            if pid is not None and pid in self.other_players:
                self.other_players[pid]["display_name"] = msg.get("display_name", self.other_players[pid].get("display_name", ""))
                self.other_players[pid]["bio"] = msg.get("bio", self.other_players[pid].get("bio", ""))

        elif t == T_PONG:
            if self._last_ping_sent is not None:
                self.ping_ms = max(0.0, (time.time() - self._last_ping_sent) * 1000.0)
                self._last_ping_sent = None
            self.send_client_status()

        elif t == T_PREY_SYNC:
            self._hydrate_prey(msg.get("prey", []))

        elif t == T_ERROR:
            logger.warning("Server error message: %s", msg.get("message"))

    def _append_chat_message(self, entry: dict[str, Any]) -> None:
        self.chat_messages.append(entry)
        if len(self.chat_messages) > 200:
            self.chat_messages = self.chat_messages[-200:]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pid(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _hydrate_players(self, player_list: list[dict]) -> None:
        """Populate ``other_players`` from the server's welcome payload."""
        self.other_players = {}
        for p in player_list:
            pid = self._pid(p.get("id"))
            if pid is None or pid == self.client_id:
                continue
            x, y, z = float(p.get("x", 0)), float(p.get("y", 0)), float(p.get("z", 0))
            self.other_players[pid] = {
                "username": p.get("username", "Player"),
                "display_name": p.get("display_name", ""),
                "x": x, "y": y, "z": z,
                "tx": x, "ty": y, "tz": z,
                "state": p.get("state", "idle"),
                "bio": p.get("bio", ""),
                "ping_ms": p.get("ping_ms"),
                "player_message": p.get("player_message", ""),
                "message_time": p.get("message_time", 0.0),
            }

    def _hydrate_prey(self, prey_list: list[dict]) -> None:
        self.remote_prey = []
        for payload in prey_list:
            try:
                prey = Prey(float(payload.get("x", 0.0)), float(payload.get("y", 0.0)))
                prey.state = payload.get("state", Prey.IDLE)
                prey.alpha = int(payload.get("alpha", 255))
                prey.bob_timer = float(payload.get("bob_timer", 0.0))
                prey.name = payload.get("name", "Mouse")
                self.remote_prey.append(prey)
            except (TypeError, ValueError):
                continue

    def _upsert_player(self, payload: dict) -> None:
        """Update remote player using server-authoritative snapshot."""
        pid = self._pid(payload.get("id"))
        if pid is None or pid == self.client_id:
            return
        is_new = pid not in self.other_players
        entry = self.other_players.setdefault(pid, {
            "username": "Player", "x": 0.0, "y": 0.0, "z": 0.0,
            "tx": 0.0, "ty": 0.0, "tz": 0.0, "state": "idle", "bio": "",
            "display_name": "", "ping_ms": None, "player_message": "", "message_time": 0.0,
        })
        # Update targets for smooth interpolation; reject NaN/Inf coordinates
        for key in ("x", "y", "z"):
            if key in payload:
                try:
                    val = float(payload[key])
                    import math as _math
                    if _math.isnan(val) or _math.isinf(val):
                        logger.warning("Rejected invalid coordinate %s=%r from pid=%s", key, val, pid)
                        continue
                    entry["t" + key] = val
                    if is_new:           # snap new players
                        entry[key] = val
                except (TypeError, ValueError):
                    pass
        for key in ("username", "state", "bio", "display_name"):
            if key in payload:
                entry[key] = payload[key]
        if "ping_ms" in payload:
            entry["ping_ms"] = payload.get("ping_ms")

    def tick_interpolation(self) -> None:
        """Advance interpolation for all remote players.

        Call once per frame *outside* the lock (takes it internally briefly).
        The lerp constants live in ``core.constants``.
        """
        with self.lock:
            for entry in self.other_players.values():
                entry["x"] += (entry.get("tx", entry["x"]) - entry["x"]) * REMOTE_LERP_XY
                entry["y"] += (entry.get("ty", entry["y"]) - entry["y"]) * REMOTE_LERP_XY
                entry["z"] += (entry.get("tz", entry["z"]) - entry["z"]) * REMOTE_LERP_Z
