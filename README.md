# Shocker Roulette

A multiplayer social game that uses local speech-to-text to punish connected players with a shock (or vibration/beep) when anyone says a forbidden word.

## Project Structure
- `/server`: Coordinates the lobby status, manages forbidden and secret word lists, handles spectator HTTP/WebSocket multiplexing on a single port (8765), and broadcasts game events.
- `/client`: Captures microphone audio, performs local speech-to-text, serves a local Client Web UI dashboard (port 5000), and executes API commands on the player's collar under local safety limits.

---

## Setup & Dependencies

Install the required libraries on host and client machines:

```bash
pip install openshock websockets faster-whisper sounddevice numpy requests
```

> [!NOTE]
> `sounddevice` and `faster_whisper` are used on the client machines to capture audio from the microphone and transcribe it locally.

---

## How to Play

### 1. Set Up the Server (The Host)
1. Navigate to the `server/` directory.
2. Start the server once to generate the default configuration:
   ```bash
   python server.py
   ```
3. Open the newly created `server/config.json` file and adjust your lobby settings:
   - **`forbidden_words`**: List the words that players are banned from saying.
   - **`punishment_type`**: Decide the default server punishment: `"shock"`, `"vibrate"`, or `"sound"`.
   - **`intensity`**: Power level (1-100%). Keep this low (e.g., 5-15%).
   - **`duration_ms`**: Punishment duration in milliseconds (e.g., `1000` = 1 second).
4. Restart `server.py` to apply the config. Both WebSocket and HTTP services run multiplexed on port `8765`.

### 2. Connect the Clients (The Players)
Each player runs their client application to join the lobby.
1. Navigate to the `client/` directory.
2. Start the client:
   ```bash
   python client.py
   ```
3. Once running, open your web browser and navigate to:
   **`http://localhost:5000`**
4. Under the **Settings** tab, configure your player name, server IP, API type, credentials, and safety limits.
5. In the **Device Testing** tab, test your collar with a sound or vibration to ensure the connection works.
6. The client will automatically sync the active forbidden word list, start transcribing your speech, and display active logs in the **Lobby Dashboard** tab.

### 3. Join as a Spectator
Anyone can join the game as a spectator without installing any files.
1. Open a web browser and navigate to the server's IP and port:
   **`http://<server-ip>:8765/`**
2. Spectators can view active player names, live roulette stakes, public forbidden words, and the lobby event log.
3. **Cooperative Trap Words**: Spectators share a pool of rechargeable tokens. You can use a token to submit a secret trap word. These words are hidden (rendered as `?` cards) from the players. If any player speaks a secret trap word:
   - The speaker is punished immediately.
   - The word is revealed and migrated to the public forbidden list, where it escalates the roulette stakes.

---

## Safety & Safeguards

- **Local Hardware Cap Assertions**: The client enforces local safety intensity and duration limits. If a rogue or misconfigured server commands a shock exceeding the local `max_intensity` or `max_duration_ms` values, the client program immediately terminates execution to protect the user.
- **Client Configuration Validation**: Strict type and range validation is enforced on configuration updates (rejecting `max_intensity` values outside `1-100` and `max_duration` values outside `100-15000ms`).
- **Word Submission Validation**: The server filters and rejects punctuation-only word submissions (e.g., `","` or `"!?"`) to prevent wasting slots or spectator tokens.
- **PiShock Duration Scaling**: PiShock duration is measured in integer seconds (1-15), while the server runs on milliseconds. The client automatically converts milliseconds to seconds (`1000ms` -> `1s`) before calling the PiShock API.
- **Personal Comfort Override**: By setting `"punishment_override": "vibrate"` or `"sound"` in your settings, you can play shock-free.
- **Server Cooldown**: A global cooldown prevents rapid-fire shocks if words are repeated in quick succession.
