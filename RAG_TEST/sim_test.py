"""sim_test.py (Atlas). 30-day terminal playthrough. No UI, no AI, no network."""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent            # ...\RAG_TEST
for _p in (_HERE.parent, _HERE.parent / "nexus_ai"):   # project root, then nexus_ai if present
    if _p.is_dir():
        sys.path.insert(0, str(_p))

from backend import NexusBackend, RES

STRATEGIES = {
    "max_everything": lambda s: {k: 100 for k in RES + ("shielding",)},
    "all_in_power":   lambda s: {"power": 100, "oxygen": 0, "water": 0, "food": 0, "shielding": 0},
    "adaptive":       lambda s: {**{r: 1 + max(0, 60 - s.resources[r]) / 10 for r in RES},
                                 "shielding": 0.6, "power": 1.6 + max(0, 60 - s.resources["power"]) / 10},
}


def play(dest, strat, seed, verbose=False):
    b = NexusBackend()
    s = b.start_mission("Gabby", dest, seed=seed)
    while s.status == "active":
        if s.active_event:
            b.apply_choice(s.active_event["options"][0]["id"])   # fixed policy: first option
        s = b.advance_day(STRATEGIES[strat](s))
        if verbose:
            print(f"D{s.day-1:02d} " + " ".join(f"{r}={s.resources[r]:5.1f}" for r in RES)
                  + f" co2={s.flags['co2']:4.0f} rad={max(c['radiation'] for c in s.crew):5.1f}"
                  + f" ready={s.readiness:5.1f} delay={s.comm_delay_min}")
    return s


if __name__ == "__main__":
    print("== Daily trace: adaptive, Mars, seed 1 (simulation values) ==")
    play("mars", "adaptive", 1, verbose=True)
    print("\n== Summary over seeds 1-10 ==")
    wins = {}
    for dest in ("moon", "mars"):
        for st in STRATEGIES:
            res = [play(dest, st, sd) for sd in range(1, 11)]
            w = sum(r.status == "success" for r in res)
            wins[(dest, st)] = w
            print(f"{dest:5} {st:15} success {w:2}/10 | avg readiness "
                  f"{sum(r.readiness for r in res)/10:5.1f} | e.g. {res[0].flags['fail_reason'] or 'ok'}")
    ok = all(wins[(d, "max_everything")] <= 3 and wins[(d, "adaptive")] >= 8
             for d in ("moon", "mars"))
    print("\nTRADE-OFF CHECK:",
          "PASS (maxing everything fails; careful play survives)" if ok
          else "FAIL (retune BREAK_EVEN / CONSUMPTION / NIGHT_POWER_LOAD)")
    sys.exit(0 if ok else 1)
