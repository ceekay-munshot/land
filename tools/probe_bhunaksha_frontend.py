#!/usr/bin/env python3
"""Deep static extraction of UP Bhu-Naksha's Angular bundles to find the REAL
plot-geometry endpoint and the GetMap LAYERS/layercodes that actually render
boundaries.

Why: the SPA uses OpenLayers readFeatures (client-side vector), so plot geometry
arrives as GeoJSON/WKT from some endpoint. But the bundles don't hardcode the
'bhunakshaserver/' prefix (URLs are config-injected), so a naive grep finds no
endpoints. Here we instead pull every string-literal API-ish path and grab
context windows around the key calls (readFeatures, getMap, LAYERS, layercodes,
gisCode, getPlot*) — minified code keeps string literals intact, so the endpoint
paths and WMS params are readable.

Writes _probe/bhunaksha_frontend.json. Needs egress to upbhunaksha.gov.in (CI).
"""
import os
import re
import json
import time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://upbhunaksha.gov.in"
OUT = os.path.join(ROOT, "_probe", "bhunaksha_frontend.json")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
# fallback bundle list (hashes rotate; we re-read them from the homepage first)
FALLBACK = ["/main-76RVRF3Z.js", "/chunk-SFFPZX3Y.js", "/chunk-UFEAADAO.js",
            "/polyfills-RM666RQK.js", "/scripts-BZQBXHEN.js"]

# tokens whose surrounding code reveals the geometry endpoint / WMS construction
KEYS = ["readFeatures", "GeoJSON", "readGeometry", "WKT", "format:",
        "getMap", "GetMap", "REQUEST=GetMap", "LAYERS", "layercodes", "layerCodes",
        "getVVVV", "gis_code", "giscode", "gisCode", "gisLevels",
        "ImageWMS", "TileWMS", "geoserver", "TRANSPARENT", "VectorSource",
        "getPlotData", "getMapData", "getPlotReport", "getPlotInfo", "getPlotAtXY",
        "MapInfo/", "masterdata/", "serverUrl", "baseUrl", "apiUrl", "bhunakshaserver"]
PATH_RE = re.compile(r'''["'`]([A-Za-z][A-Za-z0-9]*/[A-Za-z0-9_/]{2,})["'`]''')
URL_RE = re.compile(r'https?://[A-Za-z0-9_./:%-]+')
ASSET_SUFFIX = (".js", ".css", ".svg", ".png", ".jpg", ".gif", ".woff", ".woff2",
                ".ttf", ".ico", ".map", ".json")


def main():
    out = {"base": BASE, "errors": [], "bundles": []}
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": BASE + "/"})

    def get(u):
        last = None
        for i in range(5):
            try:
                return s.get(u, timeout=50)
            except Exception as e:
                last = e
                time.sleep(2 * (i + 1))
        out["errors"].append("GET %s failed: %r" % (u, last))
        return None

    home = get(BASE + "/")
    out["home_status"] = getattr(home, "status_code", None)
    srcs = []
    if home is not None and home.status_code == 200:
        srcs = re.findall(r'<script[^>]+src=["\']([^"\']+\.js)["\']', home.text, re.I)
    srcs = sorted(set(srcs)) or FALLBACK
    out["scripts_on_page"] = srcs

    blob = ""
    for src in srcs:
        u = src if src.startswith("http") else BASE + "/" + src.lstrip("/")
        r = get(u)
        ok = r is not None and r.status_code == 200
        out["bundles"].append({"url": u, "status": getattr(r, "status_code", None),
                               "len": len(r.text) if ok else 0})
        if ok:
            blob += "\n/*%s*/\n" % src + r.text
    out["blob_chars"] = len(blob)

    paths = sorted(set(PATH_RE.findall(blob)))
    out["string_paths"] = [p for p in paths if not p.lower().endswith(ASSET_SUFFIX)][:250]
    out["urls"] = sorted(set(u for u in URL_RE.findall(blob)
                             if not u.lower().endswith(ASSET_SUFFIX)))[:80]

    ctx = {}
    for k in KEYS:
        hits = []
        start = 0
        while len(hits) < 8:
            i = blob.find(k, start)
            if i < 0:
                break
            seg = re.sub(r"\s+", " ", blob[max(0, i - 170): i + 210]).strip()
            if seg not in hits:
                hits.append(seg)
            start = i + len(k)
        if hits:
            ctx[k] = hits
    out["context"] = ctx
    _write(out)


def _write(out):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("wrote", OUT, "blob_chars", out.get("blob_chars"),
          "paths", len(out.get("string_paths", [])))


if __name__ == "__main__":
    main()
