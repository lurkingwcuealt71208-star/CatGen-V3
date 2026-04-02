"""Game logic — status bar updates, stamina, prey management, pounce, tracking."""

from __future__ import annotations

import time
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.state import PlayerState
    from game.prey import Prey
    from game.inventory import Inventory, Item

# ---------------------------------------------------------------------------
# Status bars
# ---------------------------------------------------------------------------

def update_status_bars(state: "PlayerState", dt: float) -> None:
    """Drain status bars proportionally to elapsed time."""
    state.hunger  = max(0.0, state.hunger  - 0.6  * dt)
    state.thirst  = max(0.0, state.thirst  - 0.9  * dt)
    state.bathroom = max(0.0, state.bathroom - 0.48 * dt)
    state.sleep   = max(0.0, state.sleep   - 0.3  * dt)

    if state.dash_cooldown > 0:
        state.dash_cooldown = max(0.0, state.dash_cooldown - dt)


# ---------------------------------------------------------------------------
# Stamina
# ---------------------------------------------------------------------------

def update_stamina(state: "PlayerState", dt: float) -> None:
    """Drain stamina while sprinting; regenerate otherwise."""
    if state.is_sprinting and state.stamina > 0:
        state.stamina -= (100 / 30) * dt
        if state.stamina <= 0:
            state.stamina = 0.0
            state.is_sprinting = False
    elif not state.is_sprinting and state.stamina < state.max_stamina:
        state.stamina = min(state.max_stamina,
                            state.stamina + (100 / 20) * dt)


# ---------------------------------------------------------------------------
# Chat message timer
# ---------------------------------------------------------------------------

def update_chat_messages(state: "PlayerState", dt: float) -> None:
    """Age out the speech-bubble message."""
    if state.message_timer > 0:
        state.message_timer -= dt
        if state.message_timer <= 0:
            state.player_message = ""
            state.message_timer = 0.0


# ---------------------------------------------------------------------------
# Map position
# ---------------------------------------------------------------------------

def update_player_map_position(state: "PlayerState",
                                map_width: int, map_height: int) -> None:
    state.player_map_x = max(0, min(map_width - 1,
                                    map_width // 2 + state.world_x // 100))
    state.player_map_y = max(0, min(map_height - 1,
                                    map_height // 2 + state.world_y // 100))


# ---------------------------------------------------------------------------
# Prey
# ---------------------------------------------------------------------------

def spawn_prey(world_x: float, world_y: float, width: int, height: int) -> "Prey":
    """Return a new Prey at a random off-screen world position."""
    from game.prey import Prey
    px = world_x + random.randint(-width, width * 2)
    py = world_y + random.randint(-height, height * 2)
    return Prey(px, py)


def update_prey(state: "PlayerState",
                prey_list: list,
                dt: float,
                width: int, height: int) -> None:
    """Tick spawn timer, advance each prey AI, cull dead ones."""
    state.prey_spawn_timer += dt
    if state.prey_spawn_timer >= 15.0:
        state.prey_spawn_timer = 0.0
        prey_list.append(spawn_prey(state.world_x, state.world_y, width, height))

    player_wx = state.world_x + width // 2
    player_wy = state.world_y + height // 2

    prey_list[:] = [
        p for p in prey_list
        if p.update(player_wx, player_wy, dt)
    ]

    # Prune stale prey tracks older than 30 s to prevent unbounded memory growth
    if state.prey_tracks:
        cutoff = time.time() - 30.0
        state.prey_tracks = [t for t in state.prey_tracks if t.get("time", 0) >= cutoff]


def check_prey_collision(state: "PlayerState",
                         prey_list: list,
                         inventory: "Inventory",
                         cat_rect_fn,
                         width: int, height: int) -> bool:
    """Check player vs all prey; return True if a catch happened.

    cat_rect_fn() -> pygame.Rect  (screen-space rect for the cat sprite)
    Prey coordinates are world-space; cat world pos derived from state.
    """
    import pygame
    from game.prey import Prey

    cat_wx = state.world_x + width // 2
    cat_wy = state.world_y + height // 2
    cat_r = cat_rect_fn()

    caught = False
    for prey in prey_list[:]:
        if prey.state in (Prey.HIDING, Prey.DEAD):
            continue
        prey_rect = pygame.Rect(prey.x - 25, prey.y - 25, 50, 50)
        # Convert cat world rect to test against prey world coords
        cat_world_rect = pygame.Rect(
            cat_wx - cat_r.width // 2,
            cat_wy - cat_r.height // 2,
            cat_r.width, cat_r.height,
        )
        if cat_world_rect.colliderect(prey_rect):
            # Mark dead in place — player right-clicks to pick up
            prey.state = Prey.DEAD
            prey.vx = 0.0
            prey.vy = 0.0
            state.last_hunt_time = time.time()

            # XP and skill progression
            state.hunting_xp += 1
            state.hunting_skill = min(100, state.hunting_skill + 1)
            if state.hunting_skill >= 100:
                state.player_level += 1
                state.hunting_skill = 0

            caught = True
            break

    if not caught:
        # Frighten nearby prey on pounce miss
        from game.prey import Prey as P
        for prey in prey_list:
            dist = ((prey.x - cat_wx) ** 2 + (prey.y - cat_wy) ** 2) ** 0.5
            if dist < 150:
                prey.state = P.FLEEING
                prey.panic_timer = 1.5

    return caught


# ---------------------------------------------------------------------------
# Pounce meter
# ---------------------------------------------------------------------------

def update_pounce(state: "PlayerState", charging: bool, dt: float) -> None:
    """Charge pounce when held; decay otherwise."""
    if charging:
        state.pounce_meter = min(state.max_pounce, state.pounce_meter + 4)
    else:
        state.pounce_meter = max(0, state.pounce_meter - 2)


def release_pounce(state: "PlayerState",
                   prey_list: list,
                   inventory: "Inventory",
                   cat_rect_fn,
                   width: int, height: int) -> bool:
    """Fire pounce; returns True if a prey was caught."""
    if state.pounce_meter >= state.max_pounce:
        state.pounce_meter = 0
        return check_prey_collision(state, prey_list, inventory,
                                    cat_rect_fn, width, height)
    state.pounce_meter = 0
    return False


# ---------------------------------------------------------------------------
# Tracking / scent / burying
# ---------------------------------------------------------------------------

def track_prey(state: "PlayerState", prey_list: list,
               width: int, height: int) -> None:
    """Append scent-trail nodes for all nearby prey."""
    player_wx = state.world_x + width // 2
    player_wy = state.world_y + height // 2
    for prey in prey_list:
        dist = ((prey.x - player_wx) ** 2 +
                (prey.y - player_wy) ** 2) ** 0.5
        if dist < 400:
            state.prey_tracks.append({
                "x": prey.x,
                "y": prey.y,
                "time": time.time(),
                "type": "trail",
                "prey_id": id(prey),
            })


def scent_mark(state: "PlayerState") -> None:
    """Leave a scent mark at the player's current world position."""
    state.prey_tracks.append({
        "x": state.world_x,
        "y": state.world_y,
        "type": "scent",
        "time": time.time(),
    })


def bury_prey(state: "PlayerState") -> bool:
    """Bury a fresh catch. Returns True on success (within 30 s of last hunt)."""
    if time.time() - state.last_hunt_time <= 30:
        state.buried_prey.append({
            "x": state.world_x,
            "y": state.world_y,
            "time": time.time(),
        })
        return True
    return False
