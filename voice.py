"""Voice I/O: microphone recording (with silence auto-stop) and TTS playback.

STT is done by the backend (Groq Whisper); this module only captures audio
and speaks text via Windows SAPI (pyttsx3, offline).
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
import subprocess
import queue
import winsound

import numpy as np
import sounddevice as sd

try:
    import tts_eleven
except Exception:
    tts_eleven = None

SAMPLE_RATE = 16000          # Whisper expects 16 kHz mono
MAX_SECONDS = 15.0           # hard cap on one utterance
SILENCE_RMS = 0.012          # below this = silence
END_SILENCE_S = 1.6          # patience after you stop talking
MIN_SPEECH_S = 0.35          # ignore clicks/coughs shorter than this
NOISE_CALIB_S = 0.4          # measure room noise at the start

_proc = None
_proc_lock = threading.Lock()
_el_playing = False


class MicRecorder:
    """Records mic audio until stop() is called or silence is detected."""

    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self._last_voice = 0.0
        self._heard_voice = False
        self._t0 = 0.0
        self._noise = 0.0
        self._voiced_s = 0.0
        self.level = 0.0
        self._session = 0
        self.on_auto_stop = None   # called when watchdog stops the recording

    def start(self) -> None:
        import time
        self.stop()
        self._chunks = []
        self._heard_voice = False
        self._last_voice = time.monotonic()
        self._t0 = time.monotonic()
        self._noise = 0.0
        self._voiced_s = 0.0
        self.level = 0.0
        self._session += 1
        session = self._session
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=1024, callback=self._callback)
        self._stream.start()
        threading.Thread(
            target=self._watchdog, args=(session,), daemon=True).start()

    def _callback(self, indata, frames, time_info, status):
        rms = float(np.sqrt(np.mean(indata ** 2)))
        now = time.monotonic()
        self.level = min(1.0, rms * 12)
        if now - self._t0 < NOISE_CALIB_S:
            self._noise = min(0.01, max(self._noise, rms))
        threshold = max(SILENCE_RMS, self._noise * 2.5)
        if rms > threshold:
            self._voiced_s += frames / SAMPLE_RATE
            if self._voiced_s >= MIN_SPEECH_S:
                self._heard_voice = True
                self._last_voice = now
        with self._lock:
            self._chunks.append(indata.copy())

    def _watchdog(self, session: int) -> None:
        """Auto-stop after trailing silence or max duration."""
        import time
        while session == self._session and self._stream is not None:
            time.sleep(0.1)
            now = time.monotonic()
            if now - self._t0 > MAX_SECONDS:
                break
            if self._heard_voice and now - self._last_voice > END_SILENCE_S:
                break
        if session != self._session:
            return
        if self._stream is not None:      # still recording -> auto-stop fired
            if self.on_auto_stop is not None:
                self.on_auto_stop()       # owner calls stop() to collect audio
            else:
                self.stop()

    def stop(self):
        """Stop recording and return float32 mono audio (may be empty)."""
        self._session += 1
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        with self._lock:
            chunks = self._chunks
            self._chunks = []
        if not chunks:
            return np.zeros(0, dtype="float32")
        return np.concatenate(chunks).reshape(-1)


def speak(text: str, on_done=None, mood: str = "") -> None:
    """Speak via ElevenLabs, falling back to Windows SAPI."""
    global _proc, _el_playing
    wav = None
    if tts_eleven is not None:
        try:
            wav = tts_eleven.synthesize(text, mood=mood)
        except Exception:
            wav = None
    if wav:
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav)
                path = f.name
            _el_playing = True
            winsound.PlaySound(path, winsound.SND_FILENAME)
        except Exception:
            pass
        finally:
            _el_playing = False
            if path:
                try:
                    os.remove(path)
                except Exception:
                    pass
        if on_done is not None:
            on_done()
        return
    ps = ("[Console]::InputEncoding=[Text.Encoding]::UTF8; "
          "Add-Type -AssemblyName System.Speech; "
          "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "$s.Speak([Console]::In.ReadToEnd())")
    proc = None
    try:
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with _proc_lock:
            _proc = proc
        proc.communicate(input=text.encode("utf-8"), timeout=120)
    except Exception:
        pass
    finally:
        with _proc_lock:
            if _proc is proc:
                _proc = None
        if on_done is not None:
            on_done()


def speak_async(text: str, on_done=None) -> None:
    stop_speaking()
    threading.Thread(target=speak, args=(text, on_done), daemon=True).start()


def stop_speaking() -> None:
    global _el_playing
    _el_playing = False
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
    with _proc_lock:
        proc = _proc
    if proc is not None and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass


def is_speaking() -> bool:
    with _proc_lock:
        return _proc is not None or _el_playing


class SpeechQueue:
    """Speaks sentences in order and clears pending speech on stop."""

    def __init__(self, on_idle=None, on_speaking=None):
        self.on_idle = on_idle
        self.on_speaking = on_speaking
        self._q: queue.Queue[tuple[int, str, str]] = queue.Queue()
        self._gen = 0
        self._pending = 0
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    @property
    def is_idle(self) -> bool:
        with self._lock:
            return self._pending == 0

    def say(self, sentence: str, mood: str = "") -> None:
        if not sentence.strip():
            return
        with self._lock:
            self._pending += 1
            gen = self._gen
        self._q.put((gen, sentence, mood))

    def stop(self) -> None:
        with self._lock:
            self._gen += 1
            self._pending = 0
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        stop_speaking()
        if self.on_speaking:
            self.on_speaking(False)

    def _run(self) -> None:
        while True:
            gen, first, mood = self._q.get()
            batch, count = [first], 1
            while True:
                try:
                    next_gen, sentence, _m = self._q.get_nowait()
                except queue.Empty:
                    break
                if next_gen == gen:
                    batch.append(sentence)
                    count += 1
            with self._lock:
                stale = gen != self._gen
            if not stale:
                if self.on_speaking:
                    self.on_speaking(True)
                speak(" ".join(batch), mood=mood)
            idle = False
            with self._lock:
                if gen == self._gen:
                    self._pending = max(0, self._pending - count)
                    idle = self._pending == 0
            if (idle or stale) and self.on_speaking:
                self.on_speaking(False)
            if idle and self.on_idle is not None:
                self.on_idle()
