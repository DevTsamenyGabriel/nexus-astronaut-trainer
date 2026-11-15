import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from backend import NexusBackend
import knowledge
import evidence_bank as eb

for dest in ("moon", "mars"):
    config.set_days(config.QUICK_DAYS)
    b = NexusBackend()
    b.start_mission("Test", dest)
    b.advance_day()
    ev = b.get_active_event()
    print(dest, "day", b.get_state().day, "event:", ev["id"])
    assert ev["id"] == "solar_particle"
    print(" ", b.apply_choice("spe_shelter")["ok"])
    b.advance_day()
    ev = b.get_active_event()
    print(dest, "day", b.get_state().day, "event:", ev["id"])
    assert ev["id"] == "crew_symptoms"
    print(" ", b.apply_choice("symptom_standdown")["ok"])
    b.advance_day()
    s = b.get_state()
    print(dest, "end: day", s.day, "status", s.status, "readiness", round(s.readiness))
    assert s.status in ("success", "failed") and s.day == 4

config.set_days(config.FULL_DAYS)
b = NexusBackend(); b.start_mission("Test", "moon")
print("full mission days:", config.MISSION_DAYS)
assert config.MISSION_DAYS == 30

for eid in ("solar_particle", "crew_symptoms"):
    _m, q = eb.question_for(eid, 2)
    pref, lim = eb.prefer_for(eid)
    print("\n", eid, "|", q)
    print(knowledge.evidence(q, prefer=pref, limit=lim))
