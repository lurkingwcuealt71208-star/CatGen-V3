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
import math

# Setup Logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "game.log")
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
    """Get path for save files in a platform-appropriate user data directory.

    - Windows: %LOCALAPPDATA%\CatGen or ~/AppData/Local/CatGen
    - macOS: ~/Library/Application Support/CatGen
    - Linux: ~/.local/share/CatGen
    """
    home = os.path.expanduser("~")
    try:
        if sys.platform == 'win32':
            app_data = os.path.join(home, "AppData", "Local", "CatGen")
        elif sys.platform == 'darwin':
            app_data = os.path.join(home, "Library", "Application Support", "CatGen")
        else:
            app_data = os.path.join(home, ".local", "share", "CatGen")
    except Exception:
        app_data = os.path.join(home, ".catgen")

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

# Configuration
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
def load_game_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading config: {e}")
    return {"use_12h_format": True}

def save_game_config(config_data):
    # Ensure current state is included
    config_data["username"] = username
    config_data["character_name"] = character_name
    config_data["character_bio"] = character_bio
    config_data["hunting_skill"] = hunting_skill
    config_data["combat_skill"] = combat_skill
    config_data["tracking_skill"] = tracking_skill
    config_data["hunting_xp"] = hunting_xp
    config_data["combat_xp"] = combat_xp
    config_data["tracking_xp"] = tracking_xp
    config_data["player_level"] = player_level
    config_data["use_12h_format"] = use_12h_format
    config_data["texture_pack"] = current_texture_pack
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving config: {e}")

game_config = load_game_config()
username = game_config.get("username", "Player")
character_name = game_config.get("character_name", username)
character_bio = game_config.get("character_bio", "")
hunting_skill = game_config.get("hunting_skill", 0)
combat_skill = game_config.get("combat_skill", 0)
tracking_skill = game_config.get("tracking_skill", 0)
hunting_xp = game_config.get("hunting_xp", 0)
combat_xp = game_config.get("combat_xp", 0)
tracking_xp = game_config.get("tracking_xp", 0)
player_level = game_config.get("player_level", 1)
use_12h_format = game_config.get("use_12h_format", True)

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
    "STREAMER": pygame.K_F9,
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
character_name = "Player"
character_bio = ""
menu_stack = []
# Overlay stack for modal UI layers (topmost closed by ESC)
overlay_stack = []  # items: 'inventory','char_info','upgrades','chat', etc.

def push_overlay(name):
    """Open a named overlay and push it to the overlay stack."""
    global overlay_stack, inventory_open, char_info_open, upgrades_menu_open, chat_open
    overlay_stack.append(name)
    if name == 'inventory':
        inventory_open = True
        # If the player is carrying prey, start with it attached to cursor
        try:
            if carried_prey:
                prey_obj = carried_prey.pop()
                # Create an Item wrapper for the prey for dragging
                it = Item("Prey", (200, 150, 100), "A fresh catch.", 1)
                it.is_prey = True
                it.prey_hunger = getattr(prey_obj, 'hunger', 20)
                it.prey_ref = prey_obj
                inventory.dragged_item = it
                inventory.dragged_item_index = -1
                inventory.dragged_item_is_prey = True
                inventory.dragged_prey_ref = prey_obj
        except Exception:
            pass
    elif name == 'char_info':
        char_info_open = True
    elif name == 'upgrades':
        upgrades_menu_open = True
    elif name == 'chat':
        chat_open = True

def pop_top_overlay():
    """Close the topmost overlay if any and return its name."""
    global overlay_stack, inventory_open, char_info_open, upgrades_menu_open, chat_open
    if not overlay_stack:
        return None
    name = overlay_stack.pop()
    if name == 'inventory':
        # If an inventory drag of a carried prey is active, return it to carried_prey
        try:
            if inventory.dragged_item_is_prey and inventory.dragged_prey_ref is not None:
                carried_prey.append(inventory.dragged_prey_ref)
        except Exception:
            pass
        inventory_open = False
    elif name == 'char_info':
        char_info_open = False
    elif name == 'upgrades':
        upgrades_menu_open = False
    elif name == 'chat':
        chat_open = False
    return name

def close_overlay(name):
    """Close a specific overlay by name if present in the stack."""
    global overlay_stack
    if not overlay_stack:
        return False
    # If the named overlay is the top one, pop it
    if overlay_stack and overlay_stack[-1] == name:
        pop_top_overlay()
        return True
    # Otherwise remove any occurrence and ensure its boolean is cleared
    if name in overlay_stack:
        overlay_stack[:] = [n for n in overlay_stack if n != name]
        if name == 'inventory':
            globals()['inventory_open'] = False
        elif name == 'char_info':
            globals()['char_info_open'] = False
        elif name == 'upgrades':
            globals()['upgrades_menu_open'] = False
        elif name == 'chat':
            globals()['chat_open'] = False
        return True
    return False
streamer_mode = False
dash_charge = 0
max_dash_charge = 1.5 # seconds
is_charging_dash = False
hunting_skill = 0
combat_skill = 0
tracking_skill = 0
hunting_xp = 0
combat_xp = 0
tracking_xp = 0
player_level = 1
player_z = 0
player_vel_z = 0
is_jumping = False
camera_offset_x, camera_offset_y = 0, 0
is_panning = False
last_pan_pos = (0, 0)
char_info_open = False
upgrades_menu_open = False
char_name_input = ""
char_bio_input = ""
char_info_focus = "name" # "name", "bio"
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
# LAN broadcast state for in-game hosting
lan_broadcast_thread = None
lan_broadcast_running = False
LAN_BROADCAST_PORT = 25566
hosted_server = None
# UI layout constants
UI_MARGIN = 10

# Minimal upgrades data (do not replace existing upgrade UI architecture)
UPGRADES = [
    {'id': 'hunting_1', 'name': 'Improved Scenting', 'required_level': 2, 'locked': True},
    {'id': 'stamina_1', 'name': 'Stamina Boost', 'required_level': 3, 'locked': True}
]

def attempt_unlock(upgrade_id):
    """Attempt to unlock an upgrade. Returns (success, message)."""
    for up in UPGRADES:
        if up['id'] == upgrade_id:
            if player_level < up.get('required_level', 0):
                return False, f"Requires level {up['required_level']}"
            if not up.get('locked', True):
                return False, "Already unlocked"
            up['locked'] = False
            return True, "Unlocked"
    return False, "Unknown upgrade"

# Default status bar container (manually adjustable)
status_bar_container = None
try:
    status_bar_container = StatusBarContainer(
        x=10,
        y=10,
        width=150,
        height=15,
        padding=8,
        orientation='horizontal',
        bars=[
            {'name': 'Hunger', 'var': 'hunger', 'color': RED},
            {'name': 'Thirst', 'var': 'thirst', 'color': LIGHT_BLUE},
            {'name': 'Bathroom', 'var': 'bathroom', 'color': YELLOW},
            {'name': 'Sleep', 'var': 'sleep', 'color': PURPLE},
            {'name': 'Stamina', 'var': 'stamina', 'color': GREEN}
        ]
    )
except Exception:
    status_bar_container = None

# Multiplayer Menu States
MP_STATE_LIST = "list"
MP_STATE_DIRECT = "direct"
MP_STATE_ADD = "add"
MP_STATE_EDIT = "edit"
mp_menu_state = MP_STATE_LIST

# Server List
server_list_file = get_save_path("servers.json")
def load_servers():
    if os.path.exists(server_list_file):
        try:
            with open(server_list_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[MP ERROR] Failed to load servers list: {e}")
            return []
    return []

def save_servers(servers):
    try:
        with open(server_list_file, 'w') as f:
            json.dump(servers, f, indent=4)
    except Exception as e:
        print(f"[MP ERROR] Failed to save servers list: {e}")

saved_servers = load_servers()
selected_server_index = -1
server_scroll_offset = 0

# Input fields for screens
edit_server_name = ""
edit_server_ip = ""
edit_server_port = "25565"
edit_server_pass = ""
direct_ip = ""
direct_port = "25565"
direct_pass = ""
input_focus = "name" # "name", "ip", "port", "pass"

# Network Client Class
class NetworkClient:
    def __init__(self):
        self.socket = None
        self.connected = False
        self.client_id = None
        self.thread = None
        self.heartbeat_thread = None
        self.heartbeat_running = False
        self.message_queue = queue.Queue()
        self.username = "Player"
        self.other_players = {}  # {player_id: dict}
        self.other_typing = {}   # {player_id: bool}
        self.chat_messages = []
        self.lock = threading.Lock()
        self.send_lock = threading.Lock()
        self._recv_buffer = ""

    # ------------------------------------------------------------------
    # Low-level I/O helpers
    # ------------------------------------------------------------------

    def _raw_send(self, conn, message):
        """Serialize and send one JSON line. Caller holds send_lock."""
        print("[CLIENT SEND]", message)
        conn.sendall((json.dumps(message) + '\n').encode('utf-8'))

    def _read_next_line(self, timeout=None):
        """Block until a complete JSON line is available from the socket."""
        old_timeout = self.socket.gettimeout()
        self.socket.settimeout(timeout)
        try:
            while True:
                if '\n' in self._recv_buffer:
                    line, self._recv_buffer = self._recv_buffer.split('\n', 1)
                    if line.strip():
                        print("[CLIENT RECEIVE]", line)
                        return json.loads(line)
                data = self.socket.recv(4096)
                if not data:
                    raise ConnectionError("Server closed the connection")
                self._recv_buffer += data.decode('utf-8')
        finally:
            self.socket.settimeout(old_timeout)

    # ------------------------------------------------------------------
    # Player state helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_player_id(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _hydrate_players(self, players_list):
        """Overwrite other_players from an accept/welcome payload."""
        hydrated = {}
        if isinstance(players_list, dict):
            items = players_list.values()
        else:
            items = players_list or []
        for payload in items:
            pid = self._to_player_id(payload.get('id'))
            if pid is None or pid == self.client_id:
                continue
            hydrated[pid] = {
                'username': payload.get('username', 'Player'),
                'x': float(payload.get('x', 0.0)),
                'y': float(payload.get('y', 0.0)),
                'z': float(payload.get('z', 0.0)),
                'state': payload.get('state', 'idle'),
                'bio': payload.get('bio', ''),
            }
        self.other_players = hydrated

    def _upsert_player(self, payload):
        """Insert or update a remote player entry."""
        pid = self._to_player_id(payload.get('id'))
        if pid is None or pid == self.client_id:
            return
        is_new = pid not in self.other_players
        entry = self.other_players.setdefault(pid, {
            'username': 'Player', 'x': 0.0, 'y': 0.0, 'z': 0.0,
            'tx': 0.0, 'ty': 0.0, 'tz': 0.0,
            'state': 'idle', 'bio': ''
        })
        if 'username' in payload:
            entry['username'] = payload['username']
        for key in ('x', 'y', 'z'):
            if key in payload:
                try:
                    val = float(payload[key])
                    entry['t' + key] = val  # interpolation target
                    if is_new:
                        entry[key] = val    # snap new players immediately
                except (TypeError, ValueError):
                    pass
        if 'state' in payload:
            entry['state'] = payload['state']
        if 'bio' in payload:
            entry['bio'] = payload['bio']

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self, ip, port, username, password=""):
        self.disconnect()
        self.username = username
        try:
            print(f"[MP] Client attempting connection: {ip}:{port}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((ip, int(port)))
            self.socket = sock
            self._recv_buffer = ""

            # Handshake: send connect, expect accept
            handshake = {'type': 'connect', 'username': username, 'password': password}
            with self.send_lock:
                self._raw_send(sock, handshake)

            response = self._read_next_line(timeout=5)
            if response.get('type') == 'error':
                raise ConnectionError(response.get('message', 'Rejected by server'))
            if response.get('type') != 'accept':
                raise ConnectionError(f"Unexpected handshake response: {response.get('type')}")  

            self.client_id = self._to_player_id(response.get('id'))
            if self.client_id is None:
                raise ConnectionError('Server did not provide a client id')

            with self.lock:
                self._hydrate_players(response.get('players', []))

            self.connected = True
            self.socket.settimeout(0.5)
            print(f"[MP] Connected as player id={self.client_id}")

            self.thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.thread.start()
            self.heartbeat_running = True
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()
            return True, "Connected"
        except Exception as e:
            print(f"[MP ERROR] Connection failed: {e}")
            self.disconnect()
            return False, str(e)

    def disconnect(self):
        self.connected = False
        self.heartbeat_running = False
        self.client_id = None
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        self._recv_buffer = ""
        with self.lock:
            self.other_players = {}
            self.other_typing = {}

    def send(self, message):
        """Send a message to the server. Normalizes legacy packet types."""
        if not self.connected or not self.socket:
            return
        try:
            normalized = self._normalize_outgoing(message)
            with self.send_lock:
                self._raw_send(self.socket, normalized)
        except Exception as e:
            print(f"[MP ERROR] Send error: {e}")
            self.disconnect()

    def _normalize_outgoing(self, message):
        """Translate legacy packet shapes into the canonical format."""
        msg = dict(message)
        msg_type = msg.get('type')

        # Legacy 'join' → 'connect'
        if msg_type == 'join':
            msg['type'] = 'connect'

        # Legacy 'position' → 'player_update'
        elif msg_type == 'position':
            msg = {
                'type': 'player_update',
                'id': self.client_id,
                'x': float(msg.get('x', 0.0)),
                'y': float(msg.get('y', 0.0)),
                'z': float(msg.get('z', 0.0)),
                'state': msg.get('state', 'idle'),
                'username': msg.get('username', self.username),
                'bio': msg.get('bio', ''),
            }

        # Ensure id is always set for player_update
        elif msg_type == 'player_update':
            msg['id'] = self.client_id
            msg['x'] = float(msg.get('x', 0.0))
            msg['y'] = float(msg.get('y', 0.0))
            msg['z'] = float(msg.get('z', 0.0))
            msg.setdefault('state', 'idle')
            msg.setdefault('username', self.username)
            msg.setdefault('bio', '')

        # Tag other client→server packets with id
        if self.client_id is not None and msg_type in {
                'chat', 'typing_start', 'typing_stop', 'ping', 'username_change'}:
            msg.setdefault('id', self.client_id)

        return msg

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _heartbeat_loop(self):
        while self.heartbeat_running and self.connected:
            try:
                self.send({'type': 'ping'})
            except Exception:
                pass
            time.sleep(10)

    def _receive_loop(self):
        while self.connected and self.socket:
            try:
                message = self._read_next_line(timeout=0.5)
                with self.lock:
                    self._handle_message(message)
            except socket.timeout:
                continue
            except (TimeoutError, OSError):
                continue
            except json.JSONDecodeError as e:
                print(f"[MP ERROR] JSON decode error: {e}")
            except ConnectionError as e:
                if self.connected:
                    print(f"[MP ERROR] Receive error: {e}")
                break
            except Exception as e:
                if self.connected:
                    print(f"[MP ERROR] Receive error: {e}")
                break
        self.disconnect()

    def _handle_message(self, message):
        """Dispatch an inbound server message. Called with self.lock held."""
        msg_type = message.get('type')

        if msg_type == 'error':
            self.chat_messages.append(f"Error: {message.get('message')}")

        elif msg_type in ('accept', 'welcome'):
            # accept arrives during handshake; welcome is legacy – both carry player list
            self._hydrate_players(message.get('players', []) or message.get('players', {}))

        elif msg_type == 'player_joined':
            self._upsert_player(message)
            self.chat_messages.append(f"{message.get('username', 'Player')} joined")

        elif msg_type == 'player_left':
            pid = self._to_player_id(message.get('id'))
            uname = message.get('username', 'Player')
            if pid is not None:
                self.other_players.pop(pid, None)
                self.other_typing.pop(pid, None)
            self.chat_messages.append(f"{uname} left")

        elif msg_type in ('player_update', 'player_position'):
            self._upsert_player(message)

        elif msg_type == 'chat':
            self.chat_messages.append(f"{message.get('username', '?')}: {message.get('message', '')}")

        elif msg_type == 'typing_start':
            pid = self._to_player_id(message.get('id'))
            if pid is not None:
                self.other_typing[pid] = True

        elif msg_type == 'typing_stop':
            pid = self._to_player_id(message.get('id'))
            if pid is not None:
                self.other_typing.pop(pid, None)

        elif msg_type == 'username_change':
            pid = self._to_player_id(message.get('id'))
            if pid in self.other_players:
                self.other_players[pid]['username'] = message.get('new_username', self.other_players[pid]['username'])

        elif msg_type == 'pong':
            pass  # heartbeat acknowledged

        else:
            print(f"[MP ERROR] Unknown packet type from server: {message}")

network_client = NetworkClient()

# LAN scan state
lan_scan_results = []  # list of dicts {ip, port}
lan_scanning = False
lan_scan_thread = None
lan_spinner_angle = 0.0

def get_local_ip_prefix():
    """Return local IPv4 prefix like '192.168.1.' or None if unknown."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # connect to public DNS to determine local IP without sending data
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        parts = local_ip.split('.')
        if len(parts) == 4:
            return '.'.join(parts[:3]) + '.'
    except Exception:
        pass
    return None

def _scan_host(ip, port, timeout=0.6):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        res = sock.connect_ex((ip, port))
        sock.close()
        return res == 0
    except Exception:
        return False

def scan_lan_servers(port=25565, timeout=0.6, max_workers=50):
    """Scan local /24 subnet for open TCP servers on `port`.
    Returns a list of (ip, port) tuples. Runs in background if called via thread.
    """
    global lan_scan_results, lan_scanning
    lan_scan_results = []
    lan_scanning = True

    print(f"[MP] Starting LAN scan on port: {port}")

    # First, try to listen for UDP broadcast announcements for a short period
    results = []
    udp_results = []
    try:
        usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        usock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            usock.bind(('', LAN_BROADCAST_PORT))
        except Exception:
            usock.close()
            usock = None
        if usock:
            usock.settimeout(0.5)
            start = time.time()
            while time.time() - start < 2.0:
                try:
                    data, addr = usock.recvfrom(1024)
                    if not data: continue
                    try:
                        msg = json.loads(data.decode('utf-8'))
                        if msg.get('type') == 'lan_announce':
                            udp_results.append({'ip': addr[0], 'port': msg.get('port', port), 'name': msg.get('name', '')})
                    except Exception:
                        pass
                except socket.timeout:
                    pass
            try: usock.close()
            except: pass

    except Exception:
        pass

    # Continue with TCP / active scan if UDP didn't find any
    prefix = get_local_ip_prefix()
    if not prefix:
        # If we found udp_results, return them
        lan_scanning = False
        lan_scan_results = udp_results
        return udp_results

    ips = [f"{prefix}{i}" for i in range(1, 255)]

    from concurrent.futures import ThreadPoolExecutor, as_completed
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as exe:
            futures = {exe.submit(_scan_host, ip, port, timeout): ip for ip in ips}
            for fut in as_completed(futures):
                ip = futures[fut]
                try:
                    ok = fut.result()
                    if ok:
                        results.append({'ip': ip, 'port': port})
                except Exception:
                    pass
    finally:
        # Merge UDP-discovered servers first, then TCP scan results (avoid duplicates)
        merged = {f"{r['ip']}:{r['port']}": r for r in (udp_results + results)}
        lan_scan_results = list(merged.values())
        lan_scanning = False
    try:
        print(f"[MP] LAN scan complete: found {len(lan_scan_results)} servers")
    except Exception:
        pass
    return lan_scan_results


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
current_texture_pack = game_config.get("texture_pack", "Default")

def load_img(name, size=None):
    # Try texture pack first
    if current_texture_pack != "Default":
        pack_path = os.path.join("texturepacks", current_texture_pack, name)
        if os.path.exists(pack_path):
            try:
                img = pygame.image.load(pack_path).convert_alpha()
                if size: img = pygame.transform.scale(img, size)
                return img
            except Exception as e:
                logging.debug(f"Failed loading from texture pack {pack_path}: {e}")

    # Fallback to assets
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

# Texture pack discovery
TEXTUREPACK_DIR = resource_path("texturepacks")
if not os.path.exists(TEXTUREPACK_DIR):
    try:
        os.makedirs(TEXTUREPACK_DIR, exist_ok=True)
    except Exception:
        pass

def list_texture_packs():
    packs = ["Default"]
    try:
        for name in os.listdir(TEXTUREPACK_DIR):
            full = os.path.join(TEXTUREPACK_DIR, name)
            if os.path.isdir(full):
                packs.append(name)
    except Exception:
        pass
    return packs

# Validate selected texture pack
available_packs = list_texture_packs()
if current_texture_pack not in available_packs:
    current_texture_pack = "Default"
    game_config['texture_pack'] = "Default"
    save_game_config(game_config)

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
    except Exception:
        return pygame.font.SysFont("Arial", size)

font = get_font("Arial", 28)
small_font = get_font("Arial", 20)
tiny_font = get_font("Arial", 16)
clock_font = get_font("Arial", 24)
aero_font = get_font("Segoe UI", 20)

# Game state
game_state = "playing"
menu_stack = []

def set_game_state(new_state):
    """Set game state and update menu stack"""
    global game_state, menu_stack
    if new_state == "playing":
        menu_stack = []
    elif game_state != new_state:
        if game_state != "playing":
            if not menu_stack or menu_stack[-1] != game_state:
                menu_stack.append(game_state)
    game_state = new_state

def go_back():
    """Go back to previous menu or playing"""
    global game_state, menu_stack
    if menu_stack:
        game_state = menu_stack.pop()
    else:
        game_state = "playing"

if "username" not in game_config:
    game_state = "setup"
cat_x = WIDTH // 2
cat_y = HEIGHT // 2
world_x = 0  # Camera position
world_y = 0

# Status bars (0-100)
hunger = 100
thirst = 100
bathroom = 100
sleep = 100
dash_cooldown = 0
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

def connect_to_server(ip, port, username, password=""):
    """Connect to a real multiplayer server"""
    return network_client.connect(ip, port, username, password)

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

        # Keep within boundaries
        # Boundaries should be large enough for the world
        world_size_w, world_size_h = 5000, 5000
        if self.x < -world_size_w // 2 or self.x > world_size_w // 2:
            self.vx *= -1
            self.x = max(-world_size_w // 2, min(world_size_w // 2, self.x))
        if self.y < -world_size_h // 2 or self.y > world_size_h // 2:
            self.vy *= -1
            self.y = max(-world_size_h // 2, min(world_size_h // 2, self.y))
        
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
    def __init__(self, name, icon_color, description="", count=1):
        self.name = name
        self.icon_color = icon_color
        self.description = description
        self.count = int(count)
        self.is_prey = False
        self.prey_hunger = 0
        self.prey_ref = None

class Inventory:
    def __init__(self, slots=32):
        self.slots = slots
        self.items = [None] * slots  # Grid of 32 slots (8x4)
        self.selected_tab = "Inventory" # "Inventory", "Skills"
        self.dragged_item = None
        self.dragged_item_index = -1
        self.dragged_item_is_prey = False
        self.dragged_prey_ref = None
        self.drag_pos = None
        self.context_menu = None  # {'slot':i, 'pos':(x,y), 'options':[...]} 

    def add_item(self, item):
        # Try to merge with existing stack first
        for i in range(self.slots):
            s = self.items[i]
            if s and s.name == item.name:
                s.count += getattr(item, 'count', 1)
                return True
        # Place in first empty slot
        for i in range(self.slots):
            if self.items[i] is None:
                self.items[i] = item
                return True
        return False

    def handle_input(self, event):
        global upgrades_menu_open
        # If context menu open, handle its clicks first
        if event.type == pygame.MOUSEBUTTONDOWN and self.context_menu:
            cmx, cmy = self.context_menu['pos']
            opts = self.context_menu['options']
            w = 120
            h = 28
            mx, my = event.pos
            for idx, opt in enumerate(opts):
                rx = cmx
                ry = cmy + idx * (h + 4)
                if pygame.Rect(rx, ry, w, h).collidepoint(mx, my):
                    slot = self.context_menu['slot']
                    item = self.items[slot]
                    if not item:
                        self.context_menu = None
                        return
                    # Eat
                    if opt == 'Eat':
                        global hunger
                        hunger = min(100, hunger + getattr(item, 'prey_hunger', 20))
                        # If this item references a prey object, remove or mark it consumed
                        try:
                            if getattr(item, 'prey_ref', None) is not None:
                                # If the prey exists in world list, ensure it's removed
                                pr = item.prey_ref
                                try:
                                    if pr in prey_list:
                                        prey_list.remove(pr)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        self.items[slot] = None
                        self.context_menu = None
                        return
                    # Drop
                    if opt == 'Drop':
                        # Spawn prey at player position
                        cat_world_x = world_x + WIDTH // 2
                        cat_world_y = world_y + HEIGHT // 2
                        # If the stored item refers to an existing prey object, reuse it
                        if getattr(item, 'prey_ref', None) is not None:
                            pr = item.prey_ref
                            try:
                                pr.x = cat_world_x
                                pr.y = cat_world_y
                                pr.alpha = 0
                                pr.state = Prey.IDLE
                                prey_list.append(pr)
                            except Exception:
                                # fallback to new prey
                                new_prey = Prey(cat_world_x, cat_world_y)
                                new_prey.alpha = 0
                                prey_list.append(new_prey)
                        else:
                            new_prey = Prey(cat_world_x, cat_world_y)
                            new_prey.alpha = 0
                            prey_list.append(new_prey)
                        self.items[slot] = None
                        self.context_menu = None
                        return
                    # Bury
                    if opt == 'Bury':
                        ok = bury_prey()
                        if ok:
                            self.items[slot] = None
                        self.context_menu = None
                        return
            # Click outside options closes menu
            self.context_menu = None
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            inv_w, inv_h = 600, 450
            ix, iy = WIDTH // 2 - inv_w // 2, HEIGHT // 2 - inv_h // 2
            
            # Tab switching
            tabs = ["Inventory", "Skills"]
            for i, tab in enumerate(tabs):
                tx = ix + i * 120
                ty = iy - 30
                tw, th = 110, 30
                if pygame.Rect(tx, ty, tw, th).collidepoint(mx, my):
                    self.selected_tab = tab
                    return

            if self.selected_tab == "Inventory":
                slot_size = 60
                gap = 10
                cols = 8
                start_x = ix + (inv_w - (cols * (slot_size + gap) - gap)) // 2
                start_y = iy + 70

                for i in range(self.slots):
                    row = i // cols
                    col = i % cols
                    sx = start_x + col * (slot_size + gap)
                    sy = start_y + row * (slot_size + gap)
                    if pygame.Rect(sx, sy, slot_size, slot_size).collidepoint(mx, my):
                        if event.button == 1: # Left Click -> pick up or begin drag
                            if self.items[i]:
                                self.dragged_item = self.items[i]
                                self.dragged_item_index = i
                                self.dragged_item_is_prey = getattr(self.items[i], 'is_prey', False)
                                self.dragged_prey_ref = getattr(self.items[i], 'prey_ref', None)
                        elif event.button == 3: # Right Click -> context menu for prey or split stacks
                            if self.items[i] and getattr(self.items[i], 'is_prey', False):
                                # Open context menu for prey; show Bury only when allowed by cooldown
                                opts = ['Eat', 'Drop']
                                try:
                                    if time.time() - last_hunt_time <= 30:
                                        opts.append('Bury')
                                except Exception:
                                    pass
                                self.context_menu = {'slot': i, 'pos': (mx, my), 'options': opts}
                                return
                            if self.items[i] and getattr(self.items[i], 'count', 1) > 1:
                                orig = self.items[i]
                                split_count = orig.count // 2
                                orig.count -= split_count
                                new_item = Item(orig.name, orig.icon_color, orig.description, split_count)
                                # Place split into first empty slot
                                placed = False
                                for j in range(self.slots):
                                    if self.items[j] is None:
                                        self.items[j] = new_item
                                        placed = True
                                        break
                                if not placed:
                                    orig.count += split_count
                        return
            
            elif self.selected_tab == "Skills":
                # Upgrades button
                btn_w, btn_h = 200, 40
                btn_x = ix + inv_w // 2 - btn_w // 2
                btn_y = iy + inv_h - 70
                if pygame.Rect(btn_x, btn_y, btn_w, btn_h).collidepoint(mx, my):
                    push_overlay('upgrades')
                    return

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.dragged_item:
                mx, my = event.pos
                inv_w, inv_h = 600, 450
                ix, iy = WIDTH // 2 - inv_w // 2, HEIGHT // 2 - inv_h // 2
                
                slot_size = 60
                gap = 10
                cols = 8
                start_x = ix + (inv_w - (cols * (slot_size + gap) - gap)) // 2
                start_y = iy + 70

                placed = False
                placed_index = None
                for i in range(self.slots):
                    row = i // cols
                    col = i % cols
                    sx = start_x + col * (slot_size + gap)
                    sy = start_y + row * (slot_size + gap)
                    if pygame.Rect(sx, sy, slot_size, slot_size).collidepoint(mx, my):
                        target = self.items[i]
                        # Place into empty slot
                        if target is None:
                            self.items[i] = self.dragged_item
                            if self.dragged_item_index >= 0:
                                self.items[self.dragged_item_index] = None
                            placed = True
                            placed_index = i
                            break

                        # Merge stacks if same item
                        if getattr(target, 'name', None) == getattr(self.dragged_item, 'name', None):
                            target.count += getattr(self.dragged_item, 'count', 1)
                            if self.dragged_item_index >= 0:
                                self.items[self.dragged_item_index] = None
                            placed = True
                            placed_index = i
                            break

                        # Swap only if dragged from an inventory slot
                        if self.dragged_item_index >= 0:
                            self.items[self.dragged_item_index], self.items[i] = self.items[i], self.items[self.dragged_item_index]
                            placed = True
                            placed_index = i
                            break

                        # Dragged from carried prey and target occupied -> cannot swap; leave unplaced
                        placed = False
                        break

                # If not placed, return to original slot or back to carried list
                if not placed:
                    if self.dragged_item_index >= 0:
                        # original slot still holds it (no changes needed)
                        pass
                    else:
                        if self.dragged_item_is_prey and self.dragged_prey_ref is not None:
                            carried_prey.append(self.dragged_prey_ref)
                else:
                    # If placed and was prey from carried, set stored.prey_ref to the prey object
                    if self.dragged_item_is_prey and self.dragged_prey_ref is not None and placed_index is not None:
                        stored = self.items[placed_index]
                        if stored:
                            stored.is_prey = True
                            stored.prey_hunger = getattr(self.dragged_item, 'prey_hunger', 20)
                            stored.prey_ref = self.dragged_prey_ref

                self.dragged_item = None
                self.dragged_item_index = -1
                self.dragged_item_is_prey = False
                self.dragged_prey_ref = None
                self.drag_pos = None
                self.context_menu = None

    def draw(self, surface):
        """Draw inventory UI (Grid-based 32 slots)"""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        inv_w, inv_h = 600, 450
        ix, iy = WIDTH // 2 - inv_w // 2, HEIGHT // 2 - inv_h // 2
        
        # Black to Cyan panel
        draw_gradient_rect(surface, (10, 10, 10), DARK_CYAN, (ix, iy, inv_w, inv_h))
        pygame.draw.rect(surface, CYAN, (ix, iy, inv_w, inv_h), 2)

        # Tabs
        tabs = ["Inventory", "Skills"]
        for i, tab in enumerate(tabs):
            tx = ix + i * 120
            ty = iy - 30
            tw, th = 110, 30
            color = (30, 30, 30) if self.selected_tab != tab else DARK_CYAN
            pygame.draw.rect(surface, color, (tx, ty, tw, th))
            pygame.draw.rect(surface, CYAN, (tx, ty, tw, th), 1)
            txt = small_font.render(tab, True, WHITE)
            surface.blit(txt, (tx + tw // 2 - txt.get_width() // 2, ty + 5))

        if self.selected_tab == "Inventory":
            # Grid layout (8x4 = 32 slots)
            slot_size = 60
            gap = 10
            cols = 8
            
            # Title
            title = font.render("Inventory", True, CYAN)
            surface.blit(title, (ix + 20, iy + 20))

            start_x = ix + (inv_w - (cols * (slot_size + gap) - gap)) // 2
            start_y = iy + 70

            for i in range(self.slots):
                row = i // cols
                col = i % cols
                sx = start_x + col * (slot_size + gap)
                sy = start_y + row * (slot_size + gap)
                
                pygame.draw.rect(surface, (20, 20, 20), (sx, sy, slot_size, slot_size))
                pygame.draw.rect(surface, CYAN, (sx, sy, slot_size, slot_size), 1)
                
                # Highlight if dragged item is from this slot (show it as empty while dragging)
                if self.dragged_item_index == i:
                    continue

                if self.items[i]:
                    icon_color = getattr(self.items[i], 'icon_color', RED)
                    pygame.draw.rect(surface, icon_color, (sx + 5, sy + 5, slot_size - 10, slot_size - 10))
                    # Draw count if stacked
                    count = getattr(self.items[i], 'count', 1)
                    if count > 1:
                        cnt_txt = tiny_font.render(str(count), True, WHITE)
                        surface.blit(cnt_txt, (sx + slot_size - cnt_txt.get_width() - 6, sy + slot_size - cnt_txt.get_height() - 4))

                # Draw dragged item at interpolated mouse position for smooth follow
            if self.dragged_item:
                mx, my = pygame.mouse.get_pos()
                if self.drag_pos is None:
                    self.drag_pos = (mx, my)
                else:
                    # lerp position
                    self.drag_pos = (self.drag_pos[0] + (mx - self.drag_pos[0]) * 0.35,
                                     self.drag_pos[1] + (my - self.drag_pos[1]) * 0.35)
                dx, dy = int(self.drag_pos[0]), int(self.drag_pos[1])
                # If this dragged item represents a prey, render the prey image (preserve assets)
                if getattr(self.dragged_item, 'is_prey', False) and (self.dragged_prey_ref is not None or getattr(self.dragged_item, 'prey_ref', None) is not None):
                    try:
                        img = prey_img
                        scaled = pygame.transform.scale(img, (50, 50))
                        surface.blit(scaled, (dx - 25, dy - 25))
                        pygame.draw.rect(surface, WHITE, (dx - 25, dy - 25, 50, 50), 2)
                    except Exception:
                        icon_color = getattr(self.dragged_item, 'icon_color', RED)
                        pygame.draw.rect(surface, icon_color, (dx - 25, dy - 25, 50, 50))
                        pygame.draw.rect(surface, WHITE, (dx - 25, dy - 25, 50, 50), 2)
                else:
                    icon_color = getattr(self.dragged_item, 'icon_color', RED)
                    pygame.draw.rect(surface, icon_color, (dx - 25, dy - 25, 50, 50))
                    pygame.draw.rect(surface, WHITE, (dx - 25, dy - 25, 50, 50), 2)

            # Draw context menu if open
            if self.context_menu:
                cmx, cmy = self.context_menu['pos']
                opts = self.context_menu['options']
                w = 120
                h = 28
                for idx, opt in enumerate(opts):
                    rx = cmx
                    ry = cmy + idx * (h + 4)
                    pygame.draw.rect(surface, (30, 30, 30), (rx, ry, w, h))
                    pygame.draw.rect(surface, CYAN, (rx, ry, w, h), 1)
                    txt = small_font.render(opt, True, WHITE)
                    surface.blit(txt, (rx + 8, ry + 6))

        
        elif self.selected_tab == "Skills":
            # Skills display
            title = font.render("Skills", True, CYAN)
            surface.blit(title, (ix + 20, iy + 20))
            
            skills = [
                ("Hunting", hunting_skill),
                ("Combat", combat_skill),
                ("Tracking", tracking_skill)
            ]
            
            for i, (name, progress) in enumerate(skills):
                sy = iy + 80 + i * 70
                lbl = font.render(name, True, WHITE)
                surface.blit(lbl, (ix + 40, sy))
                
                # Progress bar
                bar_w, bar_h = 300, 30
                bx, by = ix + inv_w - 350, sy + 5
                pygame.draw.rect(surface, (20, 20, 20), (bx, by, bar_w, bar_h))
                # Ensure progress is 0-100
                fill_w = int(bar_w * (max(0, min(100, progress)) / 100))
                pygame.draw.rect(surface, CYAN, (bx, by, fill_w, bar_h))
                pygame.draw.rect(surface, WHITE, (bx, by, bar_w, bar_h), 2)
                
                perc = small_font.render(f"{int(progress)}%", True, WHITE)
                surface.blit(perc, (bx + bar_w // 2 - perc.get_width() // 2, by + 5))

            # Upgrades button
            btn_w, btn_h = 200, 40
            btn_x = ix + inv_w // 2 - btn_w // 2
            btn_y = iy + inv_h - 70
            pygame.draw.rect(surface, DARK_CYAN, (btn_x, btn_y, btn_w, btn_h))
            pygame.draw.rect(surface, CYAN, (btn_x, btn_y, btn_w, btn_h), 2)
            btn_txt = small_font.render("Upgrades", True, WHITE)
            surface.blit(btn_txt, (btn_x + btn_w // 2 - btn_txt.get_width() // 2, btn_y + 10))

        # Morph Selection Panel (Right side)
        mx, my = ix + inv_w + 10, iy
        mw, mh = 150, inv_h
        draw_gradient_rect(surface, (10, 10, 10), DARK_CYAN, (mx, my, mw, mh))
        pygame.draw.rect(surface, CYAN, (mx, my, mw, mh), 2)
        
        m_title = small_font.render("Morphs", True, CYAN)
        surface.blit(m_title, (mx + mw // 2 - m_title.get_width() // 2, my + 10))
        
        for i in range(5):
            box_h = 60
            box_rect = pygame.Rect(mx + 10, my + 40 + i * (box_h + 10), mw - 20, box_h)
            pygame.draw.rect(surface, (50, 50, 50), box_rect)
            pygame.draw.rect(surface, CYAN, box_rect, 1)
            m_txt = tiny_font.render(f"Morph {i+1}", True, WHITE)
            surface.blit(m_txt, (box_rect.x + 5, box_rect.y + 5))

        instr = small_font.render("Press I to Close", True, WHITE)
        surface.blit(instr, (ix + inv_w - instr.get_width() - 10, iy + inv_h - 30))

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
    # Spawn prey at a random location within a larger world area
    # px and py should be world coordinates. 
    # world_x, world_y are the top-left of the current screen view.
    px = world_x + random.randint(-WIDTH, WIDTH * 2)
    py = world_y + random.randint(-HEIGHT, HEIGHT * 2)
    prey_list.append(Prey(px, py))

def is_point_over_ui(px, py):
    """Return True if the given screen point is over any UI element or overlay.

    This is used to prevent starting camera pans when the user clicks on UI.
    """
    # Any open overlay blocks panning
    if overlay_stack:
        return True

    # Bottom HUD area
    hud_h = 60 + UI_MARGIN
    hud_y = HEIGHT - hud_h - UI_MARGIN
    if py >= hud_y:
        return True

    # Inventory overlay region
    if inventory_open:
        inv_w, inv_h = 600, 450
        ix, iy = WIDTH // 2 - inv_w // 2, HEIGHT // 2 - inv_h // 2
        if ix <= px <= ix + inv_w and iy <= py <= iy + inv_h:
            return True

    # Character info overlay
    if char_info_open:
        mw, mh = 600, 450
        mx, my = WIDTH // 2 - mw // 2, HEIGHT // 2 - mh // 2
        if mx <= px <= mx + mw and my <= py <= my + mh:
            return True

    # Upgrades overlay
    if upgrades_menu_open:
        mw, mh = 500, 400
        mx, my = WIDTH // 2 - mw // 2, HEIGHT // 2 - mh // 2
        if mx <= px <= mx + mw and my <= py <= my + mh:
            return True

    return False

def update_prey(dt):
    global prey_spawn_timer, prey_list
    prey_spawn_timer += dt
    # Increase spawn rate for more active world
    if prey_spawn_timer >= 15.0: # Spawn every 15 seconds
        spawn_prey()
        prey_spawn_timer = 0
    
    # Update each prey relative to world coordinates
    new_prey_list = []
    for prey in prey_list:
        # Prey should think player is at (world_x + WIDTH/2, world_y + HEIGHT/2)
        if prey.update(world_x + WIDTH // 2, world_y + HEIGHT // 2, dt):
            new_prey_list.append(prey)
    prey_list = new_prey_list

def draw_prey():
    for prey in prey_list:
        # Draw relative to camera and including camera_offset for smooth panning
        screen_x = prey.x - world_x - camera_offset_x
        screen_y = prey.y - world_y - camera_offset_y
        
        # Only draw if on screen
        if -100 < screen_x < WIDTH + 100 and -100 < screen_y < HEIGHT + 100:
            if prey.alpha < 255:
                temp_img = prey_img.copy()
                temp_img.set_alpha(prey.alpha)
                screen.blit(temp_img, (screen_x - 25, screen_y - 25))
            else:
                screen.blit(prey_img, (screen_x - 25, screen_y - 25))

def check_prey_collision():
    global hunger, prey_list, last_hunt_time, carried_prey, hunting_xp, hunting_skill, player_level
    cat_world_x = world_x + WIDTH // 2
    cat_world_y = world_y + HEIGHT // 2
    cat_rect = pygame.Rect(cat_world_x - cat_img.get_width() // 2, cat_world_y - cat_img.get_height() // 2, cat_img.get_width(), cat_img.get_height())
    caught = False
    for prey in prey_list[:]:
        if prey.state == Prey.HIDING: continue
        prey_rect = pygame.Rect(prey.x - 25, prey.y - 25, 50, 50)
        if cat_rect.colliderect(prey_rect):
            # Successful catch using world coordinates
            hunger = min(100, hunger + 20)
            try:
                prey_list.remove(prey)
            except ValueError:
                pass
            last_hunt_time = time.time()

            # Hunting progression: increment XP and skill by 1%
            hunting_xp = globals().get('hunting_xp', 0) + 1
            hunting_skill = min(100, hunting_skill + 1)
            if hunting_skill >= 100:
                player_level += 1
                hunting_skill = 0
                save_game_config(game_config)

            # Carry system
            if len(carried_prey) < MAX_CARRY:
                carried_prey.append(prey)
            else:
                inventory.add_item(Item("Mouse", (200, 150, 100), "A fresh catch."))

            logging.info(f"Caught prey at {prey.x:.1f},{prey.y:.1f} - Hunting XP now {hunting_xp}")
            caught = True
            break
    
    if not caught:
        # Pounce failed - trigger panic in nearby prey
        for prey in prey_list:
            dist = ((prey.x - cat_world_x)**2 + (prey.y - cat_world_y)**2)**0.5
            if dist < 150:
                prey.state = Prey.FLEEING
                prey.panic_timer = 1.5

def draw_pounce_meter():
    # Respect streamer mode: hide pounce HUD when streamer_mode is active
    if 'streamer_mode' in globals() and globals().get('streamer_mode'):
        return
    # Only show if near prey (using world coords)
    cat_world_x = world_x + WIDTH // 2
    cat_world_y = world_y + HEIGHT // 2
    cat_rect = pygame.Rect(cat_world_x - cat_img.get_width() // 2, cat_world_y - cat_img.get_height() // 2, cat_img.get_width(), cat_img.get_height())
    near_prey = any(pygame.Rect(prey.x - 25, prey.y - 25, 50, 50).colliderect(cat_rect.inflate(200, 200)) for prey in prey_list if prey.state != Prey.HIDING)
    if near_prey:
        bar_x = WIDTH // 2 - 50
        bar_y = HEIGHT // 2 - 80
        # Pounce meter is a screen-space HUD element; do not apply camera offsets
        pygame.draw.rect(screen, GRAY, (bar_x, bar_y, 100, 12))
        pygame.draw.rect(screen, ORANGE, (bar_x, bar_y, int((pounce_meter / max_pounce) * 100), 12))
        pygame.draw.rect(screen, BLACK, (bar_x, bar_y, 100, 12), 2)
        text = tiny_font.render("Pounce", True, WHITE)
        screen.blit(text, (bar_x + 110, bar_y - 2))

def draw_dash_charge():
    """Draw yellow dash charge bar when charging."""
    if 'streamer_mode' in globals() and globals().get('streamer_mode'):
        return
    if not is_charging_dash:
        return
    # Bar position - centered above bottom HUD
    hud_h = 60
    bar_w = 220
    bar_h = 14
    bx = WIDTH // 2 - bar_w // 2
    by = HEIGHT - hud_h - 30

    # Background
    pygame.draw.rect(screen, (40, 40, 40), (bx, by, bar_w, bar_h))
    # Fill
    fill = int((dash_charge / max_dash_charge) * bar_w)
    pygame.draw.rect(screen, (240, 200, 60), (bx, by, fill, bar_h))
    # Border
    pygame.draw.rect(screen, BLACK, (bx, by, bar_w, bar_h), 2)
    # Text
    txt = tiny_font.render(f"Dash: {int((dash_charge/max_dash_charge)*100)}%", True, WHITE)
    screen.blit(txt, (bx + bar_w + 8, by - 2))


class StatusBarContainer:
    """Container for manual placement of status bars.

    Usage:
      - Create a global `status_bar_container = StatusBarContainer(...)`
      - Each bar entry is a dict with keys: name, var (string name of global), color
      - Call `status_bar_container.render(screen, font)` from the main render loop
    """
    def __init__(self, x=10, y=10, width=150, height=15, padding=8, orientation='vertical', bars=None):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.padding = padding
        self.orientation = orientation  # 'vertical' or 'horizontal'
        self.bars = bars or []

    def render(self, surface, font):
        """Render all bars relative to the container position.

        Each bar uses the global variable name provided in `var` field to
        fetch its current value (0-100). This keeps the placement manual
        and editable in code.
        """
        cx, cy = self.x, self.y
        for i, b in enumerate(self.bars):
            name = b.get('name')
            var_name = b.get('var')
            color = b.get('color', WHITE)

            # Fetch value from globals; default to 0 if missing
            value = globals().get(var_name, 0)
            try:
                value = float(value)
            except Exception:
                value = 0.0

            # Calculate position for this bar
            if self.orientation == 'vertical':
                bx = cx
                by = cy + i * (self.height + self.padding)
                bw = self.width
                bh = self.height
            else:
                bx = cx + i * (self.width + self.padding)
                by = cy
                bw = self.width
                bh = self.height

            # Background
            pygame.draw.rect(surface, GRAY, (bx, by, bw, bh))

            # Fill according to value
            fill_w = int(max(0, min(1.0, value / 100.0)) * bw)
            pygame.draw.rect(surface, color, (bx, by, fill_w, bh))

            # Border and text
            pygame.draw.rect(surface, BLACK, (bx, by, bw, bh), 2)
            if font:
                txt = font.render(f"{name}: {int(value)}", True, WHITE)
                surface.blit(txt, (bx + bw + 6, by))


def draw_status_bars():
    """Backwards-compatible wrapper: renders status bars from the
    configurable StatusBarContainer if present. This keeps manual
    placement control and preserves previous behaviour by default.
    """
    # Hide status bars in streamer mode (chat-only remains elsewhere)
    if 'streamer_mode' in globals() and globals().get('streamer_mode'):
        return

    if 'status_bar_container' in globals() and status_bar_container is not None:
        status_bar_container.render(screen, tiny_font)
        return

    # Fallback: legacy rendering (keeps old appearance if container missing)
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
    now = datetime.now()
    if use_12h_format:
        current_time = now.strftime("%I:%M %p")
    else:
        current_time = now.strftime("%H:%M")
    time_text = tiny_font.render(current_time, True, WHITE)
    return time_text

def draw_bottom_hud():
    """Draw Sims-style HUD at the bottom"""
    if 'streamer_mode' in globals() and globals().get('streamer_mode'):
        return
    hud_h = 60
    hud_y = HEIGHT - hud_h
    
    # Gradient panel
    draw_gradient_rect(screen, (10, 10, 10), DARK_CYAN, (0, hud_y, WIDTH, hud_h))
    pygame.draw.line(screen, CYAN, (0, hud_y), (WIDTH, hud_y), 2)
    
    # Time
    time_txt = draw_clock()
    screen.blit(time_txt, (20, hud_y + 10))
    
    # Player Level
    lvl_txt = small_font.render(f"Level: {player_level}", True, WHITE)
    screen.blit(lvl_txt, (20, hud_y + 30))
    
    # Character Info Button (Right side)
    btn_w, btn_h = 150, 40
    btn_x = WIDTH - btn_w - 20
    btn_y = hud_y + (hud_h - btn_h) // 2
    
    pygame.draw.rect(screen, (30, 30, 30), (btn_x, btn_y, btn_w, btn_h))
    pygame.draw.rect(screen, CYAN, (btn_x, btn_y, btn_w, btn_h), 2)
    
    btn_txt = small_font.render("Character Info", True, WHITE)
    screen.blit(btn_txt, (btn_x + btn_w // 2 - btn_txt.get_width() // 2, btn_y + 8))

def draw_upgrades_menu():
    """Draw the dedicated Upgrades menu"""
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 200))
    screen.blit(overlay, (0, 0))
    
    mw, mh = 500, 400
    mx, my = WIDTH // 2 - mw // 2, HEIGHT // 2 - mh // 2
    
    draw_gradient_rect(screen, (10, 10, 10), DARK_CYAN, (mx, my, mw, mh))
    pygame.draw.rect(screen, CYAN, (mx, my, mw, mh), 2)
    
    title = font.render("Upgrades", True, CYAN)
    screen.blit(title, (mx + 20, my + 20))
    
    empty_msg = small_font.render("No upgrades available yet.", True, GRAY)
    # Render available upgrades with lock state
    start_y = my + 70
    row_h = 46
    for i, up in enumerate(UPGRADES):
        uy = start_y + i * (row_h + 8)
        rect = pygame.Rect(mx + 30, uy, mw - 60, row_h)
        pygame.draw.rect(screen, (30, 30, 30), rect)
        border_col = CYAN if not up.get('locked', True) else GRAY
        pygame.draw.rect(screen, border_col, rect, 2)
        name_txt = small_font.render(up.get('name', 'Unknown'), True, WHITE if not up.get('locked', True) else LIGHT_GRAY)
        screen.blit(name_txt, (rect.x + 10, rect.y + 8))
        # Requirement text
        req_txt = tiny_font.render(f"Requires level {up.get('required_level', 0)}", True, LIGHT_GRAY)
        screen.blit(req_txt, (rect.x + rect.width - req_txt.get_width() - 10, rect.y + 12))
    
    back_msg = small_font.render("Press ESC to Back", True, WHITE)
    screen.blit(back_msg, (mx + mw // 2 - back_msg.get_width() // 2, my + mh - 40))

def draw_character_info():
    """Draw Character Info editing screen"""
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 200))
    screen.blit(overlay, (0, 0))
    
    mw, mh = 600, 450
    mx, my = WIDTH // 2 - mw // 2, HEIGHT // 2 - mh // 2
    
    draw_gradient_rect(screen, (10, 10, 10), DARK_CYAN, (mx, my, mw, mh))
    pygame.draw.rect(screen, CYAN, (mx, my, mw, mh), 2)
    
    title = font.render("Character Info", True, CYAN)
    screen.blit(title, (mx + 20, my + 20))
    
    # Name Field
    lbl_name = small_font.render("Character Name:", True, WHITE)
    screen.blit(lbl_name, (mx + 40, my + 80))
    name_rect = pygame.Rect(mx + 40, my + 110, mw - 80, 40)
    bg_color = (40, 40, 40) if char_info_focus == "name" else (20, 20, 20)
    pygame.draw.rect(screen, bg_color, name_rect)
    pygame.draw.rect(screen, CYAN if char_info_focus == "name" else GRAY, name_rect, 2)
    name_txt = small_font.render(char_name_input, True, WHITE)
    screen.blit(name_txt, (name_rect.x + 10, name_rect.y + 8))
    
    # Bio Field
    lbl_bio = small_font.render("Character Bio:", True, WHITE)
    screen.blit(lbl_bio, (mx + 40, my + 170))
    bio_rect = pygame.Rect(mx + 40, my + 200, mw - 80, 150)
    bg_color = (40, 40, 40) if char_info_focus == "bio" else (20, 20, 20)
    pygame.draw.rect(screen, bg_color, bio_rect)
    pygame.draw.rect(screen, CYAN if char_info_focus == "bio" else GRAY, bio_rect, 2)
    
    # Wrap bio text
    words = char_bio_input.split(' ')
    lines = []
    current_line = ""
    for word in words:
        test_line = current_line + word + " "
        if small_font.size(test_line)[0] < bio_rect.width - 20:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word + " "
    lines.append(current_line)
    
    for i, line in enumerate(lines[:6]): # Show up to 6 lines
        txt = small_font.render(line, True, WHITE)
        screen.blit(txt, (bio_rect.x + 10, bio_rect.y + 10 + i * 25))

    # Save and Close hint
    hint = small_font.render("Press ENTER to Save | ESC to Cancel", True, WHITE)
    screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 40))

def handle_character_info_input(event):
    global char_info_open, char_name_input, char_bio_input, char_info_focus
    global character_name, character_bio
    
    if event.type == pygame.MOUSEBUTTONDOWN:
        mx, my = event.pos
        mw, mh = 600, 450
        px, py = WIDTH // 2 - mw // 2, HEIGHT // 2 - mh // 2
        if pygame.Rect(px + 40, py + 110, mw - 80, 40).collidepoint(mx, my):
            char_info_focus = "name"
        elif pygame.Rect(px + 40, py + 200, mw - 80, 150).collidepoint(mx, my):
            char_info_focus = "bio"

    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            pop_top_overlay()
        elif event.key == pygame.K_RETURN:
            character_name = char_name_input
            character_bio = char_bio_input
            save_game_config(game_config)
            # Update server if connected
            if network_client.connected:
                network_client.send({'type': 'username_change', 'new_username': character_name})
            pop_top_overlay()
        elif event.key == pygame.K_BACKSPACE:
            if char_info_focus == "name":
                char_name_input = char_name_input[:-1]
            else:
                char_bio_input = char_bio_input[:-1]
        elif event.key == pygame.K_TAB:
            char_info_focus = "bio" if char_info_focus == "name" else "name"
        else:
            if event.unicode.isprintable():
                if char_info_focus == "name" and len(char_name_input) < 20:
                    char_name_input += event.unicode
                elif char_info_focus == "bio" and len(char_bio_input) < 200:
                    char_bio_input += event.unicode

def handle_upgrades_input(event):
    global upgrades_menu_open
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            pop_top_overlay()
            return
    if event.type == pygame.MOUSEBUTTONDOWN:
        mx, my = event.pos
        mw, mh = 500, 400
        mx0, my0 = WIDTH // 2 - mw // 2, HEIGHT // 2 - mh // 2
        start_y = my0 + 70
        row_h = 46
        for i, up in enumerate(UPGRADES):
            uy = start_y + i * (row_h + 8)
            rect = pygame.Rect(mx0 + 30, uy, mw - 60, row_h)
            if rect.collidepoint(mx, my):
                success, msg = attempt_unlock(up['id'])
                print(f"[UPGRADE] {up['id']} click -> {success}: {msg}")
                return

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

# UI Theme Constants
CYAN = (0, 255, 255)
DARK_CYAN = (0, 100, 100)

def draw_gradient_rect(surface, color1, color2, rect):
    """Draw a vertical gradient rectangle"""
    target_rect = pygame.Rect(rect)
    color_rect = pygame.Surface((2, 2))
    pygame.draw.line(color_rect, color1, (0, 0), (1, 0))
    pygame.draw.line(color_rect, color2, (0, 1), (1, 1))
    color_rect = pygame.transform.smoothscale(color_rect, (target_rect.width, target_rect.height))
    surface.blit(color_rect, target_rect)

def draw_setup_screen():
    """Draw the first-time setup screen"""
    # Black to Cyan gradient background
    draw_gradient_rect(screen, BLACK, DARK_CYAN, (0, 0, WIDTH, HEIGHT))
    
    title = font.render("First-Time Setup", True, CYAN)
    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 100))
    
    prompt = small_font.render("Enter your username:", True, WHITE)
    screen.blit(prompt, (WIDTH // 2 - prompt.get_width() // 2, 200))
    
    # Input box
    box_w, box_h = 300, 40
    box_x, box_y = WIDTH // 2 - box_w // 2, 240
    pygame.draw.rect(screen, (20, 20, 20), (box_x, box_y, box_w, box_h))
    pygame.draw.rect(screen, CYAN, (box_x, box_y, box_w, box_h), 2)
    
    name_text = small_font.render(username, True, WHITE)
    screen.blit(name_text, (box_x + 10, box_y + 10))
    
    instr = tiny_font.render("Press ENTER to continue", True, (150, 150, 150))
    screen.blit(instr, (WIDTH // 2 - instr.get_width() // 2, 300))

def handle_setup_input(event):
    global username, game_state, game_config
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_RETURN:
            if username.strip() and username != "Player":
                game_config["username"] = username.strip()
                save_game_config(game_config)
                game_state = "menu"
        elif event.key == pygame.K_BACKSPACE:
            username = username[:-1]
        else:
            if len(username) < 15 and event.unicode.isprintable():
                if username == "Player":
                    username = ""
                username += event.unicode

def draw_menu():
    """Draw the main menu"""
    draw_gradient_rect(screen, BLACK, DARK_CYAN, (0, 0, WIDTH, HEIGHT))

    # Title
    title_text = font.render("CatGen Alpha - Main Menu", True, CYAN)
    screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 50))
    
    # Subtitle with username
    user_text = small_font.render(f"Logged in as: {username}", True, WHITE)
    screen.blit(user_text, (WIDTH // 2 - user_text.get_width() // 2, 90))

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
        # Draw rectangular panel for buttons
        btn_w, btn_h = 320, 35
        bx, by = WIDTH // 2 - btn_w // 2, 150 + i * 45 - btn_h // 2
        pygame.draw.rect(screen, (20, 20, 20), (bx, by, btn_w, btn_h))
        pygame.draw.rect(screen, CYAN, (bx, by, btn_w, btn_h), 1)
        
        option_text = small_font.render(option, True, WHITE)
        screen.blit(option_text, (WIDTH // 2 - option_text.get_width() // 2, 150 + i * 45 - option_text.get_height() // 2))

    # Current time
    current_time = datetime.now().strftime("%H:%M:%S")
    time_text = small_font.render(f"Current Time: {current_time}", True, LIGHT_GRAY)
    screen.blit(time_text, (WIDTH // 2 - time_text.get_width() // 2, HEIGHT - 50))

def draw_multiplayer_menu():
    """Draw modern Minecraft-style multiplayer menu"""
    draw_gradient_rect(screen, BLACK, DARK_CYAN, (0, 0, WIDTH, HEIGHT))
    
    if mp_menu_state == MP_STATE_LIST:
        title = font.render("Play Multiplayer", True, CYAN)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 30))
        
        # Server list panel
        list_rect = pygame.Rect(50, 80, WIDTH - 100, HEIGHT - 200)
        pygame.draw.rect(screen, (10, 10, 10), list_rect)
        pygame.draw.rect(screen, CYAN, list_rect, 1)
        
        # Draw servers (LAN results first)
        displayed_servers = (lan_scan_results or []) + saved_servers
        visible_count = (list_rect.height - 10) // 60
        for i in range(visible_count):
            idx = i + server_scroll_offset
            if idx >= len(displayed_servers): break

            s = displayed_servers[idx]
            entry_rect = pygame.Rect(list_rect.x + 5, list_rect.y + 5 + i * 60, list_rect.width - 10, 55)

            # Selection highlight
            if idx == selected_server_index:
                pygame.draw.rect(screen, (0, 60, 60), entry_rect)
                pygame.draw.rect(screen, WHITE, entry_rect, 1)
            else:
                pygame.draw.rect(screen, (30, 30, 30), entry_rect)

            name = s.get('name', f"LAN {s['ip']}")
            name_t = small_font.render(name, True, CYAN)
            addr_t = tiny_font.render(f"{s['ip']}:{s['port']}", True, LIGHT_GRAY)
            screen.blit(name_t, (entry_rect.x + 10, entry_rect.y + 5))
            screen.blit(addr_t, (entry_rect.x + 10, entry_rect.y + 30))

            # Connection status (ping placeholder or LAN tag)
            if 'ping' in s:
                status_text = f"{s.get('ping', '??')} ms"
            else:
                status_text = "LAN"
            status_t = tiny_font.render(status_text, True, (100, 100, 100))
            screen.blit(status_t, (entry_rect.right - status_t.get_width() - 10, entry_rect.y + 20))

        # Bottom buttons
        btn_w, btn_h = 120, 30
        host_label = "Stop Hosting" if is_multiplayer_host else "Host LAN"
        buttons = [
            ("Scan LAN", 0, 0),
            ("Join Server", 1, 0),
            ("Direct Connect", 2, 0),
            (host_label, 0, 1),
            ("Add Server", 1, 1),
            ("Edit Server", 2, 1),
            ("Delete Server", 0, 2),
            ("Back", 1, 2)
        ]

        start_x = WIDTH // 2 - (3 * btn_w + 20) // 2
        start_y = HEIGHT - 100

        for name, col, row in buttons:
            bx = start_x + col * (btn_w + 10)
            by = start_y + row * (btn_h + 10)
            pygame.draw.rect(screen, (20, 20, 20), (bx, by, btn_w, btn_h))

            # Highlight join/edit/delete if no selection
            is_enabled = True
            if name in ["Join Server", "Edit Server", "Delete Server"] and selected_server_index == -1:
                is_enabled = False

            border_col = CYAN if is_enabled else (50, 50, 50)
            pygame.draw.rect(screen, border_col, (bx, by, btn_w, btn_h), 1)

            txt_col = WHITE if is_enabled else GRAY
            txt = tiny_font.render(name, True, txt_col)
            screen.blit(txt, (bx + btn_w // 2 - txt.get_width() // 2, by + btn_h // 2 - txt.get_height() // 2))

            # Draw spinner on Scan LAN while scanning
            if name == "Scan LAN" and lan_scanning:
                cx = bx + btn_w - 16
                cy = by + btn_h // 2
                angle = (time.time() * 360) % 360
                rad = math.radians(angle)
                ex = cx + int(math.cos(rad) * 8)
                ey = cy + int(math.sin(rad) * 8)
                pygame.draw.circle(screen, CYAN, (cx, cy), 8, 1)
                pygame.draw.line(screen, CYAN, (cx, cy), (ex, ey), 2)

    elif mp_menu_state in [MP_STATE_ADD, MP_STATE_EDIT, MP_STATE_DIRECT]:
        title_str = "Add Server" if mp_menu_state == MP_STATE_ADD else ("Edit Server" if mp_menu_state == MP_STATE_EDIT else "Direct Connect")
        title = font.render(title_str, True, CYAN)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
        
        # Fields
        fields = []
        if mp_menu_state != MP_STATE_DIRECT:
            fields.append(("Server Name", edit_server_name, "name"))
        fields.append(("Server Address", edit_server_ip if mp_menu_state != MP_STATE_DIRECT else direct_ip, "ip"))
        fields.append(("Port", edit_server_port if mp_menu_state != MP_STATE_DIRECT else direct_port, "port"))
        fields.append(("Password (Optional)", edit_server_pass if mp_menu_state != MP_STATE_DIRECT else direct_pass, "pass"))
        
        for i, (label, value, fid) in enumerate(fields):
            ly = 120 + i * 70
            lbl = small_font.render(label, True, WHITE)
            screen.blit(lbl, (WIDTH // 2 - 150, ly))
            
            box_rect = pygame.Rect(WIDTH // 2 - 150, ly + 25, 300, 30)
            pygame.draw.rect(screen, (10, 10, 10), box_rect)
            
            border_col = WHITE if input_focus == fid else CYAN
            pygame.draw.rect(screen, border_col, box_rect, 1 if input_focus != fid else 2)
            
            val_t = small_font.render(value + ("_" if input_focus == fid and int(time.time()*2)%2 else ""), True, WHITE)
            screen.blit(val_t, (box_rect.x + 5, box_rect.y + 5))
            
        # Buttons
        btn_w, btn_h = 140, 35
        bx1, by1 = WIDTH // 2 - 150, HEIGHT - 100
        bx2, by2 = WIDTH // 2 + 10, HEIGHT - 100
        
        pygame.draw.rect(screen, (20, 20, 20), (bx1, by1, btn_w, btn_h))
        pygame.draw.rect(screen, CYAN, (bx1, by1, btn_w, btn_h), 1)
        pygame.draw.rect(screen, (20, 20, 20), (bx2, by2, btn_w, btn_h))
        pygame.draw.rect(screen, CYAN, (bx2, by2, btn_w, btn_h), 1)
        
        t1 = small_font.render("Save/Connect" if mp_menu_state == MP_STATE_DIRECT else "Done", True, WHITE)
        t2 = small_font.render("Cancel", True, WHITE)
        screen.blit(t1, (bx1 + btn_w // 2 - t1.get_width() // 2, by1 + btn_h // 2 - t1.get_height() // 2))
        screen.blit(t2, (bx2 + btn_w // 2 - t2.get_width() // 2, by2 + btn_h // 2 - t2.get_height() // 2))

def draw_chat():
    """Draw chat interface (Roblox style, Aero look)"""
    if not chat_open and len(chat_messages) == 0:
        return

    # Chat history background (rounded, semi-transparent, Aero style)
    chat_height = 200
    bottom_offset = 60 + 40 # Bottom HUD height + extra margin
    chat_bg = pygame.Surface((WIDTH - 40, chat_height), pygame.SRCALPHA)
    chat_bg.fill((240, 255, 255, 180))  # Aero blue/white
    pygame.draw.rect(chat_bg, (180, 220, 255, 220), chat_bg.get_rect(), border_radius=18)
    screen.blit(chat_bg, (20, HEIGHT - chat_height - bottom_offset))

    # Chat messages (stacked, Roblox style)
    max_visible = 8
    with network_client.lock:
        visible_messages = network_client.chat_messages[-max_visible:]
    for i, msg in enumerate(visible_messages):
        msg_text = aero_font.render(msg, True, (30, 30, 30))
        screen.blit(msg_text, (36, HEIGHT - chat_height - bottom_offset + 10 + i * 24))

    # Chat input
    if chat_open:
        input_bg = pygame.Surface((WIDTH - 40, 36), pygame.SRCALPHA)
        input_bg.fill((240, 255, 255, 220))
        pygame.draw.rect(input_bg, (180, 220, 255, 220), input_bg.get_rect(), border_radius=18)
        screen.blit(input_bg, (20, HEIGHT - 38 - 60)) # Above HUD

        prompt = f"Say: {chat_input}"
        input_text = aero_font.render(prompt, True, (30, 30, 30))
        screen.blit(input_text, (36, HEIGHT - 32 - 60))

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

def start_lan_host(port=25565, password=""):
    """Start hosting a LAN game"""
    from server import GameServer
    global is_multiplayer_host
    global lan_broadcast_thread, lan_broadcast_running
    
    def run_server():
        global hosted_server
        try:
            server = GameServer(port=int(port), password=password)
            hosted_server = server
            server.start()
        except Exception as e:
            print(f"Server error: {e}")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    is_multiplayer_host = True
    print(f"LAN server started on port {port}")

    # Start UDP broadcast announcer so clients can discover the host without scanning all IPs
    def _broadcaster():
        import socket as _socket
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            s.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
            while lan_broadcast_running:
                try:
                    player_count = 1
                    if hosted_server is not None:
                        try:
                            player_count = max(1, len(hosted_server.players))
                        except Exception:
                            pass
                    announce = json.dumps({
                        'type': 'lan_announce',
                        'name': 'CatGen Server',
                        'players': player_count,
                        'port': int(port),
                    })
                    s.sendto(announce.encode('utf-8'), ('255.255.255.255', LAN_BROADCAST_PORT))
                except Exception as e:
                    print(f"[MP ERROR] LAN broadcast send failed: {e}")
                time.sleep(1.0)
        except Exception as e:
            print(f"[MP ERROR] LAN broadcaster failed: {e}")
        finally:
            try: s.close()
            except: pass

    lan_broadcast_running = True
    lan_broadcast_thread = threading.Thread(target=_broadcaster, daemon=True)
    lan_broadcast_thread.start()

def stop_lan_host():
    """Stop an in-game hosted LAN server if running."""
    global lan_broadcast_running, is_multiplayer_host, hosted_server
    lan_broadcast_running = False
    is_multiplayer_host = False
    try:
        if hosted_server:
            hosted_server.running = False
            hosted_server = None
            print("LAN server stopped")
    except Exception as e:
        print(f"Error stopping hosted server: {e}")
def update_status_bars(dt):
    """Update status bars over time"""
    global hunger, thirst, bathroom, sleep, dash_cooldown

    # Decrease over time (very slow for demo) - normalized to 60 FPS
    hunger -= 0.6 * dt
    thirst -= 0.9 * dt
    bathroom -= 0.48 * dt
    sleep -= 0.3 * dt

    if dash_cooldown > 0:
        dash_cooldown -= dt

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
                # No longer requiring "say" prefix
                msg_to_send = chat_input
                with network_client.lock:
                    network_client.chat_messages.append(f"{character_name}: {msg_to_send}")
                player_message = msg_to_send
                message_timer = 5.0  # 5 seconds
                
                # Send chat to server
                network_client.send({'type': 'chat', 'message': msg_to_send, 'username': character_name})
                network_client.send({'type': 'typing_stop'})
                
                chat_input = ""
                # Close chat overlay
                pop_top_overlay()
        elif event.key == pygame.K_ESCAPE:
                pop_top_overlay()
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
            go_back()
        elif event.key == pygame.K_m:
            set_game_state("map")
        elif event.key == pygame.K_p:
            set_game_state("multiplayer")
        elif event.key == pygame.K_c:
            set_game_state("credits")
        elif event.key == pygame.K_l:
            set_game_state("changelog")
        elif event.key == pygame.K_k:
            set_game_state("keybinds")
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
    """Handle modern multiplayer menu input"""
    global game_state, mp_menu_state, selected_server_index, saved_servers
    global edit_server_name, edit_server_ip, edit_server_port, edit_server_pass
    global direct_ip, direct_port, direct_pass, input_focus, server_scroll_offset

    if mp_menu_state == MP_STATE_LIST:
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            # List selection
            list_rect = pygame.Rect(50, 80, WIDTH - 100, HEIGHT - 200)
            if list_rect.collidepoint(mx, my):
                displayed_servers = (lan_scan_results or []) + saved_servers
                idx = (my - list_rect.y - 5) // 60 + server_scroll_offset
                if 0 <= idx < len(displayed_servers):
                    selected_server_index = idx
            
            # Scroll
            if event.button == 4: # Scroll up
                server_scroll_offset = max(0, server_scroll_offset - 1)
            elif event.button == 5: # Scroll down
                displayed_servers = (lan_scan_results or []) + saved_servers
                max_scroll = max(0, len(displayed_servers) - (list_rect.height // 60))
                server_scroll_offset = min(max_scroll, server_scroll_offset + 1)

            # Buttons
            btn_w, btn_h = 120, 30
            start_x = WIDTH // 2 - (3 * btn_w + 20) // 2
            start_y = HEIGHT - 100
            
            host_label = "Stop Hosting" if is_multiplayer_host else "Host LAN"
            button_names = ["Scan LAN", "Join Server", "Direct Connect", host_label, "Add Server", "Edit Server", "Delete Server", "Back"]
            for i, name in enumerate(button_names):
                col, row = i % 3, i // 3
                bx = start_x + col * (btn_w + 10)
                by = start_y + row * (btn_h + 10)
                if pygame.Rect(bx, by, btn_w, btn_h).collidepoint(mx, my):
                    if name == "Scan LAN":
                        if not lan_scanning:
                            def _runner():
                                scan_lan_servers()
                            lan_scan_thread = threading.Thread(target=_runner, daemon=True)
                            lan_scan_thread.start()
                    elif name == "Host LAN":
                        # Start hosting in-game (default port)
                        start_lan_host(port=25565, password="")
                    elif name == "Stop Hosting":
                        # Stop hosting announcer and server
                        try:
                            stop_lan_host()
                        except Exception:
                            pass
                    elif name == "Join Server" and selected_server_index != -1:
                        displayed_servers = (lan_scan_results or []) + saved_servers
                        s = displayed_servers[selected_server_index]
                        success, msg = connect_to_server(s['ip'], s['port'], username, s.get('password', ''))
                        if success:
                            set_game_state("playing")
                    elif name == "Direct Connect":
                        mp_menu_state = MP_STATE_DIRECT
                        input_focus = "ip"
                    elif name == "Add Server":
                        mp_menu_state = MP_STATE_ADD
                        edit_server_name = ""
                        edit_server_ip = ""
                        edit_server_port = "25565"
                        edit_server_pass = ""
                        input_focus = "name"
                    elif name == "Edit Server" and selected_server_index != -1:
                        # Only editable if selection is from saved_servers
                        if selected_server_index >= len(lan_scan_results):
                            s = saved_servers[selected_server_index - len(lan_scan_results)]
                            edit_server_name = s['name']
                            edit_server_ip = s['ip']
                            edit_server_port = s['port']
                            edit_server_pass = s.get('password', '')
                            mp_menu_state = MP_STATE_EDIT
                            input_focus = "name"
                    elif name == "Delete Server" and selected_server_index != -1:
                        if selected_server_index >= len(lan_scan_results):
                            saved_servers.pop(selected_server_index - len(lan_scan_results))
                            save_servers(saved_servers)
                            selected_server_index = -1
                    elif name == "Back":
                        go_back()

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if mp_menu_state == MP_STATE_LIST:
                    go_back()
                else:
                    mp_menu_state = MP_STATE_LIST

    elif mp_menu_state in [MP_STATE_ADD, MP_STATE_EDIT, MP_STATE_DIRECT]:
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            # Button detection
            btn_w, btn_h = 140, 35
            bx1, by1 = WIDTH // 2 - 150, HEIGHT - 100
            bx2, by2 = WIDTH // 2 + 10, HEIGHT - 100
            
            if pygame.Rect(bx1, by1, btn_w, btn_h).collidepoint(mx, my): # Done / Connect
                if mp_menu_state == MP_STATE_DIRECT:
                    success, msg = connect_to_server(direct_ip, direct_port, username, direct_pass)
                    if success: set_game_state("playing")
                else:
                    new_server = {"name": edit_server_name, "ip": edit_server_ip, "port": edit_server_port, "password": edit_server_pass}
                    if mp_menu_state == MP_STATE_ADD:
                        saved_servers.append(new_server)
                    else:
                        saved_servers[selected_server_index] = new_server
                    save_servers(saved_servers)
                    mp_menu_state = MP_STATE_LIST
            elif pygame.Rect(bx2, by2, btn_w, btn_h).collidepoint(mx, my): # Cancel / Back
                if mp_menu_state == MP_STATE_DIRECT:
                    go_back()
                else:
                    mp_menu_state = MP_STATE_LIST

            # Field focus
            fields = ["name", "ip", "port", "pass"] if mp_menu_state != MP_STATE_DIRECT else ["ip", "port", "pass"]
            for i, fid in enumerate(fields):
                ly = 120 + i * 70
                if pygame.Rect(WIDTH // 2 - 150, ly + 25, 300, 30).collidepoint(mx, my):
                    input_focus = fid

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                mp_menu_state = MP_STATE_LIST
            elif event.key == pygame.K_TAB:
                fields = ["name", "ip", "port", "pass"] if mp_menu_state != MP_STATE_DIRECT else ["ip", "port", "pass"]
                idx = fields.index(input_focus)
                input_focus = fields[(idx + 1) % len(fields)]
            elif event.key == pygame.K_BACKSPACE:
                if mp_menu_state == MP_STATE_DIRECT:
                    if input_focus == "ip": direct_ip = direct_ip[:-1]
                    elif input_focus == "port": direct_port = direct_port[:-1]
                    elif input_focus == "pass": direct_pass = direct_pass[:-1]
                else:
                    if input_focus == "name": edit_server_name = edit_server_name[:-1]
                    elif input_focus == "ip": edit_server_ip = edit_server_ip[:-1]
                    elif input_focus == "port": edit_server_port = edit_server_port[:-1]
                    elif input_focus == "pass": edit_server_pass = edit_server_pass[:-1]
            elif event.key == pygame.K_RETURN:
                # Same as Done button
                if mp_menu_state == MP_STATE_DIRECT:
                    success, msg = connect_to_server(direct_ip, direct_port, username, direct_pass)
                    if success: game_state = "playing"
                else:
                    new_server = {"name": edit_server_name, "ip": edit_server_ip, "port": edit_server_port, "password": edit_server_pass}
                    if mp_menu_state == MP_STATE_ADD:
                        saved_servers.append(new_server)
                    else:
                        saved_servers[selected_server_index] = new_server
                    save_servers(saved_servers)
                    mp_menu_state = MP_STATE_LIST
            else:
                if event.unicode.isprintable():
                    if mp_menu_state == MP_STATE_DIRECT:
                        if input_focus == "ip": direct_ip += event.unicode
                        elif input_focus == "port" and event.unicode.isdigit(): direct_port += event.unicode
                        elif input_focus == "pass": direct_pass += event.unicode
                    else:
                        if input_focus == "name": edit_server_name += event.unicode
                        elif input_focus == "ip": edit_server_ip += event.unicode
                        elif input_focus == "port" and event.unicode.isdigit(): edit_server_port += event.unicode
                        elif input_focus == "pass": edit_server_pass += event.unicode

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

# Auto-connect helper for testing: set environment var CATGEN_AUTOCONNECT=1
try:
    if os.environ.get('CATGEN_AUTOCONNECT') == '1':
        # Attempt to auto-connect to localhost for test runs
        print("[MP AUTOCONNECT] attempting to connect to 127.0.0.1:25565")
        ok, msg = connect_to_server('127.0.0.1', 25565, username)
        print(f"[MP AUTOCONNECT] result: {ok} - {msg}")
except Exception as e:
    print(f"[MP AUTOCONNECT] error: {e}")

# Auto-host helper for testing: set environment var CATGEN_HOST=1
try:
    if os.environ.get('CATGEN_HOST') == '1':
        print('[MP AUTOHOST] starting in-game host on 25565')
        start_lan_host(port=25565, password='')
except Exception as e:
    print(f"[MP AUTOHOST] error: {e}")

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
                if event.key == pygame.K_ESCAPE or event.key == controls.get("MENU", pygame.K_ESCAPE):
                    # ESC behaviour:
                    # - If any overlay/modal is open, close the topmost overlay.
                    # - If no overlays: pressing ESC from playing opens main menu.
                    # - If in a submenu (not main menu), return to main menu.
                    # - If already in main menu, return to playing.
                    if overlay_stack:
                        pop_top_overlay()
                    else:
                        if game_state == "playing":
                            set_game_state("menu")
                        elif game_state != "menu":
                            # In a submenu / other screen: go to main menu
                            set_game_state("menu")
                        else:
                            # Already in main menu -> resume playing
                            set_game_state("playing")
                    continue
                elif event.key == pygame.K_F11:
                    toggle_fullscreen()
                elif event.key == pygame.K_F12:
                    capture_screenshot()
                elif event.key == controls.get("STREAMER"):
                    # Toggle streamer mode (hide HUD/UI except chat)
                    streamer_mode = not streamer_mode
                    logging.info(f"Streamer mode set to {streamer_mode}")
                # Start dash charge when dash key is pressed
                if event.key == controls.get("DASH") and game_state == "playing" and not overlay_stack:
                    # Begin charging dash (actual dash happens on KEYUP)
                    is_charging_dash = True
                    dash_charge = 0.0

            if event.type == pygame.KEYUP:
                # Release dash and perform dash proportional to charge
                if event.key == controls.get("DASH") and is_charging_dash:
                    # Only execute dash if not on cooldown
                    if dash_cooldown <= 0 and stamina > 5:
                        charge_ratio = max(0.0, min(1.0, dash_charge / max_dash_charge))
                        # Determine dash direction from current movement keys
                        keys_now = pygame.key.get_pressed()
                        dx, dy = 0, 0
                        if keys_now[controls["MOVE_LEFT"]]: dx -= 1
                        if keys_now[controls["MOVE_RIGHT"]]: dx += 1
                        if keys_now[controls["MOVE_UP"]]: dy -= 1
                        if keys_now[controls["MOVE_DOWN"]]: dy += 1
                        if dx != 0 or dy != 0:
                            mag = (dx*dx + dy*dy) ** 0.5
                            dx /= mag
                            dy /= mag
                            # Dash strength scales with charge_ratio
                            dash_strength = 80 + 220 * charge_ratio
                            world_x += dx * dash_strength
                            world_y += dy * dash_strength
                            # Stamina cost scales with charge
                            stamina_cost = int(30 * (0.4 + 0.6 * charge_ratio))
                            stamina = max(0, stamina - stamina_cost)
                            dash_cooldown = 1.0
                    # Reset charging state
                    is_charging_dash = False
                    dash_charge = 0.0

            if upgrades_menu_open:
                handle_upgrades_input(event)
                continue

            if char_info_open:
                handle_character_info_input(event)
                continue

            if inventory_open:
                if event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.MOUSEBUTTONUP:
                    inventory.handle_input(event)

                if event.type == pygame.KEYDOWN:
                    if event.key == controls["INVENTORY"]:
                        # Close topmost overlay if it's inventory
                        if overlay_stack and overlay_stack[-1] == 'inventory':
                            pop_top_overlay()
                        else:
                            close_overlay('inventory')
                continue

            if game_state == "playing":
                if chat_open:
                    handle_chat_input(event)
                else:
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        mx, my = event.pos

                        # HUD Character Info button (left click opens overlay)
                        hud_h = 60
                        hud_y = HEIGHT - hud_h
                        btn_w, btn_h = 150, 40
                        btn_x = WIDTH - btn_w - 20
                        btn_y = hud_y + (hud_h - btn_h) // 2
                        if event.button == 1 and pygame.Rect(btn_x, btn_y, btn_w, btn_h).collidepoint(mx, my):
                            push_overlay('char_info')
                            char_name_input = character_name
                            char_bio_input = character_bio
                        elif event.button == 3: # Right click -> start panning only if not over UI
                            if not is_point_over_ui(mx, my):
                                is_panning = True
                                last_pan_pos = event.pos

                    elif event.type == pygame.MOUSEBUTTONUP:
                        if event.button == 3:
                            # Commit visual camera offset into world coordinates so
                            # panning doesn't permanently shift rendering offsets
                            if is_panning:
                                world_x += camera_offset_x
                                world_y += camera_offset_y
                            camera_offset_x = 0
                            camera_offset_y = 0
                            is_panning = False
                    
                    elif event.type == pygame.MOUSEMOTION:
                        if is_panning:
                            dx = event.pos[0] - last_pan_pos[0]
                            dy = event.pos[1] - last_pan_pos[1]
                            camera_offset_x -= dx
                            camera_offset_y -= dy
                            last_pan_pos = event.pos

                    if event.type == pygame.KEYDOWN:
                        if event.key == controls["MENU"]:
                            game_state = "menu"
                        elif event.key == controls["CHAT"]:
                            push_overlay('chat')
                            chat_input = ""
                        elif event.key == controls["MEOW"]:
                            current_time = time.time()
                            if current_time - last_meow_time > 1:  # Cooldown
                                msg = "*Meow!*"
                                # Die Hard Easter Egg: If player's name is "McClane" and they meow,
                                # they say a famous line instead.
                                if username.lower() == "mcclane":
                                    msg = "Yippee-ki-yay, motherclucker!"
                                print(msg)
                                player_message = msg
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
                            # Tracking progression
                            tracking_skill = min(100, tracking_skill + 1)
                            if tracking_skill >= 100:
                                player_level += 1
                                tracking_skill = 0
                                save_game_config(game_config)
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
                            if inventory_open:
                                # close inventory overlay if open
                                if overlay_stack and overlay_stack[-1] == 'inventory':
                                    pop_top_overlay()
                                else:
                                    close_overlay('inventory')
                            else:
                                push_overlay('inventory')

            elif game_state == "menu":
                handle_menu_input(event)
            elif game_state == "multiplayer":
                handle_multiplayer_input(event)
            elif game_state == "setup":
                handle_setup_input(event)
            elif game_state == "keybinds":
                handle_keybinds_input(event)
            else:
                handle_other_screen_input(event)

        # Game logic
        is_any_menu_open = (len(overlay_stack) > 0) or (game_state != "playing")
        if game_state == "playing" and not is_any_menu_open:
            keys = pygame.key.get_pressed()
            is_sprinting = keys[controls["SPRINT"]] and stamina > 0
            
            # Slower when carrying multiple prey
            weight_factor = 1.0 - (len(carried_prey) * 0.1)
            speed = (8 if is_sprinting else 4) * 60 * dt * weight_factor

            # Movement logic
            move_x, move_y = 0, 0
            if keys[controls["MOVE_LEFT"]]: move_x -= speed
            if keys[controls["MOVE_RIGHT"]]: move_x += speed
            if keys[controls["MOVE_UP"]]: move_y -= speed
            if keys[controls["MOVE_DOWN"]]: move_y += speed
            
            # Rotation of movement vector based on camera? No, requirement says 2D pan.
            world_x += move_x
            world_y += move_y
            # Clamp to world bounds
            world_x = max(-4000, min(4000, world_x))
            world_y = max(-4000, min(4000, world_y))

            # Dash charging logic (hold dash key to charge, release to dash)
            if is_charging_dash and dash_cooldown <= 0 and stamina > 5:
                dash_charge = min(max_dash_charge, dash_charge + dt)

            # Jump logic
            if keys[controls["JUMP"]] and not is_jumping:
                player_vel_z = 8.0 # Jump force
                is_jumping = True
            
            if is_jumping:
                player_z += player_vel_z
                player_vel_z -= 0.4 # Gravity
                if player_z <= 0:
                    player_z = 0
                    player_vel_z = 0
                    is_jumping = False

            update_status_bars(dt)
            update_stamina(dt)
            update_chat_messages(dt)
            update_player_map_position()
            update_prey(dt)

            cat_world_x = world_x + WIDTH // 2
            cat_world_y = world_y + HEIGHT // 2
            cat_rect = pygame.Rect(cat_world_x - cat_img.get_width() // 2, cat_world_y - cat_img.get_height() // 2, cat_img.get_width(), cat_img.get_height())
            near_prey = any(pygame.Rect(prey.x - 25, prey.y - 25, 50, 50).colliderect(cat_rect.inflate(200, 200)) for prey in prey_list if prey.state != Prey.HIDING)
            
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

        if game_state == "playing" and network_client.connected:
            _mp_state = 'idle'
            if is_charging_dash or dash_cooldown > 0:
                _mp_state = 'dashing'
            elif move_x != 0 or move_y != 0:
                _mp_state = 'moving'
            network_client.send({
                'type': 'player_update',
                'x': world_x,
                'y': world_y,
                'z': player_z,
                'state': _mp_state,
                'username': character_name,
                'bio': character_bio,
            })

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
            
            hint_text = tiny_font.render("F12: Screenshot", True, (255, 200, 200))
            screen.blit(hint_text, (10, HEIGHT - 30))
            
            # Draw Player Name Overhead
            name_label = small_font.render(character_name, True, CYAN)
            name_x = WIDTH // 2 - name_label.get_width() // 2 - camera_offset_x
            name_y = HEIGHT // 2 - cat_img.get_height() // 2 - player_z - 30 - camera_offset_y
            screen.blit(name_label, (name_x, name_y))
            
            # Draw Player Bio Overhead
            if character_bio:
                bio_label = tiny_font.render(character_bio, True, WHITE)
                screen.blit(bio_label, (WIDTH // 2 - bio_label.get_width() // 2 - camera_offset_x, name_y + 20))

            screen.blit(cat_img, (WIDTH // 2 - cat_img.get_width() // 2 - camera_offset_x, HEIGHT // 2 - cat_img.get_height() // 2 - player_z - camera_offset_y))
            
            # Draw carried prey (hidden in streamer mode)
            if not streamer_mode:
                for i, prey in enumerate(carried_prey):
                    offset_y = 10 + i * 5
                    screen.blit(pygame.transform.scale(prey_img, (30, 30)), (WIDTH // 2 - 15 - camera_offset_x, HEIGHT // 2 + offset_y - player_z - camera_offset_y))

            if player_message: draw_speech_bubble(player_message, WIDTH // 2 - camera_offset_x, HEIGHT // 2 - 60 - player_z - camera_offset_y)
            # Draw remote players in the world layer (only while playing, before HUD)
            if network_client.connected:
                with network_client.lock:
                    for pid, pdata in network_client.other_players.items():
                        if isinstance(pdata, dict):
                            # Smooth interpolation toward server-reported position
                            pdata['x'] += (pdata.get('tx', pdata['x']) - pdata['x']) * 0.15
                            pdata['y'] += (pdata.get('ty', pdata['y']) - pdata['y']) * 0.15
                            pdata['z'] += (pdata.get('tz', pdata['z']) - pdata['z']) * 0.3
                            ox = WIDTH // 2 + (pdata['x'] - world_x) - camera_offset_x
                            oy = HEIGHT // 2 + (pdata['y'] - world_y) - camera_offset_y
                            oz = pdata['z']
                            if -100 < ox < WIDTH + 100 and -100 < oy < HEIGHT + 100:
                                other_name = pdata.get('username', 'Player')
                                other_bio = pdata.get('bio', '')
                                other_label = small_font.render(other_name, True, WHITE)
                                name_y_offset = oy - cat_img.get_height() // 2 - oz - 30
                                screen.blit(other_label, (ox - other_label.get_width() // 2, name_y_offset))
                                if other_bio:
                                    other_bio_label = tiny_font.render(other_bio, True, (200, 200, 200))
                                    screen.blit(other_bio_label, (ox - other_bio_label.get_width() // 2, name_y_offset + 20))
                                screen.blit(cat_img, (ox - cat_img.get_width() // 2, oy - cat_img.get_height() // 2 - oz))
                                if network_client.other_typing.get(pid):
                                    overlay_width, overlay_height = 120, 22
                                    overlay_surf = pygame.Surface((overlay_width, overlay_height), pygame.SRCALPHA)
                                    overlay_surf.fill((240, 255, 255, 180))
                                    pygame.draw.rect(overlay_surf, (180, 220, 255, 180), overlay_surf.get_rect(), border_radius=8)
                                    text = aero_font.render("is typing...", True, (30, 30, 30))
                                    text = pygame.transform.smoothscale(text, (int(text.get_width() * 0.7), int(text.get_height() * 0.7)))
                                    overlay_surf.blit(text, (overlay_width // 2 - text.get_width() // 2, overlay_height // 2 - text.get_height() // 2))
                                    screen.blit(overlay_surf, (ox - overlay_width // 2, oy - cat_img.get_height() // 2 - 38))
            # Health/Stats background (hidden in streamer mode)
            if not streamer_mode:
                stats_bg = pygame.Surface((170, 160), pygame.SRCALPHA)
                stats_bg.fill((0, 0, 0, 150))
                pygame.draw.rect(stats_bg, CYAN, stats_bg.get_rect(), 2)
                screen.blit(stats_bg, (5, 5))
            
            draw_status_bars(); draw_chat(); draw_pounce_meter(); draw_dash_charge(); draw_bottom_hud()
            
            # Version Label (hidden in streamer mode)
            if not streamer_mode:
                version_text = small_font.render("CatGen v4 ALPHA", True, CYAN)
                screen.blit(version_text, (10, HEIGHT - 100)) # Moved away from status bars

            if inventory_open: inventory.draw(screen)
            if upgrades_menu_open: draw_upgrades_menu()
            if char_info_open: draw_character_info()
            if not chat_open:
                hint_text = tiny_font.render("F11: Fullscreen", True, WHITE)
                screen.blit(hint_text, (WIDTH - hint_text.get_width() - 10, 10))
        elif game_state == "menu": draw_menu()
        elif game_state == "map": draw_map()
        elif game_state == "multiplayer": draw_multiplayer_menu()
        elif game_state == "credits": show_credits()
        elif game_state == "changelog": show_changelog()
        elif game_state == "setup": draw_setup_screen()
        elif game_state == "keybinds": draw_keybinds()

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
