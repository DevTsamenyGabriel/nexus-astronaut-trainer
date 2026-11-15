"""NEXUS TRAINER: entry point and Controller."""
from __future__ import annotations

import config
import itertools
import re
import sys
import traceback
import faulthandler
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QLineEdit, QTextEdit

from backend import NexusBackend
from orb import NexusOrb
from state import MissionState
from ui import theme
from ui.common import mono
from ui.dashboard import DashboardWindow
import voice
import nasa_data
from wake import WakeWordListener
from knowledge import evidence, REFUSAL
from evidence_bank import question_for, aligned_option, prefer_for
import evidence_bank as _eb
_EVENT_Q = getattr(_eb, 'EVENT_QUESTIONS', {})
from ui.event_card import SHORT_LABELS
from ui.intel_panel import short_sources
from ui.entry_flow import EntryWindow

faulthandler.enable()          # also dumps native crashes

def _excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)

sys.excepthook = _excepthook

DEMO_PHRASES = [
    "What is the solar radiation risk?",
    "Can we shorten the EVA to 2 hours?",
    "Let's delay the EVA and use the shelter.",
]
WAKE_MODEL = str(Path(__file__).resolve().parent
                 / "models" / "vosk-model-small-en-us-0.15")
DEMO_VOICE_FALLBACK = False   # True = type a canned demo question when speech is not recognised

# ---- CONSTANTS (module level, after DEMO_VOICE_FALLBACK) ----
COMMANDER_NAME = "Gabs"
QUESTION_START = re.compile(r"^(what|why|how|explain)\b")
TRAIN_RE = re.compile(r"^train (?:on|for) (?:the )?(moon|mars)$")
QUICK_RE = re.compile(r"^quick(?: run)?(?: on| for)?(?: the)? (moon|mars)$")
BOOST_RE = re.compile(r"^boost (power|oxygen|water|food)$")
GAME_WORDS = {"ready", "go", "status", "abort", "show shelter", "radiation"}
HELP_TEXT = ("Commands: train on moon, train on mars, boost power, boost oxygen, "
             "boost water, boost food, ready, go, status, show shelter, radiation, "
             "repeat, abort, help. Ask what, why, how or explain for NASA science. "
             "All values are simulation values.")


class StreamWorker(QThread):
    sentence = pyqtSignal(int, str)
    action = pyqtSignal(int, dict)
    done = pyqtSignal(int)

    def __init__(self, backend, text, state, rid, parent=None):
        super().__init__(parent)
        self.backend, self.text, self.state, self.rid = backend, text, state, rid

    def run(self):
        try:
            sentences = []
            for kind, payload in self.backend.respond_stream(
                    self.text, self.state):
                if self.isInterruptionRequested():
                    break
                if kind == "sentence":
                    sentences.append(str(payload))
                else:
                    self.action.emit(self.rid, payload)
            if sentences:
                self.sentence.emit(self.rid, " ".join(sentences))
        except Exception as exc:
            self.sentence.emit(self.rid, f"Backend error: {exc}")
        self.done.emit(self.rid)


class TranscribeWorker(QThread):
    done = pyqtSignal(str)

    def __init__(self, backend, audio, parent=None):
        super().__init__(parent)
        self.backend, self.audio = backend, audio

    def run(self):
        try:
            text = self.backend.transcribe(self.audio)
        except Exception:
            text = None
        self.done.emit(text or "")


class DataWorker(QThread):
    """Fetches real NASA/NOAA data off the UI thread. Never raises."""
    done = pyqtSignal(dict)

    def run(self):
        result = {"neo": None, "proton": None, "sep": None}
        for key, fn in (("neo", nasa_data.get_neo),
                        ("proton", nasa_data.get_proton_flux),
                        ("sep", nasa_data.get_sep_history)):
            if self.isInterruptionRequested():
                break
            try:
                result[key] = fn()
            except Exception:
                result[key] = None
        self.done.emit(result)


class WarmupWorker(QThread):
    """Loads the NASA index and its embedding model once, off the UI thread, so the
    first real retrieval is instant. Never raises."""

    def run(self):
        try:
            import knowledge
            col = knowledge._get_collection()
            col.query(query_texts=["solar particle event"], n_results=1)
        except Exception:
            pass


class Controller(QObject):
    auto_stop = pyqtSignal()
    wake_detected = pyqtSignal()
    speech_idle = pyqtSignal()
    speaking_changed = pyqtSignal(bool)
    VIEWS = {
        "mission": 0, "scenarios": 1, "hazards": 2,
        "knowledge": 3, "eva": 4, "progress": 5,
    }

    # ---- CLASS ATTRIBUTES (inside class Controller, under VIEWS) ----
    mission_started = False
    _decisions = []
    pending_alloc: dict = {}
    _last_reply = ""
    _ended = False
    _intel_mode = False
    _intel_sourced = False
    _daily_options: list = []
    _spoken_key = None
    _welcome_pending = False
    _welcome_hold = False

    def __init__(self, app: QApplication, name: str = "") -> None:
        super().__init__()
        self.commander_name = (name or "").strip()
        self.app = app
        self.state = MissionState()
        self.backend = NexusBackend()
        bind = getattr(self.backend, "bind", None)
        if callable(bind):
            bind(self.state)
        self.window = DashboardWindow(self.state)
        self.orb = NexusOrb()
        self.busy = False
        self.listening = False
        self.speaking = False
        self._ptt = False
        self._req = 0
        self._row = None
        self._stream_done = True
        self._pending_action = None
        self._last_user_text = ""
        self._worker = None
        self._workers: list[QThread] = []
        self._phrases = itertools.cycle(DEMO_PHRASES)
        self.mic = voice.MicRecorder()
        self.auto_stop.connect(self.stop_listening)
        self.mic.on_auto_stop = self.auto_stop.emit
        self.orb.simulate_mic = False
        self.mic_timer = QTimer(self)
        self.mic_timer.setInterval(30)
        self.mic_timer.timeout.connect(
            lambda: self.orb.set_mic_level(self.mic.level))
        self.speech = voice.SpeechQueue(
            on_idle=self.speech_idle.emit,
            on_speaking=self.speaking_changed.emit)
        self.speech_idle.connect(self._maybe_finish)
        self.speaking_changed.connect(self._on_speaking_changed)
        self.wake = None
        try:
            self.wake = WakeWordListener(
                WAKE_MODEL, on_wake=self.wake_detected.emit)
            self.wake_detected.connect(self._on_wake)
        except Exception as exc:
            print(f"Wake word disabled: {exc}")

        chat = self.window.chat
        chat.submitted.connect(self.send_user_message)
        chat.mic_clicked.connect(self.toggle_listening)
        chat.stop_clicked.connect(self.interrupt)      # NEW
        self.window.command_requested.connect(self.send_user_message)
        self.window.event_choice.connect(self.choose_event_option)
        self.window.mission.card.explain.connect(self.send_user_message)
        self.window.mission.result.restart.connect(self._on_restart)
        self.window.mission.intel.continued.connect(self._offer_daily)
        briefing = getattr(self.window.mission, "briefing", None)
        if briefing is not None:
            briefing.start.connect(self._on_restart)
        self.state.changed.connect(self._check_end)
        self.orb.clicked.connect(self.toggle_listening)
        self.orb.show_dashboard_requested.connect(self.show_dashboard)
        self.orb.quit_requested.connect(app.quit)
        self.window.closing.connect(app.quit)
        self.state.changed.connect(self._sync_orb)
        app.aboutToQuit.connect(self._shutdown)
        app.installEventFilter(self)

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self.state.tick)

        self._data_worker = None
        self.space_data = {}
        self.data_timer = QTimer(self)
        self.data_timer.setInterval(30 * 60 * 1000)
        self.data_timer.timeout.connect(self._start_data_fetch)

    def _on_wake(self) -> None:
        if self.listening:
            return
        self.start_listening()      # no spoken reply: it was recorded and interrupted you

    def _on_speaking_changed(self, talking: bool) -> None:
        self.window.chat.set_speaking(talking)         # NEW
        self.orb.set_talking(talking)
        if talking and not self.listening:
            self.orb.set_state("speaking")

    def _update_wake(self) -> None:
        if self.wake is None:
            return
        if self.listening or self.busy or self.speaking:
            self.wake.pause()
        else:
            self.wake.resume()

    def start(self, greet: bool = True) -> None:
        self.window.show()
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.orb.move(geo.left() + 80, geo.bottom() - self.orb.height() - 70)
        self.orb.set_state("thinking")
        self.orb.show()
        self.tick_timer.start()
        if greet:
            QTimer.singleShot(600, self.window.chat.show_typing)
            QTimer.singleShot(1900, self._greet)
        QTimer.singleShot(1500, self._start_data_fetch)
        self.data_timer.start()

    def _greet(self) -> None:
        self._stream_done = False
        self._row = None
        self._pending_action = None
        greeting = self.backend.greeting(self.state)
        for sentence in re.split(r"(?<=[.!?])\s+", greeting):
            if sentence.strip():
                self._on_sentence(self._req, sentence.strip())
        self._on_stream_done(self._req)

    def show_dashboard(self) -> None:
        self.window.showFullScreen()
        self.window.raise_()
        self.window.activateWindow()

    def _shutdown(self) -> None:
        if self.wake is not None:
            self.wake.shutdown()
        self.speech.stop()
        self.data_timer.stop()
        for worker in self._workers:
            worker.requestInterruption()
            if not worker.wait(2500):
                worker.terminate()      # exit only: a network call may still be open
                worker.wait(500)

    def _start_data_fetch(self) -> None:
        """Fetch real NASA/NOAA data in the background (never on the UI thread)."""
        if self._data_worker is not None and self._data_worker.isRunning():
            return
        self._workers = [w for w in self._workers if w.isRunning()]
        worker = DataWorker(self)
        worker.done.connect(self._on_data)
        self._workers.append(worker)
        self._data_worker = worker
        worker.start()

    def _on_data(self, data: dict) -> None:
        def st(item):
            return (item or {}).get("status", "none")
        print("NASA data: neo=%s proton=%s sep=%s" % (
            st(data.get("neo")), st(data.get("proton")), st(data.get("sep"))))
        self.space_data = data
        win = self.window
        try:
            if hasattr(win, "radar_panel") and hasattr(win.radar_panel, "set_data"):
                win.radar_panel.set_data(data.get("neo"))
        except Exception as exc:
            print("radar update skipped: %s" % exc)
        try:
            if hasattr(win, "set_space_weather"):
                win.set_space_weather(data.get("proton"), data.get("sep"))
        except Exception as exc:
            print("space weather update skipped: %s" % exc)
        self._refresh_evidence()

    def _base_state(self) -> str:
        return "alert" if self.state.scenario_active else "idle"

    def _sync_orb(self) -> None:
        if self.orb.state_name in ("idle", "alert"):
            self.orb.set_state(self._base_state())

    def interrupt(self) -> None:
        self._req += 1
        self.speech.stop()
        if self._worker is not None:
            self._worker.requestInterruption()
        self.speaking = False
        self.window.chat.set_speaking(False)           # NEW
        self.busy = False
        self.window.chat.hide_typing()
        self.window.chat.set_busy(False)
        self.orb.hide_bubble()
        self._update_wake()

    # ---- METHODS (inside class Controller, before send_user_message) ----
    def _snapshot(self) -> dict:
        """Plain numbers from the real simulation state."""
        sim = self.backend.get_state()
        res = sim.resources
        return {
            "power": float(res.get("power", 0.0)),
            "oxygen": float(res.get("oxygen", 0.0)),
            "water": float(res.get("water", 0.0)),
            "food": float(res.get("food", 0.0)),
            "radiation": max((c.get("radiation", 0.0) for c in sim.crew), default=0.0),
            "day": int(sim.day),
        }

    def _verdict(self, snap: dict):
        """STABLE / CAUTION / CRITICAL from the same thresholds as the scene hotspots."""
        worst_key = min(("power", "oxygen", "water", "food"), key=lambda k: snap[k])
        worst = snap[worst_key]
        radiation = snap["radiation"]
        if worst < 20 or radiation >= 80:
            if worst < 20:
                return "critical", f"CRITICAL · {worst_key.title()} {worst:.0f}"
            return "critical", f"CRITICAL · Radiation {radiation:.0f}"
        if worst <= 50 or radiation >= 50:
            if worst <= 50:
                return "caution", f"CAUTION · {worst_key.title()} {worst:.0f}"
            return "caution", f"CAUTION · Radiation {radiation:.0f}"
        return "stable", "ALL SYSTEMS STABLE"

    def _show_report(self, headline: str, note: str, before: dict, after: dict) -> None:
        level, status = self._verdict(after)
        deltas = [
            ("Power", after["power"] - before["power"], True),
            ("Oxygen", after["oxygen"] - before["oxygen"], True),
            ("Water", after["water"] - before["water"], True),
            ("Food", after["food"] - before["food"], True),
            ("Radiation", after["radiation"] - before["radiation"], False),
        ]
        try:
            self.window.mission.report_show(headline, status, level, note, deltas)
        except Exception:
            pass

    def _report_after(self, clean: str, before: dict, effort) -> None:
        """Visible feedback after END DAY or the shelter command. Never crashes the app."""
        try:
            sim = self.backend.get_state()
            if sim.status != "active":
                return                      # the end screen takes over
            after = self._snapshot()
            if clean == "go":
                if after["day"] == before["day"]:
                    return
                event = self.backend.get_active_event()
                if event:
                    note = (f"New event: {event.get('title', 'Event')}. "
                            "Decide on the card below.")
                elif effort:
                    note = f"Extra crew effort went to {effort}."
                else:
                    note = "Balanced crew effort."
                self._show_report(f"DAY {before['day']} COMPLETE", note, before, after)
            else:
                self._show_report("SHELTER ORDERED", "", before, after)
        except Exception:
            pass

    def handle_command(self, text: str):
        """Return a reply string for a command, or None if text is a science question."""
        clean = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())
        clean = " ".join(clean.split())
        if QUESTION_START.match(clean):
            return None
        self._close_intel()
        if clean == "repeat":
            return self._last_reply or "Nothing to repeat yet."
        if TRAIN_RE.match(clean):
            self._decisions = []
        before, effort = None, None
        if self.mission_started and clean in ("go", "show shelter"):
            try:
                before = self._snapshot()
            except Exception:
                before = None
            effort = next(iter(self.pending_alloc), None)
        reply = self._run_command(clean)
        self._last_reply = reply
        if before is not None:
            self._report_after(clean, before, effort)
        try:
            self.window.levers.set_selected(next(iter(self.pending_alloc), None))
        except Exception:
            pass          # a highlight glitch must never block a command
        self._offer_daily()
        self._speak_event_prompt()
        return reply

    def _run_command(self, clean: str) -> str:
        try:
            quick = QUICK_RE.match(clean)
            match = TRAIN_RE.match(clean) or quick
            if match:
                dest = match.group(1)
                config.set_days(config.QUICK_DAYS if quick else config.FULL_DAYS)
                self.backend.start_mission((self.commander_name or COMMANDER_NAME), dest)
                self.mission_started = True
                self.pending_alloc = {}
                label = "Quick run started" if quick else "Mission started"
                return (f"{label} at the {dest} outpost. Day 1 of {config.MISSION_DAYS}. "
                        "Choose where the crew works, then press END DAY. "
                        "All values are simulation values.")
            if clean == "help":
                return HELP_TEXT
            boost = BOOST_RE.match(clean)
            if not self.mission_started:
                if boost or clean in GAME_WORDS:
                    return "No mission is running. Press START, or say train on moon or train on mars."
                return "I didn't catch a command. Say help to hear what I understand."
            if boost:
                res = boost.group(1)
                self.pending_alloc = {res: 2.0}
                return f"Extra effort set to {res}. Press END DAY to apply it (simulation values)."
            if clean == "ready":
                return self._status_text() + " Press END DAY to continue."
            if clean == "status":
                return self._status_text()
            if clean == "abort":
                self.mission_started = False
                self.pending_alloc = {}
                return "Mission aborted. Press START, or say train on moon or train on mars."
            if clean == "go":
                if self.window.mission.debrief_active:
                    return "Read the debrief and press CONTINUE first."
                state = self.backend.get_state()
                if state.status in ("success", "failed"):
                    return self._after_day(state)
                event = self.backend.get_active_event()
                if event:
                    return "Resolve the active event first. " + self._event_text(event)
                state = self.backend.advance_day(self.pending_alloc or None)
                self.pending_alloc = {}
                return self._after_day(state)
            if clean == "show shelter":
                event = self.backend.get_active_event()
                if event and event.get("id") == "solar_particle":
                    result = self.backend.apply_choice("spe_shelter")
                    if result.get("ok"):
                        return f"{result.get('message', 'Shelter ordered')} (simulation values)."
                    return "The shelter order had no effect."
                return "No solar event is active, so there is no shelter order to give."
            if clean == "radiation":
                state = self.backend.get_state()
                top = max((c.get("radiation", 0.0) for c in state.crew), default=0.0)
                shield = state.flags.get("shielding", 0.0)
                return (f"Highest crew radiation index is {top:.1f} and shielding is {shield:.0f} "
                        "(simulation values). This is a planning reference, "
                        "never medical clearance.")
            return "I didn't catch a command. Say help to hear what I understand."
        except Exception:
            return "That command failed safely. Say status to check the mission."

    def _event_text(self, event: dict) -> str:
        """Short spoken line. The options are shown on the event card, not read aloud."""
        return f"{event.get('title', 'Event')}. Choose an option on the screen."

    def _status_text(self) -> str:
        state = self.backend.get_state()
        if state.status in ("success", "failed"):
            return self._after_day(state)
        res = state.resources
        text = (f"Day {state.day} of {config.MISSION_DAYS} at the {state.destination} outpost. "
                f"Power {res['power']:.0f}, oxygen {res['oxygen']:.0f}, "
                f"water {res['water']:.0f}, food {res['food']:.0f} (simulation values).")
        event = self.backend.get_active_event()
        if event:
            text += " " + self._event_text(event)
        return text

    def _after_day(self, state) -> str:
        if state.status == "success":
            return (f"Mission complete. Success with readiness {state.readiness:.0f} "
                    "(simulation values).")
        if state.status == "failed":
            reason = state.flags.get("fail_reason") or "Mission failed."
            return f"Mission failed. {reason}"
        return self._status_text()

    def _deliver_reply(self, reply: str) -> None:
        self._intel_mode = False
        self._row, self._stream_done = None, False
        self._pending_action = None
        for sentence in re.split(r"(?<=[.!?])\s+", reply):
            if sentence.strip():
                self._on_sentence(self._req, sentence.strip())
        self._on_stream_done(self._req)

    def _daily_evidence(self) -> None:
        """Daily retrieval-only science briefing when no event is active."""
        try:
            sim = self.backend.get_state()
            mode, question = question_for(None, sim.day)
            hit = evidence(question)
            if hit.get("ok"):
                self.window.set_evidence(
                    "DAILY BRIEFING · RETRIEVAL ONLY",
                    question,
                    hit.get("text", ""),
                    hit.get("source", ""),
                    "Verbatim from indexed NASA/NOAA documents. No AI rewriting.",
                )
            else:
                self.window.set_evidence_empty(
                    "Daily science briefing",
                    "No indexed NASA excerpt matched today's science topic.",
                )
        except Exception:
            pass

    def _refresh_evidence(self) -> None:
        """Keep the right-side NASA EVIDENCE card in sync with the mission state."""
        try:
            sim = self.backend.get_state()
            event = self.backend.get_active_event()
            if event:
                mode, question = question_for(event.get("id"), sim.day)
                hit = evidence(question)
                if hit.get("ok"):
                    title = str(event.get("title", "Event"))
                    self.window.set_evidence(
                        "EVENT EVIDENCE · RETRIEVAL ONLY",
                        title,
                        hit.get("text", ""),
                        hit.get("source", ""),
                        "Verbatim from indexed NASA/NOAA documents. No AI rewriting.",
                    )
                else:
                    self.window.set_evidence_empty(
                        str(event.get("title", "Event")),
                        "No NASA excerpt in the index for this event.",
                    )
            else:
                self._daily_evidence()
        except Exception:
            pass

    _STOP_WORDS = {"go", "to", "the", "a", "an", "in", "on", "it", "out", "use", "by", "of", "and", "now"}

    def _typed_choice(self, text: str):
        """Map typed text to an option of the ACTIVE event. Plain matching in code, never AI.
        Returns an option id only when exactly one option matches."""
        try:
            event = self.backend.get_active_event()
            if not event:
                return self._typed_daily(text)
            options = list(event.get("options", []))[:3]
            clean = " ".join(re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split())
            if not clean or QUESTION_START.match(clean):
                return None
            for i, option in enumerate(options):
                if clean in (str(i + 1), f"option {i + 1}", f"number {i + 1}", f"choice {i + 1}"):
                    return str(option.get("id"))
            words = set(clean.split())
            hits = []
            for option in options:
                oid = str(option.get("id"))
                label = " ".join(re.sub(r"[^a-z0-9 ]", " ", str(option.get("label", "")).lower()).split())
                short = SHORT_LABELS.get(oid, "").lower().split()
                tokens = [w for w in short if w not in self._STOP_WORDS]
                if (len(clean) >= 5 and clean in label) or (tokens and all(w in words for w in tokens)):
                    hits.append(oid)
            return hits[0] if len(hits) == 1 else None
        except Exception:
            return None

    EFFORTS = ("power", "oxygen", "water", "food")
    _DAILY_TEXT = {
        "moon": (
            "Day {day} of {total} at the {place}. {low} reads {val:.0f} (simulation). "
            "Where does the crew work today?",
            "Lunar day {day} of {total}. {low} is your weakest system at {val:.0f} "
            "(simulation). Which system gets the extra effort?",
            "Day {day} of {total}. Regolith dust and long shadows are routine here, and "
            "{low} reads {val:.0f} (simulation). Where do you send the crew?",
        ),
        "mars": (
            "Day {day} of {total} at the {place}. {low} reads {val:.0f} (simulation). "
            "Where does the crew work today?",
            "Sol {day} of {total}. {low} is your weakest system at {val:.0f} "
            "(simulation). Which system gets the extra effort?",
            "Day {day} of {total}. Dust can cut the arrays for days here, and {low} reads "
            "{val:.0f} (simulation). Where do you send the crew?",
        ),
    }

    def _daily_prompt(self, sim):
        """Deterministic daily crew question. No AI, no numbers in the sentence."""
        res = sim.resources
        day = int(sim.day)
        total = int(config.MISSION_DAYS)
        dest = str(getattr(sim, "destination", "moon")).lower()
        place = "lunar outpost" if dest == "moon" else "Mars outpost"
        values = {key: float(res.get(key, 100.0)) for key in self.EFFORTS}
        low = min(self.EFFORTS, key=lambda k: values[k])
        cycle = ("food", "power", "oxygen", "water")
        omit = cycle[(day - 1) % 4]
        if omit == low:
            omit = cycle[day % 4]
        keys = [key for key in self.EFFORTS if key != omit]
        text = (f"Day {day} of {total} at the {place}. Choose ONE system for the crew "
                "to work on today. It gets extra effort, then the day ends.")
        items = [(f"effort:{key}", key.upper(),
                  f"Extra crew effort goes to {key}, then the day ends (simulation)")
                 for key in keys]
        return text, items, keys

    def _say_banner(self, text: str) -> None:
        """Speak exactly what the top banner shows. One voice for NEXUS: and NASA:."""
        try:
            clean = " ".join(str(text or "").split())
            if clean:
                self.speech.say(clean)
        except Exception:
            pass

    def _welcome_text(self, sim) -> str:
        name = (self.commander_name or COMMANDER_NAME)
        planet = str(getattr(sim, "destination", "moon")).title()
        return (f"Welcome to mission control, Commander {name}. I'm NEXUS, your NASA librarian "
                "with a flight suit. Ask me anything about space weather or radiation, by typing "
                "or speaking, and I'll pull the answer from NASA's own files. "
                f"{config.MISSION_DAYS} days on {planet}. Let's go!")

    def _release_welcome(self) -> None:
        if not self._welcome_hold:
            return
        self._welcome_hold = False
        self._offer_daily()

    def _speak_event_prompt(self) -> None:
        """Speak the event question once, when it appears in the banner."""
        try:
            event = self.backend.get_active_event()
            if not event or self.window.mission.debrief_active:
                return
            key = ("event", str(event.get("id")), int(self.backend.get_state().day))
            if key == self._spoken_key:
                return
            self._spoken_key = key
            self._say_banner(str(event.get("question", "")))
        except Exception:
            pass

    def _offer_daily(self) -> None:
        """Show today's question in the NEXUS bar with three chips, or hide it."""
        try:
            mission = self.window.mission
            self._daily_options = []
            if not self.mission_started:
                mission.hide_daily()
                return
            sim = self.backend.get_state()
            if sim.status != "active":
                mission.hide_daily()
                return
            if self.backend.get_active_event() or mission.debrief_active:
                return                      # the event card or debrief owns the bar
            if self._welcome_pending:
                self._welcome_pending = False
                self._welcome_hold = True
                welcome = self._welcome_text(sim)
                mission.nexus_bar.type_text(welcome)
                self._say_banner(welcome)
                QTimer.singleShot(12000, self._release_welcome)   # safety if audio fails
                return
            if self._welcome_hold:
                return
            text, items, keys = self._daily_prompt(sim)
            self._daily_options = keys
            mission.show_daily(int(sim.day), text, items)
            if getattr(mission, "_card_mode", None) == "daily":
                key = ("daily", int(sim.day))
                if key != self._spoken_key:
                    self._spoken_key = key
                    self._say_banner(text)
        except Exception:
            pass

    def _typed_daily(self, text: str):
        """Typed '1', '2', '3' or a resource name picks that day's chip. Plain matching in code."""
        try:
            options = list(self._daily_options)
            clean = " ".join(re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split())
            if not options or not clean or QUESTION_START.match(clean):
                return None
            for i, key in enumerate(options):
                if clean in (str(i + 1), key, f"boost {key}"):
                    return f"effort:{key}"
            return None
        except Exception:
            return None

    def _close_intel(self) -> None:
        """Close the INTEL panel unless the post-choice debrief is open."""
        try:
            if not self.window.mission.debrief_active:
                self.window.mission.intel_close()
        except Exception:
            pass

    _BAD_FRAGMENT = re.compile(r"(table|figure|appendix|gm/cm|et al\.|\bfig\b|\bref\b)", re.I)

    @staticmethod
    def _pick_sentence(text: str, question: str, limit: int = 190) -> str:
        """Choose the clearest whole sentence from a retrieved passage. Verbatim: nothing is
        rewritten. Table and figure fragments are skipped; the sentence sharing the most words
        with the fixed question wins."""
        clean = " ".join(str(text or "").split())
        wanted = set(re.findall(r"[a-z]{4,}", str(question or "").lower()))
        best, best_score = "", -99.0
        for part in re.split(r"(?<=[.!?])\s+", clean):
            sentence = part.strip()
            if len(sentence) < 40 or not sentence[:1].isupper():
                continue
            if Controller._BAD_FRAGMENT.search(sentence):
                continue
            if sum(char.isdigit() for char in sentence) > len(sentence) * 0.08:
                continue
            score = len(set(re.findall(r"[a-z]{4,}", sentence.lower())) & wanted)
            score -= len(sentence) / 400.0
            if score > best_score:
                best, best_score = sentence, score
        if not best:
            best = re.sub(r"^[^A-Z]*", "", clean) or clean
        if len(best) > limit:
            cut = best[:limit]
            space = cut.rfind(" ")
            best = (cut[:space] if space > 0 else cut).rstrip(" ,;:") + "..."
        return best

    def _show_debrief(self, event: dict, option_id: str, note: str) -> None:
        """NASA line in the banner after a choice, and spoken. Retrieval only, always cited.
        The lead-in wording is fixed code: it never decides an outcome."""
        try:
            event_id = str((event or {}).get("id", ""))
            line = REFUSAL
            if event_id in _EVENT_Q:
                _mode, question = question_for(event_id, self.backend.get_state().day)
                prefer, limit = prefer_for(event_id)
                hit = evidence(question, prefer=prefer, limit=limit) or {}
                if hit.get("ok"):
                    lead, tag = "Here's what the files say: ", ""
                    aligned = aligned_option(event_id)
                    if aligned:
                        if option_id == aligned:
                            lead = "Nice call, Commander! The files agree: "
                        else:
                            lead = "Close one, Commander! The files say: "
                            label = ""
                            for option in (event or {}).get("options", []):
                                if str(option.get("id")) == str(aligned):
                                    label = str(option.get("label", ""))
                            if label:
                                tag = f' The indexed documents support "{label}" instead.'
                    labels = short_sources([hit.get("source", "")])
                    cite = f" ({labels[0]})" if labels else ""
                    line = lead + str(hit.get("text", "")) + cite + tag
            chip = "CONTINUE  ›  NEXT DAY"
            if config.is_quick():
                day = int(self.backend.get_state().day)
                chip = ("CONTINUE  ›  RESULTS" if day >= config.MISSION_DAYS
                        else f"CONTINUE  ›  DAY {day + 1}")
            self.window.mission.debrief_start(line, chip_label=chip)
            self._say_banner(line.replace(", p. ", ", page "))
        except Exception:
            pass

    def _show_decision_evidence(self, event: dict, option_id: str) -> None:
        """After a successful choice, show a short debrief in the right-side evidence card."""
        try:
            event_id = str((event or {}).get("id", ""))
            title = str((event or {}).get("title", "Decision"))
            mode, question = question_for(event_id, self.backend.get_state().day)
            hit = evidence(question)
            aligned = aligned_option(event_id)
            if hit.get("ok"):
                if aligned:
                    status = ("NASA-aligned option chosen."
                              if option_id == aligned else "Different from the NASA-aligned option.")
                else:
                    status = "Event debrief from indexed documents."
                self.window.set_evidence(
                    "DECISION DEBRIEF · RETRIEVAL ONLY",
                    title,
                    hit.get("text", ""),
                    hit.get("source", ""),
                    status,
                )
            else:
                self.window.set_evidence_empty(
                    title,
                    "No NASA excerpt in the index for this event.",
                )
        except Exception:
            pass

    def _check_end(self) -> None:
        """On every state change: show the result card when the real mission has ended,
        and clear it when a new mission is running."""
        try:
            sim = self.backend.get_state()
            status = getattr(sim, "status", "active")
        except Exception:
            return
        if status in ("success", "failed"):
            if not self._ended:
                self._ended = True
                self._show_end(sim)
        elif self._ended:
            self._ended = False
            try:
                self.window.mission.result_hide()
                self.window.levers.set_enabled(True)
                self._daily_evidence()
            except Exception:
                pass

    def _show_end(self, sim) -> None:
        """Build the end screen only from real simulation state and the decision log."""
        try:
            total = config.MISSION_DAYS
            success = sim.status == "success"
            if success:
                headline = "MISSION COMPLETE"
                detail = (f"Commander {sim.commander_name} kept the {sim.destination} "
                          f"outpost running for {total} days.")
            else:
                headline = "MISSION FAILED"
                detail = sim.flags.get("fail_reason") or "The mission could not continue."
            res = sim.resources
            top = max((c.get("radiation", 0.0) for c in sim.crew), default=0.0)
            days = max(0, min(sim.day - 1, total))
            stats = [
                f"Days completed: {days} of {total}  ·  {sim.destination.upper()}  ·  "
                f"readiness {sim.readiness:.0f}",
                f"Power {res['power']:.0f}  ·  Oxygen {res['oxygen']:.0f}  ·  "
                f"Water {res['water']:.0f}  ·  Food {res['food']:.0f}",
                f"Highest crew radiation index {top:.1f} (planning reference, "
                "not medical clearance)",
            ]
            if self._decisions:
                stats.append("")
                stats.append("YOUR DECISIONS")
                for item in self._decisions[:4]:
                    stats.append(f"Day {item['day']} · {item['title']}: {item['choice']}")
            self.window.mission.result_show(success, headline, detail, stats)
        except Exception:
            pass          # the end screen must never crash the app

    def begin_mission(self, dest: str) -> None:
        """Start the chosen mission through the single existing start route."""
        briefing = getattr(self.window.mission, "briefing", None)
        if briefing is not None:
            try:
                briefing.hide_briefing()
            except Exception:
                pass
        self._welcome_pending = True
        self._on_restart(dest)

    def _on_restart(self, dest: str) -> None:
        if dest in ("moon", "mars"):
            self.send_user_message(f"train on {dest}")
        elif dest in ("moon-quick", "mars-quick"):
            self.send_user_message(f"quick run on {dest.split('-')[0]}")

    def choose_daily_effort(self, effort: str) -> None:
        """A daily chip was clicked. Same path as typing 'boost <resource>' then 'go'."""
        self._daily_options = []
        if effort in ("power", "oxygen", "water", "food"):
            self.pending_alloc = {effort: 2.0}
        else:
            self.pending_alloc = {}
        self.send_user_message("go")

    def choose_event_option(self, option_id: str) -> None:
        """Player clicked an event option. The backend decides the outcome; we only report it."""
        if str(option_id).startswith("effort:"):
            self.choose_daily_effort(str(option_id).split(":", 1)[1])
            return
        if str(option_id) == "nexus:continue":
            self.window.mission.debrief_finish()
            if config.is_quick() and self.mission_started:
                self.send_user_message("go")      # same path as typing go: advance once
            else:
                self._offer_daily()
            return
        self._daily_options = []
        self.interrupt()
        label = option_id
        event = None
        try:
            before = self._snapshot()
        except Exception:
            before = None
        try:
            event = self.backend.get_active_event()
            for option in (event or {}).get("options", []):
                if option.get("id") == option_id:
                    label = str(option.get("label", option_id))
        except Exception:
            pass
        try:
            self.window.chat.add_message(f"Choice: {label}", is_user=True)
        except Exception:
            pass
        try:
            result = self.backend.apply_choice(option_id) or {}
        except Exception:
            result = {}
        if result.get("ok"):
            note = str(result.get("message") or "Choice applied")
            reply = f"{note} (simulation values). Read the debrief, then press Continue."
            try:
                entry = {"day": before["day"] if before else 0,
                         "title": str((event or {}).get("title", "Event")),
                         "choice": label}
                self._decisions = list(self._decisions) + [entry]
            except Exception:
                pass
            try:
                sim = self.backend.get_state()
                if sim.status == "active":
                    if before is not None:
                        self._show_report(f"DECISION · {label}", note,
                                          before, self._snapshot())
                    self._show_debrief(event, option_id, note)
            except Exception:
                pass
        else:
            reply = "That choice had no effect. Pick another option."
            try:
                if event:
                    self.window.mission.show_event(event)
            except Exception:
                pass
        self._last_reply = reply
        self._deliver_reply(reply)

    def send_user_message(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.interrupt()
        rid = self._req
        self._row, self._stream_done = None, False
        self._pending_action, self._last_user_text = None, text
        self.busy = True
        chat = self.window.chat
        chat.add_message(text, is_user=True)
        option_id = self._typed_choice(text)
        if option_id:
            self.choose_event_option(option_id)
            return

        reply = self.handle_command(text)
        if reply is not None:
            self._intel_mode = False
            self._close_intel()
            self._deliver_reply(reply)
            return

        self._intel_mode, self._intel_sourced = True, False
        try:
            self.window.mission.intel_start(text)
        except Exception:
            pass
        chat.show_typing()
        self.orb.set_state("thinking")

        self._workers = [w for w in self._workers if w.isRunning()]
        worker = StreamWorker(self.backend, text, self.state, rid, self)
        worker.sentence.connect(self._on_sentence)
        worker.action.connect(self._on_action)
        worker.done.connect(self._on_stream_done)
        self._workers.append(worker)
        self._worker = worker
        worker.start()
        self._update_wake()

    def _on_sentence(self, rid: int, sentence: str) -> None:
        if rid != self._req:
            return
        chat = self.window.chat
        if self._row is None:
            chat.hide_typing()
            self._row = chat.add_message(sentence, is_user=False)
            self.speaking = True
            self.orb.set_state("speaking")
        else:
            self._row.append_text(sentence)
        if self._intel_mode:
            try:
                self.window.mission.intel_append(sentence)
            except Exception:
                pass
        self.orb.say(sentence, 5.0)
        if self._intel_mode:
            self.speech.say(sentence, mood=self._speech_mood())      # only science answers shown in the banner are spoken here

    def _speech_mood(self) -> str:
        """ElevenLabs v3 audio tag for the current moment."""
        try:
            if self.backend.get_active_event():
                return "tense"
            if getattr(self.state, "status", "") in ("success", "failed"):
                return "emotional"
        except Exception:
            pass
        return "warmly"

    def _on_action(self, rid: int, action: dict) -> None:
        if rid != self._req:
            return
        self._pending_action = action
        if self._intel_mode and action.get("type") == "show_sources":
            sources = action.get("sources")
            sources = list(sources) if isinstance(sources, (list, tuple)) else []
            self._intel_sourced = True
            try:
                self.window.mission.intel_sources(sources, bool(sources))
            except Exception:
                pass

    def _on_stream_done(self, rid: int) -> None:
        if rid != self._req:
            return
        self._stream_done = True
        self.busy = False
        if self._row is None:
            self.window.chat.hide_typing()
        if self._pending_action:
            self.run_action(self._pending_action)
        if self._intel_mode and not self._intel_sourced:
            self._intel_sourced = True
            try:
                self.window.mission.intel_sources([], False)
            except Exception:
                pass
        self._maybe_finish()
        self._update_wake()

    def _maybe_finish(self) -> None:
        if self._stream_done and self.speech.is_idle:
            self.speaking = False
            self.window.chat.set_speaking(False)       # NEW
            if not self.listening and self.orb.state_name == "speaking":
                self.orb.set_state(self._base_state())
            if self._welcome_hold:
                self._release_welcome()
        self._update_wake()

    def run_action(self, action: dict) -> None:
        """Execute only known, well-formed actions. Simulation changes go through the backend."""
        kind = action.get("type")
        said = self._last_user_text.lower()
        win, chat = self.window, self.window.chat
        try:
            if kind == "show_sources":
                sources = action.get("sources")
                sources = list(sources) if isinstance(sources, (list, tuple)) else []
                chat.add_sources(sources, from_nasa=bool(sources))
            elif kind == "open_view" and action.get("view") in self.VIEWS:
                view = action["view"]
                win.show_view(self.VIEWS[view])
                chat.add_action_chip(f"OPENED {view.upper()}")
            elif kind == "start_scenario":
                win.open_scenario()
                chat.add_action_chip("SCENARIO STARTED")
            elif kind in ("activate_shelter", "delay_eva"):
                word, option_id = (("shelter", "spe_shelter") if kind == "activate_shelter"
                                   else ("delay", "spe_postpone"))
                if word in said:
                    event = self.state.active_event
                    if event and event.get("id") == "solar_particle":
                        result = self.backend.apply_choice(option_id)
                        if result.get("ok"):
                            chat.add_action_chip(f"{result.get('message', 'DONE')} (SIM)".upper())
                        else:
                            chat.add_action_chip("NO EFFECT")
                    else:
                        chat.add_action_chip("NO SOLAR EVENT ACTIVE")
            elif kind == "set_eva_hours":
                chat.add_action_chip("EVA HOURS COME FROM EVENT CHOICES")
            elif kind == "highlight":
                win.flash(str(action.get("panel")))
        except Exception:
            pass          # a bad action must never crash the app

    def toggle_listening(self) -> None:
        if self.listening:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self) -> None:
        if self.listening:
            return
        self.interrupt()
        if self.wake is not None:
            self.wake.pause()
        self.listening = True
        self.window.chat.set_listening(True)
        self.orb.set_state("listening")
        self.orb.say("Listening…", 60)
        try:
            self.mic.start()
            self.mic_timer.start()
        except Exception:
            pass
        self._update_wake()

    def stop_listening(self) -> None:
        if not self.listening:
            return
        self.listening = False
        self.mic_timer.stop()
        self.window.chat.set_listening(False)
        self.orb.hide_bubble()
        audio = self.mic.stop()
        if len(audio) > 0:
            worker = TranscribeWorker(self.backend, audio, self)
            worker.done.connect(self._on_transcribed)
            self._workers.append(worker)
            worker.start()
        else:
            if DEMO_VOICE_FALLBACK:
                self.send_user_message(next(self._phrases))
            else:
                self.window.chat.add_action_chip("DIDN'T CATCH THAT")
        self._update_wake()

    def _on_transcribed(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            if DEMO_VOICE_FALLBACK:
                text = next(self._phrases)
            else:
                self.window.chat.add_action_chip("DIDN'T CATCH THAT")
                return
        self.send_user_message(text)

    def eventFilter(self, obj, event):
        event_type = event.type()
        if (event_type == QEvent.Type.KeyPress
                and event.key() == Qt.Key.Key_Escape):
            self.interrupt()
            return True
        if event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) \
                and event.key() == Qt.Key.Key_Space:
            if isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit)):
                return False
            if event.isAutoRepeat():
                return True
            if event_type == QEvent.Type.KeyPress and not self._ptt:
                self._ptt = True
                self.start_listening()
            elif event_type == QEvent.Type.KeyRelease and self._ptt:
                self._ptt = False
                self.stop_listening()
            return True
        return False


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NEXUS TRAINER")
    app.setFont(mono(10))
    app.setStyleSheet(theme.GLOBAL_QSS)

    holder: list = []                 # keeps the Controller alive
    entry = EntryWindow()
    warm = WarmupWorker()
    warm.start()
    app.aboutToQuit.connect(lambda: warm.wait(3000))

    def on_ready(name: str, dest: str) -> None:
        try:
            controller = Controller(app, name)
            holder.append(controller)
            controller.start(greet=False)
            controller.begin_mission(dest)
        except Exception:
            traceback.print_exc()
            for c in holder:          # hide a half-started dashboard, never close it
                c.window.hide()
                c.orb.hide()
            holder.clear()
            entry.back_to_destination()
            return
        entry.close()

    entry.ready.connect(on_ready)
    entry.showFullScreen()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
