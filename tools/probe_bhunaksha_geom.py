#!/usr/bin/env python3
"""Find how UP Bhu-Naksha serves the REAL plot polygon (not just the bbox we use now).

Step 1 (cheapest): dump the FULL getPlotAtXY response for a Nalgadha plot — maybe the real
geometry is already there and we only read minx/miny/maxx/maxy. Also try likely vector
endpoints. Resilient: retries transient drops, always writes _probe/bhunaksha_geom.json.
"""
import os
import json
import time
import requests

BASE = "https://upbhunaksha.gov.in/bhunakshaserver"
HOME = "https://upbhunaksha.gov.in/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": HOME, "Origin": "https://upbhunaksha.gov.in",
                  "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/plain, */*"})
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def post(path, retries=5, **kw):
    last = None
    for i in range(retries):
        try:
            return s.post(f"{BASE}/{path}", timeout=40, **kw)
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def level(n, codes=""):
    return post("masterdata/levelvalue", data={"level": n, "codes": codes}, headers=FORM).json()


def find(items, n):
    return next((it for it in items if n in (it.get("value") or "")), None)


out = {}
try:
    s.get(HOME, timeout=40)
    d = find(level(1, ""), "गौतम")
    t = find(level(2, d["code"]), "गौतमबुद्धनगर")
    v = next(x for x in level(3, f'{d["code"]},{t["code"]}') if x["code"] == "120241")
    ext = post("MapInfo/getVVVVExtentGeoref",
               data={"gisLevels": f'{d["code"]},{t["code"]},{v["code"]}'}, headers=FORM).json()
    out["extent"] = ext
    gis = ext["gisCode"]
    cx, cy = (ext["xmin"] + ext["xmax"]) / 2, (ext["ymin"] + ext["ymax"]) / 2

    j = post("MapInfo/getPlotAtXY",
             data={"giscode": gis, "x": cx, "y": cy, "plotno": "undefined"}, headers=FORM).json()
    out["getPlotAtXY_full"] = j
    kide = j.get("kide")

    if kide:
        out["getPlotInfo_head"] = post("MapInfo/getPlotInfo", json={"gisCode": gis, "plotNo": kide},
                                       headers={"Content-Type": "application/json"}).text[:1000]

    out["probes"] = []
    for path, payload in [
        ("MapInfo/getPlotKML", {"gisCode": gis, "plotNo": kide}),
        ("MapInfo/getPlotByGisCode", {"gisCode": gis, "plotNo": kide}),
        ("MapInfo/getmap", {"gisCode": gis}),
        ("MapInfo/getMapSvg", {"gisCode": gis}),
        ("MapInfo/getVVPlots", {"gisCode": gis}),
        ("rest/MapInfo/getPlotsByGisCode", {"gisCode": gis}),
    ]:
        try:
            r = post(path, retries=2, data=payload, headers=FORM)
            out["probes"].append({"path": path, "status": r.status_code,
                                  "ct": r.headers.get("content-type"), "len": len(r.content),
                                  "head": r.text[:300]})
        except Exception as e:
            out["probes"].append({"path": path, "error": str(e)[:150]})
except Exception as e:
    out["fatal_error"] = repr(e)[:300]

os.makedirs("_probe", exist_ok=True)
json.dump(out, open("_probe/bhunaksha_geom.json", "w"), ensure_ascii=False, indent=2, default=str)
print("getPlotAtXY keys:", list(out.get("getPlotAtXY_full", {}).keys()))
print("probes:", [(p.get("path"), p.get("status"), p.get("ct"), p.get("len"), p.get("error")) for p in out.get("probes", [])])
print("fatal_error:", out.get("fatal_error"))
