// Add a new forbidden word to the server
function addBannedWord(event) {
    event.preventDefault();
    const input = document.getElementById('new-banned-word');
    const word = input.value.trim().toLowerCase();
    
    if (!word) return;

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: "add_word",
            word: word
        }));
        input.value = '';
    } else {
        alert("Cannot add word: disconnected from lobby server.");
    }
}

// WebSocket connection manager
function connectWebSocket() {
    if (ws) {
        intentionalClose = true;
        ws.close();
    }
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
    }

    const dot = document.getElementById('server-status-dot');
    const txt = document.getElementById('server-status-text');
    dot.className = 'status-dot-sidebar disconnected';
    txt.innerText = 'Connecting...';
    txt.style.color = '#f59e0b';

    let host = window.location.host || "localhost:8765";
    let protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
    let address = protocol + host;

    addServerLog("server", `Connecting to game server at ${address}...`);

    try {
        ws = new WebSocket(address);

        ws.onopen = () => {
            dot.className = 'status-dot-sidebar connected';
            const cleanUrl = address.replace('ws://', '').replace('wss://', '');
            txt.innerText = 'Connected: ' + cleanUrl;
            txt.style.color = '#a7f3d0';
            addServerLog("server", "Lobby server connection established!");

            // Register
            ws.send(JSON.stringify({
                action: "register",
                name: config.player_name,
                client_sha1: "",
                voice_recog_sha1: ""
            }));

            startHeartbeat();
        };

        ws.onmessage = (e) => {
            const data = JSON.parse(e.data);
            handleServerMessage(data);
        };

        ws.onclose = () => {
            dot.className = 'status-dot-sidebar disconnected';
            txt.innerText = 'Offline';
            txt.style.color = '';
            stopHeartbeat();
            
            if (intentionalClose) {
                intentionalClose = false;
            } else {
                addServerLog("server", "Connection lost. Reconnecting in 5 seconds...");
                reconnectTimeout = setTimeout(connectWebSocket, 5000);
            }
        };

        ws.onerror = (err) => {
            addServerLog("server", "WebSocket connection error.");
        };

    } catch (e) {
        addServerLog("server", `WebSocket connection failed: ${e}`);
        reconnectTimeout = setTimeout(connectWebSocket, 5000);
    }
}

// Process Incoming Server WebSocket events
const serverEventHandlers = {
    welcome: (data) => {
        forbiddenWords = data.forbidden_words || [];
        secretHashes = data.secret_hashes || [];
        maxWords = data.max_words_per_player || 3;
        cooldownSec = data.word_add_cooldown_seconds || 60;
        lobbyPlayers = data.players || [];
        
        addServerLog("server", `Joined lobby. Banned words synced: ${forbiddenWords.join(", ")}`);
        updateMetrics();
        updateLobbyUI();
        updateWordSlotsUI();
        
        startListening();
    },
    add_word_success: (data) => {
        myWordTimestamps.push(Date.now());
        localStorage.setItem('myWordTimestamps', JSON.stringify(myWordTimestamps));
        updateWordSlotsUI();
    },
    player_joined: (data) => {
        addServerLog("server", `Player '${data.name}' joined the game.`);
        lobbyPlayers = data.players || [];
        updateMetrics();
        updateLobbyUI();
        if (typeof pushFeedItem === "function") {
            pushFeedItem("info", "📥", `<strong>${data.name}</strong> joined the lobby`);
        }
    },
    player_left: (data) => {
        addServerLog("server", `Player '${data.name}' disconnected.`);
        lobbyPlayers = data.players || [];
        updateMetrics();
        updateLobbyUI();
        if (typeof pushFeedItem === "function") {
            pushFeedItem("info", "📤", `<strong>${data.name}</strong> left the lobby`);
        }
    },
    telemetry_update: (data) => {
        lobbyPlayers = data.players || [];
        updateLobbyUI();
    },
    words_updated: (data) => {
        forbiddenWords = data.forbidden_words || [];
        secretHashes = data.secret_hashes || [];
        addServerLog("server", data.message || "Forbidden words updated.");
        updateMetrics();
        if (data.message && typeof pushFeedItem === "function") {
            pushFeedItem("trigger", "🚨", data.message);
        }
    },
    punish: (data) => {
        const speaker = data.speaker;
        const word = data.word;
        const type = data.punishment_type || "shock";
        const intensity = data.intensity || 10;
        const durationMs = data.duration_ms || 1000;
        const immuneList = data.immune_players || [];
        
        sessionShocks++;
        updateMetrics();

        const isMe = speaker.toLowerCase() === config.player_name.toLowerCase();
        if (typeof pushFeedItem === "function") {
            pushFeedItem("punish", "⚡", `<strong>${speaker}</strong> spoke forbidden word <strong>'${word}'</strong><br><span style="font-size:11px; opacity:0.85;">Triggered ${type.toUpperCase()} (${intensity}%, ${durationMs}ms)</span>`);
        }

        const isImmune = immuneList.some(imp => imp.toLowerCase() === config.player_name.toLowerCase());
        if (isImmune) {
            addServerLog("server", `Trigger word '${word}' matched speaker '${speaker}', but you are immune!`);
            return;
        }
        
        executePunishment(speaker, word, type, intensity, durationMs);
    },
    roulette: (data) => {
        const seq = data.ticking_sequence || [];
        const delay = data.tick_delay_ms || 350;
        const vib = data.vibrate_intensity || 100;
        
        addServerLog("server", "Roulette triggered! Spinning the wheel...");
        if (typeof pushFeedItem === "function") {
            pushFeedItem("trigger", "🔄", `<strong>Roulette Triggered by ${data.speaker || 'unknown'}!</strong> Spinning the wheel...`);
        }
        runRouletteAnimation(seq, delay, vib);
    },
    error: (data) => {
        addServerLog("server", `Server Error: ${data.message}`);
    }
};

// Process Incoming Server WebSocket events
function handleServerMessage(data) {
    const event = data.event;

    // Stakes level calculations
    if (data.roulette_start_intensity !== undefined) {
        const start = data.roulette_start_intensity || 10;
        const max = data.roulette_max_intensity || 50;
        const current = data.roulette_current_intensity || 10;
        const pct = max > start ? Math.min(100, Math.max(0, ((current - start) / (max - start)) * 100)) : 0;
        
        document.getElementById('stakes-current-val').innerText = current + '%';
        document.getElementById('stakes-progress-bar').style.width = pct + '%';
        document.getElementById('stakes-cap-label').innerText = `Start: ${start}% | Max: ${max}%`;
    }

    const handler = serverEventHandlers[event];
    if (handler) {
        handler(data);
    }
}

// local punishment hardware executor
async function executePunishment(speaker, word, rawType, intensity, durationMs) {
    let type = rawType.toLowerCase();

    if (config.punishment_override === 'vibrate') {
        type = 'vibrate';
        addServerLog("system", "Comfort Override: Shock command clamped to Vibrate.");
    } else if (config.punishment_override === 'sound') {
        type = 'sound';
        addServerLog("system", "Comfort Override: Shock/Vibe command clamped to Beep.");
    }

    const clampedIntensity = Math.min(Math.max(1, intensity), config.max_intensity);
    const clampedDuration = Math.min(Math.max(100, durationMs), config.max_duration_ms);

    addPunishLog(speaker, `Spoke '${word}'! Triggering ${type.toUpperCase()} on collar (${clampedIntensity}%, ${clampedDuration}ms)`);
    
    if (config.api_type === "openshock") {
        await executeOpenShock(type, clampedIntensity, clampedDuration);
    } else {
        console.error("Unsupported api type")
    }
}

// OpenShock Cloud Integration
async function executeOpenShock(type, intensity, durationMs) {
    let token = (config.openshock_token || "").trim();
    let shockerIdStr = (config.shocker_id || "").trim();

    if (!token) {
        addServerLog("server", "OpenShock call failed: API Token is empty.");
        return;
    }

    // TODO: we should clean this up when user inputs it the first time
    if ((token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'"))) {
        token = token.slice(1, -1).trim();
    }
    if ((shockerIdStr.startsWith('"') && shockerIdStr.endsWith('"')) || (shockerIdStr.startsWith("'") && shockerIdStr.endsWith("'"))) {
        shockerIdStr = shockerIdStr.slice(1, -1).trim();
    }

    let shocker_uuids = [];

    const headers = {
        "Content-Type": "application/json"
    };
    if (config.openshock_use_headers !== false) {
        headers["Open-Shock-Token"] = token;
        headers["OpenShockToken"] = token;
        headers["Authorization"] = `Bearer ${token}`;
    }

    const fetchOptions = {
        headers: headers
    };
    if (config.openshock_use_cookies !== false) {
        fetchOptions.credentials = "include";
    }


    shocker_uuids = shockerIdStr.split(",").map(u => {
        u = u.trim();
        if ((u.startsWith('"') && u.endsWith('"')) || (u.startsWith("'") && u.endsWith("'"))) {
            u = u.slice(1, -1).trim();
        }
        return u;
    }).filter(Boolean);


    if (shocker_uuids.length === 0) {
        addServerLog("server", "OpenShock call failed: No target shocker UUIDs found.");
        return;
    }

    // Handle Shocker Selection Mode: Random or All
    const shockerMode = (config.shocker_mode || "all").toLowerCase();
    if (shockerMode === "random" && shocker_uuids.length > 1) {
        const totalCount = shocker_uuids.length;
        const randomIndex = Math.floor(Math.random() * totalCount);
        const selectedUuid = shocker_uuids[randomIndex];
        shocker_uuids = [selectedUuid];
        addServerLog("system", `🎲 Randomized Collar Mode: targeting collar ${randomIndex + 1} of ${totalCount}`);
    }

    let opType = "Sound";
    const lowerType = type.toLowerCase();
    if (lowerType === "vibrate") opType = "Vibrate";
    if (lowerType === "shock") opType = "Shock";
    if (lowerType === "stop") opType = "Stop";

    const shocks = shocker_uuids.map(uuid => ({
        id: uuid,
        type: opType,
        intensity: intensity,
        duration: durationMs,
        exclusive: true
    }));

    const payload = {
        shocks: shocks,
        customName: null
    };

    try {
        addServerLog("system", `Sending ${opType.toUpperCase()} request directly from browser...`);
        const res = await fetch("https://api.openshock.app/2/shockers/control", {
            method: "POST",
            body: JSON.stringify(payload),
            ...fetchOptions
        });

        if (res.ok) {
            addServerLog("system", `OpenShock command executed successfully from browser! Status: ${res.status}`);
        } else {
            const errorText = await res.text();
            addServerLog("server", `OpenShock command failed (Status ${res.status}): ${errorText}`);
        }
    } catch(e) {
        addServerLog("server", `OpenShock browser fetch communication error: ${e}`);
    }
}

// Roulettesequential vibrate ticking
async function runRouletteAnimation(sequence, delayMs, vibrateIntensity) {
    for (let player of sequence) {
        if (player.toLowerCase() === config.player_name.toLowerCase()) {
            let type = "vibrate";
            if (config.punishment_override === "sound") type = "sound";
            const clampedIntensity = Math.min(config.max_intensity, vibrateIntensity);
            
            if (config.api_type === "openshock") {
                executeOpenShock(type, clampedIntensity, 300);
            } else {
                console.error("Unsupported api type")
            }
        }
        
        highlightPlayerRow(player);
        await new Promise(r => setTimeout(r, delayMs));
    }
}

// Heartbeat packets loop
function startHeartbeat() {
    stopHeartbeat();
    heartbeatInterval = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                action: "heartbeat",
                phrases_spoken: totalPhrasesSpoken,
                mic_active: isListening
            }));
        }
    }, 10000);
}

function stopHeartbeat() {
    if (heartbeatInterval) clearInterval(heartbeatInterval);
}

if (typeof globalThis !== 'undefined') {
    globalThis.serverEventHandlers = serverEventHandlers;
}
