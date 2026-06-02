#!/usr/bin/env python3
"""Fetch REAL catalyst geometry near Jewar from OpenStreetMap (Overpass) — the
Noida International Airport plus expressways/major roads. Free via a GitHub Actions
runner (Overpass is reachable). Emits road lines + a single airport point (centroid),
and records the airport centroid in meta for client-side distance scoring.
"""
import json
import os
import urllib.request
import urllib.parse

OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = "27.95,77.30,28.70,77.95"          # Jewar / southern Gautam Buddh Nagar (S,W,N,E)
FALLBACK_AIRPORT = [77.5806, 28.1561]     # approx Noida Int'l Airport if OSM lacks it
OUT = "web/data/catalysts_osm.geojson"

QUERY = f"""
[out:json][timeout:120];
(
  nwr["aeroway"="aerodrome"]({BBOX});
  way["highway"="motorway"]({BBOX});
  way["highway"="trunk"]({BBOX});
);
out geom center;
"""


def centroid(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [sum(xs) / len(xs), sum(ys) / len(ys)]


def main():
    feats = []
    airport_pts = []
    try:
        data = urllib.parse.urlencode({"data": QUERY}).encode()
        req = urllib.request.Request(OVERPASS, data=data,
                                     headers={"User-Agent": "land-catalysts/1.0 (research)"})
        res = json.load(urllib.request.urlopen(req, timeout=180))
        for el in res.get("elements", []):
            tags = el.get("tags", {})
            if tags.get("aeroway") == "aerodrome":
                if el.get("geometry"):
                    airport_pts += [[g["lon"], g["lat"]] for g in el["geometry"]]
                elif el.get("center"):
                    airport_pts.append([el["center"]["lon"], el["center"]["lat"]])
                elif el.get("lat"):
                    airport_pts.append([el["lon"], el["lat"]])
                continue
            hwy = tags.get("highway")
            if hwy and el.get("geometry"):
                coords = [[g["lon"], g["lat"]] for g in el["geometry"]]
                if len(coords) >= 2:
                    feats.append({"type": "Feature",
                                  "properties": {"kind": "road", "highway": hwy, "name": tags.get("name")},
                                  "geometry": {"type": "LineString", "coordinates": coords}})
    except Exception as e:
        print("Overpass failed, using fallback airport only:", e)

    airport = centroid(airport_pts) if airport_pts else FALLBACK_AIRPORT
    feats.append({"type": "Feature",
                  "properties": {"kind": "airport", "name": "Noida International Airport (Jewar)",
                                 "status": "Phase-1 ~2026"},
                  "geometry": {"type": "Point", "coordinates": airport}})

    fc = {"type": "FeatureCollection",
          "meta": {"source": "OpenStreetMap (Overpass) © OSM contributors",
                   "airport_centroid": airport, "feature_count": len(feats)},
          "features": feats}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    roads = sum(1 for x in feats if x["properties"]["kind"] == "road")
    print(f"wrote {roads} roads + airport {airport} -> {OUT}")


if __name__ == "__main__":
    main()
