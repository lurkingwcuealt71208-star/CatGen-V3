"""Server-authoritative game server.

Architecture
------------
* One TCP listener thread (the main server thread).
* One daemon thread per connected client (``handle_client``).
* One cleanup daemon thread.
* ``_game_tick`` is called in each client thread's idle time — the server
  runs physics for every player it manages so clients *never* set position.

Security
--------
* All positions are generated/validated server-side.
* Client packets only carry *input intent* (keys pressed, chat text).
* Oversized / malformed packets are silently dropped.
* Optional password authentication in handshake.
"""

from __future__ import annotations

import json
import logging
import math
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap: SDK/network/server.py -> SDK/network -> SDK -> project root
# This makes 'core', 'game' importable from Main/ when run standalone.
# ---------------------------------------------------------------------------
_SDK  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # SDK/
_ROOT = os.path.dirname(_SDK)                                         # project root
_MAIN = os.path.join(_ROOT, "Main")
for _p in (_MAIN, _SDK):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.constants import (  # pyright: ignore[reportMissingImports]
    BASE_WALK_SPEED, BASE_SPRINT_SPEED, DASH_COOLDOWN,
    DASH_MAX_CHARGE, DASH_MAX_STRENGTH, DASH_MIN_STRENGTH,
    DASH_STAMINA_BASE, DASH_STAMINA_SCALE, DEFAULT_PORT,
    GRAVITY, JUMP_FORCE, LAN_BROADCAST_PORT, MAX_STATUS,
    STAMINA_DRAIN_SECONDS, STAMINA_REGEN_SECONDS, WORLD_HALF,
)
from network.packets import (
    LineReader, make_accept, make_chat, make_error,
    make_player_joined, make_player_left, make_player_update,
    make_pong, send_packet, make_prey_sync, make_username_change,
    T_MOVE_INPUT, T_CLICK_MOVE, T_CHAT, T_TYPING_START,
    T_TYPING_STOP, T_PING, T_USERNAME_CHANGE, T_CONNECT,
    T_PROFILE_UPDATE, T_CLIENT_STATUS, T_PREY_SYNC, T_MEMBER_ACTION,
)

logger = logging.getLogger(__name__)

# Packet size guard (bytes before newline)
_MAX_PACKET_BYTES = 4096


# ---------------------------------------------------------------------------
# Player server-side state
# ---------------------------------------------------------------------------

@dataclass
class ServerPlayer:
    pid: int
    conn: socket.socket
    addr: tuple
    username: str
    display_name: str = ""
    password: str = ""
    bio: str = ""
    ping_ms: float | None = None

    # Physics
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vz: float = 0.0
    is_jumping: bool = False

    # Dash
    dash_charge: float = 0.0
    is_charging_dash: bool = False
    dash_cooldown: float = 0.0

    # Stamina
    stamina: float = float(MAX_STATUS)
    is_sprinting: bool = False

    # Click-to-move target (smooth target position set by right-click)
    target_x: float | None = None
    target_y: float | None = None

    # Input state (updated by incoming move_input packets)
    inp_up: bool = False
    inp_down: bool = False
    inp_left: bool = False
    inp_right: bool = False
    inp_sprint: bool = False
    inp_jump: bool = False
    inp_dash_charge: bool = False
    inp_dash_release: bool = False

    # Meta
    state: str = "idle"               # idle|moving|dashing|jumping
    is_typing: bool = False
    last_activity: float = field(default_factory=time.time)
    connected: bool = True
    send_failures: int = 0  # consecutive send failures; player removed after threshold

    # Per-player send lock
    send_lock: threading.Lock = field(default_factory=threading.Lock)

    def to_dict(self) -> dict:
        return {
            "id": self.pid, "username": self.username,
            "display_name": self.display_name,
            "x": round(self.x, 2), "y": round(self.y, 2),
            "z": round(self.z, 2), "state": self.state, "bio": self.bio,
            "ping_ms": self.ping_ms,
        }

    def send(self, data: dict) -> None:
        try:
            send_packet(self.conn, data, lock=self.send_lock)
        except Exception as exc:
            logger.debug("Failed sending to player %d: %s", self.pid, exc)
            self.connected = False


# ---------------------------------------------------------------------------
# Game Server
# ---------------------------------------------------------------------------

class GameServer:
    """Threaded, server-authoritative game server."""

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 password: str = "") -> None:
        self.host = host
        self.port = port
        self.password = password

        self.players: dict[int, ServerPlayer] = {}
        self.prey_state: list[dict] = []
        self.banned_users: set[str] = set()
        self._next_pid = 1
        self._lock = threading.Lock()        # protects players dict
        self._running = False
        self._server_sock: socket.socket | None = None
        self._broadcast_tick: int = 0        # rate-limits position broadcasts

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Bind and listen; blocks until ``stop()`` is called."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.host, self.port))
        except OSError as exc:
            logger.error("Server bind failed on port %d: %s", self.port, exc)
            sock.close()
            return
        sock.listen(16)
        sock.settimeout(0.5)
        self._server_sock = sock
        self._running = True

        logger.info("Server started on %s:%d", self.host, self.port)

        cleanup_t = threading.Thread(target=self._cleanup_loop, daemon=True)
        cleanup_t.start()

        try:
            while self._running:
                try:
                    conn, addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                t = threading.Thread(
                    target=self.handle_client, args=(conn, addr), daemon=True,
                )
                t.start()
        finally:
            self._shutdown()

    def stop(self) -> None:
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass

    def _shutdown(self) -> None:
        with self._lock:
            for p in list(self.players.values()):
                try:
                    p.conn.close()
                except Exception:
                    pass
            self.players.clear()
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        logger.info("Server shut down")

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    def handle_client(self, conn: socket.socket, addr: tuple) -> None:
        """Per-client thread: handshake, then game loop."""
        conn.settimeout(0.5)
        reader = LineReader()

        # Perform handshake
        try:
            player = self._handshake(conn, addr, reader)
        except Exception as exc:
            logger.warning("Handshake failed from %s: %s", addr, exc)
            try:
                conn.close()
            except Exception:
                pass
            return

        # Register player
        with self._lock:
            self.players[player.pid] = player

        # Notify all existing players that someone joined
        joined_pkt = make_player_joined(
            player.pid, player.username, player.x, player.y, player.z,
            player.display_name, player.bio,
        )
        self._broadcast(joined_pkt, exclude_pid=player.pid)

        logger.info("Player %s (id=%d) connected from %s", player.username, player.pid, addr)

        # Per-client message loop
        last_tick = time.time()
        try:
            while self._running and player.connected:
                now = time.time()
                dt = now - last_tick
                last_tick = now

                # Run server-side physics for this player
                try:
                    self._tick_player(player, dt)
                except Exception as exc:
                    logger.error("Physics tick error for player %d: %s", player.pid, exc)

                # Read incoming packets (non-blocking)
                try:
                    pkt = reader.read_line(conn, timeout=0.05)
                    player.last_activity = time.time()
                    try:
                        self._handle_packet(player, pkt)
                    except Exception as exc:
                        logger.warning("Packet handler error for player %d: %s", player.pid, exc)
                except socket.timeout:
                    pass
                except (ConnectionError, OSError):
                    break
                except json.JSONDecodeError:
                    pass  # drop malformed packet

        except Exception as exc:
            logger.debug("Client loop error for %s: %s", addr, exc)
        finally:
            self._remove_player(player.pid)

    def _handshake(self, conn: socket.socket, addr: tuple,
                   reader: LineReader) -> ServerPlayer:
        """Synchronous handshake. Returns a validated ``ServerPlayer``."""
        conn.settimeout(5.0)
        pkt = reader.read_line(conn, timeout=5.0)

        if pkt.get("type") != T_CONNECT:
            send_packet(conn, make_error("Expected connect packet"))
            raise ValueError(f"Expected connect, got {pkt.get('type')}")

        if self.password and pkt.get("password", "") != self.password:
            send_packet(conn, make_error("Incorrect password"))
            raise PermissionError("Wrong password")

        username = str(pkt.get("username", "Player"))[:32]
        if not username.strip():
            username = "Player"
        display_name = str(pkt.get("display_name", ""))[:32]
        bio = str(pkt.get("bio", ""))[:200]
        if username in self.banned_users:
            send_packet(conn, make_error("You are banned from this server"))
            raise PermissionError("Banned username")

        with self._lock:
            pid = self._next_pid
            self._next_pid += 1
            existing = [p.to_dict() for p in self.players.values()]

        player = ServerPlayer(pid=pid, conn=conn, addr=addr,
                      username=username, display_name=display_name,
                      bio=bio)

        accept_pkt = make_accept(pid, existing, username)  # echo accepted name
        accept_pkt["display_name"] = display_name
        accept_pkt["bio"] = bio
        accept_pkt["prey"] = list(self.prey_state)
        send_packet(conn, accept_pkt)
        return player

    # ------------------------------------------------------------------
    # Packet dispatch
    # ------------------------------------------------------------------

    def _handle_packet(self, player: ServerPlayer, pkt: dict) -> None:
        t = pkt.get("type")

        if t == T_MOVE_INPUT:
            self._apply_input(player, pkt)

        elif t == T_CLICK_MOVE:
            # Server stores click-to-move target; physics tick smooths toward it
            try:
                tx = float(pkt["target_x"])
                ty = float(pkt["target_y"])
                # Reject NaN / Inf to prevent coordinate poisoning
                if math.isnan(tx) or math.isinf(tx) or math.isnan(ty) or math.isinf(ty):
                    raise ValueError("NaN or Inf coordinate rejected")
                # Clamp target to world bounds
                player.target_x = max(-WORLD_HALF, min(WORLD_HALF, tx))
                player.target_y = max(-WORLD_HALF, min(WORLD_HALF, ty))
            except (KeyError, TypeError, ValueError):
                pass

        elif t == T_CHAT:
            message = str(pkt.get("message", "")).strip()
            if len(message) > 256:
                # Notify sender before truncating
                player.send(make_error(f"Message too long ({len(message)} chars); truncated to 256."))
                message = message[:256]
            if message:
                chat_pkt = make_chat(player.pid, player.username,
                                     player.display_name or player.username,
                                     message)
                self._broadcast(chat_pkt)   # send to ALL including sender
                logger.debug("Chat from %s: %s", player.username, message)

        elif t == T_TYPING_START:
            player.is_typing = True
            self._broadcast(
                {"type": T_TYPING_START, "id": player.pid, "username": player.username},
                exclude_pid=player.pid,
            )

        elif t == T_TYPING_STOP:
            player.is_typing = False
            self._broadcast(
                {"type": T_TYPING_STOP, "id": player.pid},
                exclude_pid=player.pid,
            )

        elif t == T_PING:
            player.send(make_pong(player.pid))

        elif t == T_USERNAME_CHANGE:
            new_name = str(pkt.get("new_username", player.username))[:32].strip()
            if not new_name:
                new_name = "Player"
            if new_name in self.banned_users:
                player.send(make_error("That username is banned"))
                return
            player.username = new_name
            self._broadcast(
                make_username_change(player.pid, new_name),
                exclude_pid=player.pid,
            )

        elif t == T_PROFILE_UPDATE:
            new_name = str(pkt.get("display_name", player.display_name or ""))[:32]
            new_bio = str(pkt.get("bio", player.bio))[:200]
            player.display_name = new_name
            player.bio = new_bio
            self._broadcast(
                {
                    "type": T_PROFILE_UPDATE,
                    "id": player.pid,
                    "display_name": new_name,
                    "bio": new_bio,
                },
                exclude_pid=player.pid,
            )

        elif t == T_CLIENT_STATUS:
            try:
                ping_ms = float(pkt.get("ping_ms", 0.0))
                if math.isnan(ping_ms) or math.isinf(ping_ms):
                    raise ValueError
                player.ping_ms = max(0.0, ping_ms)
            except (TypeError, ValueError):
                pass

        elif t == T_PREY_SYNC:
            prey = pkt.get("prey", [])
            if isinstance(prey, list):
                self.prey_state = prey[:200]
                self._broadcast(make_prey_sync(self.prey_state))

        elif t == T_MEMBER_ACTION:
            if player.pid != 1:
                return
            action = str(pkt.get("action", "")).lower()
            target_id = self._safe_int(pkt.get("target_id"))
            if target_id is None:
                return
            with self._lock:
                target = self.players.get(target_id)
            if target is None or target.pid == player.pid:
                return
            if action == "ban":
                self.banned_users.add(target.username)
            self._remove_player(target_id)

        else:
            logger.debug("Unknown packet type '%s' from player %d", t, player.pid)

    def _apply_input(self, player: ServerPlayer, pkt: dict) -> None:
        """Validate and store input-key state from client."""
        player.inp_up = bool(pkt.get("up", False))
        player.inp_down = bool(pkt.get("down", False))
        player.inp_left = bool(pkt.get("left", False))
        player.inp_right = bool(pkt.get("right", False))
        player.inp_sprint = bool(pkt.get("sprint", False))
        player.inp_jump = bool(pkt.get("jump", False))
        player.inp_dash_charge = bool(pkt.get("dash_charge", False))
        player.inp_dash_release = bool(pkt.get("dash_release", False))
        # Any input cancels click-move target
        if any([player.inp_up, player.inp_down, player.inp_left, player.inp_right]):
            player.target_x = None
            player.target_y = None

    # ------------------------------------------------------------------
    # Server-side physics
    # ------------------------------------------------------------------

    def _tick_player(self, p: ServerPlayer, dt: float) -> None:
        """Advance one physics tick for *p* on the server."""
        if dt <= 0:
            return

        # ── Stamina ──
        if p.is_sprinting and p.stamina > 0:
            p.stamina -= (MAX_STATUS / STAMINA_DRAIN_SECONDS) * dt
            p.stamina = max(0.0, p.stamina)
            if p.stamina == 0:
                p.is_sprinting = False
        elif not p.is_sprinting and p.stamina < MAX_STATUS:
            p.stamina += (MAX_STATUS / STAMINA_REGEN_SECONDS) * dt
            p.stamina = min(MAX_STATUS, p.stamina)

        # ── Movement via keyboard input ──
        p.is_sprinting = p.inp_sprint and p.stamina > 0
        speed = (BASE_SPRINT_SPEED if p.is_sprinting else BASE_WALK_SPEED) * 60 * dt
        move_x, move_y = 0.0, 0.0
        if p.inp_left:
            move_x -= speed
        if p.inp_right:
            move_x += speed
        if p.inp_up:
            move_y -= speed
        if p.inp_down:
            move_y += speed

        # ── Click-to-move (smooth approach) ──
        if p.target_x is not None and p.target_y is not None:
            dx = p.target_x - p.x
            dy = p.target_y - p.y
            dist = math.hypot(dx, dy)
            arrive_threshold = 4.0
            if dist <= arrive_threshold:
                p.x = p.target_x
                p.y = p.target_y
                p.target_x = None
                p.target_y = None
            else:
                # Use same walk speed for click-move
                step = min(dist, speed)
                move_x += (dx / dist) * step
                move_y += (dy / dist) * step

        # ── Dash ──
        if p.inp_dash_charge and p.dash_cooldown <= 0 and p.stamina > 5:
            p.is_charging_dash = True
            p.dash_charge = min(DASH_MAX_CHARGE, p.dash_charge + dt)
        elif p.inp_dash_release and p.is_charging_dash:
            if p.dash_cooldown <= 0 and p.stamina > 5:
                charge_ratio = max(0.0, min(1.0, p.dash_charge / DASH_MAX_CHARGE))
                dx, dy = 0.0, 0.0
                if p.inp_left:
                    dx -= 1
                if p.inp_right:
                    dx += 1
                if p.inp_up:
                    dy -= 1
                if p.inp_down:
                    dy += 1
                mag = math.hypot(dx, dy)
                if mag > 0:
                    dx /= mag
                    dy /= mag
                    strength = DASH_MIN_STRENGTH + DASH_MAX_STRENGTH * charge_ratio
                    move_x += dx * strength
                    move_y += dy * strength
                    stamina_cost = DASH_STAMINA_BASE + DASH_STAMINA_SCALE * charge_ratio
                    p.stamina = max(0.0, p.stamina - stamina_cost)
                    p.dash_cooldown = DASH_COOLDOWN
            p.is_charging_dash = False
            p.dash_charge = 0.0
        if not p.inp_dash_charge:
            p.is_charging_dash = False

        if p.dash_cooldown > 0:
            p.dash_cooldown -= dt

        # ── Jump ──
        if p.inp_jump and not p.is_jumping:
            p.vz = JUMP_FORCE
            p.is_jumping = True
        if p.is_jumping:
            p.z += p.vz
            p.vz -= GRAVITY
            if p.z <= 0:
                p.z = 0.0
                p.vz = 0.0
                p.is_jumping = False

        # ── Apply movement and clamp ──
        p.x = max(-WORLD_HALF, min(WORLD_HALF, p.x + move_x))
        p.y = max(-WORLD_HALF, min(WORLD_HALF, p.y + move_y))

        # ── Determine visual state ──
        if p.is_charging_dash or p.dash_cooldown > 0:
            p.state = "dashing"
        elif p.is_jumping:
            p.state = "jumping"
        elif move_x != 0 or move_y != 0:
            p.state = "moving"
        else:
            p.state = "idle"

        # Broadcast authoritative position to all clients (~20/s, not every physics tick)
        self._broadcast_tick += 1
        if self._broadcast_tick % 3 == 0 or p.state != getattr(p, "_last_broadcast_state", None):
            upd = make_player_update(p.pid, p.x, p.y, p.z, p.state, p.username,
                                     p.display_name or p.username, p.bio, p.ping_ms)
            self._broadcast(upd)
            p._last_broadcast_state = p.state  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Player removal
    # ------------------------------------------------------------------

    def _remove_player(self, pid: int) -> None:
        with self._lock:
            p = self.players.pop(pid, None)
        if p is None:
            return
        try:
            p.conn.close()
        except Exception:
            pass
        p.connected = False
        logger.info("Player %s (id=%d) disconnected", p.username, pid)
        self._broadcast(make_player_left(pid, p.username))

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def _broadcast(self, pkt: dict, exclude_pid: int | None = None) -> None:
        """Send *pkt* to all connected players, collecting dead connections."""
        with self._lock:
            targets = list(self.players.values())

        dead: list[int] = []
        raw = (json.dumps(pkt, separators=(",", ":")) + "\n").encode("utf-8")
        for p in targets:
            if p.pid == exclude_pid:
                continue
            try:
                with p.send_lock:
                    p.conn.sendall(raw)
                p.send_failures = 0  # reset on success
            except Exception:
                p.send_failures += 1
                if p.send_failures >= 3:  # only remove after 3 consecutive failures
                    dead.append(p.pid)

        for pid in dead:
            self._remove_player(pid)

    # ------------------------------------------------------------------
    # Cleanup loop
    # ------------------------------------------------------------------

    def _cleanup_loop(self) -> None:
        from core.constants import CLEANUP_TIMEOUT  # pyright: ignore[reportMissingImports]
        while self._running:
            time.sleep(10)
            now = time.time()
            with self._lock:
                stale = [
                    pid for pid, p in self.players.items()
                    if now - p.last_activity > CLEANUP_TIMEOUT
                ]
            for pid in stale:
                logger.info("Cleaning up inactive player %d", pid)
                self._remove_player(pid)

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def player_count(self) -> int:
        with self._lock:
            return len(self.players)
