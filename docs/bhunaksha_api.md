# Bhu-Naksha (UP) — real API map

How **upbhunaksha.gov.in** actually fetches cadastral data, reverse-engineered from its
Angular bundle (`main-*.js`, 5.17 MB) by `tools/probe_bhunaksha_frontend.py`. Raw extract:
`_probe/bhunaksha_frontend.json`.

## TL;DR — the one that matters
Real plot **geometry is available as direct GeoJSON** (vector polygons), not just a bbox and
not only the rendered raster we currently trace in `fetch_bhunaksha_geom.py`:

```
POST  https://upbhunaksha.gov.in/bhunakshaserver/mapModificationController/getGeoJSONLayerData
      body: { giscode, layercodes, oprType }     (cookies required; responseType: text → GeoJSON)
```

If this returns true tessellating boundaries, it **replaces the raster→vector tracing pipeline**
(Phase 7) with a direct download. Validate first (see "Open questions").

## Base URLs
From the bundle's environment object `zi`, and crucially the HTTP service sets
`this.baseUrl = zi.apiUrl`:

```
apiUrl  (=> service baseUrl) : https://upbhunaksha.gov.in/bhunakshaserver
site baseUrl                 : https://upbhunaksha.gov.in
```

So every `${baseUrl}/…` below is under **`/bhunakshaserver`**.

## Geometry (vector / GeoJSON)
| Purpose | Method | Path | Body |
|---|---|---|---|
| Plot polygons (GeoJSON) | POST | `/mapModificationController/getGeoJSONLayerData` | `{ giscode, layercodes, oprType }` |
| Temp/edit-session polygons | POST | `/mapModificationController/getGeoJSONTempLayerData` | `{ giscode, layercodes, divId }` |

Both `withCredentials: true`, `responseType: "text"` (response is GeoJSON serialized as text).

## Layer codes (you need these for the call above — they're dynamic, per village)
| Purpose | Method | Path | Body |
|---|---|---|---|
| All layers for a giscode | POST | `/Layers/getLayers` | `{ layerType: "TABLE_LAYER_MASTER", giscode }` |
| Derived layers | POST | `/Layers/getLayers` | `{ layerType: "TABLE_DERIVED_LAYERS" }` |
| Generic | POST | `/Layers/getLayers` | `{ layerType }` |

`layercodes` are **not hardcoded** in the bundle — you fetch them here per village, then pass
them into `getGeoJSONLayerData`.

## giscode resolution + admin hierarchy
| Purpose | Method | Path | Notes |
|---|---|---|---|
| Level labels | GET | `/Levels/levelLabels` | state→district→tehsil→village labels |
| Level values | POST | `/masterdata/levelvalue` | `{ level, codes }` — walk the tree |
| giscode from levels | POST | `/Levels/getGisCodeFromLevels?gisLevels=<…>` | returns giscode (text) |
| Village extent / georef | POST | `/MapInfo/getVVVVExtentGeoref` | `{ gisLevels }` → bbox to frame the map |

## Plot lookup / attributes
| Purpose | Method | Path | Body |
|---|---|---|---|
| Click point → plot | POST | `/MapInfo/getPlotAtXY` | `{ giscode, x, y, plotno }` → `{ id, kide, … }` |
| By plot number | POST | `/MapInfo/getPlotByPlotNo` | `{ giscode, plotno }` |
| Plot info | POST | `/MapInfo/getPlotInfo` | `{ gisCode, plotNo }` (text) |
| By plot id | POST | `/v1/khasramap/plot` | params `{ bhucode, id }` |
| Plot report (image) | GET | `/api/plots?gisCode=..&plotNo=..` | → `{ imageBase64, scale }` |

## WMS raster (geoserver) — basemap only, not the vector source
| Purpose | URL | Key params |
|---|---|---|
| Derived-layer overlay | `/WMS` | `LAYERS=DERIVED_LAYER, gis_code, layercodes, plotId` |
| Village tiles | `/WMS/tile` | `LAYERS=VILLAGE_MAP, gis_code, STYLES=VILLAGE_MAP` |
| Transparent tiles | `/WMS/tile` | `STYLES=VILLAGE_MAP_TRANSPARENT` |

Standard OpenLayers WMS params: `REQUEST=GetMap, SERVICE=WMS, FORMAT=image/png, TRANSPARENT=TRUE`,
plus `BBOX`/`CRS`. GetFeatureInfo uses `QUERY_LAYERS` + `INFO_FORMAT=application/json`.
`serverType: "geoserver"` ⇒ the backend is GeoServer (so WFS may also be reachable — untested).

## Shape import/edit (admin side, for reference)
`/shape/isVillageImported {gisLevels}` · `/shape/importVillage {geoJson,crs,parcelId,gisLevels}` ·
`/shape/deleteVillage`.

## End-to-end recipe (one village → real polygons)
1. Resolve `giscode` — `Levels/getGisCodeFromLevels?gisLevels=<state.district.tehsil.village>`.
2. Get `layercodes` — `Layers/getLayers {layerType:"TABLE_LAYER_MASTER", giscode}`.
3. Fetch geometry — `POST mapModificationController/getGeoJSONLayerData {giscode, layercodes, oprType}`.
4. (Optional) extent `MapInfo/getVVVVExtentGeoref`; attrs `MapInfo/getPlotInfo`; image `api/plots`.

## Caveats
- **Session required.** The geometry calls send cookies (`withCredentials`). Establish a session
  first: `POST /auth/login` → `GET /session/validate`. Anonymous calls may 401/empty.
- **CRS.** Confirm the GeoJSON CRS (likely EPSG:4326 from GeoServer, but the import path mentions
  UTM/`crs`); reproject to EPSG:4326 on ingest to match `web/data/*`.
- **Politeness.** Public record, but a govt server: rate-limit, cache, back off, run from Actions
  (matches the repo's egress model).

## Open questions to validate (do these before scaling)
1. Does `getGeoJSONLayerData` return **true tessellating parcel boundaries** (not bboxes)? If yes,
   it supersedes `fetch_bhunaksha_geom.py`'s raster tracing.
2. What `oprType` value does the live app send? (grep the bundle around the `getGeoJSONLayerData`
   caller for the argument.)
3. Is a logged-in session strictly required, or do read-only calls work anonymously?
4. Same endpoint shape on **other states'** NIC Bhu-Naksha portals (Rajasthan, some Haryana)? If so,
   one adapter parameterized by base URL covers most of NCR (see `docs/ncr_rollout.md`).
