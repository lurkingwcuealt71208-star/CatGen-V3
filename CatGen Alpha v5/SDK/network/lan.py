"""LAN discovery — UDP broadcast sender (server) and scanner (client)."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from core.constants import DEFAULT_PORT, LAN_BROADCAST_PORT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Broadcaster (server-side)
# ---------------------------------------------------------------------------

class LanBroadcaster:
    """UDP broadcast announcer that runs in a daemon thread."""

    def __init__(self, port: int = DEFAULT_PORT,
                 get_player_count: Callable[[], int] | None = None,
                 server_name: str = "CatGen Server",
                 rainbow_text: bool = False,
                 password_required: bool = False) -> None:
        self.port = port
        self.server_name = server_name
        self.rainbow_text = rainbow_text
        self.password_required = password_required
        self._get_count = get_player_count or (lambda: 0)
        self._running = False
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None

    def start(self) -> None:
        self._started_at = time.time()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="lan-bcast")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while self._running:
                try:
                    payload = json.dumps({
                        "type": "lan_announce",
                        "name": self.server_name,
                        "players": self._get_count(),
                        "port": self.port,
                        "uptime": 0.0 if self._started_at is None else max(0.0, time.time() - self._started_at),
                        "rainbow_text": self.rainbow_text,
                        "password_required": self.password_required,
                    })
                    s.sendto(payload.encode("utf-8"),
                             ("255.255.255.255", LAN_BROADCAST_PORT))
                except Exception as exc:
                    logger.debug("Broadcast send error: %s", exc)
                time.sleep(1.0)
        except Exception as exc:
            logger.error("LAN broadcaster fatal: %s", exc)
        finally:
            try:
                s.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Scanner (client-side)
# ---------------------------------------------------------------------------

def scan_lan_servers(port: int = DEFAULT_PORT,
                     udp_timeout: float = 1.5,
                     tcp_timeout: float = 0.4,
                     max_tcp_workers: int = 50) -> list[dict]:
    """Discover LAN servers via UDP broadcast and /24 TCP probe.

    Returns a deduplicated list of ``{ip, port, name, players, uptime}`` dicts.
    """
    udp_results: list[dict] = []
    tcp_results: list[dict] = []

    # ── UDP broadcast listener ──────────────────────────────────────
    def _udp_listen():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(udp_timeout)
            s.bind(("", LAN_BROADCAST_PORT))
            while True:
                try:
                    data, addr = s.recvfrom(1024)
                    info = json.loads(data.decode("utf-8"))
                    if info.get("type") == "lan_announce":
                        udp_results.append({
                            "ip": addr[0],
                            "port": info.get("port", port),
                            "name": info.get("name", "CatGen Server"),
                            "players": info.get("players", 0),
                            "uptime": info.get("uptime", 0.0),
                            "rainbow_text": info.get("rainbow_text", False),
                            "password_required": info.get("password_required", False),
                        })
                except socket.timeout:
                    break
                except Exception:
                    break
        except Exception as exc:
            logger.debug("UDP scan error: %s", exc)
        finally:
            try:
                s.close()
            except Exception:
                pass

    udp_t = threading.Thread(target=_udp_listen, daemon=True)
    udp_t.start()
    udp_t.join(timeout=udp_timeout + 0.5)

    # ── TCP /24 subnet probe ─────────────────────────────────────────
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        subnet = ".".join(local_ip.split(".")[:3])
    except Exception:
        subnet = "192.168.1"

    def _probe(ip: str) -> bool:
        try:
            with socket.create_connection((ip, port), timeout=tcp_timeout):
                return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=max_tcp_workers) as ex:
        futures = {ex.submit(_probe, f"{subnet}.{i}"): f"{subnet}.{i}"
                   for i in range(1, 255)}
        for fut in as_completed(futures):
            ip = futures[fut]
            try:
                if fut.result():
                    tcp_results.append({"ip": ip, "port": port})
            except Exception:
                pass

    # ── Merge (UDP wins for metadata) ───────────────────────────────
    merged: dict[str, dict] = {}
    for r in udp_results:
        merged[f"{r['ip']}:{r['port']}"] = r
    for r in tcp_results:
        key = f"{r['ip']}:{r['port']}"
        merged.setdefault(key, r)

    results = list(merged.values())
    logger.info("LAN scan complete: %d server(s) found", len(results))
    return results
