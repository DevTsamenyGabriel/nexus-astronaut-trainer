"""NEXUS backend: the swap point for the real AI.

The UI only ever calls:
    NexusBackend().greeting(state)
    NexusBackend().respond(user_text, state)

To plug in RAG + Groq later, replace the body of this class and keep the
signatures. Nothing else in the app needs to change.

respond() is called from a worker thread, so it may block (network, LLM, etc.)
without freezing the UI.
"""
from __future__ import annotations

import config
import copy
import functools
import io
import json
import os
import random
import re
import time
import wave
import zlib

import numpy as np
from dotenv import load_dotenv

from events import EVENT_BY_ID, eligible
from state import MissionState, SimState

load_dotenv()

SIM_NOTE = " (Simulation values, not real NASA data.)"

# ---- Atlas: simulation constants (all SIMULATION VALUES) ----
DAYS = 30
RES = ("power", "oxygen", "water", "food")
CONSUMPTION = {"power": 4.0, "oxygen": 3.0, "water": 2.5, "food": 3.0}      # per day
BREAK_EVEN = {"power": 0.34, "oxygen": 0.26, "water": 0.20, "food": 0.26}   # effort share to break even at solar 1.0
SHIELD_BREAK_EVEN = 0.14   # offsets shielding decay of 3.5/day
NIGHT_POWER_LOAD = 1.0   # extra power use at lunar night (heating), simulation value
RAD_BASE = 1.0           # radiation per crew per day before shielding, simulation value
CREW = [("Ama", 70), ("Kofi", 60), ("Efua", 80), ("Yaw", 50)]
QUICK_SCHEDULE = {2: "solar_particle", 3: "crew_symptoms"}   # Quick Run only


def _clip(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _publishes(fn):
    """After a sim call, push the new SimState into the UI's MissionState."""
    @functools.wraps(fn)
    def wrapper(self, *a, **k):
        out = fn(self, *a, **k)
        self._publish()
        return out
    return wrapper

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DELIM = "|||ACTION|||"
_SENT_END = re.compile(r"(?<=[.!?])\s+")
KNOWLEDGE_TRIGGER = re.compile(
    r"^\s*(what|why|how|explain|define|tell me about)\b", re.I)

ACTION_PROMPT = """
Reply in 1-3 short spoken sentences. No markdown, no lists, no emojis.
Only if the commander clearly asks to open a screen or highlight a panel, add a final line:
|||ACTION|||{"type": "...", ...}
Allowed actions (never invent others):
{"type":"open_view","view":"mission|scenarios|hazards|knowledge|eva|progress"}
{"type":"start_scenario"}
{"type":"highlight","panel":"feeds|radar|readiness"}
You cannot change the mission. Never say you have activated, delayed, cancelled or chosen
anything: decisions are made by the Commander through the event options, and the simulation
applies them. Do not invent NASA procedure names, events or numbers. Label any figure as a
simulation value.
"""

SYSTEM_PROMPT = (
    "You are NEXUS, the AI copilot of a Moon and Mars outpost mission trainer. "
    "You explain and advise; you never decide outcomes and you never invent events, "
    "numbers or results. Mention an event only if the mission state says one is active. "
    "Use only numbers given in the mission state and call them simulation values. "
    "Radiation figures are planning references, never medical clearance. "
    "Answer in 2-4 concise sentences, in a warm, calm, professional tone — "
    "like a trusted AI companion: reassuring, clear, never robotic."
)


class StreamParser:
    """Turns streamed text deltas into sentences and an optional action."""

    def __init__(self):
        self.buf = ""
        self.action_raw = ""
        self.in_action = False

    def feed(self, delta: str) -> list[str]:
        if self.in_action:
            self.action_raw += delta
            return []
        self.buf += delta
        i = self.buf.find(DELIM)
        if i != -1:
            head = self.buf[:i]
            self.action_raw = self.buf[i + len(DELIM):]
            self.buf = ""
            self.in_action = True
            return [p.strip() for p in _SENT_END.split(head) if p.strip()]
        parts = _SENT_END.split(self.buf)
        self.buf = parts[-1]
        return [p.strip() for p in parts[:-1] if p.strip()]

    def finish(self):
        rest = []
        if not self.in_action and self.buf.strip():
            rest = [self.buf.strip()]
        self.buf = ""
        action = None
        raw = self.action_raw.strip()
        if raw:
            try:
                parsed = json.loads(raw)
                action = parsed if isinstance(parsed, dict) else None
            except ValueError:
                action = None
        return rest, action


# =====================================================================
# === BACKEND SWAP POINT: replace the internals of this class only ===
# =====================================================================
class NexusBackend:
    """Grok-powered backend with scripted offline fallback."""

    THINK_DELAY_S = 1.5   # simulated latency; only used in scripted fallback

    def __init__(self):
        self._client = None
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
            except Exception:
                self._client = None
        self._model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip() \
            or "openai/gpt-oss-120b"
        self._s = SimState()          # Atlas: simulation state
        self._rng = random.Random(0)
        self._ui = None

    # ================= Atlas: simulation (no AI, no network) =================
    def bind(self, ui_state):
        """Orion calls this once: backend.bind(self.state)."""
        self._ui = ui_state
        self._publish()

    def _publish(self):
        if self._ui is not None:
            try:
                self._ui.sync(self.get_state())
            except Exception:
                pass                      # the sim must never crash the UI

    @_publishes
    def start_mission(self, name, destination, seed=None):
        dest = destination if destination in ("moon", "mars") else "moon"
        self._rng = random.Random(seed if seed is not None else zlib.crc32(name.encode()))
        s = SimState(commander_name=name, destination=dest)
        s.crew = [{"name": n, "stress": 10.0, "skill": k, "radiation": 0.0} for n, k in CREW]
        s.flags = {"co2": 10.0, "shielding": 50.0, "dust_days": 0,
                   "crew_time_debt": 0.0, "zero_days": 0, "fail_reason": ""}
        s.comm_delay_min = self._delay(1, dest)
        s.log.append(f"Day 1: {name} takes command of the {dest} outpost (simulation values).")
        self._s = s
        return self.get_state()

    def get_state(self):
        return copy.deepcopy(self._s)

    def get_active_event(self):
        return copy.deepcopy(self._s.active_event)

    @staticmethod
    def _delay(day, dest):
        # Stored value only. Mars 3 -> 22 min across the mission. Moon 0.
        return 0 if dest == "moon" else 3 + round(19 * (day - 1) / (max(2, config.MISSION_DAYS) - 1))

    def _solar(self):
        s = self._s
        if s.destination == "moon":
            return 0.05 if ((s.day - 1) % 28) >= 14 else 1.0   # was 0.2
        return 0.3 if s.flags["dust_days"] > 0 else 0.8        # Mars dust storm / normal

    @staticmethod
    def _norm(alloc):
        keys = RES + ("shielding",)
        a = {k: max(0.0, float((alloc or {}).get(k, 1.0))) for k in keys}
        t = sum(a.values())
        return {k: (v / t if t > 0 else 0.2) for k, v in a.items()}

    @_publishes
    def advance_day(self, allocation=None):
        """Simulate the current day. allocation: optional {power,oxygen,water,food,shielding: weight}.
        Weights are normalised, so 'max everything' = an even split."""
        s = self._s
        if s.status != "active" or not s.crew:
            return self.get_state()
        if s.active_event:
            s.log.append("Resolve the active event before advancing.")
            return self.get_state()
        f, a, solar = s.flags, self._norm(allocation), self._solar()
        night = s.destination == "moon" and ((s.day - 1) % 28) >= 14
        for r in RES:
            prod = CONSUMPTION[r] / BREAK_EVEN[r] * a[r] * (solar if r == "power" else 1.0)
            cons = CONSUMPTION[r] + (NIGHT_POWER_LOAD if (night and r == "power") else 0.0)
            s.resources[r] = _clip(s.resources[r] + prod - cons)
        f["co2"] = _clip(f["co2"] + 1.5 - 7.5 * a["oxygen"])
        if f["co2"] > 60:
            s.resources["oxygen"] = _clip(s.resources["oxygen"] - 2)
        f["shielding"] = _clip(f["shielding"] + 25 * a["shielding"] - 3.5)
        low = any(s.resources[r] < 20 for r in RES)
        for c in s.crew:
            c["radiation"] += RAD_BASE * (1 - 0.7 * f["shielding"] / 100)
            d = 0.5 * (1 - c["skill"] / 200) + (3 if low else 0) + (2 if f["co2"] > 60 else 0)
            if all(s.resources[r] >= 50 for r in RES):
                d -= 1
            c["stress"] = _clip(c["stress"] + d)
        f["dust_days"] = max(0, f["dust_days"] - 1)
        f["crew_time_debt"] = max(0.0, f["crew_time_debt"] - 1)
        self._update_status()
        s.log.append(f"Day {s.day}: " + " ".join(f"{r} {s.resources[r]:.0f}" for r in RES)
                     + f" | CO2 {f['co2']:.0f} | readiness {s.readiness:.0f} (simulation values)")
        s.day += 1
        s.comm_delay_min = self._delay(min(s.day, config.MISSION_DAYS), s.destination)
        if s.status == "active":
            if s.day > config.MISSION_DAYS:
                ok = s.readiness >= 40
                s.status = "success" if ok else "failed"
                if not ok:
                    f["fail_reason"] = f"Readiness too low at day {config.MISSION_DAYS}."
            else:
                self._roll_event()
        return self.get_state()

    def _update_status(self):
        s, f = self._s, self._s.flags
        n = len(s.crew)
        ms = sum(c["stress"] for c in s.crew) / n
        mr = sum(c["radiation"] for c in s.crew) / n
        pen = 5 * sum(1 for r in RES if s.resources[r] < 20)
        s.readiness = _clip(100 - 0.35 * ms - 0.3 * mr - 3 * f["crew_time_debt"]
                            - 0.3 * max(0, f["co2"] - 40) - pen)
        f["zero_days"] = f["zero_days"] + 1 if any(s.resources[r] <= 0 for r in RES) else 0
        reason = ""
        if s.resources["oxygen"] <= 0:
            reason = "Oxygen ran out."
        elif f["zero_days"] >= 2:
            reason = "A critical system stayed at zero for 2 days."
        elif ms >= 90:
            reason = "Crew stress reached breaking point."
        elif max(c["radiation"] for c in s.crew) >= 100:
            reason = "Crew exposure reached the planning reference limit (simulation values)."
        if reason:
            s.status, f["fail_reason"] = "failed", reason
            s.log.append(f"MISSION FAILED: {reason}")

    def _roll_event(self):
        s = self._s
        if config.is_quick():
            forced = EVENT_BY_ID.get(QUICK_SCHEDULE.get(s.day))
            if forced is not None:
                self._start_event(forced)
            return
        for ev in eligible(s.destination, s.day):
            if self._rng.random() < ev.chance:
                self._start_event(ev)
                return

    def _start_event(self, ev):
        s = self._s
        self._apply_effects(ev.effects)
        s.active_event = {"id": ev.id, "title": ev.title, "question": ev.question,
                          "options": [{"id": o.id, "label": o.label} for o in ev.options]}
        if ev.id == "solar_particle":
            s.flags["minutes_to_peak"] = 45.0   # display-only simulation value
        s.log.append(f"Day {s.day} EVENT: {ev.title}")
        self._update_status()

    def _apply_effects(self, eff):
        s, f = self._s, self._s.flags
        for k, v in eff.items():
            if k in RES:
                s.resources[k] = _clip(s.resources[k] + v)
            elif k == "stress":
                for c in s.crew: c["stress"] = _clip(c["stress"] + v)
            elif k == "radiation":
                for c in s.crew: c["radiation"] = max(0.0, c["radiation"] + v)
            elif k == "shielding":
                f["shielding"] = _clip(f["shielding"] + v)
            elif k == "co2":
                f["co2"] = _clip(f["co2"] + v)
            elif k == "crew_time":
                f["crew_time_debt"] += v
            elif k == "dust_days":
                f["dust_days"] = max(0, f["dust_days"] + v)

    @_publishes
    def apply_choice(self, option_id):
        s = self._s
        if not s.active_event:
            return {"ok": False, "message": "No active event."}
        ev = EVENT_BY_ID.get(s.active_event["id"])
        opt = next((o for o in ev.options if o.id == option_id), None) if ev else None
        if opt is None:
            return {"ok": False, "message": "Unknown option."}
        self._apply_effects(opt.effects)
        s.log.append(f"Day {s.day} choice: {opt.label}. {opt.note}")
        if ev.id == "solar_particle":
            s.flags["solar_choice"] = {"spe_shelter": "SHELTER",
                                       "spe_postpone": "EVA_DELAYED"}.get(option_id, "CLEAR")
        s.active_event = None
        self._update_status()
        return {"ok": True, "message": opt.note, "effects": dict(opt.effects)}
    # ================= end Atlas simulation =================

    def _state_context(self, state: MissionState) -> str:
        """Describe the real simulation state. Never invent anything not in the state."""
        try:
            parts = [
                f"Commander: {state.commander_name or 'Commander'}.",
                f"Destination: {state.destination}. Mission day {state.mission_day} of {config.MISSION_DAYS}. "
                f"Mission status: {state.status}.",
                "Resources (0-100 simulation values): "
                + ", ".join(f"{k} {v:.0f}" for k, v in state.resources.items()) + ".",
                f"Readiness {state.readiness_pct} (simulation value). "
                f"Crew radiation, highest member: {state.radiation_level:.0f} of 100 "
                f"(simulation planning scale, not mSv).",
                f"Communication delay: {state.comm_delay_min} min one-way (simulation value).",
            ]
            ev = state.active_event
            if ev:
                parts.append(f"Active event: {ev['title']}. {ev['question']} Options: "
                             + "; ".join(o["label"] for o in ev["options"]) + ".")
            else:
                parts.append("No active event.")
            return " ".join(parts)
        except Exception:
            return "Mission state unavailable."

    def _chat(self, user_text: str, state: MissionState) -> str:
        """Call Grok via the OpenAI-compatible xAI endpoint."""
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + ACTION_PROMPT},
                {"role": "user", "content":
                    f"{self._state_context(state)}\n\nCommander says: {user_text}"},
            ],
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()

    def _build_messages(self, user_text: str, state: MissionState):
        return [
            {"role": "system", "content": SYSTEM_PROMPT + ACTION_PROMPT},
            {"role": "user", "content":
                f"{self._state_context(state)}\n\nCommander says: {user_text}"},
        ]

    def ask(self, question):
        """NASA-grounded answer from knowledge.py. Never raises."""
        try:
            import knowledge
            return knowledge.ask(question)
        except Exception:
            return {"answer": "AI: OFFLINE", "sources": []}

    def respond_stream(self, user_text, state):
        """Yield sentence events followed by an optional action event."""
        if KNOWLEDGE_TRIGGER.search(user_text or ""):
            result = self.ask(user_text) or {}
            answer = str(result.get("answer", ""))
            for sentence in _SENT_END.split(answer):
                if sentence.strip():
                    yield ("sentence", sentence.strip())
            if answer.strip() != "AI: OFFLINE":
                # Always tell the UI, even with no sources, so it can label "NOT FROM NASA SOURCES".
                yield ("action", {"type": "show_sources",
                                  "sources": list(result.get("sources") or [])})
            return
        if self._client is None:
            text = self.respond(user_text, state)
            for sentence in _SENT_END.split(text):
                if sentence.strip():
                    yield ("sentence", sentence.strip())
            return

        parser = StreamParser()
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=self._build_messages(user_text, state),
            stream=True,
            temperature=0.4,
            max_tokens=300,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                for sentence in parser.feed(delta):
                    yield ("sentence", sentence)
        rest, action = parser.finish()
        for sentence in rest:
            yield ("sentence", sentence)
        if action:
            yield ("action", action)

    def transcribe(self, audio) -> str | None:
        """Speech-to-text via Groq Whisper. Returns None if unavailable or silent."""
        if self._client is None or audio is None or len(audio) == 0:
            return None
        try:
            # Near-silence makes Whisper invent text (even in other languages): skip it.
            if float(np.sqrt(np.mean(np.square(audio)))) < 0.004:
                return None
            pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(pcm.tobytes())
            buf.seek(0)
            buf.name = "speech.wav"
            resp = self._client.audio.transcriptions.create(
                model="whisper-large-v3-turbo", file=buf, language="en",
                prompt="NEXUS mission control. Moon, Mars, EVA, radiation, shelter.",
                temperature=0)
            return (resp.text or "").strip() or None
        except Exception:
            return None

    def greeting(self, state: MissionState) -> str:
        """First line NEXUS speaks on startup. Uses only real state."""
        try:
            if not state.crew:
                return ("Welcome, Commander. I'm NEXUS, your mission copilot. "
                        "Say train on moon or train on mars to begin. "
                        "All values are simulation values.")
            ev = state.active_event
            tail = (f"Active event: {ev['title']}." if ev else "No active event.")
            return (f"Welcome back, Commander {state.commander_name}. "
                    f"Day {state.mission_day} of {config.MISSION_DAYS} at the {state.destination} outpost. {tail}")
        except Exception:
            return "Welcome, Commander. I'm NEXUS, your mission copilot."

    def respond(self, user_text: str, state: MissionState) -> str:
        """Reply to the commander's text. Never changes the mission, never invents numbers."""
        if self._client is not None:
            try:
                return self._chat(user_text, state)
            except Exception:
                return ("I can't reach the AI service right now. "
                        "Mission values are still available, Commander.")
        return self._status_reply(state)

    def _status_reply(self, state: MissionState) -> str:
        """Offline reply built only from the real simulation state."""
        try:
            if not state.crew:
                return ("No mission is running yet. Say 'train on moon' or 'train on mars' "
                        "to begin. All values are simulation values.")
            ev = state.active_event
            if ev:
                opts = "; ".join(o["label"] for o in ev["options"])
                return f"Active event: {ev['title']}. {ev['question']} Options: {opts}."
            r = state.resources
            return (f"Day {state.mission_day} of {config.MISSION_DAYS} at the {state.destination} outpost. "
                    f"Power {r['power']:.0f}, oxygen {r['oxygen']:.0f}, "
                    f"water {r['water']:.0f}, food {r['food']:.0f} (simulation values). "
                    f"No active event.")
        except Exception:
            return "Standing by, Commander."
