import sys
import os
import json
import unittest
import asyncio
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

from server import ShockerServer

class MockWebSocket:
    def __init__(self, remote_address="127.0.0.1"):
        self.remote_address = remote_address
        self.closed = False
        self.sent_messages = []

    async def send(self, message):
        self.sent_messages.append(message)

class TestServerRoulette(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ShockerServer()
        self.game_loop = self.server.game_mode

        # Configure deterministic roulette settings for fast test execution
        self.game_loop.config["forbidden_words"] = ["spin"]
        self.game_loop.config["word_max_triggers"] = 1
        self.game_loop.config["roulette_rounds"] = 2
        self.game_loop.config["roulette_current_intensity"] = 20
        self.game_loop.config["roulette_intensity_increment"] = 5
        self.game_loop.config["roulette_max_intensity"] = 50
        self.game_loop.config["roulette_multiplier"] = 1.5
        self.game_loop.config["duration_ms"] = 1000
        self.game_loop.config["duration_variance_ms"] = 0
        self.game_loop.config["cooldown_seconds"] = 0.0
        self.game_loop.update_hashed_words_lookup()

        self.ws_a = MockWebSocket("127.0.0.1:1001")
        self.ws_b = MockWebSocket("127.0.0.1:1002")

        await self.server.handle_register(self.ws_a, {"action": "register", "name": "PlayerA"})
        await self.server.handle_register(self.ws_b, {"action": "register", "name": "PlayerB"})

        self.ws_a.sent_messages.clear()
        self.ws_b.sent_messages.clear()

    @patch("random.choice")
    async def test_roulette_spin_sequence_and_victim_shock(self, mock_random_choice):
        """Mock randomness to pick PlayerB as victim, verifying spin sequence, stakes escalation, and shock delivery."""
        mock_random_choice.return_value = "PlayerB"

        # Trigger word "spin" by PlayerA to initiate Roulette
        await self.game_loop.trigger("PlayerA", word="spin")

        # 1. Verify "spin" is removed from forbidden_words
        self.assertNotIn("spin", self.game_loop.config["forbidden_words"], "Word should be removed from play upon hitting trigger limit")

        # 2. Verify broadcast roulette spin event
        all_broadcasts = [json.loads(m) for m in self.ws_a.sent_messages + self.ws_b.sent_messages]
        roulette_events = [e for e in all_broadcasts if e.get("event") == "roulette"]

        self.assertGreater(len(roulette_events), 0, "Roulette event must be broadcast to clients")
        roulette_event = roulette_events[0]
        self.assertEqual(roulette_event["speaker"], "PlayerA")
        
        # Ticking sequence must end on victim PlayerB
        seq = roulette_event["ticking_sequence"]
        self.assertEqual(seq[-1], "PlayerB", "Ticking sequence must land on chosen victim PlayerB")

        # 3. Verify stakes escalated for next spin: 20% + 5% = 25%
        self.assertEqual(self.game_loop.config["roulette_current_intensity"], 25, "Stakes should escalate from 20% to 25%")

        # 4. Wait for deliver_roulette_shock task to complete (spin delay is ~2.25s)
        await asyncio.sleep(2.8)

        # 5. Verify final punishment broadcast: intensity = 20% * 1.5 = 30%
        updated_broadcasts = [json.loads(m) for m in self.ws_a.sent_messages + self.ws_b.sent_messages]
        roulette_punish_events = [
            e for e in updated_broadcasts 
            if e.get("event") == "punish" and e.get("speaker") == "Roulette Wheel"
        ]

        self.assertGreater(len(roulette_punish_events), 0, "Roulette Wheel punish event should be delivered")
        punish = roulette_punish_events[0]
        self.assertEqual(punish["intensity"], 30, "Roulette shock intensity must equal base stakes (20%) * multiplier (1.5) = 30%")
        self.assertIn("PlayerA", punish.get("immune_players", []), "Non-victim PlayerA must be listed in immune_players so only victim PlayerB receives shock")

if __name__ == "__main__":
    unittest.main()
