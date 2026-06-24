#!/usr/bin/env python3
"""Branch A: discover whether Bhu-Naksha exposes REAL plot VECTOR geometry, and
find the WMS LAYERS that renders plot boundaries (for the raster->vector fallback).

Static + cheap: fetch the SPA and its JS bundles, grep for how plots are drawn
(vector source vs ImageWMS) and every bhunakshaserver endpoint / layer name; then
probe the most promising candidates for one real Nalgadha plot. Always writes
_probe/bhunaksha_vector_recon.json so the vector-vs-raster decision is auditable.

Needs egress to upbhunaksha.gov.in (run in CI, or here once allowlisted).
Run: python3 tools/recon_bhunaksha_vector.py
"""
import os
import re
import json
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://upbhunaksha.gov.in"
SRV = BASE + "/bhunakshaserver"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
OUT = os.path.join(ROOT, "_probe", "bhunaksha_vector_recon.json")
GIS = "14100743120241"   # Nalgadha

VECTOR_HINTS = ["ol.source.Vector", "VectorSource", "ol.format.GeoJSON", "ol.format.WKT",
                "new GeoJSON(", "L.geoJSON", "readFeatures", "VectorLayer"]
RASTER_HINTS = ["ol.source.ImageWMS", "ImageWMS", "TileWMS", "ol.source.TileWMS",
                "ol.layer.Image", "L.tileLayer", "getMap"]
ENDPOINT_RE = re.compile(r"bhunakshaserver/([A-Za-z0-9_./]+)")
LAYER_RE = re.compile(r"[\"']([A-Za-z0-9_]*(?:LAYER|layer|plot|Plot|BOUNDARY|boundary)[A-Za-z0-9_]*)[\"']")
SVG_HINTS = ["image/svg", "<svg", "<path", "viewBox", "plotReport", "PlotReport", "नक्शा"]


def main():
    out = {"base": SRV, "gis": GIS, "errors": []}
    try:
        import requests
    except Exception as e:
        out["errors"].append("requests missing: %r" % e)
        _write(out); return
    requests.packages.urllib3.disable_warnings()
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": BASE})

    def get(u, **kw):
        for i in range(4):
            try:
                return s.get(u, timeout=40, verify=False, **kw)
            except Exception:
                time.sleep(2 * (i + 1))
        return None

    # 1) SPA + JS bundles
    home = get(BASE + "/")
    out["home_status"] = getattr(home, "status_code", None)
    srcs = []
    if home is not None:
        srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', home.text, re.I)
        srcs += re.findall(r'["\'](/?[A-Za-z0-9_./-]+\.js)["\']', home.text)
    srcs = sorted(set(srcs))[:40]
    out["scripts"] = srcs

    blob = ""
    fetched = []
    for src in srcs:
        u = src if src.startswith("http") else BASE + "/" + src.lstrip("/")
        r = get(u)
        if r is not None and r.status_code == 200 and "javascript" in r.headers.get("content-type", "") or (r and r.text and src.endswith(".js")):
            blob += "\n" + r.text
            fetched.append(u)
    out["bundles_fetched"] = fetched
    out["bundle_chars"] = len(blob)

    out["vector_hits"] = {h: blob.count(h) for h in VECTOR_HINTS if h in blob}
    out["raster_hits"] = {h: blob.count(h) for h in RASTER_HINTS if h in blob}
    out["svg_hits"] = {h: blob.count(h) for h in SVG_HINTS if h in blob}
    eps = sorted(set(ENDPOINT_RE.findall(blob)))
    out["endpoints"] = eps[:60]
    out["layer_tokens"] = sorted(set(LAYER_RE.findall(blob)))[:40]

    # 2) Probe a real plot: extent -> a plotno via getPlotAtXY center -> candidates
    def post(path, **kw):
        for i in range(3):
            try:
                return s.post(f"{SRV}/{path}", timeout=40, verify=False, **kw)
            except Exception:
                time.sleep(2 * (i + 1))
        return None

    probes = []
    ext = post("MapInfo/getVVVVExtentGeoref", data={"gisLevels": "141,00743,120241"})
    extent = None
    if ext is not None:
        try:
            extent = ext.json()
        except Exception:
            pass
    out["extent"] = extent
    plotno = None
    if extent:
        cx = (extent["xmin"] + extent["xmax"]) / 2
        cy = (extent["ymin"] + extent["ymax"]) / 2
        pj = post("MapInfo/getPlotAtXY", data={"giscode": GIS, "x": cx, "y": cy, "plotno": "undefined"})
        try:
            plotno = pj.json().get("kide")
        except Exception:
            pass
    out["probe_plotno"] = plotno

    # candidate VECTOR endpoints (per-plot geometry / SVG report)
    for path, payload in [
        ("MapInfo/getPlotReport", {"gisCode": GIS, "plotNo": plotno or "1"}),
        ("MapInfo/getMapData", {"gisCode": GIS, "plotNo": plotno or "1"}),
        ("rest/MapInfo/getPlotReport", {"gisCode": GIS, "plotNo": plotno or "1"}),
        ("MapInfo/printPlot", {"gisCode": GIS, "plotNo": plotno or "1"}),
    ]:
        r = post(path, data=payload)
        if r is None:
            continue
        body = r.text[:600] if "text" in r.headers.get("content-type", "") or "svg" in r.headers.get("content-type", "") else ""
        probes.append({"path": path, "status": r.status_code,
                       "ct": r.headers.get("content-type"), "len": len(r.content),
                       "has_svg_path": ("<path" in body) or ("svg" in r.headers.get("content-type", "")),
                       "has_coords": bool(re.search(r"POLYGON|coordinates|\d+\.\d+ \d+\.\d+", body)),
                       "snippet": body[:200]})

    # candidate boundary GetMap LAYERS (for raster->vector)
    layer_candidates = ["DERIVED_LAYER"] + [t for t in out["layer_tokens"] if "LAYER" in t.upper()][:6]
    getmap = []
    if extent:
        bbox = f'{extent["xmin"]},{extent["ymin"]},{extent["xmax"]},{extent["ymax"]}'
        for lyr in dict.fromkeys(layer_candidates):
            r = get(f"{SRV}/WMS", params={
                "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "LAYERS": lyr,
                "SRS": extent.get("crs", "EPSG:32644"), "BBOX": bbox, "WIDTH": 512, "HEIGHT": 256,
                "FORMAT": "image/png", "TRANSPARENT": "true", "gis_code": GIS, "state": "", "layercodes": ""})
            if r is None:
                continue
            getmap.append({"layers": lyr, "status": r.status_code,
                           "ct": r.headers.get("content-type"), "len": len(r.content),
                           "is_image": r.headers.get("content-type", "").startswith("image")})
    out["vector_probes"] = probes
    out["getmap_probes"] = getmap

    # decision
    vec = any(p["has_svg_path"] or p["has_coords"] for p in probes)
    img_layers = [g["layers"] for g in getmap if g["is_image"] and g["len"] > 800]
    out["decision"] = {
        "vector_endpoint_found": vec,
        "recommended_branch": "A (vector)" if vec else "B (raster->vector)",
        "recommended_getmap_layers": img_layers[:1] or layer_candidates[:1],
        "note": "vector hits vs raster hits in bundles: %d vs %d"
                % (sum(out["vector_hits"].values()), sum(out["raster_hits"].values())),
    }
    _write(out)


def _write(out):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("wrote", OUT)
    print("decision:", json.dumps(out.get("decision", {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
