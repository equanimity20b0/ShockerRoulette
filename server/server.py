import asyncio
import json
import os
import time
import logging
import websockets
import hashlib
import string

from http_handler import HttpHandler
from game_loop import GameLoop

# Setup logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GameServer")
logging.getLogger("websockets").setLevel(logging.WARNING)

class ShockerServer:
    def __init__(self, game_mode_class=GameLoop):
        # Track active client websocket connections {player_name: websocket}
        self.clients = {}
        # Spectator client websockets
        self.spectator_clients = set()
        # Telemetry tracker for anti-cheat verification {player_name: {"phrases_spoken": int, "mic_active": bool, "last_active": float}}
        self.client_telemetry = {}
        # Reference client file checksums for anti-cheat verification
        self.ref_client_sha1 = ""
        self.ref_voice_recog_sha1 = ""
        
        # Instantiate active game mode engine
        self.game_mode = game_mode_class(server=self)

    def get_players_state(self):
        '''
        Gather all known player states for other players, mic_active is important to know when other players 
        are not setup correctly, or disabled their mic for some reason.
        '''
        players_state = []
        for name in self.clients.keys():
            telemetry = self.client_telemetry.get(name, {})
            players_state.append({
                "name": name,
                "mic_active": telemetry.get("mic_active", False),
                "phrases_spoken": telemetry.get("phrases_spoken", 0)
            })
        return players_state

    async def process_request(self, *args, **kwargs):
        return await HttpHandler.process_request(self, *args, **kwargs)

    async def broadcast(self, payload):
        '''
        Notify all players and spectators of message.
        '''
        if not self.clients and not self.spectator_clients:
            return
        
        message = json.dumps(payload)
        targets = list(self.clients.values()) + list(self.spectator_clients)
        await asyncio.gather(*[ws.send(message) for ws in targets if not ws.closed], return_exceptions=True)

    async def broadcast_except(self, websocket, payload):
        message = json.dumps(payload)
        targets = [ws for ws in list(self.clients.values()) + list(self.spectator_clients) if ws != websocket and not ws.closed]
        if targets:
            await asyncio.gather(*[ws.send(message) for ws in targets], return_exceptions=True)

    # Action Handlers Map functions
    async def handle_register(self, websocket, data):
        is_spectator = (data.get("type") == "spectator")

        if is_spectator:
            self.spectator_clients.add(websocket)
            logger.info(f"Spectator joined from {websocket.remote_address}")
            
            welcome_payload = await self.game_mode.get_spectator_welcome_payload()
            await websocket.send(json.dumps(welcome_payload))
            return None
        else:
            player_name = data.get("name", "").strip()
        
            if not player_name:
                await websocket.send(json.dumps({
                    "event": "error",
                    "message": "Registration failed: Player name is required."
                }))
                return None
                
            if player_name in self.clients:
                await websocket.send(json.dumps({
                    "event": "error",
                    "message": f"Registration failed: Name '{player_name}' is already taken."
                }))
                return None

            # Register connection
            self.clients[player_name] = websocket
            self.client_telemetry[player_name] = {
                "phrases_spoken": 0,
                "mic_active": False,
                "last_active": time.time()
            }
            logger.info(f"Player '{player_name}' joined from {websocket.remote_address}")
            
            welcome_payload = await self.game_mode.get_welcome_payload(player_name)
            await websocket.send(json.dumps(welcome_payload))
            
            await self.broadcast({
                "event": "player_joined",
                "name": player_name,
                "players": self.get_players_state()
            })

            await self.game_mode.on_player_joined(player_name)
            return player_name

    async def handle_heartbeat(self, websocket, data, player_name):
        if not player_name:
            return
        phrases = data.get("phrases_spoken", 0)
        mic_active = data.get("mic_active", False)
        
        old_telemetry = self.client_telemetry.get(player_name, {})
        old_mic = old_telemetry.get("mic_active", False)
        
        self.client_telemetry[player_name] = {
            "phrases_spoken": phrases,
            "mic_active": mic_active,
            "last_active": time.time()
        }
        
        if old_mic != mic_active:
            await self.broadcast({
                "event": "telemetry_update",
                "players": self.get_players_state()
            })

    async def handle_client(self, websocket, path):
        player_name = None

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue

                action = data.get("action")

                if action == "register":
                    reg_name = await self.handle_register(websocket, data)
                    if reg_name:
                        player_name = reg_name
                elif action == "heartbeat":
                    await self.handle_heartbeat(websocket, data, player_name)
                else:
                    # Delegate game mode specific actions to active game engine
                    handled = await self.game_mode.handle_action(websocket, action, data, player_name)
                    if not handled:
                        logger.warning(f"Unhandled action '{action}' from {player_name or 'spectator'}")

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection closed for {player_name or 'unregistered client'}")
        finally:
            if websocket in self.spectator_clients:
                self.spectator_clients.remove(websocket)
                logger.info("Spectator disconnected.")
            elif player_name and player_name in self.clients:
                del self.clients[player_name]
                await self.game_mode.on_player_left(player_name)
                await self.broadcast({
                    "event": "player_left",
                    "name": player_name,
                    "players": self.get_players_state()
                })

    async def run(self):
        server = await websockets.serve(self.handle_client, "0.0.0.0", 8765, process_request=self.process_request)
        logger.info("Shocker Roulette Server running on ws://0.0.0.0:8765 (and HTTP on http://0.0.0.0:8765)")
        await server.wait_closed()

def download_transformers_local():
    web_dir = os.path.join(os.path.dirname(__file__), "web")
    local_path = os.path.join(web_dir, "transformers.min.js")
    if not os.path.exists(local_path):
        logger.info("Local transformers.min.js not found. Downloading bootstrap file...")
        try:
            import urllib.request
            url = "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.16.0/dist/transformers.min.js"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                content = response.read()
            os.makedirs(web_dir, exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(content)
            logger.info("Local transformers.min.js downloaded successfully!")
        except Exception as e:
            logger.error(f"Failed to download local transformers.min.js: {e}")

if __name__ == "__main__":
    download_transformers_local()
    server_instance = ShockerServer()
    try:
        asyncio.run(server_instance.run())
    except KeyboardInterrupt:
        logger.info("Server stopped manually.")
    finally:
        server_instance.game_mode.on_exit()
