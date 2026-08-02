import time
import string
import logging
import random
import asyncio
import json
import hashlib
from constants import PunishmentType
from config_manager import ConfigManager

logger = logging.getLogger("GameServer")

class BaseGameMode:
    """Abstract base class for modular game modes."""
    def __init__(self, server):
        self.server = server

    async def get_welcome_payload(self, player_name: str) -> dict:
        raise NotImplementedError

    async def get_spectator_welcome_payload(self) -> dict:
        raise NotImplementedError

    async def handle_action(self, websocket, action: str, data: dict, player_name: str = None) -> bool:
        """
        Handles game-mode specific actions.
        Returns True if handled, False if unhandled/unknown action.
        """
        raise NotImplementedError

    async def on_player_joined(self, player_name: str):
        pass

    async def on_player_left(self, player_name: str):
        pass

    def on_exit():
        pass


class GameLoop(BaseGameMode):
    '''
    Shocker Roulette Game Mode Engine
    '''
    def __init__(self, server):
        super().__init__(server)
        self.config = {}
        self.hashed_words = {}
        self.public_trigger_counts = {}
        self.player_word_timestamps = {}
        self.last_trigger_time = 0.0

        # Spectator Mode variables
        self.spectator_tokens = 5
        self.last_token_recharge_time = time.time()

        self.load_config()

    def load_config(self):
        self.config = ConfigManager.load_config()
        self.update_hashed_words_lookup()

    def load_words(self):
        words_data = ConfigManager.load_words()
        self.config["forbidden_words"] = words_data.get("forbidden_words", [])
        self.config["secret_words"] = words_data.get("secret_words", [])
        self.config["spectator_words"] = words_data.get("spectator_words", [])

    def on_exit(self):
        ConfigManager.save_words(self.config)
        ConfigManager.save_config(self.config)

    def update_hashed_words_lookup(self):
        self.hashed_words = ConfigManager.build_hashed_words_lookup(self.config)

    def try_recharge_spectator_tokens(self):
        now = time.time()
        elapsed = now - self.last_token_recharge_time
        recharge_rate = self.config.get("spectator_token_recharge_seconds", 60)
        max_tokens = self.config.get("spectator_max_tokens", 5)
        
        if elapsed >= recharge_rate:
            recharged = int(elapsed // recharge_rate)
            self.spectator_tokens = min(max_tokens, self.spectator_tokens + recharged)
            self.last_token_recharge_time += recharged * recharge_rate

    def get_spectator_status(self):
        self.try_recharge_spectator_tokens()
        now = time.time()
        time_to_next_recharge = max(0.0, self.config.get("spectator_token_recharge_seconds", 60) - (now - self.last_token_recharge_time))
        recharge_seconds_left = int(time_to_next_recharge)
        
        max_tokens = self.config.get("spectator_max_tokens", 5)
        if self.spectator_tokens < max_tokens and recharge_seconds_left <= 0:
            recharge_seconds_left = 1
            
        return {
            "spectator_tokens": self.spectator_tokens,
            "spectator_max_tokens": max_tokens,
            "recharge_seconds_left": recharge_seconds_left
        }

    def get_stakes_state(self):
        return {
            "roulette_start_intensity": self.config.get("roulette_start_intensity", 10),
            "roulette_max_intensity": self.config.get("roulette_max_intensity", 50),
            "roulette_current_intensity": self.config.get("roulette_current_intensity", 10)
        }

    def get_combined_secret_hashes(self):
        return (
            [entry["hash"] for entry in self.config.get("secret_words", []) if isinstance(entry, dict) and "hash" in entry] +
            [entry["hash"] for entry in self.config.get("spectator_words", []) if isinstance(entry, dict) and "hash" in entry]
        )

    async def get_welcome_payload(self, player_name: str) -> dict:
        combined_secret_hashes = self.get_combined_secret_hashes()
        return {
            "event": "welcome",
            "message": f"Welcome {player_name} to Shocker Roulette!",
            "forbidden_words": self.config["forbidden_words"],
            "secret_hashes": combined_secret_hashes,
            "players": self.server.get_players_state(),
            "max_words_per_player": self.config.get("max_words_per_player", 3),
            "word_add_cooldown_seconds": self.config.get("word_add_cooldown_seconds", 60.0),
            "roulette_start_intensity": self.config.get("roulette_start_intensity", 10),
            "roulette_max_intensity": self.config.get("roulette_max_intensity", 50),
            "roulette_current_intensity": self.config.get("roulette_current_intensity", 10)
        }

    async def get_spectator_welcome_payload(self) -> dict:
        combined_secret_hashes = self.get_combined_secret_hashes()
        status = self.get_spectator_status()
        return {
            "event": "welcome",
            "message": "Welcome spectator to Shocker Roulette!",
            "forbidden_words": self.config["forbidden_words"],
            "secret_hashes": combined_secret_hashes,
            "players": self.server.get_players_state(),
            "roulette_start_intensity": self.config.get("roulette_start_intensity", 10),
            "roulette_max_intensity": self.config.get("roulette_max_intensity", 50),
            "roulette_current_intensity": self.config.get("roulette_current_intensity", 10),
            **status
        }

    async def handle_action(self, websocket, action: str, data: dict, player_name: str = None) -> bool:
        handlers = {
            "add_spectator_word": self.handle_add_spectator_word,
            "spectator_ping": self.handle_spectator_ping,
            "add_word": self.handle_add_word,
            "trigger": self.handle_trigger
        }
        handler = handlers.get(action)
        if handler:
            await handler(websocket, data, player_name)
            return True
        return False

    async def handle_add_word_generic(self, websocket, data, player_name, is_spectator=False):
        if is_spectator:
            self.try_recharge_spectator_tokens()
            if self.spectator_tokens < 1:
                await websocket.send(json.dumps({
                    "event": "error",
                    "message": "Shared spectator word pool is empty! Please wait for a token to recharge."
                }))
                return
            creator = "Spectator"
        else:
            if not player_name:
                await websocket.send(json.dumps({
                    "event": "error",
                    "message": "You must register before adding forbidden words."
                }))
                return
                
            current_time = time.time()
            cooldown_dur = self.config.get("word_add_cooldown_seconds", 60.0)
            max_words = self.config.get("max_words_per_player", 3)
            
            if player_name not in self.player_word_timestamps:
                self.player_word_timestamps[player_name] = []
                
            recent_timestamps = [t for t in self.player_word_timestamps[player_name] if current_time - t < cooldown_dur]
            self.player_word_timestamps[player_name] = recent_timestamps

            if len(recent_timestamps) >= max_words:
                oldest_t = min(recent_timestamps)
                wait_remaining = int((oldest_t + cooldown_dur) - current_time)
                await websocket.send(json.dumps({
                    "event": "error",
                    "message": f"Banned word limit reached! Wait {wait_remaining}s before adding another."
                }))
                return
            creator = player_name

        new_word = data.get("word", "").strip().lower()
        if not new_word:
            return
        translator = str.maketrans('', '', string.punctuation)
        clean_new_word = new_word.translate(translator).lower().strip()
        if not clean_new_word:
            await websocket.send(json.dumps({
                "event": "error",
                "message": "Word cannot consist solely of punctuation."
            }))
            return
        
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
            return
            
        new_hash = hashlib.sha256(clean_new_word.encode('utf-8')).hexdigest()
        entry = {
            "hash": new_hash,
            "word": new_word,
            "creator": creator,
            "triggers": 0
        }

        if is_spectator:
            self.spectator_tokens -= 1
            if "spectator_words" not in self.config:
                self.config["spectator_words"] = []
            self.config["spectator_words"].append(entry)
            logger.info(f"🆕 Added SPECTATOR secret word: '{new_word}' (Tokens remaining: {self.spectator_tokens})")
        else:
            if "secret_words" not in self.config:
                self.config["secret_words"] = []
            self.config["secret_words"].append(entry)
            self.player_word_timestamps[player_name].append(current_time)
            logger.info(f"🆕 Added SECRET forbidden word: '{new_word}' (requested by {player_name})")

        self.update_hashed_words_lookup()
            
        combined_secret_hashes = self.get_combined_secret_hashes()
        
        if is_spectator:
            spec_status = self.get_spectator_status()
            await self.server.broadcast({
                "event": "words_updated",
                "forbidden_words": self.config["forbidden_words"],
                "secret_hashes": combined_secret_hashes,
                "message": "A spectator added a new hidden trap word to the lobby!",
                **spec_status,
                **self.get_stakes_state()
            })
        else:
            await websocket.send(json.dumps({
                "event": "add_word_success",
                "word": new_word
            }))
            await websocket.send(json.dumps({
                "event": "words_updated",
                "forbidden_words": self.config["forbidden_words"],
                "secret_hashes": combined_secret_hashes,
                "message": f"Successfully added secret word: '{new_word}'!",
                **self.get_stakes_state()
            }))
            
            await self.server.broadcast_except(websocket, {
                "event": "words_updated",
                "forbidden_words": self.config["forbidden_words"],
                "secret_hashes": combined_secret_hashes,
                "message": "A player added a new secret forbidden word to the lobby! Watch your tongue!",
                **self.get_stakes_state()
            })

    async def handle_add_spectator_word(self, websocket, data, player_name):
        await self.handle_add_word_generic(websocket, data, player_name, is_spectator=True)

    async def handle_spectator_ping(self, websocket, data, player_name):
        status = self.get_spectator_status()
        await websocket.send(json.dumps({
            "event": "spectator_status",
            **status
        }))

    async def handle_add_word(self, websocket, data, player_name):
        await self.handle_add_word_generic(websocket, data, player_name, is_spectator=False)

    async def handle_trigger(self, websocket, data, player_name):
        if not player_name:
            return
        await self.trigger(
            player_name=player_name,
            transcript=data.get("transcript"),
            word=data.get("word"),
            word_hash=data.get("hash")
        )

    async def on_player_left(self, player_name: str):
        if player_name in self.player_word_timestamps:
            del self.player_word_timestamps[player_name]

    async def trigger(self, player_name, transcript=None, word=None, word_hash=None):
        if not player_name:
            return

        # Increments phrases spoken telemetry
        if transcript and player_name in self.server.client_telemetry:
            self.server.client_telemetry[player_name]["phrases_spoken"] = self.server.client_telemetry[player_name].get("phrases_spoken", 0) + 1

        matched_word = None
        is_secret = False
        matched_entry = None
        matched_hash = None
        translator = str.maketrans('', '', string.punctuation)

        # 1. Direct secret word hash trigger (from Web clients to keep words secret)
        if word_hash:
            for list_key in ("secret_words", "spectator_words"):
                if matched_word:
                    break
                for entry in self.config.get(list_key, []):
                    if isinstance(entry, dict) and entry.get("hash") == word_hash:
                        # Check creator immunity (only applies to player secret_words)
                        if list_key == "secret_words" and self.config.get("creator_immunity_on_secret", True) and entry.get("creator", "").lower() == player_name.lower():
                            logger.info(f"🛡️ Creator Immunity: {player_name} spoke their own secret word (hash: {word_hash})")
                            return
                        matched_word = entry["word"]
                        is_secret = True
                        matched_entry = entry
                        matched_hash = entry["hash"]
                        break

        # 2. Direct public word trigger (from Web clients)
        elif word:
            for forbidden in self.config.get("forbidden_words", []):
                if forbidden.translate(translator).lower().strip() == word.translate(translator).lower().strip():
                    matched_word = forbidden
                    break

        if not matched_word:
            return

        word_str = str(matched_word)
        
        # Check cooldown
        current_time = time.time()
        cooldown = self.config.get("cooldown_seconds", 3.0)
        if current_time - self.last_trigger_time < cooldown:
            logger.info(f"Trigger ignored: Cooldown active")
            return

        self.last_trigger_time = current_time

        # Prepare punishment settings from server config
        raw_punishment = self.config.get("punishment_type", "shock")
        try:
            punishment = PunishmentType(raw_punishment.lower()).value
        except ValueError as e:
            # Default to sound, something is wrong.
            logger.warning("Failed to look up punishment type, defaulting to sound: %s", e)
            punishment = PunishmentType.SOUND.value
            
        base_duration = self.config.get("duration_ms", 1000)
        dur_variance = self.config.get("duration_variance_ms", 0)

        if dur_variance > 0:
            min_d = max(100, base_duration - dur_variance)
            max_d = base_duration + dur_variance
            final_duration_ms = random.randint(min_d, max_d)
        else:
            final_duration_ms = base_duration

        # Calculate random variance around base intensity (scales with current roulette stakes)
        base_intensity = self.config.get("roulette_current_intensity", self.config.get("intensity", 10))
        variance = self.config.get("intensity_variance", 0)

        if variance > 0:
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
                list_key = "spectator_words"
                message_txt = f"🚨 Spectator hidden word '{word_str}' was triggered by {player_name} and is now PUBLIC!"
                immune_players = []
            else:
                logger.info(f"⚡ SECRET TRAP TRIGGERED: '{player_name}' said secret word '{word_str}' created by '{creator}'!")
                list_key = "secret_words"
                message_txt = f"🚨 Secret word '{word_str}' was triggered by {player_name} and is now PUBLIC! Creator: {creator}."
                immune_players = [creator] if creator else []
                
            # Unified migration logic
            self.config[list_key] = [e for e in self.config.get(list_key, []) if isinstance(e, dict) and e.get("hash") != matched_hash]
            if word_str not in self.config["forbidden_words"]:
                self.config["forbidden_words"].append(word_str)
                
            self.update_hashed_words_lookup()
            
            combined_secret_hashes = self.get_combined_secret_hashes()
            
            # Broadcast updated public word list with migration announcement
            await self.server.broadcast({
                "event": "words_updated",
                "forbidden_words": self.config["forbidden_words"],
                "secret_hashes": combined_secret_hashes,
                "message": message_txt,
                **self.get_stakes_state()
            })
            
            # Execute targeted punishment
            await self.server.broadcast({
                "event": "punish",
                "speaker": player_name,
                "word": word_str,
                "punishment_type": punishment,
                "intensity": final_intensity,
                "duration_ms": final_duration_ms,
                "immune_players": immune_players
            })
        else:
            # Public Word Triggered:
            clean_word = word_str.translate(translator).lower().strip()
            
            trigger_count = self.public_trigger_counts.get(clean_word, 0) + 1
            self.public_trigger_counts[clean_word] = trigger_count
            max_triggers = self.config.get("word_max_triggers", 3)
            
            if trigger_count >= max_triggers:
                # Trigger ROULETTE!
                self.public_trigger_counts[clean_word] = 0 # reset
                
                # Remove the word from play (case-insensitive)
                for w in list(self.config.get("forbidden_words", [])):
                    if w.translate(translator).lower().strip() == clean_word:
                        self.config["forbidden_words"].remove(w)
                        
                self.update_hashed_words_lookup()
                
                # Broadcast words list update to all clients to show the word is gone
                await self.server.broadcast({
                    "event": "words_updated",
                    "forbidden_words": self.config["forbidden_words"],
                    "secret_hashes": self.get_combined_secret_hashes(),
                    "message": f"💥 Word '{word_str}' hit its trigger limit, initiated ROULETTE, and is REMOVED from play!",
                    **self.get_stakes_state()
                })
                
                players_list = list(self.server.clients.keys())
                if players_list:
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
                    await self.server.broadcast({
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
                        
                        multiplier = self.config.get("roulette_multiplier", 1.5)
                        final_intensity = min(100, max(1, int(intensity * multiplier)))
                        
                        await self.server.broadcast({
                            "event": "punish",
                            "speaker": "Roulette Wheel",
                            "word": f"Roulette Landing (Stakes: {intensity}% x{multiplier})",
                            "punishment_type": "shock",
                            "intensity": final_intensity,
                            "duration_ms": dur,
                            "immune_players": [p for p in players_list if p.lower() != victim_player.lower()]
                        })
                        # Send stakes escalation notice
                        await self.server.broadcast({
                            "event": "words_updated",
                            "forbidden_words": self.config["forbidden_words"],
                            "secret_hashes": self.get_combined_secret_hashes(),
                            "message": f"📈 Roulette stakes escalated! Next landing intensity is now {next_int}%!",
                            **self.get_stakes_state()
                        })
                    
                    asyncio.create_task(deliver_roulette_shock(total_delay_sec, victim, roulette_shock_intensity, final_duration_ms, next_stakes))
            else:
                # Normal group punishment
                logger.info(f"⚡ PUBLIC TRIGGER: '{player_name}' spoke public word '{word_str}' (Triggers: {trigger_count}/{max_triggers}).")
                await self.server.broadcast({
                    "event": "punish",
                    "speaker": player_name,
                    "word": f"{word_str} ({trigger_count}/{max_triggers})",
                    "punishment_type": punishment,
                    "intensity": final_intensity,
                    "duration_ms": final_duration_ms
                })

