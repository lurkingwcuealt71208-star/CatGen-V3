"""
Localhost multiplayer integration test.

Starts a GameServer in a background thread, connects two raw TCP clients
(listener + sender), walks through the full handshake cycle, sends a
player_update, verifies that the listener receives the forwarded packet,
and confirms ping/pong works.

Run from the project root:
    python tests/test_localhost_multiplayer.py
"""
import json
import socket
import sys
import threading
import time

# Allow importing from project root
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network.server import GameServer

PORT = 25565


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connect_and_handshake(username, timeout=5):
    """Open a raw TCP socket, perform the connect/accept handshake and return
    (sock, client_id, leftover_buffer)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(('127.0.0.1', PORT))

    pkt = {'type': 'connect', 'username': username}
    print('[CLIENT SEND]', pkt)
    sock.sendall((json.dumps(pkt) + '\n').encode('utf-8'))

    buf = ''
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk.decode('utf-8')
        while '\n' in buf:
            line, buf = buf.split('\n', 1)
            if not line.strip():
                continue
            print('[CLIENT RECEIVE]', line)
            msg = json.loads(line)
            if msg.get('type') == 'accept':
                return sock, int(msg['id']), buf
            if msg.get('type') == 'error':
                raise ConnectionError(f"Server rejected handshake: {msg.get('message')}")

    raise RuntimeError('Timed out waiting for accept packet')


def _drain(sock, seconds=1.5):
    """Read all available messages for `seconds`, return list of dicts."""
    sock.settimeout(0.2)
    buf = ''
    messages = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk.decode('utf-8')
        while '\n' in buf:
            line, buf = buf.split('\n', 1)
            if line.strip():
                print('[CLIENT RECEIVE]', line)
                messages.append(json.loads(line))
    return messages


def _send(sock, message):
    print('[CLIENT SEND]', message)
    sock.sendall((json.dumps(message) + '\n').encode('utf-8'))


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

def main():
    errors = []

    server = GameServer(host='0.0.0.0', port=PORT)
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    time.sleep(0.4)  # give the server a moment to bind

    listener_sock = None
    sender_sock = None
    try:
        # 1. Both clients perform handshake
        listener_sock, listener_id, _ = _connect_and_handshake('Listener')
        sender_sock, sender_id, _ = _connect_and_handshake('Sender')
        print(f'\n[TEST] listener_id={listener_id}, sender_id={sender_id}')

        # Consume any player_joined notifications
        _drain(listener_sock, seconds=0.5)

        # 2. Sender sends a player_update
        update = {
            'type': 'player_update',
            'id': sender_id,
            'x': 42.0,
            'y': 99.0,
            'z': 0.0,
            'state': 'moving',
            'username': 'Sender',
        }
        _send(sender_sock, update)

        # 3. Listener should receive the forwarded player_update
        forwarded = _drain(listener_sock, seconds=1.5)
        pu = next(
            (m for m in forwarded
             if m.get('type') == 'player_update' and m.get('id') == sender_id),
            None
        )
        if pu is None:
            errors.append('FAIL: listener did not receive forwarded player_update')
        else:
            if abs(pu.get('x', 0) - 42.0) > 0.001:
                errors.append(f"FAIL: player_update x mismatch – expected 42.0 got {pu.get('x')}")
            else:
                print('[TEST PASS] player_update forwarded correctly')

        # 4. Ping / pong
        _send(sender_sock, {'type': 'ping', 'id': sender_id})
        pong_msgs = _drain(sender_sock, seconds=1.0)
        if not any(m.get('type') == 'pong' for m in pong_msgs):
            errors.append('FAIL: sender did not receive pong')
        else:
            print('[TEST PASS] pong received')

        # 5. Chat broadcast
        _send(sender_sock, {'type': 'chat', 'id': sender_id, 'message': 'hello'})
        chat_msgs = _drain(listener_sock, seconds=1.0)
        if not any(m.get('type') == 'chat' and 'hello' in m.get('message', '') for m in chat_msgs):
            errors.append('FAIL: listener did not receive chat broadcast')
        else:
            print('[TEST PASS] chat broadcast received')

    except Exception as exc:
        errors.append(f'EXCEPTION: {exc}')
    finally:
        for sock in (listener_sock, sender_sock):
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        server.stop()  # use public API; server.running = False would silently create a new attr
        time.sleep(0.5)

    if errors:
        print('\n[TEST RESULTS] FAILED:')
        for err in errors:
            print(' ', err)
        sys.exit(1)
    else:
        print('\n[TEST RESULTS] ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
