"""events.py — all keyboard and mouse event handling for CatGen.

Called once per frame from main.py via handle_events().
Keeps main.py clean by moving all input logic here.
"""

from __future__ import annotations

import time
import threading

import pygame

from core.constants import WORLD_HALF
from game.prey import Prey
from game.logic import track_prey, scent_mark, bury_prey, check_prey_collision


def handle_events(
    events,          # list from pygame.event.get()
    state,           # PlayerState
    controls,        # dict of action -> pygame key constant
    game_state,      # current str (e.g. "playing", "menu")
    overlay_stack,   # list[str]
    # callbacks so events.py stays decoupled from heavy game objects
    set_game_state,
    go_back,
    push_overlay,
    pop_overlay,
    top_overlay,
    toggle_fullscreen,
    capture_screenshot,
    screen,
    # objects needed for specific actions
    network_client,
    inventory,
    prey_list,
    mp_state_obj,
    saved_servers,
    lan_servers,
    is_host,
    lan_scanning,
    do_scan,
    start_lan_host,
    stop_lan_host,
    save_servers_fn,
    save_controls_fn,
    controls_ref,    # list[dict] wrapper so caller can see updated controls
    remapping_key_ref,  # list[str|None] wrapper
    is_charging_dash_ref,  # list[bool] wrapper
    pounce_charging_ref,   # list[bool] wrapper
    pounce_ready_ref,      # list[bool] wrapper
    char_name_ref,         # list[str] wrapper
    char_bio_ref,          # list[str] wrapper
    char_info_focus_ref,   # list[bool] wrapper
    music_paused_ref,      # list[bool] wrapper
    connect_status_ref,    # list[str] wrapper
    upgrade_msg_ref,       # list[str] wrapper
    upgrade_msg_color_ref, # list[tuple] wrapper
    char_info_btn_rect_ref, # list[Rect|None] wrapper
    member_actions_ref,     # list[list[tuple]] wrapper
    cat_img,
    WIDTH, HEIGHT,
):
    """Process all pygame events for the current frame.

    Uses mutable single-element lists (ref pattern) so callers can read
    back changed values without Python 'nonlocal' gymnastics.
    """
    controls      = controls_ref[0]
    remapping_key = remapping_key_ref[0]

    for event in events:
        if event.type == pygame.QUIT:
            raise SystemExit

        # Window resize
        if event.type == pygame.VIDEORESIZE:
            pass  # main.py handles the resize itself via RESIZABLE flag

        # Global hotkeys — always active regardless of game state
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                toggle_fullscreen()
            if event.key == pygame.K_F12:
                capture_screenshot(screen)
            if event.key == pygame.K_BACKSLASH and game_state == "playing" and network_client.connected and is_host:
                push_overlay(overlay_stack, "members")

        if event.type == pygame.KEYUP and event.key == pygame.K_BACKSLASH and top_overlay(overlay_stack) == "members":
            pop_overlay(overlay_stack)

        # ----------------------------------------------------------------
        # Overlay input — topmost overlay gets the event first
        # ----------------------------------------------------------------
        top = top_overlay(overlay_stack)

        if top == "inventory":
            if event.type == pygame.KEYDOWN and (
                event.key == pygame.K_ESCAPE
                or event.key == controls.get("INVENTORY")
            ):
                pop_overlay(overlay_stack)
                continue
            _hunger_ref = [state.hunger]
            inventory.handle_input(
                event, WIDTH, HEIGHT,
                hunger_ref=_hunger_ref,
                prey_list=prey_list,
                carried_prey=state.carried_prey,
                last_hunt_time=state.last_hunt_time,
                push_overlay_fn=lambda n: push_overlay(overlay_stack, n),
                draw_gradient_fn=lambda *a: None,
            )
            state.hunger = _hunger_ref[0]
            if network_client.connected:
                network_client.send_prey_sync(prey_list)
            continue

        elif top == "char_info":
            cn, cb, cf, action = _handle_char_info(
                event,
                char_name_ref[0], char_bio_ref[0], char_info_focus_ref[0],
                state, network_client, overlay_stack, pop_overlay,
                lambda n: save_game_config_from_state(state, n),
            )
            char_name_ref[0]       = cn
            char_bio_ref[0]        = cb
            char_info_focus_ref[0] = cf
            continue

        elif top == "upgrades":
            action = _handle_upgrades(
                event, WIDTH, HEIGHT, state.player_level,
                overlay_stack, pop_overlay,
                upgrade_msg_ref, upgrade_msg_color_ref,
            )
            continue

        elif top == "chat":
            if event.type == pygame.MOUSEWHEEL:
                step = event.y if event.y else 0
                state.chat_scroll = max(0, min(240, state.chat_scroll + step * 3))
                continue
            _handle_chat(event, state, network_client, overlay_stack, pop_overlay)
            continue

        elif top == "members":
            _handle_members(event, network_client, member_actions_ref, is_host)
            continue

        # ----------------------------------------------------------------
        # State-specific input
        # ----------------------------------------------------------------
        if game_state == "playing" and not overlay_stack:
            _handle_playing(
                event, state, controls, is_charging_dash_ref,
                pounce_charging_ref, pounce_ready_ref,
                prey_list, inventory, network_client,
                overlay_stack, push_overlay,
                set_game_state, music_paused_ref,
                char_name_ref, char_bio_ref, char_info_focus_ref,
                char_info_btn_rect_ref, cat_img, WIDTH, HEIGHT,
            )

        elif game_state == "menu":
            _handle_menu(event, go_back, set_game_state, music_paused_ref)

        elif game_state == "multiplayer":
            _handle_multiplayer(
                event, mp_state_obj, lan_servers, saved_servers,
                is_host, lan_scanning, go_back,
                do_scan, start_lan_host, stop_lan_host, save_servers_fn,
                state, network_client, connect_status_ref, set_game_state,
                WIDTH, HEIGHT,
            )

        elif game_state == "setup":
            _handle_setup(event, state, network_client, set_game_state)

        elif game_state == "keybinds":
            _handle_keybinds(
                event, controls_ref, remapping_key_ref,
                save_controls_fn, go_back, WIDTH, HEIGHT,
            )

        else:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                go_back()

    # Write back controls in case keybinds were remapped
    controls_ref[0] = controls


# ============================================================
# Private helpers (one per overlay / game-state)
# ============================================================

def _handle_char_info(event, char_name, char_bio, focus_name,
                      state, network_client, overlay_stack, pop_overlay,
                      save_fn):
    from ui.overlays import handle_character_info_input
    from core.config import save_game_config
    char_name, char_bio, focus_name, action = handle_character_info_input(
        event, char_name, char_bio, focus_name)
    if action == "save":
        state.character_name = char_name
        state.character_bio  = char_bio
        from core.config import load_game_config
        cfg = load_game_config()
        state.write_to_config(cfg)
        save_game_config(cfg)
        if network_client.connected:
            network_client.send_profile_update(state.character_name, state.character_bio)
        pop_overlay(overlay_stack)
    elif action == "cancel":
        char_name = state.character_name
        char_bio  = state.character_bio
        pop_overlay(overlay_stack)
    return char_name, char_bio, focus_name, action


def save_game_config_from_state(state, cfg):
    """Helper used by char_info handler."""
    pass  # actual save happens inside _handle_char_info


def _handle_upgrades(event, WIDTH, HEIGHT, player_level,
                     overlay_stack, pop_overlay,
                     upgrade_msg_ref, upgrade_msg_color_ref):
    from ui.overlays import handle_upgrades_input
    action = handle_upgrades_input(event, WIDTH, HEIGHT, player_level)
    if action == "close":
        upgrade_msg_ref[0] = ""
        pop_overlay(overlay_stack)
    elif action.startswith("unlock:"):
        _, status, msg = action.split(":", 2)
        upgrade_msg_ref[0]       = msg
        upgrade_msg_color_ref[0] = (0, 220, 100) if status == "ok" else (220, 60, 60)


def _handle_chat(event, state, network_client, overlay_stack, pop_overlay):
    if event.type != pygame.KEYDOWN:
        return
    if event.key == pygame.K_RETURN:
        msg = state.chat_input.strip()
        if msg:
            if not network_client.connected:
                full = {
                    "kind": "chat",
                    "time": time.time(),
                    "username": state.username,
                    "display_name": state.character_name or state.username,
                    "message": msg,
                }
                with network_client.lock:
                    network_client.chat_messages.append(full)
            state.player_message = msg
            state.message_timer  = 5.0
            state.chat_scroll = 0
            if network_client.connected:
                network_client.send_chat(msg, state.character_name)
                network_client.send_typing(False)
        state.chat_input = ""
        pop_overlay(overlay_stack)
    elif event.key == pygame.K_ESCAPE:
        state.chat_input = ""
        state.chat_scroll = 0
        if network_client.connected:
            network_client.send_typing(False)
        pop_overlay(overlay_stack)
    elif event.key == pygame.K_BACKSPACE:
        state.chat_input = state.chat_input[:-1]
    elif event.unicode.isprintable():
        if not state.chat_input and network_client.connected:
            network_client.send_typing(True)
        state.chat_input += event.unicode


def _handle_members(event, network_client, member_actions_ref, is_host):
    if not is_host or event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
        return
    from ui.menus import handle_members_input
    handle_members_input(event, network_client, member_actions_ref[0], is_host)


def _handle_playing(event, state, controls, is_charging_dash_ref,
                    pounce_charging_ref, pounce_ready_ref,
                    prey_list, inventory, network_client,
                    overlay_stack, push_overlay,
                    set_game_state, music_paused_ref,
                    char_name_ref, char_bio_ref, char_info_focus_ref,
                    char_info_btn_rect_ref, cat_img, WIDTH, HEIGHT):
    if event.type == pygame.KEYDOWN:
        k = event.key
        if k == controls["MENU"]:
            set_game_state("menu")
        elif k == controls["INVENTORY"]:
            push_overlay(overlay_stack, "inventory")
        elif k == controls["CHAT"]:
            push_overlay(overlay_stack, "chat")
        elif k == controls.get("STREAMER"):
            state.streamer_mode = not state.streamer_mode
        elif k == controls.get("TRACK"):
            track_prey(state, prey_list, WIDTH, HEIGHT)
            state.tracking_skill = min(100, state.tracking_skill + 1)
            if state.tracking_skill >= 100:
                state.player_level   += 1
                state.tracking_skill = 0
        elif k == controls.get("SCENT"):
            scent_mark(state)
        elif k == controls.get("BURY"):
            bury_prey(state)
        elif k == controls.get("MUSIC"):
            _toggle_music(music_paused_ref)
        elif k == controls.get("DROP_PREY") and state.carried_prey:
            p = state.carried_prey.pop()
            p.x, p.y = state.world_x + WIDTH // 2, state.world_y + HEIGHT // 2
            p.state = Prey.DEAD
            prey_list.append(p)
            if network_client.connected:
                network_client.send_prey_sync(prey_list)
        elif k == controls.get("DASH"):
            is_charging_dash_ref[0] = True

    if event.type == pygame.KEYUP:
        if event.key == controls.get("DASH") and is_charging_dash_ref[0]:
            is_charging_dash_ref[0] = False
            if (state.dash_charge > 0.3
                    and state.dash_cooldown <= 0
                    and state.stamina > 5):
                keys_now = pygame.key.get_pressed()
                dx = dy = 0
                spd = state.dash_charge * 600
                if keys_now[controls["MOVE_LEFT"]]:  dx -= spd
                if keys_now[controls["MOVE_RIGHT"]]: dx += spd
                if keys_now[controls["MOVE_UP"]]:    dy -= spd
                if keys_now[controls["MOVE_DOWN"]]:  dy += spd
                if dx == 0 and dy == 0:
                    dy = -spd
                import time as _time   # avoid shadowing top-level time
                dt = 1 / 60            # single-frame estimate for impulse
                state.world_x = max(-WORLD_HALF,
                                    min(WORLD_HALF, state.world_x + int(dx * dt)))
                state.world_y = max(-WORLD_HALF,
                                    min(WORLD_HALF, state.world_y + int(dy * dt)))
                state.dash_cooldown = 1.0
                state.stamina = max(0, state.stamina - 15)
            state.dash_charge = 0.0

    # Right-click drag — desktop-icon placement (local-only, never sent to server)
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
        state.is_panning    = True
        state.last_pan_pos  = event.pos
        state.pan_start_pos = event.pos
        # Any right-click dismisses an open world context menu
        state.world_context_menu = None

    if event.type == pygame.MOUSEMOTION and state.is_panning:
        dx = event.pos[0] - state.last_pan_pos[0]
        dy = event.pos[1] - state.last_pan_pos[1]
        state.camera_offset_x -= dx
        state.camera_offset_y -= dy
        state.last_pan_pos = event.pos

    if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
        mx, my = event.pos
        sx0, sy0 = state.pan_start_pos
        state.is_panning = False
        # Treat as a right-click (not a drag) when mouse barely moved
        if abs(mx - sx0) < 5 and abs(my - sy0) < 5:
            # Convert screen click to world coords
            wx_click = state.world_x + mx + state.camera_offset_x
            wy_click = state.world_y + my + state.camera_offset_y
            state.world_context_menu = None
            for preyobj in prey_list:
                if preyobj.state != Prey.DEAD:
                    continue
                dist = ((preyobj.x - wx_click) ** 2 +
                        (preyobj.y - wy_click) ** 2) ** 0.5
                if dist < 60:
                    state.world_context_menu = {"pos": (mx, my), "prey": preyobj}
                    break
            else:
                if network_client.connected:
                    network_client.send_click_move(wx_click, wy_click)

    # Left-click on Character Info button  /  world context menu pickup
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        # World context menu — pick up dead prey
        if state.world_context_menu:
            cmx, cmy = state.world_context_menu["pos"]
            if pygame.Rect(cmx, cmy, 180, 32).collidepoint(event.pos):
                preyobj = state.world_context_menu.get("prey")
                if preyobj is not None and preyobj in prey_list:
                    prey_list.remove(preyobj)
                    from game.inventory import Item
                    inv_item = Item(
                        getattr(preyobj, "name", "Mouse"),
                        (200, 150, 100),
                        "A fresh catch.",
                    )
                    inv_item.is_prey = True
                    inv_item.prey_hunger = 20
                    inv_item.prey_ref = preyobj
                    inventory.add_item(inv_item)
                    state.pickup_msg = f"Picked up {getattr(preyobj, 'name', 'Mouse')}"
                    state.pickup_timer = 2.0
                    if network_client.connected:
                        network_client.send_prey_sync(prey_list)
            state.world_context_menu = None
        # Character Info button
        rect = char_info_btn_rect_ref[0]
        if rect and rect.collidepoint(event.pos):
            char_name_ref[0]       = state.character_name
            char_bio_ref[0]        = state.character_bio
            char_info_focus_ref[0] = True
            push_overlay(overlay_stack, "char_info")


def _handle_menu(event, go_back, set_game_state, music_paused_ref):
    from ui.menus import handle_menu_input
    action = handle_menu_input(event)
    if action == "playing":    go_back()
    elif action == "quit":     raise SystemExit
    elif action == "toggle_music":
        _toggle_music(music_paused_ref)
    elif action == "change_username":
        set_game_state("setup")
    elif action:
        set_game_state(action)


def _handle_multiplayer(event, mp_state_obj, lan_servers, saved_servers,
                        is_host, lan_scanning, go_back,
                        do_scan, start_lan_host, stop_lan_host, save_servers_fn,
                        state, network_client, connect_status_ref,
                        set_game_state, WIDTH, HEIGHT):
    from ui.menus import handle_multiplayer_input
    action = handle_multiplayer_input(
        event, mp_state_obj,
        lan_servers, saved_servers, is_host, WIDTH, HEIGHT,
    )
    if action == "back":
        go_back()
    elif action == "scan" and not lan_scanning:
        threading.Thread(target=do_scan, daemon=True).start()
    elif action == "stop_host":
        stop_lan_host(network_client)
    elif action == "save_servers":
        save_servers_fn(saved_servers)
    elif action.startswith("host:"):
        parts = action.split(":", 4)
        _, port_s, pw, server_name, rainbow_flag = (parts + ["", "", "", ""])[:5]
        port_s = port_s.strip()
        if (not port_s or not port_s.isdigit()
                or not (1 <= int(port_s) <= 65535)):
            connect_status_ref[0] = f"Invalid port: '{port_s}'"
        else:
            start_lan_host(int(port_s), pw, server_name, rainbow_flag == "1")
    elif action == "disconnect":
        network_client.disconnect()
        connect_status_ref[0] = "Disconnected"
        mp_state_obj.connecting = False
    elif action.startswith("join:"):
        if mp_state_obj.connecting:
            return
        _, ip, port_s, pw = action.split(":", 3)
        port_s = port_s.strip()
        if (not port_s or not port_s.isdigit()
                or not (1 <= int(port_s) <= 65535)):
            connect_status_ref[0] = f"Invalid port: '{port_s}'"
            return

        mp_state_obj.connecting = True
        connect_status_ref[0] = f"Connecting to {ip}:{port_s} …"

        def _join_worker() -> None:
            try:
                ok, msg = network_client.connect(
                    ip, int(port_s), state.username, pw,
                    state.character_name, state.character_bio,
                )
                connect_status_ref[0] = msg
                if ok:
                    set_game_state("playing")
            finally:
                mp_state_obj.connecting = False

        threading.Thread(target=_join_worker, daemon=True, name="mp-join").start()


def _handle_setup(event, state, network_client, set_game_state):
    from ui.menus import handle_setup_input
    from core.config import load_game_config, save_game_config
    previous_username = state.username
    new_name, action = handle_setup_input(event, state.username)
    state.username = new_name
    if action == "confirm":
        cfg = load_game_config()
        cfg["username"]      = state.username
        save_game_config(cfg)
        if network_client is not None and network_client.connected and state.username != previous_username:
            network_client.send_username_change(state.username)
        set_game_state("menu")


def _handle_keybinds(event, controls_ref, remapping_key_ref,
                     save_controls_fn, go_back, WIDTH, HEIGHT):
    from ui.menus import handle_keybinds_input
    updated, new_remap, action = handle_keybinds_input(
        event, controls_ref[0], remapping_key_ref[0], WIDTH, HEIGHT)
    controls_ref[0]      = updated
    remapping_key_ref[0] = new_remap
    if action == "back":
        save_controls_fn(controls_ref[0])
        go_back()


def _toggle_music(music_paused_ref):
    import pygame as _pg
    if _pg.mixer.music.get_busy() and not music_paused_ref[0]:
        _pg.mixer.music.pause()
        music_paused_ref[0] = True
    else:
        _pg.mixer.music.unpause()
        music_paused_ref[0] = False
