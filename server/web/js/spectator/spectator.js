// Spectator Dashboard logic
const socketUrl = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host;
let ws = null;
let rechargeInterval = null;
let rechargeSecondsLeft = 0;

function connect() {
    const dot = document.getElementById('server-status-dot');
    const txt = document.getElementById('server-status-text');

    txt.innerText = "Connecting...";
    dot.className = "status-dot-sidebar disconnected";

    ws = new WebSocket(socketUrl);

    ws.onopen = () => {
        txt.innerText = "Connected";
        dot.className = "status-dot-sidebar connected";
        addLog("System", "WebSocket connection established.");
        
        // Register as spectator client
        ws.send(JSON.stringify({
            action: "register",
            type: "spectator"
        }));
    };

    ws.onclose = () => {
        txt.innerText = "Offline";
        dot.className = "status-dot-sidebar disconnected";
        addLog("System", "WebSocket connection closed. Reconnecting in 3s...");
        setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
        console.error("Socket error: ", err);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleEvent(data);
    };
}

function handleEvent(data) {
    // 1. Process welcome and general status syncs
    if (data.event === "welcome" || data.event === "words_updated" || data.event === "player_joined" || data.event === "player_left" || data.event === "punish" || data.event === "roulette" || data.event === "spectator_status" || data.event === "telemetry_update") {
        // Update players
        if (data.players) {
            updatePlayerList(data.players);
        }
        
        // Update forbidden words list
        if (data.forbidden_words) {
            updateWordsList(data.forbidden_words, data.secret_hashes || []);
        }
        
        // Update stakes
        if (data.roulette_start_intensity !== undefined) {
            updateStakes(data.roulette_start_intensity, data.roulette_max_intensity, data.roulette_current_intensity);
        }
        
        // Update spectator tokens
        if (data.spectator_tokens !== undefined) {
            updateTokens(data.spectator_tokens, data.spectator_max_tokens, data.recharge_seconds_left);
        }
    }

    // 2. Banner and Specific event messaging
    if (data.message) {
        showBanner(data.message);
        addLog("Lobby", data.message);
    }

    if (data.event === "punish") {
        addLog("Punish", `${data.speaker} triggered shock on word '${data.word}'! Power: ${data.intensity}%`);
        if (typeof pushFeedItem === "function") {
            pushFeedItem("punish", "⚡", `<strong>${data.speaker}</strong> spoke forbidden word <strong>'${data.word}'</strong><br><span style="font-size:11px; opacity:0.85;">Triggered ${(data.punishment_type || 'SHOCK').toUpperCase()} (${data.intensity}%, ${data.duration_ms || 1000}ms)</span>`);
        }
    } else if (data.event === "roulette") {
        addLog("Roulette", `Roulette spin sequence initiated by speaker '${data.speaker}'!`);
        if (typeof pushFeedItem === "function") {
            pushFeedItem("trigger", "🔄", `<strong>Roulette Triggered by ${data.speaker || 'unknown'}!</strong> Spinning the wheel...`);
        }
    } else if (data.event === "player_joined") {
        addLog("Server", `Player '${data.name}' joined the game lobby.`);
        if (typeof pushFeedItem === "function") {
            pushFeedItem("info", "📥", `<strong>${data.name}</strong> joined the lobby`);
        }
    } else if (data.event === "player_left") {
        addLog("Server", `Player '${data.name}' left the game lobby.`);
        if (typeof pushFeedItem === "function") {
            pushFeedItem("info", "📤", `<strong>${data.name}</strong> left the lobby`);
        }
    } else if (data.event === "words_updated" && data.message) {
        if (typeof pushFeedItem === "function") {
            pushFeedItem("trigger", "🚨", data.message);
        }
    } else if (data.event === "error") {
        alert("Error from server: " + data.message);
    }
}

function updatePlayerList(players) {
    const container = document.getElementById('player-list-container');
    if (players.length === 0) {
        container.innerHTML = '<div class="table-empty">Nobody online.</div>';
        return;
    }
    container.innerHTML = players.map(p => {
        const pName = typeof p === 'object' ? p.name : p;
        const micActive = typeof p === 'object' ? p.mic_active : false;
        
        let micStatusHtml = '';
        if (typeof p === 'object') {
            if (micActive) {
                micStatusHtml = `<span style="font-size: 9px; padding: 2px 6px; margin-left: 8px; border-radius: 4px; font-weight: bold; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid #10b981;">🎙️ Mic Active</span>`;
            } else {
                micStatusHtml = `<span style="font-size: 9px; padding: 2px 6px; margin-left: 8px; border-radius: 4px; font-weight: bold; background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444;">🔇 Mic Off</span>`;
            }
        }

        return `
            <div class="player-row" style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
                <div class="player-left" style="display: flex; align-items: center; gap: 8px;">
                    <span class="player-dot" style="background-color: ${micActive ? '#10b981' : '#ef4444'};"></span>
                    <span>${pName}</span>
                    ${micStatusHtml}
                </div>
            </div>
        `;
    }).join('');
}

function updateWordsList(forbidden, secretHashes) {
    const list = document.getElementById('forbidden-words-list');
    let html = '';
    
    if (forbidden && forbidden.length > 0) {
        html += forbidden.map(w => `<span class="word-tag">${w}</span>`).join('');
    }
    if (secretHashes && secretHashes.length > 0) {
        html += secretHashes.map(() => `<span class="word-tag secret">?</span>`).join('');
    }
    
    if (html === '') {
        list.innerHTML = '<div class="table-empty">No active forbidden words loaded.</div>';
    } else {
        list.innerHTML = html;
    }
}

function updateStakes(start, max, current) {
    const pct = max > start ? Math.min(100, Math.max(0, ((current - start) / (max - start)) * 100)) : 0;
    document.getElementById('stakes-current-val').innerText = `${current}%`;
    document.getElementById('stakes-progress-bar').style.width = `${pct}%`;
    document.getElementById('stakes-cap-label').innerText = `Start: ${start}% | Max: ${max}%`;
}

function updateTokens(tokens, max, rechargeLeft) {
    document.getElementById('token-label').innerText = `Shared Submitter Tokens: ${tokens}/${max}`;
    const pct = (tokens / max) * 100;
    document.getElementById('token-progress-bar').style.width = `${pct}%`;

    const btn = document.getElementById('submit-btn');
    btn.disabled = (tokens < 1);

    rechargeSecondsLeft = rechargeLeft;
    const rechargeLabel = document.getElementById('recharge-label');
    
    if (tokens >= max) {
        rechargeLabel.innerText = "Pool Full";
        if (rechargeInterval) {
            clearInterval(rechargeInterval);
            rechargeInterval = null;
        }
    } else {
        rechargeLabel.innerText = `Recharging token in ${rechargeSecondsLeft}s`;
        if (!rechargeInterval) {
            rechargeInterval = setInterval(tickRecharge, 1000);
        }
    }
}

function tickRecharge() {
    if (rechargeSecondsLeft > 0) {
        rechargeSecondsLeft--;
        document.getElementById('recharge-label').innerText = `Recharging token in ${rechargeSecondsLeft}s`;
    } else {
        // Countdown ended, request update from server
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: "spectator_ping" }));
        }
    }
}

function submitSpectatorWord(event) {
    event.preventDefault();
    const input = document.getElementById('new-word-input');
    const word = input.value.trim().toLowerCase();
    
    if (!word) return;

    ws.send(JSON.stringify({
        action: "add_spectator_word",
        word: word
    }));

    input.value = '';
    
    // Play notification sound
    try {
        document.getElementById('success-sound').play();
    } catch (e) {}
}

function showBanner(msg) {
    const banner = document.getElementById('lobby-banner');
    banner.innerText = msg;
    banner.style.display = 'flex';
    
    // Auto hide banner after 8s
    setTimeout(() => {
        banner.style.display = 'none';
    }, 8000);
}

function addLog(source, msg) {
    const feed = document.getElementById('log-feed');
    if (feed.querySelector('.table-empty')) {
        feed.innerHTML = '';
    }

    const tr = document.createElement('div');
    tr.className = 'log-row';
    const timeStr = new Date().toLocaleTimeString();
    tr.innerHTML = `
        <span class="log-time">[${timeStr}]</span>
        <span class="log-msg"><strong>${source}:</strong> ${msg}</span>
    `;
    
    feed.appendChild(tr);
    feed.scrollTop = feed.scrollHeight; // auto scroll
}

// Init
connect();
