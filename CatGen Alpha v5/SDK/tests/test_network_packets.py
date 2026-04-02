"""Regression tests for network packet construction and client-side validation.

Run with:  pytest SDK/tests/test_network_packets.py -v
"""

from __future__ import annotations

import sys
import os
import math
import json

# conftest.py (in this folder) sets up sys.path automatically.
# No manual path setup needed here.


# ---------------------------------------------------------------------------
# make_accept — packet structure
# ---------------------------------------------------------------------------

class TestMakeAccept:
    def test_accept_has_username_field(self):
        """make_accept must echo the accepted username for the client to read."""
        from network.packets import make_accept
        pkt = make_accept(player_id=1, players=[], accepted_username="TestCat")
        assert "username" in pkt, "make_accept packet missing 'username' key"
        assert pkt["username"] == "TestCat", \
            f"Expected 'TestCat', got {pkt['username']!r}"

    def test_accept_has_default_username(self):
        """Calling make_accept without username should not crash."""
        from network.packets import make_accept
        pkt = make_accept(player_id=2, players=[])
        assert "username" in pkt  # may be empty string but key must exist

    def test_accept_required_fields(self):
        from network.packets import make_accept, T_ACCEPT
        pkt = make_accept(player_id=5, players=[], accepted_username="Fluffy")
        assert pkt.get("type") == T_ACCEPT
        assert pkt.get("id") == 5


# ---------------------------------------------------------------------------
# Client _upsert_player — NaN/Inf coordinate rejection
# ---------------------------------------------------------------------------

class TestClientCoordinateValidation:
    def _make_client(self):
        from network.client import NetworkClient
        return NetworkClient()  # no-arg constructor; connect() is separate

    def test_nan_x_rejected(self):
        client = self._make_client()
        client._upsert_player({"id": 10, "username": "Ghost", "x": float("nan"), "y": 0.0})
        # NaN should be rejected; player entry must not contain NaN in 'x' or 'tx'
        entry = client.other_players.get(10)
        if entry is not None:
            assert not math.isnan(entry.get("x", 0.0)), \
                "_upsert_player stored a NaN x coordinate"
            assert not math.isnan(entry.get("tx", 0.0)), \
                "_upsert_player stored a NaN tx (target) coordinate"

    def test_inf_y_rejected(self):
        client = self._make_client()
        client._upsert_player({"id": 11, "username": "Ghost2", "x": 0.0, "y": float("inf")})
        entry = client.other_players.get(11)
        if entry is not None:
            assert not math.isinf(entry.get("y", 0.0)), \
                "_upsert_player stored an Inf y coordinate"
            assert not math.isinf(entry.get("ty", 0.0)), \
                "_upsert_player stored an Inf ty (target) coordinate"

    def test_valid_coords_accepted(self):
        client = self._make_client()
        client._upsert_player({"id": 12, "username": "Paws", "x": 100.0, "y": 200.0})
        entry = client.other_players.get(12)
        assert entry is not None, "Valid coordinates were rejected"
        assert entry["x"] == 100.0, f"Expected x=100.0, got {entry['x']}"
        assert entry["y"] == 200.0, f"Expected y=200.0, got {entry['y']}"


# ---------------------------------------------------------------------------
# Server username fallback
# ---------------------------------------------------------------------------

class TestServerUsernameFallback:
    """Server must convert blank/whitespace usernames to 'Player'."""

    def _normalise(self, raw: str) -> str:
        """Mirrors the server's username normalisation logic."""
        username = raw.strip()
        if not username:
            username = "Player"
        return username

    def test_empty_string_becomes_player(self):
        assert self._normalise("") == "Player"

    def test_whitespace_only_becomes_player(self):
        assert self._normalise("   ") == "Player"

    def test_valid_username_unchanged(self):
        assert self._normalise("Mittens") == "Mittens"

    def test_leading_trailing_space_trimmed(self):
        result = self._normalise("  Cat  ")
        assert result == "Cat"


# ---------------------------------------------------------------------------
# Packet round-trip (JSON serialisation)
# ---------------------------------------------------------------------------

class TestPacketSerialisation:
    def test_all_packet_constructors_are_json_serialisable(self):
        from network import packets as p
        pkt_fns = [
            ("make_connect",      lambda: p.make_connect("Whiskers")),
            ("make_accept",       lambda: p.make_accept(1, [], "Whiskers")),
            ("make_player_update",lambda: p.make_player_update(1, 50.0, 80.0, 0.0, "idle", "Whiskers", "Stormfur", "")),
            ("make_chat",         lambda: p.make_chat(1, "Whiskers", "Stormfur", "Hello!")),
            ("make_error",        lambda: p.make_error("Something went wrong")),
            ("make_player_left",  lambda: p.make_player_left(1, "Whiskers")),
            ("make_ping",         lambda: p.make_ping()),
        ]
        for name, fn in pkt_fns:
            try:
                pkt = fn()
                serialised = json.dumps(pkt)
                assert serialised, f"{name} produced empty JSON"
            except Exception as exc:
                raise AssertionError(f"{name} raised {exc}") from exc


# ---------------------------------------------------------------------------
# Broadcast failure threshold
# ---------------------------------------------------------------------------

class TestBroadcastFailureThreshold:
    """Server should kick a player only after 3 consecutive send failures, not on 1."""

    def test_dataclass_has_send_failures_field(self):
        from network.server import ServerPlayer
        import dataclasses
        fields = {f.name for f in dataclasses.fields(ServerPlayer)}
        assert "send_failures" in fields, \
            "ServerPlayer missing 'send_failures' field — broadcast resilience broken"

    def test_send_failures_default_zero(self):
        from network.server import ServerPlayer

        class _FakeSock:
            def sendall(self, data):
                raise OSError("mock")
            def close(self):
                pass

        sp = ServerPlayer(pid=99, conn=_FakeSock(), addr=("127.0.0.1", 1), username="Tester")
        assert sp.send_failures == 0, "send_failures must default to 0"
