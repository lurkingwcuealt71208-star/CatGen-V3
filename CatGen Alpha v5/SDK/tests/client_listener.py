"""Passive test helper: Listener.

Connects to a running server and prints all packets it receives for 10 seconds.
Run alongside client_sender.py to verify broadcast delivery.
"""
import socket, json, time

PORT = 25565
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(('127.0.0.1', PORT))
    print('[LISTENER] Connected to server')

    # --- handshake ---
    connect_pkt = {'type': 'connect', 'username': 'Listener', 'password': ''}
    s.sendall((json.dumps(connect_pkt) + '\n').encode('utf-8'))

    # --- read all server messages for 10 seconds ---
    buffer = ''
    start = time.time()
    s.settimeout(1)
    while time.time() - start < 10:
        try:
            data = s.recv(4096).decode('utf-8')
            if not data:
                break
            buffer += data
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line.strip():
                    print('[CLIENT RECEIVE]', line)
        except socket.timeout:
            pass
    print('[LISTENER] Done')

except Exception as e:
    print('[LISTENER ERROR]', e)
finally:
    try:
        s.close()
    except Exception:
        pass
