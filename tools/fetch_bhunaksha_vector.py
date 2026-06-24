#!/usr/bin/env python3
"""Fetch REAL parcel polygons for UP Bhu-Naksha villages via the DIRECT vector
endpoint discovered in the frontend deep-extract (docs/bhunaksha_api.md):

    POST {SRV}/mapModificationController/getGeoJSONLayerData
         { giscode, layercodes, oprType }   -> GeoJSON (text)

This supersedes the bbox grid-sampler (fetch_gbn_parcels.py, overlapping
rectangles) and the raster->vector tracer (fetch_bhunaksha_geom.py): one call
returns every plot in a village as a true tessellating polygon.

Because the exact request shape (oprType value, body encoding, layercode source,
GeoJSON CRS) was reverse-engineered statically, this tool DISCOVERS the working
combination at runtime and records it, so a wrong guess can never silently write
bad data — it only writes geometry when a real FeatureCollection comes back.

Needs egress to upbhunaksha.gov.in -> runs in GitHub Actions.

MODES (env MODE):
  validate : probe ONE village, dump every attempt to _probe/bhunaksha_vector_live.json,
             write NO map data. Run this first.
  fetch    : auto-discover the combo, then fetch every target village and write OUT.

Targeting (fetch): VILLAGE_CODE (single) OR DISTRICT/TEHSIL enumeration OR the
unique gis_codes already present in OUT.
"""
import os
import re
import sys
import json
import time

BASE = "https://upbhunaksha.gov.in"
SRV = BASE + "/bhunakshaserver"
HOME = BASE + "/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODE = os.environ.get("MODE", "validate")
GIS = os.environ.get("GIS", "14100743120241")          # default probe village: Nalgadha
DISTRICT = os.environ.get("DISTRICT", "गौतम")
TEHSIL = os.environ.get("TEHSIL", "जेवर")
VILLAGE_CODE = os.environ.get("VILLAGE_CODE", "")
OUT = os.environ.get("OUT", "web/data/gbn_parcels_vector.geojson")
PROBE_OUT = os.environ.get("PROBE_OUT", "_probe/bhunaksha_vector_live.json")
MAX_VILLAGES = int(os.environ.get("MAX_VILLAGES", "60"))
SLEEP = float(os.environ.get("SLEEP", "0.3"))
SOURCE_GEOJSON = os.environ.get("SOURCE_GEOJSON", "web/data/gbn_parcels.geojson")

# oprType is unknown from the static extract — try the plausible values the
# map-modification controller would accept (numeric op codes + map/ror names).
OPRTYPE_CANDIDATES = ["0", "1", "2", "3", "MAP", "ROR", "map", "ror", "MAP_PLOT", ""]

s = None
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
JSONH = {"Content-Type": "application/json"}


def session():
    import requests
    requests.packages.urllib3.disable_warnings()
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": UA, "Referer": HOME, "Origin": BASE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
    })
    try:                       # establish JSESSIONID (geometry calls are withCredentials)
        sess.get(HOME, timeout=40, verify=False)
        sess.get(SRV + "/session/validate", timeout=40, verify=False)
    except Exception:
        pass
    return sess


def post(path, *, data=None, json_body=None, timeout=60):
    headers = JSONH if json_body is not None else FORM
    for i in range(4):
        try:
            return s.post(f"{SRV}/{path}", data=data, json=json_body,
                          headers=headers, timeout=timeout, verify=False)
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def gislevels_of(giscode):
    """giscode 14100743120241 -> '141,00743,120241' (state 3, district 5, village 6)."""
    g = str(giscode)
    return f"{g[0:3]},{g[3:8]},{g[8:14]}" if len(g) >= 14 else g


def get_layercodes(giscode):
    """Ask Layers/getLayers for this village and pull every plausible layer-code
    value out of the response. Returns (codes, raw)."""
    codes, raw = [], {}
    for lt in ("TABLE_LAYER_MASTER", "TABLE_DERIVED_LAYERS"):
        r = post("Layers/getLayers", data={"layerType": lt, "giscode": giscode})
        body = None
        if r is not None:
            try:
                body = r.json()
            except Exception:
                body = r.text[:2000]
        raw[lt] = {"status": getattr(r, "status_code", None), "body": body}
        for c in _harvest_codes(body):
            if c not in codes:
                codes.append(c)
    return codes, raw


def _harvest_codes(body):
    out = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if re.search(r"layer.?code|^code$|gis.?layer", str(k), re.I) and isinstance(v, (str, int)):
                    out.append(str(v))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(body)
    return out


def _featurecollection(text):
    """Parse text as GeoJSON; return (n_features, geom_types, prop_keys, obj) or None."""
    try:
        obj = json.loads(text)
    except Exception:
        return None
    feats = obj.get("features") if isinstance(obj, dict) else None
    if not isinstance(feats, list) or not feats:
        return None
    gtypes, pkeys = set(), set()
    for f in feats:
        g = (f.get("geometry") or {}).get("type")
        if g:
            gtypes.add(g)
        pkeys |= set((f.get("properties") or {}).keys())
    if not gtypes:
        return None
    return len(feats), sorted(gtypes), sorted(pkeys), obj


def try_geojson(giscode, layercodes, oprtype, body_style):
    payload = {"giscode": giscode, "layercodes": layercodes, "oprType": oprtype}
    if body_style == "json":
        r = post("mapModificationController/getGeoJSONLayerData", json_body=payload)
    else:
        r = post("mapModificationController/getGeoJSONLayerData", data=payload)
    rec = {"layercodes": layercodes, "oprType": oprtype, "body": body_style,
           "status": getattr(r, "status_code", None),
           "ct": (r.headers.get("content-type") if r is not None else None),
           "len": (len(r.text) if r is not None and r.text else 0)}
    fc = _featurecollection(r.text) if (r is not None and r.text) else None
    if fc:
        n, gtypes, pkeys, obj = fc
        rec.update({"features": n, "geom_types": gtypes, "prop_keys": pkeys, "ok": True})
        return rec, obj
    rec["snippet"] = (r.text[:400] if (r is not None and r.text) else "")
    rec["ok"] = False
    return rec, None


def discover(giscode, attempts_sink=None):
    """Find a (layercodes, oprType, body_style) that returns a polygon FeatureCollection.
    Returns (combo_dict, geojson_obj) or (None, None)."""
    codes, raw = get_layercodes(giscode)
    if attempts_sink is not None:
        attempts_sink["getLayers"] = raw
        attempts_sink["harvested_codes"] = codes
    # layercodes formats to try: all joined, each single, and empty
    lc_variants = []
    if codes:
        lc_variants.append(",".join(codes))
        lc_variants += codes[:6]
    lc_variants.append("")
    seen = set()
    for body_style in ("json", "form"):
        for lc in lc_variants:
            for opr in OPRTYPE_CANDIDATES:
                key = (body_style, lc, opr)
                if key in seen:
                    continue
                seen.add(key)
                rec, obj = try_geojson(giscode, lc, opr, body_style)
                if attempts_sink is not None:
                    attempts_sink.setdefault("attempts", []).append(rec)
                if rec.get("ok") and any("Poly" in g for g in rec.get("geom_types", [])):
                    return {"layercodes": lc, "oprType": opr, "body": body_style}, obj
                time.sleep(0.1)
    return None, None


def reproject_fc(obj):
    """Reproject a GeoJSON FeatureCollection to EPSG:4326 in place. CRS is detected
    from coordinate magnitude (UTM 44N northing ~3.1e6) unless declared."""
    from pyproj import Transformer
    crs = "EPSG:4326"
    decl = (((obj.get("crs") or {}).get("properties") or {}).get("name") or "")
    if "32644" in decl:
        crs = "EPSG:32644"
    else:
        c = _first_coord(obj)
        if c and abs(c[0]) > 1000:        # not lon/lat -> assume UTM 44N
            crs = "EPSG:32644"
    if crs == "EPSG:4326":
        return obj
    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    def rt(coords):
        if isinstance(coords[0], (int, float)):
            x, y = tr.transform(coords[0], coords[1])
            return [round(x, 7), round(y, 7)]
        return [rt(c) for c in coords]
    for f in obj.get("features", []):
        g = f.get("geometry") or {}
        if g.get("coordinates"):
            g["coordinates"] = rt(g["coordinates"])
    obj["_crs_source"] = crs
    return obj


def _first_coord(obj):
    for f in obj.get("features", []):
        c = (f.get("geometry") or {}).get("coordinates")
        while isinstance(c, list) and c and isinstance(c[0], list):
            c = c[0]
        if isinstance(c, list) and len(c) >= 2 and isinstance(c[0], (int, float)):
            return c
    return None


def normalize(obj, giscode, village, combo):
    """Tag each feature with schema-v1 properties (docs/ncr_rollout.md)."""
    today = time.strftime("%Y-%m-%d")
    feats = []
    for f in obj.get("features", []):
        p = f.get("properties") or {}
        plot_no = str(p.get("plotno") or p.get("plotNo") or p.get("PLOTNO")
                      or p.get("kide") or p.get("plot_no") or p.get("gisno") or "").strip()
        props = {
            "plot_no": plot_no,
            "uid": f"{(village or '').strip()}|{plot_no}",
            "village": village,
            "gis_code": giscode,
            "source": "UP Bhu-Naksha",
            "geometry_method": "vector_api",
            "fetched_at": today,
        }
        for k in ("khata_no", "area_ha", "khasra", "area"):
            if k in p:
                props[k] = p[k]
        feats.append({"type": "Feature", "geometry": f.get("geometry"), "properties": props})
    return feats


JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}")
TOKEN_KEY_RE = re.compile(r"token|jwt|access|authoriz|bearer", re.I)


def _harvest_tokens(text):
    """Pull JWT-looking strings and token-ish JSON values out of a response."""
    toks = list(dict.fromkeys(JWT_RE.findall(text or "")))
    try:
        obj = json.loads(text)

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if isinstance(v, str) and TOKEN_KEY_RE.search(str(k)) and len(v) > 12:
                        toks.append(v)
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(obj)
    except Exception:
        pass
    return list(dict.fromkeys(toks))


def probe_token():
    """Hunt for an ANONYMOUS/guest token the vector endpoint would accept."""
    import requests
    out = {"mode": "token", "gis": GIS, "bundle_hits": {}, "endpoints": [], "token_retry": []}

    # 1) How is the Authorization header built? Grep the bundle.
    blob = ""
    try:
        home = s.get(HOME, timeout=40, verify=False).text
        srcs = set(re.findall(r'src=["\']([^"\']+\.js)["\']', home) +
                   re.findall(r'["\'](/?[A-Za-z0-9_./-]+\.js)["\']', home))
        for src in list(srcs)[:8]:
            u = src if src.startswith("http") else BASE + "/" + src.lstrip("/")
            try:
                blob += "\n" + s.get(u, timeout=40, verify=False).text
            except Exception:
                pass
    except Exception as e:
        out["bundle_error"] = repr(e)
    out["bundle_chars"] = len(blob)
    for kw in ["Authorization", "Bearer ", "setHeaders", "intercept", "getToken",
               "localStorage.getItem", "sessionStorage", "auth/login", "auth/token",
               "/token", "jwt", "X-Auth", "apiKey", "api_key", "guest", "public_token"]:
        hits = [m.start() for m in re.finditer(re.escape(kw), blob)][:2]
        if hits:
            out["bundle_hits"][kw] = [blob[max(0, i - 120):i + 160] for i in hits]

    # 2) Try anonymous token-issuing endpoints.
    candidates = [
        ("post", "auth/login", {}), ("post", "auth/login", {"username": "guest", "password": "guest"}),
        ("get", "auth/token", None), ("post", "auth/token", {}),
        ("get", "token", None), ("post", "getToken", {}),
        ("get", "session/validate", None), ("get", "masterdata/web-menu", None),
        ("get", "auth/guest", None), ("post", "auth/guestLogin", {}),
    ]
    found = []
    for method, path, body in candidates:
        try:
            if method == "get":
                r = s.get(f"{SRV}/{path}", timeout=40, verify=False)
            else:
                r = s.post(f"{SRV}/{path}", json=body, headers=JSONH, timeout=40, verify=False)
        except Exception as e:
            out["endpoints"].append({"path": path, "method": method, "error": repr(e)})
            continue
        toks = _harvest_tokens(r.text)
        hdr_auth = r.headers.get("Authorization") or r.headers.get("authorization")
        if hdr_auth:
            toks.append(hdr_auth.replace("Bearer ", ""))
        out["endpoints"].append({
            "path": path, "method": method, "status": r.status_code,
            "set_cookie": bool(r.headers.get("set-cookie")),
            "len": len(r.text or ""), "snippet": (r.text or "")[:200],
            "tokens_found": len(toks),
        })
        found += toks
    found = list(dict.fromkeys(found))
    out["tokens_found_total"] = len(found)

    # 3) If we got any token, retry the vector endpoint with it.
    codes, _ = get_layercodes(GIS)
    lc = ",".join(codes) if codes else ""
    for tok in found[:4]:
        for opr in ("0", "1", "MAP"):
            try:
                r = s.post(f"{SRV}/mapModificationController/getGeoJSONLayerData",
                           json={"giscode": GIS, "layercodes": lc, "oprType": opr},
                           headers={**JSONH, "Authorization": f"Bearer {tok}"},
                           timeout=40, verify=False)
            except Exception as e:
                out["token_retry"].append({"tok": tok[:16] + "…", "error": repr(e)})
                continue
            fc = _featurecollection(r.text) if r.text else None
            out["token_retry"].append({
                "tok": tok[:16] + "…", "oprType": opr, "status": r.status_code,
                "len": len(r.text or ""), "is_featurecollection": bool(fc),
                "snippet": (r.text or "")[:160],
            })
            if fc:
                out["UNLOCKED"] = True
    return out


def enumerate_villages():
    """Return [(giscode, village_name), ...] for the configured DISTRICT/TEHSIL."""

    def level(n, codes=""):
        r = post("masterdata/levelvalue", data={"level": n, "codes": codes})
        return r.json() if r is not None else []

    def find(items, needle):
        return next((it for it in items if needle in (it.get("value") or "")), None)

    out = []
    try:
        d = find(level(1), DISTRICT)
        t = find(level(2, d["code"]), TEHSIL)
        villages = level(3, f"{d['code']},{t['code']}")
        for v in villages[:MAX_VILLAGES]:
            gl = f"{d['code']},{t['code']},{v['code']}"
            ext = post("MapInfo/getVVVVExtentGeoref", data={"gisLevels": gl})
            try:
                gc = ext.json().get("gisCode")
            except Exception:
                gc = None
            if gc:
                out.append((gc, v.get("value")))
            time.sleep(SLEEP)
    except Exception as e:
        print("enumerate failed:", repr(e), file=sys.stderr)
    return out


def villages_from_existing():
    path = os.path.join(ROOT, SOURCE_GEOJSON)
    out, seen = [], set()
    try:
        d = json.load(open(path, encoding="utf-8"))
        for f in d.get("features", []):
            p = f.get("properties") or {}
            gc, vil = p.get("gis_code"), p.get("village")
            if gc and gc not in seen:
                seen.add(gc)
                out.append((gc, vil))
    except Exception:
        pass
    return out


def write_json(rel, obj):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print("wrote", rel, os.path.getsize(path), "bytes")


def main():
    global s
    s = session()

    if MODE == "token":
        out = probe_token()
        write_json(PROBE_OUT, out)
        print("TOKEN PROBE:", "UNLOCKED" if out.get("UNLOCKED") else
              f"no working anon token ({out.get('tokens_found_total', 0)} tokens seen)")
        return

    if MODE == "validate":
        sink = {"gis": GIS, "gislevels": gislevels_of(GIS), "mode": "validate"}
        combo, obj = discover(GIS, sink)
        sink["combo"] = combo
        if combo and obj:
            fc = _featurecollection(json.dumps(obj))
            sink["result"] = {"features": fc[0], "geom_types": fc[1], "prop_keys": fc[2]}
            sink["sample_geometry"] = (obj["features"][0].get("geometry") or {})
        write_json(PROBE_OUT, sink)
        print("DISCOVERED:", combo if combo else "NONE — see " + PROBE_OUT)
        return

    # fetch mode
    if VILLAGE_CODE:
        targets = [(VILLAGE_CODE if len(VILLAGE_CODE) >= 14 else GIS, None)]
    else:
        targets = enumerate_villages() or villages_from_existing()
    if not targets:
        print("no target villages", file=sys.stderr)
        sys.exit(1)

    combo = None
    all_feats, report = [], {"villages": [], "combo": None}
    for gc, vil in targets:
        if combo is None:
            combo, obj = discover(gc)
            report["combo"] = combo
            if not combo:
                print("could not discover working combo on", gc, file=sys.stderr)
                continue
        else:
            rec, obj = try_geojson(gc, combo["layercodes"], combo["oprType"], combo["body"])
            if not (rec.get("ok") and obj):
                # layercodes can be per-village; re-discover for this one
                combo2, obj = discover(gc)
                if not (combo2 and obj):
                    report["villages"].append({"gis": gc, "village": vil, "features": 0})
                    continue
        obj = reproject_fc(obj)
        feats = normalize(obj, gc, vil, combo)
        all_feats.extend(feats)
        report["villages"].append({"gis": gc, "village": vil, "features": len(feats)})
        print(f"village {gc} {vil}: {len(feats)} polygons")
        time.sleep(SLEEP)

    if not all_feats:
        print("no polygons fetched — aborting write (existing data untouched)", file=sys.stderr)
        write_json(PROBE_OUT, report)
        sys.exit(1)

    fc = {"type": "FeatureCollection",
          "meta": {"source": "UP Bhu-Naksha getGeoJSONLayerData",
                   "geometry_method": "vector_api", "combo": combo,
                   "villages": len(report["villages"]), "parcels": len(all_feats),
                   "fetched_at": time.strftime("%Y-%m-%d")},
          "features": all_feats}
    write_json(OUT, fc)
    write_json(PROBE_OUT, report)
    print(f"DONE: {len(all_feats)} parcels across {len(report['villages'])} villages -> {OUT}")


if __name__ == "__main__":
    main()
