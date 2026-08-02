import os
import json
import logging
import hashlib
import string
from constants import CONFIG_PATH, WORDS_PATH, DEFAULT_CONFIG, DEFAULT_WORDS

logger = logging.getLogger("GameServer")

class ConfigManager:
    '''
    Manages loading, saving, merging, and hashed lookup indexing for game configuration and word lists.
    '''

    @staticmethod
    def load_config():
        config = DEFAULT_CONFIG.copy()

        # load config if it exists, if not create the file with defaults
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    file_config = json.load(f)
                    config.update(file_config)
                logger.info(f"Configuration loaded and merged from {CONFIG_PATH}")
            except Exception as e:
                logger.error(f"Error loading config.json, using defaults. Error: {e}")
        else:
            try:
                with open(CONFIG_PATH, "w") as f:
                    json.dump(config, f, indent=4)
                logger.info(f"Created default configuration file at {CONFIG_PATH}")
            except Exception as e:
                logger.error(f"Failed to create config.json: {e}")
        
        words_data = ConfigManager.load_words()
        config["forbidden_words"] = words_data.get("forbidden_words", [])
        config["secret_words"] = words_data.get("secret_words", [])
        config["spectator_words"] = words_data.get("spectator_words", [])

        config["roulette_current_intensity"] = config.get("roulette_start_intensity", 10)
        return config

    @staticmethod
    def load_words():
        words_data = DEFAULT_WORDS.copy()

        if os.path.exists(WORDS_PATH):
            try:
                with open(WORDS_PATH, "r") as f:
                    file_words = json.load(f)
                    words_data.update(file_words)
                logger.info(f"Word list loaded and merged from {WORDS_PATH}")
            except Exception as e:
                logger.error(f"Error loading words.json, using defaults. Error: {e}")
        else:
            try:
                with open(WORDS_PATH, "w") as f:
                    json.dump(words_data, f, indent=4)
                logger.info(f"Created default word list file at {WORDS_PATH}")
            except Exception as e:
                logger.error(f"Failed to create words.json: {e}")

        return words_data

    @staticmethod
    def save_words(config):
        try:
            words_data = {
                "forbidden_words": config.get("forbidden_words", []),
                "secret_words": config.get("secret_words", []),
                "spectator_words": config.get("spectator_words", [])
            }
            with open(WORDS_PATH, "w") as f:
                json.dump(words_data, f, indent=4)
            logger.info(f"Word list saved to {WORDS_PATH}")
        except Exception as e:
            logger.error(f"Failed to save words.json: {e}")

    @staticmethod
    def save_config(config):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=4)
            logger.info(f"Configuration saved to {CONFIG_PATH}")
        except Exception as e:
            logger.error(f"Failed to save config.json: {e}")

    @staticmethod
    def build_hashed_words_lookup(config):
        hashed_words = {}
        translator = str.maketrans('', '', string.punctuation)

        for word in config.get("forbidden_words", []):
            clean = word.translate(translator).lower().strip()
            if clean:
                h = hashlib.sha256(clean.encode('utf-8')).hexdigest()
                hashed_words[h] = word
                
        for entry in config.get("secret_words", []):
            if isinstance(entry, dict) and "hash" in entry:
                hashed_words[entry["hash"]] = entry

        for entry in config.get("spectator_words", []):
            if isinstance(entry, dict) and "hash" in entry:
                hashed_words[entry["hash"]] = entry

        return hashed_words
