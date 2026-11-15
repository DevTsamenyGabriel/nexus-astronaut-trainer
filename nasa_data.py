"""nasa_data.py - Helios real-data layer for NEXUS (radar and space-weather chips).

No UI and no Qt imports. Every public function returns a dict and never raises.
Status values: "live" (fetched now), "cached" (saved copy, see "fetched"), "none" (no data).
Real values are for display only. They never change simulation outcomes.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()  # same pattern as backend.py
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data_cache"
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

TIMEOUT_S = 8
FRESH_S = 6 * 3600
SWPC_PROTON_URL = "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-6-hour.json"
DONKI_SEP_URL = "https://api.nasa.gov/DONKI/SEP"
NEO_FEED_URL = "https://api.nasa.gov/neo/rest/v1/feed"
# NOAA S-scale thresholds on >=10 MeV proton flux (pfu), highest first.
S_THRESHOLDS = [(100000, 5), (10000, 4), (1000, 3), (100, 2), (10, 1)]


def s_level(flux):
    """NOAA S-scale level for a proton flux in pfu. None if flux is missing."""
    try:
        if flux is None:
            return None
        f = float(flux)
    except (TypeError, ValueError):
        return None
    for threshold, level in S_THRESHOLDS:
        if f >= threshold:
            return level
    return 0


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _api_key():
    return (os.environ.get("NASA_API_KEY") or "").strip() or "DEMO_KEY"


def _fetch_json(url, params=None):
    if os.environ.get("NEXUS_OFFLINE") == "1":   # test switch
        raise OSError("forced offline")
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, headers={"User-Agent": "NEXUS-Helios/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------- cache ----------
def _cache_path(name):
    return DATA_DIR / (name + ".json")


def _read_cache(name):
    try:
        with open(_cache_path(name), "r", encoding="utf-8") as f:
            d = json.load(f)
        if (isinstance(d, dict) and isinstance(d.get("data"), dict)
                and isinstance(d.get("fetched"), str)):
            return d
    except Exception:
        pass
    return None


def _write_cache(name, payload):
    try:
        tmp = DATA_DIR / (name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, _cache_path(name))
    except Exception:
        pass  # a cache write failure must never break the app


def _cache_age_s(cached):
    try:
        ts = datetime.fromisoformat(cached["fetched"])
        return (_now() - ts).total_seconds()
    except Exception:
        return None


LAST_ERROR = {}


def _resolve(name, fetch_fn, empty, force=False):
    """Fresh cache -> network -> older cache -> empty. Never raises."""
    cached = _read_cache(name)
    age = _cache_age_s(cached) if cached else None
    if not force and age is not None and 0 <= age < FRESH_S:
        return dict(cached["data"], status="cached", fetched=cached["fetched"])
    try:
        data = fetch_fn()
        LAST_ERROR.pop(name, None)
        now = _iso(_now())
        _write_cache(name, {"fetched": now, "data": data})
        return dict(data, status="live", fetched=now)
    except Exception as exc:
        LAST_ERROR[name] = f"{type(exc).__name__}: {exc}"
    if cached:
        return dict(cached["data"], status="cached", fetched=cached["fetched"])
    return dict(empty, status="none", fetched="")


# ---------- parsers ----------
def parse_neo(feed, date_str):
    """Turn a NeoWs feed dict into a list of objects, nearest first. Bad items are skipped."""
    objs = []
    neos = (feed or {}).get("near_earth_objects") or {}
    for item in neos.get(date_str) or []:
        try:
            cad = (item.get("close_approach_data") or [{}])[0]
            miss = float((cad.get("miss_distance") or {}).get("kilometers"))
            speed = float((cad.get("relative_velocity") or {}).get("kilometers_per_second"))
            dia = float(((item.get("estimated_diameter") or {}).get("meters") or {})
                        .get("estimated_diameter_max"))
            objs.append({"name": str(item.get("name", "?")), "miss_km": miss,
                         "speed_kms": speed, "diameter_m": dia,
                         "hazardous": bool(item.get("is_potentially_hazardous_asteroid"))})
        except (TypeError, ValueError, AttributeError, IndexError):
            continue
    objs.sort(key=lambda o: o["miss_km"])
    return objs


# ---------- public functions ----------
def get_neo(date_str=None, force=False):
    """NASA NeoWs close approaches for one day (default: today UTC)."""
    day = date_str or _now().date().isoformat()

    def fetch():
        feed = _fetch_json(NEO_FEED_URL, {"start_date": day, "end_date": day,
                                          "api_key": _api_key()})
        return {"source": "NASA NeoWs", "date": day, "objects": parse_neo(feed, day)}

    return _resolve("neo", fetch, {"source": "NASA NeoWs", "date": day, "objects": []},
                    force=force)


def get_proton_flux(force=False):
    """Latest NOAA GOES >=10 MeV proton flux and its S-scale level."""
    def fetch():
        rows = _fetch_json(SWPC_PROTON_URL)
        if not isinstance(rows, list):
            raise ValueError("unexpected NOAA proton JSON")
        good = [r for r in rows if isinstance(r, dict) and r.get("energy") == ">=10 MeV"]
        if not good:
            raise ValueError("no >=10 MeV rows")
        best = max(good, key=lambda r: str(r.get("time_tag", "")))
        flux = float(best.get("flux"))
        return {"source": "NOAA SWPC", "time_tag": str(best.get("time_tag", "")),
                "flux_pfu": flux, "s_level": s_level(flux)}

    return _resolve("proton", fetch, {"source": "NOAA SWPC", "time_tag": "",
                                      "flux_pfu": None, "s_level": None}, force=force)


def get_sep_history(years=2, force=False):
    """NASA DONKI solar radiation storm (SEP) events, newest first.

    DONKI rejects long date ranges (HTTP 400), so the window is requested in
    30-day chunks and the results are merged.
    """
    def fetch():
        end = _now().date()
        start_all = end - timedelta(days=int(years * 365.25))
        seen = {}
        win_end = end
        while win_end > start_all:
            win_start = max(start_all, win_end - timedelta(days=30))
            rows = _fetch_json(DONKI_SEP_URL, {"startDate": win_start.isoformat(),
                                               "endDate": win_end.isoformat(),
                                               "api_key": _api_key()})
            if not isinstance(rows, list):
                raise ValueError("unexpected DONKI SEP JSON")
            for r in rows:
                if isinstance(r, dict) and r.get("sepID"):
                    sid = str(r.get("sepID"))
                    seen[sid] = {"id": sid, "time": str(r.get("eventTime") or "")}
            win_end = win_start - timedelta(days=1)
        events = sorted(seen.values(), key=lambda e: e["time"], reverse=True)
        return {"source": "NASA DONKI", "events": events}

    return _resolve("sep", fetch, {"source": "NASA DONKI", "events": []}, force=force)


# ---------- CLI ----------
def _main(argv):
    if "--refresh" not in argv:
        print("usage: python nasa_data.py --refresh")
        return 0
    neo = get_neo(force=True)
    proton = get_proton_flux(force=True)
    sep = get_sep_history(force=True)
    print("NEO    status=%s date=%s objects=%d fetched=%s" % (
        neo["status"], neo.get("date", ""), len(neo.get("objects") or []), neo.get("fetched", "")))
    print("PROTON status=%s flux_pfu=%s s_level=%s fetched=%s" % (
        proton["status"], proton.get("flux_pfu"), proton.get("s_level"), proton.get("fetched", "")))
    print("SEP    status=%s events=%d fetched=%s" % (
        sep["status"], len(sep.get("events") or []), sep.get("fetched", "")))
    for name, err in LAST_ERROR.items():
        print("ERROR  %s -> %s" % (name, err))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
