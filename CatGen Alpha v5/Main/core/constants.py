"""Global constants and colour palette for CatGen."""

# Window defaults
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
FPS = 144
GAME_TITLE = "CatGen Alpha v0.0.4"
VERSION = "0.0.4"

# World
WORLD_HALF = 4000  # world extends from -4000 to +4000

# Colours (R, G, B)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DARK_BLUE = (10, 10, 30)
LIGHT_BLUE = (100, 150, 255)
GREEN = (50, 200, 50)
GRAY = (128, 128, 128)
LIGHT_GRAY = (200, 200, 200)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)
PURPLE = (128, 0, 128)
BROWN = (139, 69, 19)
PINK = (255, 192, 203)
CYAN = (0, 255, 255)
DARK_CYAN = (0, 100, 100)

# Network
DEFAULT_PORT = 25565
LAN_BROADCAST_PORT = 25566
HEARTBEAT_INTERVAL = 10  # seconds
CLEANUP_TIMEOUT = 30     # seconds

# Status bars
MAX_STATUS = 100
STAMINA_DRAIN_SECONDS = 30
STAMINA_REGEN_SECONDS = 20

# Movement
BASE_WALK_SPEED = 4
BASE_SPRINT_SPEED = 8
DASH_MAX_CHARGE = 1.5          # seconds
DASH_MIN_STRENGTH = 80         # pixels
DASH_MAX_STRENGTH = 300        # pixels
DASH_COOLDOWN = 1.0            # seconds
DASH_STAMINA_BASE = 12
DASH_STAMINA_SCALE = 18

# Player
JUMP_FORCE = 8.0
GRAVITY = 0.4
MAX_CARRY = 3

# Prey
PREY_SPAWN_INTERVAL = 15.0  # seconds
PREY_DETECTION_RADIUS = 180
PREY_FLEE_SPEED = 3.5
PREY_IDLE_SPEED = 1.5
PREY_WORLD_SIZE = 5000

# Interpolation
REMOTE_LERP_XY = 0.25
REMOTE_LERP_Z = 0.4

# Server-authoritative movement validation
MAX_SPEED_PER_SEC = BASE_SPRINT_SPEED * 60 * 1.5   # generous cap for sprint + dash
