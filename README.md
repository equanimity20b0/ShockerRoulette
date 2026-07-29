# Shocker Roulette ⚡

A multiplayer social game that uses local speech-to-text to punish **all** connected players with a shock (or vibration/beep) when anyone says a forbidden word.

## Project Structure
- `/server`: Coordinates the lobby status, manages the forbidden word list, and broadcasts punishment requests to all clients.
- `/client`: Captures microphone audio, performs local speech-to-text, checks for forbidden words, serves a local **Client Web UI dashboard**, and executes API commands on the player's collar under local safety limits.

---

## 📦 Setup & Dependencies

Make sure your machine and your friends' machines have the required libraries installed. You can install them by running:

```bash
pip install openshock websockets faster-whisper sounddevice numpy requests
```

> [!NOTE]
> `sounddevice` and `faster_whisper` are used on the client machines to capture audio from the microphone and transcribe it locally.

---

## 🎮 How to Play

### 1. Set Up the Server (The Host)
1. Navigate to the `server/` directory.
2. Start the server once to generate the default configuration:
   ```bash
   python server.py
   ```
3. Open the newly created `server/config.json` file and adjust your lobby settings:
   - **`forbidden_words`**: List the words that players are banned from saying (e.g., `["apple", "banana"]`).
   - **`punishment_type`**: Decide the default server punishment: `"shock"`, `"vibrate"`, or `"sound"`.
   - **`intensity`**: Power level (1-100%). Keep this low (e.g., 5-15%).
   - **`duration_ms`**: Punishment duration in milliseconds (e.g., `1000` = 1 second).
4. Restart `server.py` to apply the config. The server runs on port `8765`.

### 2. Connect the Clients (The Players)
Each player runs their client application to join the lobby.

1. Navigate to the `client/` directory.
2. Start the client:
   ```bash
   python client.py
   ```
3. Once running, open your web browser and navigate to:
   👉 **`http://localhost:5000`**
4. Under the **Client Settings** tab, configure your player name, server IP, API type, credentials, and safety limits.
5. In the **Device Testing** tab, test your collar with a sound or vibration to ensure the connection works.
6. The client will automatically sync the active forbidden word list, start transcribing your speech, and display active logs in the **Lobby Dashboard** tab.

---

## 🛡️ Safety & Safeguards
- **Client-Side Clamping**: Because OpenShock/PiShock API calls are fired locally by the client, your personal safety limits in `client_config.json` act as a hardware guard. If a server request is higher than your caps, the client clamps it before sending it to the collar.
- **PiShock Duration Scaling**: PiShock duration is measured in integer seconds (1-15), while the server runs on milliseconds (e.g., 1000ms). The client automatically converts milliseconds to seconds (`1000ms` -> `1s`) before calling the PiShock API.
- **Personal Comfort Override**: By setting `"punishment_override": "vibrate"` or `"sound"` in your settings, you can play shock-free.
- **Server Cooldown**: A global cooldown prevents rapid-fire shocks if words are repeated in quick succession.
