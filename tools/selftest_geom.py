#!/usr/bin/env python3
"""Offline self-tests for the cadastre raster->vector + colouring pipeline.
No network: synthesises a rendered cadastre, traces it back, and checks the
recovered polygons are real, tessellating, correctly id-tagged, and colourable.

Run: python3 tools/selftest_geom.py   (exit 0 = all pass)
"""
import sys
import numpy as np
from shapely.geometry import MultiPoint, box, Polygon
from shapely.ops import voronoi_diagram

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import cadastre_core as cc

FAIL = 0
def check(cond, msg):
    global FAIL
    print(("  ok  " if cond else "  FAIL ") + msg)
    if not cond:
        FAIL += 1


def test_affine():
    print("== affine pixel<->UTM ==")
    bbox = (149750.0, 3155400.0, 153060.0, 3157120.0)
    W, H = 6620, 3440  # 0.5 m/px
    px, sx, sy = cc.affine_from_bbox(bbox, W, H)
    check(abs(sx - 0.5) < 1e-9 and abs(sy - 0.5) < 1e-9, "scale = 0.5 m/px")
    x0, y0 = px(0, 0)            # top-left pixel centre = west / NORTH
    check(abs(x0 - (149750.0 + 0.25)) < 1e-6, "col0 -> xmin+half px")
    check(abs(y0 - (3157120.0 - 0.25)) < 1e-6, "row0 -> ymax-half px (north)")
    xl, yl = px(W - 1, H - 1)
    check(yl < y0 and xl > x0, "row increases southward, col eastward")


def synth_cadastre(seed=7, n=26):
    rng = np.random.default_rng(seed)
    # village cluster occupies B; render frame adds a margin so edge plots are interior
    B = (150000.0, 3155600.0, 151000.0, 3156200.0)   # 1000 x 600 m
    pts = [(rng.uniform(B[0] + 40, B[2] - 40), rng.uniform(B[1] + 40, B[3] - 40)) for _ in range(n)]
    env = box(*B)
    vd = voronoi_diagram(MultiPoint(pts), envelope=env)
    cells = []
    for g in vd.geoms:
        c = g.intersection(env)
        if c.geom_type == "Polygon" and c.area > 200:
            cells.append(c)
    margin = 40.0
    rbbox = (B[0] - margin, B[1] - margin, B[2] + margin, B[3] + margin)
    W = int((rbbox[2] - rbbox[0]) / 0.5)
    H = int((rbbox[3] - rbbox[1]) / 0.5)
    ids = [(f"P{i}", cells[i].representative_point()) for i in range(len(cells))]
    numbers = [((p.x, p.y), pid.replace("P", "")) for pid, p in ids]
    img = cc.rasterize_boundaries(cells, rbbox, W, H, line_px=2, numbers=numbers)
    return cells, ids, img, rbbox, W, H


def test_raster_to_vector():
    print("== raster -> vector (synthetic Voronoi cadastre) ==")
    cells, ids, img, rbbox, W, H = synth_cadastre()
    px, _, _ = cc.affine_from_bbox(rbbox, W, H)
    rings = cc.trace_pixel_rings(img)
    polys = [cc.simplify_orient(p, 0.5) for p in cc.pixel_rings_to_polys(rings, px)]
    polys = [p for p in polys if p.is_valid and p.area > 100]

    check(len(polys) > 0, f"recovered {len(polys)} polygons (input {len(cells)})")
    check(abs(len(polys) - len(cells)) <= max(2, len(cells) // 10),
          f"plot count matches input within tolerance (text removed): {len(polys)} vs {len(cells)}")

    vtx = sorted(len(p.exterior.coords) - 1 for p in polys)
    med = vtx[len(vtx) // 2]
    check(med > 4, f"median vertices/plot = {med} (>4 => real polygons, not 5-pt bbox)")

    # non-axis-aligned: a bbox has every edge horizontal/vertical
    def axis_aligned(p):
        c = list(p.exterior.coords)
        return all(abs(c[i][0] - c[i + 1][0]) < 1e-6 or abs(c[i][1] - c[i + 1][1]) < 1e-6
                   for i in range(len(c) - 1))
    check(sum(axis_aligned(p) for p in polys) == 0, "no polygon is an axis-aligned box")

    # tessellation: negligible pairwise overlap
    from shapely.strtree import STRtree
    tree = STRtree(polys)
    overlap = 0.0
    for i, p in enumerate(polys):
        for j in tree.query(p):
            j = int(j)
            if j <= i:
                continue
            inter = p.intersection(polys[j]).area
            if inter > 1.0:
                overlap += inter
    total = sum(p.area for p in polys)
    check(overlap / total < 0.005, f"pairwise overlap {overlap/total*100:.3f}% < 0.5% (tessellates)")

    # id assignment by centroid containment
    centroids = [(pid, (pt.x, pt.y)) for pid, pt in ids]
    poly_id, unmatched = cc.assign_ids(polys, centroids)
    matched = sum(1 for x in poly_id if x is not None)
    rate = matched / len(centroids)
    check(rate >= 0.90, f"plot-id match rate {rate*100:.0f}% (>=90%)")
    # every assignment is geometrically correct (centroid inside its polygon)
    from shapely.geometry import Point
    idmap = {pid: (pt.x, pt.y) for pid, pt in ids}
    bad = 0
    for k, pid in enumerate(poly_id):
        if pid is None:
            continue
        cx, cy = idmap[pid]
        if not polys[k].buffer(0.5).contains(Point(cx, cy)):
            bad += 1
    check(bad == 0, "every tagged polygon contains its plot centroid")


def test_assign_outside_fallback():
    print("== id assignment edge cases ==")
    grid = [Polygon([(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)])
            for i in range(2) for j in range(2)]
    cents = [("a", (0.5, 0.5)), ("b", (1.5, 0.5)), ("c", (0.5, 1.5)),
             ("d", (1.5, 1.5)), ("outside", (9.0, 9.0))]
    poly_id, unmatched = cc.assign_ids(grid, cents)
    check(unmatched == ["outside"], "centroid outside all polygons -> unmatched (bbox fallback)")
    check(sorted(x for x in poly_id if x) == ["a", "b", "c", "d"], "interior centroids tagged")


def test_graph_color():
    print("== graph colouring (Welsh-Powell) ==")
    # 6x6 checkerboard of unit squares -> 4-colourable planar graph
    grid = [Polygon([(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)])
            for i in range(6) for j in range(6)]
    colors = cc.graph_color(grid, eps=0.1)
    from shapely.strtree import STRtree
    tree = STRtree(grid)
    bad = 0
    for i, p in enumerate(grid):
        for j in tree.query(p.buffer(0.1)):
            j = int(j)
            if j <= i:
                continue
            if p.distance(grid[j]) < 0.1 and colors[i] == colors[j]:
                bad += 1
    check(bad == 0, "no edge-adjacent squares share a colour")
    check(max(colors) <= 5, f"uses <=6 colours (max index {max(colors)})")


if __name__ == "__main__":
    test_affine()
    test_raster_to_vector()
    test_assign_outside_fallback()
    test_graph_color()
    print(f"\n{'ALL PASS' if not FAIL else str(FAIL)+' FAILED'}")
    sys.exit(1 if FAIL else 0)
