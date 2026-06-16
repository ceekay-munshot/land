#!/usr/bin/env python3
"""Find Bhu-Naksha's REAL plot-geometry endpoint.

Confirmed: getPlotAtXY returns only a bbox (minx/miny/maxx/maxy + bhucode), and guessed
endpoints 500'd. So read the web app's own JS bundles and extract the API calls it uses to
draw plot polygons (SVG/KML/GeoJSON/WFS). Writes _probe/bhunaksha_geom.json.
"""
import os
import re
import json
import time
import requests

HOME = "https://upbhunaksha.gov.in/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": HOME})

PAT = re.compile(
    r"(MapInfo/[A-Za-z0-9_]+|getmapsvg|getMapSvg|getmap[A-Za-z]*|getPlot[A-Za-z]*|"
    r"getVVVV[A-Za-z]*|/rest/[A-Za-z0-9/_]+|geoserver[\w/]*|GetFeature[A-Za-z]*|"
    r"plotmap[A-Za-z]*|getKml[A-Za-z]*|\.kml|geojson|getsvg|plotsvg|svgmap)", re.I)


def get(url, **kw):
    for i in range(4):
        try:
            return s.get(url, timeout=60, **kw)
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


out = {"note": "getPlotAtXY = bbox only (minx/miny/maxx/maxy + bhucode). Hunting real geometry call in JS.",
       "js": []}
try:
    html = get(HOME).text
    jsfiles = set(re.findall(r'src=["\']([^"\']+\.js)["\']', html))
    jsfiles |= set(re.findall(r'["\']([\w./-]*(?:main|runtime|polyfills|scripts|chunk|vendor)[\w./-]*\.js)["\']', html))
    out["js_found"] = sorted(jsfiles)
    for j in sorted(jsfiles):
        url = j if j.startswith("http") else HOME.rstrip("/") + "/" + j.lstrip("/")
        r = get(url)
        if not r or r.status_code != 200:
            out["js"].append({"url": url, "status": getattr(r, "status_code", None)})
            continue
        found = sorted(set(m.group(0) for m in PAT.finditer(r.text)))
        out["js"].append({"url": url, "len": len(r.text), "matches": found})
except Exception as e:
    out["fatal_error"] = repr(e)[:300]

os.makedirs("_probe", exist_ok=True)
json.dump(out, open("_probe/bhunaksha_geom.json", "w"), ensure_ascii=False, indent=2, default=str)
print("js found:", out.get("js_found"))
for f in out["js"]:
    if f.get("matches"):
        print(f["url"].split("/")[-1], "->", f["matches"])
print("fatal_error:", out.get("fatal_error"))
