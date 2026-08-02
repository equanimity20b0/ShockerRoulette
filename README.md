# Shocker Roulette

A multiplayer social game that uses local speech-to-text to punish connected players with a shock (or vibration/beep) when anyone says a forbidden word.

## Project Structure
- `/server`: Coordinates the lobby status, manages forbidden and secret word lists, handles spectator HTTP/WebSocket multiplexing on a single port (8765), and broadcasts game events.
- `/server/web/js`: as of now, the client web-based side of the game... I will update with more instructions once done refactoring

---

## Setup & Dependencies
Just need to install dependencies

### Bare Metal
```bash
python pip install -r server/server_requirements.txt
```

### Docker
```bash
 docker build -t shocker-roulette-server .
```
---

## How to Play

### 1. Set Up the Server (The Host) on Bare Metal
1. Navigate to the `server/` directory.
2. Start the server once to generate the default configuration:
   ```bash
   python server.py
   ```

### 1. Set Up on Docker
1. Start up the docker image
   ```bash
   docker run -d -p 8765:8765 --name roulette-server shocker-roulette-server
   ```

### 2. Connect the Clients (The Players)
Players can connect by going to the hosts ip addres or web url.
From there they can setup and start playing!

---

## Safety & Safeguards

- **Local Hardware Cap Assertions**: The client enforces local safety intensity and duration limits. If a rogue or misconfigured server commands a shock exceeding the local `max_intensity` or `max_duration_ms` values, the client program immediately terminates execution to protect the user.
- **Client Configuration Validation**: Strict type and range validation is enforced on configuration updates (rejecting `max_intensity` values outside `1-100` and `max_duration` values outside `100-15000ms`).
- **Word Submission Validation**: The server filters and rejects punctuation-only word submissions (e.g., `","` or `"!?"`) to prevent wasting slots or spectator tokens.
- **PiShock Duration Scaling**: PiShock duration is measured in integer seconds (1-15), while the server runs on milliseconds. The client automatically converts milliseconds to seconds (`1000ms` -> `1s`) before calling the PiShock API.
- **Personal Comfort Override**: By setting `"punishment_override": "vibrate"` or `"sound"` in your settings, you can play shock-free.
- **Server Cooldown**: A global cooldown prevents rapid-fire shocks if words are repeated in quick succession.
