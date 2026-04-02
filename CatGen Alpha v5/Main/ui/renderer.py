"""World / game-space renderer.

Handles: grass background, prey sprites, local player sprite,
remote player sprites with interpolation labels.
"""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from game.state import PlayerState
    from network.client import NetworkClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def draw_gradient_rect(surface: pygame.Surface,
                       color1: tuple, color2: tuple,
                       rect: tuple | pygame.Rect) -> None:
    """Vertical gradient rectangle."""
    target = pygame.Rect(rect)
    tmp = pygame.Surface((2, 2))
    pygame.draw.line(tmp, color1, (0, 0), (1, 0))
    pygame.draw.line(tmp, color2, (0, 1), (1, 1))
    tmp = pygame.transform.smoothscale(tmp, (target.width, target.height))
    surface.blit(tmp, target)


# ---------------------------------------------------------------------------
# Grass background
# ---------------------------------------------------------------------------

def draw_grass_background(surface: pygame.Surface,
                           grass_img: pygame.Surface,
                           world_x: float, world_y: float,
                           width: int, height: int) -> None:
    gw, gh = grass_img.get_width(), grass_img.get_height()
    if gw <= 0 or gh <= 0:
        return
    off_x = world_x % gw
    off_y = world_y % gh
    for tx in range(width // gw + 2):
        for ty in range(height // gh + 2):
            surface.blit(grass_img,
                         (tx * gw - off_x, ty * gh - off_y))


# ---------------------------------------------------------------------------
# Prey sprites
# ---------------------------------------------------------------------------

def draw_prey_list(surface: pygame.Surface,
                   prey_list: list,
                   prey_img: pygame.Surface,
                   world_x: float, world_y: float,
                   camera_offset_x: float, camera_offset_y: float,
                   width: int, height: int,
                   font: pygame.font.Font | None = None) -> None:
    from game.prey import Prey as _Prey
    for prey in prey_list:
        sx = prey.x - world_x - camera_offset_x
        sy = prey.y - world_y - camera_offset_y
        if -100 < sx < width + 100 and -100 < sy < height + 100:
            if prey.state == _Prey.DEAD:
                bob = math.sin(prey.bob_timer * 3) * 4
                draw_y = sy + bob
                if prey.alpha < 255:
                    tmp = prey_img.copy()
                    tmp.set_alpha(int(prey.alpha))
                    surface.blit(tmp, (sx - 25, draw_y - 25))
                else:
                    surface.blit(prey_img, (sx - 25, draw_y - 25))
                # Name label above the dead prey
                if font is not None:
                    lbl = font.render(getattr(prey, "name", "Mouse"), True, WHITE)
                    surface.blit(lbl,
                                 (int(sx) - lbl.get_width() // 2,
                                  int(draw_y) - 42))
            else:
                if prey.alpha < 255:
                    tmp = prey_img.copy()
                    tmp.set_alpha(int(prey.alpha))
                    surface.blit(tmp, (sx - 25, sy - 25))
                else:
                    surface.blit(prey_img, (sx - 25, sy - 25))


# ---------------------------------------------------------------------------
# Carried / held prey (above player sprite)
# ---------------------------------------------------------------------------

def draw_carried_prey(surface: pygame.Surface,
                      carried_prey: list,
                      prey_img: pygame.Surface,
                      cat_x: int, cat_y: int) -> None:
    for i, _ in enumerate(carried_prey):
        scaled = pygame.transform.scale(prey_img, (30, 30))
        surface.blit(scaled, (cat_x - 15 + i * 8, cat_y - 50 - i * 6))


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


def _draw_wrapped_bubble(surface: pygame.Surface,
                         font: pygame.font.Font,
                         text: str,
                         center_x: int, top_y: int,
                         max_width: int = 180,
                         alpha: int = 255) -> None:
    lines = _wrap_text(font, text, max_width - 12)
    if not lines:
        return
    line_surfs = [font.render(line, True, BLACK) for line in lines]
    bubble_w = max(s.get_width() for s in line_surfs) + 12
    bubble_h = sum(s.get_height() for s in line_surfs) + 8 + (len(line_surfs) - 1) * 2
    bx = center_x - bubble_w // 2
    by = top_y - bubble_h
    pygame.draw.rect(surface, WHITE, (bx, by, bubble_w, bubble_h))
    pygame.draw.rect(surface, CYAN, (bx, by, bubble_w, bubble_h), 1)
    yy = by + 4
    for surf in line_surfs:
        surf.set_alpha(alpha)
        surface.blit(surf, (bx + 6, yy))
        yy += surf.get_height() + 2


# ---------------------------------------------------------------------------
# Local cat sprite
# ---------------------------------------------------------------------------

def draw_cat(surface: pygame.Surface,
             cat_img: pygame.Surface,
             cat_x: int, cat_y: int,
             facing_left: bool = False) -> None:
    img = pygame.transform.flip(cat_img, True, False) if facing_left else cat_img
    surface.blit(img, (cat_x - img.get_width() // 2,
                       cat_y - img.get_height() // 2))


# ---------------------------------------------------------------------------
# Remote players  (interpolated by network/client.py)
# ---------------------------------------------------------------------------

_REMOTE_Z_OFFSET = 1.0  # screen-space lift per z unit

WHITE  = (255, 255, 255)
YELLOW = (255, 255,   0)
CYAN   = (  0, 255, 255)
BLACK  = (  0,   0,   0)


def draw_remote_players(surface: pygame.Surface,
                        cat_img: pygame.Surface,
                        paw_img: pygame.Surface,
                        client: "NetworkClient",
                        world_x: float, world_y: float,
                        camera_offset_x: float, camera_offset_y: float,
                        width: int, height: int,
                        small_font: pygame.font.Font,
                        tiny_font: pygame.font.Font) -> None:
    """Render all other connected players using their interpolated positions."""
    with client.lock:
        players = dict(client.other_players)
        typing  = set(client.other_typing)

    for pid, p in players.items():
        try:
            rx = float(p.get("x", 0.0))
            ry = float(p.get("y", 0.0))
            rz = float(p.get("z", 0.0))
            if math.isnan(rx) or math.isinf(rx): rx = 0.0
            if math.isnan(ry) or math.isinf(ry): ry = 0.0
            if math.isnan(rz) or math.isinf(rz): rz = 0.0
        except (TypeError, ValueError):
            continue

        sx = (width // 2) + (rx - world_x) - camera_offset_x
        sy = (height // 2) + (ry - world_y) - camera_offset_y

        if sx < -100 or sx > width + 100 or sy < -100 or sy > height + 100:
            continue

        scale_f = 1.0
        w = int(cat_img.get_width()  * scale_f)
        h = int(cat_img.get_height() * scale_f)
        if w < 1 or h < 1:
            continue

        scaled_cat = pygame.transform.scale(cat_img, (w, h))
        blit_x = int(sx) - w // 2
        blit_y = int(sy - rz * _REMOTE_Z_OFFSET) - h // 2
        surface.blit(scaled_cat, (blit_x, blit_y))

        # Display label (display name if available, otherwise username)
        uname = str(p.get("display_name", "") or p.get("username", "Player"))[:20]
        tag = small_font.render(uname, True, WHITE)
        tag_bg = pygame.Surface((tag.get_width() + 6, tag.get_height() + 4),
                                pygame.SRCALPHA)
        tag_bg.fill((0, 0, 0, 140))
        tx = int(sx) - tag.get_width() // 2
        ty = blit_y - tag.get_height() - 6
        surface.blit(tag_bg, (tx - 3, ty - 2))
        surface.blit(tag, (tx, ty))

        bio = str(p.get("bio", "")).strip()
        if bio:
            bio_text = bio[:40]
            bio_surf = tiny_font.render(bio_text, True, (200, 240, 255))
            bio_bg = pygame.Surface((bio_surf.get_width() + 6, bio_surf.get_height() + 4), pygame.SRCALPHA)
            bio_bg.fill((0, 0, 0, 110))
            bio_y = ty + tag.get_height() + 2
            surface.blit(bio_bg, (int(sx) - bio_surf.get_width() // 2 - 3, bio_y - 2))
            surface.blit(bio_surf, (int(sx) - bio_surf.get_width() // 2, bio_y))

        # Typing indicator
        if pid in typing:
            typing_text = "typing..."
            bubble = tiny_font.render(typing_text, True, BLACK)
            bw, bh = bubble.get_width() + 12, bubble.get_height() + 8
            bx = int(sx) - bw // 2
            by = ty - bh - 4
            pygame.draw.rect(surface, WHITE, (bx, by, bw, bh))
            pygame.draw.rect(surface, CYAN, (bx, by, bw, bh), 1)
            surface.blit(bubble, (bx + 6, by + 4))

        # Speech bubble (server echoes chat as player_message field)
        msg = str(p.get("player_message", "")).strip()
        if msg:
            age = max(0.0, time.time() - float(p.get("message_time", time.time())))
            if age >= 5.0:
                continue
            fade = max(0.0, min(1.0, 1.0 - age / 5.0))
            alpha = int(255 * (fade * fade * (3 - 2 * fade)))
            _draw_wrapped_bubble(surface, small_font, msg, int(sx), blit_y - 30, 180, alpha)


# ---------------------------------------------------------------------------
# Scent / track marks
# ---------------------------------------------------------------------------

PAW_ALPHA_SECS = 30.0


def draw_prey_tracks(surface: pygame.Surface,
                     paw_img: pygame.Surface,
                     prey_tracks: list,
                     world_x: float, world_y: float,
                     camera_offset_x: float, camera_offset_y: float) -> None:
    now = time.time()
    for t in prey_tracks:
        age = now - t.get("time", now)
        if age > PAW_ALPHA_SECS:
            continue
        alpha = int(255 * (1.0 - age / PAW_ALPHA_SECS))
        sx = t["x"] - world_x - camera_offset_x
        sy = t["y"] - world_y - camera_offset_y
        tmp = paw_img.copy()
        tmp.set_alpha(alpha)
        surface.blit(tmp, (int(sx) - 12, int(sy) - 12))
