"""Evidence bank: fixed questions whose retrieved NASA/NOAA passages were checked by hand
for clarity. Code, not AI, chooses which question to retrieve for. Retrieval only."""
from __future__ import annotations

# Decision evidence: only for events the NASA index can genuinely support.
EVENT_QUESTIONS = {
    "solar_particle": "What dose ranges do large solar particle events contribute?",
    "crew_symptoms": "What are the acute radiation syndrome risks for astronauts?",
}

# Daily briefing rotation, used whenever no covered decision is on screen.
DAILY_QUESTIONS = (
    "How long can a solar particle event last?",
    "What is a geomagnetic storm?",
    "How does space weather affect astronauts?",
    "What is the difference between solar flares and coronal mass ejections?",
    "What are the acute radiation syndrome risks for astronauts?",
    "Why does NASA plan to return to the Moon?",
)

# The option that matches NASA guidance, written by hand, only where a document supports it.
NASA_ALIGNED = {"solar_particle": "spe_shelter", "crew_symptoms": "symptom_standdown"}


def question_for(event_id, day) -> tuple:
    """Return (mode, question). mode is 'decision' for a covered event, else 'briefing'."""
    if event_id in EVENT_QUESTIONS:
        return "decision", EVENT_QUESTIONS[event_id]
    index = (max(int(day or 1), 1) - 1) % len(DAILY_QUESTIONS)
    return "briefing", DAILY_QUESTIONS[index]


def aligned_option(event_id):
    """The NASA-aligned option id for an event, or None if no document supports one."""
    return NASA_ALIGNED.get(event_id)


# Words that steer which retrieved sentence is shown, plus a display length limit.
EVENT_PREFER = {
    "solar_particle": (("cannot be predicted",), 300),
    "crew_symptoms": (("hematopoietic",), 300),
}


def prefer_for(event_id):
    """(prefer words, length limit) for an event's NASA line."""
    return EVENT_PREFER.get(event_id, (None, 240))
