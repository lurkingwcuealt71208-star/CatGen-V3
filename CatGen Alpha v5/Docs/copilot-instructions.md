# CatGen Alpha v5 — Copilot Coding Instructions

These instructions apply to every chat and agent session working on this codebase.
Follow them strictly to prevent regressions.

---

## Project Architecture

Entry point: `py Main/main.py`

| Module | Responsibility |
|--------|---------------|
| `Main/main.py` | Slim game loop (~250 lines); delegates events to `events.py`, drawing to `draw.py` |
| `Main/events.py` | All keyboard/mouse handling; writes back via mutable list-ref wrappers |
| `Main/draw.py` | All per-frame draw calls; `draw_frame()` dispatches to ui/* modules |
| `Main/core/config.py` | Config/controls load-save; `init_default_controls()` → None, `load_controls()` → dict |
| `Main/core/constants.py` | All numeric constants; source of truth for WORLD_HALF, MAX_STATUS, speeds |
| `Main/core/assets.py` | Image/font loading; ASSETS_DIR=`Main/assets/`, TEXTUREPACK_DIR=`Texturepacks/` |
| `Main/game/state.py` | **Single source of truth** for all `PlayerState` attributes. Add attributes HERE before using elsewhere. |
| `Main/game/logic.py` | Pure functions; updates state, no rendering |
| `Main/game/prey.py` | Prey AI; uses `dt` for all movement (no hardcoded FPS) |
| `Main/game/inventory.py` | Inventory grid; hunger must be synced back in main.py via `_hunger_ref` pattern |
| `Main/ui/renderer.py` | World rendering; validate remote coords before use |
| `Main/ui/hud.py` | HUD elements; `draw_bottom_hud()` returns a `pygame.Rect` — caller must store it |
| `Main/ui/menus.py` | All menu screens and handlers |
| `Main/ui/overlays.py` | Overlay screens (character info, upgrades) |
| `SDK/network/client.py` | Client-side session; never sets own position |
| `SDK/network/server.py` | Server-authoritative physics and broadcast |
| `SDK/network/packets.py` | Packet constructors; source of truth for packet formats |
| `SDK/tests/` | pytest suite; `conftest.py` auto-sets sys.path — no per-file path setup needed |
| `SDK/tools/` | Legacy files (main_legacy.py, server_legacy.py, launcher_legacy.py) |

---

## Mandatory Rules Before Any Edit

1. **Attribute names** — If a `PlayerState` attribute is referenced in any file, it MUST be declared in `game/state.py`'s `__init__`. Never use `getattr(state, "attr", default)` to compensate for missing attributes; add them properly.

2. **Physics dt** — All movement must scale with `dt`. Never use `* 60` as an FPS-compensation hack without also applying `dt`. Never multiply by both `60` and `dt` on the same velocity that is also accumulated (double-scaling). Prey GRAZING and FLEEING must use consistent dt handling.

3. **Controls loading** — Always call `init_default_controls()` (no return value), then `controls = load_controls()`. Never pass `controls` as an argument to `load_controls`.

4. **Coordinate validation** — Any `float()` conversion of network-received data must reject NaN and Inf:
   ```python
   import math
   val = float(raw)
   if math.isnan(val) or math.isinf(val):
       continue  # or use default
   ```

5. **Thread safety** — `self.connected` in `NetworkClient` is read by three threads; treat changes carefully. Heartbeat must sleep in ≤0.1 s increments.

6. **Port validation** — User-supplied port strings must be validated: non-empty, digits only, integer in range 1–65535 before calling `int()`.

7. **Hunger sync** — `inventory.handle_input()` takes `hunger_ref=[state.hunger]`. After the call, **always** write back: `state.hunger = _hunger_ref[0]`.

8. **Broadcast rate** — Server position broadcasts use `self._broadcast_tick % 3 == 0` to avoid flooding. Do not remove this gate.

9. **No bare `print()` in network server/client** — Use `logger.info/warning/error`, not `print()`.

10. **Username fallback** — Empty or whitespace-only usernames must fall back to `"Player"` on both server and client.

---

## Pre-Edit Checklist

Before submitting any change to this repo, confirm:

- [ ] Does the change reference a `PlayerState` attribute? → Verify it exists in `game/state.py`.
- [ ] Does the change modify movement physics? → Verify dt-scaling is applied correctly once.
- [ ] Does the change handle network data? → Verify NaN/Inf rejection and bounds clamping.
- [ ] Does the change touch controls? → Verify `load_controls()` pattern (no-arg, returns dict).
- [ ] Does the change affect click detection? → Verify it uses the `pygame.Rect` returned by `draw_bottom_hud()`, not a recalculated one.
- [ ] Run `pytest tests/` and confirm all tests pass before finishing.

---

## Do Not Touch

- `main_legacy.py`, `server_legacy.py`, `launcher_legacy.py` — legacy files, ignore.
- `WORLD_HALF` in `core/constants.py` — world coordinate boundary used everywhere; changing it requires updating NaN-clamping bounds too.
- The `_broadcast_tick % 3` broadcast rate gate in `network/server.py`.

---

## Known Incomplete / Stub Features

These are intentionally unfinished. Do **not** add logic here unless explicitly asked:

- Morphs tab in inventory (`draw()` shows panel but is non-functional)
- Skills beyond UI display (tracking_skill, combat_skill tracked but don't affect gameplay)
- Map interaction (map screen shows position but is read-only)
