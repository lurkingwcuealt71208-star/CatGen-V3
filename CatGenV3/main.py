import logging
import pygame
import sys
import os
import time
import socket
import threading
import json
import random
import queue
from datetime import datetime

# Setup Logging
log_file = os.path.join(os.path.expanduser("~"), "AppData", "Local", "CatGen", "game.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)
logging.info("Game Starting...")

# Helper function for PyInstaller resources
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_save_path(filename):
    """ Get path for save files in Local AppData for portability """
    app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local", "CatGen")
    os.makedirs(app_data, exist_ok=True)
    return os.path.join(app_data, filename)

def get_desktop_screenshots_folder():
    """ Get path to screenshots folder on user's Desktop """
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    ss_folder = os.path.join(desktop, "screenshots")
    os.makedirs(ss_folder, exist_ok=True)
    return ss_folder

# Initialize Pygame and mixer
try:
    pygame.init()
    pygame.mixer.init()
except Exception as e:
    logging.critical(f"Failed to initialize Pygame: {e}")
    sys.exit(1)

# Window settings
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("CatGen Alpha v0.0.3")
clock = pygame.time.Clock()
FPS = 144
is_fullscreen = False

# Controls Configuration
CONFIG_FILE = get_save_path("controls.json")
DEFAULT_CONTROLS = {
    "MOVE_UP": pygame.K_w,
    "MOVE_DOWN": pygame.K_s,
    "MOVE_LEFT": pygame.K_a,
    "MOVE_RIGHT": pygame.K_d,
    "SPRINT": pygame.K_LSHIFT,
    "MEOW": pygame.K_1,
    "CHAT": pygame.K_t,
    "MUSIC": pygame.K_m,
    "TRACK": pygame.K_e,
    "SCENT": pygame.K_f,
    "BURY": pygame.K_b,
    "DASH": pygame.K_q,
    "JUMP": pygame.K_SPACE,
    "INVENTORY": pygame.K_i,
    "MENU": pygame.K_ESCAPE
}
controls = DEFAULT_CONTROLS.copy()

def load_controls():
    global controls
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                loaded = json.load(f)
                # Only update if keys match
                for k in DEFAULT_CONTROLS:
                    if k in loaded:
                        controls[k] = loaded[k]
    except Exception as e:
        print(f"Error loading controls: {e}")

def save_controls():
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(controls, f)
    except Exception as e:
        print(f"Error saving controls: {e}")

load_controls()

# Global variables
username = "Player"
saving_level_timer = 0
saving_level_duration = 2.0  # seconds
music_paused = False
prey_tracks = []  # List of scent/track marks
buried_prey = []  # List of buried prey
last_hunt_time = 0  # Timestamp of last successful prey catch
inventory_open = False
scent_color = (200, 100, 255)
carried_prey = []  # List of prey objects currently being carried
MAX_CARRY = 3
is_multiplayer_host = False
multiplayer_socket = None
client_ip_input = ''
client_port_input = ''
client_input_mode = None

# Network Client Class
class NetworkClient:
    def __init__(self):
        self.socket = None
        self.connected = False
        self.thread = None
        self.message_queue = queue.Queue()
        self.username = "Player"
        self.other_players = {}
        self.other_typing = {}
        self.chat_messages = []
        self.lock = threading.Lock()

    def connect(self, ip, port, username):
        self.disconnect()
        self.username = username
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((ip, int(port)))
            self.socket.settimeout(None)
            self.connected = True
            
            self.send({'type': 'username_change', 'username': username})
            
            self.thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.thread.start()
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self.disconnect()
            return False

    def disconnect(self):
        self.connected = False
        if self.socket:
            try: self.socket.close()
            except: pass
            self.socket = None
        with self.lock:
            self.other_players = {}
            self.other_typing = {}

    def send(self, message):
        if not self.connected or not self.socket: return
        try:
            data = (json.dumps(message) + '\n').encode('utf-8')
            self.socket.sendall(data)
        except Exception as e:
            print(f"Send error: {e}")
            self.disconnect()

    def _receive_loop(self):
        buffer = ""
        while self.connected and self.socket:
            try:
                data = self.socket.recv(4096).decode('utf-8')
                if not data: break
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        self._handle_message(json.loads(line))
            except Exception as e:
                if self.connected: print(f"Receive error: {e}")
                break
        self.disconnect()

    def _handle_message(self, message):
        msg_type = message.get('type')
        with self.lock:
            if msg_type == 'welcome':
                self.other_players = message.get('players', {})
            elif msg_type == 'player_joined':
                addr = message.get('addr')
                uname = message.get('username')
                self.other_players[addr] = {'username': uname, 'x': 0, 'y': 0}
                self.chat_messages.append(f"{uname} joined")
            elif msg_type == 'player_left':
                addr = message.get('addr')
                uname = message.get('username')
                self.other_players.pop(addr, None)
                self.other_typing.pop(addr, None)
                self.chat_messages.append(f"{uname} left")
            elif msg_type == 'player_position':
                addr = message.get('addr')
                if addr in self.other_players:
                    self.other_players[addr]['x'] = message.get('x', 0)
                    self.other_players[addr]['y'] = message.get('y', 0)
            elif msg_type == 'chat':
                uname = message.get('username')
                msg = message.get('message')
                self.chat_messages.append(f"{uname}: {msg}")
            elif msg_type == 'typing_start':
                self.other_typing[message.get('addr')] = True
            elif msg_type == 'typing_stop':
                self.other_typing.pop(message.get('addr'), None)
            elif msg_type == 'username_change':
                addr = message.get('addr')
                if addr in self.other_players:
                    self.other_players[addr]['username'] = message.get('new_username')

network_client = NetworkClient()

# Colors
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

# Load assets helper with error handling
def load_img(name, size=None):
    path = resource_path(os.path.join("assets", name))
    try:
        if not os.path.exists(path):
            logging.error(f"Asset missing: {path}")
            # Fallback to a placeholder surface if image fails to load
            placeholder = pygame.Surface(size if size else (50, 50))
            placeholder.fill((255, 0, 255)) # Magenta placeholder
            return placeholder
        img = pygame.image.load(path).convert_alpha()
        if size:
            img = pygame.transform.scale(img, size)
        return img
    except Exception as e:
        logging.error(f"Error loading image {name}: {e}")
        placeholder = pygame.Surface(size if size else (50, 50))
        placeholder.fill((255, 0, 255))
        return placeholder

def capture_screenshot():
    """ Capture screen and save to Desktop/screenshots in JPEG format """
    try:
        folder = get_desktop_screenshots_folder()
        date_str = datetime.now().strftime("%m-%d-%Y")
        filename = f"{date_str}.jpg"
        path = os.path.join(folder, filename)
        
        # Handle duplicates
        count = 1
        while os.path.exists(path):
            filename = f"{date_str}_{count}.jpg"
            path = os.path.join(folder, filename)
            count += 1
            
        pygame.image.save(screen, path)
        logging.info(f"Screenshot saved: {path}")
    except Exception as e:
        logging.error(f"Failed to capture screenshot: {e}")

def toggle_fullscreen():
    global is_fullscreen, screen, WIDTH, HEIGHT
    is_fullscreen = not is_fullscreen
    if is_fullscreen:
        # Get desktop resolution for better fullscreen
        info = pygame.display.Info()
        screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN | pygame.RESIZABLE)
        WIDTH, HEIGHT = info.current_w, info.current_h
    else:
        WIDTH, HEIGHT = 800, 600
        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    logging.info(f"Fullscreen toggled: {is_fullscreen}")

# Load original images
sky_img = load_img("sky.png")
grass_img = load_img("grass.png")
cat_img = load_img("cat_idle.png")
prey_img = load_img("preytest1alpha.png", (50, 50))
paw_img = load_img("cat_idle.png", (24, 24))

# Load and play music with error handling
try:
    music_path = resource_path(os.path.join("assets", "creative2.ogg"))
    if os.path.exists(music_path):
        pygame.mixer.music.load(music_path)
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)
    else:
        logging.error(f"Music file missing: {music_path}")
except Exception as e:
    logging.error(f"Could not load music: {e}")

# Fonts
def get_font(name, size):
    try:
        return pygame.font.SysFont(name, size)
    except:
        return pygame.font.SysFont("Arial", size)

font = get_font("Arial", 28)
small_font = get_font("Arial", 20)
tiny_font = get_font("Arial", 16)
clock_font = get_font("Arial", 24)
aero_font = get_font("Segoe UI", 20)

# Game state
game_state = "playing"  # "playing", "menu", "map", "credits", "changelog", "keybinds", "multiplayer"
cat_x = WIDTH // 2
cat_y = HEIGHT // 2
world_x = 0  # Camera position
world_y = 0

# Status bars (0-100)
hunger = 100
thirst = 100
bathroom = 100
sleep = 100
stamina = 100

# Stamina system
max_stamina = 100
stamina_drain_rate = 100 / (30 * FPS)  # 30 seconds to drain
stamina_regen_rate = 100 / (20 * FPS)  # 20 seconds to fully regenerate
is_sprinting = False

# Chat system
chat_open = False
chat_input = ""
chat_messages = []
player_message = ""
message_timer = 0

def connect_to_server(ip, port, username):
    """Connect to a real multiplayer server"""
    return network_client.connect(ip, port, username)

def send_to_server(message):
    """Send a message to the server"""
    network_client.send(message)

def disconnect_from_server():
    """Disconnect from the server"""
    network_client.disconnect()

# Prey system (New AI Implementation)
class Prey:
    IDLE = "idle"
    GRAZING = "grazing"
    ALERT = "alert"
    FLEEING = "fleeing"
    HIDING = "hiding"

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = 0
        self.vy = 0
        self.state = self.IDLE
        self.state_timer = 0
        self.speed = 1.5
        self.flee_speed = 3.5
        self.detection_radius = 180
        self.alpha = 255
        self.visible = True
        self.panic_timer = 0
        self.hide_timer = 0
        self.last_known_threat = None
        self.change_direction()

    def change_direction(self):
        angle = random.uniform(0, 2 * 3.14159)
        self.vx = random.uniform(0.5, 1.0) * self.speed * (1 if random.random() > 0.5 else -1)
        self.vy = random.uniform(0.5, 1.0) * self.speed * (1 if random.random() > 0.5 else -1)

    def update(self, player_x, player_y, dt):
        dist = ((self.x - player_x)**2 + (self.y - player_y)**2)**0.5

        if self.state == self.HIDING:
            self.hide_timer -= dt
            if self.alpha > 0:
                self.alpha = max(0, self.alpha - (255 * dt)) # Fade out over 1s
            if self.hide_timer <= 0:
                return False  # Mark for removal
            return True

        if self.state == self.FLEEING:
            self.panic_timer -= dt
            if self.panic_timer <= 0:
                self.state = self.HIDING
                self.hide_timer = 3.0  # 3 seconds of hiding
                return True
            
            # Flee away from player
            dx = self.x - player_x
            dy = self.y - player_y
            mag = (dx**2 + dy**2)**0.5
            if mag > 0:
                self.vx = (dx / mag) * self.flee_speed * 60 * dt
                self.vy = (dy / mag) * self.flee_speed * 60 * dt
        
        elif dist < self.detection_radius:
            if self.state != self.ALERT:
                self.state = self.ALERT
                self.state_timer = 3.0
            self.last_known_threat = (player_x, player_y)
            # If really close, start fleeing
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
                        self.change_direction()
                    else:
                        self.vx, self.vy = 0, 0

        # Move
        if self.state != self.IDLE and self.state != self.ALERT:
            self.x += self.vx
            self.y += self.vy
        elif self.state == self.GRAZING:
            self.x += self.vx * 60 * dt
            self.y += self.vy * 60 * dt

        # Keep within boundaries (simple bounce for now)
        if self.x < 50 or self.x > WIDTH - 50:
            self.vx *= -1
            self.x = max(50, min(WIDTH - 50, self.x))
        if self.y < 50 or self.y > HEIGHT - 50:
            self.vy *= -1
            self.y = max(50, min(HEIGHT - 50, self.y))
        
        return True

    def draw(self, surface):
        if self.alpha < 255:
            temp_img = prey_img.copy()
            temp_img.set_alpha(self.alpha)
            surface.blit(temp_img, (self.x - 25, self.y - 25))
        else:
            surface.blit(prey_img, (self.x - 25, self.y - 25))

# Inventory System
class Item:
    def __init__(self, name, icon_color, description=""):
        self.name = name
        self.icon_color = icon_color
        self.description = description

class Inventory:
    def __init__(self, slots=20):
        self.slots = slots
        self.items = [None] * slots  # Grid of 20 slots

    def add_item(self, item):
        for i in range(self.slots):
            if self.items[i] is None:
                self.items[i] = item
                return True
        return False

    def draw(self, surface):
        # Semi-transparent background
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        # Inventory box
        inv_w, inv_h = 400, 320
        inv_x, inv_y = (WIDTH - inv_w) // 2, (HEIGHT - inv_h) // 2
        pygame.draw.rect(surface, (50, 50, 50), (inv_x, inv_y, inv_w, inv_h))
        pygame.draw.rect(surface, WHITE, (inv_x, inv_y, inv_w, inv_h), 3)

        title = font.render("Inventory (WIP)", True, WHITE)
        surface.blit(title, (inv_x + 10, inv_y + 10))

        # Grid
        grid_x, grid_y = inv_x + 20, inv_y + 50
        slot_size = 60
        margin = 10
        for i in range(self.slots):
            row = i // 5
            col = i % 5
            sx = grid_x + col * (slot_size + margin)
            sy = grid_y + row * (slot_size + margin)
            pygame.draw.rect(surface, (80, 80, 80), (sx, sy, slot_size, slot_size))
            pygame.draw.rect(surface, LIGHT_GRAY, (sx, sy, slot_size, slot_size), 1)
            
            if self.items[i] is not None:
                item = self.items[i]
                icon_color = getattr(item, 'icon_color', RED)
                item_name = getattr(item, 'name', "Item")
                pygame.draw.rect(surface, icon_color, (sx+5, sy+5, slot_size-10, slot_size-10))
                name_txt = tiny_font.render(item_name[:8], True, WHITE)
                surface.blit(name_txt, (sx + 2, sy + slot_size - 18))

        instr = small_font.render("Press I to Close", True, WHITE)
        surface.blit(instr, (inv_x + inv_w - instr.get_width() - 10, inv_y + inv_h - 30))

inventory = Inventory()

# Map data - simplified
map_width = 20
map_height = 15
player_map_x = map_width // 2
player_map_y = map_height // 2

# Prey system variables
prey_list = []
prey_spawn_timer = 0
# Change prey spawn interval to be much less frequent
prey_spawn_interval = 70 * FPS  # Spawn every ~70 seconds
pounce_meter = 0
max_pounce = 100
pounce_charging = False
pounce_ready = False

def spawn_prey():
    # Spawn prey at a random location within the visible area
    px = random.randint(100, WIDTH - 100)
    py = random.randint(100, HEIGHT - 100)
    prey_list.append(Prey(px, py))

def update_prey(dt):
    global prey_spawn_timer, prey_list
    prey_spawn_timer += dt
    if prey_spawn_timer >= prey_spawn_interval:
        spawn_prey()
        prey_spawn_timer = 0
    
    # Update each prey
    cat_rect_center = (WIDTH // 2, HEIGHT // 2)
    new_prey_list = []
    for prey in prey_list:
        if prey.update(cat_rect_center[0], cat_rect_center[1], dt):
            new_prey_list.append(prey)
    prey_list = new_prey_list

def draw_prey():
    for prey in prey_list:
        prey.draw(screen)

def check_prey_collision():
    global hunger, prey_list, last_hunt_time, carried_prey
    cat_rect = pygame.Rect(WIDTH // 2 - cat_img.get_width() // 2, HEIGHT // 2 - cat_img.get_height() // 2, cat_img.get_width(), cat_img.get_height())
    caught = False
    for prey in prey_list[:]:
        if prey.state == Prey.HIDING: continue
        prey_rect = pygame.Rect(prey.x - 25, prey.y - 25, 50, 50)
        if cat_rect.colliderect(prey_rect):
            hunger = min(100, hunger + 20)
            prey_list.remove(prey)
            last_hunt_time = time.time()
            
            # Carry system
            if len(carried_prey) < MAX_CARRY:
                carried_prey.append(prey)
            else:
                inventory.add_item(Item("Mouse", (200, 150, 100), "A fresh catch."))
            
            caught = True
            break
    
    if not caught:
        # Pounce failed - trigger panic in nearby prey
        for prey in prey_list:
            dist = ((prey.x - (WIDTH//2))**2 + (prey.y - (HEIGHT//2))**2)**0.5
            if dist < 150:
                prey.state = Prey.FLEEING
                prey.panic_timer = 1.5

def draw_pounce_meter():
    # Only show if near prey
    cat_rect = pygame.Rect(WIDTH // 2 - cat_img.get_width() // 2, HEIGHT // 2 - cat_img.get_height() // 2, cat_img.get_width(), cat_img.get_height())
    near_prey = any(pygame.Rect(prey.x - 25, prey.y - 25, 50, 50).colliderect(cat_rect.inflate(100, 100)) for prey in prey_list if prey.state != Prey.HIDING)
    if near_prey:
        bar_x = WIDTH // 2 - 50
        bar_y = HEIGHT // 2 - 80
        pygame.draw.rect(screen, GRAY, (bar_x, bar_y, 100, 12))
        pygame.draw.rect(screen, ORANGE, (bar_x, bar_y, int((pounce_meter / max_pounce) * 100), 12))
        pygame.draw.rect(screen, BLACK, (bar_x, bar_y, 100, 12), 2)
        text = tiny_font.render("Pounce", True, WHITE)
        screen.blit(text, (bar_x + 110, bar_y - 2))

def draw_status_bars():
    """Draw all status bars"""
    bar_width = 150
    bar_height = 15
    start_x = 10
    start_y = 10

    bars = [
        ("Hunger", hunger, RED),
        ("Thirst", thirst, LIGHT_BLUE),
        ("Bathroom", bathroom, YELLOW),
        ("Sleep", sleep, PURPLE),
        ("Stamina", stamina, GREEN)
    ]

    for i, (name, value, color) in enumerate(bars):
        y = start_y + i * 25

        # Background
        pygame.draw.rect(screen, GRAY, (start_x, y, bar_width, bar_height))

        # Fill
        fill_width = int((value / 100) * bar_width)
        pygame.draw.rect(screen, color, (start_x, y, fill_width, bar_height))

        # Border
        pygame.draw.rect(screen, BLACK, (start_x, y, bar_width, bar_height), 2)

        # Text
        text = tiny_font.render(f"{name}: {int(value)}", True, WHITE)
        screen.blit(text, (start_x + bar_width + 10, y))

def draw_clock():
    """Draw current time"""
    current_time = datetime.now().strftime("%H:%M:%S")
    time_text = clock_font.render(f"Time: {current_time}", True, WHITE)
    screen.blit(time_text, (10, HEIGHT - 30))

def draw_grass_background():
    """Draw simple grass background that scrolls"""
    # Calculate offset for infinite scrolling
    grass_offset_x = world_x % grass_img.get_width()
    grass_offset_y = world_y % grass_img.get_height()

    # Draw grass tiles to cover screen
    tiles_x = (WIDTH // grass_img.get_width()) + 2
    tiles_y = (HEIGHT // grass_img.get_height()) + 2

    for x in range(tiles_x):
        for y in range(tiles_y):
            screen.blit(grass_img, (
                x * grass_img.get_width() - grass_offset_x,
                y * grass_img.get_height() - grass_offset_y
            ))

def draw_map():
    """Draw the game map with player position"""
    screen.fill(BLACK)

    # Title
    title_text = font.render("Game Map", True, WHITE)
    screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 20))

    # Map grid
    start_x = WIDTH // 2 - (map_width * 15) // 2
    start_y = HEIGHT // 2 - (map_height * 15) // 2
    cell_size = 15

    for row in range(map_height):
        for col in range(map_width):
            x = start_x + col * cell_size
            y = start_y + row * cell_size

            # Default grass color
            color = GREEN

            # Player position
            if col == player_map_x and row == player_map_y:
                color = RED  # Player dot

            pygame.draw.rect(screen, color, (x, y, cell_size, cell_size))
            pygame.draw.rect(screen, WHITE, (x, y, cell_size, cell_size), 1)

    # Player info
    player_text = small_font.render(f"Player Position: ({player_map_x}, {player_map_y})", True, WHITE)
    screen.blit(player_text, (WIDTH // 2 - player_text.get_width() // 2, start_y + map_height * cell_size + 20))

    # Legend
    legend_text = small_font.render("Red dot = Your position", True, RED)
    screen.blit(legend_text, (WIDTH // 2 - legend_text.get_width() // 2, HEIGHT - 80))

    # Instructions
    inst_text = small_font.render("Press ESC to return to menu", True, WHITE)
    screen.blit(inst_text, (WIDTH // 2 - inst_text.get_width() // 2, HEIGHT - 50))

def draw_menu():
    """Draw the main menu"""
    screen.fill(DARK_BLUE)

    # Title
    title_text = font.render("CatGen Alpha - Main Menu", True, WHITE)
    screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 50))

    # Menu options
    menu_options = [
        "R - Resume Game",
        "M - View Map",
        "P - Multiplayer",
        "C - Credits",
        "L - Changelog",
        "K - Keybinds",
        "Q - Quit Game",
        f"T - Toggle Music ({'Off' if music_paused else 'On'})"
    ]

    for i, option in enumerate(menu_options):
        option_text = small_font.render(option, True, WHITE)
        screen.blit(option_text, (WIDTH // 2 - option_text.get_width() // 2, 150 + i * 40))

    # Current time
    current_time = datetime.now().strftime("%H:%M:%S")
    time_text = small_font.render(f"Current Time: {current_time}", True, LIGHT_GRAY)
    screen.blit(time_text, (WIDTH // 2 - time_text.get_width() // 2, HEIGHT - 50))

def draw_multiplayer_menu():
    """Draw multiplayer setup menu"""
    screen.fill(DARK_BLUE)

    # Title
    title_text = font.render("Multiplayer Setup", True, WHITE)
    screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 50))

    # Options
    options = [
        "H - Host LAN Game",
        "J - Join LAN Game",
        "Status: " + ("Connected" if network_client.connected else "Not connected"),
        f"Connected Players: {len(network_client.other_players)}"
    ]

    for i, option in enumerate(options):
        color = WHITE
        if option.startswith("Status:"):
            color = GREEN if network_client.connected else LIGHT_GRAY
        elif option.startswith("Connected"):
            color = YELLOW

        option_text = small_font.render(option, True, color)
        screen.blit(option_text, (WIDTH // 2 - option_text.get_width() // 2, 150 + i * 40))

    # Username/IP/Port input
    if client_input_mode == 'username':
        prompt = f"Enter Username: {username}_"
        prompt_text = small_font.render(prompt, True, WHITE)
        screen.blit(prompt_text, (WIDTH // 2 - prompt_text.get_width() // 2, 350))
    elif client_input_mode == 'ip':
        prompt = f"Enter IP: {client_ip_input}_"
        prompt_text = small_font.render(prompt, True, WHITE)
        screen.blit(prompt_text, (WIDTH // 2 - prompt_text.get_width() // 2, 350))
    elif client_input_mode == 'port':
        prompt = f"Enter Port: {client_port_input}_"
        prompt_text = small_font.render(prompt, True, WHITE)
        screen.blit(prompt_text, (WIDTH // 2 - prompt_text.get_width() // 2, 350))

    # Instructions
    inst_text = small_font.render("Press ESC to return to main menu", True, WHITE)
    screen.blit(inst_text, (WIDTH // 2 - inst_text.get_width() // 2, HEIGHT - 100))

    # IP info if hosting
    if is_multiplayer_host:
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            ip_text = tiny_font.render(f"Your IP: {local_ip} (Others use this to connect)", True, LIGHT_BLUE)
            screen.blit(ip_text, (WIDTH // 2 - ip_text.get_width() // 2, HEIGHT - 70))
        except:
            pass

def draw_chat():
    """Draw chat interface (Roblox style, Aero look)"""
    if not chat_open and len(chat_messages) == 0:
        return

    # Chat history background (rounded, semi-transparent, Aero style)
    chat_height = 200
    chat_bg = pygame.Surface((WIDTH - 40, chat_height), pygame.SRCALPHA)
    chat_bg.fill((240, 255, 255, 180))  # Aero blue/white
    pygame.draw.rect(chat_bg, (180, 220, 255, 220), chat_bg.get_rect(), border_radius=18)
    screen.blit(chat_bg, (20, HEIGHT - chat_height - 40))

    # Chat messages (stacked, Roblox style)
    max_visible = 8
    with network_client.lock:
        visible_messages = network_client.chat_messages[-max_visible:]
    for i, msg in enumerate(visible_messages):
        msg_text = aero_font.render(msg, True, (30, 30, 30))
        screen.blit(msg_text, (36, HEIGHT - chat_height - 30 + i * 24))

    # Chat input
    if chat_open:
        input_bg = pygame.Surface((WIDTH - 40, 36), pygame.SRCALPHA)
        input_bg.fill((240, 255, 255, 220))
        pygame.draw.rect(input_bg, (180, 220, 255, 220), input_bg.get_rect(), border_radius=18)
        screen.blit(input_bg, (20, HEIGHT - 38))

        prompt = f"Say: {chat_input}"
        input_text = aero_font.render(prompt, True, (30, 30, 30))
        screen.blit(input_text, (36, HEIGHT - 32))

        # Cursor
        cursor_x = 36 + input_text.get_width()
        if int(time.time() * 2) % 2:  # Blinking cursor
            pygame.draw.line(screen, (30, 30, 30), (cursor_x, HEIGHT - 32), (cursor_x, HEIGHT - 12), 2)

        # Typing indicator (Aero overlay, Minecraft-style fade)
        if chat_input:
            typing_alpha = int(220 * min(1.0, abs((time.time() * 2 % 2) - 1)))
            overlay_width = 320
            overlay_height = 48
            overlay_surf = pygame.Surface((overlay_width, overlay_height), pygame.SRCALPHA)
            overlay_surf.fill((240, 255, 255, 180))
            pygame.draw.rect(overlay_surf, (180, 220, 255, int(typing_alpha)), overlay_surf.get_rect(), border_radius=18)
            text = aero_font.render(f"{username} is typing...", True, (30, 30, 30))
            overlay_surf.blit(text, (overlay_width // 2 - text.get_width() // 2, overlay_height // 2 - text.get_height() // 2))
            screen.blit(overlay_surf, (WIDTH // 2 - overlay_width // 2, HEIGHT - chat_height - 80))

def draw_speech_bubble(text, x, y):
    """Draw speech bubble above character (no triangle, Aero style)"""
    if not text:
        return

    bubble_text = aero_font.render(text, True, (30, 30, 30))
    bubble_width = bubble_text.get_width() + 20
    bubble_height = bubble_text.get_height() + 10

    # Bubble background (rounded, Aero style)
    bubble_rect = pygame.Rect(x - bubble_width // 2, y - bubble_height - 10, bubble_width, bubble_height)
    bubble_surf = pygame.Surface((bubble_width, bubble_height), pygame.SRCALPHA)
    bubble_surf.fill((240, 255, 255, 180))
    pygame.draw.rect(bubble_surf, (180, 220, 255, 220), bubble_surf.get_rect(), border_radius=12)
    bubble_surf.blit(bubble_text, (10, 5))
    screen.blit(bubble_surf, (bubble_rect.x, bubble_rect.y))

def show_credits():
    """Show credits screen"""
    screen.fill(BLACK)

    # Title
    title_text = font.render("Credits", True, WHITE)
    screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 30))

    lines = [
        "Catgen Alpha Ver001.3"
        "Development still in alpha stage!"
        "Credits to myself!"
        "Press ESC to return to menu",
    ]

    for i, line in enumerate(lines):
        if line == "":
            continue
        text = small_font.render(line, True, WHITE)
        screen.blit(text, (WIDTH // 2 - text.get_width() // 2, 80 + i * 30))

def show_changelog():
    """Show changelog screen"""
    screen.fill(DARK_BLUE)

    # Title
    title_text = font.render("Changelog - CatGen Alpha", True, WHITE)
    screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 30))

    lines = [
        "v0.0.1.3:",
        "- Did some various edits."
        "- Fixed what ai fucked up because I can code in python now"
        "",
        "v0.0.1.2:",
        "- Original cat sprite restored",
        "- Infinite scrolling grass background",
        "- Status bars (Hunger, Thirst, Bathroom, Sleep, Stamina)",
        "- Sprinting system (Hold Shift)",
        "- Chat system (Press T)",
        "- Meow function (Press 1)",
        "- Simplified map with player position",
        "- LAN multiplayer setup menu",
        "",
        "v0.0.1:",
        "- Basic cat movement with WASD/Arrow keys",
        "- Grass and sky backgrounds",
        "- First test cat sprite",
        "- Credits and changelog screens",
        "- Background music",
        "",
        "Press ESC to return to menu"
    ]

    for i, line in enumerate(lines):
        if line == "":
            continue
        elif line.startswith("v0.0"):
            text = small_font.render(line, True, LIGHT_BLUE)
        elif line.startswith("-"):
            text = small_font.render(line, True, LIGHT_GRAY)
        else:
            text = small_font.render(line, True, WHITE)
        screen.blit(text, (50, 80 + i * 22))

def show_keybinds():
    """Show keybinds screen"""
    screen.fill(BLACK)

    # Title
    title_text = font.render("Keybinds", True, WHITE)
    screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 30))

    # Keybind list
    keybinds = [
        "Movement:",
        "  WASD or Arrow Keys - Move cat",
        "  Hold Shift - Sprint (uses stamina)",
        "",
        "Actions:",
        "  1 - Meow",
        "  T - Open chat",
        "  M - Toggle music pause/play",
        "  E - Track prey",
        "  F - Scent mark",
        "  B - Bury prey",
        "  Q - Dash",
        "  Space - Jump (hold for long jump)",
        "",
        "Menu Controls:",
        "  ESC - Open/Close menu",
        "  R - Resume game",
        "  M - View map",
        "  P - Multiplayer setup",
        "  C - Credits",
        "  L - Changelog",
        "  K - Keybinds",
        "  Q - Quit game",
        "  T - Toggle music (menu)",
        "",
        "Press ESC to return to menu"
    ]

    for i, line in enumerate(keybinds):
        if line.startswith("  "):
            text = small_font.render(line, True, LIGHT_GRAY)
        elif line == "":
            continue
        else:
            text = small_font.render(line, True, WHITE)
        screen.blit(text, (50, 80 + i * 25))

def start_lan_host():
    """Start hosting a LAN game"""
    global is_multiplayer_host, multiplayer_socket
    try:
        multiplayer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        multiplayer_socket.bind(('', 12345))
        multiplayer_socket.listen(5)
        is_multiplayer_host = True
        print("LAN server started on port 12345")
    except Exception as e:
        print(f"Failed to start LAN server: {e}")

def update_status_bars(dt):
    """Update status bars over time"""
    global hunger, thirst, bathroom, sleep

    # Decrease over time (very slow for demo) - normalized to 60 FPS
    hunger -= 0.6 * dt
    thirst -= 0.9 * dt
    bathroom -= 0.48 * dt
    sleep -= 0.3 * dt

    # Clamp values
    hunger = max(0, hunger)
    thirst = max(0, thirst)
    bathroom = max(0, bathroom)
    sleep = max(0, sleep)

def update_stamina(dt):
    """Update stamina based on sprinting"""
    global stamina, is_sprinting

    if is_sprinting and stamina > 0:
        stamina -= (100 / 30) * dt  # 30 seconds to drain
        if stamina <= 0:
            stamina = 0
            is_sprinting = False
    elif not is_sprinting and stamina < max_stamina:
        stamina += (100 / 20) * dt  # 20 seconds to fully regenerate
        if stamina > max_stamina:
            stamina = max_stamina

def update_chat_messages(dt):
    """Update chat message timers"""
    global message_timer, player_message

    if message_timer > 0:
        message_timer -= dt
        if message_timer <= 0:
            player_message = ""
            message_timer = 0

def update_player_map_position():
    """Update player position on map based on world coordinates"""
    global player_map_x, player_map_y

    # Convert world coordinates to map coordinates
    player_map_x = (map_width // 2) + (world_x // 100)
    player_map_y = (map_height // 2) + (world_y // 100)

    # Keep within map bounds
    player_map_x = max(0, min(player_map_x, map_width - 1))
    player_map_y = max(0, min(player_map_y, map_height - 1))

def handle_chat_input(event):
    """Handle chat input"""
    global chat_input, chat_open, chat_messages, player_message, message_timer

    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_RETURN:
            if chat_input.strip():
                with network_client.lock:
                    network_client.chat_messages.append(f"You: {chat_input}")
                player_message = chat_input
                message_timer = 5.0  # 5 seconds
                
                # Send chat to server
                network_client.send({'type': 'chat', 'message': chat_input})
                network_client.send({'type': 'typing_stop'})
                
                chat_input = ""
            chat_open = False
        elif event.key == pygame.K_ESCAPE:
            chat_open = False
            chat_input = ""
            # Send typing stop
            network_client.send({'type': 'typing_stop'})
        elif event.key == pygame.K_BACKSPACE:
            chat_input = chat_input[:-1]
        else:
            if not chat_input:  # Just started typing
                network_client.send({'type': 'typing_start'})
            chat_input += event.unicode

def handle_menu_input(event):
    """Handle input while in menu"""
    global game_state, music_paused

    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_r:
            game_state = "playing"
        elif event.key == pygame.K_m:
            game_state = "map"
        elif event.key == pygame.K_p:
            game_state = "multiplayer"
        elif event.key == pygame.K_c:
            game_state = "credits"
        elif event.key == pygame.K_l:
            game_state = "changelog"
        elif event.key == pygame.K_k:
            game_state = "keybinds"
        elif event.key == pygame.K_q:
            pygame.quit()
            sys.exit()
        elif event.key == pygame.K_t:
            # Toggle music from menu
            if pygame.mixer.music.get_busy() and not music_paused:
                pygame.mixer.music.pause()
                music_paused = True
            else:
                pygame.mixer.music.unpause()
                music_paused = False

def handle_multiplayer_input(event):
    """Handle multiplayer menu input"""
    global game_state, client_input_mode, client_ip_input, client_port_input, username

    if client_input_mode == 'username':
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if username.strip():
                    client_input_mode = 'ip'
                    client_ip_input = ''
                    client_port_input = ''
                else:
                    username = "Player"
            elif event.key == pygame.K_BACKSPACE:
                username = username[:-1]
            elif event.key == pygame.K_ESCAPE:
                client_input_mode = None
                username = "Player"
            else:
                if len(username) < 20:
                    username += event.unicode
        return
    elif client_input_mode == 'ip':
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if client_ip_input.strip():
                    client_input_mode = 'port'
                else:
                    client_input_mode = None
            elif event.key == pygame.K_BACKSPACE:
                client_ip_input = client_ip_input[:-1]
            elif event.key == pygame.K_ESCAPE:
                client_input_mode = None
                client_ip_input = ''
            else:
                if len(client_ip_input) < 32:
                    client_ip_input += event.unicode
        return
    elif client_input_mode == 'port':
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                # Try to connect
                if connect_to_server(client_ip_input, client_port_input, username):
                    game_state = "playing"
                client_input_mode = None
                client_ip_input = ''
                client_port_input = ''
            elif event.key == pygame.K_BACKSPACE:
                client_port_input = client_port_input[:-1]
            elif event.key == pygame.K_ESCAPE:
                client_input_mode = None
                client_port_input = ''
            else:
                if len(client_port_input) < 6 and event.unicode.isdigit():
                    client_port_input += event.unicode
        return

    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            game_state = "menu"
        elif event.key == pygame.K_h:
            start_lan_host()
        elif event.key == pygame.K_j:
            client_input_mode = 'username'
            username = "Player"

# Add input for credits, changelog, keybinds, and map screens
def handle_other_screen_input(event):
    """Handle input for credits, changelog, keybinds, and map screens"""
    global game_state

    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            game_state = "menu"

# Add placeholders for new prey system actions
def track_prey():
    """Find nearby prey and start tracking them (multiple trails)"""
    global prey_tracks
    # Track all prey within a certain radius
    for prey in prey_list:
        dist = ((prey.x - (WIDTH//2))**2 + (prey.y - (HEIGHT//2))**2)**0.5
        if dist < 400: # Tracking radius
            # Add a scent mark at current prey position
            prey_tracks.append({
                'x': world_x + (prey.x - WIDTH//2), 
                'y': world_y + (prey.y - HEIGHT//2), 
                'time': time.time(),
                'type': 'trail',
                'prey_id': id(prey)
            })
    print(f"Tracking {len(prey_list)} nearby prey.")

def scent_mark():
    # Placeholder: Add a scent mark at the player's position
    prey_tracks.append({'x': world_x, 'y': world_y, 'type': 'scent', 'time': time.time()})

def bury_prey():
    # Restrict bury mechanic: success catch within last 30 seconds
    current_time = time.time()
    if current_time - last_hunt_time <= 30:
        buried_prey.append({'x': world_x, 'y': world_y, 'time': current_time})
        print("Prey buried successfully.")
        return True
    else:
        print("Cannot bury. No fresh catch within 30 seconds.")
        return False

# Add remapping state
remapping_key = None

def draw_keybinds():
    """Show keybinds screen (remastered with remapping)"""
    screen.fill(BLACK)

    # Title
    title_text = font.render("Settings - Keybinds", True, WHITE)
    screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 30))

    # Instructions
    instr = small_font.render("Click an option to remap. Press ESC to save/return.", True, LIGHT_GRAY)
    screen.blit(instr, (WIDTH // 2 - instr.get_width() // 2, 70))

    # Keybind list
    y_offset = 110
    col1_x = 50
    col2_x = WIDTH // 2 + 20
    
    i = 0
    for action, key in controls.items():
        # Draw box for each keybind
        bx = col1_x if i < 8 else col2_x
        by = y_offset + (i % 8) * 45
        
        box_w = 330
        box_h = 35
        
        color = GRAY
        if remapping_key == action:
            color = YELLOW
        
        pygame.draw.rect(screen, (30, 30, 30), (bx, by, box_w, box_h))
        pygame.draw.rect(screen, color, (bx, by, box_w, box_h), 2)
        
        key_name = pygame.key.name(key).upper()
        if remapping_key == action:
            key_name = "..."
        
        txt = small_font.render(f"{action.replace('_', ' ')}:", True, WHITE)
        screen.blit(txt, (bx + 10, by + 7))
        
        key_txt = small_font.render(key_name, True, color)
        screen.blit(key_txt, (bx + box_w - key_txt.get_width() - 10, by + 7))
        i += 1

def handle_keybinds_input(event):
    global remapping_key, controls, game_state
    
    if remapping_key:
        if event.type == pygame.KEYDOWN:
            # Check for escape (cancel)
            if event.key == pygame.K_ESCAPE:
                remapping_key = None
                return
            
            # Check if key already used
            for action, key in controls.items():
                if key == event.key:
                    print(f"Key {pygame.key.name(event.key)} already bound to {action}")
                    remapping_key = None
                    return
            
            controls[remapping_key] = event.key
            remapping_key = None
            save_controls()
        return

    if event.type == pygame.MOUSEBUTTONDOWN:
        mx, my = pygame.mouse.get_pos()
        y_offset = 110
        col1_x = 50
        col2_x = WIDTH // 2 + 20
        
        i = 0
        for action in controls.keys():
            bx = col1_x if i < 8 else col2_x
            by = y_offset + (i % 8) * 45
            if bx <= mx <= bx + 330 and by <= my <= by + 35:
                remapping_key = action
                break
            i += 1

    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            game_state = "menu"

    # Main game loop
running = True
last_meow_time = 0

try:
    while running:
        # Calculate delta time
        dt = clock.tick(FPS) / 1000.0  # seconds
        
        # Debug information
        current_fps = clock.get_fps()

        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.VIDEORESIZE:
                WIDTH, HEIGHT = event.w, event.h
                if not is_fullscreen:
                    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                logging.info(f"Window resized to {WIDTH}x{HEIGHT}")

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    toggle_fullscreen()
                elif event.key == pygame.K_F12:
                    capture_screenshot()

            if game_state == "playing":
                if chat_open:
                    handle_chat_input(event)
                else:
                    if event.type == pygame.KEYDOWN:
                        if event.key == controls["MENU"]:
                            game_state = "menu"
                        elif event.key == controls["CHAT"]:
                            chat_open = True
                            chat_input = ""
                        elif event.key == controls["MEOW"]:
                            current_time = time.time()
                            if current_time - last_meow_time > 1:  # Cooldown
                                print("*Meow!*")
                                player_message = "*Meow!*"
                                message_timer = 180  # 3 seconds
                                last_meow_time = current_time
                        elif event.key == controls["MUSIC"]:
                            if pygame.mixer.music.get_busy():
                                pygame.mixer.music.pause()
                                music_paused = True
                            else:
                                pygame.mixer.music.unpause()
                                music_paused = False
                        elif event.key == controls["TRACK"]:
                            track_prey()
                        elif event.key == controls["SCENT"]:
                            scent_mark()
                        elif event.key == controls["BURY"]:
                            bury_prey()
                        elif event.key == pygame.K_g: # Drop prey
                            if carried_prey:
                                p = carried_prey.pop()
                                # Spawn it back into the world at current location
                                p.x, p.y = WIDTH // 2, HEIGHT // 2
                                p.state = Prey.IDLE
                                prey_list.append(p)
                        elif event.key == controls["INVENTORY"]:
                            inventory_open = not inventory_open

            elif game_state == "menu":
                handle_menu_input(event)
            elif game_state == "multiplayer":
                handle_multiplayer_input(event)
            elif game_state == "keybinds":
                handle_keybinds_input(event)
            else:
                handle_other_screen_input(event)

        # Game logic
        if game_state == "playing" and not chat_open and not inventory_open:
            keys = pygame.key.get_pressed()
            is_sprinting = keys[controls["SPRINT"]] and stamina > 0
            
            # Slower when carrying multiple prey
            weight_factor = 1.0 - (len(carried_prey) * 0.1)
            speed = (8 if is_sprinting else 4) * 60 * dt * weight_factor

            move_x, move_y = 0, 0
            if keys[controls["MOVE_LEFT"]]: move_x -= speed
            if keys[controls["MOVE_RIGHT"]]: move_x += speed
            if keys[controls["MOVE_UP"]]: move_y -= speed
            if keys[controls["MOVE_DOWN"]]: move_y += speed
            
            world_x += move_x
            world_y += move_y

            update_status_bars(dt)
            update_stamina(dt)
            update_chat_messages(dt)
            update_player_map_position()
            update_prey(dt)

            cat_rect = pygame.Rect(WIDTH // 2 - cat_img.get_width() // 2, HEIGHT // 2 - cat_img.get_height() // 2, cat_img.get_width(), cat_img.get_height())
            near_prey = any(pygame.Rect(prey.x - 25, prey.y - 25, 50, 50).colliderect(cat_rect.inflate(100, 100)) for prey in prey_list if prey.state != Prey.HIDING)
            
            if near_prey:
                if keys[controls["JUMP"]]:
                    pounce_charging = True
                    pounce_meter = min(max_pounce, pounce_meter + 4)
                    if pounce_meter >= max_pounce:
                        pounce_ready = True
                else:
                    if pounce_charging:
                        if pounce_ready:
                            check_prey_collision()
                        pounce_charging = False
                        pounce_ready = False
                        pounce_meter = 0
            else:
                pounce_charging = False
                pounce_ready = False
                pounce_meter = 0

        if network_client.connected:
            network_client.send({'type': 'position', 'x': world_x, 'y': world_y})

        # Rendering
        if game_state == "playing":
            draw_grass_background()
            draw_prey()
            for track in prey_tracks[:]:
                age = time.time() - track.get('time', 0)
                if age > 60:
                    prey_tracks.remove(track)
                    continue
                
                x, y = WIDTH // 2 + (track['x'] - world_x), HEIGHT // 2 + (track['y'] - world_y)
                # Fade based on age
                alpha = max(0, 255 * (1 - age / 60))
                
                if track.get('type') == 'scent': 
                    pygame.draw.circle(screen, scent_color, (int(x), int(y)), 10, 2)
                elif track.get('type') == 'trail':
                    # Draw a different mark for tracks
                    color = (255, 255, 100, alpha)
                    pygame.draw.rect(screen, color, (int(x)-5, int(y)-5, 10, 10), 1)
                else: 
                    screen.blit(paw_img, (int(x) - 12, int(y) - 12))
            for mound in buried_prey:
                age = time.time() - mound.get('time', 0)
                if age < 300:
                    x, y = WIDTH // 2 + (mound['x'] - world_x), HEIGHT // 2 + (mound['y'] - world_y)
                    pygame.draw.ellipse(screen, (139, 69, 19), (x - 10, y - 5, 20, 10))
            
            hint_text = tiny_font.render("E: Track | F: Scent | B: Bury | Q: Dash | I: Inventory | F12: Screenshot", True, (255, 200, 200))
            screen.blit(hint_text, (10, HEIGHT - 30))
            screen.blit(cat_img, (WIDTH // 2 - cat_img.get_width() // 2, HEIGHT // 2 - cat_img.get_height() // 2))
            
            # Draw carried prey
            for i, prey in enumerate(carried_prey):
                # Draw prey hanging from mouth/back
                offset_y = 10 + i * 5
                screen.blit(pygame.transform.scale(prey_img, (30, 30)), (WIDTH // 2 - 15, HEIGHT // 2 + offset_y))

            if player_message: draw_speech_bubble(player_message, WIDTH // 2, HEIGHT // 2 - 60)
            draw_status_bars(); draw_clock(); draw_chat(); draw_pounce_meter()
            if inventory_open: inventory.draw(screen)
            if not chat_open:
                hint_text = tiny_font.render("ESC: Menu | T: Chat | 1: Meow | Shift: Sprint | I: Inv | F11: Fullscreen", True, WHITE)
                screen.blit(hint_text, (WIDTH - hint_text.get_width() - 10, 10))
        elif game_state == "menu": draw_menu()
        elif game_state == "map": draw_map()
        elif game_state == "multiplayer": draw_multiplayer_menu()
        elif game_state == "credits": show_credits()
        elif game_state == "changelog": show_changelog()
        elif game_state == "keybinds": draw_keybinds()

        if network_client.connected:
            with network_client.lock:
                for pid, pdata in network_client.other_players.items():
                    if isinstance(pdata, dict):
                        # Only draw if they are on screen relative to us
                        ox, oy = WIDTH // 2 + (pdata.get('x', 0) - world_x), HEIGHT // 2 + (pdata.get('y', 0) - world_y)
                        if -100 < ox < WIDTH + 100 and -100 < oy < HEIGHT + 100:
                            screen.blit(cat_img, (ox - cat_img.get_width() // 2, oy - cat_img.get_height() // 2))
                            if network_client.other_typing.get(pid):
                                overlay_width, overlay_height = 120, 22
                                overlay_surf = pygame.Surface((overlay_width, overlay_height), pygame.SRCALPHA)
                                overlay_surf.fill((240, 255, 255, 180))
                                pygame.draw.rect(overlay_surf, (180, 220, 255, 180), overlay_surf.get_rect(), border_radius=8)
                                text = aero_font.render("is typing...", True, (30, 30, 30))
                                text = pygame.transform.smoothscale(text, (int(text.get_width() * 0.7), int(text.get_height() * 0.7)))
                                overlay_surf.blit(text, (overlay_width // 2 - text.get_width() // 2, overlay_height // 2 - text.get_height() // 2))
                                screen.blit(overlay_surf, (ox - overlay_width // 2, oy - cat_img.get_height() // 2 - 38))

        if saving_level_timer > 0: saving_level_timer -= dt
        
        # F3 Debug Overlay
        keys = pygame.key.get_pressed()
        if keys[pygame.K_F3]:
            debug_lines = [
                f"FPS: {current_fps:.1f}",
                f"Pos: {world_x:.1f}, {world_y:.1f}",
                f"Prey: {len(prey_list)} (Carrying: {len(carried_prey)})",
                f"Network: {'Connected' if network_client.connected else 'Offline'}",
                f"Window: {WIDTH}x{HEIGHT} ({'FS' if is_fullscreen else 'Win'})",
                f"Log: {log_file}",
                f"DT: {dt:.4f}"
            ]
            if network_client.connected:
                debug_lines.append(f"Players: {len(network_client.other_players) + 1}")
            
            for i, line in enumerate(debug_lines):
                debug_surf = tiny_font.render(line, True, YELLOW)
                screen.blit(debug_surf, (WIDTH - debug_surf.get_width() - 10, 50 + i * 18))

        pygame.display.flip()
except Exception as e:
    logging.critical(f"Uncaught exception in main loop: {e}", exc_info=True)
finally:
    pygame.quit()
    sys.exit()
