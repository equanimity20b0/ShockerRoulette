import http.server
import os
import json
import hashlib
import asyncio
import string

class ClientHTTPServer(http.server.BaseHTTPRequestHandler):
    client_instance = None
    
    def log_message(self, format, *args):
        # Mute standard HTTP logging to keep console clear
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html_path = os.path.join(os.path.dirname(__file__), "web", "index.html")
            try:
                with open(html_path, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            except Exception as e:
                self.wfile.write(f"Error loading index.html: {e}".encode("utf-8"))
                
        elif self.path.startswith("/sound/"):
            filename = os.path.basename(self.path)
            sound_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sound", filename)
            if os.path.exists(sound_path) and os.path.isfile(sound_path):
                self.send_response(200)
                if filename.lower().endswith(".wav"):
                    self.send_header("Content-Type", "audio/wav")
                elif filename.lower().endswith(".mp3"):
                    self.send_header("Content-Type", "audio/mpeg")
                self.end_headers()
                with open(sound_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            status = {
                "player_name": self.client_instance.player_name,
                "server_url": self.client_instance.server_url,
                "connected": self.client_instance.websocket is not None and not self.client_instance.websocket.closed,
                "forbidden_words": self.client_instance.forbidden_words,
                "players": self.client_instance.players_in_lobby,
                "session_shocks": self.client_instance.session_shocks,
                "secret_words_count": self.client_instance.secret_words_count,
                "max_words_per_player": self.client_instance.max_words_per_player,
                "word_add_cooldown_seconds": self.client_instance.word_add_cooldown_seconds,
                "logs": self.client_instance.logs,
                "config": self.client_instance.config
            }
            self.wfile.write(json.dumps(status).encode("utf-8"))
        elif self.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.client_instance.config).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == "/api/config":
            try:
                new_config = json.loads(post_data.decode("utf-8"))
                self.client_instance.update_config(new_config)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        elif self.path == "/api/test":
            try:
                test_params = json.loads(post_data.decode("utf-8"))
                test_type = test_params.get("type", "sound")
                intensity = int(test_params.get("intensity", 10))
                duration_ms = int(test_params.get("duration_ms", 1000))
                
                self.client_instance.execute_test_command(test_type, intensity, duration_ms)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        elif self.path == "/api/add_word":
            try:
                params = json.loads(post_data.decode("utf-8"))
                word = params.get("word", "").strip()
                if not word:
                    raise ValueError("Word cannot be empty.")
                
                if not self.client_instance.websocket or self.client_instance.websocket.closed:
                    raise ConnectionError("Not connected to game server.")
                
                msg = {
                    "action": "add_word",
                    "word": word
                }
                asyncio.run_coroutine_threadsafe(
                    self.client_instance.websocket.send(json.dumps(msg)),
                    self.client_instance.loop
                )
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
