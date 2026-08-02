// Multi-Collar Trigger Mode Segmented Switch Controller
function setShockerMode(mode) {
    const hiddenInput = document.getElementById('shocker_mode');
    if (hiddenInput) hiddenInput.value = mode;
    document.querySelectorAll('#shocker-mode-toggle .segmented-option').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-value') === mode);
    });
}

// Personal Comfort Override MUX Button Select Controller
function setComfortOverride(val) {
    const hiddenInput = document.getElementById('punishment_override');
    if (hiddenInput) hiddenInput.value = val;
    document.querySelectorAll('#comfort-override-mux .mux-option').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-value') === val);
    });
}

// Switch between tabs
function switchTab(tabId) {
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
    
    const navItem = document.getElementById(`nav-${tabId}`);
    if (navItem) navItem.classList.add('active');
    
    const panel = document.getElementById(`tab-${tabId}`);
    if (panel) panel.classList.add('active');
}

// Log tab switching (Speech / Server)
function switchLogTab(tab) {
    document.getElementById('log-panel-speech').style.display = tab === 'speech' ? 'block' : 'none';
    document.getElementById('log-panel-server').style.display = tab === 'server' ? 'block' : 'none';
    document.getElementById('log-tab-speech').classList.toggle('active', tab === 'speech');
    document.getElementById('log-tab-server').classList.toggle('active', tab === 'server');
}

function clearCurrentLog(event) {
    if (event) event.preventDefault();
    if (document.getElementById('log-panel-speech').style.display !== 'none') {
        clearSpeechLogs(event);
    } else {
        clearServerLogs(event);
    }
}

// Navigate to settings with cog redirection
function goToSettings(event) {
    if (event) event.preventDefault();
    switchTab('settings');
}

// Navigate to safety tab with cog redirection
function goToSafety(event) {
    if (event) event.preventDefault();
    switchTab('safety');
}

// Clear Speech log entries
function clearSpeechLogs(event) {
    if (event) event.preventDefault();
    speechLogs = [];
    renderLogs();
}

// Clear Server log entries
function clearServerLogs(event) {
    if (event) event.preventDefault();
    serverLogs = [];
    renderLogs();
}

// Metrics Card Renderer
function updateMetrics() {
    const publicCount = forbiddenWords.length;
    const secretCount = secretHashes.length;
    const currentTotal = publicCount + secretCount;

    document.getElementById('metric-words').innerText = currentTotal;
    document.getElementById('metric-players').innerText = lobbyPlayers.length;
    document.getElementById('metric-mode').innerText = config.api_type ? config.api_type.toUpperCase() : 'NONE';
    document.getElementById('metric-shocks').innerText = sessionShocks;

    lastTotalWords = currentTotal;

    const playerCountSub = document.getElementById('player-count-sub');
    if (playerCountSub) playerCountSub.innerText = `${lobbyPlayers.length} online`;

    // Render Forbidden words danger tags
    const wordsList = document.getElementById('forbidden-words-list');
    let tagsHtml = '';
    if (forbiddenWords.length > 0) {
        tagsHtml += forbiddenWords.map(w => `<span class="word-tag">${w}</span>`).join('');
    }
    if (secretHashes.length > 0) {
        for (let i = 0; i < secretHashes.length; i++) {
            tagsHtml += `<span class="word-tag secret">?</span>`;
        }
    }
    if (tagsHtml !== '') {
        wordsList.innerHTML = tagsHtml;
    } else {
        wordsList.innerHTML = '<span class="table-empty">No active forbidden words loaded.</span>';
    }
}

// Word limit slot progress calculations
function updateWordSlotsUI() {
    const now = Date.now();
    myWordTimestamps = myWordTimestamps.filter(t => now - t < cooldownSec * 1000);
    localStorage.setItem('myWordTimestamps', JSON.stringify(myWordTimestamps));

    const remaining = Math.max(0, maxWords - myWordTimestamps.length);
    const pct = (remaining / maxWords) * 100;
    
    const progressBar = document.getElementById('player-token-progress-bar');
    if (progressBar) {
        progressBar.style.width = `${pct}%`;
    }
    
    const tokenLabel = document.getElementById('player-token-label');
    if (tokenLabel) {
        tokenLabel.innerText = `My Word Slots: ${remaining}/${maxWords}`;
    }
    
    const rechargeLabel = document.getElementById('player-recharge-label');
    let secondsLeft = 0;
    if (remaining < maxWords && myWordTimestamps.length > 0) {
        const oldest = Math.min(...myWordTimestamps);
        secondsLeft = Math.max(0, Math.ceil(((oldest + cooldownSec * 1000) - now) / 1000));
    }

    if (rechargeLabel) {
        if (remaining >= maxWords) {
            rechargeLabel.innerText = "Pool Full";
        } else {
            rechargeLabel.innerText = `Slot recharge in ${secondsLeft}s`;
        }
    }

    const addBtn = document.querySelector('#add-word-form button[type="submit"]');
    if (addBtn) {
        if (remaining === 0) {
            addBtn.disabled = true;
            addBtn.innerText = `Wait ${secondsLeft}s`;
            addBtn.style.opacity = '0.5';
            addBtn.style.cursor = 'not-allowed';
        } else {
            addBtn.disabled = false;
            addBtn.innerText = `➕ Add Word`;
            addBtn.style.opacity = '';
            addBtn.style.cursor = '';
        }
    }
}

// Sync visual Connected players list
function updateLobbyUI() {
    const playerList = document.getElementById('lobby-player-list');
    if (lobbyPlayers.length > 0) {
        playerList.innerHTML = lobbyPlayers.map(p => {
            const pName = typeof p === 'object' ? p.name : p;
            const micActive = typeof p === 'object' ? p.mic_active : false;
            const isMe = pName.toLowerCase() === config.player_name.toLowerCase();
            
            let micStatusHtml = '';
            if (typeof p === 'object') {
                if (micActive) {
                    micStatusHtml = `<span style="font-size: 9px; padding: 2px 6px; margin-left: 8px; border-radius: 4px; font-weight: bold; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid #10b981;">🎙️ Mic Active</span>`;
                } else {
                    micStatusHtml = `<span style="font-size: 9px; padding: 2px 6px; margin-left: 8px; border-radius: 4px; font-weight: bold; background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444;">🔇 Mic Off</span>`;
                }
            }

            return `
                <div class="player-row" style="display: flex; align-items: center; justify-content: space-between;">
                    <div class="player-left" style="display: flex; align-items: center; gap: 8px;">
                        <span class="player-dot" style="background-color: ${micActive ? 'var(--success)' : 'var(--danger)'};"></span>
                        <span>${pName}</span>
                        ${micStatusHtml}
                    </div>
                    ${isMe ? '<span class="player-badge">You</span>' : ''}
                </div>
            `;
        }).join('');
    } else {
        playerList.innerHTML = '<div class="table-empty">Nobody connected yet.</div>';
    }
}

function highlightPlayerRow(name) {
    const rows = document.querySelectorAll(".player-row");
    rows.forEach(row => {
        const label = row.querySelector("span:not(.player-dot):not(.player-badge)");
        if (label && label.innerText.toLowerCase() === name.toLowerCase()) {
            row.style.backgroundColor = "rgba(59, 130, 246, 0.25)";
            setTimeout(() => {
                row.style.backgroundColor = "";
            }, 300);
        }
    });
}

// Logs display rendering
function addSpeechLog(text) {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    speechLogs.push({ time, message: text });
    if (speechLogs.length > 30) speechLogs.shift();
    renderLogs();
}

function addServerLog(source, text) {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    serverLogs.push({ time, type: source, message: text });
    if (serverLogs.length > 50) serverLogs.shift();
    renderLogs();
}

function addPunishLog(player, text) {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    serverLogs.push({ time, type: 'punish', player, message: text });
    if (serverLogs.length > 50) serverLogs.shift();
    renderLogs();
}

function renderLogs() {
    const speechBody = document.getElementById('speech-table-body');
    const serverBody = document.getElementById('server-table-body');

    // 1. Render Speech table
    if (speechLogs.length > 0) {
        speechBody.innerHTML = speechLogs.map(log => `
            <tr>
                <td class="col-time">${log.time}</td>
                <td class="col-details" style="font-weight: 500; color: #fff;">${log.message}</td>
            </tr>
        `).join('');
    } else {
        speechBody.innerHTML = '<tr><td colspan="2" class="table-empty">Waiting for speech...</td></tr>';
    }

    // 2. Render Server console table
    if (serverLogs.length > 0) {
        serverBody.innerHTML = serverLogs.map(log => {
            let statusDot = '<span class="status-dot-table success"></span>';
            let badgeClass = 'badge-server';
            let eventLabel = 'Server';
            
            if (log.type === 'system') {
                statusDot = '<span class="status-dot-table warning"></span>';
                badgeClass = 'badge-server';
                eventLabel = 'System';
            } else if (log.type === 'punish') {
                statusDot = '<span class="status-dot-table danger pulse"></span>';
                badgeClass = 'badge-punish';
                eventLabel = 'PUNISHED';
            }
            
            const source = log.player || 'System';
            const details = log.message;

            return `
                <tr>
                    <td class="col-time">${log.time}</td>
                    <td class="col-player">${source}</td>
                    <td class="col-event"><span class="badge ${badgeClass}">${eventLabel}</span></td>
                    <td class="col-details">${details}</td>
                    <td class="col-status">${statusDot}</td>
                </tr>
            `;
        }).join('');
    } else {
        serverBody.innerHTML = '<tr><td colspan="5" class="table-empty">Waiting for server logs...</td></tr>';
    }

    // Auto-scroll
    const speechContainer = document.getElementById('speech-log-container');
    const serverContainer = document.getElementById('server-log-container');
    if (speechContainer) speechContainer.scrollTop = speechContainer.scrollHeight;
    if (serverContainer) serverContainer.scrollTop = serverContainer.scrollHeight;
}

// Safety Modal controllers
function confirmShockTest() {
    document.getElementById('confirm-shock-modal').style.display = 'flex';
}

function closeShockModal() {
    document.getElementById('confirm-shock-modal').style.display = 'none';
}

// Trigger testing command
function triggerTest(type) {
    closeShockModal();
    const intensity = parseInt(document.getElementById('test_intensity').value);
    const duration_ms = parseInt(document.getElementById('test_duration_ms').value);
    
    const statusDiv = document.getElementById('test-status');
    statusDiv.style.color = '#f59e0b';
    statusDiv.innerText = `Sending ${type.toUpperCase()} test command...`;

    executePunishment(config.player_name, "TEST_COMMAND", type, intensity, duration_ms)
        .then(() => {
            statusDiv.style.color = '#10b981';
            statusDiv.innerText = `Command executed successfully!`;
        })
        .catch(err => {
            statusDiv.style.color = '#ef4444';
            statusDiv.innerText = `Failed to send command: ${err}`;
        });
}

// Onboarding Wizard Controllers
function showOnboardingWizard() {
    document.getElementById('setup_player_name').value = config.player_name;
    document.getElementById('setup_api_type').value = config.api_type || '';
    document.getElementById('setup_openshock_token').value = config.openshock_token || '';
    document.getElementById('setup_speech_engine').value = config.speech_engine || 'webspeech';
    
    toggleSetupApiFields();
    
    document.getElementById('onboarding-modal').style.display = 'flex';
}

function submitOnboarding() {
    const name = document.getElementById('setup_player_name').value.trim();
    const apiType = document.getElementById('setup_api_type').value;
    const token = document.getElementById('setup_openshock_token').value.trim();
    const speechEngine = document.getElementById('setup_speech_engine').value;

    if (!name) {
        alert("Please enter a player name!");
        return;
    }

    config.player_name = name;
    config.api_type = apiType;
    config.openshock_token = token;
    config.speech_engine = speechEngine;

    document.getElementById('player_name').value = name;
    document.getElementById('api_type').value = apiType;
    document.getElementById('openshock_token').value = token;
    document.getElementById('speech_engine').value = speechEngine;
    
    toggleApiFields();

    localStorage.setItem("shocker_roulette_player_config", JSON.stringify(config));
    updateLocalSafetyWidget();

    // Update sidebar player name
    const sidebarName = document.getElementById('sidebar-name-val');
    if (sidebarName) sidebarName.innerText = config.player_name;

    document.getElementById('onboarding-modal').style.display = 'none';

    addServerLog("system", "Onboarding configuration saved!");

    // If OpenShock is selected and a token is provided, proceed to Shocker selection!
    if (apiType === 'openshock' && token) {
        document.getElementById('shocker-select-modal').style.display = 'flex';
        fetchOwnedShockers(token);
    } else {
        finishOnboardingLobbyJoin();
    }
}

async function fetchOwnedShockers(token) {
    const spinner = document.getElementById('shocker-loading-spinner');
    const listContainer = document.getElementById('shocker-list-container');
    const btnGroup = document.getElementById('shocker-select-btn-group');
    const subtitle = document.getElementById('shocker-select-subtitle');

    spinner.style.display = 'block';
    listContainer.style.display = 'none';
    btnGroup.style.display = 'none';
    subtitle.innerText = "Querying your OpenShock devices...";

    const headers = {
        "Content-Type": "application/json"
    };
    if (config.openshock_use_headers !== false) {
        headers["Open-Shock-Token"] = token;
        headers["OpenShockToken"] = token;
        headers["Authorization"] = `Bearer ${token}`;
    }

    const fetchOptions = {
        method: "GET",
        headers: headers
    };
    if (config.openshock_use_cookies !== false) {
        fetchOptions.credentials = "include";
    }

    try {
        const res = await fetch("https://api.openshock.app/1/shockers/own", fetchOptions);
        if (!res.ok) {
            throw new Error(`API returned status ${res.status}`);
        }
        const resData = await res.json();
        
        let allShockers = [];
        const dataArr = resData.data || [];
        dataArr.forEach(hub => {
            if (hub.shockers && Array.isArray(hub.shockers)) {
                hub.shockers.forEach(sh => {
                    allShockers.push({
                        id: sh.id,
                        name: sh.name || `${hub.name} (Ch ${sh.rfId})`,
                        model: sh.model || 'Unknown'
                    });
                });
            }
        });

        spinner.style.display = 'none';
        listContainer.style.display = 'block';
        btnGroup.style.display = 'flex';

        if (allShockers.length === 0) {
            subtitle.innerText = "No shocker collars found on your OpenShock profile.";
            listContainer.innerHTML = `<div style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 20px;">Ensure your device is turned on and registered in your OpenShock account.</div>`;
        } else {
            subtitle.innerText = "Check the collar device(s) you wish to use in this session:";
            listContainer.innerHTML = allShockers.map(sh => `
                <label style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px; cursor: pointer; padding: 6px; border-radius: 4px;">
                    <input type="checkbox" name="selected_shocker" value="${sh.id}" checked style="width: auto; cursor: pointer; margin: 0;">
                    <div>
                        <div style="font-size: 13px; font-weight: bold; color: #fff;">${sh.name}</div>
                        <div style="font-size: 10px; color: var(--text-muted); font-family: monospace;">UUID: ${sh.id}</div>
                    </div>
                </label>
            `).join('');
        }

    } catch (e) {
        spinner.style.display = 'none';
        listContainer.style.display = 'block';
        btnGroup.style.display = 'flex';
        subtitle.innerText = "Failed to communicate with OpenShock API.";
        listContainer.innerHTML = `
            <div style="font-size: 12px; color: var(--danger); text-align: center; padding: 10px;">
                Error: ${e.message}<br>
                <span style="font-size: 10px; color: var(--text-muted); display: block; margin-top: 6px;">Ensure your token is valid and your browser allows cross-origin requests.</span>
            </div>
        `;
    }
}

function submitShockerSelection() {
    const checkboxes = document.querySelectorAll('input[name="selected_shocker"]:checked');
    const selectedIds = Array.from(checkboxes).map(cb => cb.value);

    if (selectedIds.length > 0) {
        config.shocker_id = selectedIds.join(",");
        document.getElementById('shocker_id').value = config.shocker_id;
        
        localStorage.setItem("shocker_roulette_player_config", JSON.stringify(config));
        addServerLog("system", `Mapped ${selectedIds.length} shockers: ${config.shocker_id}`);
    }

    document.getElementById('shocker-select-modal').style.display = 'none';
    finishOnboardingLobbyJoin();
}

function skipShockerSelection() {
    document.getElementById('shocker-select-modal').style.display = 'none';
    finishOnboardingLobbyJoin();
}

function finishOnboardingLobbyJoin() {
    if (config.speech_engine === 'whisper_wasm') {
        initWhisper();
    }
    connectWebSocket();
}
