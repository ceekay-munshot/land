#!/usr/bin/env python3
"""Geocode the YEIDA sectors referenced by live schemes -> real coordinates, so the map
can pin each scheme where it actually is.

"Sector 18" is ambiguous (Noida / Greater Noida / YEIDA all use it), so we bound Nominatim
tightly to the YEIDA corridor (south of Greater Noida, along the Yamuna Expressway) and
keep only hits inside it. Anything we can't place reliably is left unpinned — no fake
coordinates. Results are cached in web/data/yeida_sectors.json; a full dump for inspection
goes to _probe/yeida_geocode.json.

Runs on GitHub Actions (egress). Polite Nominatim use: 1 req/sec + identifying UA.
"""
import os
import re
import json
import time
import urllib.parse
import urllib.request

# YEIDA corridor bbox (excludes most Noida / Greater Noida sectors to the north).
LAT_MIN, LAT_MAX = 28.05, 28.45
LON_MIN, LON_MAX = 77.45, 77.95
UA = "LAND-map/1.0 (https://github.com/ceekay-munshot/land; ceekay@muns.io)"

# Reliable town anchors (sanity references + fallbacks for known clusters).
ANCHORS = ["Dankaur, Gautam Buddh Nagar, Uttar Pradesh, India",
           "Jewar, Gautam Buddh Nagar, Uttar Pradesh, India"]


def nominatim(q):
    url = ("https://nominatim.openstreetmap.org/search?"
           + urllib.parse.urlencode({"format": "jsonv2", "limit": 5, "q": q,
                                     "viewbox": f"{LON_MIN},{LAT_MAX},{LON_MAX},{LAT_MIN}",
                                     "bounded": 1}))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=40))
    except Exception as e:
        return {"query": q, "error": str(e)[:150], "results": []}
    res = [{"lat": float(r["lat"]), "lon": float(r["lon"]), "type": r.get("type"),
            "category": r.get("category"), "display_name": r.get("display_name")}
           for r in data]
    time.sleep(1.1)
    return {"query": q, "results": res}


def in_corridor(r):
    return LAT_MIN <= r["lat"] <= LAT_MAX and LON_MIN <= r["lon"] <= LON_MAX


def collect_sectors():
    secs = set()
    try:
        d = json.load(open("web/data/yeida_schemes.json"))
    except Exception:
        return []
    for s in d.get("schemes", []):
        for src in (s.get("sector"), (s.get("brochure") or {}).get("sectors")):
            for tok in re.findall(r"\d+[A-Z]?", src or ""):
                secs.add(tok)
    return sorted(secs)


def main():
    os.makedirs("_probe", exist_ok=True)
    os.makedirs("web/data", exist_ok=True)
    sectors = collect_sectors()
    dump = {"sectors": [], "anchors": []}

    for a in ANCHORS:
        dump["anchors"].append(nominatim(a))

    cache = {}
    for sec in sectors:
        rec = {"sector": sec, "attempts": []}
        for q in (f"Sector {sec}, Yamuna Expressway, Gautam Buddh Nagar, Uttar Pradesh, India",
                  f"YEIDA Sector {sec}, Uttar Pradesh, India",
                  f"Sector {sec}, Yamuna Expressway Industrial Development Authority"):
            r = nominatim(q)
            rec["attempts"].append(r)
            hit = next((x for x in r.get("results", []) if in_corridor(x)), None)
            if hit:
                rec["chosen"] = hit
                cache[sec] = {"lat": hit["lat"], "lng": hit["lon"],
                              "display_name": hit["display_name"], "query": q}
                break
        dump["sectors"].append(rec)

    json.dump(dump, open("_probe/yeida_geocode.json", "w"), ensure_ascii=False, indent=2)
    json.dump({"note": "Only YEIDA-corridor matches; unplaced sectors omitted (no fake coords).",
               "sectors": cache}, open("web/data/yeida_sectors.json", "w"),
              ensure_ascii=False, indent=2)
    print(f"sectors referenced: {sectors}")
    print(f"geocoded inside corridor: {sorted(cache)} ({len(cache)}/{len(sectors)})")


if __name__ == "__main__":
    main()
