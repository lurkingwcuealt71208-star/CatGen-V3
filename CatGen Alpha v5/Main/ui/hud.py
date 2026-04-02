"""HUD elements drawn during gameplay.

Covers: status bars, clock, bottom bar, chat, speech bubble,
pounce meter, dash charge bar.
"""

from __future__ import annotations

import time
import math
from datetime import datetime
from typing import TYPE_CHECKING

import pygame

from core.constants import (
    BLACK, CYAN, DARK_CYAN, GRAY, GREEN, LIGHT_BLUE, LIGHT_GRAY,
    ORANGE, PURPLE, RED, WHITE, YELLOW,
)
from ui.renderer import draw_gradient_rect

if TYPE_CHECKING:
    from game.state import PlayerState
    from network.client import NetworkClient


# ---------------------------------------------------------------------------
# Status bars
# ---------------------------------------------------------------------------

class StatusBarContainer:
    """Configurable vertical stack of status bars.

    bars: list of dicts — {name, attr, color}
         where `attr` is the attribute name on PlayerState.
    """
    def __init__(self, x: int = 10, y: int = 10,
                 width: int = 150, height: int = 15,
                 padding: int = 8, bars: list | None = None) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.padding = padding
        self.bars = bars or [
            {"name": "Hunger",   "attr": "hunger",   "color": RED},
            {"name": "Thirst",   "attr": "thirst",   "color": LIGHT_BLUE},
            {"name": "Bathroom", "attr": "bathroom", "color": YELLOW},
            {"name": "Sleep",    "attr": "sleep",    "color": PURPLE},
            {"name": "Stamina",  "attr": "stamina",  "color": GREEN},
        ]

    def render(self, surface: pygame.Surface,
               state: "PlayerState",
               font: pygame.font.Font) -> None:
        if state.streamer_mode:
            return
        for i, b in enumerate(self.bars):
            bx = self.x
            by = self.y + i * (self.height + self.padding)
            value = float(getattr(state, b["attr"], 0))
            fill = int(max(0, min(1.0, value / 100)) * self.width)
            pygame.draw.rect(surface, GRAY, (bx, by, self.width, self.height))
            pygame.draw.rect(surface, b["color"], (bx, by, fill, self.height))
            pygame.draw.rect(surface, BLACK, (bx, by, self.width, self.height), 2)
            txt = font.render(f"{b['name']}: {int(value)}", True, WHITE)
            surface.blit(txt, (bx + self.width + 6, by))


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------

def draw_clock(surface: pygame.Surface,
               font: pygame.font.Font,
               x: int, y: int,
               use_12h: bool = False) -> None:
    now = datetime.now()
    fmt = "%I:%M %p" if use_12h else "%H:%M"
    surface.blit(font.render(now.strftime(fmt), True, WHITE), (x, y))


# ---------------------------------------------------------------------------
# Bottom HUD
# ---------------------------------------------------------------------------

def draw_bottom_hud(surface: pygame.Surface,
                    width: int, height: int,
                    small_font: pygame.font.Font,
                    tiny_font: pygame.font.Font,
                    player_level: int,
                    use_12h: bool = False,
                    streamer_mode: bool = False) -> "pygame.Rect | None":
    if streamer_mode:
        return
    hud_h = 60
    hud_y = height - hud_h
    draw_gradient_rect(surface, (3, 3, 6), (0, 200, 220), (0, hud_y, width, hud_h))
    shine = pygame.Surface((width, hud_h), pygame.SRCALPHA)
    shine.fill((255, 255, 255, 18))
    surface.blit(shine, (0, hud_y))
    pygame.draw.line(surface, (150, 250, 255), (0, hud_y), (width, hud_y), 2)
    pygame.draw.line(surface, (0, 0, 0), (0, hud_y + hud_h - 1), (width, hud_y + hud_h - 1), 1)

    # Clock
    now = datetime.now()
    clk = now.strftime("%I:%M %p" if use_12h else "%H:%M")
    surface.blit(tiny_font.render(clk, True, WHITE), (20, hud_y + 7))

    # Level
    surface.blit(small_font.render(f"Level: {player_level}", True, WHITE),
                 (20, hud_y + 35))

    # Character Info button
    btn_w, btn_h = 150, 40
    bx = width - btn_w - 20
    by = hud_y + (hud_h - btn_h) // 2
    btn_bg = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
    draw_gradient_rect(btn_bg, (20, 20, 20), (0, 170, 180), (0, 0, btn_w, btn_h))
    surface.blit(btn_bg, (bx, by))
    pygame.draw.rect(surface, CYAN, (bx, by, btn_w, btn_h), 2)
    t = small_font.render("Character Info", True, WHITE)
    surface.blit(t, (bx + btn_w // 2 - t.get_width() // 2, by + 8))
    return pygame.Rect(bx, by, btn_w, btn_h)  # caller can use for click detection


# ---------------------------------------------------------------------------
# Chat overlay
# ---------------------------------------------------------------------------

def _wrap_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if font.size(candidate)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if font.size(word)[0] <= max_width:
            current = word
            continue
        chunk = ""
        for char in word:
            trial = chunk + char
            if font.size(trial)[0] <= max_width:
                chunk = trial
            else:
                if chunk:
                    lines.append(chunk)
                chunk = char
        current = chunk
    if current:
        lines.append(current)
    return lines or [text]


def _format_chat_entry(msg: dict) -> tuple[str, str]:
    kind = str(msg.get("kind", "chat"))
    if kind == "system":
        return "system", str(msg.get("text", msg.get("message", "")))
    username = str(msg.get("username", "")).strip()
    display_name = str(msg.get("display_name", "")).strip()
    message = str(msg.get("message", "")).strip()
    if username or display_name:
        header = f"[{username or 'Player'}] {display_name or username or 'Player'}:"
        return "chat", f"{header} {message}".strip()
    return "chat", message


def _wrap_paragraphs(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
    paragraphs = text.split("\n")
    lines: list[str] = []
    for paragraph in paragraphs:
        wrapped = _wrap_text(font, paragraph, max_width)
        lines.extend(wrapped if wrapped else [""])
    return lines or [""]

def draw_chat(surface: pygame.Surface,
              width: int, height: int,
              chat_messages: list,
              chat_open: bool,
              chat_input: str,
              typing_active: bool,
              chat_scroll: int,
              small_font: pygame.font.Font,
              aero_font: pygame.font.Font) -> None:
    now = time.time()
    visible = chat_messages[-120:]
    has_visible_message = bool(visible)

    if not chat_open and not has_visible_message:
        return

    chat_w = min(760, width - 40)
    chat_h = 220
    bottom_off = 96  # above bottom HUD

    latest_age = 999.0
    for msg in visible:
        if isinstance(msg, dict):
            latest_age = min(latest_age, max(0.0, now - float(msg.get("time", now))))
        elif visible:
            latest_age = 0.0

    if chat_open:
        panel_alpha = 235
    else:
        fade = max(0.0, min(1.0, 1.0 - latest_age / 40.0))
        panel_alpha = int(170 * (fade * fade * (3 - 2 * fade)))

    if panel_alpha <= 0:
        return

    bg = pygame.Surface((chat_w, chat_h), pygame.SRCALPHA)
    draw_gradient_rect(bg, (8, 8, 10), (0, 150, 180), bg.get_rect())
    overlay = pygame.Surface((chat_w, chat_h), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, max(0, panel_alpha - 30)))
    bg.blit(overlay, (0, 0))
    pygame.draw.rect(bg, (110, 250, 255, panel_alpha), bg.get_rect(), 2)
    surface.blit(bg, (20, height - chat_h - bottom_off))

    lines_area_h = chat_h - (46 if chat_open else 16)
    max_text_w = chat_w - 32
    rendered_lines: list[tuple[str, str, int, str, str]] = []
    for msg in visible:
        if not isinstance(msg, dict):
            kind = "chat"
            text = str(msg)
            age = 0.0
            username = ""
            display_name = ""
        else:
            kind, text = _format_chat_entry(msg)
            age = max(0.0, now - float(msg.get("time", now)))
            username = str(msg.get("username", "")).strip()
            display_name = str(msg.get("display_name", "")).strip()
        fade = max(0.0, min(1.0, 1.0 - age / 40.0))
        alpha = int(255 * (fade * fade * (3 - 2 * fade)))
        if kind == "system":
            for line in _wrap_paragraphs(small_font, text, max_text_w):
                rendered_lines.append((kind, line, alpha, "", ""))
            continue

        prefix = f"[{username or 'Player'}]"
        display_text = display_name or username or "Player"
        header_font = small_font
        prefix_w = header_font.size(prefix + " ")[0]
        display_w = header_font.size(display_text + ": ")[0]
        body_width = max(80, max_text_w - prefix_w - display_w)
        body_lines = _wrap_paragraphs(aero_font, text, body_width)
        for i, line in enumerate(body_lines):
            rendered_lines.append((kind, line, alpha, prefix if i == 0 else "", display_text if i == 0 else ""))

    line_spacing = 19
    usable_lines = max(1, lines_area_h // line_spacing)
    max_scroll = max(0, len(rendered_lines) - usable_lines)
    scroll = max(0, min(max_scroll, chat_scroll))
    start = max(0, len(rendered_lines) - usable_lines - scroll)
    end = start + usable_lines
    y = height - bottom_off - chat_h + 10
    for kind, line, alpha, prefix, display_text in rendered_lines[start:end]:
        if kind == "system":
            surf = small_font.render(line, True, (100, 250, 255))
            surf.set_alpha(alpha)
            surface.blit(surf, (34, y))
        else:
            x = 34
            if prefix:
                prefix_surf = small_font.render(prefix, True, (120, 255, 120))
                prefix_surf.set_alpha(alpha)
                surface.blit(prefix_surf, (x, y))
                x += prefix_surf.get_width() + 4

                display_surf = small_font.render(display_text, True, (90, 200, 255))
                display_surf.set_alpha(alpha)
                surface.blit(display_surf, (x, y))
                x += display_surf.get_width()

                colon_surf = small_font.render(":", True, (90, 250, 255))
                colon_surf.set_alpha(alpha)
                surface.blit(colon_surf, (x, y))
                x += colon_surf.get_width() + 6

            body_surf = aero_font.render(line, True, (90, 250, 255))
            body_surf.set_alpha(alpha)
            surface.blit(body_surf, (x, y))
        y += line_spacing

    if max_scroll > 0:
        bar_x = 20 + chat_w - 10
        bar_y = height - chat_h - bottom_off + 10
        bar_h = chat_h - 20
        pygame.draw.rect(surface, (20, 20, 20), (bar_x, bar_y, 5, bar_h))
        thumb_h = max(18, int(bar_h * (usable_lines / max(1, len(rendered_lines)))))
        thumb_range = max(1, bar_h - thumb_h)
        thumb_y = bar_y + int(thumb_range * (scroll / max_scroll)) if max_scroll else bar_y
        pygame.draw.rect(surface, (120, 250, 255), (bar_x, thumb_y, 5, thumb_h))

    if chat_open:
        inp_bg = pygame.Surface((chat_w, 36), pygame.SRCALPHA)
        draw_gradient_rect(inp_bg, (5, 5, 6), (0, 120, 160), inp_bg.get_rect())
        pygame.draw.rect(inp_bg, (110, 250, 255, 220), inp_bg.get_rect(), 1)
        surface.blit(inp_bg, (20, height - 38 - 60))
        prompt_text = f"Say: {chat_input}"
        prompt = aero_font.render(prompt_text, True, (90, 250, 255))
        surface.blit(prompt, (36, height - 32 - 60))
        cx = 36 + prompt.get_width()
        if int(time.time() * 2) % 2:
            pygame.draw.line(surface, (110, 250, 255),
                             (cx, height - 32 - 60),
                             (cx, height - 12 - 60), 2)


def draw_connection_status(surface: pygame.Surface,
                           width: int,
                           network_client,
                           small_font: pygame.font.Font,
                           is_host: bool = False) -> None:
    status = "Disconnected"
    status_color = (220, 80, 80)
    ping_text = "Ping: --"
    if getattr(network_client, "connected", False):
        status = "Hosting" if is_host else "Connected"
        status_color = (70, 210, 120)
        ping_ms = getattr(network_client, "ping_ms", None)
        if ping_ms is not None:
            ping_text = f"Ping: {int(round(ping_ms))} ms"
    label = f"{status}  |  {ping_text}"
    text = small_font.render(label, True, WHITE)
    panel_w = text.get_width() + 20
    panel_h = text.get_height() + 12
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 150))
    pygame.draw.rect(panel, status_color, panel.get_rect(), 2)
    panel.blit(text, (10, 6))
    surface.blit(panel, (width // 2 - panel_w // 2, 10))


# ---------------------------------------------------------------------------
# Speech bubble above local cat
# ---------------------------------------------------------------------------

def draw_speech_bubble(surface: pygame.Surface,
                       message: str,
                       cat_x: int, cat_y: int,
                       font: pygame.font.Font) -> None:
    if not message:
        return
    lines = _wrap_text(font, message, 160)
    rendered = [font.render(line, True, BLACK) for line in lines]
    bw = max(s.get_width() for s in rendered) + 16
    bh = sum(s.get_height() for s in rendered) + 10 + (len(rendered) - 1) * 2
    bx = cat_x - bw // 2
    by = cat_y - bh - 40
    pygame.draw.rect(surface, WHITE, (bx, by, bw, bh))
    pygame.draw.rect(surface, CYAN,  (bx, by, bw, bh), 2)
    yy = by + 5
    for surf in rendered:
        surface.blit(surf, (bx + 8, yy))
        yy += surf.get_height() + 2


# ---------------------------------------------------------------------------
# Pounce meter
# ---------------------------------------------------------------------------

def draw_pounce_meter(surface: pygame.Surface,
                      pounce_meter: float, max_pounce: float,
                      cat_x: int, cat_y: int,
                      font: pygame.font.Font,
                      near_prey: bool,
                      streamer_mode: bool = False) -> None:
    # Show while near prey OR while meter is still fading out (> 0)
    if streamer_mode or (not near_prey and pounce_meter <= 0):
        return
    bx = cat_x - 50
    by = cat_y - 80
    pygame.draw.rect(surface, GRAY, (bx, by, 100, 12))
    pygame.draw.rect(surface, ORANGE,
                     (bx, by, int(pounce_meter / max_pounce * 100), 12))
    pygame.draw.rect(surface, BLACK, (bx, by, 100, 12), 2)
    surface.blit(font.render("Pounce", True, WHITE), (bx + 110, by - 2))


# ---------------------------------------------------------------------------
# Dash charge bar
# ---------------------------------------------------------------------------

def draw_dash_charge(surface: pygame.Surface,
                     dash_charge: float, max_dash_charge: float,
                     width: int, height: int,
                     is_charging: bool,
                     font: pygame.font.Font,
                     streamer_mode: bool = False) -> None:
    if streamer_mode or not is_charging:
        return
    bar_w, bar_h = 220, 14
    bx = width // 2 - bar_w // 2
    by = height - 60 - 30
    pygame.draw.rect(surface, (40, 40, 40), (bx, by, bar_w, bar_h))
    fill = int((dash_charge / max(1, max_dash_charge)) * bar_w)
    pygame.draw.rect(surface, (240, 200, 60), (bx, by, fill, bar_h))
    pygame.draw.rect(surface, BLACK, (bx, by, bar_w, bar_h), 2)
    pct = int(dash_charge / max(1, max_dash_charge) * 100)
    surface.blit(font.render(f"Dash: {pct}%", True, WHITE),
                 (bx + bar_w + 8, by - 2))


def draw_pickup_toast(surface: pygame.Surface,
                      width: int, height: int,
                      small_font: pygame.font.Font,
                      pickup_msg: str,
                      pickup_timer: float) -> None:
    """Bottom-center toast for world item pickup feedback."""
    if pickup_timer <= 0 or not pickup_msg:
        return
    alpha = min(1.0, pickup_timer / 0.5)
    toast = pygame.Surface((320, 38), pygame.SRCALPHA)
    toast.fill((0, 0, 0, int(200 * alpha)))
    txt = small_font.render(pickup_msg, True, CYAN)
    txt.set_alpha(int(255 * alpha))
    toast.blit(txt, (160 - txt.get_width() // 2, 7))
    surface.blit(toast, (width // 2 - 160, height - 130))
