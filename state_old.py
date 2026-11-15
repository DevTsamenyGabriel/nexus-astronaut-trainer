"""MissionState: the single source of truth every widget reads from.

Anything that mutates the state goes through update()/tick()/etc., which emit
`changed`. Widgets connect a bound method to `changed` and re-read the fields.
(Bound methods of QObjects are delivered on the GUI thread, so the backend
worker thread can safely call update().)
"""
from __future__ import annotations

import random
import threading

from PyQt6.QtCore import QObject, pyqtSignal


class MissionState(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.RLock()

        # --- Core mission fields (all values are SIMULATION values) ---
        self.mission_day: int = 3
        self.solar_status: str = "ACTIVE"      # ACTIVE | EVA_DELAYED | SHELTER
        self.scenario_active: bool = True
        self.radiation_msv: float = 67.0
        self.planned_eva_hours: float = 3.0
        self.minutes_to_peak: float = 6.0      # solar event peak countdown
        self.suit_o2_pct: float = 88.0
        self.readiness_pct: int = 72

        # --- Extra live-feed fields ---
        self.surface_temp_c: float = 127.0
        self.solar_wind: str = "LOW"           # LOW | MODERATE | HIGH

        # --- Training progress: [name, status] ---
        self.training: list[list[str]] = [
            ["Suit pressure & O₂ check", "PASSED"],
            ["Radiation shelter drill", "PASSED"],
            ["Solar flare EVA decision", "PENDING"],
            ["Asteroid proximity response", "FAILED"],
        ]

    # ------------------------------------------------------------------
    def update(self, **fields) -> None:
        """Set one or more fields and notify listeners."""
        with self._lock:
            for key, value in fields.items():
                if not hasattr(self, key):
                    raise AttributeError(f"MissionState has no field '{key}'")
                setattr(self, key, value)
        self.changed.emit()

    def tick(self) -> None:
        """Called once per second: countdown + small random drift of live values."""
        with self._lock:
            self.minutes_to_peak = max(0.0, self.minutes_to_peak - 1.0 / 60.0)
            self.radiation_msv = _walk(self.radiation_msv, 0.8, 62.0, 74.0)
            self.suit_o2_pct = _walk(self.suit_o2_pct, 0.2, 86.0, 89.5)
            self.surface_temp_c = _walk(self.surface_temp_c, 0.5, 124.0, 130.0)
        self.changed.emit()

    def record_scenario_result(self, score: int) -> None:
        """Store the (placeholder) result of the scenario view."""
        passed = score >= 70
        with self._lock:
            self.training[2][1] = "PASSED" if passed else "FAILED"
            delta = 6 if passed else -3
            self.readiness_pct = max(0, min(100, self.readiness_pct + delta))
        self.changed.emit()


def _walk(value: float, step: float, lo: float, hi: float) -> float:
    """Bounded random walk."""
    return max(lo, min(hi, value + random.uniform(-step, step)))
