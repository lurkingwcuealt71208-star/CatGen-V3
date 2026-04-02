"""Overlay screens drawn on top of gameplay.

Covers: character info editor, upgrades menu, overlay stack management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from core.constants import (
    BLACK, CYAN, DARK_CYAN, GRAY, LIGHT_GRAY, WHITE,
)
from ui.renderer import draw_gradient_rect

if TYPE_CHECKING:
    from game.state import PlayerState


def _get_clipboard_text() -> str:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            text = root.clipboard_get()
        finally:
            root.destroy()
        return str(text)
    except Exception:
        try:
            if hasattr(pygame, "scrap"):
                if not pygame.scrap.get_init():
                    pygame.scrap.init()
                text = pygame.scrap.get(pygame.SCRAP_TEXT)
                if isinstance(text, bytes):
                    return text.decode("utf-8", errors="ignore")
                if text:
                    return str(text)
        except Exception:
            pass
    return ""


# ---------------------------------------------------------------------------
# Overlay stack helpers
# ---------------------------------------------------------------------------

def push_overlay(stack: list[str], name: str) -> None:
    if not stack or stack[-1] != name:
        stack.append(name)


def pop_overlay(stack: list[str]) -> str | None:
    return stack.pop() if stack else None


def top_overlay(stack: list[str]) -> str | None:
    return stack[-1] if stack else None


# ---------------------------------------------------------------------------
# Character Info
# ---------------------------------------------------------------------------

def draw_character_info(surface: pygame.Surface,
                         width: int, height: int,
                         char_name: str, char_bio: str,
                         name_focus: bool,
                         font: pygame.font.Font,
                         small_font: pygame.font.Font,
                         tiny_font: pygame.font.Font) -> None:
    overlay_surf = pygame.Surface((width, height), pygame.SRCALPHA)
    overlay_surf.fill((0, 0, 0, 200))
    surface.blit(overlay_surf, (0, 0))

    mw, mh = 600, 450
    mx = width  // 2 - mw // 2
    my = height // 2 - mh // 2
    draw_gradient_rect(surface, (10, 10, 10), DARK_CYAN, (mx, my, mw, mh))
    pygame.draw.rect(surface, CYAN, (mx, my, mw, mh), 2)

    surface.blit(font.render("Character Info", True, CYAN), (mx + 20, my + 20))

    # Name field
    surface.blit(small_font.render("Character Name:", True, WHITE), (mx + 40, my + 80))
    name_r = pygame.Rect(mx + 40, my + 110, mw - 80, 40)
    pygame.draw.rect(surface, (40, 40, 40) if name_focus else (20, 20, 20), name_r)
    pygame.draw.rect(surface, CYAN if name_focus else GRAY, name_r, 2)
    surface.blit(small_font.render(char_name, True, CYAN), (name_r.x + 10, name_r.y + 8))

    # Bio field
    surface.blit(small_font.render("Character Bio:", True, WHITE), (mx + 40, my + 170))
    bio_r = pygame.Rect(mx + 40, my + 200, mw - 80, 150)
    pygame.draw.rect(surface, (20, 20, 20) if name_focus else (40, 40, 40), bio_r)
    pygame.draw.rect(surface, GRAY if name_focus else CYAN, bio_r, 2)

    words = char_bio.split(" ")
    lines, current = [], ""
    for w in words:
        test = current + w + " "
        if small_font.size(test)[0] < bio_r.width - 20:
            current = test
        else:
            if current.strip():
                lines.append(current)
            current = w + " "  # force long word onto its own line
    if current.strip():
        lines.append(current)
    for i, line in enumerate(lines[:6]):
        surface.blit(small_font.render(line, True, CYAN),
                     (bio_r.x + 10, bio_r.y + 10 + i * 25))

    hint = small_font.render("Click a field to edit | ENTER — Save | ESC — Cancel", True, LIGHT_GRAY)
    surface.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 40))


def handle_character_info_input(event: pygame.event.Event,
                                 char_name: str, char_bio: str,
                                 name_focus: bool) -> tuple[str, str, bool, str]:
    """Returns (char_name, char_bio, name_focus, action).

    action: "" | "save" | "cancel"
    """
    mw, mh = 600, 450
    # The editor layout is fixed, so click detection can reuse the same rects.
    width, height = pygame.display.get_surface().get_size() if pygame.display.get_surface() else (800, 600)
    mx = width // 2 - mw // 2
    my = height // 2 - mh // 2
    name_r = pygame.Rect(mx + 40, my + 110, mw - 80, 40)
    bio_r = pygame.Rect(mx + 40, my + 200, mw - 80, 150)

    if event.type == pygame.MOUSEBUTTONDOWN:
        if name_r.collidepoint(event.pos):
            return char_name, char_bio, True, ""
        if bio_r.collidepoint(event.pos):
            return char_name, char_bio, False, ""
        return char_name, char_bio, name_focus, ""
    if event.type != pygame.KEYDOWN:
        return char_name, char_bio, name_focus, ""

    if event.key == pygame.K_ESCAPE:
        return char_name, char_bio, name_focus, "cancel"
    if event.key == pygame.K_RETURN:
        return char_name, char_bio, name_focus, "save"
    if event.key == pygame.K_BACKSPACE:
        if name_focus:
            return char_name[:-1], char_bio, name_focus, ""
        return char_name, char_bio[:-1], name_focus, ""
    if not name_focus:
        mods = event.mod if hasattr(event, "mod") else 0
        ctrl_mask = pygame.KMOD_CTRL | getattr(pygame, "KMOD_GUI", 0) | getattr(pygame, "KMOD_META", 0)
        if event.key == pygame.K_v and mods & ctrl_mask:
            clip = _get_clipboard_text().replace("\r\n", "\n").replace("\r", "\n")
            if clip:
                clip = clip.strip("\x00")
                room = max(0, 200 - len(char_bio))
                if room > 0:
                    return char_name, char_bio + clip[:room], name_focus, ""
    if event.unicode.isprintable():
        if name_focus and len(char_name) < 20:
            return char_name + event.unicode, char_bio, name_focus, ""
        if not name_focus and len(char_bio) < 200:
            return char_name, char_bio + event.unicode, name_focus, ""
    return char_name, char_bio, name_focus, ""


# ---------------------------------------------------------------------------
# Upgrades
# ---------------------------------------------------------------------------

UPGRADES: list[dict] = [
    {"id": "sprint_boost",   "name": "Sprint Boost",   "required_level": 2,  "locked": True},
    {"id": "jump_height",    "name": "Jump Height",    "required_level": 3,  "locked": True},
    {"id": "carry_capacity", "name": "Carry Capacity", "required_level": 5,  "locked": True},
    {"id": "stealth_step",   "name": "Stealth Step",   "required_level": 8,  "locked": True},
    {"id": "dash_range",     "name": "Dash Range",     "required_level": 10, "locked": True},
]


def attempt_unlock(upgrade_id: str, player_level: int) -> tuple[bool, str]:
    for up in UPGRADES:
        if up["id"] == upgrade_id:
            if player_level >= up["required_level"]:
                up["locked"] = False
                return True, "Unlocked!"
            return False, f"Requires level {up['required_level']}"
    return False, "Unknown upgrade"


def draw_upgrades_menu(surface: pygame.Surface,
                        width: int, height: int,
                        player_level: int,
                        font: pygame.font.Font,
                        small_font: pygame.font.Font,
                        tiny_font: pygame.font.Font,
                        upgrade_message: str = "",
                        upgrade_message_color: tuple = (255, 255, 255)) -> None:
    overlay_surf = pygame.Surface((width, height), pygame.SRCALPHA)
    overlay_surf.fill((0, 0, 0, 200))
    surface.blit(overlay_surf, (0, 0))

    mw, mh = 500, 400
    mx = width  // 2 - mw // 2
    my = height // 2 - mh // 2
    draw_gradient_rect(surface, (10, 10, 10), DARK_CYAN, (mx, my, mw, mh))
    pygame.draw.rect(surface, CYAN, (mx, my, mw, mh), 2)
    surface.blit(font.render("Upgrades", True, CYAN), (mx + 20, my + 20))

    row_h = 46
    for i, up in enumerate(UPGRADES):
        uy = my + 70 + i * (row_h + 8)
        r = pygame.Rect(mx + 30, uy, mw - 60, row_h)
        pygame.draw.rect(surface, (30, 30, 30), r)
        border = CYAN if not up.get("locked", True) else GRAY
        pygame.draw.rect(surface, border, r, 2)
        col = WHITE if not up.get("locked", True) else LIGHT_GRAY
        surface.blit(small_font.render(up["name"], True, col), (r.x + 10, r.y + 8))
        req = tiny_font.render(f"Requires level {up['required_level']}", True, LIGHT_GRAY)
        surface.blit(req, (r.right - req.get_width() - 10, r.y + 12))

    back = small_font.render("Press ESC to back", True, WHITE)
    surface.blit(back, (mx + mw // 2 - back.get_width() // 2, my + mh - 40))

    # Show unlock result message if any
    if upgrade_message:
        msg_surf = small_font.render(upgrade_message, True, upgrade_message_color)
        surface.blit(msg_surf, (mx + mw // 2 - msg_surf.get_width() // 2, my + mh - 65))


def handle_upgrades_input(event: pygame.event.Event,
                           width: int, height: int,
                           player_level: int) -> str:
    """Returns "close" or the upgrade result string, or "".

    Return format: "unlock:<ok|fail>:<message>" when a row is clicked.
    """
    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
        return "close"
    if event.type == pygame.MOUSEBUTTONDOWN:
        mw, mh = 500, 400
        mx = width  // 2 - mw // 2
        my = height // 2 - mh // 2
        row_h = 46
        for i, up in enumerate(UPGRADES):
            uy = my + 70 + i * (row_h + 8)
            if pygame.Rect(mx + 30, uy, mw - 60, row_h).collidepoint(event.pos):
                ok, msg = attempt_unlock(up["id"], player_level)
                return f"unlock:{'ok' if ok else 'fail'}:{msg}"
    return ""
