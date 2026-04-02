"""Asset loading with texture-pack support, screenshots, and font helpers."""

import logging
import os
from datetime import datetime

import pygame

from core.config import resource_path

# Path helpers: this file is at Main/core/assets.py
_HERE = os.path.dirname(os.path.abspath(__file__))  # Main/core
_MAIN = os.path.dirname(_HERE)                       # Main
_ROOT = os.path.dirname(_MAIN)                       # project root

# Assets live inside Main/assets/; texture packs live at root/Texturepacks/
ASSETS_DIR      = os.path.join(_MAIN, "assets")
TEXTUREPACK_DIR = os.path.join(_ROOT, "Texturepacks")
os.makedirs(TEXTUREPACK_DIR, exist_ok=True)


def list_texture_packs() -> list[str]:
    packs = ["Default"]
    try:
        for name in os.listdir(TEXTUREPACK_DIR):
            if os.path.isdir(os.path.join(TEXTUREPACK_DIR, name)):
                packs.append(name)
    except Exception:
        pass
    return packs


# ---------------------------------------------------------------------------
# Image loader
# ---------------------------------------------------------------------------

def load_img(name: str, size: tuple[int, int] | None = None,
             texture_pack: str = "Default") -> pygame.Surface:
    """Load an image from the active texture pack, falling back to assets/."""
    if texture_pack != "Default":
        pack_path = os.path.join(TEXTUREPACK_DIR, texture_pack, name)
        if os.path.exists(pack_path):
            try:
                img = pygame.image.load(pack_path).convert_alpha()
                if size:
                    img = pygame.transform.scale(img, size)
                return img
            except Exception as exc:
                logging.debug("Texture pack load failed for %s: %s", pack_path, exc)

    path = os.path.join(ASSETS_DIR, name)
    try:
        if not os.path.exists(path):
            logging.error("Asset missing: %s", path)
            surf = pygame.Surface(size or (50, 50))
            surf.fill((255, 0, 255))
            return surf
        img = pygame.image.load(path).convert_alpha()
        if size:
            img = pygame.transform.scale(img, size)
        return img
    except Exception as exc:
        logging.error("Error loading %s: %s", name, exc)
        surf = pygame.Surface(size or (50, 50))
        surf.fill((255, 0, 255))
        return surf


# ---------------------------------------------------------------------------
# Font helper
# ---------------------------------------------------------------------------

def get_font(name: str, size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont(name, size)
    except Exception:
        return pygame.font.SysFont("Arial", size)


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def get_desktop_screenshots_folder() -> str:
    ss = os.path.join(_ROOT, "Screenshots")
    os.makedirs(ss, exist_ok=True)
    return ss


def capture_screenshot(screen: pygame.Surface) -> None:
    try:
        folder = get_desktop_screenshots_folder()
        date_str = datetime.now().strftime("%m-%d-%Y")
        filename = f"{date_str}.jpg"
        path = os.path.join(folder, filename)
        count = 1
        while os.path.exists(path):
            filename = f"{date_str}_{count}.jpg"
            path = os.path.join(folder, filename)
            count += 1
        pygame.image.save(screen, path)
        logging.info("Screenshot saved: %s", path)
    except Exception as exc:
        logging.error("Screenshot failed: %s", exc)
