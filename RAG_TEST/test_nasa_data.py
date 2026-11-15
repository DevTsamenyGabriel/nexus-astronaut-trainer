"""Offline tests for nasa_data.py. Uses a temp cache folder and never touches the network."""
import json
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import nasa_data as nd

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


tmp = Path(tempfile.mkdtemp(prefix="nexus_cache_"))
nd.DATA_DIR = tmp  # keep the real data_cache untouched


def boom(*a, **k):
    raise OSError("simulated offline")


urllib.request.urlopen = boom

# 1. Empty cache + offline -> status "none", no exception
r = nd.get_neo()
check("neo offline, no cache -> none", r["status"] == "none" and r["objects"] == [])
r = nd.get_proton_flux()
check("proton offline, no cache -> none", r["status"] == "none" and r["flux_pfu"] is None
      and r["s_level"] is None)
r = nd.get_sep_history()
check("sep offline, no cache -> none", r["status"] == "none" and r["events"] == [])

# 2. S-scale thresholds
for flux, want in [(5, 0), (10, 1), (150, 2), (20000, 4), (2e5, 5)]:
    check(f"s_level({flux}) == {want}", nd.s_level(flux) == want)
check("s_level(None) is None", nd.s_level(None) is None)

# 3. NeoWs parser on a hand-written sample
sample = {"near_earth_objects": {"2026-11-15": [
    {"name": "(2026 AB)", "is_potentially_hazardous_asteroid": True,
     "estimated_diameter": {"meters": {"estimated_diameter_max": 120.5}},
     "close_approach_data": [{"miss_distance": {"kilometers": "312000.7"},
                              "relative_velocity": {"kilometers_per_second": "11.2"}}]},
    {"name": "broken"},
    {"name": "(2026 CD)", "is_potentially_hazardous_asteroid": False,
     "estimated_diameter": {"meters": {"estimated_diameter_max": 8}},
     "close_approach_data": [{"miss_distance": {"kilometers": "90000"},
                              "relative_velocity": {"kilometers_per_second": "7"}}]},
]}}
objs = nd.parse_neo(sample, "2026-11-15")
check("parser keeps 2, skips broken item", len(objs) == 2)
check("parser sorts nearest first", objs[0]["name"] == "(2026 CD)" and objs[0]["miss_km"] == 90000.0)
check("parser fields correct", objs[1]["hazardous"] is True and abs(objs[1]["speed_kms"] - 11.2) < 1e-9)

# 4. Stale cache + offline -> status "cached" with its original timestamp
old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat(timespec="seconds")
(tmp / "proton.json").write_text(json.dumps({"fetched": old, "data": {
    "source": "NOAA SWPC", "time_tag": "2026-11-14T10:00:00Z", "flux_pfu": 0.3, "s_level": 0}}))
r = nd.get_proton_flux()
check("stale cache offline -> cached with date", r["status"] == "cached"
      and r["flux_pfu"] == 0.3 and r["fetched"] == old)

# 5. Fresh cache -> cached and no network call at all
fresh = nd._iso(nd._now())
(tmp / "neo.json").write_text(json.dumps({"fetched": fresh, "data": {
    "source": "NASA NeoWs", "date": "2026-11-15",
    "objects": [{"name": "X", "miss_km": 1.0, "speed_kms": 2.0,
                 "diameter_m": 3.0, "hazardous": False}]}}))
calls = []


def counting(*a, **k):
    calls.append(1)
    raise OSError("offline")


urllib.request.urlopen = counting
r = nd.get_neo()
check("fresh cache -> cached, no network call", r["status"] == "cached"
      and len(r["objects"]) == 1 and calls == [])

print("RESULT:", "ALL PASS" if not failures else f"{len(failures)} FAILED")
sys.exit(1 if failures else 0)
