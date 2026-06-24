#!/usr/bin/env python3
"""cadastre_core — pure geometry helpers for turning a RENDERED cadastre image
into real, tessellating parcel polygons, plus graph-colouring for the map.

No network here; everything is deterministic and unit-testable offline
(tools/selftest_geom.py). The live fetch (GetMap from Bhu-Naksha) lives in
tools/fetch_bhunaksha_geom.py and calls into these functions.

Pipeline (raster -> vector):
  affine_from_bbox  : exact pixel<->world (UTM) mapping from a GetMap BBOX
  trace_pixel_rings : binarise dark boundary lines, drop printed plot numbers,
                      skeletonise, label enclosed regions, marching-squares each
                      -> rings that share the skeleton => tessellate, no overlap
  pixel_rings_to_polys / simplify_orient : world-space shapely polygons
  assign_ids        : tag each polygon with the plot uid whose centroid it contains
  graph_color       : Welsh-Powell so adjacent parcels never share a colour
"""
import numpy as np


# --------------------------------------------------------------------------- #
# Georeferencing: exact, linear pixel <-> world (no distortion)
# --------------------------------------------------------------------------- #
def affine_from_bbox(bbox, W, H):
    """Return px_to_world(col, row) for a GetMap of `bbox`=(xmin,ymin,xmax,ymax)
    rendered at W x H pixels. Pixel CENTRES (+0.5); row 0 is the NORTH edge
    (image Y grows down, world Y/northing grows up)."""
    xmin, ymin, xmax, ymax = bbox
    sx = (xmax - xmin) / float(W)
    sy = (ymax - ymin) / float(H)

    def px_to_world(col, row):
        return (xmin + (col + 0.5) * sx, ymax - (row + 0.5) * sy)

    return px_to_world, sx, sy


# --------------------------------------------------------------------------- #
# Raster -> vector
# --------------------------------------------------------------------------- #
def boundary_mask(img, dark_thresh=None):
    """1 where a dark boundary/text pixel is, else 0. img is BGR or gray."""
    import cv2
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if dark_thresh is None:
        _, m = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        m = ((gray < dark_thresh).astype(np.uint8)) * 255
    return (m > 0).astype(np.uint8)


def drop_text_components(mask, keep_frac=0.10, min_span_px=80):
    """Remove printed plot-number glyphs: keep the connected boundary NETWORK
    (long, spanning components), drop small compact blobs (digits).

    A component is kept if it is large relative to the biggest component OR it
    spans a wide bounding box (a long boundary line). Cadastral boundaries form
    one big connected lattice; numbers are small islands."""
    import cv2
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if num <= 1:
        return mask
    areas = stats[1:, cv2.CC_STAT_AREA]
    biggest = areas.max() if len(areas) else 0
    keep = np.zeros(mask.shape, np.uint8)
    for i in range(1, num):
        a = stats[i, cv2.CC_STAT_AREA]
        span = max(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT])
        if a >= biggest * keep_frac or span >= min_span_px:
            keep[labels == i] = 1
    return keep


def trace_pixel_rings(img, dark_thresh=None, keep_frac=0.10, min_span_px=80,
                      min_region_px=60, drop_text=True):
    """Rendered cadastre image -> list of pixel-space rings (each an Nx2 array of
    (col,row) float vertices), one per enclosed plot.

    Region-labelling guarantees a tessellation: neighbours are separated by the
    1px skeleton, so their contours run along the SAME line => shared edges."""
    from skimage.morphology import skeletonize
    from skimage.measure import label, find_contours

    mask = boundary_mask(img, dark_thresh)
    if drop_text:
        mask = drop_text_components(mask, keep_frac, min_span_px)
    skel = skeletonize(mask > 0)

    interior = (skel == 0)
    lab = label(interior, connectivity=1)
    # regions touching the image border are "outside" the cadastre -> drop
    border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])

    rings = []
    for k in range(1, int(lab.max()) + 1):
        if k in border:
            continue
        region = (lab == k)
        if int(region.sum()) < min_region_px:
            continue
        contours = find_contours(region.astype(float), 0.5)
        if not contours:
            continue
        c = max(contours, key=len)          # (row, col)
        ring = np.column_stack([c[:, 1], c[:, 0]])   # -> (col, row) = (x_px, y_px)
        rings.append(ring)
    return rings


def pixel_rings_to_polys(rings, px_to_world, min_pts=4):
    """Map pixel rings -> shapely Polygons in world (UTM) coords."""
    from shapely.geometry import Polygon
    polys = []
    for ring in rings:
        if len(ring) < min_pts:
            continue
        pts = [px_to_world(float(x), float(y)) for x, y in ring]
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area <= 0:
            continue
        polys.append(poly)
    return polys


def simplify_orient(poly, tol_m=0.5):
    """Douglas-Peucker simplify (drops marching-squares stair-steps) + CCW exterior."""
    from shapely.geometry.polygon import orient
    p = poly.simplify(tol_m, preserve_topology=True)
    if p.is_empty or not p.is_valid:
        p = poly.buffer(0)
    # keep the largest part if simplify produced a MultiPolygon
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda g: g.area)
    return orient(p, sign=1.0)


# --------------------------------------------------------------------------- #
# Tag each traced polygon with the plot whose centroid it contains
# --------------------------------------------------------------------------- #
def assign_ids(polys, id_centroids):
    """id_centroids: list of (id, (x, y)) world points (one per known plot).
    Returns (poly_id: list aligned to polys with the matched id or None,
             unmatched_ids: ids whose centroid fell in no polygon)."""
    from shapely.strtree import STRtree
    from shapely.geometry import Point

    tree = STRtree(polys)
    poly_id = [None] * len(polys)
    unmatched = []
    for pid, (cx, cy) in id_centroids:
        pt = Point(cx, cy)
        # NOTE: STRtree.query(pt, predicate=...) evaluates pt.<predicate>(poly),
        # so use "intersects" then prefer a polygon that strictly contains pt.
        cand = [int(i) for i in tree.query(pt, predicate="intersects")]
        contains = [i for i in cand if polys[i].contains(pt)]
        pool = contains if contains else cand
        # take the first FREE polygon; if the containing polygon is already
        # claimed (two plots merged into one traced region), don't steal it —
        # this plot falls back to its bbox geometry instead.
        hit = next((i for i in pool if poly_id[i] is None), None)
        if hit is None:
            unmatched.append(pid)
        else:
            poly_id[hit] = pid
    return poly_id, unmatched


# --------------------------------------------------------------------------- #
# Graph colouring so adjacent parcels never share a colour (Welsh-Powell)
# --------------------------------------------------------------------------- #
def graph_color(polys, eps=0.6, ncolors=6):
    """Return a colour index (0..ncolors-1) per polygon; neighbours differ.
    Adjacency = polygons within `eps` metres (touching, or a tracing-gap apart)."""
    from shapely.strtree import STRtree

    n = len(polys)
    tree = STRtree(polys)
    adj = [set() for _ in range(n)]
    for i in range(n):
        for j in tree.query(polys[i].buffer(eps)):
            j = int(j)
            if j <= i:
                continue
            if polys[i].distance(polys[j]) < eps:
                adj[i].add(j)
                adj[j].add(i)
    order = sorted(range(n), key=lambda i: -len(adj[i]))   # highest degree first
    color = [-1] * n
    for i in order:
        used = {color[j] for j in adj[i] if color[j] >= 0}
        c = 0
        while c in used:
            c += 1
        color[i] = c % ncolors
    return color


# --------------------------------------------------------------------------- #
# Test helper: rasterise polygon boundaries (+ optional numbers) to an image,
# i.e. a stand-in for Bhu-Naksha's rendered cadastre.
# --------------------------------------------------------------------------- #
def rasterize_boundaries(polys, bbox, W, H, line_px=2, numbers=None):
    import cv2
    xmin, ymin, xmax, ymax = bbox
    sx = (xmax - xmin) / float(W)
    sy = (ymax - ymin) / float(H)

    def world_to_px(x, y):
        return (int(round((x - xmin) / sx - 0.5)), int(round((ymax - y) / sy - 0.5)))

    img = np.full((H, W, 3), 255, np.uint8)
    for poly in polys:
        ring = list(poly.exterior.coords)
        pts = np.array([world_to_px(x, y) for x, y in ring], np.int32).reshape(-1, 1, 2)
        cv2.polylines(img, [pts], True, (0, 0, 0), line_px)
    if numbers:
        for (x, y), txt in numbers:
            px, py = world_to_px(x, y)
            cv2.putText(img, str(txt), (px - 8, py + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    return img
