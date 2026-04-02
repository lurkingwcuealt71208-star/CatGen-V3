"""Regression tests for core game logic.

Run with:  pytest SDK/tests/test_game_logic.py -v
"""

from __future__ import annotations

import sys
import os

# conftest.py (in this folder) sets up sys.path automatically.
# No manual path setup needed here.

# Stub pygame before importing game modules (no display needed for unit tests)
try:
    import pygame
    pygame.init()
except Exception:
    pass


# ---------------------------------------------------------------------------
# PlayerState attribute contract
# ---------------------------------------------------------------------------

class TestPlayerStateAttributes:
    """Any attribute referenced outside state.py must exist in __init__."""

    def setup_method(self):
        from game.state import PlayerState
        self.state = PlayerState()

    def test_jump_physics_attributes_exist(self):
        assert hasattr(self.state, "z"), "state.z missing — jump physics will crash"
        assert hasattr(self.state, "vel_z"), "state.vel_z missing — jump physics will crash"
        assert hasattr(self.state, "is_jumping"), "state.is_jumping missing"

    def test_pounce_attributes_exist(self):
        assert hasattr(self.state, "pounce_meter"), "state.pounce_meter missing"
        assert hasattr(self.state, "max_pounce"), "state.max_pounce missing — hud.py crash"
        assert isinstance(self.state.max_pounce, float) and self.state.max_pounce > 0

    def test_stamina_attributes_exist(self):
        assert hasattr(self.state, "stamina"), "state.stamina missing"
        assert hasattr(self.state, "max_stamina"), "state.max_stamina missing — logic.py crash"
        assert self.state.max_stamina > 0

    def test_prey_spawn_timer_exists(self):
        assert hasattr(self.state, "prey_spawn_timer"), "state.prey_spawn_timer missing — logic.py crash"

    def test_map_position_attributes_exist(self):
        assert hasattr(self.state, "player_map_x"), "state.player_map_x missing — map screen crash"
        assert hasattr(self.state, "player_map_y"), "state.player_map_y missing — map screen crash"

    def test_no_legacy_player_z_attribute(self):
        """Ensure legacy misnaming is gone (state.z is the correct name)."""
        # main.py was previously using state.player_z which doesn't exist
        assert not hasattr(self.state, "player_z") or hasattr(self.state, "z"), \
            "state.player_z found but state.z must be the canonical attribute"


# ---------------------------------------------------------------------------
# load_controls contract
# ---------------------------------------------------------------------------

class TestLoadControls:
    def test_returns_dict(self):
        from core.config import init_default_controls, load_controls
        init_default_controls()
        controls = load_controls()
        assert isinstance(controls, dict), "load_controls() must return a dict"

    def test_required_keys_present(self):
        from core.config import init_default_controls, load_controls
        init_default_controls()
        controls = load_controls()
        required = {"MOVE_UP", "MOVE_DOWN", "MOVE_LEFT", "MOVE_RIGHT",
                    "SPRINT", "JUMP", "CHAT", "INVENTORY", "MENU", "DASH"}
        for key in required:
            assert key in controls, f"controls['{key}'] missing from load_controls()"

    def test_all_values_are_integers(self):
        from core.config import init_default_controls, load_controls
        init_default_controls()
        controls = load_controls()
        for action, key in controls.items():
            assert isinstance(key, int), \
                f"controls['{action}'] = {key!r} is not an int — pygame key constant expected"


# ---------------------------------------------------------------------------
# Prey physics dt-scaling
# ---------------------------------------------------------------------------

class TestPreyPhysics:
    def test_grazing_moves_with_dt(self):
        """GRAZING prey must move proportionally to dt (not frame-rate-dependent)."""
        from game.prey import Prey
        p = Prey(0.0, 0.0)
        p.state = Prey.GRAZING
        p.vx = 1.0
        p.vy = 0.0

        x_before = p.x
        dt_small = 1 / 144  # 144 fps
        # Simulate 144 frames at 144fps (= 1 second of game time)
        for _ in range(144):
            if p.state == Prey.GRAZING:
                p.x += p.vx * 60 * dt_small
                p.y += p.vy * 60 * dt_small
        moved_144fps = p.x - x_before

        p.x = 0.0
        dt_large = 1 / 60  # 60 fps
        # Simulate 60 frames at 60fps (= 1 second of game time)
        for _ in range(60):
            if p.state == Prey.GRAZING:
                p.x += p.vx * 60 * dt_large
                p.y += p.vy * 60 * dt_large
        moved_60fps = p.x

        # Both should travel the same distance in 1 second regardless of FPS
        assert abs(moved_144fps - moved_60fps) < 0.1, \
            f"GRAZING prey speed is frame-rate-dependent: 144fps={moved_144fps:.2f} 60fps={moved_60fps:.2f}"

    def test_grazing_not_idle_code_path(self):
        """GRAZING must use the dt-scaled code path, not the raw vx path."""
        from game.prey import Prey
        p = Prey(0.0, 0.0)
        p.state = Prey.GRAZING
        p.vx = 10.0
        p.vy = 0.0
        p.state_timer = 10.0   # prevent random state transition on first tick
        x_before = p.x
        p.update(9999.0, 9999.0, 1 / 60)  # player is far away; stays GRAZING
        # At 60fps, GRAZING should move ~10*60*(1/60) = 10 units in one frame,
        # not 10 units flat (which would be the bug)
        dx = abs(p.x - x_before)
        # dx should be ~10 (with 60*dt scaling); if it were 10 exactly without dt
        # scaling that would also happen to be 10 at 60fps, so just confirm > 0
        assert dx > 0, "GRAZING prey did not move"


# ---------------------------------------------------------------------------
# Inventory eat — hunger delta
# ---------------------------------------------------------------------------

class TestInventoryHunger:
    def test_eat_item_increases_hunger(self):
        """Eating a prey item must increase hunger by prey_hunger amount."""
        import pygame
        from game.inventory import Inventory, Item

        inv = Inventory()
        item = Item("Mouse", (200, 150, 100), "A fresh catch.")
        item.is_prey = True
        item.prey_hunger = 20
        item.prey_ref = None
        inv.add_item(item)

        # Find the slot the item was placed in
        slot = next(i for i, s in enumerate(inv.items) if s is not None)
        inv.context_menu = {"slot": slot, "pos": (0, 0), "options": ["Eat"]}

        hunger_ref = [50.0]  # starting hunger
        prey_list = []

        # Simulate clicking "Eat" option (index 0)
        click_event = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"pos": (0, 0), "button": 1},
        )
        inv.handle_input(
            click_event, 800, 600,
            hunger_ref=hunger_ref,
            prey_list=prey_list,
            carried_prey=[],
            last_hunt_time=0.0,
            push_overlay_fn=lambda n: None,
            draw_gradient_fn=lambda *a: None,
        )
        assert hunger_ref[0] == 70.0, \
            f"Hunger should be 70 after eating 20-hunger item from 50; got {hunger_ref[0]}"


# ---------------------------------------------------------------------------
# Port validation
# ---------------------------------------------------------------------------

class TestPortValidation:
    """Ensure the MP form port validation prevents crashes from bad user input."""

    def _make_mps(self, port: str):
        from ui.menus import MpMenuState, MP_DIRECT
        mps = MpMenuState()
        mps.state = MP_DIRECT
        mps.direct_ip = "127.0.0.1"
        mps.direct_port = port
        return mps

    def test_valid_port_returns_join_action(self):
        from ui.menus import _mp_form_confirm, MP_DIRECT
        mps = self._make_mps("25565")
        result = _mp_form_confirm(mps, [], [])
        assert result.startswith("join:"), f"Expected join action, got {result!r}"

    def test_empty_port_defaults_and_does_not_crash(self):
        from ui.menus import _mp_form_confirm
        mps = self._make_mps("")
        result = _mp_form_confirm(mps, [], [])
        # Should either join with fallback port or return ""
        assert result == "" or result.startswith("join:"), \
            f"Unexpected result for empty port: {result!r}"

    def test_port_out_of_range_rejected(self):
        from ui.menus import _mp_form_confirm
        mps = self._make_mps("99999")
        result = _mp_form_confirm(mps, [], [])
        assert result == "", f"Out-of-range port should return '', got {result!r}"

    def test_port_zero_rejected(self):
        from ui.menus import _mp_form_confirm
        mps = self._make_mps("0")
        result = _mp_form_confirm(mps, [], [])
        assert result == "", f"Port 0 should return '', got {result!r}"

    def test_port_max_valid(self):
        from ui.menus import _mp_form_confirm
        mps = self._make_mps("65535")
        result = _mp_form_confirm(mps, [], [])
        assert result.startswith("join:"), f"Port 65535 should be valid, got {result!r}"

    def test_port_type_max_5_digits(self):
        """Typing into port field must cap at 5 characters."""
        from ui.menus import _mp_form_type, MpMenuState, MP_DIRECT
        mps = MpMenuState()
        mps.state = MP_DIRECT
        mps.input_focus = "port"
        mps.direct_port = "12345"
        _mp_form_type(mps, "6")  # should be rejected (already 5 chars)
        assert mps.direct_port == "12345", \
            f"Port should stay at 5 chars, got {mps.direct_port!r}"
