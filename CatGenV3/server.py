import socket
import threading
import json
import time
import sys

HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 25565      # Default port (like Minecraft)

class Player:
    def __init__(self, conn, addr, username="Player"):
        self.conn = conn
        self.addr = addr
        self.username = username
        self.x = 0
        self.y = 0
        self.is_typing = False
        self.last_message = ""
        self.message_timer = 0
        self.connected = True
        self.last_activity = time.time()

class GameServer:
    def __init__(self):
        self.players = {}  # {addr: Player}
        self.lock = threading.Lock()
        self.running = True
        
    def broadcast(self, message, exclude_addr=None):
        """Broadcast a message to all connected players"""
        with self.lock:
            disconnected = []
            for addr, player in self.players.items():
                if addr != exclude_addr and player.connected:
                    try:
                        player.conn.sendall((json.dumps(message) + '\n').encode('utf-8'))
                    except:
                        disconnected.append(addr)
            
            # Remove disconnected players
            for addr in disconnected:
                self.remove_player(addr)
    
    def remove_player(self, addr):
        """Remove a player from the server"""
        with self.lock:
            if addr in self.players:
                player = self.players[addr]
                print(f"Player {player.username} ({addr}) disconnected")
                try:
                    player.conn.close()
                except:
                    pass
                del self.players[addr]
                
                # Broadcast player left
                self.broadcast({
                    'type': 'player_left',
                    'username': player.username,
                    'addr': str(addr)
                })
    
    def handle_client(self, conn, addr):
        """Handle a single client connection"""
        print(f"New connection from {addr}")
        player = Player(conn, addr)
        
        with self.lock:
            self.players[addr] = player
        
        try:
            # Send welcome message with current players
            with self.lock:
                welcome_msg = {
                    'type': 'welcome',
                    'username': player.username,
                    'players': {str(a): {'username': p.username, 'x': p.x, 'y': p.y} 
                               for a, p in self.players.items() if a != addr}
                }
            conn.sendall((json.dumps(welcome_msg) + '\n').encode('utf-8'))
            
            # Broadcast new player joined
            self.broadcast({
                'type': 'player_joined',
                'username': player.username,
                'addr': str(addr)
            }, exclude_addr=addr)
            
            # Main client loop
            buffer = ""
            while player.connected and self.running:
                try:
                    data = conn.recv(4096).decode('utf-8')
                    if not data:
                        break
                    
                    buffer += data
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            try:
                                self.handle_message(player, json.loads(line))
                            except json.JSONDecodeError:
                                print(f"Invalid JSON from {addr}")
                            
                except Exception as e:
                    print(f"Error handling client {addr}: {e}")
                    break
                    
        except Exception as e:
            print(f"Client {addr} error: {e}")
        finally:
            self.remove_player(addr)
    
    def handle_message(self, player, message):
        """Handle a message from a client"""
        msg_type = message.get('type')
        
        if msg_type == 'position':
            player.x = message.get('x', 0)
            player.y = message.get('y', 0)
            player.last_activity = time.time()
            
            # Broadcast position to other players
            self.broadcast({
                'type': 'player_position',
                'username': player.username,
                'addr': str(player.addr),
                'x': player.x,
                'y': player.y
            }, exclude_addr=player.addr)
            
        elif msg_type == 'chat':
            player.last_message = message.get('message', '')
            player.message_timer = 300  # 5 seconds
            player.last_activity = time.time()
            
            # Broadcast chat to all players
            self.broadcast({
                'type': 'chat',
                'username': player.username,
                'message': player.last_message
            })
            
        elif msg_type == 'typing_start':
            player.is_typing = True
            player.last_activity = time.time()
            
            # Broadcast typing indicator
            self.broadcast({
                'type': 'typing_start',
                'username': player.username,
                'addr': str(player.addr)
            }, exclude_addr=player.addr)
            
        elif msg_type == 'typing_stop':
            player.is_typing = False
            player.last_activity = time.time()
            
            # Broadcast typing stopped
            self.broadcast({
                'type': 'typing_stop',
                'username': player.username,
                'addr': str(player.addr)
            }, exclude_addr=player.addr)
            
        elif msg_type == 'username_change':
            old_username = player.username
            player.username = message.get('username', 'Player')
            player.last_activity = time.time()
            
            # Broadcast username change
            self.broadcast({
                'type': 'username_change',
                'old_username': old_username,
                'new_username': player.username,
                'addr': str(player.addr)
            })
    
    def cleanup_inactive_players(self):
        """Remove players who haven't sent activity in 30 seconds"""
        current_time = time.time()
        with self.lock:
            inactive = [addr for addr, player in self.players.items() 
                       if current_time - player.last_activity > 30]
            for addr in inactive:
                self.remove_player(addr)
    
    def start(self):
        """Start the server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind((HOST, PORT))
            server_socket.listen(10)
            print(f"CatGen Server started on {HOST}:{PORT}")
            print("Players can connect using your local IP address")
            
            # Get local IP for display
            try:
                import subprocess
                result = subprocess.run(['ipconfig'], capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if 'IPv4' in line and '192.168' in line:
                        local_ip = line.split(':')[-1].strip()
                        print(f"Local IP: {local_ip}")
                        break
            except:
                print("Could not determine local IP automatically")
            
            # Start cleanup thread
            cleanup_thread = threading.Thread(target=self.cleanup_loop, daemon=True)
            cleanup_thread.start()
            
            # Accept connections
            while self.running:
                try:
                    conn, addr = server_socket.accept()
                    client_thread = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
                    client_thread.start()
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Error accepting connection: {e}")
                    
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            server_socket.close()
            self.running = False
    
    def cleanup_loop(self):
        """Background thread to clean up inactive players"""
        while self.running:
            time.sleep(10)  # Check every 10 seconds
            self.cleanup_inactive_players()

if __name__ == "__main__":
    server = GameServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.running = False 