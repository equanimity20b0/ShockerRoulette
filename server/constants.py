import os
from enum import Enum

class PunishmentType(str, Enum):
    SHOCK = "shock"
    VIBRATE = "vibrate"
    SOUND = "sound"

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "config.json")
WORDS_PATH = os.path.join(os.path.dirname(__file__), "config", "words.json")

DEFAULT_CONFIG = {
    "punishment_type": PunishmentType.SHOCK.value,
    "intensity": 10,
    "intensity_variance": 3,
    "duration_ms": 1000,
    "duration_variance_ms": 300,
    "cooldown_seconds": 3.0,
    "max_words_per_player": 3,
    "word_add_cooldown_seconds": 60.0,
    "creator_immunity_on_secret": True,
    "word_max_triggers": 3,
    "roulette_rounds": 6,
    "roulette_start_intensity": 10,
    "roulette_max_intensity": 50,
    "roulette_intensity_increment": 5,
    "roulette_current_intensity": 10,
    "roulette_multiplier": 1.5,
    "spectator_max_tokens": 5,
    "spectator_token_recharge_seconds": 60
}

DEFAULT_WORDS = {
    "forbidden_words": ["shock", "roulette"],
    "secret_words": [],
    "spectator_words": []
}
