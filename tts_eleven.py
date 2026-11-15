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
# eleven_v3 understands inline audio tags like [warmly] or [tense].
# Override with ELEVENLABS_MODEL_ID in .env if needed.
MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_v3")
FALLBACK_MODEL_ID = "eleven_multilingual_v2"   # no audio-tag support
_TAG_MODEL = "eleven_v3"     # models that understand [audio tags]
SAMPLE_RATE = 16000          # matches output_format=pcm_16000
MAX_CHARS = 700              # protects the character quota
SPEED = float(os.environ.get("ELEVENLABS_SPEED", "1.15"))  # 0.7-1.2, medium-fast
LAST_ERROR = ""


def _key() -> str:
    return (os.environ.get("ELEVENLABS_API_KEY") or "").strip()


def _voice() -> str:
    return (os.environ.get("ELEVENLABS_VOICE_ID") or "").strip()


def is_configured() -> bool:
    return bool(_key() and _voice())


def _clean(text) -> str:
    return " ".join(str(text or "").split())[:MAX_CHARS]


def _strip_tags(text: str) -> str:
    """Remove [audio tag] markers for models that would speak them aloud."""
    import re
    return re.sub(r"\[[^\[\]]{1,40}\]", "", text).strip()


def _pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _cache_path(text: str, model: str) -> Path:
    raw = f"{_voice()}|{model}|{SPEED}|{text}".encode("utf-8")
    return CACHE_DIR / (hashlib.sha256(raw).hexdigest()[:24] + ".wav")


def _request(key: str, voice: str, model: str, text: str):
    """POST to ElevenLabs; return WAV bytes or None. Never raises."""
    global LAST_ERROR
    url = (API_URL + urllib.parse.quote(voice) + "?"
           + urllib.parse.urlencode({"output_format": "pcm_16000"}))
    body = json.dumps({"text": text, "model_id": model,
                       "voice_settings": {"speed": SPEED}}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        pcm = resp.read()
    if len(pcm) < 1000:
        LAST_ERROR = "audio too short"
        return None
    return _pcm_to_wav(pcm)


def _cached(path: Path):
    try:
        if path.exists():
            return path.read_bytes()           # works offline for repeated lines
    except Exception:
        pass
    return None


def _store(path: Path, wav: bytes) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav)
    except Exception:
        pass


def synthesize(text, mood: str = ""):
    """Return WAV bytes for text, or None. Never raises.

    mood: optional ElevenLabs v3 audio tag (e.g. "warmly", "tense"). It is
    sent as [mood] only to models that understand tags; the fallback model
    gets the plain text with tags stripped.
    """
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
        mood = " ".join(str(mood or "").split())[:40]
        tagged = f"[{mood}] {t}" if (mood and MODEL_ID == _TAG_MODEL) else t
        if os.environ.get("NEXUS_OFFLINE") == "1":
            LAST_ERROR = "forced offline"
            return None

        # 1) primary model (cached)
        path = _cache_path(tagged, MODEL_ID)
        hit = _cached(path)
        if hit:
            return hit
        try:
            wav = _request(key, voice, MODEL_ID, tagged)
        except urllib.error.HTTPError:
            wav = None
        if wav:
            _store(path, wav)
            return wav

        # 2) fallback model without audio tags (cached separately)
        plain = _strip_tags(tagged) or t
        path2 = _cache_path(plain, FALLBACK_MODEL_ID)
        hit = _cached(path2)
        if hit:
            return hit
        try:
            wav = _request(key, voice, FALLBACK_MODEL_ID, plain)
        except urllib.error.HTTPError as exc:
            LAST_ERROR = f"HTTP {exc.code}"
            return None
        except Exception as exc:
            LAST_ERROR = type(exc).__name__
            return None
        if wav:
            _store(path2, wav)
        return wav
    except urllib.error.HTTPError as exc:
        LAST_ERROR = f"HTTP {exc.code}"
        return None
    except Exception as exc:
        LAST_ERROR = type(exc).__name__
        return None
