import os
import argparse
import asyncio

from voice_recog import VoiceRecog, bcolors
from config_handler import load_client_config
from shocker_client import ShockerClient

# Global configuration path definition
CLIENT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "client_config.json")

def main():
    parser = argparse.ArgumentParser(description="Shocker Roulette Client")
    parser.add_argument("--server", type=str, help="Server IP address")
    parser.add_argument("--name", type=str, help="Your player name")
    parser.add_argument("--shocker", type=str, help="Your shocker identifier (OpenShock UUID or PiShock Share Code)")
    args = parser.parse_args()

    print(f"{bcolors.HEADER}=== Shocker Roulette Client ==={bcolors.ENDC}")
    
    global CLIENT_CONFIG_PATH
    if args.name:
        CLIENT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), f"client_config_{args.name}.json")
        
    config = load_client_config(args.name, args.shocker, CLIENT_CONFIG_PATH)
    
    # Allow command line server IP override
    if args.server:
        config["server_ip"] = args.server
        
    client = ShockerClient(config, CLIENT_CONFIG_PATH)
    
    try:
        asyncio.run(client.connect_and_run())
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        VoiceRecog.end()

if __name__ == "__main__":
    main()
