"""All menu screens and their input handlers.

Each draw_* function returns nothing.
Each handle_*_input function returns an action string or None.
The caller (main.py) acts on returned action strings.

Action strings follow the pattern "<target_state>" or "<verb>:<arg>".
"""

from __future__ import annotations

import colorsys
import time
import math
from datetime import datetime

import pygame

from core.constants import (
    BLACK, CYAN, DARK_CYAN, GRAY, GREEN, LIGHT_GRAY, RED, WHITE, YELLOW,
)
from ui.renderer import draw_gradient_rect

# ---------------------------------------------------------------------------
# Setup screen
# ---------------------------------------------------------------------------

def draw_setup_screen(surface: pygame.Surface,
                      width: int, height: int,
                      username: str,
                      font: pygame.font.Font,
                      small_font: pygame.font.Font,
                      tiny_font: pygame.font.Font) -> None:
    draw_gradient_rect(surface, BLACK, DARK_CYAN, (0, 0, width, height))
    title = font.render("Username Setup", True, CYAN)
    surface.blit(title, (width // 2 - title.get_width() // 2, 100))
    prompt = small_font.render("Enter your username:", True, WHITE)
    surface.blit(prompt, (width // 2 - prompt.get_width() // 2, 200))
    bw, bh = 300, 40
    bx, by = width // 2 - bw // 2, 240
    pygame.draw.rect(surface, (20, 20, 20), (bx, by, bw, bh))
    pygame.draw.rect(surface, CYAN, (bx, by, bw, bh), 2)
    surface.blit(small_font.render(username, True, WHITE), (bx + 10, by + 10))
    surface.blit(
        tiny_font.render("Press ENTER to continue", True, (150, 150, 150)),
        (width // 2 - 90, 300),
    )


def handle_setup_input(event: pygame.event.Event,
                       username: str) -> tuple[str, str]:
    """Returns (new_username, action).

    action is "" normally, "confirm" when user presses Enter with a valid name.
    """
    if event.type != pygame.KEYDOWN:
        return username, ""
    if event.key == pygame.K_RETURN:
        stripped = username.strip()
        if stripped:
            return stripped, "confirm"
    elif event.key == pygame.K_BACKSPACE:
        return username[:-1], ""
    elif event.unicode.isprintable() and len(username) < 15:
        if username == "Player":
            return event.unicode, ""
        return username + event.unicode, ""
    return username, ""


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def draw_menu(surface: pygame.Surface,
              width: int, height: int,
              username: str,
              music_paused: bool,
              font: pygame.font.Font,
              small_font: pygame.font.Font) -> None:
    draw_gradient_rect(surface, BLACK, DARK_CYAN, (0, 0, width, height))
    title = font.render("CatGen Alpha — Main Menu", True, CYAN)
    surface.blit(title, (width // 2 - title.get_width() // 2, 50))
    user_t = small_font.render(f"Logged in as: {username}", True, WHITE)
    surface.blit(user_t, (width // 2 - user_t.get_width() // 2, 90))

    options = [
        "R — Resume Game",
        "M — View Map",
        "P — Multiplayer",
        "U — Change Username",
        "C — Credits",
        "L — Changelog",
        "K — Keybinds",
        f"T — Toggle Music ({'Off' if music_paused else 'On'})",
        "Q — Quit Game",
    ]
    for i, opt in enumerate(options):
        bw, bh = 320, 35
        bx = width // 2 - bw // 2
        by = 150 + i * 45 - bh // 2
        pygame.draw.rect(surface, (20, 20, 20), (bx, by, bw, bh))
        pygame.draw.rect(surface, CYAN, (bx, by, bw, bh), 1)
        t = small_font.render(opt, True, WHITE)
        surface.blit(t, (width // 2 - t.get_width() // 2,
                         150 + i * 45 - t.get_height() // 2))

    time_t = small_font.render(
        f"Current Time: {datetime.now().strftime('%H:%M:%S')}", True, LIGHT_GRAY)
    surface.blit(time_t, (width // 2 - time_t.get_width() // 2, height - 50))


def handle_menu_input(event: pygame.event.Event) -> str:
    """Return an action string or ''."""
    if event.type != pygame.KEYDOWN:
        return ""
    mapping = {
        pygame.K_ESCAPE: "playing",
        pygame.K_r: "playing",
        pygame.K_m: "map",
        pygame.K_p: "multiplayer",
        pygame.K_u: "change_username",
        pygame.K_c: "credits",
        pygame.K_l: "changelog",
        pygame.K_k: "keybinds",
        pygame.K_q: "quit",
        pygame.K_t: "toggle_music",
    }
    return mapping.get(event.key, "")


# ---------------------------------------------------------------------------
# Multiplayer menu
# ---------------------------------------------------------------------------

MP_LIST    = "list"
MP_ADD     = "add"
MP_EDIT    = "edit"
MP_DIRECT  = "direct"
MP_HOST    = "host"


def _draw_rainbow_text(surface: pygame.Surface,
                       font: pygame.font.Font,
                       text: str,
                       x: int, y: int,
                       phase: float | None = None) -> None:
    phase = time.time() if phase is None else phase
    cursor_x = x
    for i, char in enumerate(text):
        hue = ((phase * 0.18) + i * 0.07) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
        surf = font.render(char, True, (int(r * 255), int(g * 255), int(b * 255)))
        surface.blit(surf, (cursor_x, y))
        cursor_x += surf.get_width()


def draw_multiplayer_menu(
        surface: pygame.Surface,
        width: int, height: int,
        mp_state: str,
        lan_servers: list,
        saved_servers: list,
        selected_idx: int,
        scroll_offset: int,
        is_host: bool,
        lan_scanning: bool,
        connected: bool = False,
        network_client=None,
        # edit / direct connect field values
        edit_name: str = "", edit_ip: str = "",
        edit_port: str = "25565", edit_pass: str = "",
        direct_ip: str = "", direct_port: str = "25565",
        direct_pass: str = "",
        host_name: str = "",
        host_port: str = "25565", host_pass: str = "",
        host_rainbow_text: bool = False,
        input_focus: str = "ip",
        connect_status: str = "",
        font: pygame.font.Font | None = None,
        small_font: pygame.font.Font | None = None,
        tiny_font: pygame.font.Font | None = None,
) -> None:
    draw_gradient_rect(surface, BLACK, DARK_CYAN, (0, 0, width, height))

    if mp_state == MP_LIST:
        _draw_mp_list(surface, width, height,
                      lan_servers, saved_servers, selected_idx, scroll_offset,
                      is_host, connected, lan_scanning, connect_status,
                      network_client,
                      font, small_font, tiny_font)
    else:
        _draw_mp_form(surface, width, height, mp_state,
                      edit_name, edit_ip, edit_port, edit_pass,
                      direct_ip, direct_port, direct_pass,
                      host_name, host_port, host_pass, host_rainbow_text, input_focus,
                      font, small_font, tiny_font)


def _draw_mp_list(surface, width, height,
                  lan_servers, saved_servers, selected_idx, scroll_offset,
                  is_host, connected, lan_scanning, connect_status,
                  network_client,
                  font, small_font, tiny_font):
    title = font.render("Play Multiplayer", True, CYAN)
    surface.blit(title, (width // 2 - title.get_width() // 2, 20))

    roster_visible = network_client is not None and getattr(network_client, "connected", False)
    list_w = max(260, width - (320 if roster_visible else 100))
    list_rect = pygame.Rect(50, 80, list_w, height - 220)
    pygame.draw.rect(surface, (10, 10, 10), list_rect)
    pygame.draw.rect(surface, CYAN, list_rect, 1)

    col_name_x = list_rect.x + 10
    col_addr_x = list_rect.x + 290
    col_play_x = list_rect.x + list_rect.width - 126

    # Column headers
    pygame.draw.line(surface, DARK_CYAN,
                     (list_rect.x, list_rect.y + 26),
                     (list_rect.right, list_rect.y + 26), 1)
    surface.blit(tiny_font.render("Server Name", True, LIGHT_GRAY),
                 (col_name_x, list_rect.y + 6))
    surface.blit(tiny_font.render("Address / Uptime", True, LIGHT_GRAY),
                 (col_addr_x, list_rect.y + 6))
    surface.blit(tiny_font.render("Players/Ping", True, LIGHT_GRAY),
                 (col_play_x, list_rect.y + 6))

    all_servers = (lan_servers or []) + saved_servers
    row_h = 56
    visible = (list_rect.height - 30) // row_h
    for i in range(visible):
        idx = i + scroll_offset
        if idx >= len(all_servers):
            break
        s = all_servers[idx]
        ry = list_rect.y + 30 + i * row_h
        entry_r = pygame.Rect(list_rect.x + 5, ry, list_rect.width - 10, row_h - 4)
        if idx == selected_idx:
            pygame.draw.rect(surface, (0, 60, 60), entry_r)
            pygame.draw.rect(surface, WHITE, entry_r, 1)
        else:
            pygame.draw.rect(surface, (25, 25, 25), entry_r)

        tag = "(LAN) " if idx < len(lan_servers) else ""
        name = tag + s.get("name", f"Server {s['ip']}")
        rainbow = bool(s.get("rainbow_text", False))
        if rainbow:
            _draw_rainbow_text(surface, small_font, name, entry_r.x + 8, entry_r.y + 5)
        else:
            surface.blit(small_font.render(name, True, CYAN),
                         (entry_r.x + 8, entry_r.y + 5))

        if s.get("password_required", False):
            lock = tiny_font.render("Locked", True, (255, 180, 120))
            surface.blit(lock, (entry_r.right - lock.get_width() - 10, entry_r.y + 6))

        port = s.get('port', 25565)
        uptime = float(s.get("uptime", 0.0) or 0.0)
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        uptime_txt = f"Up {hours:02d}:{minutes:02d}:{seconds:02d}"
        surface.blit(tiny_font.render(f"{s['ip']}:{port}", True, LIGHT_GRAY),
                     (col_addr_x, entry_r.y + 7))
        surface.blit(tiny_font.render(uptime_txt, True, (160, 220, 220)),
                     (col_addr_x, entry_r.y + 27))
        player_count = s.get("players", "?")
        ping_txt = f"{player_count} players"
        if "ping" in s:
            ping_txt = f"{s.get('ping','?')} ms"
        surface.blit(tiny_font.render(ping_txt, True, (130, 130, 130)),
                     (col_play_x, entry_r.y + 18))

    # Status message
    if connect_status:
        st = tiny_font.render(connect_status, True, YELLOW
                              if "…" in connect_status else
                              (GREEN if "OK" in connect_status or "joined" in connect_status.lower() else RED))
        surface.blit(st, (width // 2 - st.get_width() // 2, list_rect.bottom + 6))

    if roster_visible:
        panel = pygame.Rect(list_rect.right + 12, 80, max(160, width - list_rect.right - 62), 170)
        pygame.draw.rect(surface, (12, 12, 12), panel)
        pygame.draw.rect(surface, CYAN, panel, 1)
        surface.blit(tiny_font.render("Connected Players", True, WHITE), (panel.x + 12, panel.y + 8))
        rows = []
        with network_client.lock:
            rows.append((network_client.username, network_client.display_name, "You"))
            for data in network_client.other_players.values():
                rows.append((data.get("username", "Player"), data.get("display_name", ""), data.get("bio", "")))
        y = panel.y + 32
        for username, display_name, bio in rows[:5]:
            label = display_name or username
            surface.blit(small_font.render(label, True, CYAN), (panel.x + 12, y))
            if display_name and display_name != username:
                surface.blit(tiny_font.render(f"@{username}", True, LIGHT_GRAY), (panel.x + 12, y + 20))
            if bio and bio != "You":
                surface.blit(tiny_font.render(str(bio)[:18], True, (160, 220, 220)), (panel.x + 90, y + 20))
            y += 32

    # Buttons
    host_lbl = "Stop Hosting" if is_host else "Host LAN"
    buttons = [
        ("Scan LAN",      0, 0), ("Join",          1, 0), ("IP / Localhost", 2, 0),
        (host_lbl,        0, 1), ("Add Server",     1, 1), ("Edit Server",    2, 1),
        ("Delete Server", 0, 2), ("Back",           1, 2), ("Disconnect", 2, 2),
    ]
    btn_w, btn_h = 120, 30
    start_x = width // 2 - (3 * btn_w + 20) // 2
    start_y = height - 110
    for label, col, row in buttons:
        bx = start_x + col * (btn_w + 10)
        by = start_y + row * (btn_h + 8)
        enabled = True
        if label in ("Join", "Edit Server", "Delete Server") and selected_idx == -1:
            enabled = False
        if label == "Disconnect" and not connected:
            enabled = False
        pygame.draw.rect(surface, (20, 20, 20), (bx, by, btn_w, btn_h))
        pygame.draw.rect(surface, CYAN if enabled else (50, 50, 50),
                         (bx, by, btn_w, btn_h), 1)
        t = tiny_font.render(label, True, WHITE if enabled else GRAY)
        surface.blit(t, (bx + btn_w // 2 - t.get_width() // 2,
                         by + btn_h // 2 - t.get_height() // 2))
        if label == "Scan LAN" and lan_scanning:
            cx, cy = bx + btn_w - 14, by + btn_h // 2
            a = math.radians((time.time() * 360) % 360)
            pygame.draw.circle(surface, CYAN, (cx, cy), 7, 1)
            pygame.draw.line(surface, CYAN, (cx, cy),
                             (cx + int(math.cos(a) * 7),
                              cy + int(math.sin(a) * 7)), 2)


def _draw_mp_form(surface, width, height, mp_state,
                  edit_name, edit_ip, edit_port, edit_pass,
                  direct_ip, direct_port, direct_pass,
                  host_name, host_port, host_pass, host_rainbow_text, input_focus,
                  font, small_font, tiny_font):
    titles = {
        MP_ADD: "Add Server",
        MP_EDIT: "Edit Server",
        MP_DIRECT: "Direct Connect",
        MP_HOST: "Host LAN",
    }
    title = font.render(titles.get(mp_state, ""), True, CYAN)
    surface.blit(title, (width // 2 - title.get_width() // 2, 50))

    if mp_state == MP_DIRECT:
        fields = [("Server Address", direct_ip, "ip"),
                  ("Port",          direct_port, "port"),
                  ("Password (optional)", direct_pass, "pass")]
    elif mp_state == MP_HOST:
        fields = [("Server Name", host_name, "name"),
                  ("Port (default 25565)", host_port, "port"),
                  ("Password (optional)", host_pass, "pass"),
                  ("Rainbow Title", "On" if host_rainbow_text else "Off", "rainbow")]
    else:
        fields = [("Server Name",    edit_name, "name"),
                  ("Server Address", edit_ip,   "ip"),
                  ("Port",           edit_port, "port"),
                  ("Password",       edit_pass, "pass")]

    for i, (label, value, fid) in enumerate(fields):
        ly = 120 + i * 70
        surface.blit(small_font.render(label, True, WHITE), (width // 2 - 150, ly))
        box_r = pygame.Rect(width // 2 - 150, ly + 25, 300, 30)
        pygame.draw.rect(surface, (10, 10, 10), box_r)
        border = WHITE if input_focus == fid else CYAN
        pygame.draw.rect(surface, border, box_r, 2 if input_focus == fid else 1)
        cursor = "_" if input_focus == fid and int(time.time() * 2) % 2 else ""
        if fid == "rainbow":
            shown_value = value
        elif "Password" in label:
            shown_value = "•" * len(value)
        else:
            shown_value = value
        surface.blit(small_font.render(shown_value + cursor, True, WHITE),
                     (box_r.x + 5, box_r.y + 5))

    hint_text = "TAB to switch fields | ENTER to submit"
    if mp_state == MP_HOST:
        hint_text = "TAB to switch fields | ENTER to submit | Rainbow Title toggles the server browser color"
    hint = tiny_font.render(hint_text, True, LIGHT_GRAY)
    surface.blit(hint, (width // 2 - hint.get_width() // 2, height - 138))

    bw, bh = 140, 35
    bx1, by1 = width // 2 - 150, height - 100
    bx2, by2 = width // 2 + 10, height - 100
    for bx, by, lbl in [(bx1, by1, "Connect" if mp_state in (MP_DIRECT, MP_HOST) else "Save"),
                         (bx2, by2, "Cancel")]:
        pygame.draw.rect(surface, (20, 20, 20), (bx, by, bw, bh))
        pygame.draw.rect(surface, CYAN, (bx, by, bw, bh), 1)
        t = small_font.render(lbl, True, WHITE)
        surface.blit(t, (bx + bw // 2 - t.get_width() // 2,
                         by + bh // 2 - t.get_height() // 2))


# ---------------------------------------------------------------------------
# Multiplayer input handler
# ---------------------------------------------------------------------------

class MpMenuState:
    """Mutable state carried by the MP menu."""
    def __init__(self) -> None:
        self.state: str = MP_LIST
        self.selected_idx: int = -1
        self.scroll_offset: int = 0
        self.connecting: bool = False
        self.input_focus: str = "ip"
        self.edit_name: str = ""
        self.edit_ip: str = ""
        self.edit_port: str = "25565"
        self.edit_pass: str = ""
        self.direct_ip: str = ""
        self.direct_port: str = "25565"
        self.direct_pass: str = ""
        self.host_port: str = "25565"
        self.host_pass: str = ""
        self.host_server_name: str = ""
        self.host_rainbow_text: bool = False


def handle_multiplayer_input(
        event: pygame.event.Event,
        mps: MpMenuState,
        lan_servers: list,
        saved_servers: list,
        is_host: bool,
        width: int, height: int,
) -> str:
    """Return action string or ''. Mutates mps in place.

    Action strings:
      "back"                    — go back to main menu
      "join:<ip>:<port>:<pass>" — attempt connection
      "scan"                    — start LAN scan thread
      "host"                    — start LAN server
      "stop_host"               — stop server
      "save_server"             — saved_servers was appended by caller
      "playing"                 — already connected, switch state
      ""                        — no action
    """
    all_servers = (lan_servers or []) + saved_servers

    if mps.state == MP_LIST:
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            list_rect = pygame.Rect(50, 80, width - 100, height - 220)

            # List click
            if list_rect.collidepoint(mx, my):
                row_idx = (my - list_rect.y - 30) // 56 + mps.scroll_offset
                if 0 <= row_idx < len(all_servers):
                    mps.selected_idx = row_idx
                return ""

            # Scroll
            if event.button == 4:
                mps.scroll_offset = max(0, mps.scroll_offset - 1)
            elif event.button == 5:
                mps.scroll_offset = min(max(0, len(all_servers) - 1),
                                        mps.scroll_offset + 1)

            # Buttons
            host_lbl = "Stop Hosting" if is_host else "Host LAN"
            buttons = [
                ("Scan LAN",      0, 0), ("Join",          1, 0), ("IP / Localhost", 2, 0),
                (host_lbl,        0, 1), ("Add Server",     1, 1), ("Edit Server",    2, 1),
                ("Delete Server", 0, 2), ("Back",           1, 2),
                ("Disconnect",   2, 2),
            ]
            btn_w, btn_h = 120, 30
            start_x = width // 2 - (3 * btn_w + 20) // 2
            start_y = height - 110
            for label, col, row in buttons:
                bx = start_x + col * (btn_w + 10)
                by = start_y + row * (btn_h + 8)
                if pygame.Rect(bx, by, btn_w, btn_h).collidepoint(mx, my):
                    if label == "Scan LAN":
                        return "scan"
                    if label == "Stop Hosting":
                        return "stop_host"
                    if label == "Join" and mps.selected_idx != -1:
                        s = all_servers[mps.selected_idx]
                        if s.get("password_required", False) and not s.get("password", ""):
                            mps.state = MP_DIRECT
                            mps.direct_ip = s.get("ip", "")
                            mps.direct_port = str(s.get("port", 25565))
                            mps.direct_pass = ""
                            mps.input_focus = "pass"
                            return ""
                        return f"join:{s['ip']}:{s.get('port', 25565)}:{s.get('password', '')}"
                    if label == "IP / Localhost":
                        mps.state = MP_DIRECT
                        mps.direct_ip = mps.direct_ip or "127.0.0.1"
                        mps.direct_port = mps.direct_port or "25565"
                        mps.input_focus = "ip"
                    if label == "Host LAN":
                        mps.state = MP_HOST
                        mps.host_port = mps.host_port or "25565"
                        mps.input_focus = "name"
                    if label == "Add Server":
                        mps.state = MP_ADD
                        mps.edit_name = mps.edit_ip = mps.edit_pass = ""
                        mps.edit_port = "25565"
                        mps.input_focus = "name"
                    if label == "Edit Server" and mps.selected_idx != -1:
                        si = mps.selected_idx - len(lan_servers)
                        if si >= 0 and si < len(saved_servers):
                            s = saved_servers[si]
                            mps.edit_name = s.get("name", "")
                            mps.edit_ip   = s["ip"]
                            mps.edit_port = str(s.get("port", 25565))
                            mps.edit_pass = s.get("password", "")
                            mps.state = MP_EDIT
                            mps.input_focus = "name"
                    if label == "Delete Server" and mps.selected_idx != -1:
                        si = mps.selected_idx - len(lan_servers)
                        if 0 <= si < len(saved_servers):
                            saved_servers.pop(si)
                            mps.selected_idx = -1
                            return "save_servers"
                    if label == "Back":
                        return "back"
                    if label == "Disconnect":
                        return "disconnect"
                    return ""

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "back"
            if event.key == pygame.K_RETURN and mps.selected_idx != -1:
                s = all_servers[mps.selected_idx]
                if s.get("password_required", False) and not s.get("password", ""):
                    mps.state = MP_DIRECT
                    mps.direct_ip = s.get("ip", "")
                    mps.direct_port = str(s.get("port", 25565))
                    mps.direct_pass = ""
                    mps.input_focus = "pass"
                    return ""
                return f"join:{s['ip']}:{s.get('port', 25565)}:{s.get('password', '')}"

    elif mps.state in (MP_ADD, MP_EDIT, MP_DIRECT, MP_HOST):
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            bw, bh = 140, 35
            bx1, by1 = width // 2 - 150, height - 100
            bx2, by2 = width // 2 + 10,  height - 100
            if pygame.Rect(bx1, by1, bw, bh).collidepoint(mx, my):
                return _mp_form_confirm(mps, saved_servers, lan_servers)
            if pygame.Rect(bx2, by2, bw, bh).collidepoint(mx, my):
                mps.state = MP_LIST if mps.state != MP_DIRECT else MP_LIST
                return ""
            # Field focus
            fields = (["name", "ip", "port", "pass"]
                      if mps.state in (MP_ADD, MP_EDIT) else
                      ["ip", "port", "pass"] if mps.state == MP_DIRECT else
                      ["name", "port", "pass", "rainbow"])
            for i, fid in enumerate(fields):
                field_rect = pygame.Rect(width // 2 - 150, 120 + i * 70 + 25, 300, 30)
                if field_rect.collidepoint(mx, my):
                    if mps.state == MP_HOST and fid == "rainbow":
                        mps.host_rainbow_text = not mps.host_rainbow_text
                        mps.input_focus = fid
                        return ""
                    mps.input_focus = fid

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                mps.state = MP_LIST
            elif event.key == pygame.K_RETURN:
                if mps.state == MP_HOST and mps.input_focus == "rainbow":
                    mps.host_rainbow_text = not mps.host_rainbow_text
                else:
                    return _mp_form_confirm(mps, saved_servers, lan_servers)
            elif event.key == pygame.K_TAB:
                fields = (["name", "ip", "port", "pass"]
                          if mps.state in (MP_ADD, MP_EDIT) else
                          ["ip", "port", "pass"] if mps.state == MP_DIRECT else
                          ["name", "port", "pass", "rainbow"])
                idx = fields.index(mps.input_focus) if mps.input_focus in fields else 0
                mps.input_focus = fields[(idx + 1) % len(fields)]
            elif mps.state == MP_HOST and mps.input_focus == "rainbow" and event.key in (pygame.K_SPACE, pygame.K_y, pygame.K_n):
                if event.key in (pygame.K_SPACE, pygame.K_y):
                    mps.host_rainbow_text = not mps.host_rainbow_text
                else:
                    mps.host_rainbow_text = False
            elif event.key == pygame.K_BACKSPACE:
                _mp_form_backspace(mps)
            elif event.unicode.isprintable():
                _mp_form_type(mps, event.unicode)
    return ""


def _mp_form_confirm(mps: MpMenuState,
                     saved_servers: list,
                     lan_servers: list) -> str:
    if mps.state == MP_HOST:
        port_s = mps.host_port if mps.host_port else "25565"
        try:
            port_i = int(port_s)
            if not (1 <= port_i <= 65535):
                mps.host_port = "25565"
                return ""
        except ValueError:
            mps.host_port = "25565"
            return ""
        mps.state = MP_LIST
        host_name = mps.host_server_name.strip()
        return f"host:{port_s}:{mps.host_pass}:{host_name}:{int(mps.host_rainbow_text)}"
    if mps.state == MP_DIRECT:
        if mps.direct_ip:
            port_s = mps.direct_port if mps.direct_port else "25565"
            try:
                port_i = int(port_s)
                if not (1 <= port_i <= 65535):
                    mps.direct_port = "25565"
                    return ""
            except ValueError:
                mps.direct_port = "25565"
                return ""
            return f"join:{mps.direct_ip}:{port_s}:{mps.direct_pass}"
        return ""
    # Validate port for saved server forms too
    port_s = mps.edit_port if mps.edit_port else "25565"
    try:
        port_i = int(port_s)
        if not (1 <= port_i <= 65535):
            mps.edit_port = "25565"
    except ValueError:
        mps.edit_port = "25565"
    new_s = {"name": mps.edit_name, "ip": mps.edit_ip,
              "port": mps.edit_port, "password": mps.edit_pass}
    if mps.state == MP_ADD:
        saved_servers.append(new_s)
    else:
        si = mps.selected_idx - len(lan_servers)
        if 0 <= si < len(saved_servers):
            saved_servers[si] = new_s
    mps.state = MP_LIST
    return "save_servers"


def _mp_form_backspace(mps: MpMenuState) -> None:
    f = mps.input_focus
    if mps.state == MP_DIRECT:
        if f == "ip":   mps.direct_ip   = mps.direct_ip[:-1]
        elif f == "port": mps.direct_port = mps.direct_port[:-1]
        elif f == "pass": mps.direct_pass = mps.direct_pass[:-1]
    elif mps.state == MP_HOST:
        if f == "name": mps.host_server_name = mps.host_server_name[:-1]
        elif f == "port": mps.host_port = mps.host_port[:-1]
        elif f == "pass": mps.host_pass = mps.host_pass[:-1]
    else:
        if f == "name": mps.edit_name = mps.edit_name[:-1]
        elif f == "ip":   mps.edit_ip   = mps.edit_ip[:-1]
        elif f == "port": mps.edit_port = mps.edit_port[:-1]
        elif f == "pass": mps.edit_pass = mps.edit_pass[:-1]


def _mp_form_type(mps: MpMenuState, char: str) -> None:
    f = mps.input_focus
    if mps.state == MP_DIRECT:
        if f == "ip":   mps.direct_ip   += char
        elif f == "port" and char.isdigit() and len(mps.direct_port) < 5:
            mps.direct_port += char
        elif f == "pass": mps.direct_pass += char
    elif mps.state == MP_HOST:
        if f == "name": mps.host_server_name += char
        elif f == "port" and char.isdigit() and len(mps.host_port) < 5:
            mps.host_port += char
        elif f == "pass": mps.host_pass += char
    else:
        if f == "name": mps.edit_name += char
        elif f == "ip":   mps.edit_ip   += char
        elif f == "port" and char.isdigit() and len(mps.edit_port) < 5:
            mps.edit_port += char
        elif f == "pass": mps.edit_pass += char


# ---------------------------------------------------------------------------
# Map screen
# ---------------------------------------------------------------------------

def draw_map(surface: pygame.Surface,
             width: int, height: int,
             map_w: int, map_h: int,
             player_map_x: int, player_map_y: int,
             font: pygame.font.Font,
             small_font: pygame.font.Font) -> None:
    surface.fill(BLACK)
    title = font.render("Game Map", True, WHITE)
    surface.blit(title, (width // 2 - title.get_width() // 2, 20))
    cell = 15
    sx = width  // 2 - (map_w * cell) // 2
    sy = height // 2 - (map_h * cell) // 2
    for row in range(map_h):
        for col in range(map_w):
            color = RED if (col == player_map_x and row == player_map_y) else GREEN
            x, y = sx + col * cell, sy + row * cell
            pygame.draw.rect(surface, color, (x, y, cell, cell))
            pygame.draw.rect(surface, WHITE, (x, y, cell, cell), 1)
    pos_t = small_font.render(
        f"Player Position: ({player_map_x}, {player_map_y})", True, WHITE)
    surface.blit(pos_t, (width // 2 - pos_t.get_width() // 2,
                          sy + map_h * cell + 20))
    leg = small_font.render("Red dot = Your position", True, RED)
    surface.blit(leg, (width // 2 - leg.get_width() // 2, height - 80))
    inst = small_font.render("Press ESC to return", True, WHITE)
    surface.blit(inst, (width // 2 - inst.get_width() // 2, height - 50))


# ---------------------------------------------------------------------------
# Credits, Changelog, Keybinds
# ---------------------------------------------------------------------------

_CREDITS_TEXT = [
    "CatGen Alpha",
    "",
    "Development: CatGen Team",
    "Engine: pygame-ce",
    "",
    "Press ESC to go back",
]

_CHANGELOG_TEXT = [
    "v0.3 — Full architecture rewrite",
    "  Server-authoritative movement",
    "  Modular codebase (core/network/game/ui)",
    "  New multiplayer server browser",
    "",
    "v0.2 — LAN multiplayer + stability",
    "v0.1 — Initial release",
    "",
    "Press ESC to go back",
]


def draw_credits(surface: pygame.Surface, width: int, height: int,
                 font: pygame.font.Font, small_font: pygame.font.Font) -> None:
    draw_gradient_rect(surface, BLACK, DARK_CYAN, (0, 0, width, height))
    for i, line in enumerate(_CREDITS_TEXT):
        f = font if i == 0 else small_font
        t = f.render(line, True, CYAN if i == 0 else WHITE)
        surface.blit(t, (width // 2 - t.get_width() // 2, 80 + i * 35))


def draw_changelog(surface: pygame.Surface, width: int, height: int,
                   font: pygame.font.Font, small_font: pygame.font.Font) -> None:
    draw_gradient_rect(surface, BLACK, DARK_CYAN, (0, 0, width, height))
    title = font.render("Changelog", True, CYAN)
    surface.blit(title, (width // 2 - title.get_width() // 2, 30))
    for i, line in enumerate(_CHANGELOG_TEXT):
        t = small_font.render(line, True, WHITE)
        surface.blit(t, (width // 2 - t.get_width() // 2, 80 + i * 28))


def draw_keybinds(surface: pygame.Surface, width: int, height: int,
                  controls: dict, remapping_key: str | None,
                  font: pygame.font.Font, small_font: pygame.font.Font,
                  tiny_font: pygame.font.Font) -> None:
    surface.fill(BLACK)
    title = font.render("Settings — Keybinds", True, WHITE)
    surface.blit(title, (width // 2 - title.get_width() // 2, 30))
    instr = small_font.render(
        "Click an action to remap. Press ESC to save/return.", True, LIGHT_GRAY)
    surface.blit(instr, (width // 2 - instr.get_width() // 2, 70))
    y_off = 110
    col1 = 50
    col2 = width // 2 + 20
    for i, (action, key) in enumerate(controls.items()):
        bx = col1 if i < 8 else col2
        by = y_off + (i % 8) * 45
        color = (255, 200, 0) if remapping_key == action else GRAY
        pygame.draw.rect(surface, color, (bx, by, 330, 35))
        pygame.draw.rect(surface, WHITE, (bx, by, 330, 35), 1)
        key_name = pygame.key.name(key) if isinstance(key, int) else str(key)
        t = tiny_font.render(f"{action}: {key_name}", True, BLACK)
        surface.blit(t, (bx + 10, by + 10))
    back = small_font.render("Press ESC to return", True, WHITE)
    surface.blit(back, (width // 2 - back.get_width() // 2, height - 40))


def draw_members_overlay(surface: pygame.Surface,
                         width: int, height: int,
                         network_client,
                         is_host: bool,
                         small_font: pygame.font.Font,
                         tiny_font: pygame.font.Font) -> list[tuple[int, pygame.Rect, pygame.Rect]]:
    overlay_surf = pygame.Surface((width, height), pygame.SRCALPHA)
    overlay_surf.fill((0, 0, 0, 150))
    surface.blit(overlay_surf, (0, 0))

    panel_w, panel_h = min(640, width - 80), min(420, height - 120)
    px = width // 2 - panel_w // 2
    py = height // 2 - panel_h // 2
    pygame.draw.rect(surface, (12, 12, 12), (px, py, panel_w, panel_h))
    pygame.draw.rect(surface, CYAN, (px, py, panel_w, panel_h), 2)
    title = small_font.render("Server Members", True, WHITE)
    surface.blit(title, (px + panel_w // 2 - title.get_width() // 2, py + 12))
    hint_text = "Select a player to kick or ban them" if is_host else "Members list is host-only"
    hint = tiny_font.render(hint_text, True, LIGHT_GRAY)
    surface.blit(hint, (px + panel_w // 2 - hint.get_width() // 2, py + 36))

    members = []
    with network_client.lock:
        if network_client.client_id is not None:
            members.append((network_client.client_id,
                            network_client.username,
                            network_client.display_name,
                            network_client.ping_ms,
                            network_client.connected,
                            "You"))
        for pid, data in network_client.other_players.items():
            members.append((pid,
                            data.get("username", f"Player {pid}"),
                            data.get("display_name", ""),
                            data.get("ping_ms"), True,
                            data.get("bio", "")))

    members.sort(key=lambda item: (item[2] or item[1]).lower())
    row_h = 54
    visible = min(len(members), max(1, (panel_h - 90) // row_h))
    actions: list[tuple[int, pygame.Rect, pygame.Rect]] = []
    for i, (pid, username, display_name, ping_ms, online, bio) in enumerate(members[:visible]):
        ry = py + 60 + i * row_h
        row = pygame.Rect(px + 20, ry, panel_w - 40, row_h - 6)
        pygame.draw.rect(surface, (30, 30, 30), row)
        pygame.draw.rect(surface, (70, 180, 120) if online else (150, 60, 60), row, 1)
        display_ping = f"{int(round(ping_ms))} ms" if isinstance(ping_ms, (int, float)) else "--"
        show_name = display_name or username
        name_surf = small_font.render(show_name, True, WHITE)
        surface.blit(name_surf, (row.x + 10, row.y + 5))
        if display_name and display_name != username:
            user_surf = tiny_font.render(f"@{username}", True, LIGHT_GRAY)
            surface.blit(user_surf, (row.x + 10, row.y + 22))
        if bio:
            bio_surf = tiny_font.render(str(bio)[:28], True, (160, 220, 220))
            surface.blit(bio_surf, (row.x + 120, row.y + 22))
        surface.blit(tiny_font.render(display_ping, True, CYAN), (row.right - 110, row.y + 12))
        kick_r = pygame.Rect(row.right - 170, row.y + 7, 60, 24)
        ban_r = pygame.Rect(row.right - 102, row.y + 7, 60, 24)
        if is_host and pid != getattr(network_client, "client_id", None):
            pygame.draw.rect(surface, (70, 70, 70), kick_r)
            pygame.draw.rect(surface, (120, 40, 40), ban_r)
            surface.blit(tiny_font.render("Kick", True, WHITE), (kick_r.x + 12, kick_r.y + 4))
            surface.blit(tiny_font.render("Ban", True, WHITE), (ban_r.x + 15, ban_r.y + 4))
        actions.append((pid, kick_r, ban_r))

    back = tiny_font.render("Release \\ to close", True, LIGHT_GRAY)
    surface.blit(back, (px + panel_w // 2 - back.get_width() // 2, py + panel_h - 28))
    return actions


def handle_members_input(event: pygame.event.Event,
                         network_client,
                         member_actions: list[tuple[int, pygame.Rect, pygame.Rect]],
                         is_host: bool) -> str:
    if not is_host or event.type != pygame.MOUSEBUTTONDOWN:
        return ""
    if event.button != 1:
        return ""
    for pid, kick_r, ban_r in member_actions:
        if kick_r.collidepoint(event.pos):
            network_client.send_member_action("kick", pid)
            return "kick"
        if ban_r.collidepoint(event.pos):
            network_client.send_member_action("ban", pid)
            return "ban"
    return ""


def handle_keybinds_input(event: pygame.event.Event,
                          controls: dict,
                          remapping_key: str | None,
                          width: int, height: int) -> tuple[dict, str | None, str]:
    """Returns (controls, remapping_key, action)."""
    if event.type == pygame.MOUSEBUTTONDOWN:
        mx, my = event.pos
        y_off = 110
        col1, col2 = 50, width // 2 + 20
        for i, action in enumerate(controls):
            bx = col1 if i < 8 else col2
            by = y_off + (i % 8) * 45
            if pygame.Rect(bx, by, 330, 35).collidepoint(mx, my):
                return controls, action, ""
    if event.type == pygame.KEYDOWN:
        if remapping_key:
            # Prevent binding a key that is already used by another action
            for existing_action, bound_key in controls.items():
                if existing_action != remapping_key and bound_key == event.key:
                    # Key already taken — silently skip (do not rebind)
                    return controls, None, ""
            controls[remapping_key] = event.key
            return controls, None, ""
        if event.key == pygame.K_ESCAPE:
            return controls, None, "back"
    return controls, remapping_key, ""
