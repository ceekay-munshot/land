#!/usr/bin/env python3
"""Find how UP Bhu-Naksha serves the REAL plot polygon (not just the bbox we use now).

Step 1 (cheapest): dump the FULL getPlotAtXY response for a Nalgadha plot — maybe the real
geometry is already in there and we're only reading minx/miny/maxx/maxy. Also try a handful
of likely vector endpoints. Writes _probe/bhunaksha_geom.json. Free US runner.
"""
import os
import json
import requests

BASE = "https://upbhunaksha.gov.in/bhunakshaserver"
HOME = "https://upbhunaksha.gov.in/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": HOME, "Origin": "https://upbhunaksha.gov.in",
                  "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/plain, */*"})
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def level(n, codes=""):
    return s.post(f"{BASE}/masterdata/levelvalue", data={"level": n, "codes": codes},
                  headers=FORM, timeout=40).json()


def find(items, n):
    return next((it for it in items if n in (it.get("value") or "")), None)


s.get(HOME, timeout=40)
d = find(level(1, ""), "गौतम")
t = find(level(2, d["code"]), "गौतमबुद्धनगर")
v = next(x for x in level(3, f'{d["code"]},{t["code"]}') if x["code"] == "120241")
ext = s.post(f"{BASE}/MapInfo/getVVVVExtentGeoref",
             data={"gisLevels": f'{d["code"]},{t["code"]},{v["code"]}'}, headers=FORM, timeout=40).json()
gis = ext["gisCode"]
cx, cy = (ext["xmin"] + ext["xmax"]) / 2, (ext["ymin"] + ext["ymax"]) / 2

out = {"extent": ext, "gisCode": gis}

# 1) FULL getPlotAtXY response — does it already carry the real polygon?
j = s.post(f"{BASE}/MapInfo/getPlotAtXY",
           data={"giscode": gis, "x": cx, "y": cy, "plotno": "undefined"}, headers=FORM, timeout=30).json()
out["getPlotAtXY_full"] = j
kide = j.get("kide")

# 2) FULL getPlotInfo text
if kide:
    out["getPlotInfo_head"] = s.post(f"{BASE}/MapInfo/getPlotInfo", json={"gisCode": gis, "plotNo": kide},
                                     headers={"Content-Type": "application/json"}, timeout=30).text[:1000]

# 3) try likely vector / map endpoints
out["probes"] = []
candidates = [
    ("MapInfo/getPlotKML", {"gisCode": gis, "plotNo": kide}),
    ("MapInfo/getPlotByGisCode", {"gisCode": gis, "plotNo": kide}),
    ("MapInfo/getmap", {"gisCode": gis}),
    ("MapInfo/getMapSvg", {"gisCode": gis}),
    ("MapInfo/getVVPlots", {"gisCode": gis}),
    ("rest/MapInfo/getPlotsByGisCode", {"gisCode": gis}),
]
for path, payload in candidates:
    try:
        r = s.post(f"{BASE}/{path}", data=payload, headers=FORM, timeout=30)
        out["probes"].append({"path": path, "status": r.status_code,
                              "ct": r.headers.get("content-type"), "len": len(r.content),
                              "head": r.text[:300]})
    except Exception as e:
        out["probes"].append({"path": path, "error": str(e)[:150]})

os.makedirs("_probe", exist_ok=True)
json.dump(out, open("_probe/bhunaksha_geom.json", "w"), ensure_ascii=False, indent=2, default=str)
print("getPlotAtXY keys:", list(j.keys()))
print("probes:", [(p.get("path"), p.get("status"), p.get("ct"), p.get("len"), p.get("error")) for p in out["probes"]])
