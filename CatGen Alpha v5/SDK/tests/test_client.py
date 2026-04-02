"""Integration test: connect to local server and send move_input packets.

Expects a GameServer to already be running on 127.0.0.1:25565.
Run test_start_host.py first in a separate process.
"""
import socket, json, time

PORT = 25565
PASSED = []
FAILED = []

def check(label, condition):
    if condition:
        PASSED.append(label)
        print(f'  [PASS] {label}')
    else:
        FAILED.append(label)
        print(f'  [FAIL] {label}')

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(('127.0.0.1', PORT))
    print('[TEST] Connected to server')

    # --- handshake ---
    connect_pkt = {'type': 'connect', 'username': 'TestClient', 'password': ''}
    s.sendall((json.dumps(connect_pkt) + '\n').encode('utf-8'))
    print('[TEST] Sent connect packet')

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
                print('[CLIENT RECEIVE]', line)
                try:
                    msg = json.loads(line)
                    if msg.get('type') == 'accept':
                        accepted = msg
                except json.JSONDecodeError:
                    pass
        if accepted:
            break

    check('Received accept packet', accepted is not None)
    if not accepted:
        raise RuntimeError('No accept packet received')

    client_id = accepted.get('id')
    check('Accept contains id', client_id is not None)
    print(f'[TEST] Got client id={client_id}')

    # --- send move_input (new protocol: clients only send input, not position) ---
    move_pkt = {
        'type': 'move_input',
        'up': True, 'down': False, 'left': False, 'right': False,
        'sprint': False, 'jump': False,
        'dash_charge': False, 'dash_release': False,
    }
    s.sendall((json.dumps(move_pkt) + '\n').encode('utf-8'))
    print('[TEST] Sent move_input packet')
    time.sleep(0.3)

    # --- send chat ---
    chat_pkt = {'type': 'chat', 'message': 'hello from test'}
    s.sendall((json.dumps(chat_pkt) + '\n').encode('utf-8'))
    print('[TEST] Sent chat packet')
    time.sleep(0.3)

    # --- read player_update broadcast ---
    s.settimeout(2)
    got_update = False
    try:
        more = s.recv(4096).decode('utf-8')
        for line in more.split('\n'):
            if line.strip():
                print('[CLIENT RECEIVE]', line)
                try:
                    m = json.loads(line)
                    if m.get('type') == 'player_update':
                        got_update = True
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    check('Received player_update broadcast', got_update)

except Exception as e:
    print('[TEST ERROR]', e)
    FAILED.append(str(e))
finally:
    try:
        s.close()
    except Exception:
        pass
    print()
    print(f'[TEST RESULTS] {len(PASSED)} passed, {len(FAILED)} failed')
    if FAILED:
        print('[FAILED CHECKS]', FAILED)
    else:
        print('[TEST RESULTS] ALL CHECKS PASSED')

