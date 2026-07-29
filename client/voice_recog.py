import os
import sys
import queue
import time
import collections
import numpy as np
import threading
import sounddevice as sd
from faster_whisper import WhisperModel

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class VoiceRecog:

    worker_thread = None
    running = True

    @staticmethod
    def end():
        print("\nEnding voice recognition...")
        VoiceRecog.running = False
        if VoiceRecog.worker_thread:
            try:
                VoiceRecog.worker_thread.join(timeout=1.0)
            except Exception:
                pass

    @staticmethod
    def init_voice_recog(on_text_callback=None, on_typing_callback=None, use_float32=False, decoding_method="greedy_search", num_threads=1):
        print(f"{bcolors.OKCYAN}Loading local tiny.en Whisper model (cpu_threads={num_threads})...{bcolors.ENDC}")
        model = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=num_threads)
        print(f"{bcolors.OKGREEN}Whisper model loaded successfully.{bcolors.ENDC}")

        # Audio parameters
        SAMPLERATE = 16000
        BLOCKSIZE = 1024
        MIN_SPEECH_DURATION = 0.5   # Minimum speech duration to transcribe (sec)
        SILENCE_DURATION = 1.0      # Silence duration to finalize phrase (sec)

        try:
            input_device_id = sd.default.device['input']
        except Exception:
            input_device_id = None
            
        audio_queue = queue.Queue()
        
        def mic_callback(indata, frames, time_info, status):
            if status:
                print(f"Status error: {status}", file=sys.stderr)
            audio_queue.put(indata.copy().flatten())

        input_stream = sd.InputStream(
            samplerate=SAMPLERATE,
            blocksize=BLOCKSIZE,
            device=input_device_id,
            dtype="float32",
            channels=1,
            callback=mic_callback
        )

        VoiceRecog.running = True
        
        def voice_recog_thread():
            audio_buffer = []
            is_speaking = False
            silence_start_time = None
            speech_start_time = None

            rms_history = collections.deque(maxlen=150)
            for _ in range(150):
                rms_history.append(0.005)

            try:
                with input_stream:
                    while VoiceRecog.running:
                        try:
                            samples = audio_queue.get(timeout=0.05)
                        except queue.Empty:
                            continue

                        # Compute block RMS
                        rms = np.sqrt(np.mean(samples**2))
                        rms_history.append(rms)

                        # Dynamic noise floor: 15th percentile of history
                        noise_floor = np.percentile(rms_history, 15)
                        dynamic_threshold = max(noise_floor * 2.2, 0.003)

                        # Log gate status in place
                        sys.stdout.write(f"\r[Gate] RMS: {rms:.5f} | Floor: {noise_floor:.5f} | Thresh: {dynamic_threshold:.5f} | Speaking: {is_speaking}   ")
                        sys.stdout.flush()

                        # Check for signal
                        if rms > dynamic_threshold:
                            if not is_speaking:
                                is_speaking = True
                                speech_start_time = time.time()
                                if on_typing_callback:
                                    on_typing_callback(True)
                            silence_start_time = None
                        else:
                            if is_speaking and silence_start_time is None:
                                silence_start_time = time.time()

                        # If speaking, accumulate audio
                        if is_speaking:
                            audio_buffer.append(samples)

                            # Check for endpoint (silence duration met)
                            if silence_start_time is not None and (time.time() - silence_start_time) >= SILENCE_DURATION:
                                duration = time.time() - speech_start_time
                                if on_typing_callback:
                                    on_typing_callback(False)
                                    
                                if duration >= MIN_SPEECH_DURATION:
                                    audio_data = np.concatenate(audio_buffer)
                                    
                                    # Final transcription (beam_size=3 for speed/accuracy balance)
                                    segments, _ = model.transcribe(audio_data, beam_size=3, vad_filter=True)
                                    text = " ".join([seg.text for seg in segments]).strip()
                                    
                                    sys.stdout.write("\r\033[K")  # Clear line
                                    sys.stdout.flush()
                                    if text:
                                        print(f"{bcolors.OKGREEN}Finalized: {text}{bcolors.ENDC}")
                                        if on_text_callback:
                                            on_text_callback(text)
                                    else:
                                        print("[No speech recognized]")
                                else:
                                    sys.stdout.write("\r\033[K")  # Clear line
                                    sys.stdout.flush()
                                
                                # Reset buffer/state
                                audio_buffer = []
                                is_speaking = False
                                silence_start_time = None

            except Exception as e:
                print(f"\n{bcolors.FAIL}Voice Recognition Error: {e}{bcolors.ENDC}")

        VoiceRecog.worker_thread = threading.Thread(target=voice_recog_thread, daemon=True)
        VoiceRecog.worker_thread.start()
