import os
import string
import json
import threading
from enum import Enum
import requests
from openshock import OpenShockClient, Control
from voice_recog import bcolors

class PunishmentType(str, Enum):
    SHOCK = "shock"
    VIBRATE = "vibrate"
    SOUND = "sound"

class HardwareManager:
    def __init__(self):
        self.openshock_client = None

    def init_openshock(self):
        if not self.config["openshock_token"] or "your_" in self.config["openshock_token"]:
            return
        try:
            self.openshock_client = OpenShockClient(api_token=self.config["openshock_token"])
        except Exception as e:
            if hasattr(self, 'add_log'):
                self.add_log("server", f"Could not initialize OpenShock: {e}")
            self.openshock_client = None

    def execute_punishment(self, speaker: str, word: str, punishment_type: PunishmentType, intensity: int, duration_ms: int):
        """Processes and triggers the punishment command locally using safety clamps."""
        self.session_shocks += 1
        personal_override = self.config.get("punishment_override")
        
        op_str = punishment_type.value if isinstance(punishment_type, PunishmentType) else str(punishment_type)
        raw_op = personal_override if personal_override else op_str
        final_op = raw_op.strip().lower()
        
        # Apply safety limits
        local_max_intensity = self.config.get("max_intensity", 15)
        local_max_duration = self.config.get("max_duration_ms", 2000)
        
        clamped_duration_ms = min(max(100, duration_ms), local_max_duration)
        if final_op == "shock":
            clamped_intensity = min(max(1, intensity), local_max_intensity)
        else:
            clamped_intensity = min(max(1, intensity), 100)

        print(f"\n{bcolors.FAIL}{'='*60}")
        print(f"💥 PUNISHMENT BROADCAST 💥")
        print(f"{speaker} said the forbidden word: '{word}'!")
        if personal_override:
            print(f"Personal Override Active: Converted server '{punishment_type}' to '{personal_override}'")
        print(f"Action: Triggering {final_op.upper()} ({clamped_intensity}% for {clamped_duration_ms}ms) on your collar!")
        print(f"{'='*60}{bcolors.ENDC}\n")

        # Execute
        if self.api_type == "openshock":
            self._execute_openshock(final_op, clamped_intensity, clamped_duration_ms)
        elif self.api_type == "pishock":
            self._execute_pishock(final_op, clamped_intensity, clamped_duration_ms)

    def execute_test_command(self, test_type: str, intensity: int, duration_ms: int):
        """Triggers local manual test with limits applied."""
        local_max_intensity = self.config.get("max_intensity", 15)
        local_max_duration = self.config.get("max_duration_ms", 2000)
        
        clamped_duration_ms = min(max(100, duration_ms), local_max_duration)
        test_op = test_type.strip().lower()
        if test_op == "shock":
            clamped_intensity = min(max(1, intensity), local_max_intensity)
        else:
            clamped_intensity = min(max(1, intensity), 100)
            
        if self.api_type == "openshock":
            self._execute_openshock(test_type, clamped_intensity, clamped_duration_ms)
        elif self.api_type == "pishock":
            self._execute_pishock(test_type, clamped_intensity, clamped_duration_ms)

    def _execute_openshock(self, op_type: str, intensity: int, duration_ms: int):
        """Send command to OpenShock API."""
        if not self.openshock_client:
            print(f"{bcolors.FAIL}Error: OpenShock client not initialized.{bcolors.ENDC}")
            return
            
        op_map = {
            "sound": "Sound",
            "beep": "Sound",
            "vibrate": "Vibrate",
            "shock": "Shock"
        }
        normalized_op = op_map.get(op_type.lower(), "Sound")
        
        # Hard Security Assert: block API execution if intensity exceeds cap
        local_max_intensity = self.config.get("max_intensity", 15)
        if normalized_op == "Shock":
            assert intensity <= local_max_intensity, f"you have been freed from the game, your shocker limits were violated (intensity {intensity}% exceeds cap {local_max_intensity}%)"
            
        shocker_id_str = self.config.get("shocker_id", "").strip()
        use_auto_discovery = shocker_id_str.lower() in ("", "all", "auto", "detect")

        shocker_uuids = []
        try:
            own_shockers = self.openshock_client.shockers.list_own()
            name_to_uuid = {}
            for s in own_shockers:
                if isinstance(s, dict):
                    s_id, s_name = s.get("id"), s.get("name")
                else:
                    s_id, s_name = getattr(s, "id", None), getattr(s, "name", None)
                
                if s_id:
                    name_to_uuid[s_name.strip().lower() if s_name else ""] = s_id
                    
            if use_auto_discovery:
                shocker_uuids = list(name_to_uuid.values())
                print(f"{bcolors.OKGREEN}Auto Discovery: Detected {len(shocker_uuids)} registered shocker(s) on your account.{bcolors.ENDC}")
                if hasattr(self, 'add_log'):
                    self.add_log("server", f"Auto-discovered {len(shocker_uuids)} shockers.")
            else:
                shocker_uuids_or_names = [u.strip() for u in shocker_id_str.split(",") if u.strip()]
                import re
                UUID_REGEX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
                
                for item in shocker_uuids_or_names:
                    item_lower = item.lower()
                    if item_lower in name_to_uuid:
                        shocker_uuids.append(name_to_uuid[item_lower])
                    elif UUID_REGEX.match(item):
                        shocker_uuids.append(item)
                    else:
                        print(f"{bcolors.WARNING}Warning: '{item}' is not a valid UUID and does not match any registered nickname. Skipping.{bcolors.ENDC}")
                        if hasattr(self, 'add_log'):
                            self.add_log("server", f"Skipped invalid shocker: '{item}'")
        except Exception as e:
            print(f"Failed to fetch own shockers list: {e}.")
            if use_auto_discovery:
                print(f"{bcolors.FAIL}Error: Auto-discovery failed because the account shocker list could not be retrieved.{bcolors.ENDC}")
                return
            else:
                shocker_uuids_or_names = [u.strip() for u in shocker_id_str.split(",") if u.strip()]
                import re
                UUID_REGEX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
                shocker_uuids = [u for u in shocker_uuids_or_names if UUID_REGEX.match(u)]

        if not shocker_uuids:
            print(f"{bcolors.FAIL}Error: No valid shockers selected or discovered.{bcolors.ENDC}")
            return

        # Handle Shocker Selection Mode: Random or All
        shocker_mode = self.config.get("shocker_mode", "all").lower()
        if shocker_mode == "random" and len(shocker_uuids) > 1:
            import random
            selected_uuid = random.choice(shocker_uuids)
            shocker_uuids = [selected_uuid]
            print(f"{bcolors.OKBLUE}[Hardware] Random selection: targeting shocker '{selected_uuid}'{bcolors.ENDC}")
            if hasattr(self, 'add_log'):
                self.add_log("server", f"Collar selection randomized to: {selected_uuid}")

        try:
            cmds = []
            for uuid in shocker_uuids:
                cmds.append(Control(
                    id=uuid,
                    type=normalized_op,
                    intensity=intensity,
                    duration=duration_ms
                ))
            
            def run_api_call():
                try:
                    self.openshock_client.shockers.control(cmds)
                except Exception as e:
                    if hasattr(self, 'add_log'):
                        self.add_log("server", f"OpenShock API call failed: {e}")
                    print(f"\n{bcolors.FAIL}Failed to execute OpenShock command: {e}{bcolors.ENDC}\n")

            threading.Thread(target=run_api_call, daemon=True).start()
        except Exception as e:
            print(f"{bcolors.FAIL}Failed to prepare OpenShock command: {e}{bcolors.ENDC}")

    def _execute_pishock(self, op_type: str, intensity: int, duration_ms: int):
        """Send command to PiShock API for one or more share codes."""
        username = self.config.get("pishock_username")
        api_key = self.config.get("pishock_api_key")
        share_code_str = self.config.get("pishock_share_code", "")
        share_codes = [c.strip() for c in share_code_str.split(",") if c.strip()]

        # Handle Shocker Selection Mode: Random or All
        shocker_mode = self.config.get("shocker_mode", "all").lower()
        if shocker_mode == "random" and len(share_codes) > 1:
            import random
            selected_code = random.choice(share_codes)
            share_codes = [selected_code]
            print(f"{bcolors.OKBLUE}[Hardware] Random selection: targeting PiShock code '{selected_code}'{bcolors.ENDC}")
            if hasattr(self, 'add_log'):
                self.add_log("server", f"PiShock code randomized to: {selected_code}")

        if not username or not api_key or not share_codes or "your_" in username or "your_" in api_key:
            if hasattr(self, 'add_log'):
                self.add_log("server", "PiShock call failed: Credentials not configured.")
            print(f"{bcolors.FAIL}Error: PiShock credentials are not configured in client_config.json.{bcolors.ENDC}")
            return

        duration_sec = max(1, min(round(duration_ms / 1000.0), 15))
        op_map = {
            "shock": 0,
            "vibrate": 1,
            "sound": 2,
            "beep": 2
        }
        op_code = op_map.get(op_type.lower(), 2)

        # Hard Security Assert: block API execution if intensity exceeds cap
        local_max_intensity = self.config.get("max_intensity", 15)
        if op_code == 0:  # 0 is Shock
            assert intensity <= local_max_intensity, f"you have been freed from the game, you shocker limits were violated (intensity {intensity}% exceeds cap {local_max_intensity}%)"

        def send_pishock_request(code):
            payload = {
                "Username": username,
                "Apikey": api_key,
                "Code": code,
                "Name": "Shocker Roulette Client",
                "Op": op_code,
                "Intensity": intensity,
                "Duration": duration_sec
            }
            try:
                r = requests.post("https://do.pishock.com/api/apioperate/", json=payload, timeout=10)
                if r.status_code == 200:
                    response_text = r.text.strip()
                    if response_text == "Operation Attempted.":
                        pass
                    elif response_text == "Shocker is Paused.":
                        if hasattr(self, 'add_log'):
                            self.add_log("server", f"PiShock collar ({code}) is paused on pishock.com.")
                        print(f"\n{bcolors.WARNING}PiShock ({code}): Shocker is paused on PiShock.com.{bcolors.ENDC}\n")
                    else:
                        if hasattr(self, 'add_log'):
                            self.add_log("server", f"PiShock ({code}) API error: {response_text}")
                        print(f"\n{bcolors.FAIL}PiShock ({code}) API Response: {response_text}{bcolors.ENDC}\n")
                else:
                    if hasattr(self, 'add_log'):
                        self.add_log("server", f"PiShock ({code}) HTTP error: {r.status_code}")
                    print(f"\n{bcolors.FAIL}PiShock ({code}) HTTP Error: {r.status_code} - {r.text[:200]}{bcolors.ENDC}\n")
            except Exception as e:
                if hasattr(self, 'add_log'):
                    self.add_log("server", f"Failed connecting to PiShock ({code}): {e}")
                print(f"\n{bcolors.FAIL}Failed to connect to PiShock API ({code}): {e}{bcolors.ENDC}\n")

        for code in share_codes:
            threading.Thread(target=send_pishock_request, args=(code,), daemon=True).start()
