#!/usr/bin/env python3
"""Extract Gautam Buddh Nagar tehsils from the UP sub-district GeoJSON and
attach Phase-0 PLACEHOLDER growth scores, so the map can demo the
green/orange/red mechanism end-to-end.

The scores below are MOCK. Real scores come from the Phase-4 scoring engine
(distance-decay to catalysts x land-use-change likelihood x rate momentum ...).

Input : data_src/up_subdistricts.geojson   (large raw source, gitignored)
Output: web/data/gbn_tehsils.geojson        (small, served by the app)
"""
import json
import os
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "data_src", "up_subdistricts.geojson")
SRC_URL = (
    "https://raw.githubusercontent.com/datta07/INDIAN-SHAPEFILES/"
    "master/STATES/UTTAR%20PRADESH/UTTAR%20PRADESH_SUBDISTRICTS.geojson"
)
OUT = os.path.join(ROOT, "web", "data", "gbn_tehsils.geojson")

# Phase-0 placeholders ONLY. Jewar = Noida Int'l Airport core = hottest.
MOCK = {
    "Jewar": {
        "score": 82, "band_6m": "+8-14%", "band_12m": "+18-30%", "band_24m": "+40-70%",
        "driver": "Noida Int'l Airport (Jewar) + YEIDA aerotropolis",
    },
    "Gautam Buddha Nagar": {
        "score": 67, "band_6m": "+4-8%", "band_12m": "+10-18%", "band_24m": "+22-38%",
        "driver": "Noida / Greater Noida sprawl + expressway grid",
    },
    "Dadri": {
        "score": 54, "band_6m": "+3-6%", "band_12m": "+7-13%", "band_24m": "+15-26%",
        "driver": "New Noida (DNGIR) spillover - early stage",
    },
}


def main():
    if not os.path.exists(SRC):
        print("source missing -> downloading UP sub-districts (~29MB) ...")
        os.makedirs(os.path.dirname(SRC), exist_ok=True)
        urllib.request.urlretrieve(SRC_URL, SRC)

    with open(SRC) as fh:
        gj = json.load(fh)

    feats = []
    for ft in gj["features"]:
        p = ft.get("properties", {})
        if str(p.get("dtname", "")).strip().lower() != "gautam buddha nagar":
            continue
        name = p.get("sdtname")
        m = MOCK.get(name, {"score": 50, "band_6m": "n/a", "band_12m": "n/a",
                            "band_24m": "n/a", "driver": "n/a"})
        ft["properties"] = {
            "tehsil": name,
            "district": "Gautam Buddha Nagar",
            "state": "Uttar Pradesh",
            "lgd_code": p.get("Subdt_LGD"),
            # --- PLACEHOLDER (mock) Phase-0 values ---
            "mock_score": m["score"],
            "mock_band_6m": m["band_6m"],
            "mock_band_12m": m["band_12m"],
            "mock_band_24m": m["band_24m"],
            "mock_driver": m["driver"],
            "is_placeholder": True,
        }
        feats.append(ft)

    out = {"type": "FeatureCollection", "features": feats}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh)
    print(f"wrote {len(feats)} tehsils -> {OUT}")


if __name__ == "__main__":
    main()
