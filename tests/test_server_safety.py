import sys
import os
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

from server import ShockerServer

class MockWebSocket:
    def __init__(self, remote_address="127.0.0.1"):
        self.remote_address = remote_address
        self.closed = False
        self.sent_messages = []

    async def send(self, message):
        self.sent_messages.append(message)

class TestServerSafetyLimits(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ShockerServer()
        self.game_loop = self.server.game_mode
        self.ws = MockWebSocket("127.0.0.1:1001")
        await self.server.handle_register(self.ws, {"action": "register", "name": "TestPlayer"})
        self.ws.sent_messages.clear()

    async def test_server_intensity_clamping(self):
        """Verify that server intensity calculations never exceed 100%."""
        self.game_loop.config["forbidden_words"] = ["danger"]
        self.game_loop.config["roulette_current_intensity"] = 150 # Excessive intensity
        self.game_loop.config["intensity_variance"] = 50
        self.game_loop.update_hashed_words_lookup()

        await self.game_loop.trigger("TestPlayer", word="danger")

        punish_events = [json.loads(m) for m in self.ws.sent_messages if json.loads(m).get("event") == "punish"]
        self.assertEqual(len(punish_events), 1)
        intensity = punish_events[0]["intensity"]
        self.assertLessEqual(intensity, 100, f"Server intensity ({intensity}%) must not exceed 100%")

    async def test_invalid_punishment_type_fallback(self):
        """Verify that an invalid punishment type falls back safely to 'sound'."""
        self.game_loop.config["forbidden_words"] = ["safe"]
        self.game_loop.config["punishment_type"] = "invalid_mode_xyz"
        self.game_loop.update_hashed_words_lookup()

        await self.game_loop.trigger("TestPlayer", word="safe")

        punish_events = [json.loads(m) for m in self.ws.sent_messages if json.loads(m).get("event") == "punish"]
        self.assertEqual(len(punish_events), 1)
        self.assertEqual(punish_events[0]["punishment_type"], "sound", "Invalid punishment type must fall back to 'sound'")

if __name__ == "__main__":
    unittest.main()
