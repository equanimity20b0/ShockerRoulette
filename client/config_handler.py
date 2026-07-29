import os
import json
import logging

logger = logging.getLogger("Client")

DEFAULT_CLIENT_CONFIG = {
    "player_name": "Player",
    "server_ip": "localhost",                     # Server host IP
    "api_type": "openshock",                     # "openshock" or "pishock"
    "openshock_token": "your_openshock_token_here",
    "shocker_id": "your_shocker_uuid_here",
    "pishock_username": "your_pishock_username_here",
    "pishock_api_key": "your_pishock_api_key_here",
    "pishock_share_code": "your_pishock_share_code_here",
    "max_intensity": 15,                         # Safety cap (1-100)
    "max_duration_ms": 2000,                     # Safety cap in milliseconds
    "punishment_override": None                 # Force "vibrate" or "sound" for personal comfort, or null
}

def load_client_config(name_arg, shocker_arg, config_path) -> dict:
    config = DEFAULT_CLIENT_CONFIG.copy()
    
    # Load config file if it exists
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                file_config = json.load(f)
                config.update(file_config)
            logger.info("Loaded client config from file.")
        except Exception as e:
            print(f"Error loading config file: {e}")
    else:
        # Create default config file if it doesn't exist
        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=4)
            print(f"Created default configuration file at {config_path}")
        except Exception as e:
            print(f"Failed to create config file: {e}")

    # Validate/Prompt API Type
    if config["api_type"].lower() not in ["openshock", "pishock"]:
        api_type_input = input("Choose Shocker API type (openshock/pishock): ").strip().lower()
        while api_type_input not in ["openshock", "pishock"]:
            api_type_input = input("Invalid choice. Enter openshock or pishock: ").strip().lower()
        config["api_type"] = api_type_input

    # Validate/Prompt Player Name
    if config["player_name"] == "Player" or not config["player_name"]:
        if name_arg:
            config["player_name"] = name_arg
        else:
            config["player_name"] = input("Enter your player name: ").strip()
            while not config["player_name"]:
                config["player_name"] = input("Player name cannot be empty. Enter name: ").strip()

    # Prompts for OpenShock
    if config["api_type"] == "openshock":
        if config["openshock_token"] == "your_openshock_token_here" or not config["openshock_token"]:
            config["openshock_token"] = input("Enter your OpenShock API token: ").strip()
            while not config["openshock_token"]:
                config["openshock_token"] = input("API token cannot be empty: ").strip()

        if config["shocker_id"] == "your_shocker_uuid_here" or not config["shocker_id"]:
            if shocker_arg:
                config["shocker_id"] = shocker_arg
            else:
                config["shocker_id"] = input("Enter your OpenShock Shocker ID (UUID): ").strip()
                while not config["shocker_id"]:
                    config["shocker_id"] = input("Shocker ID cannot be empty. Enter ID: ").strip()

    # Prompts for PiShock
    elif config["api_type"] == "pishock":
        if config["pishock_username"] == "your_pishock_username_here" or not config["pishock_username"]:
            config["pishock_username"] = input("Enter your PiShock Username: ").strip()
            while not config["pishock_username"]:
                config["pishock_username"] = input("Username cannot be empty: ").strip()

        if config["pishock_api_key"] == "your_pishock_api_key_here" or not config["pishock_api_key"]:
            config["pishock_api_key"] = input("Enter your PiShock API Key: ").strip()
            while not config["pishock_api_key"]:
                config["pishock_api_key"] = input("API Key cannot be empty: ").strip()

        if config["pishock_share_code"] == "your_pishock_share_code_here" or not config["pishock_share_code"]:
            if shocker_arg:
                config["pishock_share_code"] = shocker_arg
            else:
                config["pishock_share_code"] = input("Enter your PiShock Share Code: ").strip()
                while not config["pishock_share_code"]:
                    config["pishock_share_code"] = input("Share Code cannot be empty. Enter ID: ").strip()

    # Save configuration changes back to file
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
    except Exception:
        pass

    return config
