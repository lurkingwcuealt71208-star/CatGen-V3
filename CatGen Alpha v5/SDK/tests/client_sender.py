"""Multi-client test helper: Sender.

Connects to a running server, sends move_input packets, then chat.
Run alongside client_listener.py to verify broadcast delivery.
"""
import socket, json, time

PORT = 25565
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(('127.0.0.1', PORT))
    print('[SENDER] Connected to server')

    # --- handshake ---
    connect_pkt = {'type': 'connect', 'username': 'Sender', 'password': ''}
    s.sendall((json.dumps(connect_pkt) + '\n').encode('utf-8'))

    buf = ''
    accepted = None
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            chunk = s.recv(4096).decode('utf-8')
            buf += chunk
        except socket.timeout:
            break
        while '\n' in buf:
            line, buf = buf.split('\n', 1)
            if line.strip():
                print('[SENDER RECV]', line)
                try:
                    msg = json.loads(line)
                    if msg.get('type') == 'accept':
                        accepted = msg
                except json.JSONDecodeError:
                    pass
        if accepted:
            break

    if not accepted:
        raise RuntimeError('No accept packet received')
    print(f'[SENDER] Got client id={accepted.get("id")}')

    # --- send 5 move_input packets (new protocol: input only, no position) ---
    time.sleep(0.3)
    directions = [
        {'up': True,  'right': False},
        {'up': False, 'right': True},
        {'up': True,  'right': True},
        {'up': False, 'right': False, 'sprint': True},
        {'up': False, 'right': False},
    ]
    for i, d in enumerate(directions):
        pkt = {
            'type': 'move_input',
            'up': d.get('up', False), 'down': False,
            'left': False, 'right': d.get('right', False),
            'sprint': d.get('sprint', False), 'jump': False,
            'dash_charge': False, 'dash_release': False,
        }
        print(f'[SENDER] Sending move_input {i+1}/5:', pkt)
        s.sendall((json.dumps(pkt) + '\n').encode('utf-8'))
        time.sleep(0.5)

    # --- send a chat message ---
    chat_pkt = {'type': 'chat', 'message': 'Hello from Sender!'}
    s.sendall((json.dumps(chat_pkt) + '\n').encode('utf-8'))
    print('[SENDER] Sent chat message')
    time.sleep(1)

except Exception as e:
    print('[SENDER ERROR]', e)
finally:
    try:
        s.close()
    except Exception:
        pass
    print('[SENDER] Finished')

