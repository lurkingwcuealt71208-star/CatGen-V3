"""Prey entity — AI states, physics, and rendering."""

from __future__ import annotations

import random

import pygame

from core.constants import (
    PREY_DETECTION_RADIUS, PREY_FLEE_SPEED, PREY_IDLE_SPEED, PREY_WORLD_SIZE,
)


class Prey:
    IDLE = "idle"
    GRAZING = "grazing"
    ALERT = "alert"
    FLEEING = "fleeing"
    HIDING = "hiding"
    DEAD = "dead"

    def __init__(self, x: float, y: float,
                 prey_img: pygame.Surface | None = None) -> None:
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.state = self.IDLE
        self.state_timer = 0.0
        self.speed = PREY_IDLE_SPEED
        self.flee_speed = PREY_FLEE_SPEED
        self.detection_radius = PREY_DETECTION_RADIUS
        self.alpha = 255
        self.visible = True
        self.panic_timer = 0.0
        self.hide_timer = 0.0
        self.bob_timer: float = 0.0
        self.name: str = "Mouse"
        self.last_known_threat: tuple[float, float] | None = None
        self._img: pygame.Surface | None = prey_img
        self._change_direction()

    def set_image(self, img: pygame.Surface) -> None:
        self._img = img

    def _change_direction(self) -> None:
        sign = lambda: 1 if random.random() > 0.5 else -1
        self.vx = random.uniform(0.5, 1.0) * self.speed * sign()
        self.vy = random.uniform(0.5, 1.0) * self.speed * sign()

    def update(self, player_x: float, player_y: float, dt: float) -> bool:
        """Advance AI; returns ``False`` when the prey should be removed."""
        dist = ((self.x - player_x) ** 2 + (self.y - player_y) ** 2) ** 0.5

        if self.state == self.DEAD:
            self.bob_timer += dt
            self.vx = 0.0
            self.vy = 0.0
            return True

        if self.state == self.HIDING:
            self.hide_timer -= dt
            if self.alpha > 0:
                self.alpha = max(0, self.alpha - 255 * dt)
            return self.hide_timer > 0

        if self.state == self.FLEEING:
            self.panic_timer -= dt
            if self.panic_timer <= 0:
                self.state = self.HIDING
                self.hide_timer = 3.0
                return True
            dx = self.x - player_x
            dy = self.y - player_y
            mag = (dx ** 2 + dy ** 2) ** 0.5
            if mag > 0:
                self.vx = (dx / mag) * self.flee_speed * 60 * dt
                self.vy = (dy / mag) * self.flee_speed * 60 * dt

        elif dist < self.detection_radius:
            if self.state != self.ALERT:
                self.state = self.ALERT
                self.state_timer = 3.0
            self.last_known_threat = (player_x, player_y)
            if dist < 100:
                self.state = self.FLEEING
                self.panic_timer = 2.0
        else:
            if self.state == self.ALERT:
                self.state_timer -= dt
                if self.state_timer <= 0:
                    self.state = self.IDLE
                    self.state_timer = random.uniform(2, 5)
            else:
                self.state_timer -= dt
                if self.state_timer <= 0:
                    self.state = random.choice([self.IDLE, self.GRAZING])
                    self.state_timer = random.uniform(2, 5)
                    if self.state == self.GRAZING:
                        self._change_direction()
                    else:
                        self.vx = self.vy = 0.0

        if self.state == self.GRAZING:
            # vx/vy are base speeds set by _change_direction; scale by dt
            self.x += self.vx * 60 * dt
            self.y += self.vy * 60 * dt
        elif self.state not in (self.IDLE, self.ALERT):
            # FLEEING: vx/vy already incorporate dt scaling (recalculated each frame)
            self.x += self.vx
            self.y += self.vy

        half = PREY_WORLD_SIZE // 2
        if self.x < -half or self.x > half:
            self.vx *= -1
            self.x = max(-half, min(half, self.x))
        if self.y < -half or self.y > half:
            self.vy *= -1
            self.y = max(-half, min(half, self.y))

        return True

    def draw(self, surface: pygame.Surface, screen_x: float, screen_y: float) -> None:
        if self._img is None:
            return
        if self.alpha < 255:
            tmp = self._img.copy()
            tmp.set_alpha(int(self.alpha))
            surface.blit(tmp, (int(screen_x) - 25, int(screen_y) - 25))
        else:
            surface.blit(self._img, (int(screen_x) - 25, int(screen_y) - 25))
