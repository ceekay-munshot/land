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
# from the repo root
python3 -m http.server 8000
# then open http://localhost:8000/web/
```
A static server is needed so the browser can fetch the GeoJSON in `data/`.

## 🗺️ What's on the map
- **India outline** → auto-flies to **Gautam Buddh Nagar** (3 tehsils: Dadri, Sadar, **Jewar**).
- Tehsils coloured by a **mock growth score**; click one for its 6 / 12 / 24-month band + driver.
- **Catalyst pins** (airport, Yamuna E-way, YEIDA, Noida / Gr. Noida) — approximate placeholders.

## 🧱 Roadmap
| Phase | What | Egress |
|---|---|---|
| **0 ✅** | Map + tehsils + catalyst pins + colour mechanism | none |
| 1 | ESA WorldCover vacant-land grid + circle-rate price floor | low |
| 2 | Real parcels (Bhu-Naksha WMS → GeoJSON, UP code 09) | India |
| 3 | Catalyst ingestion (YEIDA / Bhoomi Rashi / eGazette) + geocoding | India |
| 4 | Scoring engine → real colour + confidence bands | — |
| 5 | Claude routines (refresh / alerts) + CRM owner-join | India |

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
data/     geojson (boundaries, GBN tehsils, catalysts)
web/      the map app (MapLibre GL — no build step)
scripts/  extract_gbn.py — rebuilds data/gbn_tehsils.geojson
```
