const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

// 1. Mock Browser Environment Globals required before websocket.js load
global.config = { 
    player_name: "PlayerA",
    max_intensity: 30,         // User safety max intensity limit: 30%
    max_duration_ms: 2000,      // User safety max duration limit: 2000ms
    api_type: "openshock",
    openshock_token: "test_token",
    shocker_id: "test_uuid",
    punishment_override: "none" // Control override setting
};
global.sessionShocks = 0;
global.forbiddenWords = [];
global.secretHashes = [];
global.lobbyPlayers = [];
global.serverLogs = [];
global.punishLogs = [];

let lastOpenShockPayload = null;
const fetchCalls = [];
let mockWordsListHtml = '';
let mockMetricWordsText = 0;

global.document = {
    getElementById: (id) => {
        if (id === 'forbidden-words-list') {
            return {
                set innerHTML(val) { mockWordsListHtml = val; },
                get innerHTML() { return mockWordsListHtml; }
            };
        }
        if (id === 'metric-words') return { set innerText(val) { mockMetricWordsText = val; } };
        if (id === 'metric-players') return { set innerText(val) {} };
        if (id === 'metric-mode') return { set innerText(val) {} };
        if (id === 'metric-shocks') return { set innerText(val) {} };
        if (id === 'player-count-sub') return { set innerText(val) {} };
        return { innerText: '', innerHTML: '' };
    }
};

global.updateMetrics = () => {
    const publicCount = global.forbiddenWords.length;
    const secretCount = global.secretHashes.length;
    const currentTotal = publicCount + secretCount;

    const metricElem = document.getElementById('metric-words');
    if (metricElem) metricElem.innerText = currentTotal;

    const wordsList = document.getElementById('forbidden-words-list');
    if (wordsList) {
        let tagsHtml = '';
        if (global.forbiddenWords.length > 0) {
            tagsHtml += global.forbiddenWords.map(w => `<span class="word-tag">${w}</span>`).join('');
        }
        if (global.secretHashes.length > 0) {
            for (let i = 0; i < global.secretHashes.length; i++) {
                tagsHtml += `<span class="word-tag secret">?</span>`;
            }
        }
        if (tagsHtml !== '') {
            wordsList.innerHTML = tagsHtml;
        } else {
            wordsList.innerHTML = '<span class="table-empty">No active forbidden words loaded.</span>';
        }
    }
};
global.updateLobbyUI = () => {};
global.updateWordSlotsUI = () => {};
global.pushFeedItem = () => {};
global.highlightPlayerRow = () => {};
global.addServerLog = (type, msg) => {
    global.serverLogs.push({ type, msg });
};
global.addPunishLog = (speaker, msg) => {
    global.punishLogs.push({ speaker, msg });
};

// Mock fetch to capture OpenShock payload structure
global.fetch = async (url, options) => {
    if (options && options.body) {
        lastOpenShockPayload = JSON.parse(options.body);
        fetchCalls.push(lastOpenShockPayload);
    }
    return {
        ok: true,
        status: 200,
        text: async () => "OK"
    };
};

// 2. Load websocket.js code into execution context
const websocketJsPath = path.join(__dirname, '..', 'server', 'web', 'js', 'player', 'websocket.js');
const websocketJsCode = fs.readFileSync(websocketJsPath, 'utf8');
eval(websocketJsCode);

// 3. Test Cases for Immunity & Migration
test('Web Client Punish Handler - Player A (Word Issuer) is immune when listed in immune_players', () => {
    global.punishLogs = [];
    global.serverLogs = [];
    global.config.player_name = "PlayerA";

    const eventData = {
        event: "punish",
        speaker: "PlayerB",
        word: "pineapple",
        punishment_type: "shock",
        intensity: 25,
        duration_ms: 1000,
        immune_players: ["PlayerA"] // PlayerA is the word issuer!
    };

    serverEventHandlers.punish(eventData);

    assert.strictEqual(global.punishLogs.length, 0, "addPunishLog should NOT be called for immune player (PlayerA)");
    assert.ok(
        global.serverLogs.some(log => log.msg.includes("you are immune")),
        "Server log should record that the player was immune"
    );
});

test('Web Client Punish Handler - Player C (Non-Issuer) is NOT immune and executes punishment', () => {
    global.punishLogs = [];
    global.serverLogs = [];
    global.config.player_name = "PlayerC";

    const eventData = {
        event: "punish",
        speaker: "PlayerB",
        word: "pineapple",
        punishment_type: "shock",
        intensity: 25,
        duration_ms: 1000,
        immune_players: ["PlayerA"]
    };

    serverEventHandlers.punish(eventData);

    assert.strictEqual(global.punishLogs.length, 1, "addPunishLog SHOULD be called for non-immune player (PlayerC)");
    assert.strictEqual(global.punishLogs[0].speaker, "PlayerB");
    assert.ok(global.punishLogs[0].msg.includes("pineapple"), "Punish log should reference trigger word 'pineapple'");
});

test('Web Client Words Updated Handler - updates forbiddenWords state on secret word migration', () => {
    global.forbiddenWords = [];

    const eventData = {
        event: "words_updated",
        forbidden_words: ["erp", "pineapple"],
        secret_hashes: ["hash123"],
        message: "Secret word 'pineapple' triggered!"
    };

    serverEventHandlers.words_updated(eventData);

    assert.deepStrictEqual(global.forbiddenWords, ["erp", "pineapple"]);
    assert.deepStrictEqual(global.secretHashes, ["hash123"]);
});

// 4. Test Cases for Safety Limits & Overrides
test('Web Client Safety Limits - Intensity higher than max_intensity is clamped', () => {
    global.punishLogs = [];
    lastOpenShockPayload = null;
    global.config.player_name = "PlayerC";
    global.config.max_intensity = 30; // Max safety limit 30%
    global.config.punishment_override = "none";

    const eventData = {
        event: "punish",
        speaker: "PlayerB",
        word: "danger",
        punishment_type: "shock",
        intensity: 85, // Incoming 85% shock request
        duration_ms: 1000,
        immune_players: []
    };

    serverEventHandlers.punish(eventData);

    assert.strictEqual(global.punishLogs.length, 1);
    assert.ok(global.punishLogs[0].msg.includes("30%"), "Punish log should indicate intensity clamped down to max safety limit 30%");
    assert.strictEqual(lastOpenShockPayload.shocks[0].intensity, 30, "OpenShock payload intensity MUST be clamped to 30%");
});

test('Web Client Safety Limits - Duration longer than max_duration_ms is clamped', () => {
    global.punishLogs = [];
    lastOpenShockPayload = null;
    global.config.player_name = "PlayerC";
    global.config.max_duration_ms = 1500; // Max safety duration 1500ms
    global.config.punishment_override = "none";

    const eventData = {
        event: "punish",
        speaker: "PlayerB",
        word: "danger",
        punishment_type: "shock",
        intensity: 20,
        duration_ms: 10000, // Excessive 10 second duration
        immune_players: []
    };

    serverEventHandlers.punish(eventData);

    assert.strictEqual(lastOpenShockPayload.shocks[0].duration, 1500, "OpenShock payload duration MUST be clamped to 1500ms");
});

test('Web Client Control Overrides - punishment_override = vibrate clamps shock command to Vibrate', () => {
    global.punishLogs = [];
    lastOpenShockPayload = null;
    global.config.player_name = "PlayerC";
    global.config.punishment_override = "vibrate"; // Comfort override active

    const eventData = {
        event: "punish",
        speaker: "PlayerB",
        word: "test_word",
        punishment_type: "shock",
        intensity: 20,
        duration_ms: 1000,
        immune_players: []
    };

    serverEventHandlers.punish(eventData);

    assert.ok(global.punishLogs[0].msg.includes("VIBRATE"), "Punish log should indicate type was overridden to VIBRATE");
    assert.strictEqual(lastOpenShockPayload.shocks[0].type, "Vibrate", "OpenShock payload operation type MUST be overridden to Vibrate");
});

test('Web Client Control Overrides - punishment_override = sound clamps shock command to Sound', () => {
    global.punishLogs = [];
    lastOpenShockPayload = null;
    global.config.player_name = "PlayerC";
    global.config.punishment_override = "sound"; // Comfort override active

    const eventData = {
        event: "punish",
        speaker: "PlayerB",
        word: "test_word",
        punishment_type: "shock",
        intensity: 20,
        duration_ms: 1000,
        immune_players: []
    };

    serverEventHandlers.punish(eventData);

    assert.ok(global.punishLogs[0].msg.includes("SOUND"), "Punish log should indicate type was overridden to SOUND");
    assert.strictEqual(lastOpenShockPayload.shocks[0].type, "Sound", "OpenShock payload operation type MUST be overridden to Sound");
});

// 5. Test Case for Shocker Roulette Spin & Landing Shock
test('Web Client Roulette Handler - cycles vibrate ticks during spin and delivers shock to victim', async () => {
    global.punishLogs = [];
    global.serverLogs = [];
    fetchCalls.length = 0;

    global.config.player_name = "PlayerB";
    global.config.max_intensity = 50;
    global.config.punishment_override = "none";

    // 1. Receive roulette spin event (PlayerB appears 2 times in sequence)
    const rouletteEvent = {
        event: "roulette",
        speaker: "PlayerA",
        ticking_sequence: ["PlayerA", "PlayerB", "PlayerA", "PlayerB"],
        tick_delay_ms: 10,
        vibrate_intensity: 100
    };

    serverEventHandlers.roulette(rouletteEvent);
    
    // Wait for async spin animation to complete (4 items * 10ms = 40ms)
    await new Promise(r => setTimeout(r, 80));

    // PlayerB should have received 2 Vibrate ticks at max_intensity 50%
    const vibrateTicks = fetchCalls.filter(c => c.shocks[0].type === "Vibrate");
    assert.strictEqual(vibrateTicks.length, 2, "PlayerB should receive 2 vibrate ticks during spin sequence");
    assert.strictEqual(vibrateTicks[0].shocks[0].intensity, 50, "Vibrate tick intensity must be clamped to max_intensity 50%");

    // 2. Receive landing shock punish event for victim PlayerB
    fetchCalls.length = 0;
    const punishEvent = {
        event: "punish",
        speaker: "Roulette Wheel",
        word: "Roulette Landing",
        punishment_type: "shock",
        intensity: 30,
        duration_ms: 1000,
        immune_players: ["PlayerA"] // PlayerA is immune, PlayerB is victim!
    };

    serverEventHandlers.punish(punishEvent);

    assert.strictEqual(fetchCalls.length, 1, "Victim PlayerB should receive 1 shock execution on landing");
    assert.strictEqual(fetchCalls[0].shocks[0].type, "Shock");
    assert.strictEqual(fetchCalls[0].shocks[0].intensity, 30);

    // 3. Verify non-victim PlayerA is immune on landing
    fetchCalls.length = 0;
    global.config.player_name = "PlayerA";
    serverEventHandlers.punish(punishEvent);

    assert.strictEqual(fetchCalls.length, 0, "Immune non-victim PlayerA should NOT receive shock execution");
});

// 6. Test Case for Word List Sync & DOM Update
test('Web Client Word List Sync - words_updated handler updates DOM tags without throwing errors', () => {
    global.forbiddenWords = [];
    global.secretHashes = [];
    mockWordsListHtml = '';

    const syncEvent = {
        event: "words_updated",
        forbidden_words: ["erp"],
        secret_hashes: ["hash_avocado", "hash_banana"],
        message: "Word list updated!"
    };

    serverEventHandlers.words_updated(syncEvent);

    assert.strictEqual(global.forbiddenWords.length, 1);
    assert.strictEqual(global.secretHashes.length, 2);
    assert.strictEqual(mockMetricWordsText, 3, "Total word count metric should be 1 public + 2 secret = 3");
    assert.ok(mockWordsListHtml.includes('<span class="word-tag">erp</span>'), "DOM list must render public word 'erp'");
    assert.ok(mockWordsListHtml.includes('<span class="word-tag secret">?</span>'), "DOM list must render secret word tags");
});
