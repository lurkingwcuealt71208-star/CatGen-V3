import json
import socket
import threading
import time

HOST = '0.0.0.0'
PORT = 25565


class Player:
    def __init__(self, player_id, conn, addr, username="Player"):
        self.id = player_id
        self.conn = conn
        self.addr = addr
        self.username = username
        self.bio = ""
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.state = 'idle'
        self.is_typing = False
        self.last_message = ""
        self.message_timer = 0
        self.connected = True
        self.last_activity = time.time()


class GameServer:
    def __init__(self, host='0.0.0.0', port=25565, password=""):
        self.host = host
        self.port = port
        self.password = password
        self.players = {}
        self.lock = threading.Lock()
        self.running = True
        self.next_client_id = 1
        self.server_socket = None

    def _send_packet(self, conn, message):
        print("[SERVER SEND]", message)
        conn.sendall((json.dumps(message) + '\n').encode('utf-8'))

    def _player_payload(self, player):
        return {
            'id': player.id,
            'username': player.username,
            'x': player.x,
            'y': player.y,
            'z': player.z,
            'state': player.state,
            'bio': player.bio,
        }

    def broadcast(self, message, exclude_id=None):
        with self.lock:
            recipients = [
                player
                for player_id, player in self.players.items()
                if player_id != exclude_id and player.connected
            ]

        disconnected = []
        for player in recipients:
            try:
                self._send_packet(player.conn, message)
            except Exception as e:
                print(f"[MP ERROR] Failed sending to client {player.id}: {e}")
                disconnected.append(player.id)

        for player_id in disconnected:
            self.remove_player(player_id)

    def remove_player(self, player_id):
        with self.lock:
            player = self.players.pop(player_id, None)

        if not player:
            return

        player.connected = False
        print(f"[MP] Player {player.username} ({player.id}) disconnected")
        try:
            player.conn.close()
        except Exception:
            pass

        self.broadcast({
            'type': 'player_left',
            'id': player.id,
            'username': player.username,
        }, exclude_id=player.id)

    def _perform_handshake(self, conn, addr):
        conn.settimeout(5.0)
        buffer = ""
        print(f"[MP] Awaiting handshake from {addr}")

        while self.running:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                raise TimeoutError("Handshake timed out")

            if not data:
                raise ConnectionError("Connection closed during handshake")

            buffer += data.decode('utf-8')
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if not line.strip():
                    continue

                print("[SERVER RECEIVE]", line)
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid handshake packet: {e}") from e

                if message.get('type') != 'connect':
                    raise ValueError("Expected connect packet")

                if self.password and message.get('password', '') != self.password:
                    raise PermissionError("Invalid password")

                username = str(message.get('username', 'Player')).strip() or 'Player'
                with self.lock:
                    player_id = self.next_client_id
                    self.next_client_id += 1
                    player = Player(player_id, conn, addr, username=username[:24])
                    self.players[player_id] = player
                    other_players = [
                        self._player_payload(other_player)
                        for other_id, other_player in self.players.items()
                        if other_id != player_id
                    ]

                accept_message = {
                    'type': 'accept',
                    'id': player.id,
                    'players': other_players,
                }
                print(f"[MP] Handshake accepted for {addr} as player {player.id}")
                self._send_packet(conn, accept_message)
                self.broadcast({
                    'type': 'player_joined',
                    **self._player_payload(player),
                }, exclude_id=player.id)
                conn.settimeout(0.5)
                return player, buffer

    def handle_client(self, conn, addr):
        print(f"[MP] New connection from {addr}")
        player = None
        buffer = ""

        try:
            try:
                player, buffer = self._perform_handshake(conn, addr)
            except PermissionError as e:
                print(f"[MP ERROR] Handshake rejected for {addr}: {e}")
                self._send_packet(conn, {'type': 'error', 'message': str(e)})
                conn.close()
                return
            except ValueError as e:
                print(f"[MP ERROR] Handshake failed for {addr}: {e}")
                self._send_packet(conn, {'type': 'error', 'message': str(e)})
                conn.close()
                return

            while player.connected and self.running:
                if '\n' not in buffer:
                    try:
                        data = conn.recv(4096)
                    except socket.timeout:
                        continue
                    except OSError as e:
                        print(f"[MP ERROR] Client socket error for {addr}: {e}")
                        break

                    if not data:
                        break

                    buffer += data.decode('utf-8')

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip():
                        continue

                    print("[SERVER RECEIVE]", line)
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError as e:
                        print(f"[MP ERROR] Invalid JSON from player {player.id}: {e}")
                        continue

                    self.handle_message(player, message)

        except (ConnectionError, TimeoutError) as e:
            print(f"[MP ERROR] Client {addr} error: {e}")
        except Exception as e:
            print(f"[MP ERROR] Client {addr} error: {e}")
        finally:
            if player is not None:
                self.remove_player(player.id)
            else:
                try:
                    conn.close()
                except Exception:
                    pass

    def handle_message(self, player, message):
        msg_type = message.get('type')

        if msg_type == 'ping':
            player.last_activity = time.time()
            self._send_packet(player.conn, {'type': 'pong', 'id': player.id})

        elif msg_type == 'player_update':
            try:
                player.x = float(message.get('x', player.x))
                player.y = float(message.get('y', player.y))
                player.z = float(message.get('z', player.z))
            except (TypeError, ValueError):
                print(f"[MP ERROR] Invalid player update from {player.id}: {message}")
                return

            state = str(message.get('state', 'idle')).lower()
            if state not in {'idle', 'moving', 'dashing'}:
                state = 'idle'

            player.state = state
            player.username = str(message.get('username', player.username))[:24] or player.username
            player.bio = str(message.get('bio', player.bio))[:120]
            player.last_activity = time.time()

            self.broadcast({
                'type': 'player_update',
                'id': player.id,
                'x': player.x,
                'y': player.y,
                'z': player.z,
                'state': player.state,
                'username': player.username,
                'bio': player.bio,
            }, exclude_id=player.id)

        elif msg_type == 'chat':
            player.last_message = message.get('message', '')
            player.message_timer = 300
            player.last_activity = time.time()

            self.broadcast({
                'type': 'chat',
                'id': player.id,
                'username': player.username,
                'message': player.last_message,
            })

        elif msg_type == 'typing_start':
            player.is_typing = True
            player.last_activity = time.time()
            self.broadcast({
                'type': 'typing_start',
                'id': player.id,
                'username': player.username,
            }, exclude_id=player.id)

        elif msg_type == 'typing_stop':
            player.is_typing = False
            player.last_activity = time.time()
            self.broadcast({
                'type': 'typing_stop',
                'id': player.id,
                'username': player.username,
            }, exclude_id=player.id)

        elif msg_type == 'username_change':
            old_username = player.username
            new_username = str(message.get('new_username') or message.get('username') or 'Player').strip() or 'Player'
            player.username = new_username[:24]
            player.last_activity = time.time()
            self.broadcast({
                'type': 'username_change',
                'id': player.id,
                'old_username': old_username,
                'new_username': player.username,
            })

        else:
            print(f"[MP ERROR] Unknown packet type from player {player.id}: {message}")

    def cleanup_inactive_players(self):
        current_time = time.time()
        with self.lock:
            inactive = [
                player_id
                for player_id, player in self.players.items()
                if current_time - player.last_activity > 30
            ]

        for player_id in inactive:
            self.remove_player(player_id)

    def start(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.settimeout(0.5)
        self.server_socket = server_socket

        try:
            server_socket.bind((self.host, self.port))
            server_socket.listen(10)
            print(f"[MP] Server started on port: {self.port}")
            print(f"[MP] Listening on {self.host}:{self.port}")
            if self.password:
                print("Server is password protected")

            cleanup_thread = threading.Thread(target=self.cleanup_loop, daemon=True)
            cleanup_thread.start()

            while self.running:
                try:
                    conn, addr = server_socket.accept()
                    print(f"[MP] Accepted connection from {addr}")
                    client_thread = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
                    client_thread.start()
                except socket.timeout:
                    continue
                except OSError as e:
                    if self.running:
                        print(f"[MP ERROR] Error accepting connection: {e}")
                    break
                except Exception as e:
                    print(f"[MP ERROR] Error accepting connection: {e}")

        except Exception as e:
            print(f"[MP ERROR] Server error: {e}")
        finally:
            self.running = False
            try:
                server_socket.close()
            except Exception:
                pass
            with self.lock:
                remaining_ids = list(self.players.keys())
            for player_id in remaining_ids:
                self.remove_player(player_id)

    def cleanup_loop(self):
        while self.running:
            time.sleep(10)
            self.cleanup_inactive_players()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CatGen Server")
    parser.add_argument("--port", type=int, default=25565, help="Port to listen on")
    parser.add_argument("--password", type=str, default="", help="Server password")
    args = parser.parse_args()

    server = GameServer(port=args.port, password=args.password)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.running = False