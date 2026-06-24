#!/usr/bin/env python3
"""Add a `cidx` (colour index 0..5) property to a parcel GeoJSON so the map can
colour adjacent parcels differently (a proper cadastre look). Greedy Welsh-Powell
graph colouring over shared-edge adjacency. Idempotent; `plot_no`/`uid` untouched.

Adjacency is computed in metres (reproject WGS84 -> UTM 44N) so a ~0.5 m tracing
gap between neighbours still counts as adjacent.

Usage:  IN=web/data/nalgadha_parcels.geojson python3 tools/add_cidx.py
        python3 tools/add_cidx.py web/data/nalgadha_parcels.geojson [out.geojson]
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadastre_core as cc


def to_utm_poly(ring, to_utm):
    from shapely.geometry import Polygon
    pts = [to_utm.transform(x, y) for x, y in ring]
    p = Polygon(pts)
    return p if p.is_valid else p.buffer(0)


def main():
    inp = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("IN")
           or "web/data/nalgadha_parcels.geojson")
    out = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("OUT", inp)
    geo = json.load(open(inp, encoding="utf-8"))
    feats = geo.get("features", [])
    if not feats:
        print("no features"); return

    from pyproj import Transformer
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True)
    polys, idx = [], []
    for i, ft in enumerate(feats):
        g = ft.get("geometry") or {}
        if g.get("type") != "Polygon":
            continue
        polys.append(to_utm_poly(g["coordinates"][0], to_utm))
        idx.append(i)

    colors = cc.graph_color(polys, eps=0.6, ncolors=6)
    for k, c in zip(idx, colors):
        feats[k]["properties"]["cidx"] = int(c)

    json.dump(geo, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    used = sorted(set(colors))
    print(f"add_cidx: coloured {len(polys)} parcels with {len(used)} colours {used} -> {out}")


if __name__ == "__main__":
    main()
