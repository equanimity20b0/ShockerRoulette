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

class TestServerWordSync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ShockerServer()
        self.game_loop = self.server.game_mode
        self.game_loop.config["forbidden_words"] = []
        self.game_loop.config["secret_words"] = []
        self.game_loop.config["spectator_words"] = []
        self.game_loop.update_hashed_words_lookup()

        self.ws_a = MockWebSocket("127.0.0.1:1001")
        self.ws_b = MockWebSocket("127.0.0.1:1002")
        self.ws_spec = MockWebSocket("127.0.0.1:1003")

        await self.server.handle_register(self.ws_a, {"action": "register", "name": "PlayerA"})
        await self.server.handle_register(self.ws_b, {"action": "register", "name": "PlayerB"})
        await self.server.handle_register(self.ws_spec, {"action": "register", "type": "spectator"})

        self.ws_a.sent_messages.clear()
        self.ws_b.sent_messages.clear()
        self.ws_spec.sent_messages.clear()

    async def test_add_word_sync_broadcast_to_players_and_spectators(self):
        """Verify adding a secret word broadcasts words_updated with secret_hashes to all connected clients."""
        await self.game_loop.handle_action(self.ws_a, "add_word", {"word": "avocado"}, "PlayerA")

        # Collect all words_updated events sent to ws_a, ws_b, and ws_spec
        events_a = [json.loads(m) for m in self.ws_a.sent_messages if json.loads(m).get("event") == "words_updated"]
        events_b = [json.loads(m) for m in self.ws_b.sent_messages if json.loads(m).get("event") == "words_updated"]
        events_spec = [json.loads(m) for m in self.ws_spec.sent_messages if json.loads(m).get("event") == "words_updated"]

        self.assertGreaterEqual(len(events_a), 1, "PlayerA (issuer) must receive words_updated event")
        self.assertGreaterEqual(len(events_b), 1, "PlayerB must receive words_updated sync event")
        self.assertGreaterEqual(len(events_spec), 1, "Spectator must receive words_updated sync event")

        # Verify secret_hashes in broadcast contains the hash of avocado
        secret_hashes = events_b[0]["secret_hashes"]
        self.assertEqual(len(secret_hashes), 1, "Secret hashes count must be 1")

    async def test_secret_word_trigger_migrates_word_to_public_forbidden_words_sync(self):
        """Verify triggering a secret word updates secret_hashes and appends word to forbidden_words in broadcast."""
        # 1. PlayerA adds secret word "banana"
        await self.game_loop.handle_action(self.ws_a, "add_word", {"word": "banana"}, "PlayerA")

        self.ws_a.sent_messages.clear()
        self.ws_b.sent_messages.clear()
        self.ws_spec.sent_messages.clear()

        # Get hash of banana
        banana_entry = self.game_loop.config["secret_words"][0]
        banana_hash = banana_entry["hash"]

        # 2. PlayerB speaks "banana", sending trigger hash
        await self.game_loop.handle_action(self.ws_b, "trigger", {"hash": banana_hash}, "PlayerB")

        events_a = [json.loads(m) for m in self.ws_a.sent_messages if json.loads(m).get("event") == "words_updated"]
        events_b = [json.loads(m) for m in self.ws_b.sent_messages if json.loads(m).get("event") == "words_updated"]
        events_spec = [json.loads(m) for m in self.ws_spec.sent_messages if json.loads(m).get("event") == "words_updated"]

        self.assertGreater(len(events_a), 0, "PlayerA must receive words_updated on trigger")
        self.assertGreater(len(events_b), 0, "PlayerB must receive words_updated on trigger")
        self.assertGreater(len(events_spec), 0, "Spectator must receive words_updated on trigger")

        forbidden_words = events_b[-1]["forbidden_words"]
        secret_hashes = events_b[-1]["secret_hashes"]

        self.assertIn("banana", forbidden_words, "Triggered word 'banana' must be migrated to public forbidden_words list")
        self.assertNotIn(banana_hash, secret_hashes, "Triggered hash must be removed from secret_hashes list")

if __name__ == "__main__":
    unittest.main()
