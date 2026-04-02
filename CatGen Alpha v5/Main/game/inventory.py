"""Inventory system — Item, Inventory grid, and context menus."""

from __future__ import annotations

import time

import pygame

from core.constants import (
    BLACK, CYAN, DARK_CYAN, GRAY, LIGHT_GRAY, RED, WHITE,
)


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

class Item:
    def __init__(self, name: str, icon_color: tuple,
                 description: str = "", count: int = 1) -> None:
        self.name = name
        self.icon_color = icon_color
        self.description = description
        self.count = int(count)
        self.is_prey = False
        self.prey_hunger: int = 0
        self.prey_ref = None


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class Inventory:
    SLOTS = 32
    COLS = 8
    SLOT_SIZE = 60
    GAP = 10

    def __init__(self) -> None:
        self.items: list[Item | None] = [None] * self.SLOTS
        self.selected_tab: str = "Inventory"
        self.dragged_item: Item | None = None
        self.dragged_item_index: int = -1
        self.dragged_item_is_prey: bool = False
        self.dragged_prey_ref = None
        self.drag_pos: tuple[float, float] | None = None
        self.context_menu: dict | None = None

    def add_item(self, item: Item) -> bool:
        for slot in self.items:
            if slot and slot.name == item.name and not slot.is_prey:
                slot.count += item.count
                return True
        for i, slot in enumerate(self.items):
            if slot is None:
                self.items[i] = item
                return True
        return False

    def _slot_rect(self, i: int, ix: int, iy: int) -> pygame.Rect:
        row, col = divmod(i, self.COLS)
        total_w = self.COLS * (self.SLOT_SIZE + self.GAP) - self.GAP
        start_x = ix + (600 - total_w) // 2
        start_y = iy + 70
        return pygame.Rect(
            start_x + col * (self.SLOT_SIZE + self.GAP),
            start_y + row * (self.SLOT_SIZE + self.GAP),
            self.SLOT_SIZE, self.SLOT_SIZE,
        )

    def handle_input(self, event: pygame.event.Event,
                     width: int, height: int,
                     hunger_ref: list,
                     prey_list: list,
                     carried_prey: list,
                     last_hunt_time: float,
                     push_overlay_fn,
                     draw_gradient_fn) -> None:
        """Process mouse events in the inventory panel."""
        inv_w, inv_h = 600, 450
        ix = width // 2 - inv_w // 2
        iy = height // 2 - inv_h // 2

        if event.type == pygame.MOUSEBUTTONDOWN and self.context_menu:
            cmx, cmy = self.context_menu["pos"]
            w, h = 120, 28
            mx, my = event.pos
            if event.button == 1:  # only process options on left-click
                for idx, opt in enumerate(self.context_menu["options"]):
                    rx, ry = cmx, cmy + idx * (h + 4)
                    if pygame.Rect(rx, ry, w, h).collidepoint(mx, my):
                        slot = self.context_menu["slot"]
                        item = self.items[slot]
                        if not item:
                            self.context_menu = None
                            return
                        if opt == "Eat":
                            hunger_ref[0] = min(100, hunger_ref[0] + getattr(item, "prey_hunger", 20))
                            pr = getattr(item, "prey_ref", None)
                            if pr is not None and pr in prey_list:
                                prey_list.remove(pr)
                            self.items[slot] = None
                        elif opt == "Drop":
                            pr = getattr(item, "prey_ref", None)
                            self.items[slot] = None
                            if pr is not None:
                                from game.prey import Prey
                                pr.state = Prey.DEAD
                                prey_list.append(pr)
                        elif opt == "Bury":
                            if time.time() - last_hunt_time <= 30:
                                self.items[slot] = None
                        self.context_menu = None
                        return
            self.context_menu = None

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            tabs = ["Inventory", "Skills"]
            for i, tab in enumerate(tabs):
                tr = pygame.Rect(ix + i * 120, iy - 30, 110, 30)
                if tr.collidepoint(mx, my):
                    self.selected_tab = tab
                    return

            if self.selected_tab == "Inventory":
                for i in range(self.SLOTS):
                    r = self._slot_rect(i, ix, iy)
                    if r.collidepoint(mx, my):
                        if event.button == 1 and self.items[i]:
                            self.dragged_item = self.items[i]
                            self.dragged_item_index = i
                            self.dragged_item_is_prey = getattr(self.items[i], "is_prey", False)
                            self.dragged_prey_ref = getattr(self.items[i], "prey_ref", None)
                        elif event.button == 3 and self.items[i] and getattr(self.items[i], "is_prey", False):
                            opts = ["Eat", "Drop"]
                            if time.time() - last_hunt_time <= 30:
                                opts.append("Bury")
                            # Clamp menu so it stays inside the window
                            menu_w, menu_h = 120, len(opts) * 32
                            cx = min(mx, width  - menu_w - 4)
                            cy = min(my, height - menu_h - 4)
                            self.context_menu = {"slot": i, "pos": (cx, cy), "options": opts}
                        return

            elif self.selected_tab == "Skills":
                bx = ix + inv_w // 2 - 100
                by = iy + inv_h - 70
                if pygame.Rect(bx, by, 200, 40).collidepoint(mx, my):
                    push_overlay_fn("upgrades")

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragged_item:
            mx, my = event.pos
            placed = False
            for i in range(self.SLOTS):
                r = self._slot_rect(i, ix, iy)
                if r.collidepoint(mx, my):
                    target = self.items[i]
                    if target is None:
                        self.items[i] = self.dragged_item
                        if self.dragged_item_index >= 0:
                            self.items[self.dragged_item_index] = None
                        placed = True
                        break
                    if target.name == self.dragged_item.name and not target.is_prey:
                        target.count += self.dragged_item.count
                        if self.dragged_item_index >= 0:
                            self.items[self.dragged_item_index] = None
                        placed = True
                        break
                    if self.dragged_item_index >= 0:
                        self.items[i], self.items[self.dragged_item_index] = (
                            self.items[self.dragged_item_index], self.items[i]
                        )
                        placed = True
                        break
            if not placed and self.dragged_item_is_prey and self.dragged_prey_ref is not None:
                carried_prey.append(self.dragged_prey_ref)
            self.dragged_item = None
            self.dragged_item_index = -1
            self.dragged_item_is_prey = False
            self.dragged_prey_ref = None
            self.drag_pos = None
            self.context_menu = None

    def draw(self, surface: pygame.Surface, width: int, height: int,
             prey_img: pygame.Surface,
             hunting_skill: int, combat_skill: int, tracking_skill: int,
             font, small_font, tiny_font,
             draw_gradient_fn) -> None:
        """Render inventory overlay."""
        # dim background
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180))
        surface.blit(dim, (0, 0))

        inv_w, inv_h = 600, 450
        ix = width // 2 - inv_w // 2
        iy = height // 2 - inv_h // 2

        draw_gradient_fn(surface, (10, 10, 10), DARK_CYAN, (ix, iy, inv_w, inv_h))
        pygame.draw.rect(surface, CYAN, (ix, iy, inv_w, inv_h), 2)

        # Tabs
        tabs = ["Inventory", "Skills"]
        for i, tab in enumerate(tabs):
            tx, ty = ix + i * 120, iy - 30
            col = DARK_CYAN if self.selected_tab == tab else (30, 30, 30)
            pygame.draw.rect(surface, col, (tx, ty, 110, 30))
            pygame.draw.rect(surface, CYAN, (tx, ty, 110, 30), 1)
            txt = small_font.render(tab, True, WHITE)
            surface.blit(txt, (tx + 55 - txt.get_width() // 2, ty + 5))

        if self.selected_tab == "Inventory":
            title = font.render("Inventory", True, CYAN)
            surface.blit(title, (ix + 20, iy + 20))

            for i in range(self.SLOTS):
                r = self._slot_rect(i, ix, iy)
                pygame.draw.rect(surface, (20, 20, 20), r)
                pygame.draw.rect(surface, CYAN, r, 1)
                if self.dragged_item_index == i:
                    continue
                item = self.items[i]
                if item:
                    if getattr(item, "is_prey", False):
                        # Draw prey sprite instead of coloured rect
                        scaled = pygame.transform.scale(
                            prey_img,
                            (self.SLOT_SIZE - 10, self.SLOT_SIZE - 10),
                        )
                        surface.blit(scaled, r.inflate(-10, -10).topleft)
                    else:
                        pygame.draw.rect(surface, item.icon_color,
                                         r.inflate(-10, -10))
                    if item.count > 1:
                        c = tiny_font.render(str(item.count), True, WHITE)
                        surface.blit(c, (r.right - c.get_width() - 6,
                                         r.bottom - c.get_height() - 4))

            if self.dragged_item:
                mx, my = pygame.mouse.get_pos()
                if self.drag_pos is None:
                    self.drag_pos = (float(mx), float(my))
                else:
                    lx, ly = self.drag_pos
                    self.drag_pos = (lx + (mx - lx) * 0.35, ly + (my - ly) * 0.35)
                dx, dy = int(self.drag_pos[0]), int(self.drag_pos[1])
                if getattr(self.dragged_item, "is_prey", False):
                    scaled = pygame.transform.scale(prey_img, (50, 50))
                    surface.blit(scaled, (dx - 25, dy - 25))
                    pygame.draw.rect(surface, WHITE, (dx - 25, dy - 25, 50, 50), 2)
                else:
                    pygame.draw.rect(surface, self.dragged_item.icon_color,
                                     (dx - 25, dy - 25, 50, 50))
                    pygame.draw.rect(surface, WHITE, (dx - 25, dy - 25, 50, 50), 2)

            if self.context_menu:
                cmx, cmy = self.context_menu["pos"]
                for idx, opt in enumerate(self.context_menu["options"]):
                    rx, ry = cmx, cmy + idx * 32
                    pygame.draw.rect(surface, (30, 30, 30), (rx, ry, 120, 28))
                    pygame.draw.rect(surface, CYAN, (rx, ry, 120, 28), 1)
                    t = small_font.render(opt, True, WHITE)
                    surface.blit(t, (rx + 8, ry + 6))

        elif self.selected_tab == "Skills":
            title = font.render("Skills", True, CYAN)
            surface.blit(title, (ix + 20, iy + 20))
            for i, (name, val) in enumerate([
                ("Hunting", hunting_skill),
                ("Combat", combat_skill),
                ("Tracking", tracking_skill),
            ]):
                sy = iy + 80 + i * 70
                lbl = font.render(name, True, WHITE)
                surface.blit(lbl, (ix + 40, sy))
                bw, bh = 300, 30
                bx = ix + inv_w - 350
                pygame.draw.rect(surface, (20, 20, 20), (bx, sy + 5, bw, bh))
                pygame.draw.rect(surface, CYAN, (bx, sy + 5,
                                                  int(bw * max(0, min(100, val)) / 100), bh))
                pygame.draw.rect(surface, WHITE, (bx, sy + 5, bw, bh), 2)
                pct = small_font.render(f"{int(val)}%", True, WHITE)
                surface.blit(pct, (bx + bw // 2 - pct.get_width() // 2, sy + 10))

            bx = ix + inv_w // 2 - 100
            by = iy + inv_h - 70
            pygame.draw.rect(surface, DARK_CYAN, (bx, by, 200, 40))
            pygame.draw.rect(surface, CYAN, (bx, by, 200, 40), 2)
            bt = small_font.render("Upgrades", True, WHITE)
            surface.blit(bt, (bx + 100 - bt.get_width() // 2, by + 10))

        # Morphs panel
        mp_x = ix + inv_w + 10
        draw_gradient_fn(surface, (10, 10, 10), DARK_CYAN, (mp_x, iy, 150, inv_h))
        pygame.draw.rect(surface, CYAN, (mp_x, iy, 150, inv_h), 2)
        mt = small_font.render("Morphs", True, CYAN)
        surface.blit(mt, (mp_x + 75 - mt.get_width() // 2, iy + 10))
        for i in range(5):
            br = pygame.Rect(mp_x + 10, iy + 40 + i * 70, 130, 60)
            pygame.draw.rect(surface, (50, 50, 50), br)
            pygame.draw.rect(surface, CYAN, br, 1)
            mt2 = tiny_font.render(f"Morph {i+1}", True, WHITE)
            surface.blit(mt2, (br.x + 5, br.y + 5))

        hint = small_font.render("Press I to Close", True, WHITE)
        surface.blit(hint, (ix + inv_w - hint.get_width() - 10, iy + inv_h - 30))
