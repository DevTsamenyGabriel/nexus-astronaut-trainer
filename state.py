"""state.py (Atlas). MissionState: the single source of truth every widget reads from.

SimState   = pure simulation data (no Qt), written only by backend.py.
MissionState = Qt-facing view with the SAME field names the UI already reads.
backend.sync() copies SimState into it and emits `changed`.
All numbers are SIMULATION VALUES, never real mission data."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class SimState:
    commander_name: str = ""           # Player's name (display only).
    destination: str = "moon"          # "moon" | "mars".
    day: int = 1                       # Mission day 1..30 (31 = mission over).
    resources: dict = field(default_factory=lambda: {   # Each 0-100, simulation values.
        "power": 90.0, "oxygen": 90.0, "water": 90.0, "food": 90.0})
    crew: list = field(default_factory=list)   # [{name, stress 0-100, skill 0-100, radiation 0-100}]
    active_event: Optional[dict] = None        # {id, title, question, options:[{id,label}]} or None.
    log: list = field(default_factory=list)    # Human-readable history, oldest first.
    readiness: float = 100.0           # Mission readiness 0-100.
    status: str = "active"             # "active" | "success" | "failed".
    comm_delay_min: int = 0            # One-way delay in minutes. Moon 0, Mars 3-22. Stored value only.
    flags: dict = field(default_factory=dict)  # co2, shielding, dust_days, crew_time_debt, zero_days, ...

    # ---- read-only values derived from the sim (the UI reads these) ----
    @property
    def radiation_level(self) -> float:
        """Highest crew radiation, 0-100 simulation units (100 = planning reference limit)."""
        return max((c["radiation"] for c in self.crew), default=0.0)

    @property
    def solar_status(self) -> str:
        """ACTIVE | SHELTER | EVA_DELAYED | CLEAR."""
        if self.active_event and self.active_event["id"] == "solar_particle":
            return "ACTIVE"
        return self.flags.get("solar_choice", "CLEAR")

    @property
    def training(self) -> list:
        """Four fixed training rows: [title, PASSED|PENDING|FAILED]."""
        r = self.resources
        n = max(len(self.crew), 1)
        stress = sum(c["stress"] for c in self.crew) / n

        def grade(v):
            return "PASSED" if v >= 50 else "FAILED" if v < 20 else "PENDING"
        return [["Life support (O2, water)", grade(min(r["oxygen"], r["water"]))],
                ["Power and food", grade(min(r["power"], r["food"]))],
                ["Radiation safety", grade(100 - self.radiation_level)],
                ["Crew stress", grade(100 - stress)]]


_SIM_OWNED = frozenset({
    "commander_name", "destination", "day", "resources", "crew", "active_event", "log",
    "readiness", "status", "comm_delay_min", "flags", "mission_day", "readiness_pct",
    "scenario_active", "solar_status", "radiation_level", "radiation_msv", "suit_o2_pct",
    "minutes_to_peak", "training"})   # Only the simulation may change these.


class MissionState(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.RLock()
        self.planned_eva_hours: float = 3.0   # Display only. Not used by the sim.
        self.surface_temp_c: float = 0.0      # NOT simulated. Nova: remove this row.
        self.solar_wind: str = "LOW"          # NOT simulated. Nova: remove this row.
        self.sim = SimState()
        self._apply(self.sim)

    # ------------------------------------------------------------------
    def _apply(self, s: SimState) -> None:
        # Contract fields (brief).
        self.commander_name = s.commander_name
        self.destination = s.destination
        self.day = s.day
        self.resources = dict(s.resources)
        self.crew = [dict(c) for c in s.crew]
        self.active_event = dict(s.active_event) if s.active_event else None
        self.log = list(s.log)
        self.readiness = s.readiness
        self.status = s.status
        self.comm_delay_min = s.comm_delay_min
        self.flags = dict(s.flags)
        # Names the existing UI reads.
        self.mission_day = min(s.day, 30)
        self.readiness_pct = int(round(s.readiness))
        self.scenario_active = s.active_event is not None
        self.solar_status = s.solar_status
        self.radiation_level = s.radiation_level
        self.radiation_msv = s.radiation_level      # LEGACY alias: sim units 0-100, NOT mSv. Nova: relabel.
        self.suit_o2_pct = s.resources["oxygen"]    # Sim oxygen resource.
        self.minutes_to_peak = s.flags.get("minutes_to_peak", 0.0) if self.scenario_active else 0.0
        self.training = s.training

    def sync(self, sim: SimState) -> None:
        """Called by the backend after every simulation call."""
        with self._lock:
            self.sim = sim
            self._apply(sim)
        self.changed.emit()

    def update(self, **fields) -> None:
        """Set display-only fields. Read-only or unknown fields are ignored (never crash)."""
        with self._lock:
            for key, value in fields.items():
                if key in _SIM_OWNED:
                    continue
                try:
                    if hasattr(self, key):
                        setattr(self, key, value)
                except (AttributeError, TypeError):
                    pass
        self.changed.emit()

    def tick(self) -> None:
        """Once per second. Counts down the display clock only. Changes NO simulation value."""
        with self._lock:
            if self.scenario_active:
                self.minutes_to_peak = max(0.0, self.minutes_to_peak - 1.0 / 60.0)
        self.changed.emit()

    def record_scenario_result(self, score) -> None:
        """Deprecated. Kept so old signal connections do not break. Does nothing.
        Choices are scored by the simulation through backend.apply_choice()."""
        return None
