"""draw.py — all per-frame rendering for CatGen.

Called once per frame from main.py via draw_frame().
Keeps main.py clean by moving all pygame draw calls here.
"""

from __future__ import annotations

import time

import pygame

from core.constants import CYAN, WHITE, YELLOW


def draw_frame(
    screen,
    game_state,      # str: "playing", "menu", etc.
    overlay_stack,   # list[str]
    state,           # PlayerState
    # render helpers
    grass_img, cat_img, prey_img, paw_img,
    sky_img,
    font, small_font, tiny_font, aero_font,
    # HUD / overlay state
    status_bars,
    inventory,
    network_client,
    WIDTH, HEIGHT,
    current_fps,
    is_fullscreen,
    music_paused,
    is_charging_dash,
    top_overlay,
    char_name_input, char_bio_input, char_info_focus_name,
    char_info_btn_rect_ref,   # list[Rect|None]: caller reads this back
    upgrade_msg, upgrade_msg_color,
    # multiplayer menu state
    mp_state_obj,
    lan_servers, saved_servers,
    is_host, lan_scanning,
    connect_status,
    MAP_WIDTH, MAP_HEIGHT,
    controls,
    remapping_key,
    camera_offset_x, camera_offset_y,
    member_actions_ref,
):
    """Draw everything for the current frame.

    Returns nothing — all rendering goes directly to `screen`.
    char_info_btn_rect_ref[0] is updated with the Rect from draw_bottom_hud.
    """
    from ui.renderer import (
        draw_grass_background, draw_prey_list, draw_carried_prey, draw_cat,
        draw_remote_players, draw_prey_tracks, draw_gradient_rect,
    )
    from ui.hud import (
        StatusBarContainer, draw_bottom_hud, draw_chat,
        draw_speech_bubble, draw_pounce_meter, draw_dash_charge,
        draw_pickup_toast, draw_connection_status,
    )
    from ui.menus import (
        draw_menu, draw_multiplayer_menu, draw_map, draw_credits,
        draw_changelog, draw_setup_screen, draw_keybinds,
        draw_members_overlay,
    )
    from ui.overlays import (
        top_overlay as _top_overlay,
        draw_character_info, draw_upgrades_menu,
    )

    if game_state == "playing":
        _draw_playing(
            screen, state, overlay_stack,
            grass_img, cat_img, prey_img, paw_img,
            font, small_font, tiny_font, aero_font,
            status_bars, inventory, network_client,
            is_host,
            WIDTH, HEIGHT, current_fps, is_fullscreen,
            is_charging_dash, top_overlay,
            char_name_input, char_bio_input, char_info_focus_name,
            char_info_btn_rect_ref,
            upgrade_msg, upgrade_msg_color,
            camera_offset_x, camera_offset_y,
            draw_grass_background, draw_prey_list, draw_carried_prey,
            draw_cat, draw_remote_players, draw_prey_tracks, draw_gradient_rect,
            draw_bottom_hud, draw_chat, draw_speech_bubble,
            draw_pounce_meter, draw_dash_charge, draw_pickup_toast,
            draw_character_info, draw_upgrades_menu,
            member_actions_ref,
        )

    elif game_state == "menu":
        draw_menu(screen, WIDTH, HEIGHT, state.username, music_paused, font, small_font)

    elif game_state == "multiplayer":
        draw_multiplayer_menu(
            screen, WIDTH, HEIGHT,
            mp_state_obj.state,
            lan_servers, saved_servers,
            mp_state_obj.selected_idx,
            mp_state_obj.scroll_offset,
            is_host, lan_scanning,
            edit_name   = mp_state_obj.edit_name,
            edit_ip     = mp_state_obj.edit_ip,
            edit_port   = mp_state_obj.edit_port,
            edit_pass   = mp_state_obj.edit_pass,
            direct_ip   = mp_state_obj.direct_ip,
            direct_port = mp_state_obj.direct_port,
            direct_pass = mp_state_obj.direct_pass,
            host_name   = mp_state_obj.host_server_name,
            host_port   = mp_state_obj.host_port,
            host_pass   = mp_state_obj.host_pass,
            host_rainbow_text = mp_state_obj.host_rainbow_text,
            input_focus = mp_state_obj.input_focus,
            connected=network_client.connected,
            network_client=network_client,
            connect_status=connect_status,
            font=font, small_font=small_font, tiny_font=tiny_font,
        )

    elif game_state == "map":
        draw_map(screen, WIDTH, HEIGHT,
                 MAP_WIDTH, MAP_HEIGHT,
                 state.player_map_x, state.player_map_y,
                 font, small_font)

    elif game_state == "changelog":
        draw_changelog(screen, WIDTH, HEIGHT, font, small_font)

    elif game_state == "setup":
        draw_setup_screen(screen, WIDTH, HEIGHT,
                          state.username, font, small_font, tiny_font)

    elif game_state == "keybinds":
        draw_keybinds(screen, WIDTH, HEIGHT,
                      controls, remapping_key, font, small_font, tiny_font)


# ============================================================
# Private helpers
# ============================================================

def _draw_playing(
    screen, state, overlay_stack,
    grass_img, cat_img, prey_img, paw_img,
    font, small_font, tiny_font, aero_font,
    status_bars, inventory, network_client,
    is_host,
    WIDTH, HEIGHT, current_fps, is_fullscreen,
    is_charging_dash, top_overlay,
    char_name_input, char_bio_input, char_info_focus_name,
    char_info_btn_rect_ref,
    upgrade_msg, upgrade_msg_color,
    camera_offset_x, camera_offset_y,
    draw_grass_background, draw_prey_list, draw_carried_prey,
    draw_cat, draw_remote_players, draw_prey_tracks, draw_gradient_rect,
    draw_bottom_hud, draw_chat, draw_speech_bubble,
    draw_pounce_meter, draw_dash_charge, draw_pickup_toast,
    draw_character_info, draw_upgrades_menu,
    member_actions_ref,
):
    from core.constants import CYAN, WHITE, YELLOW
    from ui.hud import draw_connection_status
    from ui.menus import draw_members_overlay

    # Grass + prey + tracks are already drawn by main.py before draw_frame is
    # called. Do NOT draw grass here — it would erase the prey sprites.

    # Buried prey mounds (world elements — no camera offset)
    for mound in state.buried_prey:
        age = time.time() - mound.get("time", 0)
        if age < 300:
            mx_ = WIDTH  // 2 + (mound["x"] - state.world_x)
            my_ = HEIGHT // 2 + (mound["y"] - state.world_y)
            pygame.draw.ellipse(screen, (139, 69, 19),
                                (int(mx_) - 10, int(my_) - 5, 20, 10))

    # Remote players (world elements — no local camera offset)
    if network_client.connected:
        draw_remote_players(
            screen, cat_img, paw_img, network_client,
            state.world_x, state.world_y,
            0, 0,
            WIDTH, HEIGHT, small_font, tiny_font,
        )

    # Local player
    cat_sx = WIDTH  // 2 - camera_offset_x
    cat_sy = HEIGHT // 2 - state.z - camera_offset_y

    display_name = state.character_name or state.username or "Player"
    name_lbl = small_font.render(display_name, True, CYAN)
    screen.blit(name_lbl,
                (int(cat_sx) - name_lbl.get_width() // 2,
                 int(cat_sy) - cat_img.get_height() // 2 - 30))
    if state.character_bio:
        bio_text = state.character_bio[:48]
        bio_lbl = tiny_font.render(bio_text, True, (200, 240, 255))
        screen.blit(bio_lbl,
                    (int(cat_sx) - bio_lbl.get_width() // 2,
                     int(cat_sy) - cat_img.get_height() // 2 - 12))

    draw_carried_prey(screen, state.carried_prey, prey_img,
                      int(cat_sx), int(cat_sy))

    if not state.streamer_mode:
        draw_cat(screen, cat_img, int(cat_sx), int(cat_sy))

    draw_speech_bubble(screen, state.player_message,
                       int(cat_sx), int(cat_sy) - 60, small_font)
    if top_overlay(overlay_stack) == "chat" and state.chat_input:
        draw_speech_bubble(screen, "typing...",
                           int(cat_sx), int(cat_sy) - 98, small_font)

    # Status bar background panel
    if not state.streamer_mode:
        stats_bg = pygame.Surface((265, 160), pygame.SRCALPHA)
        stats_bg.fill((0, 0, 0, 150))
        pygame.draw.rect(stats_bg, CYAN, stats_bg.get_rect(), 2)
        screen.blit(stats_bg, (5, 5))
    status_bars.render(screen, state, tiny_font)

    # Chat
    chat_messages = []
    typing_active = False
    if network_client.connected:
        with network_client.lock:
            chat_messages = list(network_client.chat_messages)
            typing_active = any(network_client.other_typing.values())
    draw_chat(screen, WIDTH, HEIGHT,
              chat_messages,
              top_overlay(overlay_stack) == "chat",
              state.chat_input,
              typing_active,
              state.chat_scroll,
              small_font,
              aero_font)

    draw_connection_status(screen, WIDTH, network_client, small_font, is_host=is_host)

    # Pounce / dash meters — drawn by main.py (needs _near_prey check)
    # See main.py for draw_pounce_meter and draw_dash_charge calls.

    # World context menu (right-click pick-up prompt for dead prey)
    # Draw before HUD so HUD remains the top-most layer.
    if state.world_context_menu:
        cmx, cmy = state.world_context_menu["pos"]
        prey_obj = state.world_context_menu.get("prey")
        lbl_text = f"Pick up {getattr(prey_obj, 'name', 'Mouse')} x1" if prey_obj else "Pick up"
        pygame.draw.rect(screen, (30, 30, 30), (cmx, cmy, 180, 32))
        pygame.draw.rect(screen, CYAN,         (cmx, cmy, 180, 32), 1)
        t = small_font.render(lbl_text, True, WHITE)
        screen.blit(t, (cmx + 8, cmy + 7))

    # Bottom HUD — returns Rect used for char-info button click detection
    char_info_btn_rect_ref[0] = draw_bottom_hud(
        screen, WIDTH, HEIGHT, small_font, tiny_font,
        state.player_level, state.use_12h_format,
        streamer_mode=state.streamer_mode,
    )

    # Version / hints
    if not state.streamer_mode:
        ver = small_font.render("CatGen Alpha v5", True, CYAN)
        screen.blit(ver, (10, HEIGHT - 100))
        hint_ss = tiny_font.render("F12: Screenshot", True, (255, 200, 200))
        screen.blit(hint_ss, (10, HEIGHT - 78))

    if not top_overlay(overlay_stack):
        hint_fs = tiny_font.render("F11: Fullscreen", True, WHITE)
        screen.blit(hint_fs, (WIDTH - hint_fs.get_width() - 10, 10))

    # F3 debug overlay
    if pygame.key.get_pressed()[pygame.K_F3]:
        lines = [
            f"FPS: {current_fps:.1f}",
            f"Pos: {state.world_x}, {state.world_y}",
            f"Z: {state.z:.1f}",
            f"Net: {'online' if network_client.connected else 'offline'}",
            f"Win: {WIDTH}x{HEIGHT} ({'FS' if is_fullscreen else 'Win'})",
        ]
        for i, ln in enumerate(lines):
            s = tiny_font.render(ln, True, YELLOW)
            screen.blit(s, (WIDTH - s.get_width() - 10, 50 + i * 18))

    # Overlay layers drawn on top
    top = top_overlay(overlay_stack)
    if top == "inventory":
        inventory.draw(
            screen, WIDTH, HEIGHT, prey_img,
            state.hunting_skill, state.combat_skill, state.tracking_skill,
            font, small_font, tiny_font,
            draw_gradient_fn=draw_gradient_rect,
        )
    elif top == "char_info":
        draw_character_info(
            screen, WIDTH, HEIGHT,
            char_name_input, char_bio_input,
            char_info_focus_name,
            font, small_font, tiny_font,
        )
    elif top == "upgrades":
        draw_upgrades_menu(screen, WIDTH, HEIGHT,
                           state.player_level, font, small_font, tiny_font,
                           upgrade_msg, upgrade_msg_color)
    elif top == "members":
        member_actions_ref[0] = draw_members_overlay(
            screen, WIDTH, HEIGHT, network_client, is_host, small_font, tiny_font,
        )

    draw_pickup_toast(screen, WIDTH, HEIGHT, small_font,
                      state.pickup_msg, state.pickup_timer)
