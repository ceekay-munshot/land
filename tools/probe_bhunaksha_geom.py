#!/usr/bin/env python3
"""Pull the CODE CONTEXT around Bhu-Naksha's geometry calls so we get the real GeoServer URL,
layer/typeName, and how getPlotByPlotNo / WFS are called. Writes _probe/bhunaksha_geom.json.
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

TERMS = ["geoserver", "getPlotByPlotNo", "getPlotAtXY", "wfs", "typeName", "GetFeature",
         "outputFormat", "getFeatureInfoUrl", "cql", "CQL", "workspace", "getMapInternal",
         "service=", "layers", "bhucode"]


def get(u):
    for i in range(4):
        try:
            return s.get(u, timeout=60)
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


out = {"contexts": {}}
try:
    html = get(HOME).text
    jsfiles = set(re.findall(r'src=["\']([^"\']+\.js)["\']', html))
    out["js_found"] = sorted(jsfiles)
    for j in sorted(jsfiles):
        url = j if j.startswith("http") else HOME.rstrip("/") + "/" + j.lstrip("/")
        r = get(url)
        if not r or r.status_code != 200:
            continue
        t = r.text
        for term in TERMS:
            for m in re.finditer(re.escape(term), t):
                a, b = max(0, m.start() - 100), min(len(t), m.end() + 100)
                ctxs = out["contexts"].setdefault(term, [])
                snip = t[a:b].replace("\n", " ")
                if snip not in ctxs and len(ctxs) < 6:
                    ctxs.append(snip)
except Exception as e:
    out["fatal_error"] = repr(e)[:300]

os.makedirs("_probe", exist_ok=True)
json.dump(out, open("_probe/bhunaksha_geom.json", "w"), ensure_ascii=False, indent=2)
for term, ctxs in out.get("contexts", {}).items():
    print("==", term, "==")
    for c in ctxs[:4]:
        print("   ...", c, "...")
print("fatal_error:", out.get("fatal_error"))
