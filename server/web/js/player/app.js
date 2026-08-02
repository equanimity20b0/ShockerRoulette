// Page initialization entrypoint
window.onload = function() {
    // Load saved settings first synchronously
    fetchConfig();

    // Query microphone devices
    fetchDevices();

    const isFirstVisit = !localStorage.getItem("shocker_roulette_player_config");
    const hasGenericName = config.player_name.startsWith("Player_");

    if (isFirstVisit || hasGenericName) {
        showOnboardingWizard();
    } else {
        if (config.speech_engine === 'whisper_wasm') {
            initWhisper();
        }
        connectWebSocket();
    }
    
    // Slots and cooldown UI timer loop
    setInterval(updateWordSlotsUI, 1000);
};
