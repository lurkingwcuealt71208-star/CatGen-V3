"""Configuration loading / saving for game state and controls.

All config is persisted as JSON.  Game config lives in config.json next to the
executable; controls are stored in the platform user-data directory.
"""

from __future__ import annotations

import json
import logging
import os
import sys


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resource_path(relative_path: str) -> str:
    """Get absolute path to a bundled resource (works with PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    # config.py lives at Main/core/ — go up to Main/, then up to project root
    if os.path.basename(base) == "core":
        base = os.path.dirname(base)          # Main/core -> Main
    if os.path.basename(base) == "Main":
        base = os.path.dirname(base)          # Main -> project root
    return os.path.join(base, relative_path)


def get_save_path(filename: str) -> str:
    """Return a platform-appropriate path inside the user data directory."""
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        app_data = os.path.join(home, "AppData", "Local", "CatGen")
    elif sys.platform == "darwin":
        app_data = os.path.join(home, "Library", "Application Support", "CatGen")
    else:
        app_data = os.path.join(home, ".local", "share", "CatGen")
    os.makedirs(app_data, exist_ok=True)
    return os.path.join(app_data, filename)


# ---------------------------------------------------------------------------
# Game config (config.json in project root)
# ---------------------------------------------------------------------------

_CONFIG_PATH = resource_path("config.json")

_DEFAULT_GAME_CONFIG = {
    "username": "Player",
    "character_name": "",
    "character_bio": "",
    "hunting_skill": 0,
    "combat_skill": 0,
    "tracking_skill": 0,
    "hunting_xp": 0,
    "combat_xp": 0,
    "tracking_xp": 0,
    "player_level": 1,
    "use_12h_format": True,
    "texture_pack": "Default",
    "streamer_mode": False,
    "declined_shortcut": False,
    "version": "2026.03.23",
}


def load_game_config() -> dict:
    """Load config.json, returning defaults on failure."""
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r") as f:
                data = json.load(f)
            # Merge with defaults for missing keys
            for k, v in _DEFAULT_GAME_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception as exc:
            logging.error("Error loading config: %s", exc)
    return dict(_DEFAULT_GAME_CONFIG)


def save_game_config(config_data: dict) -> None:
    """Write config_data to config.json."""
    try:
        with open(_CONFIG_PATH, "w") as f:
            json.dump(config_data, f, indent=4)
    except Exception as exc:
        logging.error("Error saving config: %s", exc)


# ---------------------------------------------------------------------------
# Controls (controls.json in user data dir)
# ---------------------------------------------------------------------------

_CONTROLS_PATH = get_save_path("controls.json")

# Key constants will be populated once pygame is initialised.  We store them
# as plain ints so the file can be loaded without pygame.
DEFAULT_CONTROLS: dict[str, int] = {}  # filled by init_default_controls()


def init_default_controls() -> None:
    """Populate DEFAULT_CONTROLS with pygame key constants.

    Must be called *after* ``pygame.init()``.
    """
    import pygame  # noqa: delayed import

    DEFAULT_CONTROLS.update({
        "MOVE_UP": pygame.K_w,
        "MOVE_DOWN": pygame.K_s,
        "MOVE_LEFT": pygame.K_a,
        "MOVE_RIGHT": pygame.K_d,
        "SPRINT": pygame.K_LSHIFT,
        "MEOW": pygame.K_1,
        "CHAT": pygame.K_t,
        "MUSIC": pygame.K_m,
        "TRACK": pygame.K_e,
        "SCENT": pygame.K_f,
        "BURY": pygame.K_b,
        "DASH": pygame.K_q,
        "JUMP": pygame.K_SPACE,
        "STREAMER": pygame.K_F9,
        "INVENTORY": pygame.K_i,
        "MENU": pygame.K_ESCAPE,
        "DROP_PREY": pygame.K_g,
    })


def load_controls() -> dict[str, int]:
    """Load key bindings, falling back to defaults for any missing keys."""
    controls = dict(DEFAULT_CONTROLS)
    try:
        if os.path.exists(_CONTROLS_PATH):
            with open(_CONTROLS_PATH, "r") as f:
                loaded = json.load(f)
            for k in DEFAULT_CONTROLS:
                if k in loaded:
                    controls[k] = loaded[k]
    except Exception as exc:
        logging.error("Error loading controls: %s", exc)
    return controls


def save_controls(controls: dict[str, int]) -> None:
    """Persist current key bindings."""
    try:
        with open(_CONTROLS_PATH, "w") as f:
            json.dump(controls, f)
    except Exception as exc:
        logging.error("Error saving controls: %s", exc)


# ---------------------------------------------------------------------------
# Server list (servers.json in user data dir)
# ---------------------------------------------------------------------------

_SERVERS_PATH = get_save_path("servers.json")


def load_servers() -> list[dict]:
    if os.path.exists(_SERVERS_PATH):
        try:
            with open(_SERVERS_PATH, "r") as f:
                return json.load(f)
        except Exception as exc:
            logging.error("Error loading servers: %s", exc)
    return []


def save_servers(servers: list[dict]) -> None:
    try:
        with open(_SERVERS_PATH, "w") as f:
            json.dump(servers, f, indent=4)
    except Exception as exc:
        logging.error("Error saving servers: %s", exc)
