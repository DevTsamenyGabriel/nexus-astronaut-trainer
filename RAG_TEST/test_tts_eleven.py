"""Tests for tts_eleven.py. Default run is offline. Use --live for a real call."""
import io
import os
import sys
import tempfile
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import tts_eleven as tts

LIVE = "--live" in sys.argv
failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


if not LIVE:
    tts.CACHE_DIR = Path(tempfile.mkdtemp(prefix="nexus_tts_"))
    os.environ["ELEVENLABS_API_KEY"] = "dummy"
    os.environ["ELEVENLABS_VOICE_ID"] = "dummy"
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise OSError("simulated offline")

    urllib.request.urlopen = boom

    check("offline, no cache -> None", tts.synthesize("Hello commander.") is None
          and tts.LAST_ERROR != "")
    check("empty text -> None", tts.synthesize("   ") is None)

    wav = tts._pcm_to_wav(b"\x00\x01" * 8000)
    with wave.open(io.BytesIO(wav), "rb") as w:
        ok = (w.getnchannels() == 1 and w.getsampwidth() == 2
              and w.getframerate() == 16000)
    check("wav header mono/16-bit/16000", ok)

    tts.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tts._cache_path("Cached line.").write_bytes(wav)
    calls.clear()
    check("cache hit works offline, no network call",
          tts.synthesize("Cached line.") == wav and calls == [])

    os.environ["ELEVENLABS_API_KEY"] = ""
    check("no key -> None", tts.synthesize("Hi there.") is None)

    print("RESULT:", "ALL PASS" if not failures else f"{len(failures)} FAILED")
    sys.exit(1 if failures else 0)
else:
    if not tts.is_configured():
        print("FAIL: set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env")
        sys.exit(1)
    audio = tts.synthesize("Systems are nominal. All values are simulation values.")
    if audio is None:
        print("LIVE FAIL:", tts.LAST_ERROR)
        sys.exit(1)
    out = HERE / "tts_sample.wav"
    out.write_bytes(audio)
    print("LIVE OK: %d bytes saved to %s" % (len(audio), out))
    try:
        import winsound
        winsound.PlaySound(str(out), winsound.SND_FILENAME)
    except Exception as exc:
        print("playback skipped:", type(exc).__name__)
