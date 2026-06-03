#!/usr/bin/env python3
"""Fetch real cadastral parcels for Gautam Buddh Nagar villages from UP Bhu-Naksha
(bhunakshaserver API) and accumulate a combined GeoJSON for the map.

FREE: runs from a GitHub Actions US runner (no geo-fence, no captcha on these
endpoints). RESUMABLE: each run reads the existing file, skips villages already
done, fetches the next batch, dedupes, and writes back — so a schedule fills in a
whole tehsil over time without ever hammering the server.

Recipe (confirmed via Playwright capture):
  POST masterdata/levelvalue        level/codes            -> district/tehsil/village lists
  POST MapInfo/getVVVVExtentGeoref  gisLevels=D,T,V        -> extent + crs + gisCode
  POST MapInfo/getPlotAtXY          giscode&x&y&plotno     -> plot bbox + id + kide(plotNo)
  POST MapInfo/getPlotInfo          {gisCode,plotNo}       -> khata + area(ha) + owners

Privacy: owner names are personal data; full lists emitted only if INCLUDE_OWNERS=1.
"""
import os
import re
import sys
import json
import math
import time
import requests
from pyproj import Transformer

BASE = "https://upbhunaksha.gov.in/bhunakshaserver"
HOME = "https://upbhunaksha.gov.in/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

DISTRICT_MATCH = os.environ.get("DISTRICT", "गौतम")
TEHSIL_MATCH = os.environ.get("TEHSIL", "जेवर")
MAX_VILLAGES = int(os.environ.get("MAX_VILLAGES", "15"))
STEP = float(os.environ.get("STEP", "30"))
PER_VILLAGE_MAX_PLOTS = int(os.environ.get("PER_VILLAGE_MAX_PLOTS", "500"))
MAX_TOTAL_PLOTS = int(os.environ.get("MAX_TOTAL_PLOTS", "100000"))
TIME_BUDGET = float(os.environ.get("TIME_BUDGET", "1500"))
SLEEP = float(os.environ.get("SLEEP", "0.06"))
APPEND = os.environ.get("APPEND", "1") == "1"
INCLUDE_OWNERS = os.environ.get("INCLUDE_OWNERS", "0") == "1"
OUT = os.environ.get("OUT", "web/data/gbn_parcels.geojson")

s = requests.Session()
s.headers.update({
    "User-Agent": UA, "Referer": HOME, "Origin": "https://upbhunaksha.gov.in",
    "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/plain, */*",
})
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
T0 = None


def budget_left():
    return (time.time() - T0) < TIME_BUDGET


def level(n, codes=""):
    r = s.post(f"{BASE}/masterdata/levelvalue", data={"level": n, "codes": codes},
               headers=FORM, timeout=30)
    r.raise_for_status()
    return r.json()


def find(items, needle):
    return next((it for it in items if needle in (it.get("value") or "")), None)


def haversine(a, b):
    R, t = 6371.0, math.pi / 180
    dlat, dlon = (b[0] - a[0]) * t, (b[1] - a[1]) * t
    h = math.sin(dlat / 2) ** 2 + math.cos(a[0] * t) * math.cos(b[0] * t) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def village_centroid(dc, tc, v):
    """Cheap centroid (lat, lng) of a village from its georeferenced extent — used to sort
    villages by distance to a catalyst. None on failure."""
    try:
        ext = s.post(f"{BASE}/MapInfo/getVVVVExtentGeoref",
                     data={"gisLevels": f"{dc},{tc},{v['code']}"}, headers=FORM, timeout=30).json()
        tr = Transformer.from_crs(ext.get("crs", "EPSG:32644"), "EPSG:4326", always_xy=True)
        lng, lat = tr.transform((ext["xmin"] + ext["xmax"]) / 2, (ext["ymin"] + ext["ymax"]) / 2)
        return [round(lat, 5), round(lng, 5)]
    except Exception:
        return None


def plot_info(gis_code, plotno):
    khata, area_ha, owners = None, None, []
    try:
        txt = s.post(f"{BASE}/MapInfo/getPlotInfo", json={"gisCode": gis_code, "plotNo": plotno},
                     headers={"Content-Type": "application/json"}, timeout=20).text
        m = re.search(r"Khata No:\s*(\S+)", txt)
        khata = m.group(1) if m else None
        m = re.search(r"Area\s*:\s*([\d.]+)", txt)
        area_ha = float(m.group(1)) if m else None
        owners = [o.strip() for o in re.findall(r"नाम\s*:\s*(.+?)\s*संरक्षक", txt)][:15]
    except Exception:
        time.sleep(0.4)
    return khata, area_ha, owners


def rect(b):
    return [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3]), (b[0], b[1])]


def fetch_village(dc, tc, v):
    try:
        ext = s.post(f"{BASE}/MapInfo/getVVVVExtentGeoref",
                     data={"gisLevels": f"{dc},{tc},{v['code']}"}, headers=FORM, timeout=30).json()
    except Exception:
        return []
    gis_code, crs = ext["gisCode"], ext.get("crs", "EPSG:32644")
    xmin, ymin, xmax, ymax = ext["xmin"], ext["ymin"], ext["xmax"], ext["ymax"]
    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    seen, covered, feats = set(), [], []
    y = ymin + STEP / 2
    while y < ymax and budget_left() and len(seen) < PER_VILLAGE_MAX_PLOTS:
        x = xmin + STEP / 2
        while x < xmax and budget_left() and len(seen) < PER_VILLAGE_MAX_PLOTS:
            if not any(a <= x <= c and b <= y <= d for (a, b, c, d) in covered):
                try:
                    j = s.post(f"{BASE}/MapInfo/getPlotAtXY",
                               data={"giscode": gis_code, "x": x, "y": y, "plotno": "undefined"},
                               headers=FORM, timeout=20).json()
                    pid = j.get("id")
                    if pid and pid not in seen and j.get("kide"):
                        bb = (j["minx"], j["miny"], j["maxx"], j["maxy"])
                        seen.add(pid)
                        covered.append(bb)
                        khata, area_ha, owners = plot_info(gis_code, j["kide"])
                        time.sleep(SLEEP)
                        props = {"plot_no": j["kide"], "khata_no": khata, "area_ha": area_ha,
                                 "owner_count": len(owners), "village": v["value"],
                                 "gis_code": gis_code, "source": "UP Bhu-Naksha"}
                        if INCLUDE_OWNERS:
                            props["owners"] = owners
                        feats.append({"type": "Feature", "properties": props,
                                      "geometry": {"type": "Polygon",
                                                   "coordinates": [[list(tr.transform(px, py)) for px, py in rect(bb)]]}})
                except Exception:
                    time.sleep(0.4)
                time.sleep(SLEEP)
            x += STEP
        y += STEP
    return feats


def main():
    global T0
    s.get(HOME, timeout=30)
    d = find(level(1, ""), DISTRICT_MATCH)
    if not d:
        sys.exit(f"district {DISTRICT_MATCH!r} not found")
    t = find(level(2, d["code"]), TEHSIL_MATCH)
    if not t:
        sys.exit(f"tehsil {TEHSIL_MATCH!r} not found")
    villages = level(3, f'{d["code"]},{t["code"]}')

    # resume: read what's already been fetched
    existing, done_codes, village_xy = [], set(), {}
    if APPEND and os.path.exists(OUT):
        try:
            cur = json.load(open(OUT, encoding="utf-8"))
            existing = cur.get("features", [])
            done_codes = set(cur.get("meta", {}).get("done_codes", []))
            village_xy = cur.get("meta", {}).get("village_xy", {})
        except Exception:
            pass

    remaining = [v for v in villages if v["code"] not in done_codes]

    # opt-in: fetch villages nearest a catalyst first (TARGET_LATLNG="lat,lng") instead of
    # alphabetically — so coverage grows outward from the hot zone. Centroids are cached in
    # meta to stay cheap; any failure falls back to the original order (no regression).
    target = os.environ.get("TARGET_LATLNG")
    if target:
        try:
            tlat, tlng = (float(x) for x in target.split(","))
            T0 = time.time()
            for v in remaining:
                if v["code"] not in village_xy and budget_left():
                    c = village_centroid(d["code"], t["code"], v)
                    if c:
                        village_xy[v["code"]] = c
                    time.sleep(SLEEP)
            remaining.sort(key=lambda v: haversine(village_xy[v["code"]], (tlat, tlng))
                           if v["code"] in village_xy else 1e9)
            print(f"prioritized villages by distance to {tlat},{tlng}")
        except Exception as e:
            print("prioritization skipped:", e)

    batch = remaining[:MAX_VILLAGES]
    print(f"{d['value']}/{t['value']}: {len(villages)} villages, "
          f"{len(done_codes)} done, {len(remaining)} remaining, fetching {len(batch)} now")

    T0 = time.time()
    new_feats = []
    for v in batch:
        if not budget_left() or len(existing) + len(new_feats) >= MAX_TOTAL_PLOTS:
            break
        feats = fetch_village(d["code"], t["code"], v)
        new_feats.extend(feats)
        if budget_left():                 # village finished within budget -> mark done
            done_codes.add(v["code"])
            print(f"  {v['value']}: +{len(feats)} (total {len(existing) + len(new_feats)}, {int(time.time() - T0)}s)")
        else:
            print(f"  {v['value']}: partial (budget) — will resume next run")
            break

    # merge + dedupe by (gis_code, plot_no)
    merged = {}
    for ft in existing + new_feats:
        merged[(ft["properties"]["gis_code"], ft["properties"]["plot_no"])] = ft
    all_feats = list(merged.values())

    fc = {"type": "FeatureCollection",
          "meta": {"district": d["value"], "tehsil": t["value"],
                   "done_codes": sorted(done_codes), "village_xy": village_xy,
                   "villages_done": len(done_codes), "villages_total": len(villages),
                   "plot_count": len(all_feats), "owners_included": INCLUDE_OWNERS,
                   "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())},
          "features": all_feats}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    print(f"WROTE {len(all_feats)} parcels | {len(done_codes)}/{len(villages)} villages done -> {OUT}")


if __name__ == "__main__":
    main()
