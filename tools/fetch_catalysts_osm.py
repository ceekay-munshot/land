#!/usr/bin/env python3
"""Fetch REAL expressway/major-road geometry near Jewar from OpenStreetMap (Overpass),
free via a GitHub Actions runner. The new Noida Int'l Airport isn't reliably tagged in
OSM yet, so its (well-known, public) location is set directly. Emits road lines + an
airport point, and records the airport centroid for client-side distance scoring.
"""
import json
import os
import urllib.request
import urllib.parse

BBOX = "27.95,77.30,28.70,77.95"                 # Jewar / southern Gautam Buddh Nagar
AIRPORT = [77.5806, 28.1561]                     # Noida International Airport (Jewar)
OUT = "web/data/catalysts_osm.geojson"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
QUERY = f"""[out:json][timeout:120];
(
  way["highway"="motorway"]({BBOX});
  way["highway"="trunk"]({BBOX});
);
out geom;"""


def fetch_overpass():
    for url in OVERPASS_URLS:
        try:
            data = urllib.parse.urlencode({"data": QUERY}).encode()
            req = urllib.request.Request(url, data=data,
                                         headers={"User-Agent": "land-catalysts/1.0 (research)"})
            els = json.load(urllib.request.urlopen(req, timeout=180)).get("elements", [])
            if els:
                return els, url
            print("overpass returned 0 elements from", url)
        except Exception as e:
            print("overpass error", url, e)
    return [], None


def main():
    els, used = fetch_overpass()
    feats = []
    for el in els:
        if el.get("type") == "way" and el.get("geometry"):
            coords = [[g["lon"], g["lat"]] for g in el["geometry"]]
            if len(coords) >= 2:
                t = el.get("tags", {})
                feats.append({"type": "Feature",
                              "properties": {"kind": "road", "highway": t.get("highway"), "name": t.get("name")},
                              "geometry": {"type": "LineString", "coordinates": coords}})
    road_count = len(feats)
    feats.append({"type": "Feature",
                  "properties": {"kind": "airport", "name": "Noida International Airport (Jewar)",
                                 "status": "Phase-1 ~2026"},
                  "geometry": {"type": "Point", "coordinates": AIRPORT}})

    fc = {"type": "FeatureCollection",
          "meta": {"source": "OpenStreetMap (Overpass) © OSM contributors", "mirror": used,
                   "raw_elements": len(els), "road_count": road_count, "airport_centroid": AIRPORT},
          "features": feats}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    names = sorted({x["properties"].get("name") for x in feats if x["properties"].get("name")})
    print(f"raw={len(els)} roads={road_count} mirror={used}")
    print("named roads:", ", ".join(n for n in names if n)[:400])


if __name__ == "__main__":
    main()
