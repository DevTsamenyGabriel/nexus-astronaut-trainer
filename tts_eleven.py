"""tts_eleven.py - optional ElevenLabs speech for NEXUS. Standard library only.

synthesize(text) returns WAV bytes, or None on any problem (no key, offline,
quota, bad voice id). The caller must then fall back to the existing voice.
It never raises. The key is read from the environment and never printed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()  # same pattern as backend.py
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "data_cache" / "tts"
API_URL = "https://api.elevenlabs.io/v1/text-to-speech/"
TIMEOUT_S = 10
MODEL_ID = "eleven_multilingual_v2"
SAMPLE_RATE = 16000          # matches output_format=pcm_16000
MAX_CHARS = 400              # protects the character quota
LAST_ERROR = ""


def _key() -> str:
    return (os.environ.get("ELEVENLABS_API_KEY") or "").strip()


def _voice() -> str:
    return (os.environ.get("ELEVENLABS_VOICE_ID") or "").strip()


def is_configured() -> bool:
    return bool(_key() and _voice())


def _clean(text) -> str:
    return " ".join(str(text or "").split())[:MAX_CHARS]


def _pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _cache_path(text: str) -> Path:
    raw = f"{_voice()}|{MODEL_ID}|{text}".encode("utf-8")
    return CACHE_DIR / (hashlib.sha256(raw).hexdigest()[:24] + ".wav")


def synthesize(text):
    """Return WAV bytes for text, or None. Never raises."""
    global LAST_ERROR
    LAST_ERROR = ""
    try:
        t = _clean(text)
        if not t:
            LAST_ERROR = "empty text"
            return None
        key, voice = _key(), _voice()
        if not key or not voice:
            LAST_ERROR = "ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID not set"
            return None
        path = _cache_path(t)
        try:
            if path.exists():
                return path.read_bytes()       # works offline for repeated lines
        except Exception:
            pass
        if os.environ.get("NEXUS_OFFLINE") == "1":
            LAST_ERROR = "forced offline"
            return None
        url = (API_URL + urllib.parse.quote(voice) + "?"
               + urllib.parse.urlencode({"output_format": "pcm_16000"}))
        body = json.dumps({"text": t, "model_id": MODEL_ID}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "xi-api-key": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            pcm = resp.read()
        if len(pcm) < 1000:
            LAST_ERROR = "audio too short"
            return None
        wav = _pcm_to_wav(pcm)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(wav)
        except Exception:
            pass
        return wav
    except urllib.error.HTTPError as exc:
        LAST_ERROR = f"HTTP {exc.code}"
        return None
    except Exception as exc:
        LAST_ERROR = type(exc).__name__
        return None
