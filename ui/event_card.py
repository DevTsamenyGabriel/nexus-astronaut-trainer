"""EventCard is now a thin controller (not a widget). It puts the event or daily question
into the NEXUS bar above the scene and the three chips into the choice bar below it.
It decides nothing. It only re-emits the id of the chip the player clicked."""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

# Compatibility for the Space Hazards display.
EXPLAIN_QUESTIONS = {
    "solar_particle": "Why should crew shelter during a solar particle event?",
    "equipment_failure": "Why is crew repair time limited during EVA operations?",
}

# Short chip labels, keyed by option id. Unknown ids fall back to the full label.
SHORT_LABELS = {
    "storm_shelter": "SHELTER IN PLACE", "storm_eva": "CLEAN PANELS", "storm_reserve": "USE BATTERIES",
    "spe_shelter": "GO TO SHELTER", "spe_postpone": "POSTPONE EVA", "spe_continue": "FINISH EVA",
    "scrub_swap": "SWAP CARTRIDGE", "scrub_repair": "REPAIR BY HAND", "scrub_ignore": "DEFER",
    "blight_destroy": "DESTROY TRAYS", "blight_treat": "WASH CROPS", "blight_eat": "HARVEST NOW",
    "equip_full": "FULL REPAIR", "equip_patch": "QUICK PATCH", "equip_cannibalize": "USE SPARE PART",
    "leak_seal": "SEAL MODULE", "leak_isolate": "ISOLATE MODULE", "leak_patch": "PATCH KIT",
    "dust_clean": "DEEP CLEAN", "dust_replace": "REPLACE SEALS", "dust_ignore": "KEEP GOING",
    "symptom_standdown": "STAND DOWN", "symptom_continue": "FINISH EVA", "symptom_ignore": "KEEP SCHEDULE",
}


class EventCard(QObject):
    chosen = pyqtSignal(str)
    explain = pyqtSignal(str)       # kept so existing wiring still connects; never emitted now

    def __init__(self, bar, choices, parent=None):
        super().__init__(parent)
        self._bar = bar
        self._choices = choices
        choices.chosen.connect(self.chosen)

    def show_event(self, event: dict) -> None:
        items = []
        for option in list(event.get("options", []))[:3]:
            option_id = str(option.get("id", ""))
            full = str(option.get("label", option_id))
            items.append((option_id, SHORT_LABELS.get(option_id, full.upper()), full))
        self._bar.set_text(str(event.get("question", "")), alert=True)
        self._choices.set_choices(items)

    def show_daily(self, question: str, items) -> None:
        self._bar.set_text(question, alert=False)
        self._choices.set_choices(items)

    def set_message(self, text: str, alert: bool = False) -> None:
        self._bar.set_text(text, alert=alert)
        self._choices.clear()

    def hide_event(self) -> None:
        self._choices.clear()
        self._bar.set_idle()

    # --- widget-like helpers so existing MissionView code keeps working ---
    def hide(self) -> None:
        self._choices.hide()

    def show(self) -> None:
        if self._choices.has_items():
            self._choices.show()

    def raise_(self) -> None:
        pass

    def isHidden(self) -> bool:
        return self._choices.isHidden()

    def setGeometry(self, *args) -> None:
        pass

    def option_buttons(self) -> list:
        return self._choices.buttons()

    def explain_button(self):
        return None
