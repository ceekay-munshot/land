# Standardizing parcels + filling all of Delhi NCR

Goal: turn the one-village UP proof into a **repeatable standard** and extend it across the
whole National Capital Region. The single most important fact up front:

## ⚠️ NCR is multi-state — one scraper does NOT cover it
"Delhi NCR" = ~24 districts across **four** different land-records systems:

| Jurisdiction | NCR districts (approx.) | Portal / system | Reuse of our UP work |
|---|---|---|---|
| **Uttar Pradesh** ✅ | Gautam Buddh Nagar, Ghaziabad, Bulandshahr, Baghpat, Hapur, Meerut, Muzaffarnagar, Shamli | `upbhunaksha.gov.in` (NIC Bhu-Naksha) | **Direct** — this is what we cracked |
| **Haryana** | Gurugram, Faridabad, Sonipat, Rohtak, Jhajjar, Panipat, Palwal, Rewari, Mahendragarh, Bhiwani, Charkhi Dadri, Nuh, Karnal, Jind | Jamabandi / HALRIS (`jamabandi.nic.in`) | **Partial** — NIC-family; new base URL + adapter |
| **Rajasthan** | Alwar, Bharatpur | `bhunaksha.rajasthan.gov.in` (NIC Bhu-Naksha) | **High** — same software, mostly config |
| **Delhi (NCT)** | 11 districts | DLR / Bhu-abhilekh (separate) | **Low** — different system, likely manual/API-specific |

Leverage: **UP + Rajasthan (+ several Haryana districts) run the same NIC "Bhu-Naksha" software**,
so the endpoint flow in `bhunaksha_api.md` transfers with just a different base URL and root level
codes. Delhi is the outlier.

## The standard (three contracts)

### 1. Parcel schema v1 (the data standard)
Extend today's `web/data/gbn_parcels.geojson` props with admin hierarchy + fixed conventions.
Current: `plot_no, uid, khata_no, area_ha, owner_count, village, gis_code, source`.

Standard (superset, all parcels everywhere):
```jsonc
{
  "uid":        "<state>.<district>.<tehsil>.<village>.<plot_no>",  // globally unique, stable
  "state":      "UP", "district": "Gautam Buddh Nagar", "tehsil": "Jewar",
  "village":    "अनवर गढ खादर", "village_code": "…",
  "plot_no":    "53", "khata_no": "00020",
  "area_ha":    0.119, "owner_count": 4,
  "gis_code":   "14100744120363",
  "source":     "UP Bhu-Naksha", "fetched_at": "2026-06-24",
  "geometry_method": "vector_api"          // vs "raster_trace" / "bbox"
}
```
Geometry: **GeoJSON Polygon/MultiPolygon in EPSG:4326** (reproject on ingest). One file per
district (not one giant file — see §3).

### 2. Fetcher interface (the code standard)
One client, parameterized by portal, implementing the 4-step recipe from `bhunaksha_api.md`:
```
BhuNakshaClient(base_url, root_levels)
  .login() / .session()                       # cookie
  .resolve_giscode(level_path) -> giscode
  .list_layercodes(giscode)    -> [codes]
  .get_geojson(giscode, codes) -> FeatureCollection (raw CRS)
  .normalize(fc, admin) -> FeatureCollection  # schema v1, EPSG:4326
```
- `tools/bhunaksha_client.py` — shared client (UP, Rajasthan, NIC-Haryana reuse it).
- `tools/portals.py` — registry: each NCR district → `{portal, base_url, root_levels}`.
- Haryana-Jamabandi and Delhi-DLR get their own adapter classes behind the **same interface**, so
  the batch driver and schema stay identical.

### 3. Serving at scale (the delivery standard)
NCR is **millions of parcels** — you cannot ship one GeoJSON to the browser.
- Per-district files: `web/data/parcels/<state>/<district>.geojson` (or `.pmtiles`).
- Build **vector tiles** (`tippecanoe` → PMTiles), host on Cloudflare (you already deploy `web/`).
- `web/app.js`: lazy-load by viewport / zoom instead of loading everything.

## What to do next (ordered)

**Step 0 — VALIDATE the vector endpoint (do this first, ~1 task).**
Add a probe that logs in and calls `getGeoJSONLayerData` for one known GBN village
(reuse a `gis_code` already in `gbn_parcels.geojson`). Confirm it returns **true polygons**, find
the real `oprType`, and confirm whether a session is required. Run on Actions (egress).
→ If it works, it **replaces** the Phase-7 raster tracing. If not, keep tracing; the rest still holds.

**Step 1 — Lock the standard.** Land schema v1 + `bhunaksha_client.py` + `portals.py`; migrate the
existing GBN fetch onto it (backward-compatible — same props plus the new fields).

**Step 2 — Enumerate UP-NCR.** Crawl `Levels`/`masterdata` to list every village `giscode` for the
8 UP-NCR districts; cache a `giscode` catalog (`data_src/giscodes_up.json`, gitignored).

**Step 3 — Batch-fetch UP-NCR.** Actions matrix over districts → per-district GeoJSON, rate-limited,
**resumable** (skip villages already fetched), nightly/weekly refresh.

**Step 4 — Serve at scale.** Tile + lazy-load so the map stays fast with millions of parcels.

**Step 5 — Other states.**
- **Rajasthan (Alwar, Bharatpur):** point `portals.py` at `bhunaksha.rajasthan.gov.in`, adjust root
  levels — likely works with little new code.
- **Haryana:** build the Jamabandi/HALRIS adapter (different endpoints, same interface).
- **Delhi (NCT):** separate DLR system — scope a dedicated adapter or manual ingest.

## Cross-cutting concerns
- **Sessions/cookies & captchas** per portal (UP needs a session; others may add captcha).
- **Politeness & legality:** public cadastral records, but govt servers — rate-limit, backoff,
  cache raw responses, run off-peak from Actions; keep `source`/`fetched_at` provenance on every parcel.
- **Idempotency:** store raw GeoJSON (`data_src/`, gitignored) + normalized (`web/data/`), so refreshes
  diff cleanly.
- **CRS discipline:** normalize everything to EPSG:4326; keep original CRS in raw.

## Reality check on scope
Filling *all* of NCR with *correct* data is a multi-week effort dominated by (a) the Haryana +
Delhi adapters and (b) the enumerate/fetch/serve scale work — not by the UP endpoint, which is
now solved. The fastest credible milestone is **all 8 UP-NCR districts** via Steps 0–4, then add
Rajasthan (cheap), then Haryana, then Delhi.
