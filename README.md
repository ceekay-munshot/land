# 🏗️ LAND — NCR Land Intelligence

A personal decision tool to find **where to buy land before the market prices it in.**
Zoomable map → land parcels → live development signals → 🟢🟠🔴 growth scoring → buy shortlist.

**Pilot:** Gautam Buddh Nagar, UP (Noida / Greater Noida / **Jewar — Noida Int'l Airport**).

---

## ⚠️ Status — Phase 0 (visual skeleton)
The map, zoom, parcels-by-tehsil, catalyst pins, and the 🟢🟠🔴 colour mechanism are live —
but **the scores and catalyst coordinates are honest placeholders** to prove the UX.
Real data arrives in Phases 1–4.

## ▶️ Run it
```bash
python3 -m http.server 8000 --directory web
# then open http://localhost:8000/
```
The **`web/` folder is fully self-contained** (app + `web/data/` GeoJSON), so you can host that
folder as-is on any static host — **Cloudflare Pages/Workers, GitHub Pages, Netlify…** Point the
deploy's root / output directory at `web/`.

## 🗺️ What's on the map
- **India home view** → auto-flies to **Gautam Buddh Nagar** (3 tehsils: Dadri, Sadar, **Jewar**).
- Tehsils coloured by a **mock growth score**; click one for its 6 / 12 / 24-month band + driver.
- **Catalyst pins** (airport, Yamuna E-way, YEIDA, Noida / Gr. Noida) — approximate placeholders.
- **🟢 Live YEIDA Schemes panel** — current plot-allotment schemes (residential / industrial /
  institutional / commercial) pulled **weekly** from the YEIDA portal, with scheme codes, deadlines
  & apply links. First live development signal on the map.

## 🧱 Roadmap
| Phase | What | Egress |
|---|---|---|
| **0 ✅** | Map + tehsils + catalyst layer | none |
| **2 ✅** | Real parcels (Bhu-Naksha, auto-batcher) + owners/area | Actions |
| **1 ✅** | Circle-rate price floor joined onto parcels | manual + Actions |
| **3 ✅** | Real catalyst geometry (airport + expressways, OSM) + per-parcel distance | Actions |
| **3b 🟢** | **Live YEIDA schemes** — portal scraped weekly via Firecrawl (stealth + India proxy); Bhoomi Rashi / eGazette next | Actions + Firecrawl |
| **4 ✅ v1** | Growth score → real parcel colours | — |
| **5 ✅** | **Parcel explorer** — search (gata/khata/owner), click-to-highlight, on-map gata labels, detail drawer, satellite toggle, URL permalinks, mobile sheets | — |
| **6 🟢** | **Ownership history (chain-of-title)** — per-gata timeline of how land changed hands. Reconstructed seed shipped (synthetic, clearly labelled — `tools/gen_nalgadha_history.py`); real deeds scaffolded via IGRSUP `newPropertySearchAction` (`tools/fetch_igrsup_deeds.py` + Actions, pending deed parser + captcha) | Actions |
| 7 | Claude routines (refresh / alerts) + CRM owner-join | India |

## 🧠 Growth score (Phase 4 v1)
Every parcel gets a transparent **heuristic** score (0–100), coloured 🟢🟠🔴:
- **65 % airport proximity** — distance-decay from Noida Int'l Airport (Jewar), → 0 at ~40 km
- **35 % price headroom** — cheaper than the area's circle-rate range = more room to appreciate near the catalyst

It is **not** a statistical probability — it's a weighted heuristic over *real* signals, shown honestly, and it sharpens as more signals (Phase 3b notifications, transaction history) are added. Computed client-side in `web/app.js`.

## 📡 Data sources (free-first)
Boundaries `datta07/INDIAN-SHAPEFILES` · parcels Bhu-Naksha (NIC) · vacant land ESA WorldCover +
Sentinel-2 (AWS Open Data) · prices state circle / DLC rates + RBI HPI · signals YEIDA / GNIDA,
Bhoomi Rashi, eGazette, UP-RERA · infra OpenStreetMap.

## 🔌 Egress model (Firecrawl-first hybrid)
Govt portals geo-fence foreign IPs and the build sandbox is allowlisted, so fetching routes through:
**GitHub Actions** (unrestricted egress) **+ Firecrawl** (India proxy) for automation ·
**manual pulls** for captcha / MoU-gated files · **Claude routines** on the timer.

## 📁 Layout
```
web/            deployable site (self-contained)
  index.html  app.js  style.css
  data/         geojson the app loads (boundaries, GBN tehsils, catalysts)
data_src/       large raw source (gitignored; re-downloaded by the script)
scripts/        extract_gbn.py — rebuilds web/data/gbn_tehsils.geojson
```
