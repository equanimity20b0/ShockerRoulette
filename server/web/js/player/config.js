// Default Client Configuration
let config = {
    player_name: "Player_" + Math.floor(Math.random() * 900 + 100),
    api_type: "openshock",
    openshock_token: "",
    shocker_id: "",
    openshock_use_headers: true,
    openshock_use_cookies: true,
    max_intensity: 15,
    max_duration_ms: 2000,
    punishment_override: "",
    mic_device_id: "",
    shocker_mode: "all",
    speech_engine: "whisper_wasm"
};

// Game status variables
let ws = null;
let reconnectTimeout = null;
let intentionalClose = false;

let forbiddenWords = [];
let secretHashes = [];

let maxWords = 3;
let cooldownSec = 60;
let myWordTimestamps = JSON.parse(localStorage.getItem('myWordTimestamps') || '[]');
let lastTotalWords = -1;
let sessionShocks = 0;
let lobbyPlayers = [];

// Speech & Audio variables
let isListening = false;
let speechRecognition = null;
let heartbeatInterval = null;
let totalPhrasesSpoken = 0;
let speechLogs = [];
let serverLogs = [];

// Toggle form input fields depending on API Type selection
function toggleApiFields() {
    const apiType = document.getElementById('api_type').value;
    const openShockFields = document.getElementById('openshock-fields');


    if (apiType === 'openshock') {
        openShockFields.style.display = 'block';
    } else {
        openShockFields.style.display = 'none';
    }
}

// Toggle setup wizard fields depending on API selection
function toggleSetupApiFields() {
    const apiType = document.getElementById('setup_api_type').value;
    const openshockFields = document.getElementById('setup-openshock-fields');
    if (apiType === 'openshock') {
        openshockFields.style.display = 'block';
    } else {
        openshockFields.style.display = 'none';
    }
}

// Update Slider indicator values dynamically
function updateSliderLabel(id) {
    const val = document.getElementById(id).value;
    const suffix = id.endsWith('ms') ? 'ms' : '%';
    document.getElementById(`${id}_val`).innerText = val + suffix;
}

// Fetch client configuration from localStorage
function fetchConfig() {
    const saved = localStorage.getItem("shocker_roulette_player_config");
    if (saved) {
        try {
            config = { ...config, ...JSON.parse(saved) };
        } catch(e) {
            console.error("Failed loading local config:", e);
        }
    }

    document.getElementById('player_name').value = config.player_name;
    document.getElementById('api_type').value = config.api_type;
    
    document.getElementById('openshock_token').value = config.openshock_token || '';
    document.getElementById('shocker_id').value = config.shocker_id || '';
    
    document.getElementById('openshock_use_headers').checked = config.openshock_use_headers !== false;
    document.getElementById('openshock_use_cookies').checked = config.openshock_use_cookies !== false;
    
    document.getElementById('max_intensity').value = config.max_intensity;
    document.getElementById('max_duration_ms').value = config.max_duration_ms;
    setComfortOverride(config.punishment_override || '');
    document.getElementById('mic_device_id').value = config.mic_device_id || '';
    setShockerMode(config.shocker_mode || 'all');
    document.getElementById('speech_engine').value = config.speech_engine || 'webspeech';
    
    updateSliderLabel('max_intensity');
    updateSliderLabel('max_duration_ms');
    toggleApiFields();
    
    updateLocalSafetyWidget();

    // Update sidebar player name
    const sidebarName = document.getElementById('sidebar-name-val');
    if (sidebarName) sidebarName.innerText = config.player_name || '--';
}

// Save client configuration back to localStorage and reconnect
function saveConfig(event) {
    event.preventDefault();
    config.player_name = document.getElementById('player_name').value.trim();
    config.api_type = document.getElementById('api_type').value;
    
    config.openshock_token = document.getElementById('openshock_token').value.trim();
    config.shocker_id = document.getElementById('shocker_id').value.trim();
    config.openshock_use_headers = document.getElementById('openshock_use_headers').checked;
    config.openshock_use_cookies = document.getElementById('openshock_use_cookies').checked;
    
    config.max_intensity = parseInt(document.getElementById('max_intensity').value);
    config.max_duration_ms = parseInt(document.getElementById('max_duration_ms').value);
    config.punishment_override = document.getElementById('punishment_override').value;
    config.mic_device_id = document.getElementById('mic_device_id').value;
    config.shocker_mode = document.getElementById('shocker_mode').value;
    config.speech_engine = document.getElementById('speech_engine').value;
    if (config.speech_engine === 'whisper_wasm') {
        initWhisper();
    }

    localStorage.setItem("shocker_roulette_player_config", JSON.stringify(config));
    
    addServerLog("system", "Configurations saved! Reconnecting WebSocket...");
    updateLocalSafetyWidget();
    
    // Reconnect websocket
    connectWebSocket();
    
    // Restart mic if listening
    if (isListening) {
        toggleMic(); // stop
        toggleMic(); // start with new mic option
    }
    
    alert("Configuration saved and client state updated successfully!");
}

// Update local limits display
function updateLocalSafetyWidget() {
    document.getElementById('limit-intensity-val').innerText = config.max_intensity + '%';
    document.getElementById('limit-duration-val').innerText = config.max_duration_ms + 'ms';

    document.getElementById('limit-intensity-bar').style.width = config.max_intensity + '%';
    const durationPct = Math.min(100, (config.max_duration_ms / 15000) * 100);
    document.getElementById('limit-duration-bar').style.width = durationPct + '%';

    const overrideBadge = document.getElementById('limit-override-val');
    if (config.punishment_override === 'vibrate') {
        overrideBadge.innerText = 'Force Vibrate';
        overrideBadge.className = 'badge badge-server';
    } else if (config.punishment_override === 'sound') {
        overrideBadge.innerText = 'Force Sound';
        overrideBadge.className = 'badge badge-speech';
    } else {
        overrideBadge.innerText = 'No Override (Full)';
        overrideBadge.className = 'badge badge-punish';
    }
}
