"""Test: start and stop the LAN server + broadcaster via network modules."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

# Minimal pygame stub so network modules that import pygame constants still load
try:
    import pygame
    pygame.init()
except Exception:
    pass

from network.server import GameServer
from network.lan import LanBroadcaster

server = GameServer(port=25565, password='')
server.start()
print('[TEST HOST] GameServer started on port 25565')

broadcaster = LanBroadcaster(port=25565, name='TestServer')
broadcaster.start()
print('[TEST HOST] LanBroadcaster started')

time.sleep(3)

try:
    server.stop()
    print('[TEST HOST] GameServer stopped')
except Exception as e:
    print('[TEST HOST ERROR]', e)

try:
    broadcaster.stop()
    print('[TEST HOST] Broadcaster stopped')
except Exception as e:
    print('[TEST HOST ERROR]', e)

