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
    active_device_id = None # Tracks currently selected microphone ID dynamically

    @staticmethod
    def get_input_devices():
        try:
            devices = sd.query_devices()
            input_devices = []
            try:
                default_input = sd.default.device[0]
            except Exception:
                default_input = -1
                
            for idx, d in enumerate(devices):
                if d.get('max_input_channels', 0) > 0:
                    input_devices.append({
                        "id": idx,
                        "name": d['name'],
                        "is_default": idx == default_input
                    })
            return input_devices
        except Exception as e:
            print(f"Error querying audio devices: {e}")
            return []

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

        audio_queue = queue.Queue()
        
        def mic_callback(indata, frames, time_info, status):
            if status:
                print(f"Status error: {status}", file=sys.stderr)
            audio_queue.put(indata.copy().flatten())

        VoiceRecog.running = True
        
        def voice_recog_thread():
            audio_buffer = []
            is_speaking = False
            silence_start_time = None
            speech_start_time = None

            rms_history = collections.deque(maxlen=150)
            for _ in range(150):
                rms_history.append(0.005)

            # Track current stream configurations
            current_stream_device = -9999
            input_stream = None

            try:
                while VoiceRecog.running:
                    # Hot-swap check: If stream not initialized or active_device_id changed
                    if input_stream is None or current_stream_device != VoiceRecog.active_device_id:
                        if input_stream is not None:
                            try:
                                input_stream.stop()
                                input_stream.close()
                            except Exception:
                                pass
                            
                            # Clean state
                            while not audio_queue.empty():
                                try:
                                    audio_queue.get_nowait()
                                except queue.Empty:
                                    break
                            audio_buffer = []
                            is_speaking = False
                            silence_start_time = None
                            if on_typing_callback:
                                on_typing_callback(False)

                        # Resolve active device
                        dev_id = VoiceRecog.active_device_id
                        if dev_id is None:
                            try:
                                dev_id = sd.default.device[0]
                            except Exception:
                                dev_id = None
                        
                        try:
                            input_stream = sd.InputStream(
                                samplerate=SAMPLERATE,
                                blocksize=BLOCKSIZE,
                                device=dev_id,
                                dtype="float32",
                                channels=1,
                                callback=mic_callback
                            )
                            input_stream.start()
                            current_stream_device = VoiceRecog.active_device_id
                            print(f"\n{bcolors.OKBLUE}[VoiceRecog] Swapped input device to ID: {dev_id}{bcolors.ENDC}")
                        except Exception as stream_err:
                            print(f"\n{bcolors.FAIL}[VoiceRecog] Failed to open device {dev_id}: {stream_err}. Retrying in 3s...{bcolors.ENDC}")
                            time.sleep(3.0)
                            continue

                    try:
                        # Fetch samples with timeout to allow hot-swap checks
                        samples = audio_queue.get(timeout=0.1)
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
                                
                                # Final transcription (beam_size=1 implements Greedy Search, which is 3x faster and significantly reduces CPU usage)
                                segments, _ = model.transcribe(audio_data, beam_size=1, vad_filter=True)
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
            finally:
                if input_stream is not None:
                    try:
                        input_stream.stop()
                        input_stream.close()
                    except Exception:
                        pass

        VoiceRecog.worker_thread = threading.Thread(target=voice_recog_thread, daemon=True)
        VoiceRecog.worker_thread.start()
