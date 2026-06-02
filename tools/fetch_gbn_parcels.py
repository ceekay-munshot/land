#!/usr/bin/env python3
"""Fetch real cadastral parcels for a Gautam Buddh Nagar village from UP Bhu-Naksha
(bhunakshaserver API) and emit GeoJSON for the map.

FREE: designed to run from a GitHub Actions US runner — these endpoints are not
geo-fenced and need no captcha. Recipe confirmed via Playwright network capture:

  POST masterdata/levelvalue      level=1&codes=             -> districts
                                  level=2&codes=<D>          -> tehsils
                                  level=3&codes=<D>,<T>      -> villages
  POST MapInfo/getVVVVExtentGeoref  gisLevels=<D>,<T>,<V>    -> extent + crs + gisCode
  POST MapInfo/getPlotAtXY        giscode&x&y&plotno         -> plot bbox + id + kide(plotNo)
  POST MapInfo/getPlotInfo        {gisCode, plotNo}          -> Khata + Area(ha) + owners

Privacy: owner names are personal data and this repo may be public, so full owner
lists are emitted only when INCLUDE_OWNERS=1; otherwise just owner_count.
"""
import os
import re
import sys
import json
import time
import requests
from pyproj import Transformer

BASE = "https://upbhunaksha.gov.in/bhunakshaserver"
HOME = "https://upbhunaksha.gov.in/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

DISTRICT_MATCH = os.environ.get("DISTRICT", "गौतम")    # Gautam (Buddh Nagar)
TEHSIL_MATCH = os.environ.get("TEHSIL", "जेवर")         # Jewar
VILLAGE_INDEX = int(os.environ.get("VILLAGE_INDEX", "0"))
STEP = float(os.environ.get("STEP", "45"))              # grid spacing, metres
MAX_POINTS = int(os.environ.get("MAX_POINTS", "1200"))
MAX_PLOTS = int(os.environ.get("MAX_PLOTS", "250"))
INCLUDE_OWNERS = os.environ.get("INCLUDE_OWNERS", "0") == "1"
OUT = os.environ.get("OUT", "web/data/gbn_parcels.geojson")

s = requests.Session()
s.headers.update({
    "User-Agent": UA,
    "Referer": HOME,
    "Origin": "https://upbhunaksha.gov.in",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
})
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def level(n, codes=""):
    r = s.post(f"{BASE}/masterdata/levelvalue", data={"level": n, "codes": codes},
               headers=FORM, timeout=30)
    r.raise_for_status()
    return r.json()


def find(items, needle):
    return next((it for it in items if needle in (it.get("value") or "")), None)


def main():
    s.get(HOME, timeout=30)  # establish session cookies

    d = find(level(1, ""), DISTRICT_MATCH)
    if not d:
        sys.exit(f"district matching {DISTRICT_MATCH!r} not found")
    print("district:", d["code"], d["value"])

    t = find(level(2, d["code"]), TEHSIL_MATCH)
    if not t:
        sys.exit(f"tehsil matching {TEHSIL_MATCH!r} not found")
    print("tehsil:", t["code"], t["value"])

    villages = level(3, f'{d["code"]},{t["code"]}')
    print(f"{len(villages)} villages in {t['value']}")
    v = villages[min(VILLAGE_INDEX, len(villages) - 1)]
    print("village:", v["code"], v["value"])

    ext = s.post(f"{BASE}/MapInfo/getVVVVExtentGeoref",
                 data={"gisLevels": f'{d["code"]},{t["code"]},{v["code"]}'},
                 headers=FORM, timeout=30).json()
    gis_code = ext["gisCode"]
    crs = ext.get("crs", "EPSG:32644")
    xmin, ymin, xmax, ymax = ext["xmin"], ext["ymin"], ext["xmax"], ext["ymax"]
    print(f"gisCode={gis_code} crs={crs} "
          f"extent=({xmin:.0f},{ymin:.0f})-({xmax:.0f},{ymax:.0f})")

    # grid-sample getPlotAtXY to enumerate plots
    plots = {}
    pts = 0
    y = ymin + STEP / 2
    while y < ymax and pts < MAX_POINTS and len(plots) < MAX_PLOTS:
        x = xmin + STEP / 2
        while x < xmax and pts < MAX_POINTS and len(plots) < MAX_PLOTS:
            pts += 1
            try:
                j = s.post(f"{BASE}/MapInfo/getPlotAtXY",
                           data={"giscode": gis_code, "x": x, "y": y, "plotno": "undefined"},
                           headers=FORM, timeout=20).json()
                pid = j.get("id")
                if pid and pid not in plots and j.get("kide"):
                    plots[pid] = {"plotNo": j["kide"], "minx": j["minx"], "miny": j["miny"],
                                  "maxx": j["maxx"], "maxy": j["maxy"]}
            except Exception:
                pass
            x += STEP
            time.sleep(0.03)
        y += STEP
    print(f"sampled {pts} points -> {len(plots)} unique plots")

    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    feats = []
    for pid, p in plots.items():
        khata, area_ha, owners = None, None, []
        try:
            txt = s.post(f"{BASE}/MapInfo/getPlotInfo",
                         json={"gisCode": gis_code, "plotNo": p["plotNo"]},
                         headers={"Content-Type": "application/json"}, timeout=20).text
            m = re.search(r"Khata No:\s*(\S+)", txt)
            khata = m.group(1) if m else None
            m = re.search(r"Area\s*:\s*([\d.]+)", txt)
            area_ha = float(m.group(1)) if m else None
            owners = [o.strip() for o in re.findall(r"नाम\s*:\s*(.+?)\s*संरक्षक", txt)][:15]
        except Exception:
            pass
        ring = [list(tr.transform(cx, cy)) for cx, cy in (
            (p["minx"], p["miny"]), (p["maxx"], p["miny"]),
            (p["maxx"], p["maxy"]), (p["minx"], p["maxy"]), (p["minx"], p["miny"]))]
        props = {"plot_no": p["plotNo"], "khata_no": khata, "area_ha": area_ha,
                 "owner_count": len(owners), "village": v["value"], "tehsil": t["value"],
                 "district": d["value"], "gis_code": gis_code,
                 "source": "UP Bhu-Naksha (bhunakshaserver)"}
        if INCLUDE_OWNERS:
            props["owners"] = owners
        feats.append({"type": "Feature",
                      "geometry": {"type": "Polygon", "coordinates": [ring]},
                      "properties": props})
        time.sleep(0.03)

    fc = {"type": "FeatureCollection",
          "meta": {"village": v["value"], "tehsil": t["value"], "district": d["value"],
                   "gis_code": gis_code, "crs_source": crs, "plot_count": len(feats),
                   "owners_included": INCLUDE_OWNERS},
          "features": feats}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    print(f"WROTE {len(feats)} parcels -> {OUT}")


if __name__ == "__main__":
    main()
