import asyncio
import json
import os
import time
import logging
import websockets
import hashlib
import string
from enum import Enum

class PunishmentType(str, Enum):
    SHOCK = "shock"
    VIBRATE = "vibrate"
    SOUND = "sound"

# Setup logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GameServer")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_CONFIG = {
    "forbidden_words": ["apple", "banana", "shock", "roulette"],
    "secret_words": [],        # Stored as [{"hash": "...", "word": "...", "creator": "..."}]
    "punishment_type": PunishmentType.SHOCK.value, # can be shock, vibrate, sound
    "intensity": 10,           # default intensity (1-100)
    "intensity_variance": 3,   # random variance added/subtracted (e.g. ±3)
    "duration_ms": 1000,       # default duration in milliseconds
    "cooldown_seconds": 3.0,   # cooldown between punishments
    "max_words_per_player": 3, # limit on added words
    "word_add_cooldown_seconds": 60.0, # cooldown to add more words
    "creator_immunity_on_secret": True, # creator is immune to their secret words before public migration
    "word_max_triggers": 3,     # number of times a public word triggers before roulette starts
    "roulette_rounds": 6,       # number of rounds the roulette cycles before landing on the victim
    "roulette_start_intensity": 10,       # starting intensity for roulette shocks
    "roulette_max_intensity": 50,         # maximum intensity for roulette shocks
    "roulette_intensity_increment": 5,   # intensity increment per roulette event
    "roulette_current_intensity": 10,     # tracks the current active roulette stakes
    "spectator_max_tokens": 5,            # max spectator tokens pool
    "spectator_token_recharge_seconds": 60, # token recharge rate in seconds
    "spectator_words": []                 # spectator-added secret words list
}

class ShockerServer:
    def __init__(self):
        # Track active client websocket connections {player_name: websocket}
        self.clients = {}
        # Cooldown management
        self.last_trigger_time = 0.0
        # Player added words timestamps {player_name: [list of timestamps]}
        self.player_word_timestamps = {}
        # Hashed banned words lookup registry {hash_string: plain_word or dict_entry}
        self.hashed_words = {}
        # Track public word trigger counts {word_string: count}
        self.public_trigger_counts = {}
        # Telemetry tracker for anti-cheat verification {player_name: {"phrases_spoken": int, "mic_active": bool, "last_active": float}}
        self.client_telemetry = {}
        # Reference client file checksums for anti-cheat verification
        self.ref_client_sha1 = ""
        self.ref_voice_recog_sha1 = ""
        
        # Spectator Mode variables
        self.spectator_clients = set()
        self.spectator_tokens = 5
        self.last_token_recharge_time = time.time()
        
        self.load_config()
        self.calculate_reference_hashes()

    def calculate_reference_hashes(self):
        try:
            dir_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "client")
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
            self.ref_client_sha1 = hashlib.sha1("".join(hashes).encode()).hexdigest()
            self.ref_voice_recog_sha1 = self._get_file_sha1(voice_path)
            
            if self.ref_client_sha1:
                logger.info(f"Anti-Cheat loaded. Combined reference client SHA-1: {self.ref_client_sha1[:8]}...")
            if self.ref_voice_recog_sha1:
                logger.info(f"Anti-Cheat loaded. Reference voice_recog.py SHA-1: {self.ref_voice_recog_sha1[:8]}...")
        except Exception as e:
            logger.error(f"Failed to calculate reference hashes: {e}")

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

    def recharge_spectator_tokens(self):
        now = time.time()
        elapsed = now - self.last_token_recharge_time
        recharge_rate = self.config.get("spectator_token_recharge_seconds", 60)
        max_tokens = self.config.get("spectator_max_tokens", 5)
        
        if elapsed >= recharge_rate:
            recharged = int(elapsed // recharge_rate)
            self.spectator_tokens = min(max_tokens, self.spectator_tokens + recharged)
            self.last_token_recharge_time += recharged * recharge_rate

    def get_spectator_status(self):
        self.recharge_spectator_tokens()
        now = time.time()
        time_to_next_recharge = max(0.0, self.config.get("spectator_token_recharge_seconds", 60) - (now - self.last_token_recharge_time))
        recharge_seconds_left = int(time_to_next_recharge)
        
        max_tokens = self.config.get("spectator_max_tokens", 5)
        # Safeguard: if tokens are not full and recharge seconds left rounds to 0, force 1s to allow timer advancement and prevent infinite fast pings
        if self.spectator_tokens < max_tokens and recharge_seconds_left <= 0:
            recharge_seconds_left = 1
            
        return {
            "spectator_tokens": self.spectator_tokens,
            "spectator_max_tokens": max_tokens,
            "recharge_seconds_left": recharge_seconds_left
        }

    def get_combined_secret_hashes(self):
        return (
            [entry["hash"] for entry in self.config.get("secret_words", []) if isinstance(entry, dict) and "hash" in entry] +
            [entry["hash"] for entry in self.config.get("spectator_words", []) if isinstance(entry, dict) and "hash" in entry]
        )

    async def process_request(self, path, headers):
        # 1. Detect if it's a WebSocket upgrade request
        upgrade_header = headers.get("Upgrade", "").lower()
        if "websocket" in upgrade_header:
            return None # Allow standard WebSocket upgrade handshake
            
        # 2. Extract path
        import urllib.parse
        import http
        url_parsed = urllib.parse.urlparse(path)
        request_path = url_parsed.path
        
        # 3. Serve root / index.html page
        if request_path in ("/", "/index.html"):
            web_dir = os.path.join(os.path.dirname(__file__), "web")
            index_path = os.path.join(web_dir, "index.html")
            if os.path.exists(index_path):
                try:
                    with open(index_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    response_headers = [
                        ('Content-Type', 'text/html; charset=utf-8'),
                        ('Content-Length', str(len(content.encode('utf-8')))),
                        ('Connection', 'close')
                    ]
                    return http.HTTPStatus.OK, response_headers, content.encode('utf-8')
                except Exception as e:
                    logger.error(f"Error serving spectator index.html: {e}")
                    return http.HTTPStatus.INTERNAL_SERVER_ERROR, [], b"Internal Server Error"
            else:
                return http.HTTPStatus.NOT_FOUND, [], b"Not Found"
                
        return http.HTTPStatus.NOT_FOUND, [], b"Not Found"

    def load_config(self):
        self.config = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    file_config = json.load(f)
                    self.config.update(file_config)
                logger.info(f"Configuration loaded and merged from {CONFIG_PATH}")
            except Exception as e:
                logger.error(f"Error loading config.json, using defaults. Error: {e}")
        else:
            try:
                with open(CONFIG_PATH, "w") as f:
                    json.dump(self.config, f, indent=4)
                logger.info(f"Created default configuration file at {CONFIG_PATH}")
            except Exception as e:
                logger.error(f"Failed to create config.json: {e}")
        
        # Reset current roulette stakes to starting level at startup for a fresh session
        self.config["roulette_current_intensity"] = self.config.get("roulette_start_intensity", 10)
        self.update_hashed_words_lookup()

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f, indent=4)
            logger.info(f"Configuration saved to {CONFIG_PATH}")
        except Exception as e:
            logger.error(f"Failed to save config.json: {e}")

    def update_hashed_words_lookup(self):
        self.hashed_words = {}
        translator = str.maketrans('', '', string.punctuation)
        
        # Add public words (value is string)
        for word in self.config.get("forbidden_words", []):
            clean = word.translate(translator).lower().strip()
            if clean:
                h = hashlib.sha256(clean.encode('utf-8')).hexdigest()
                self.hashed_words[h] = word
                
        # Add player secret words (value is dictionary)
        for entry in self.config.get("secret_words", []):
            if isinstance(entry, dict) and "hash" in entry:
                self.hashed_words[entry["hash"]] = entry

        # Add spectator secret words (value is dictionary)
        for entry in self.config.get("spectator_words", []):
            if isinstance(entry, dict) and "hash" in entry:
                self.hashed_words[entry["hash"]] = entry

    async def broadcast(self, message_dict):
        """Broadcast a message to all connected player and spectator clients."""
        if not self.clients and not self.spectator_clients:
            return
        msg = message_dict.copy()
        msg["roulette_start_intensity"] = self.config.get("roulette_start_intensity", 10)
        msg["roulette_max_intensity"] = self.config.get("roulette_max_intensity", 50)
        msg["roulette_current_intensity"] = self.config.get("roulette_current_intensity", 10)
        
        # Append spectator token status
        status = self.get_spectator_status()
        msg.update(status)
        
        payload = json.dumps(msg)
        player_sends = [client.send(payload) for client in self.clients.values()]
        spectator_sends = [client.send(payload) for client in self.spectator_clients]
        await asyncio.gather(*(player_sends + spectator_sends), return_exceptions=True)

    async def broadcast_except(self, sender_ws, message_dict):
        """Broadcast a message to all connected clients except the sender."""
        if not self.clients and not self.spectator_clients:
            return
        msg = message_dict.copy()
        msg["roulette_start_intensity"] = self.config.get("roulette_start_intensity", 10)
        msg["roulette_max_intensity"] = self.config.get("roulette_max_intensity", 50)
        msg["roulette_current_intensity"] = self.config.get("roulette_current_intensity", 10)
        
        status = self.get_spectator_status()
        msg.update(status)
        
        payload = json.dumps(msg)
        player_sends = [client.send(payload) for client in self.clients.values() if client != sender_ws]
        spectator_sends = [client.send(payload) for client in self.spectator_clients if client != sender_ws]
        await asyncio.gather(*(player_sends + spectator_sends), return_exceptions=True)

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
                    is_spectator = (data.get("type") == "spectator")
                    if is_spectator:
                        self.spectator_clients.add(websocket)
                        logger.info(f"Spectator joined from {websocket.remote_address}")
                        
                        combined_secret_hashes = self.get_combined_secret_hashes()
                        
                        status = self.get_spectator_status()
                        
                        await websocket.send(json.dumps({
                            "event": "welcome",
                            "message": "Welcome spectator to Shocker Roulette!",
                            "forbidden_words": self.config["forbidden_words"],
                            "secret_hashes": combined_secret_hashes,
                            "players": list(self.clients.keys()),
                            "roulette_start_intensity": self.config.get("roulette_start_intensity", 10),
                            "roulette_max_intensity": self.config.get("roulette_max_intensity", 50),
                            "roulette_current_intensity": self.config.get("roulette_current_intensity", 10),
                            **status
                        }))
                        continue

                    player_name = data.get("name", "").strip()
                    client_sha1 = data.get("client_sha1")
                    voice_sha1 = data.get("voice_recog_sha1")
                    
                    if not player_name:
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": "Registration failed: Player name is required."
                        }))
                        continue
                        
                    if player_name in self.clients:
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": f"Registration failed: Name '{player_name}' is already taken."
                        }))
                        continue

                    # Anti-Cheat: Verify client file integrity hashes
                    if self.ref_client_sha1 and client_sha1 != self.ref_client_sha1:
                        logger.warning(f"⚠️ INTEGRITY CHECK FAILED: {player_name} tried joining with a modified client.py!")
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": "Registration failed: Modified or outdated client file detected (client.py)."
                        }))
                        await websocket.close()
                        return
                        
                    if self.ref_voice_recog_sha1 and voice_sha1 != self.ref_voice_recog_sha1:
                        logger.warning(f"⚠️ INTEGRITY CHECK FAILED: {player_name} tried joining with a modified voice_recog.py!")
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": "Registration failed: Modified or outdated client file detected (voice_recog.py)."
                        }))
                        await websocket.close()
                        return

                    # Register the connection
                    self.clients[player_name] = websocket
                    self.client_telemetry[player_name] = {
                        "phrases_spoken": 0,
                        "mic_active": False,
                        "last_active": time.time()
                    }
                    logger.info(f"Player '{player_name}' joined from {websocket.remote_address} (integrity check passed)")
                    
                    combined_secret_hashes = self.get_combined_secret_hashes()
                    
                    # Send welcome with active configurations and secret hashes list
                    await websocket.send(json.dumps({
                        "event": "welcome",
                        "message": f"Welcome {player_name} to Shocker Roulette!",
                        "forbidden_words": self.config["forbidden_words"],
                        "secret_hashes": combined_secret_hashes,
                        "max_words_per_player": self.config.get("max_words_per_player", 3),
                        "word_add_cooldown_seconds": self.config.get("word_add_cooldown_seconds", 60.0),
                        "roulette_start_intensity": self.config.get("roulette_start_intensity", 10),
                        "roulette_max_intensity": self.config.get("roulette_max_intensity", 50),
                        "roulette_current_intensity": self.config.get("roulette_current_intensity", 10)
                    }))
                    
                    # Broadcast join event to everyone
                    await self.broadcast({
                        "event": "player_joined",
                        "name": player_name,
                        "players": list(self.clients.keys())
                    })


                elif action == "add_spectator_word":
                    self.recharge_spectator_tokens()
                    if self.spectator_tokens < 1:
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": "Shared spectator word pool is empty! Please wait for a token to recharge."
                        }))
                        continue
                        
                    new_word = data.get("word", "").strip().lower()
                    if not new_word:
                        continue
                        
                    translator = str.maketrans('', '', string.punctuation)
                    clean_new_word = new_word.translate(translator).lower().strip()
                    if not clean_new_word:
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": "Word cannot consist solely of punctuation."
                        }))
                        continue
                    
                    # Verify if it already exists in public or secret/spectator lists
                    existing_public_clean = [w.translate(translator).lower().strip() for w in self.config.get("forbidden_words", [])]
                    existing_secret_clean = []
                    for entry in self.config.get("secret_words", []) + self.config.get("spectator_words", []):
                        if isinstance(entry, dict) and "word" in entry:
                            existing_secret_clean.append(entry["word"].translate(translator).lower().strip())
                        elif isinstance(entry, str):
                            existing_secret_clean.append(entry.translate(translator).lower().strip())
                            
                    all_existing_clean = existing_public_clean + existing_secret_clean
                    if clean_new_word in all_existing_clean:
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": f"'{new_word}' is already in the banned list."
                        }))
                        continue
                        
                    # Deduct token
                    self.spectator_tokens -= 1
                    
                    # Add to spectator words
                    if "spectator_words" not in self.config:
                        self.config["spectator_words"] = []
                        
                    new_hash = hashlib.sha256(clean_new_word.encode('utf-8')).hexdigest()
                    entry = {
                        "hash": new_hash,
                        "word": new_word,
                        "creator": "Spectator",
                        "triggers": 0
                    }
                    self.config["spectator_words"].append(entry)
                    self.update_hashed_words_lookup()
                    
                    logger.info(f"🆕 Added SPECTATOR secret word: '{new_word}' (Tokens remaining: {self.spectator_tokens})")
                    
                    combined_secret_hashes = self.get_combined_secret_hashes()
                    
                    # Broadcast success and token state update to everyone
                    await self.broadcast({
                        "event": "words_updated",
                        "forbidden_words": self.config["forbidden_words"],
                        "secret_hashes": combined_secret_hashes,
                        "message": "A spectator added a new hidden trap word to the lobby!"
                    })
                    continue

                elif action == "spectator_ping":
                    status = self.get_spectator_status()
                    await websocket.send(json.dumps({
                        "event": "spectator_status",
                        **status
                    }))
                    continue

                elif action == "add_word":
                    if not player_name:
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": "You must register before adding forbidden words."
                        }))
                        continue
                        
                    # Check player word addition limits & cooldowns
                    current_time = time.time()
                    cooldown_dur = self.config.get("word_add_cooldown_seconds", 60.0)
                    max_words = self.config.get("max_words_per_player", 3)
                    
                    if player_name not in self.player_word_timestamps:
                        self.player_word_timestamps[player_name] = []
                        
                    # Keep only recent timestamps
                    recent_timestamps = [t for t in self.player_word_timestamps[player_name] if current_time - t < cooldown_dur]
                    self.player_word_timestamps[player_name] = recent_timestamps
                    
                    if len(recent_timestamps) >= max_words:
                        oldest_t = min(recent_timestamps)
                        wait_remaining = int((oldest_t + cooldown_dur) - current_time)
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": f"Banned word limit reached! Wait {wait_remaining}s before adding another."
                        }))
                        continue
                        
                    new_word = data.get("word", "").strip().lower()
                    if not new_word:
                        continue
                        
                    translator = str.maketrans('', '', string.punctuation)
                    clean_new_word = new_word.translate(translator).lower().strip()
                    if not clean_new_word:
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": "Word cannot consist solely of punctuation."
                        }))
                        continue
                    
                    # Check if already present in public or secret lists (ignoring punctuation/case/hashes)
                    existing_public_clean = [w.translate(translator).lower().strip() for w in self.config.get("forbidden_words", [])]
                    existing_secret_clean = []
                    for entry in self.config.get("secret_words", []):
                        if isinstance(entry, dict) and "word" in entry:
                            existing_secret_clean.append(entry["word"].translate(translator).lower().strip())
                        elif isinstance(entry, str):
                            existing_secret_clean.append(entry.translate(translator).lower().strip())
                            
                    all_existing_clean = existing_public_clean + existing_secret_clean
                    
                    if clean_new_word in all_existing_clean:
                        await websocket.send(json.dumps({
                            "event": "error",
                            "message": f"'{new_word}' is already in the banned list."
                        }))
                        continue
                        
                    # Initialize secret_words list if not exists
                    if "secret_words" not in self.config:
                        self.config["secret_words"] = []
                        
                    # Generate hash and add as dictionary entry
                    new_hash = hashlib.sha256(clean_new_word.encode('utf-8')).hexdigest()
                    entry = {
                        "hash": new_hash,
                        "word": new_word,
                        "creator": player_name,
                        "triggers": 0
                    }
                    self.config["secret_words"].append(entry)
                    self.player_word_timestamps[player_name].append(current_time)
                    self.update_hashed_words_lookup()
                        
                    logger.info(f"🆕 Added SECRET forbidden word: '{new_word}' (requested by {player_name})")
                    
                    # Acknowledge requester (secret word success)
                    combined_secret_hashes = self.get_combined_secret_hashes()
                    await websocket.send(json.dumps({
                        "event": "words_updated",
                        "forbidden_words": self.config["forbidden_words"], # Send public list only
                        "secret_hashes": combined_secret_hashes,
                        "message": f"Successfully added secret word: '{new_word}'!",
                        "roulette_start_intensity": self.config.get("roulette_start_intensity", 10),
                        "roulette_max_intensity": self.config.get("roulette_max_intensity", 50),
                        "roulette_current_intensity": self.config.get("roulette_current_intensity", 10)
                    }))
                    # Broadcast blind tension notice to everyone else (without revealing the word itself)
                    await self.broadcast_except(websocket, {
                        "event": "words_updated",
                        "forbidden_words": self.config["forbidden_words"], # Send public list only
                        "secret_hashes": combined_secret_hashes,
                        "message": "A player added a new secret forbidden word to the lobby! Watch your tongue!"
                    })

                elif action == "heartbeat":
                    if not player_name:
                        continue
                    phrases = data.get("phrases_spoken", 0)
                    mic_active = data.get("mic_active", False)
                    self.client_telemetry[player_name] = {
                        "phrases_spoken": phrases,
                        "mic_active": mic_active,
                        "last_active": time.time()
                    }

                elif action == "trigger":
                    if not player_name:
                        continue
                        
                    word_str = data.get("word")
                    hash_str = data.get("hash")
                    matched_entry = None
                    
                    # Verify trigger locally
                    if word_str:
                        translator = str.maketrans('', '', string.punctuation)
                        clean = word_str.translate(translator).lower().strip()
                        if clean in [w.translate(translator).lower().strip() for w in self.config.get("forbidden_words", [])]:
                            matched_entry = word_str
                    elif hash_str:
                        if hash_str in self.hashed_words:
                            matched_entry = self.hashed_words[hash_str]
                            
                    if matched_entry:
                        is_secret = isinstance(matched_entry, dict)
                        word_str = matched_entry["word"] if is_secret else matched_entry
                        matched_hash = hash_str if hash_str else matched_entry.get("hash") if is_secret else None
                        
                        # Handle secret word creator immunity (case-insensitive)
                        if is_secret:
                            creator = matched_entry.get("creator", "")
                            if creator.lower() == player_name.lower() and self.config.get("creator_immunity_on_secret", True):
                                logger.info(f"🛡️ Creator Immunity: '{player_name}' spoke their own secret word '{word_str}' (ignored).")
                                continue
                                
                        # Check cooldown
                        current_time = time.time()
                        cooldown = self.config["cooldown_seconds"]
                        if current_time - self.last_trigger_time < cooldown:
                            logger.info(f"Trigger ignored: Cooldown active")
                            continue

                        self.last_trigger_time = current_time

                        # Prepare punishment settings from server config
                        raw_punishment = self.config.get("punishment_type", "shock")
                        try:
                            punishment = PunishmentType(raw_punishment.lower()).value
                        except ValueError:
                            punishment = PunishmentType.SHOCK.value
                        duration_ms = self.config["duration_ms"]

                        # Calculate random variance around base intensity (scales with current roulette stakes)
                        base_intensity = self.config.get("roulette_current_intensity", self.config.get("intensity", 10))
                        variance = self.config.get("intensity_variance", 0)

                        if variance > 0:
                            import random
                            min_i = max(1, base_intensity - variance)
                            max_i = min(100, base_intensity + variance)
                            final_intensity = random.randint(min_i, max_i)
                        else:
                            final_intensity = base_intensity

                        # Check triggers and handle public vs secret flows
                        if is_secret:
                            is_spectator_word = (matched_entry.get("creator") == "Spectator")
                            creator = matched_entry.get("creator")
                            
                            if is_spectator_word:
                                logger.info(f"⚡ SPECTATOR TRAP TRIGGERED: '{player_name}' said spectator word '{word_str}'!")
                                
                                # 2. Migrate spectator word to public forbidden list
                                self.config["spectator_words"] = [e for e in self.config.get("spectator_words", []) if isinstance(e, dict) and e.get("hash") != matched_hash]
                                if word_str not in self.config["forbidden_words"]:
                                    self.config["forbidden_words"].append(word_str)
                                    
                                self.update_hashed_words_lookup()
                                
                                combined_secret_hashes = self.get_combined_secret_hashes()
                                
                                # 3. Broadcast updated public word list with migration announcement
                                await self.broadcast({
                                    "event": "words_updated",
                                    "forbidden_words": self.config["forbidden_words"],
                                    "secret_hashes": combined_secret_hashes,
                                    "message": f"🚨 Spectator hidden word '{word_str}' was triggered by {player_name} and is now PUBLIC!"
                                })
                                
                                # 4. Execute the targeted punishment (nobody is immune, shock the speaker!)
                                await self.broadcast({
                                    "event": "punish",
                                    "speaker": player_name,
                                    "word": word_str,
                                    "punishment_type": punishment,
                                    "intensity": final_intensity,
                                    "duration_ms": duration_ms,
                                    "immune_players": []
                                })
                            else:
                                # Normal player secret word triggered:
                                logger.info(f"⚡ SECRET TRAP TRIGGERED: '{player_name}' said secret word '{word_str}' created by '{creator}'!")
                                
                                # 2. Migrate secret word to the public forbidden list
                                self.config["secret_words"] = [e for e in self.config.get("secret_words", []) if isinstance(e, dict) and e.get("hash") != matched_hash]
                                if word_str not in self.config["forbidden_words"]:
                                    self.config["forbidden_words"].append(word_str)
                                    
                                self.update_hashed_words_lookup()
                                
                                combined_secret_hashes = self.get_combined_secret_hashes()
                                
                                # 3. Broadcast updated public word list with migration announcement
                                await self.broadcast({
                                    "event": "words_updated",
                                    "forbidden_words": self.config["forbidden_words"],
                                    "secret_hashes": combined_secret_hashes,
                                    "message": f"🚨 Secret word '{word_str}' was triggered by {player_name} and is now PUBLIC! Creator: {creator}."
                                })
                                
                                # 4. Execute the targeted punishment (creator is immune)
                                await self.broadcast({
                                    "event": "punish",
                                    "speaker": player_name,
                                    "word": word_str,
                                    "punishment_type": punishment,
                                    "intensity": final_intensity,
                                    "duration_ms": duration_ms,
                                    "immune_players": [creator] if creator else []
                                })
                        else:
                            # Public Word Triggered:
                            # Increment trigger count using cleaned lowercase word to prevent case/punctuation mismatches
                            translator = str.maketrans('', '', string.punctuation)
                            clean_word = word_str.translate(translator).lower().strip()
                            
                            trigger_count = self.public_trigger_counts.get(clean_word, 0) + 1
                            self.public_trigger_counts[clean_word] = trigger_count
                            max_triggers = self.config.get("word_max_triggers", 3)
                            
                            if trigger_count >= max_triggers:
                                # Trigger ROULETTE!
                                self.public_trigger_counts[clean_word] = 0 # reset
                                
                                # Remove the word from play forever (case-insensitive)
                                for w in list(self.config.get("forbidden_words", [])):
                                    if w.translate(translator).lower().strip() == clean_word:
                                        self.config["forbidden_words"].remove(w)
                                        
                                self.update_hashed_words_lookup()
                                
                                # Broadcast words list update to all clients to show the word is gone
                                await self.broadcast({
                                    "event": "words_updated",
                                    "forbidden_words": self.config["forbidden_words"],
                                    "secret_hashes": self.get_combined_secret_hashes(),
                                    "message": f"💥 Word '{word_str}' hit its trigger limit, initiated ROULETTE, and is REMOVED from play!"
                                })
                                
                                players_list = list(self.clients.keys())
                                if players_list:
                                    import random
                                    victim = random.choice(players_list)
                                    
                                    # Generate ticking sequence (loaded from config)
                                    rounds = self.config.get("roulette_rounds", 6)
                                    ticking_sequence = []
                                    for _ in range(rounds):
                                        ticking_sequence.extend(players_list)
                                    victim_idx = players_list.index(victim)
                                    ticking_sequence.extend(players_list[:victim_idx + 1])
                                    
                                    logger.info(f"🎯 ROULETTE ACTIVATED by '{player_name}' speaking '{word_str}' too much! Starting spin sequence...")
                                    
                                    # Resolve the escalating roulette stakes intensity
                                    current_stakes = self.config.get("roulette_current_intensity", 10)
                                    increment = self.config.get("roulette_intensity_increment", 5)
                                    max_stakes = self.config.get("roulette_max_intensity", 50)
                                    
                                    roulette_shock_intensity = current_stakes
                                    
                                    # Increment stakes for the next event and save it
                                    next_stakes = min(max_stakes, current_stakes + increment)
                                    self.config["roulette_current_intensity"] = next_stakes
                                    logger.info(f"📈 Roulette stakes escalated: {current_stakes}% -> {next_stakes}% (Max cap: {max_stakes}%)")

                                    # Broadcast roulette event (no victim info sent to prevent client-side spoilers!)
                                    await self.broadcast({
                                        "event": "roulette",
                                        "speaker": player_name,
                                        "word": word_str,
                                        "ticking_sequence": ticking_sequence,
                                        "tick_delay_ms": 350,
                                        "vibrate_intensity": 100
                                    })

                                    # Async delay for the duration of the spin before delivering shock
                                    total_delay_sec = (len(ticking_sequence) * 350 + 500) / 1000.0
                                    
                                    async def deliver_roulette_shock(delay, victim_player, intensity, dur, next_int):
                                        await asyncio.sleep(delay)
                                        logger.info(f"⚡ ROULETTE SELECTION DELIVERED: '{victim_player}' has been shocked!")
                                        await self.broadcast({
                                            "event": "punish",
                                            "speaker": "Roulette Wheel",
                                            "word": f"Roulette Landing (Stakes: {intensity}%)",
                                            "punishment_type": "shock",
                                            "intensity": intensity,
                                            "duration_ms": dur,
                                            "immune_players": [p for p in players_list if p.lower() != victim_player.lower()]
                                        })
                                        # Send stakes escalation notice
                                        await self.broadcast({
                                            "event": "words_updated",
                                            "forbidden_words": self.config["forbidden_words"],
                                            "secret_hashes": self.get_combined_secret_hashes(),
                                            "message": f"📈 Roulette stakes escalated! Next landing intensity is now {next_int}%!"
                                        })
                                    
                                    asyncio.create_task(deliver_roulette_shock(total_delay_sec, victim, roulette_shock_intensity, duration_ms, next_stakes))
                            else:
                                # Normal group punishment
                                logger.info(f"⚡ PUBLIC TRIGGER: '{player_name}' spoke public word '{word_str}' (Triggers: {trigger_count}/{max_triggers}).")
                                await self.broadcast({
                                    "event": "punish",
                                    "speaker": player_name,
                                    "word": f"{word_str} ({trigger_count}/{max_triggers})",
                                    "punishment_type": punishment,
                                    "intensity": final_intensity,
                                    "duration_ms": duration_ms
                                })

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection closed for {player_name or 'unregistered client'}")
        finally:
            if websocket in self.spectator_clients:
                self.spectator_clients.remove(websocket)
                logger.info("Spectator disconnected.")
            elif player_name and player_name in self.clients:
                del self.clients[player_name]
                # Broadcast departure
                await self.broadcast({
                    "event": "player_left",
                    "name": player_name,
                    "players": list(self.clients.keys())
                })

    async def run(self):
        # Start server on all interfaces (port 8765)
        server = await websockets.serve(self.handle_client, "0.0.0.0", 8765, process_request=self.process_request)
        logger.info("Shocker Roulette Server running on ws://0.0.0.0:8765 (and HTTP on http://0.0.0.0:8765)")
        await server.wait_closed()

if __name__ == "__main__":
    server_instance = ShockerServer()
    try:
        asyncio.run(server_instance.run())
    except KeyboardInterrupt:
        logger.info("Server stopped manually.")
    finally:
        server_instance.save_config()
