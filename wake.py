"""Offline wake-word listener ("hey nexus" / "nexus") using Vosk.

on_wake is called from a BACKGROUND thread: pass a Qt signal's .emit.
The mic stream is fully closed while paused, so MicRecorder can use the device.
"""
from __future__ import annotations

import json
import queue
import threading
import time

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

SAMPLE_RATE = 16000
GRAMMAR = json.dumps(["hey nexus", "nexus", "[unk]"])
COOLDOWN_S = 2.0


class WakeWordListener:
    def __init__(self, model_path: str, on_wake=None):
        SetLogLevel(-1)
        self._model = Model(model_path)
        self.on_wake = on_wake
        self._rec = None
        self._stream = None
        self._lock = threading.Lock()
        self._q: "queue.Queue[bytes]" = queue.Queue()
        self._last_wake = 0.0
        self._stop = False
        threading.Thread(target=self._worker, daemon=True).start()

    @property
    def active(self) -> bool:
        return self._stream is not None

    def resume(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._rec = KaldiRecognizer(self._model, SAMPLE_RATE, GRAMMAR)
            try:
                self._stream = sd.RawInputStream(
                    samplerate=SAMPLE_RATE, blocksize=4000, dtype="int16",
                    channels=1, callback=self._callback)
                self._stream.start()
            except Exception:
                self._stream = None

    def pause(self) -> None:
        with self._lock:
            stream, self._stream = self._stream, None
            self._rec = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def shutdown(self) -> None:
        self._stop = True
        self.pause()

    def _callback(self, indata, frames, time_info, status) -> None:
        self._q.put(bytes(indata))

    def _worker(self) -> None:
        while not self._stop:
            try:
                data = self._q.get(timeout=0.3)
            except queue.Empty:
                continue
            rec = self._rec
            if rec is None:
                continue
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "")
            else:
                text = json.loads(rec.PartialResult()).get("partial", "")
            if "nexus" in text.split() and (
                    time.monotonic() - self._last_wake > COOLDOWN_S):
                self._last_wake = time.monotonic()
                rec.Reset()
                if self.on_wake is not None:
                    self.on_wake()
