import asyncio
import json
import os
import hashlib
import string
import http.server
import threading
import time
from datetime import datetime
import logging
import websockets

from voice_recog import VoiceRecog, bcolors
from hardware import HardwareManager, PunishmentType
from web_server import ClientHTTPServer

logger = logging.getLogger("Client")

class ShockerClient(HardwareManager):
    def __init__(self, config: dict, config_path: str):
        # Initialize the hardware manager parent class
        super().__init__()
        
        self.config = config
        self.config_path = config_path
        
        self.player_name = config["player_name"].strip()
        self.api_type = config.get("api_type", "openshock").lower()
        self.openshock_token = config["openshock_token"]
        self.shocker_id = config["shocker_id"]
        
        self.websocket = None
        self.loop = None
        self.server_url = ""
        self.forbidden_words = []
        self.players_in_lobby = []
        self.logs = []
        self.session_shocks = 0
        self.secret_words_count = 0
        self.max_words_per_player = 3
        self.word_add_cooldown_seconds = 60.0
        self.voice_started = False
        self.running = True

        # Anti-Cheat & Telemetry
        self.secret_hashes = []
        self.total_phrases_spoken = 0
        self.client_sha1 = ""
        self.voice_recog_sha1 = ""
        self.calculate_integrity_hashes()

        # Initialize OpenShock Client
        if self.api_type == "openshock":
            self.init_openshock()

    def calculate_integrity_hashes(self):
        try:
            # Hash files dynamically relative to the execution module path
            dir_path = os.path.dirname(__file__)
            client_path = os.path.join(dir_path, "client.py")
            shocker_client_path = os.path.join(dir_path, "shocker_client.py")
            hardware_path = os.path.join(dir_path, "hardware.py")
            web_server_path = os.path.join(dir_path, "web_server.py")
            config_handler_path = os.path.join(dir_path, "config_handler.py")
            voice_path = os.path.join(dir_path, "voice_recog.py")
            
            # Combine hashes of all modules to enforce version matching
            hashes = [
                self._get_file_sha1(client_path),
                self._get_file_sha1(shocker_client_path),
                self._get_file_sha1(hardware_path),
                self._get_file_sha1(web_server_path),
                self._get_file_sha1(config_handler_path)
            ]
            self.client_sha1 = hashlib.sha1("".join(hashes).encode()).hexdigest()
            self.voice_recog_sha1 = self._get_file_sha1(voice_path)
        except Exception as e:
            logger.error(f"Failed to calculate integrity hashes: {e}")
            
    def _get_file_sha1(self, path):
        if not os.path.exists(path):
            return ""
        sha1 = hashlib.sha1()
        with open(path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha1.update(data)
        return sha1.hexdigest()

    def add_log(self, log_type: str, message: str):
        """Append log item to list for display in Web UI."""
        t = datetime.now().strftime("%H:%M:%S")
        self.logs.append({"time": t, "type": log_type, "message": message})
        if len(self.logs) > 200:
            self.logs.pop(0)

    async def connect_and_run(self):
        self.loop = asyncio.get_running_loop()
        
        # Start background Web UI HTTP server thread
        ClientHTTPServer.client_instance = self
        self.web_port = 5000
        def run_web_server():
            port = 5000
            while True:
                try:
                    server = http.server.HTTPServer(("0.0.0.0", port), ClientHTTPServer)
                    print(f"{bcolors.OKGREEN}Client Web UI running at http://localhost:{port}{bcolors.ENDC}")
                    self.web_port = port
                    server.serve_forever()
                    break
                except OSError:
                    port += 1
                except Exception as e:
                    print(f"{bcolors.FAIL}Failed to start local Web UI server: {e}{bcolors.ENDC}")
                    break
                
        threading.Thread(target=run_web_server, daemon=True).start()

        # Open the dashboard URL in the default browser automatically
        try:
            import webbrowser
            time.sleep(0.3) # Wait briefly for web server thread binding
            webbrowser.open(f"http://localhost:{self.web_port}")
        except Exception as e:
            logger.error(f"Failed to open browser automatically: {e}")

        # Connect loop (handles disconnects and IP setting updates dynamically)
        while self.running:
            server_ip = self.config.get('server_ip', 'localhost').strip()
            
            # Remove protocol prefixes if pasted
            is_secure = False
            if server_ip.startswith("https://"):
                server_ip = server_ip[8:]
                is_secure = True
            elif server_ip.startswith("http://"):
                server_ip = server_ip[7:]
                is_secure = False
            elif server_ip.startswith("wss://"):
                server_ip = server_ip[6:]
                is_secure = True
            elif server_ip.startswith("ws://"):
                server_ip = server_ip[5:]
                is_secure = False
            else:
                # Default logic: secure if ngrok-free.dev is used
                is_secure = "ngrok-free.dev" in server_ip

            extra_headers = {}
            if "ngrok-free.dev" in server_ip:
                # Ngrok free HTTP tunnels require this header to bypass browser warning pages
                extra_headers["ngrok-skip-browser-warning"] = "true"
                self.server_url = f"wss://{server_ip}" if is_secure else f"ws://{server_ip}"
            else:
                if ":" in server_ip:
                    self.server_url = f"wss://{server_ip}" if is_secure else f"ws://{server_ip}"
                else:
                    self.server_url = f"ws://{server_ip}:8765"
                    
            self.add_log("server", f"Connecting to game server at {self.server_url}...")
            print(f"{bcolors.OKCYAN}Connecting to Shocker Roulette Server at {self.server_url}...{bcolors.ENDC}")
            
            try:
                async with websockets.connect(self.server_url, extra_headers=extra_headers) as ws:
                    self.websocket = ws
                    
                    # Register player name and include integrity check hashes
                    register_msg = {
                        "action": "register",
                        "name": self.player_name,
                        "client_sha1": self.client_sha1,
                        "voice_recog_sha1": self.voice_recog_sha1
                    }
                    await ws.send(json.dumps(register_msg))
                    self.add_log("server", f"Lobby registration request sent for player '{self.player_name}'")
                    
                    # Start heartbeat loop as a background task
                    heartbeat_task = asyncio.create_task(self.run_heartbeat_loop())
                    
                    # Run receiving loop
                    await self.receive_loop()
                    
                    # Cancel heartbeat task on disconnect
                    heartbeat_task.cancel()
            except Exception as e:
                self.add_log("server", f"Connection failed: {e}")
                print(f"\n{bcolors.FAIL}Connection failed: {e}{bcolors.ENDC}")
                
            # Disconnected, clean up state
            self.websocket = None
            self.players_in_lobby = []
            
            if self.running:
                self.add_log("server", "Disconnected. Reconnecting in 5 seconds...")
                print(f"{bcolors.WARNING}Reconnecting in 5 seconds...{bcolors.ENDC}")
                await asyncio.sleep(5)

    async def receive_loop(self):
        """Listen for events from the server."""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                event = data.get("event")

                if event == "welcome":
                    self.forbidden_words = data.get("forbidden_words", [])
                    self.secret_hashes = data.get("secret_hashes", [])
                    self.secret_words_count = len(self.secret_hashes)
                    self.max_words_per_player = data.get("max_words_per_player", 3)
                    self.word_add_cooldown_seconds = data.get("word_add_cooldown_seconds", 60.0)
                    self.add_log("server", f"Joined lobby. Forbidden words synced: {', '.join(self.forbidden_words)}")
                    print(f"\n{bcolors.OKGREEN}Successfully registered in lobby as '{self.player_name}'!{bcolors.ENDC}")
                    print(f"{bcolors.BOLD}API Mode:{bcolors.ENDC} {self.api_type.upper()}")
                    print(f"{bcolors.BOLD}Active forbidden words:{bcolors.ENDC} {', '.join(self.forbidden_words)}")
                    print(f"{bcolors.BOLD}Active secret words count:{bcolors.ENDC} {self.secret_words_count}")
                    print(f"{bcolors.OKBLUE}Microphone is active. Speak freely, but watch your words!{bcolors.ENDC}\n")
                    
                    # Initialize local speech recognition once registered
                    if not self.voice_started:
                        VoiceRecog.init_voice_recog(
                            on_text_callback=self.on_speech_finalized,
                            num_threads=2
                        )
                        self.voice_started = True

                elif event == "player_joined":
                    name = data.get("name")
                    self.players_in_lobby = data.get("players", [])
                    self.add_log("server", f"Player '{name}' joined the lobby.")
                    print(f"\n{bcolors.OKBLUE}👋 {name} joined the game!{bcolors.ENDC}")
                    print(f"Current players: {', '.join(self.players_in_lobby)}")

                elif event == "player_left":
                    name = data.get("name")
                    self.players_in_lobby = data.get("players", [])
                    self.add_log("server", f"Player '{name}' left the lobby.")
                    print(f"\n{bcolors.WARNING}🚪 {name} left the game.{bcolors.ENDC}")
                    print(f"Current players: {', '.join(self.players_in_lobby)}")

                elif event == "words_updated":
                    self.forbidden_words = data.get("forbidden_words", [])
                    self.secret_hashes = data.get("secret_hashes", [])
                    self.secret_words_count = len(self.secret_hashes)
                    msg = data.get("message", "Forbidden words list updated.")
                    self.add_log("server", msg)
                    print(f"\n{bcolors.OKGREEN}🆕 {msg}{bcolors.ENDC}")
                    print(f"Active forbidden words: {', '.join(self.forbidden_words)}")
                    print(f"Active secret words count: {self.secret_words_count}")

                elif event == "punish":
                    speaker = data.get("speaker")
                    word = data.get("word")
                    raw_punishment = data.get("punishment_type", "shock")
                    try:
                        punishment_type = PunishmentType(raw_punishment.lower())
                    except ValueError:
                        punishment_type = PunishmentType.SHOCK
                        
                    intensity = data.get("intensity", 10)
                    duration_ms = data.get("duration_ms", 1000)
                    immune_list = data.get("immune_players", [])
                    
                    if any(self.player_name.lower() == imp.lower() for imp in immune_list):
                        self.add_log("server", f"Trigger ignored: you are immune to '{word}'.")
                        print(f"\n{bcolors.OKGREEN}🛡️ You are immune to '{word}'! Shock blocked.{bcolors.ENDC}")
                        continue

                    self.add_log("punish", f"PUNISHMENT: {speaker} said '{word}'! Triggering {punishment_type.value.upper()} on collar.")
                    self.execute_punishment(speaker, word, punishment_type, intensity, duration_ms)

                elif event == "roulette":
                    ticking_sequence = data.get("ticking_sequence", [])
                    victim = data.get("victim")
                    tick_delay_ms = data.get("tick_delay_ms", 350)
                    vibrate_intensity = data.get("vibrate_intensity", 15)
                    shock_intensity = data.get("shock_intensity", 20)
                    duration_ms = data.get("duration_ms", 1000)
                    
                    self.add_log("server", f"ROULETTE TRIGGERED! Victim selected: {victim}")
                    print(f"\n{bcolors.WARNING}🎯 ROULETTE TRIGGERED! Spinning the wheel...{bcolors.ENDC}")
                    
                    asyncio.create_task(self.run_roulette_sequence(
                        ticking_sequence, victim, tick_delay_ms, 
                        vibrate_intensity, shock_intensity, duration_ms
                    ))

                elif event == "error":
                    print(f"\n{bcolors.FAIL}❌ Error from server: {data.get('message')}{bcolors.ENDC}")
                    break

        except websockets.exceptions.ConnectionClosed:
            self.add_log("server", "Connection closed by remote server.")
            print(f"\n{bcolors.WARNING}Disconnected from game server.{bcolors.ENDC}")

    async def run_roulette_sequence(self, sequence, victim, delay_ms, vibrate_intensity, shock_intensity, duration_ms):
        """Simulate the physical ticking roulette by vibrating player collars sequentially, then shocking the victim."""
        for player in sequence:
            if not self.running:
                return
            
            if player.lower() == self.player_name.lower():
                print(f"{bcolors.FAIL}➔ [{player}]{bcolors.ENDC}", end=" ", flush=True)
                self.execute_test_command("vibrate", vibrate_intensity, 300)
            else:
                print(f"➔ {player}", end=" ", flush=True)
                
            await asyncio.sleep(delay_ms / 1000.0)
            
        print(f"\n{bcolors.HEADER}⚡ BOOM! Victim is {victim}!{bcolors.ENDC}")
        if victim == self.player_name:
            self.add_log("punish", f"ROULETTE PUNISHMENT: You were selected as the victim!")
            self.execute_punishment(victim, "Roulette", PunishmentType.SHOCK, shock_intensity, duration_ms)

    def update_config(self, new_config: dict):
        """Update configurations via Web UI dynamically."""
        old_server_ip = self.config.get("server_ip")
        
        self.config.update(new_config)
        
        # Save to file
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            
        self.player_name = self.config["player_name"].strip()
        self.api_type = self.config.get("api_type", "openshock").lower()
        self.openshock_token = self.config["openshock_token"]
        self.shocker_id = self.config["shocker_id"]

        # Re-initialize OpenShock
        if self.api_type == "openshock":
            self.init_openshock()
        else:
            self.openshock_client = None

        self.add_log("server", "Settings updated via Web Dashboard.")
        
        # Force a socket disconnect/reconnect if host address changed
        new_server_ip = new_config.get("server_ip")
        if new_server_ip and new_server_ip != old_server_ip and self.websocket:
            self.add_log("server", f"Server IP changed to {new_server_ip}. Reconnecting...")
            asyncio.run_coroutine_threadsafe(self.close_websocket(), self.loop)

    async def close_websocket(self):
        if self.websocket:
            await self.websocket.close()

    def on_speech_finalized(self, text: str):
        """Called by the background VoiceRecog thread when speech is finalized."""
        if not self.running or not self.loop:
            return
        
        self.add_log("speech", f"Transcribed: \"{text}\"")
        asyncio.run_coroutine_threadsafe(self.process_transcribed_text(text), self.loop)

    async def process_transcribed_text(self, text: str):
        """Evaluate speech locally. Only send triggers when public words or secret hashes match."""
        text_lower = text.lower()
        self.total_phrases_spoken += 1
        
        # 1. Check public forbidden words
        matched_public = None
        for word in self.forbidden_words:
            if word in text_lower:
                matched_public = word
                break
                
        if matched_public:
            print(f"\n{bcolors.WARNING}⚠️ You spoke the public forbidden word '{matched_public}'!{bcolors.ENDC}")
            if self.websocket and not self.websocket.closed:
                try:
                    await self.websocket.send(json.dumps({
                        "action": "trigger",
                        "word": matched_public
                    }))
                except Exception as e:
                    print(f"Failed to send public trigger: {e}")
            return

        # 2. Check secret words (via SHA-256 hashes locally)
        translator = str.maketrans('', '', string.punctuation)
        clean_text = text.translate(translator).lower()
        words = clean_text.split()
        
        # Generate n-grams and check against secret_hashes
        n = len(words)
        matched_secret_hash = None
        
        for length in range(1, min(5, n + 1)):
            if matched_secret_hash:
                break
            for i in range(n - length + 1):
                phrase = " ".join(words[i:i+length])
                phrase_hash = hashlib.sha256(phrase.encode('utf-8')).hexdigest()
                if phrase_hash in self.secret_hashes:
                    matched_secret_hash = phrase_hash
                    break
                    
        if matched_secret_hash:
            print(f"\n{bcolors.WARNING}⚠️ Triggered a secret word trap!{bcolors.ENDC}")
            if self.websocket and not self.websocket.closed:
                try:
                    await self.websocket.send(json.dumps({
                        "action": "trigger",
                        "hash": matched_secret_hash
                    }))
                except Exception as e:
                    print(f"Failed to send secret trigger: {e}")

    async def run_heartbeat_loop(self):
        """Sends periodic telemetry status heartbeats to the server for anti-cheat audit."""
        while self.running and self.websocket and not self.websocket.closed:
            try:
                payload = {
                    "action": "heartbeat",
                    "phrases_spoken": self.total_phrases_spoken,
                    "mic_active": self.voice_started
                }
                await self.websocket.send(json.dumps(payload))
            except Exception:
                pass
            await asyncio.sleep(10)
