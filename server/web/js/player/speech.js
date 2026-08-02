// Whisper WASM Integration Globals
let whisperWorker = null;
let whisperInitialized = false;
let whisperLoading = false;
let whisperAutoStart = false;
let whisperAudioContext = null;
let whisperStream = null;
let whisperProcessor = null;
let whisperBuffer = [];
let whisperIsSpeaking = false;
let whisperSilenceStart = null;
let whisperSpeakingStartTime = null;

const WHISPER_SILENCE_THRESHOLD = 0.015;
const WHISPER_SILENCE_DURATION_MS = 1000;
const WHISPER_MAX_DURATION_MS = 8000;

const whisperWorkerCode = `
    import { pipeline, env } from '${window.location.origin}/transformers.min.js';
    
    env.allowLocalModels = false;
    env.backends.onnx.wasm.numThreads = 1;

    let transcriber = null;

    self.onmessage = async (event) => {
        const { type, data } = event.data;

        if (type === 'init') {
            try {
                self.postMessage({ type: 'status', data: 'loading' });
                transcriber = await pipeline('automatic-speech-recognition', 'Xenova/whisper-tiny.en', {
                    quantized: true,
                    progress_callback: (progress) => {
                        if (progress.status === 'progress') {
                            self.postMessage({ 
                                type: 'progress', 
                                data: Math.round((progress.loaded / progress.total) * 100) 
                            });
                        }
                    }
                });
                self.postMessage({ type: 'status', data: 'ready' });
            } catch (e) {
                self.postMessage({ type: 'status', data: 'error', error: e.message });
            }
        } else if (type === 'transcribe') {
            if (!transcriber) {
                self.postMessage({ type: 'error', data: 'Transcriber not initialized' });
                return;
            }
            try {
                const response = await transcriber(data, {
                    chunk_length_s: 30,
                    stride_length_s: 5,
                    return_timestamps: false
                });
                self.postMessage({ type: 'result', data: response.text });
            } catch (e) {
                self.postMessage({ type: 'error', data: e.message });
            }
        }
    };
`;

// Fetch available microphone devices
function fetchDevices() {
    const select = document.getElementById('mic_device_id');
    select.innerHTML = '<option value="">System Default Microphone</option>';
    return navigator.mediaDevices.enumerateDevices()
        .then(devices => {
            devices.forEach(device => {
                if (device.kind === 'audioinput') {
                    const opt = document.createElement('option');
                    opt.value = device.deviceId;
                    opt.innerText = device.label || 'Microphone (' + device.deviceId.slice(0, 5) + ')';
                    select.appendChild(opt);
                }
            });
            if (config.mic_device_id) {
                select.value = config.mic_device_id;
            }
        })
        .catch(err => {
            console.error("Error fetching audio devices: ", err);
        });
}

function initWhisper() {
    if (whisperInitialized || whisperLoading) return;
    whisperLoading = true;
    
    addServerLog("system", "Starting local Whisper WASM engine initialization...");
    const btn = document.getElementById("btn-toggle-mic");
    btn.disabled = true;
    btn.innerText = "⏳ Loading Whisper Model...";

    const blob = new Blob([whisperWorkerCode], { type: 'application/javascript' });
    const workerUrl = URL.createObjectURL(blob);
    whisperWorker = new Worker(workerUrl, { type: 'module' });

    whisperWorker.onmessage = (event) => {
        const { type, data, error } = event.data;

        if (type === 'status') {
            if (data === 'ready') {
                whisperInitialized = true;
                whisperLoading = false;
                btn.disabled = false;
                btn.innerText = "🎙️ Start Listening";
                addServerLog("system", "Local Whisper WASM model successfully loaded and ready offline!");
                
                if (whisperAutoStart) {
                    whisperAutoStart = false;
                    toggleWhisperListening();
                }
            } else if (data === 'error' || data === 'error_msg') {
                whisperLoading = false;
                btn.disabled = false;
                btn.innerText = "🎙️ Start Listening";
                addServerLog("system", `Whisper initialization error: ${error || 'Failed downloading model'}`);
            }
        } else if (type === 'progress') {
            btn.innerText = `⏳ Loading Whisper (${data}%)`;
            const label = document.getElementById("mic-status-label");
            label.innerText = `Mic: Model Download ${data}%`;
        } else if (type === 'result') {
            const text = data.trim();
            if (text) {
                addServerLog("system", `Local Whisper transcribed: "${text}"`);
                processSpokenSpeech(text);
            }
        } else if (type === 'error') {
            addServerLog("system", `Whisper processing error: ${data}`);
        }
    };

    whisperWorker.postMessage({ type: 'init' });
}

function onSpeechEngineChange() {
    const engine = document.getElementById("speech_engine").value;
    if (engine === 'whisper_wasm') {
        initWhisper();
    }
}

async function toggleWhisperListening() {
    const btn = document.getElementById("btn-toggle-mic");
    const label = document.getElementById("mic-status-label");

    if (!isListening) {
        try {
            addServerLog("system", "Starting local Whisper WASM voice capture context...");
            
            const audioOptions = {
                sampleRate: 16000
            };
            if (config.mic_device_id) {
                audioOptions.deviceId = { exact: config.mic_device_id };
            }
            
            whisperAudioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });
            
            whisperStream = await navigator.mediaDevices.getUserMedia({ audio: audioOptions });
            const mediaStreamSource = whisperAudioContext.createMediaStreamSource(whisperStream);
            
            whisperProcessor = whisperAudioContext.createScriptProcessor(4096, 1, 1);
            whisperBuffer = [];
            whisperIsSpeaking = false;
            whisperSilenceStart = null;
            
            whisperProcessor.onaudioprocess = (event) => {
                // We keep track of users input volume with an RMS,
                // Only when they cross a threshold do we send their audio to
                // the whisper model. Goal is to save on performance; model 
                // only runs when the user is speaking.
                const inputData = event.inputBuffer.getChannelData(0);
                
                let sum = 0;
                for (let i = 0; i < inputData.length; i++) {
                    sum += inputData[i] * inputData[i];
                }
                const rms = Math.sqrt(sum / inputData.length);
                
                if (rms > WHISPER_SILENCE_THRESHOLD) {
                    if (!whisperIsSpeaking) {
                        whisperIsSpeaking = true;
                        whisperSpeakingStartTime = Date.now();
                        whisperBuffer = [];
                    }
                    whisperSilenceStart = null;
                } else {
                    if (whisperIsSpeaking) {
                        if (!whisperSilenceStart) {
                            whisperSilenceStart = Date.now();
                        } else if (Date.now() - whisperSilenceStart > WHISPER_SILENCE_DURATION_MS) {
                            triggerWhisperTranscription();
                        }
                    }
                }
                
                if (whisperIsSpeaking) {
                    whisperBuffer.push(...inputData);
                    if (Date.now() - whisperSpeakingStartTime > WHISPER_MAX_DURATION_MS) {
                        triggerWhisperTranscription();
                    }
                }
            };
            
            mediaStreamSource.connect(whisperProcessor);
            whisperProcessor.connect(whisperAudioContext.destination);
            
            isListening = true;
            btn.innerText = "⏹️ Stop Listening";
            btn.style.backgroundColor = "rgba(239, 68, 68, 0.1)";
            btn.style.borderColor = "var(--danger)";
            btn.style.color = "var(--danger)";
            label.innerText = "Mic: Listening Active (Whisper)";
            label.style.color = "var(--success)";
            addServerLog("system", "Local Whisper listening active. Speak forbidden words to trigger!");
            
        } catch(e) {
            addServerLog("system", `Failed starting Whisper voice capture: ${e}`);
        }
    } else {
        isListening = false;
        
        if (whisperProcessor) {
            whisperProcessor.disconnect();
            whisperProcessor = null;
        }
        if (whisperStream) {
            whisperStream.getTracks().forEach(track => track.stop());
            whisperStream = null;
        }
        if (whisperAudioContext) {
            whisperAudioContext.close();
            whisperAudioContext = null;
        }
        
        btn.innerText = "🎙️ Start Listening";
        btn.style.backgroundColor = "rgba(255,255,255,0.03)";
        btn.style.borderColor = "var(--border)";
        btn.style.color = "var(--text-muted)";
        label.innerText = "Mic: Inactive";
        label.style.color = "";
        addServerLog("system", "Local Whisper voice capture stopped.");
    }
}

function triggerWhisperTranscription() {
    whisperSilenceStart = null;
    whisperIsSpeaking = false;
    if (whisperBuffer.length === 0) return;
    
    const audioData = new Float32Array(whisperBuffer);
    whisperBuffer = [];
    
    whisperWorker.postMessage({ type: 'transcribe', data: audioData });
}

async function startListening() {
    if (isListening) return;

    const engine = config.speech_engine || 'webspeech';
    if (engine === 'whisper_wasm') {
        if (!whisperInitialized) {
            whisperAutoStart = true;
            initWhisper();
            return;
        }
        if (!whisperListening) {
            await toggleWhisperListening();
        }
    } else {
        await toggleMic();
    }
}

// Speech Recognition Setup (Web Speech API or Whisper WASM)
async function toggleMic() {
    const engine = config.speech_engine || 'webspeech';

    if (engine === 'whisper_wasm') {
        if (!whisperInitialized) {
            initWhisper();
            return;
        }
        await toggleWhisperListening();
        return;
    }

    const SpeechRecognition = window.webkitSpeechRecognition || window.SpeechRecognition;
    if (!SpeechRecognition) {
        alert("This browser does not support built-in Speech recognition. Try Chrome or Edge.");
        return;
    }

    const btn = document.getElementById("btn-toggle-mic");
    const label = document.getElementById("mic-status-label");

    if (!isListening) {
        speechRecognition = new SpeechRecognition();
        speechRecognition.continuous = true;
        speechRecognition.interimResults = false;
        speechRecognition.lang = "en-US";

        speechRecognition.onstart = () => {
            isListening = true;
            btn.innerText = "⏹️ Stop Listening";
            btn.style.backgroundColor = "rgba(239, 68, 68, 0.1)";
            btn.style.borderColor = "var(--danger)";
            btn.style.color = "var(--danger)";
            label.innerText = "Mic: Listening Active";
            label.style.color = "var(--success)";
            addServerLog("system", "Speech listener initialized. Listening to microphone...");
        };

        speechRecognition.onresult = async (event) => {
            const transcript = event.results[event.results.length - 1][0].transcript;
            await processSpokenSpeech(transcript);
        };

        speechRecognition.onerror = (e) => {
            addServerLog("system", `Mic error: ${e.error}`);
        };

        speechRecognition.onend = () => {
            if (isListening) {
                try { speechRecognition.start(); } catch(e){}
            } else {
                btn.innerText = "🎙️ Start Listening";
                btn.style.backgroundColor = "rgba(255,255,255,0.03)";
                btn.style.borderColor = "var(--border)";
                btn.style.color = "var(--text-muted)";
                label.innerText = "Mic: Inactive";
                label.style.color = "";
            }
        };

        try {
            speechRecognition.start();
        } catch(e) {
            addServerLog("system", `Failed starting speech: ${e}`);
        }
    } else {
        isListening = false;
        if (speechRecognition) {
            speechRecognition.stop();
        }
    }
}

// Process Speech
async function processSpokenSpeech(text) {
    const trimmed = text.trim();
    if (!trimmed) return;

    totalPhrasesSpoken++;
    
    // Log to speech table list
    addSpeechLog(trimmed);

    const cleanText = trimmed.toLowerCase();

    // 1. Check forbidden
    let matchedPublic = null;
    for (let word of forbiddenWords) {
        if (cleanText.includes(word.toLowerCase())) {
            matchedPublic = word;
            break;
        }
    }

    if (matchedPublic) {
        addServerLog("system", `⚠️ Spoke public forbidden word: '${matchedPublic}'! Sending trigger...`);
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                action: "trigger",
                word: matchedPublic
            }));
        }
        return;
    }

    // 2. Check secret words (SHA-256 matches)
    const cleanWords = cleanText.replace(/[.,\/#!$%\^&\*;:{}=\-_`~()?]/g,"").split(/\s+/).filter(Boolean);
    const n = cleanWords.length;
    let matchedSecretHash = null;

    for (let len = 1; len <= Math.min(4, n); len++) {
        if (matchedSecretHash) break;
        for (let i = 0; i <= n - len; i++) {
            const phrase = cleanWords.slice(i, i + len).join(" ");
            const hash = await computeSHA256(phrase);
            if (secretHashes.includes(hash)) {
                matchedSecretHash = hash;
                break;
            }
        }
    }

    if (matchedSecretHash) {
        addServerLog("system", `⚠️ Triggered a secret word trap! Sending trigger hash...`);
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                action: "trigger",
                hash: matchedSecretHash
            }));
        }
    }
}

async function computeSHA256(message) {
    const msgBuffer = new TextEncoder().encode(message);
    const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    return hashHex;
}
