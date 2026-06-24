#!/usr/bin/env python3
"""Replace bounding-box parcel geometry with REAL tessellating polygons traced
from Bhu-Naksha's rendered cadastre.

Why this exists: the public Bhu-Naksha JSON API only returns a plot's bounding
box (minx,miny,maxx,maxy) — tools/fetch_gbn_parcels.py turns those into 4-corner
rectangles, which overlap into a mush on the map. The real boundaries only exist
in the server's RENDERED map image. This tool GetMap's that image per village,
traces the boundary lattice into clean non-overlapping polygons (cadastre_core),
and tags each with the plot's `uid` via the bbox centroid we already have.

Joins are preserved: it READS the existing geojson for the plot list + attributes
(uid, plot_no, khata_no, area_ha, owner_count, village, gis_code, source) and only
swaps geometry, so nalgadha_owners.json / nalgadha_history.json keep matching.

Modes:
  network : fetch extent (getVVVVExtentGeoref) + GetMap, then vectorise. Needs
            egress to upbhunaksha.gov.in (runs in CI, or here once allowlisted).
  offline : --image <png> --bbox xmin,ymin,xmax,ymax [--crs EPSG:32644]
            vectorise a previously-saved cadastre image (no network). Lets the
            slow image step and the network step be verified independently.

Env / flags (network):
  OUT=web/data/nalgadha_parcels.geojson   file to read plots from and rewrite
  VILLAGE_CODE=120241                      only this village (else every village in OUT)
  GEOM_LAYERS=...                          WMS LAYERS for the boundary render (from recon)
  MPP=0.25  TILE_PX=2048  SIMPLIFY_M=0.5  MARGIN_M=30
Writes OUT in place (same schema + per-feature `geometry_method`, meta.geometry_method).
"""
import os
import sys
import json
import time
import math

import numpy as np
from pyproj import Transformer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadastre_core as cc

BASE = os.environ.get("BHUNAKSHA_BASE", "https://upbhunaksha.gov.in/bhunakshaserver")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# Network (only imported/used in network mode)
# --------------------------------------------------------------------------- #
def _session():
    import requests
    requests.packages.urllib3.disable_warnings()
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": BASE, "Origin": "https://upbhunaksha.gov.in"})
    return s


def _post(s, path, **kw):
    for i in range(4):
        try:
            return s.post(f"{BASE}/{path}", timeout=45, verify=False, **kw)
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def get_extent(s, gis_levels):
    r = _post(s, "MapInfo/getVVVVExtentGeoref", data={"gisLevels": gis_levels})
    j = r.json()
    return (j["xmin"], j["ymin"], j["xmax"], j["ymax"]), j.get("crs", "EPSG:32644"), j.get("gisCode")


def get_map(s, bbox, W, H, layers, gis_code, tile_px=2048):
    """GetMap the rendered cadastre into a single H x W x3 BGR array, tiling if big.

    The boundary raster renders anonymously only from LAYERS=VILLAGE_MAP via the
    /WMS/tile endpoint with STYLES=VILLAGE_MAP (validated 2026-06-24, see
    docs/bhunaksha_api.md); DERIVED_LAYER returns a ~4 KB blank. Endpoint/styles
    are env-overridable for other states' portals."""
    import cv2
    wms_path = os.environ.get("WMS_PATH", "WMS/tile")
    styles = os.environ.get("WMS_STYLES", "VILLAGE_MAP")
    xmin, ymin, xmax, ymax = bbox
    out = np.full((H, W, 3), 255, np.uint8)
    nx = max(1, math.ceil(W / tile_px))
    ny = max(1, math.ceil(H / tile_px))
    for ty in range(ny):
        for tx in range(nx):
            x0, x1 = tx * tile_px, min((tx + 1) * tile_px, W)
            y0, y1 = ty * tile_px, min((ty + 1) * tile_px, H)
            tw, th = x1 - x0, y1 - y0
            bx0 = xmin + (x0 / W) * (xmax - xmin)
            bx1 = xmin + (x1 / W) * (xmax - xmin)
            by1 = ymax - (y0 / H) * (ymax - ymin)   # row0 = north
            by0 = ymax - (y1 / H) * (ymax - ymin)
            params = {"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
                      "LAYERS": layers, "STYLES": styles, "SRS": "EPSG:32644",
                      "BBOX": f"{bx0},{by0},{bx1},{by1}", "WIDTH": tw, "HEIGHT": th,
                      "FORMAT": "image/png", "TRANSPARENT": "false",
                      "gis_code": gis_code, "state": "", "layercodes": ""}
            r = None
            for i in range(4):
                try:
                    r = s.get(f"{BASE}/{wms_path}", params=params, timeout=60, verify=False)
                    break
                except Exception:
                    time.sleep(2 * (i + 1))
            if not r or not r.headers.get("content-type", "").startswith("image"):
                raise RuntimeError(f"GetMap tile {tx},{ty} not an image: "
                                   f"{r.status_code if r else 'no resp'} "
                                   f"{r.headers.get('content-type') if r else ''}")
            arr = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
            out[y0:y1, x0:x1] = arr[:th, :tw]
    return out


# --------------------------------------------------------------------------- #
# Shared: existing plots -> (uid, attrs, centroid in UTM)
# --------------------------------------------------------------------------- #
def load_plots(out_path, village_code=None):
    """Group existing features by gis_code. Return {gis_code: {bbox_wgs, feats}}."""
    geo = json.load(open(out_path, encoding="utf-8"))
    groups = {}
    for ft in geo.get("features", []):
        p = ft["properties"]
        gc = p.get("gis_code")
        if village_code and not str(gc).endswith(str(village_code)):
            continue
        ring = ft["geometry"]["coordinates"][0]
        cx = sum(c[0] for c in ring) / len(ring)
        cy = sum(c[1] for c in ring) / len(ring)
        uid = p.get("uid") or ((p.get("village") or "").strip() + "|" + str(p.get("plot_no")))
        groups.setdefault(gc, {"feats": [], "meta": geo.get("meta", {})})
        groups[gc]["feats"].append({"uid": uid, "props": p, "centroid_wgs": (cx, cy),
                                    "geometry": ft["geometry"]})
    return geo, groups


def vectorize_village(img, bbox_utm, crs, feats, simplify_m=0.5):
    """img (BGR), bbox in UTM, list of plot feats -> list of output GeoJSON features."""
    H, W = img.shape[:2]
    px_to_utm, _, _ = cc.affine_from_bbox(bbox_utm, W, H)
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

    rings = cc.trace_pixel_rings(img)
    polys = []
    for p in cc.pixel_rings_to_polys(rings, px_to_utm):
        sp = cc.simplify_orient(p, simplify_m)
        if sp.is_valid and sp.area > 1.0:
            polys.append(sp)

    centroids = [(f["uid"], to_utm.transform(*f["centroid_wgs"])) for f in feats]
    poly_id, unmatched = cc.assign_ids(polys, centroids)
    by_uid = {f["uid"]: f for f in feats}

    out = []
    for idx, uid in enumerate(poly_id):
        if uid is None:
            continue                                  # traced region with no plot = furniture
        ring = [list(to_wgs.transform(x, y)) for x, y in polys[idx].exterior.coords]
        props = dict(by_uid[uid]["props"])
        props["geometry_method"] = "raster_vector"
        out.append({"type": "Feature", "properties": props,
                    "geometry": {"type": "Polygon", "coordinates": [ring]}})
    for uid in unmatched:                              # keep bbox so no plot disappears
        f = by_uid[uid]
        props = dict(f["props"])
        props["geometry_method"] = "bbox_fallback"
        out.append({"type": "Feature", "properties": props, "geometry": f["geometry"]})
    return out, len(polys), len(unmatched)


# --------------------------------------------------------------------------- #
def parse_args(argv):
    a = {"image": None, "bbox": None, "crs": "EPSG:32644"}
    it = iter(argv)
    for tok in it:
        if tok == "--image":
            a["image"] = next(it)
        elif tok == "--bbox":
            a["bbox"] = tuple(float(v) for v in next(it).split(","))
        elif tok == "--crs":
            a["crs"] = next(it)
    return a


def main():
    out_path = os.environ.get("OUT", os.path.join(ROOT, "web/data/nalgadha_parcels.geojson"))
    village = os.environ.get("VILLAGE_CODE")
    simplify_m = float(os.environ.get("SIMPLIFY_M", "0.5"))
    args = parse_args(sys.argv[1:])

    geo, groups = load_plots(out_path, village)
    if not groups:
        print("no matching plots in", out_path)
        return

    # OFFLINE: vectorise a saved image for ONE village (the only group), no network.
    if args["image"]:
        import cv2
        gc = next(iter(groups))
        feats = groups[gc]["feats"]
        img = cv2.imread(args["image"], cv2.IMREAD_COLOR)
        if img is None:
            print("cannot read", args["image"]); sys.exit(2)
        if not args["bbox"]:
            print("--image requires --bbox xmin,ymin,xmax,ymax (UTM)"); sys.exit(2)
        new, npoly, nfb = vectorize_village(img, args["bbox"], args["crs"], feats, simplify_m)
        print(f"[offline] {gc}: traced {npoly} polys, {len(new)-nfb} matched, {nfb} bbox-fallback")
        _write(out_path, geo, {gc: new})
        return

    # NETWORK: per village, getVVVVExtentGeoref + GetMap + vectorise.
    # Resumable + bounded: skip villages already traced (geometry_method set),
    # process at most MAX_VILLAGES new ones, and stop before TIME_BUDGET so a
    # schedule fills a whole tehsil over several runs without hitting the timeout.
    layers = os.environ.get("GEOM_LAYERS", "VILLAGE_MAP")
    mpp = float(os.environ.get("MPP", "0.3"))
    tile_px = int(os.environ.get("TILE_PX", "2048"))
    margin = float(os.environ.get("MARGIN_M", "30"))
    max_villages = int(os.environ.get("MAX_VILLAGES", "4"))
    time_budget = float(os.environ.get("TIME_BUDGET", "2400"))
    # A village is "done at this resolution" only if it was traced at an mpp <= target.
    # Villages traced coarser (or with no recorded mpp, e.g. an earlier run) are
    # re-traced so lowering MPP auto-upgrades them. Once all are at <= target, runs no-op.
    done_mpp = {}
    for ft in geo.get("features", []):
        if ft["properties"].get("geometry_method") in ("raster_vector", "bbox_fallback"):
            gc = ft["properties"].get("gis_code")
            done_mpp[gc] = min(done_mpp.get(gc, 9e9), float(ft["properties"].get("mpp", 9e9)))
    todo = [(gc, grp) for gc, grp in groups.items() if done_mpp.get(gc, 9e9) > mpp + 1e-9]
    print(f"{len(groups)-len(todo)} villages already at <= {mpp} m/px; {len(todo)} to (re)trace "
          f"(this run: <= {max_villages} villages, <= {time_budget:.0f}s)")
    s = _session()
    rebuilt = {}
    t0 = time.time()
    for gc, grp in todo:
        if len(rebuilt) >= max_villages or (time.time() - t0) > time_budget:
            print("batch limit reached — stopping (resume next run)")
            break
        gis_levels = f"{gc[:3]},{gc[3:8]},{gc[8:]}"          # district,tehsil,village
        try:
            bbox, crs, _ = get_extent(s, gis_levels)
            bbox = (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)
            W = int(round((bbox[2] - bbox[0]) / mpp))
            H = int(round((bbox[3] - bbox[1]) / mpp))
            print(f"{gc}: extent {bbox} crs {crs} -> {W}x{H}px @ {mpp} m/px")
            img = get_map(s, bbox, W, H, layers, gc, tile_px)
            new, npoly, nfb = vectorize_village(img, bbox, crs, grp["feats"], simplify_m)
            for ft in new:                                   # record the resolution we traced at
                ft["properties"]["mpp"] = mpp
            print(f"  traced {npoly} polys -> {len(new)-nfb} matched, {nfb} bbox-fallback")
            rebuilt[gc] = new
        except Exception as e:
            print(f"  {gc}: FAILED ({e!r}) — skipping this run", file=sys.stderr)
    if rebuilt:
        _write(out_path, geo, rebuilt)
    else:
        print("nothing rebuilt this run (all done or all failed)")


def _write(out_path, geo, rebuilt):
    """Replace features of the rebuilt gis_codes; keep others untouched; bump meta."""
    keep = [ft for ft in geo.get("features", [])
            if ft["properties"].get("gis_code") not in rebuilt]
    newfeats = []
    for v in rebuilt.values():
        newfeats.extend(v)
    geo["features"] = keep + newfeats
    meta = geo.setdefault("meta", {})
    meta["geometry_method"] = "raster_vector"
    rv = sum(1 for ft in newfeats if ft["properties"].get("geometry_method") == "raster_vector")
    meta["geometry_coverage"] = {"rebuilt_features": len(newfeats), "raster_vector": rv,
                                 "bbox_fallback": len(newfeats) - rv}
    json.dump(geo, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"wrote {out_path}: {len(geo['features'])} features "
          f"({rv} real polygons, {len(newfeats)-rv} bbox-fallback)")


if __name__ == "__main__":
    main()
