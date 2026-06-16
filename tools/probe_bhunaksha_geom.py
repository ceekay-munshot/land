#!/usr/bin/env python3
"""Last realistic try for REAL parcel geometry from UP Bhu-Naksha's GeoServer:
  - full getVVVVExtentGeoref (look for layercodes/layer ids)
  - WMS GetFeatureInfo as application/json (OGC standard -> returns feature WITH geometry)
  - WFS GetFeature as json (long shot)
Both plot JSON endpoints already proven bbox-only. Writes _probe/bhunaksha_geom.json.
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
                  "Accept": "application/json, text/plain, */*"})
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


def get(url, retries=4, **kw):
    last = None
    for i in range(retries):
        try:
            return s.get(url, timeout=40, **kw)
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
    out["extent_full"] = ext
    gis = ext["gisCode"]
    crs = ext.get("crs", "EPSG:32644")
    cx, cy = (ext["xmin"] + ext["xmax"]) / 2, (ext["ymin"] + ext["ymax"]) / 2
    j = post("MapInfo/getPlotAtXY",
             data={"giscode": gis, "x": cx, "y": cy, "plotno": "undefined"}, headers=FORM).json()
    px, py = (j["minx"] + j["maxx"]) / 2, (j["miny"] + j["maxy"]) / 2
    h = 60
    bbox = f"{px - h},{py - h},{px + h},{py + h}"

    out["tries"] = []
    attempts = [
        ("GetFeatureInfo v1.1.1", f"{BASE}/WMS", {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetFeatureInfo",
            "LAYERS": "DERIVED_LAYER", "QUERY_LAYERS": "DERIVED_LAYER",
            "INFO_FORMAT": "application/json", "SRS": crs, "BBOX": bbox,
            "WIDTH": "101", "HEIGHT": "101", "X": "50", "Y": "50",
            "FEATURE_COUNT": "10", "gis_code": gis, "state": "", "layercodes": ""}),
        ("GetFeatureInfo v1.3.0", f"{BASE}/WMS", {
            "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo",
            "LAYERS": "DERIVED_LAYER", "QUERY_LAYERS": "DERIVED_LAYER",
            "INFO_FORMAT": "application/json", "CRS": crs, "BBOX": bbox,
            "WIDTH": "101", "HEIGHT": "101", "I": "50", "J": "50",
            "FEATURE_COUNT": "10", "gis_code": gis, "state": "", "layercodes": ""}),
        ("WFS GetFeature /WMS", f"{BASE}/WMS", {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": "DERIVED_LAYER", "outputFormat": "application/json",
            "count": "5", "gis_code": gis}),
        ("WFS GetFeature /wfs", f"{BASE}/wfs", {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": "DERIVED_LAYER", "outputFormat": "application/json",
            "count": "5", "gis_code": gis}),
    ]
    for name, url, params in attempts:
        try:
            r = get(url, params=params)
            out["tries"].append({"name": name, "status": r.status_code,
                                 "ct": r.headers.get("content-type"), "len": len(r.content),
                                 "has_geometry": ("coordinates" in r.text or "geometry" in r.text.lower()),
                                 "body": r.text[:1200]})
        except Exception as e:
            out["tries"].append({"name": name, "error": str(e)[:150]})
except Exception as e:
    out["fatal_error"] = repr(e)[:300]

os.makedirs("_probe", exist_ok=True)
json.dump(out, open("_probe/bhunaksha_geom.json", "w"), ensure_ascii=False, indent=2, default=str)
print("extent keys:", list(out.get("extent_full", {}).keys()))
for tr in out.get("tries", []):
    print(tr.get("name"), "|", tr.get("status"), tr.get("ct"), tr.get("len"),
          "| geometry?", tr.get("has_geometry"), "| err:", tr.get("error", ""))
print("fatal_error:", out.get("fatal_error"))
