"""Player session state — all mutable game variables in one place.

Having a single ``PlayerState`` object eliminates scattered globals and
makes it trivial to save/load or reset state.
"""

from __future__ import annotations

import time

from core.constants import (
    BASE_WALK_SPEED, BASE_SPRINT_SPEED,
    DASH_MAX_CHARGE, DASH_COOLDOWN, MAX_CARRY, MAX_STATUS,
    DEFAULT_WIDTH, DEFAULT_HEIGHT,
)


class PlayerState:
    """All mutable state for the local player."""

    def __init__(self) -> None:
        # ── Identity ────────────────────────────────────────────────
        self.username: str = "Player"
        self.character_name: str = ""
        self.character_bio: str = ""
        self.player_level: int = 1
        self.hunting_skill: int = 0
        self.combat_skill: int = 0
        self.tracking_skill: int = 0
        self.hunting_xp: int = 0
        self.combat_xp: int = 0
        self.tracking_xp: int = 0

        # ── World / camera ──────────────────────────────────────────
        self.world_x: float = 0.0
        self.world_y: float = 0.0
        # camera pan offset applied during right-drag (reset on release)
        self.camera_offset_x: float = 0.0
        self.camera_offset_y: float = 0.0
        self.is_panning: bool = False
        self.last_pan_pos: tuple[int, int] = (0, 0)
        self.pan_start_pos: tuple[int, int] = (0, 0)
        # click-to-move is sent to server; this flag shows it's pending
        self.click_moving: bool = False

        # ── Physics ─────────────────────────────────────────────────
        self.z: float = 0.0
        self.vel_z: float = 0.0
        self.is_jumping: bool = False

        # ── Movement ────────────────────────────────────────────────
        self.move_x: float = 0.0
        self.move_y: float = 0.0
        self.is_sprinting: bool = False

        # ── Dash ────────────────────────────────────────────────────
        self.dash_charge: float = 0.0
        self.is_charging_dash: bool = False
        self.dash_cooldown: float = 0.0
        # frame flag: released this frame (needed for network send)
        self.dash_released_this_frame: bool = False

        # ── Status bars (0-100) ─────────────────────────────────────
        self.hunger: float = MAX_STATUS
        self.thirst: float = MAX_STATUS
        self.bathroom: float = MAX_STATUS
        self.sleep: float = MAX_STATUS
        self.stamina: float = MAX_STATUS
        self.max_stamina: float = MAX_STATUS

        # ── Carrying / inventory ────────────────────────────────────
        self.carried_prey: list = []          # Prey objects
        self.last_hunt_time: float = 0.0
        self.prey_spawn_timer: float = 0.0

        # ── Prey tracking marks ─────────────────────────────────────
        self.prey_tracks: list[dict] = []
        self.buried_prey: list[dict] = []

        # ── Chat ────────────────────────────────────────────────────
        self.chat_input: str = ""
        self.chat_scroll: int = 0
        self.player_message: str = ""
        self.message_timer: float = 0.0

        # ── Pounce ──────────────────────────────────────────────────
        self.pounce_meter: float = 0.0
        self.max_pounce: float = 100.0
        self.pounce_charging: bool = False
        self.pounce_ready: bool = False

        # ── Map ─────────────────────────────────────────────────────
        self.player_map_x: int = 10
        self.player_map_y: int = 7

        # ── Misc ────────────────────────────────────────────────────
        self.streamer_mode: bool = False
        self.use_12h_format: bool = True
        self.music_paused: bool = False

        # ── World items / pickup feedback ───────────────────────────────
        self.world_context_menu: dict | None = None
        self.pickup_msg: str = ""
        self.pickup_timer: float = 0.0

    def load_from_config(self, cfg: dict) -> None:
        self.username = cfg.get("username", "Player")
        self.character_name = cfg.get("character_name", "")
        self.character_bio = cfg.get("character_bio", "")
        self.player_level = int(cfg.get("player_level", 1))
        self.hunting_skill = int(cfg.get("hunting_skill", 0))
        self.combat_skill = int(cfg.get("combat_skill", 0))
        self.tracking_skill = int(cfg.get("tracking_skill", 0))
        self.hunting_xp = int(cfg.get("hunting_xp", 0))
        self.combat_xp = int(cfg.get("combat_xp", 0))
        self.tracking_xp = int(cfg.get("tracking_xp", 0))
        self.use_12h_format = bool(cfg.get("use_12h_format", True))
        self.streamer_mode = bool(cfg.get("streamer_mode", False))

    def write_to_config(self, cfg: dict) -> None:
        cfg["username"] = self.username
        cfg["character_name"] = self.character_name
        cfg["character_bio"] = self.character_bio
        cfg["player_level"] = self.player_level
        cfg["hunting_skill"] = self.hunting_skill
        cfg["combat_skill"] = self.combat_skill
        cfg["tracking_skill"] = self.tracking_skill
        cfg["hunting_xp"] = self.hunting_xp
        cfg["combat_xp"] = self.combat_xp
        cfg["tracking_xp"] = self.tracking_xp
        cfg["use_12h_format"] = self.use_12h_format
        cfg["streamer_mode"] = self.streamer_mode
