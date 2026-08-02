import sys
import os
import json
import unittest

# Ensure server directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

from server import ShockerServer

class MockWebSocket:
    def __init__(self, remote_address="127.0.0.1"):
        self.remote_address = remote_address
        self.closed = False
        self.sent_messages = []

    async def send(self, message):
        self.sent_messages.append(message)

class TestServerSecretWords(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ShockerServer()
        self.game_loop = self.server.game_mode
        
        # Reset word lists for clean test environment
        self.game_loop.config["forbidden_words"] = ["erp"]
        self.game_loop.config["secret_words"] = []
        self.game_loop.config["spectator_words"] = []
        self.game_loop.update_hashed_words_lookup()

        # Connect Player A (Issuer) and Player B (Speaker)
        self.ws_a = MockWebSocket("127.0.0.1:1001")
        self.ws_b = MockWebSocket("127.0.0.1:1002")

        await self.server.handle_register(self.ws_a, {"action": "register", "name": "PlayerA"})
        await self.server.handle_register(self.ws_b, {"action": "register", "name": "PlayerB"})
        
        self.ws_a.sent_messages.clear()
        self.ws_b.sent_messages.clear()

    async def test_secret_word_addition_and_migration(self):
        """Test adding secret word by PlayerA, triggering by PlayerB, and migration to public forbidden_words."""
        # 1. PlayerA adds secret word "pineapple"
        await self.game_loop.handle_add_word(self.ws_a, {"word": "pineapple"}, "PlayerA")

        # Verify "pineapple" is in secret_words and NOT in forbidden_words
        secret_entry = next((e for e in self.game_loop.config.get("secret_words", []) if e.get("word") == "pineapple"), None)
        self.assertIsNotNone(secret_entry, "Secret word 'pineapple' should be stored in secret_words")
        self.assertEqual(secret_entry["creator"], "PlayerA", "Creator should be PlayerA (the word issuer)")
        self.assertNotIn("pineapple", self.game_loop.config["forbidden_words"], "Secret word should NOT be in public forbidden_words yet")

        # 2. PlayerB speaks the secret word "pineapple" (via direct hash trigger)
        word_hash = secret_entry["hash"]
        self.ws_a.sent_messages.clear()
        self.ws_b.sent_messages.clear()

        await self.game_loop.trigger("PlayerB", word_hash=word_hash)

        # 3. Verify migration: "pineapple" removed from secret_words and added to forbidden_words
        secret_entry_after = next((e for e in self.game_loop.config.get("secret_words", []) if e.get("word") == "pineapple"), None)
        self.assertIsNone(secret_entry_after, "Secret word should be removed from secret_words after trigger")
        self.assertIn("pineapple", self.game_loop.config["forbidden_words"], "Triggered secret word should be moved to forbidden_words")

        # 4. Verify broadcast payloads
        # PlayerA (issuer) and PlayerB should receive punish event
        all_broadcasts = [json.loads(m) for m in self.ws_a.sent_messages + self.ws_b.sent_messages]
        punish_events = [e for e in all_broadcasts if e.get("event") == "punish"]
        
        self.assertGreater(len(punish_events), 0, "A punish event should be broadcast")
        punish_event = punish_events[0]
        self.assertEqual(punish_event["speaker"], "PlayerB", "Speaker should be PlayerB")
        self.assertEqual(punish_event["word"], "pineapple", "Word should be 'pineapple'")
        self.assertIn("PlayerA", punish_event.get("immune_players", []), "PlayerA (the word issuer) MUST be in immune_players list!")

    async def test_creator_immunity_when_creator_speaks_own_word(self):
        """Test that if PlayerA (creator) speaks their own secret word, creator immunity prevents the trigger."""
        await self.game_loop.handle_add_word(self.ws_a, {"word": "coconut"}, "PlayerA")
        secret_entry = next((e for e in self.game_loop.config.get("secret_words", []) if e.get("word") == "coconut"), None)
        
        self.ws_a.sent_messages.clear()
        self.ws_b.sent_messages.clear()

        # PlayerA speaks their own secret word "coconut"
        await self.game_loop.trigger("PlayerA", word_hash=secret_entry["hash"])

        # Word should remain secret and NOT be moved to forbidden_words
        self.assertIn(secret_entry, self.game_loop.config["secret_words"], "Secret word should remain secret when spoken by creator")
        self.assertNotIn("coconut", self.game_loop.config["forbidden_words"], "Coconut should NOT move to forbidden_words")

        punish_events = [json.loads(m) for m in self.ws_a.sent_messages if json.loads(m).get("event") == "punish"]
        self.assertEqual(len(punish_events), 0, "No punish event should be generated when creator speaks own word")

if __name__ == "__main__":
    unittest.main()
