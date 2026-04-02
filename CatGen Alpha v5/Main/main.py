"""CatGen Alpha v5 — main entry point.

Run with:  py Main/main.py

The game loop here is intentionally short.
- All keyboard/mouse handling is in  Main/events.py
- All drawing calls are in            Main/draw.py
- Game logic lives in                 Main/game/
- UI widgets live in                  Main/ui/
- Network code lives in               SDK/network/
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

import pygame

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
# main.py lives at  <root>/Main/main.py
# We need:  <root>/Main  on sys.path  -> so core, game, ui are importable
#           <root>/SDK   on sys.path  -> so network is importable

_MAIN_DIR = os.path.dirname(os.path.abspath(__file__))   # <root>/Main
_ROOT     = os.path.dirname(_MAIN_DIR)                    # <root>
_SDK_DIR  = os.path.join(_ROOT, "SDK")

for _p in (_MAIN_DIR, _SDK_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Logging  (write to <root>/Logs/game.log)
# ---------------------------------------------------------------------------

_log_dir = os.path.join(_ROOT, "Logs")
os.makedirs(_log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(_log_dir, "game.log"),
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="w",
)
logging.info("CatGen Alpha v5 starting ...")

# ---------------------------------------------------------------------------
# Pygame init  (must happen before anything that uses pygame.font / pygame.key)
# ---------------------------------------------------------------------------

try:
    pygame.init()
    pygame.mixer.init()
    pygame.key.set_repeat(250, 35)
except Exception as exc:
    logging.critical("Failed to initialise pygame: %s", exc)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Imports  (after pygame.init so font/key constants are ready)
# ---------------------------------------------------------------------------

from core.config import (
    load_game_config, save_game_config,
    load_controls, save_controls, init_default_controls,
    load_servers, save_servers,
)
from core.assets import load_img, get_font, capture_screenshot
from core.constants import (
    FPS, DEFAULT_PORT, WORLD_HALF,
    WHITE, BLACK, CYAN, DARK_CYAN, GRAY, LIGHT_GRAY,
    RED, GREEN, YELLOW, ORANGE, PURPLE, LIGHT_BLUE,
)
try:
    from network.client import NetworkClient  # pyright: ignore[reportMissingImports]
    from network.server import GameServer  # pyright: ignore[reportMissingImports]
    from network.lan import LanBroadcaster, scan_lan_servers  # pyright: ignore[reportMissingImports]
except ImportError:
    from SDK.network.client import NetworkClient
    from SDK.network.server import GameServer
    from SDK.network.lan import LanBroadcaster, scan_lan_servers
from game.state import PlayerState
from game.prey import Prey
from game.inventory import Inventory
from game.logic import (
    update_status_bars, update_stamina, update_chat_messages,
    update_player_map_position, update_prey,
    check_prey_collision, spawn_prey,
    track_prey, scent_mark, bury_prey,
)
from ui.renderer import (
    draw_gradient_rect, draw_grass_background,
    draw_prey_list, draw_prey_tracks,
)
from ui.hud import StatusBarContainer, draw_pounce_meter, draw_dash_charge
from ui.overlays import push_overlay, pop_overlay, top_overlay
from ui.menus import MpMenuState
from events import handle_events
from draw import draw_frame

# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("CatGen Alpha v5")
clock_pg = pygame.time.Clock()
is_fullscreen = False


def toggle_fullscreen() -> None:
    global is_fullscreen, screen, WIDTH, HEIGHT
    is_fullscreen = not is_fullscreen
    if is_fullscreen:
        info = pygame.display.Info()
        screen = pygame.display.set_mode(
            (info.current_w, info.current_h),
            pygame.FULLSCREEN,
        )
        WIDTH, HEIGHT = info.current_w, info.current_h
    else:
        WIDTH, HEIGHT = 800, 600
        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)

# ---------------------------------------------------------------------------
# Config & controls
# ---------------------------------------------------------------------------

game_config   = load_game_config()
init_default_controls()
controls      = load_controls()
saved_servers = load_servers()

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

_tp       = game_config.get("texture_pack", "Default")
sky_img   = load_img("sky.png",              texture_pack=_tp)
grass_img = load_img("grass.png",            texture_pack=_tp)
cat_img   = load_img("cat_idle.png",         texture_pack=_tp)
prey_img  = load_img("preytest1alpha.png", (50, 50), texture_pack=_tp)
paw_img   = load_img("cat_idle.png",   (24, 24), texture_pack=_tp)

try:
    _music = os.path.join(_MAIN_DIR, "assets", "creative2.ogg")
    if os.path.exists(_music):
        pygame.mixer.music.load(_music)
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)
except Exception as exc:
    logging.error("Music load failed: %s", exc)

font       = get_font("Arial", 28)
small_font = get_font("Arial", 20)
tiny_font  = get_font("Arial", 16)
aero_font  = get_font("Segoe UI", 20)

# ---------------------------------------------------------------------------
# Player state
# ---------------------------------------------------------------------------

state = PlayerState()
state.load_from_config(game_config)

# ---------------------------------------------------------------------------
# Menu / overlay state
# ---------------------------------------------------------------------------

overlay_stack = []
game_state    = "setup" if not str(game_config.get("username", "")).strip() else "menu"
menu_stack    = []
MAP_WIDTH     = 20
MAP_HEIGHT    = 15

# ---------------------------------------------------------------------------
# Multiplayer
# ---------------------------------------------------------------------------

network_client = NetworkClient()
mp_state_obj   = MpMenuState()
lan_servers    = []
lan_scanning   = False
_server        = None
_server_thread  = None
_host_setup_thread = None
_broadcaster   = None
is_host        = False
connect_status = ""


def _start_lan_host(connect_status_ref, port=DEFAULT_PORT, password="",
                    server_name="", rainbow_text=False,
                    network_client=None, state_ref=None, set_game_state_fn=None):
    global _server, _server_thread, _host_setup_thread, _broadcaster, is_host
    if _server:
        return
    _server = GameServer(port=port, password=password)
    server_obj = _server

    def _server_worker() -> None:
        try:
            server = server_obj
            if server is None:
                return
            server.start()
        except Exception as exc:
            logging.error("LAN host failed: %s", exc)
            connect_status_ref[0] = f"Host failed: {exc}"
            _server = None

    def _host_setup_worker() -> None:
        global _broadcaster, is_host
        try:
            time.sleep(0.05)
            server = server_obj
            if server is None or not server._running:
                connect_status_ref[0] = f"Host failed on port {port}"
                return

            server_label = server_name.strip() or f"{state.username}'s server"
            _broadcaster = LanBroadcaster(port=port,
                                          server_name=server_label,
                                          rainbow_text=rainbow_text,
                                          password_required=bool(password.strip()))
            _broadcaster.start()
            is_host = True
            connect_status_ref[0] = f"Hosting on port {port}"
            logging.info("LAN host started on port %d", port)

            if network_client is None or state_ref is None or set_game_state_fn is None:
                return

            for attempt in range(3):
                ok, msg = network_client.connect("127.0.0.1", port,
                                                 state_ref.username, password,
                                                 state_ref.character_name,
                                                 state_ref.character_bio)
                if ok:
                    connect_status_ref[0] = f"Hosting on port {port}"
                    set_game_state_fn("playing")
                    return
                time.sleep(0.05)
            connect_status_ref[0] = f"Hosting on port {port} (auto-connect failed)"
        except Exception as exc:
            logging.error("LAN host setup failed: %s", exc)
            connect_status_ref[0] = f"Host failed: {exc}"

    _server_thread = threading.Thread(target=_server_worker, daemon=True, name="lan-host")
    _host_setup_thread = threading.Thread(target=_host_setup_worker, daemon=True, name="lan-host-setup")
    connect_status_ref[0] = f"Starting host on port {port} …"
    _server_thread.start()
    _host_setup_thread.start()


def _stop_lan_host(network_client=None):
    global _server, _server_thread, _host_setup_thread, _broadcaster, is_host
    if _server:
        _server.stop()
        _server = None
    _server_thread = None
    _host_setup_thread = None
    if _broadcaster:
        _broadcaster.stop()
        _broadcaster = None
    if network_client is not None:
        network_client.disconnect()
    is_host = False


def _do_scan():
    global lan_servers, lan_scanning
    lan_scanning = True
    lan_servers  = scan_lan_servers(port=DEFAULT_PORT)
    lan_scanning = False

# ---------------------------------------------------------------------------
# Misc game state
# ---------------------------------------------------------------------------

char_name_input      = state.character_name
char_bio_input       = state.character_bio
char_info_focus_name = True
remapping_key        = None
music_paused         = False
is_charging_dash     = False
pounce_charging      = False
pounce_ready         = False
_upgrade_msg         = ""
_upgrade_msg_color   = (255, 255, 255)
_char_info_btn_rect  = None

status_bars = StatusBarContainer(x=10, y=10, width=150, height=15, padding=8)
inventory   = Inventory()

prey_list = []
for _ in range(3):
    prey_list.append(spawn_prey(int(state.world_x), int(state.world_y), WIDTH, HEIGHT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def set_game_state(new):
    global game_state, menu_stack
    if game_state == "setup" and new == "menu":
        if menu_stack and menu_stack[-1] == "menu":
            menu_stack.pop()
        game_state = new
        return
    if new == "playing":
        menu_stack = []
    elif game_state != new:
        if game_state != "playing" and (not menu_stack or menu_stack[-1] != game_state):
            menu_stack.append(game_state)
    game_state = new


def go_back():
    global game_state, menu_stack
    game_state = menu_stack.pop() if menu_stack else "playing"


def _near_prey():
    """True if a visible prey is within pounce range."""
    cat_wx = state.world_x + WIDTH // 2
    cat_wy = state.world_y + HEIGHT // 2
    active_prey_list = network_client.remote_prey if network_client.connected and not is_host else prey_list
    cat_r  = pygame.Rect(
        cat_wx - cat_img.get_width()  // 2,
        cat_wy - cat_img.get_height() // 2,
        cat_img.get_width(), cat_img.get_height(),
    ).inflate(200, 200)
    return any(
        pygame.Rect(p.x - 25, p.y - 25, 50, 50).colliderect(cat_r)
        for p in active_prey_list if p.state != Prey.HIDING
    )


def _cat_rect():
    wx = state.world_x + WIDTH // 2
    wy = state.world_y + HEIGHT // 2
    return pygame.Rect(
        wx - cat_img.get_width()  // 2,
        wy - cat_img.get_height() // 2,
        cat_img.get_width(), cat_img.get_height(),
    )

# ---------------------------------------------------------------------------
# Mutable reference wrappers — handle_events writes back via these
# ---------------------------------------------------------------------------

controls_ref           = [controls]
remapping_key_ref      = [remapping_key]
is_charging_dash_ref   = [is_charging_dash]
pounce_charging_ref    = [pounce_charging]
pounce_ready_ref       = [pounce_ready]
char_name_ref          = [char_name_input]
char_bio_ref           = [char_bio_input]
char_info_focus_ref    = [char_info_focus_name]
music_paused_ref       = [music_paused]
connect_status_ref     = [connect_status]
upgrade_msg_ref        = [_upgrade_msg]
upgrade_msg_color_ref  = [_upgrade_msg_color]
char_info_btn_rect_ref = [_char_info_btn_rect]
member_actions_ref     = [[]]

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

logging.info("Entering main loop")

try:
    while True:
        dt          = clock_pg.tick(FPS) / 1000.0
        dt          = min(dt, 0.05)  # cap to 50 ms
        current_fps = clock_pg.get_fps()

        # Read back values written by events.py last frame
        controls             = controls_ref[0]
        remapping_key        = remapping_key_ref[0]
        is_charging_dash     = is_charging_dash_ref[0]
        pounce_charging      = pounce_charging_ref[0]
        pounce_ready         = pounce_ready_ref[0]
        char_name_input      = char_name_ref[0]
        char_bio_input       = char_bio_ref[0]
        char_info_focus_name = char_info_focus_ref[0]
        music_paused         = music_paused_ref[0]
        connect_status       = connect_status_ref[0]
        _upgrade_msg         = upgrade_msg_ref[0]
        _upgrade_msg_color   = upgrade_msg_color_ref[0]
        active_prey_list = network_client.remote_prey if network_client.connected and not is_host else prey_list

        # ----------------------------------------------------------------
        # Events
        # ----------------------------------------------------------------
        events = pygame.event.get()

        for event in events:
            if event.type == pygame.VIDEORESIZE:
                WIDTH, HEIGHT = event.w, event.h
                if not is_fullscreen:
                    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)

        handle_events(
            events, state, controls, game_state, overlay_stack,
            set_game_state, go_back,
            push_overlay, pop_overlay, top_overlay,
            toggle_fullscreen, capture_screenshot, screen,
            network_client, inventory, active_prey_list,
            mp_state_obj, saved_servers, lan_servers,
            is_host, lan_scanning,
            _do_scan,
            lambda port=DEFAULT_PORT, password="", server_name="", rainbow_text=False: _start_lan_host(
                connect_status_ref, port, password,
                server_name, rainbow_text,
                network_client, state, set_game_state,
            ),
            lambda net_client=network_client: _stop_lan_host(net_client),
            save_servers,
            save_controls,
            controls_ref, remapping_key_ref,
            is_charging_dash_ref, pounce_charging_ref, pounce_ready_ref,
            char_name_ref, char_bio_ref, char_info_focus_ref,
            music_paused_ref, connect_status_ref,
            upgrade_msg_ref, upgrade_msg_color_ref,
            char_info_btn_rect_ref, member_actions_ref,
            cat_img, WIDTH, HEIGHT,
        )

        # Re-read refs updated this frame
        controls         = controls_ref[0]
        is_charging_dash = is_charging_dash_ref[0]
        pounce_charging  = pounce_charging_ref[0]
        pounce_ready     = pounce_ready_ref[0]
        music_paused     = music_paused_ref[0]
        connect_status   = connect_status_ref[0]

        # ----------------------------------------------------------------
        # Game logic
        # ----------------------------------------------------------------

        if game_state == "playing" and not overlay_stack:
            keys         = pygame.key.get_pressed()
            is_sprinting = bool(keys[controls["SPRINT"]]) and state.stamina > 0
            state.is_sprinting = is_sprinting

            weight_factor = max(0.3, 1.0 - len(state.carried_prey) * 0.1)
            speed = (8 if is_sprinting else 4) * 60 * dt * weight_factor

            move_x = move_y = 0.0
            if keys[controls["MOVE_LEFT"]]:  move_x -= speed
            if keys[controls["MOVE_RIGHT"]]: move_x += speed
            if keys[controls["MOVE_UP"]]:    move_y -= speed
            if keys[controls["MOVE_DOWN"]]:  move_y += speed

            if move_x != 0 or move_y != 0:
                state.camera_offset_x = 0.0
                state.camera_offset_y = 0.0

            state.world_x = max(-WORLD_HALF, min(WORLD_HALF,
                                                   state.world_x + int(move_x)))
            state.world_y = max(-WORLD_HALF, min(WORLD_HALF,
                                                   state.world_y + int(move_y)))

            if is_charging_dash and state.dash_cooldown <= 0 and state.stamina > 5:
                state.dash_charge = min(1.5, state.dash_charge + dt)

            near = _near_prey()

            if not near and keys[controls["JUMP"]] and not state.is_jumping:
                state.vel_z      = 8.0
                state.is_jumping = True
            if state.is_jumping:
                state.z    += state.vel_z
                state.vel_z -= 0.4
                if state.z <= 0:
                    state.z = state.vel_z = 0.0
                    state.is_jumping = False

            if near and keys[controls["JUMP"]]:
                pounce_charging    = True
                state.pounce_meter = min(state.max_pounce, state.pounce_meter + 4)
                if state.pounce_meter >= state.max_pounce:
                    pounce_ready = True
            else:
                if pounce_charging:
                    if pounce_ready:
                        check_prey_collision(state, active_prey_list, inventory,
                                             _cat_rect, WIDTH, HEIGHT)
                    pounce_charging = pounce_ready = False
                state.pounce_meter = max(0.0, state.pounce_meter - 200 * dt)

            pounce_charging_ref[0] = pounce_charging
            pounce_ready_ref[0]    = pounce_ready

            update_status_bars(state, dt)
            update_stamina(state, dt)
            update_chat_messages(state, dt)
            # Pickup toast timer
            if state.pickup_timer > 0:
                state.pickup_timer = max(0.0, state.pickup_timer - dt)
                if state.pickup_timer <= 0:
                    state.pickup_msg = ""
            update_player_map_position(state, MAP_WIDTH, MAP_HEIGHT)
            if not network_client.connected or is_host:
                update_prey(state, prey_list, dt, WIDTH, HEIGHT)
            if network_client.connected and is_host:
                network_client.send_prey_sync(prey_list)

            if network_client.connected:
                network_client.tick_interpolation()
                snap = network_client.self_player_snapshot
                if snap:
                    state.world_x = float(snap.get("x", state.world_x))
                    state.world_y = float(snap.get("y", state.world_y))
                    state.z = float(snap.get("z", state.z))

            if network_client.connected:
                network_client.send_input(
                    up          = bool(keys[controls["MOVE_UP"]]),
                    down        = bool(keys[controls["MOVE_DOWN"]]),
                    left        = bool(keys[controls["MOVE_LEFT"]]),
                    right       = bool(keys[controls["MOVE_RIGHT"]]),
                    sprint      = is_sprinting,
                    jump        = bool(keys[controls["JUMP"]]),
                    dash_charge = is_charging_dash,
                    dash_release= False,
                )

        # ----------------------------------------------------------------
        # Rendering
        # ----------------------------------------------------------------

        # Prey drawn here because prey_list is local to main.py
        if game_state == "playing":
            draw_grass_background(screen, grass_img,
                                                                    int(state.world_x), int(state.world_y), WIDTH, HEIGHT)
            draw_prey_list(screen, active_prey_list, prey_img,
                                                     int(state.world_x), int(state.world_y),
                           0, 0, WIDTH, HEIGHT, small_font)
            draw_prey_tracks(screen, paw_img, state.prey_tracks,
                                                         int(state.world_x), int(state.world_y),
                             0, 0)

        # draw.py renders everything else
        draw_frame(
            screen, game_state, overlay_stack, state,
            grass_img, cat_img, prey_img, paw_img, sky_img,
            font, small_font, tiny_font, aero_font,
            status_bars, inventory, network_client,
            WIDTH, HEIGHT, current_fps, is_fullscreen,
            music_paused, is_charging_dash,
            top_overlay,
            char_name_input, char_bio_input, char_info_focus_name,
            char_info_btn_rect_ref,
            _upgrade_msg, _upgrade_msg_color,
            mp_state_obj, lan_servers, saved_servers,
            is_host, lan_scanning, connect_status,
            MAP_WIDTH, MAP_HEIGHT, controls, remapping_key,
            state.camera_offset_x, state.camera_offset_y,
            member_actions_ref,
        )

        # Pounce / dash meters drawn last (need local _near_prey)
        if game_state == "playing":
            cat_sx = WIDTH  // 2 - state.camera_offset_x
            cat_sy = HEIGHT // 2 - state.z - state.camera_offset_y
            draw_pounce_meter(screen, state.pounce_meter, state.max_pounce,
                              int(cat_sx), int(cat_sy),
                              tiny_font, _near_prey() or state.pounce_meter > 0,
                              streamer_mode=state.streamer_mode)
            draw_dash_charge(screen, state.dash_charge, 1.5,
                             WIDTH, HEIGHT, is_charging_dash,
                             tiny_font,
                             streamer_mode=state.streamer_mode)
        pygame.display.flip()  # single flip per frame, for all game states

except (SystemExit, KeyboardInterrupt):
    pass
except Exception as exc:
    logging.critical("Uncaught exception: %s", exc, exc_info=True)
finally:
    state.write_to_config(game_config)
    save_game_config(game_config)
    save_controls(controls)
    if network_client.connected:
        network_client.disconnect()
    _stop_lan_host()
    pygame.quit()
    sys.exit()
