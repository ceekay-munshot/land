// LAND — Phase 5 map. The data is placeholder; the mechanism is real.
const NCR_BOUNDS = [[76.65, 27.55], [78.05, 28.95]]; // Delhi-NCR down to Jewar — the working area
const GBN_BOUNDS = [[77.28, 28.02], [77.88, 28.66]]; // approx GBN bbox
let parcelBounds = null;
let nalgadhaBounds = null;
let airportCentroid = null;
let locatedSchemes = [];   // YEIDA schemes we could place (pins + parcel proximity)
const schemePins = {};     // scheme code -> { lngLat, open() } (panel <-> map linking)
const SQFT = 10.7639;      // 1 m² in sq ft — plot rates/sizes shown in sq ft (familiar unit)
const sqft = (m2) => Math.round(m2 * SQFT).toLocaleString('en-IN');
const ratePsf = (psm) => Math.round(psm / SQFT).toLocaleString('en-IN');

// ---- Georeference calibration (align cadastre to satellite) --------------
// The Bhu-Naksha cadastre is internally consistent but its absolute position can
// drift a few metres (and sometimes rotate) from satellite imagery. CALIB holds a
// per-dataset offset in METRES (east dx, north dy) + a rotation in DEGREES, applied
// live about the dataset's own centre. Tuned from the Layers ▸ "Align to satellite"
// control, persisted to localStorage, and seedable via URL (?nudge=E,N for both, or
// ?nudge_p / ?nudge_n per dataset). Default 0 = the data is shown exactly as fetched.
const CALIB = { parcels: { dx: 0, dy: 0, rot: 0 }, nalgadha: { dx: 0, dy: 0, rot: 0 } };
const origGeo = {};        // src -> pristine FeatureCollection (never mutated)
const srcCentroid = {};    // src -> [lng,lat] rotation pivot (dataset centre)
(function initCalib() {
  const q = new URLSearchParams(location.search);
  const parse = (s) => { const m = (s || '').split(',').map(Number); return (m.length === 2 && m.every((n) => !isNaN(n))) ? m : null; };
  const all = parse(q.get('nudge'));
  if (all) { CALIB.parcels.dx = all[0]; CALIB.parcels.dy = all[1]; CALIB.nalgadha.dx = all[0]; CALIB.nalgadha.dy = all[1]; }
  const p = parse(q.get('nudge_p')); if (p) { CALIB.parcels.dx = p[0]; CALIB.parcels.dy = p[1]; }
  const n = parse(q.get('nudge_n')); if (n) { CALIB.nalgadha.dx = n[0]; CALIB.nalgadha.dy = n[1]; }
  try {
    const ls = JSON.parse(localStorage.getItem('land_calib') || 'null');
    if (ls) { if (ls.parcels) Object.assign(CALIB.parcels, ls.parcels); if (ls.nalgadha) Object.assign(CALIB.nalgadha, ls.nalgadha); }
  } catch (e) { /* localStorage unavailable */ }
})();
const calibActive = (c) => c && (c.dx || c.dy || c.rot);
// Build a transformed copy of a source (rotate about its centre, then offset).
function transformGeo(src) {
  const orig = origGeo[src], c = srcCentroid[src], cal = CALIB[src];
  if (!orig || !c) return null;
  const lat0 = c[1] * Math.PI / 180;
  const mLng = 111320 * Math.cos(lat0), mLat = 110540;
  const th = (cal.rot || 0) * Math.PI / 180, cs = Math.cos(th), sn = Math.sin(th);
  const tx = (lng, lat) => {
    const ex = (lng - c[0]) * mLng, ny = (lat - c[1]) * mLat;
    const rx = ex * cs - ny * sn, ry = ex * sn + ny * cs;
    return [c[0] + (rx + cal.dx) / mLng, c[1] + (ry + cal.dy) / mLat];
  };
  const walk = (co) => (typeof co[0] === 'number' ? tx(co[0], co[1]) : co.map(walk));
  return { type: 'FeatureCollection', features: orig.features.map((f) => ({
    type: 'Feature', properties: f.properties,
    geometry: f.geometry ? { type: f.geometry.type, coordinates: walk(f.geometry.coordinates) } : null })) };
}
function applyCalibration(src) {
  for (const s of (src ? [src] : ['parcels', 'nalgadha'])) {
    const source = map.getSource && map.getSource(s);
    if (!source || !origGeo[s]) continue;
    source.setData(calibActive(CALIB[s]) ? (transformGeo(s) || origGeo[s]) : origGeo[s]);
  }
}

// ---- Area selector model (built at runtime from the loaded datasets) -----
const GROUP_ORDER = ['Overview', 'Tehsils', 'Jewar — live parcels', 'Ownership history'];
const AREAS = [];          // { group, label, sub, bounds | ()=>bounds, opts }
// axis-aligned bounds [minLng,minLat,maxLng,maxLat] for any GeoJSON geometry
function geomBounds(geometry, b) {
  b = b || [Infinity, Infinity, -Infinity, -Infinity];
  const walk = (c) => {
    if (typeof c[0] === 'number') {
      if (c[0] < b[0]) b[0] = c[0]; if (c[1] < b[1]) b[1] = c[1];
      if (c[0] > b[2]) b[2] = c[0]; if (c[1] > b[3]) b[3] = c[1];
    } else c.forEach(walk);
  };
  if (geometry && geometry.coordinates) walk(geometry.coordinates);
  return b;
}
// per-village bounds, skipping out-of-region junk coords (some centroids are [0, 76.5])
function villageBoundsMap(features) {
  const m = {};
  for (const ft of features) {
    const v = ft.properties && ft.properties.village; if (!v) continue;
    const ring = ft.geometry && ft.geometry.coordinates && ft.geometry.coordinates[0]; if (!ring) continue;
    for (const c of ring) {
      const lng = c[0], lat = c[1];
      if (!(lng > 76 && lng < 79 && lat > 27 && lat < 30)) continue;
      const b = m[v] || (m[v] = [Infinity, Infinity, -Infinity, -Infinity]);
      if (lng < b[0]) b[0] = lng; if (lat < b[1]) b[1] = lat;
      if (lng > b[2]) b[2] = lng; if (lat > b[3]) b[3] = lat;
    }
  }
  return m;
}
const validB = (b) => b && b.every((n) => isFinite(n)) && b[2] > b[0] && b[3] > b[1];
const asLngLatBounds = (b) => [[b[0], b[1]], [b[2], b[3]]];

const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    // glyphs are needed for the on-map gata-number labels (symbol layers).
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources: {
      osm: {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenStreetMap contributors'
      }
    },
    layers: [{ id: 'osm', type: 'raster', source: 'osm' }]
  },
  bounds: NCR_BOUNDS,
  fitBoundsOptions: { padding: 20 },
  maxBounds: [[76.2, 27.1], [78.6, 29.4]], // lock to the NCR/GBN region — no empty world map
  minZoom: 8,
  maxZoom: 18
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');

// ---- Single shared popup -------------------------------------------------
// Every feature and pin reuses ONE popup instance, so clicking around the map
// can never stack overlapping cards. Parcels & gatas are drawn *on top of* the
// broad tehsil fill, so one click lands on several layers at once — a singleton
// popup means the last (most specific) layer wins and only one card is shown.
const infoPopup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: '320px' });

function showPopup(lngLat, html, maxWidth = '320px', offset = 0) {
  infoPopup.setOffset(offset).setMaxWidth(maxWidth).setLngLat(lngLat).setHTML(html);
  if (!infoPopup.isOpen()) infoPopup.addTo(map);   // reuse if already open (no re-stacking)
}

// rough centroid = mean of the first ring's vertices (good enough for a label)
function polygonCentroid(geometry) {
  let ring;
  if (!geometry) return null;
  if (geometry.type === 'Polygon') ring = geometry.coordinates[0];
  else if (geometry.type === 'MultiPolygon') ring = geometry.coordinates[0][0];
  else return null;
  let x = 0, y = 0;
  for (const [lng, lat] of ring) { x += lng; y += lat; }
  return [x / ring.length, y / ring.length];
}

// great-circle distance in km between two [lng, lat] points
function haversineKm(a, b) {
  const R = 6371, t = Math.PI / 180;
  const dLat = (b[1] - a[1]) * t, dLon = (b[0] - a[0]) * t;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * t) * Math.cos(b[1] * t) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

const scoreColor = (s) => (s >= 70 ? '#2ecc71' : s >= 45 ? '#f39c12' : '#e74c3c');

// ---- Shared formatters / geometry (module scope so popup, drawer & search reuse them) ----
const normV = (s) => (s || '').replace(/\s+/g, '');
const inr = (v) => (v >= 1e7 ? '₹' + (v / 1e7).toFixed(2) + ' Cr'
                  : v >= 1e5 ? '₹' + (v / 1e5).toFixed(1) + ' L' : '₹' + Math.round(v).toLocaleString('en-IN'));
const featCentroid = (ft) => {
  const ring = ft.geometry.coordinates[0];
  let x = 0, y = 0; for (const c of ring) { x += c[0]; y += c[1]; }
  return [x / ring.length, y / ring.length];
};
const ngEsc = (t) => (t == null ? '' : String(t)).replace(/[&<>"]/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// Stable per-gata identity across villages: gata numbers repeat in every village,
// so owner/history records key on village+plot_no (uid), not plot_no alone.
const uidOf = (p) => p.uid || ((p.village || '').trim() + '|' + p.plot_no);

// ---- Shared state across loaders + UI ----
let rates = {};               // village -> circle-rate row
let nalgadhaOwners = {};       // uid (village|plot_no) -> [owner names]
let nalgadhaHistory = {};      // uid (village|plot_no) -> { events: [...] }  (reconstructed chain-of-title)
const searchIndex = [];        // { source, id, khata, village, owners, centroid, feature, hay }
let selected = { source: null, id: null };

// ---- Selected-parcel highlight (bright outline that persists after the popup) ----
// match on uid where present (gata numbers repeat across villages), else fall back to plot_no
const SELECT_KEY = ['coalesce', ['get', 'uid'], ['get', 'plot_no']];

// Cadastre colouring. Once real polygon geometry exists, a build step (tools/add_cidx.py)
// tags each parcel with a graph-colour index `cidx` so adjacent parcels are coloured
// differently (a proper cadastre look). Until then there is no `cidx` and we fall back to
// the existing thematic colour/opacity — so this is safe to ship before the geometry lands.
const CIDX_PALETTE = ['match', ['get', 'cidx'],
  0, '#fdd8d8', 1, '#d8f5dd', 2, '#fff5d8', 3, '#d8ebff', 4, '#f0d8ff', 5, '#ffe8d8', '#e5e5e5'];
const cidxFill = (fallback) => ['case', ['has', 'cidx'], CIDX_PALETTE, fallback];
const ifCidx = (withCidx, without) => ['case', ['has', 'cidx'], withCidx, without];
// A feature has REAL traced geometry (vs an un-traced bbox box) when geometry_method
// is 'raster_vector'. Used to de-emphasise boxes and to drive the Clean-view toggle.
const IS_REAL = ['==', ['get', 'geometry_method'], 'raster_vector'];
const REAL_ONLY = IS_REAL;            // filter applied when placeholder boxes are hidden
let cleanView = true;                 // default: show only real surveyed plots (boxes hidden)
// Highlight filter for a source: the selected id, AND (when placeholders are hidden)
// only if it is a real traced plot — so selecting a hidden bbox box via search or a
// deep-link never draws a stray placeholder outline.
function highlightFilter(s) {
  const base = ['==', SELECT_KEY, (selected.source === s && selected.id) ? String(selected.id) : '__none__'];
  return cleanView ? ['all', REAL_ONLY, base] : base;
}
function refreshHighlights() {
  for (const s of ['nalgadha', 'parcels']) {
    const lyr = s + '-highlight';
    if (map.getLayer(lyr)) map.setFilter(lyr, highlightFilter(s));
  }
}
function selectFeature(source, id) {
  selected = { source, id: String(id) };
  refreshHighlights();
}
function clearSelection() {
  selected = { source: null, id: null };
  refreshHighlights();
  updateHash();
}

// ---- Popup builders (shared by the click handler and the bbox-tolerant tap path) ----
function tehsilPopupHTML(p) {
  return `
        <div class="pop">
          <h3>${p.tehsil} <small>tehsil</small></h3>
          <div class="badge" style="background:${scoreColor(+p.mock_score)}">
            Growth score ${p.mock_score}/100
          </div>
          <table>
            <tr><td>6 months</td><td>${p.mock_band_6m}</td></tr>
            <tr><td>12 months</td><td>${p.mock_band_12m}</td></tr>
            <tr><td>24 months</td><td>${p.mock_band_24m}</td></tr>
          </table>
          <div class="driver">▶ ${p.mock_driver}</div>
          <div class="mock">PLACEHOLDER · LGD ${p.lgd_code} · real scores in Phase 4</div>
        </div>`;
}

function airportPopupHTML(p) {
  return `<div class="pop"><h3>${p.name}</h3>
     <div class="ctype">${p.status || ''}</div>
     <div class="mock">real footprint · OpenStreetMap</div></div>`;
}

function parcelPopupHTML(p, feature) {
  let owners = p.owners; try { owners = JSON.parse(p.owners); } catch { /* */ }
  const r = rates[normV(p.village)];
  let priceRows = '';
  if (r && p.area_ha != null) {
    priceRows = `<tr><td>Circle value</td><td><b>${inr(p.area_ha * r.general)}</b></td></tr>`
              + `<tr><td>Rate (general)</td><td>${inr(r.general)}/ha</td></tr>`;
  }
  const distRow = p.airport_km != null ? `<tr><td>✈ Airport</td><td>~${p.airport_km} km</td></tr>` : '';
  let schemeRow = '';
  if (locatedSchemes.length) {
    const cc = featCentroid(feature);
    let best = null, bd = Infinity;
    for (const s2 of locatedSchemes) { const d = haversineKm(cc, [s2.lng, s2.lat]); if (d < bd) { bd = d; best = s2; } }
    if (best) schemeRow = `<tr><td>◆ Live scheme</td><td>${best.code || best.title} · ${bd.toFixed(1)} km</td></tr>`;
  }
  const sc = p.score;
  const col = sc == null ? '#9ca3af' : sc >= 67 ? '#2ecc71' : sc >= 40 ? '#f39c12' : '#e74c3c';
  const band = sc == null ? '—' : sc >= 67 ? 'High 🟢' : sc >= 40 ? 'Medium 🟠' : 'Low 🔴';
  const scoreHdr = sc == null ? '' :
    `<div class="badge" style="background:${col}">Growth score ${sc}/100 · ${band}</div>`;
  return `
    <div class="pop">
      <h3>Plot ${p.plot_no} <small>${p.village || ''}</small></h3>
      ${scoreHdr}
      <table>
        <tr><td>Khata</td><td>${p.khata_no || '—'}</td></tr>
        <tr><td>Area</td><td>${p.area_ha != null ? p.area_ha + ' ha' : '—'}</td></tr>
        <tr><td>Owners</td><td>${Array.isArray(owners) ? owners.length : (p.owner_count ?? '—')}</td></tr>
        ${priceRows}
        ${distRow}
        ${schemeRow}
      </table>
      <div class="driver">score v1 = 65% airport proximity + 35% price headroom · heuristic, not a guarantee</div>
      <div class="mock">parcel: Bhu-Naksha · price: IGRSUP · catalyst: OSM</div>
    </div>`;
}

function nalgadhaPopupHTML(p) {
  const key = uidOf(p);
  const owners = nalgadhaOwners[key] || [];
  const events = (nalgadhaHistory[key] || {}).events || [];
  const transfers = events.filter((e) => TL_TYPE[e.type]).length;
  return `
    <div class="pop">
      <h3>Gata ${p.plot_no} <small>${ngEsc(p.village || 'Nalgadha')}</small></h3>
      <table>
        <tr><td>Khata</td><td>${p.khata_no || '—'}</td></tr>
        <tr><td>Area</td><td>${p.area_ha != null ? p.area_ha + ' ha' : '—'}</td></tr>
        <tr><td>Owners</td><td><b>${p.owner_count ?? '—'}</b></td></tr>
        ${transfers ? `<tr><td>Changed hands</td><td><b>${transfers}×</b></td></tr>` : ''}
      </table>
      ${owners.length ? `<div class="owners"><b>Owners</b><br>${owners.map(ngEsc).join('<br>')}</div>` : ''}
      <div class="mock">title reconstruction · UP Bhu-Naksha · details in side panel →</div>
    </div>`;
}

// ---- Detail drawer (full metadata + owners + ownership-history timeline) ----
function ownerListHTML(id) {
  const list = nalgadhaOwners[String(id)] || [];
  if (!list.length) return '';
  return `<div class="dsec"><h4>Owners <span>(${list.length})</span></h4>
    <ol class="owner-list">${list.map((o) => `<li>${ngEsc(o)}</li>`).join('')}</ol></div>`;
}

const TL_TYPE = { sale: 'Sale', gift: 'Gift', inheritance: 'Inheritance', partition: 'Partition' };
function timelineHTML(id) {
  const h = nalgadhaHistory[String(id)];
  const events = (h && h.events) || [];
  if (!events.length) return '';
  const evs = [...events].sort((a, b) => String(a.date).localeCompare(String(b.date))); // oldest → newest
  const transfers = evs.filter((e) => TL_TYPE[e.type]).length;
  const anyRecon = evs.some((e) => e.confidence !== 'registry');
  let prevVal = null;
  const nodes = evs.map((e) => {
    const from = (e.from || []).map(ngEsc).join(', ') || '—';
    const to = (e.to || []).map(ngEsc).join(', ') || '—';
    let money = '';
    if (e.consideration_inr != null && e.consideration_inr > 0) {
      let trend = '';
      if (prevVal != null && prevVal > 0)
        trend = e.consideration_inr > prevVal ? ' <span class="tl-up">▲</span>'
              : e.consideration_inr < prevVal ? ' <span class="tl-down">▼</span>' : '';
      money = `<span class="tl-val">${inr(e.consideration_inr)}${trend}</span>`;
      prevVal = e.consideration_inr;
    }
    const meta = [e.share ? 'Share ' + ngEsc(e.share) : '', money, e.deed_no ? ngEsc(e.deed_no) : '']
      .filter(Boolean).join(' · ');
    return `<li class="tl-event">
        <div class="tl-date">${ngEsc(e.date)} <span class="tl-type tl-${e.type}">${TL_TYPE[e.type] || e.type}</span></div>
        <div class="tl-parties">${from} <span class="tl-arrow">→</span> <b>${to}</b></div>
        ${meta ? `<div class="tl-meta">${meta}</div>` : ''}
      </li>`;
  }).join('');
  const span = `${ngEsc(evs[0].date)} → ${ngEsc(evs[evs.length - 1].date)}`;
  const banner = anyRecon
    ? `<div class="tl-banner">⚠ RECONSTRUCTED — synthetic chain-of-title for demonstration, <b>not</b> registry-verified. Prior-holder names are placeholders; only current owners are real.</div>`
    : '';
  return `<div class="dsec">
    <h4>Ownership history</h4>
    <div class="tl-summary">Changed hands <b>${transfers}</b> time${transfers === 1 ? '' : 's'} · ${span}</div>
    ${banner}
    <ol class="timeline">${nodes}</ol>
  </div>`;
}

function openDrawerFor(rec) {
  const body = document.getElementById('drawer-body');
  const drawer = document.getElementById('drawer');
  if (!body || !drawer) return;
  const p = rec.feature.properties;
  const isNg = rec.source === 'nalgadha';
  const label = (isNg ? 'Gata ' : 'Plot ') + p.plot_no;
  const village = p.village || (isNg ? 'नलगढ़ा' : '');
  let owners = p.owner_count;
  if (!isNg) { try { const o = JSON.parse(p.owners); if (Array.isArray(o)) owners = o.length; } catch { /* */ } }
  const rows = [];
  rows.push(['Khata', p.khata_no || '—']);
  rows.push(['Area', p.area_ha != null ? p.area_ha + ' ha' : '—']);
  rows.push(['Owners', owners != null ? owners : '—']);
  const r = rates[normV(p.village)];
  if (r && p.area_ha != null) {
    rows.push(['Circle value', '<b>' + inr(p.area_ha * r.general) + '</b>']);
    rows.push(['Rate (general)', inr(r.general) + '/ha']);
  }
  if (p.airport_km != null) rows.push(['✈ Airport', '~' + p.airport_km + ' km']);
  if (p.score != null) rows.push(['Growth score', p.score + '/100']);
  if (p.gis_code) rows.push(['GIS code', p.gis_code]);
  const metaTable = `<table class="dtable">${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>`;
  body.innerHTML = `
    <div class="dhead"><h3>${label}</h3>
      <div class="dsub">${ngEsc(village)}${p.source ? ' · ' + ngEsc(p.source) : ''}</div></div>
    <div class="dsec">${metaTable}</div>
    ${isNg ? ownerListHTML(uidOf(p)) : ''}
    ${isNg ? timelineHTML(uidOf(p)) : ''}
    <div class="dfoot">${isNg
      ? 'title reconstruction · UP Bhu-Naksha · history is reconstructed (synthetic)'
      : 'parcel: Bhu-Naksha · price: IGRSUP · catalyst: OSM'}</div>`;
  drawer.classList.remove('closed');
  drawer.setAttribute('aria-hidden', 'false');
}
function closeDrawer() {
  const drawer = document.getElementById('drawer');
  if (!drawer) return;
  drawer.classList.add('closed');
  drawer.setAttribute('aria-hidden', 'true');
}
function recFromFeature(source, feature) {
  const centroid = feature.geometry ? (polygonCentroid(feature.geometry) || featCentroid(feature)) : null;
  return { source, id: uidOf(feature.properties), feature, centroid };
}
function flyToFeature(rec) {
  if (rec.centroid) map.flyTo({ center: rec.centroid, zoom: 16, duration: 1200 });
  selectFeature(rec.source, rec.id);
  openDrawerFor(rec);
  updateHash();
}

// ---- One prioritised click handler for the whole map ----------------------
// Most-specific layer wins (gata > parcel > airport > tehsil). Parcels/gatas
// get a small bbox tolerance so tiny plots are tappable on touch screens. This
// is the single code path → exactly one popup + one selection per click.
function onParcelClick(source, feature, lngLat) {
  const p = feature.properties;
  showPopup(lngLat, source === 'nalgadha' ? nalgadhaPopupHTML(p) : parcelPopupHTML(p, feature),
            source === 'nalgadha' ? '280px' : '320px');
  const rec = recFromFeature(source, feature);
  selectFeature(source, rec.id);
  openDrawerFor(rec);
  updateHash();
}
function handleMapClick(e) {
  const tol = 8;
  const bbox = [[e.point.x - tol, e.point.y - tol], [e.point.x + tol, e.point.y + tol]];
  const q = (layer, box) => (map.getLayer(layer) ? map.queryRenderedFeatures(box, { layers: [layer] })[0] : null);
  const f = q('nalgadha-fill', bbox) || q('parcels-fill', bbox)
         || q('osm-airport', e.point) || q('gbn-fill', e.point);
  if (!f) { infoPopup.remove(); clearSelection(); closeDrawer(); return; }
  const id = f.layer.id;
  if (id === 'nalgadha-fill') onParcelClick('nalgadha', f, e.lngLat);
  else if (id === 'parcels-fill') onParcelClick('parcels', f, e.lngLat);
  else if (id === 'osm-airport') showPopup(e.lngLat, airportPopupHTML(f.properties), '260px');
  else if (id === 'gbn-fill') showPopup(e.lngLat, tehsilPopupHTML(f.properties), '300px');
}
map.on('click', handleMapClick);

// ---- URL permalink / deep-link (#zoom/lat/lng[/g<gata>|/p<plot>]) ----------
let hashTimer = null;
function updateHash() {
  clearTimeout(hashTimer);
  hashTimer = setTimeout(() => {
    const c = map.getCenter();
    let h = `#${map.getZoom().toFixed(2)}/${c.lat.toFixed(5)}/${c.lng.toFixed(5)}`;
    if (selected.source && selected.id)
      h += '/' + (selected.source === 'parcels' ? 'p' : 'g') + encodeURIComponent(selected.id);
    history.replaceState(null, '', h);
  }, 250);
}
function parseHash() {
  const h = location.hash.replace(/^#/, '');
  if (!h) return null;
  const parts = h.split('/');
  const out = {};
  if (parts.length >= 3 && parts[0] !== '' && !isNaN(parseFloat(parts[0]))) {
    out.zoom = parseFloat(parts[0]); out.lat = parseFloat(parts[1]); out.lng = parseFloat(parts[2]);
  }
  for (const part of parts) {
    const m = /^([gp])(.+)$/.exec(part);
    if (m) out.sel = { source: m[1] === 'p' ? 'parcels' : 'nalgadha', id: decodeURIComponent(m[2]) };
  }
  return out;
}
function restoreFromHash() {
  const hv = parseHash();
  if (!hv || (hv.lat == null && !hv.sel)) return false;
  if (hv.lat != null && !isNaN(hv.lat) && !isNaN(hv.lng)) map.jumpTo({ center: [hv.lng, hv.lat], zoom: hv.zoom });
  if (hv.sel) {
    const rec = searchIndex.find((r) => r.source === hv.sel.source && r.id === hv.sel.id);
    if (rec) {
      selectFeature(rec.source, rec.id);
      openDrawerFor(rec);
      if (hv.lat == null && rec.centroid) map.jumpTo({ center: rec.centroid, zoom: 16 });
    }
  }
  return true;
}
map.on('moveend', updateHash);

// ---- Parcel search (gata / khata / owner name) ----------------------------
function indexFeatures(source, features, ownersOf) {
  for (const ft of features) {
    const p = ft.properties;
    const owners = (ownersOf ? ownersOf(p) : []) || [];
    searchIndex.push({
      source, id: uidOf(p), plot_no: String(p.plot_no), khata: String(p.khata_no || ''),
      village: p.village || '', owners,
      centroid: polygonCentroid(ft.geometry) || featCentroid(ft),
      feature: ft,
      hay: [p.plot_no, p.khata_no, p.village, ...owners].join(' ').toLowerCase()
    });
  }
}
function searchParcels(query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return [];
  const digits = /^\d+$/.test(q);
  const hits = [];
  for (const rec of searchIndex) {
    let rank = null;
    if (digits) {
      const idn = rec.plot_no.replace(/^0+/, ''), khn = rec.khata.replace(/^0+/, '');
      if (rec.plot_no === q || idn === q) rank = 0;
      else if (rec.plot_no.startsWith(q)) rank = 1;
      else if (rec.khata === q || khn === q) rank = 2;
      else if (rec.khata.startsWith(q) || (khn && khn.startsWith(q))) rank = 3;
    } else {
      if (rec.owners.some((o) => o.toLowerCase().includes(q))) rank = 1;
      else if (rec.village.toLowerCase().includes(q)) rank = 2;
      else if (rec.hay.includes(q)) rank = 3;
    }
    if (rank != null) hits.push({ rec, rank });
  }
  // ties: Nalgadha (the showcase, has owner + history data) ranks above GBN parcels
  const srcRank = (s) => (s === 'nalgadha' ? 0 : 1);
  hits.sort((a, b) => a.rank - b.rank || srcRank(a.rec.source) - srcRank(b.rec.source)
    || a.rec.plot_no.localeCompare(b.rec.plot_no, undefined, { numeric: true }));
  return hits.slice(0, 8).map((h) => h.rec);
}
function setupSearch() {
  const input = document.getElementById('search-input');
  const box = document.getElementById('search-results');
  if (!input || !box) return;
  let t = null;
  const render = (recs) => {
    box.__recs = recs;
    if (!recs.length) { box.innerHTML = ''; box.style.display = 'none'; return; }
    box.innerHTML = recs.map((r, i) => {
      const sub = r.source === 'nalgadha'
        ? `${ngEsc(r.village || 'Nalgadha')} · Khata ${ngEsc(r.khata || '—')}${r.owners.length ? ' · ' + r.owners.length + ' owner' + (r.owners.length > 1 ? 's' : '') : ''}`
        : `Plot · ${ngEsc(r.village)} · Khata ${ngEsc(r.khata || '—')}`;
      return `<div class="sr-row" data-i="${i}"><b>${r.source === 'nalgadha' ? 'Gata' : 'Plot'} ${ngEsc(r.plot_no)}</b><span>${sub}</span></div>`;
    }).join('');
    box.style.display = 'block';
  };
  const pick = (rec, lbl) => { flyToFeature(rec); box.style.display = 'none'; input.value = lbl; };
  input.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => render(searchParcels(input.value)), 150); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const recs = (box.__recs && box.__recs.length) ? box.__recs : searchParcels(input.value);
      if (recs.length) { const r = recs[0]; pick(r, (r.source === 'nalgadha' ? 'Gata ' : 'Plot ') + r.plot_no); input.blur(); }
    } else if (e.key === 'Escape') { box.style.display = 'none'; input.blur(); }
  });
  box.addEventListener('click', (e) => {
    const row = e.target.closest('.sr-row'); if (!row) return;
    const rec = (box.__recs || [])[+row.getAttribute('data-i')];
    if (rec) pick(rec, (rec.source === 'nalgadha' ? 'Gata ' : 'Plot ') + rec.plot_no);
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('#search')) box.style.display = 'none'; });
}

map.on('load', async () => {
  // Area selector — overview entries first (datasets/tehsils/villages appended as they load)
  AREAS.push({ group: 'Overview', label: 'NCR — full region', sub: 'Delhi → Jewar',
               bounds: NCR_BOUNDS, opts: { padding: 20, maxZoom: 11 } });
  AREAS.push({ group: 'Overview', label: 'Gautam Buddh Nagar', sub: 'pilot district',
               bounds: GBN_BOUNDS, opts: { padding: 60, maxZoom: 13 } });

  // Satellite/aerial base (Esri World Imagery, no key) — sits under all data layers,
  // hidden until toggled, so users can ground-truth parcel boundaries.
  map.addSource('esri-sat', {
    type: 'raster', tileSize: 256,
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Imagery © Esri, Maxar, Earthstar Geographics'
  });
  map.addLayer({ id: 'esri-sat-layer', type: 'raster', source: 'esri-sat', layout: { visibility: 'none' } });

  let india, gbn;
  try {
    [india, gbn] = await Promise.all([
      fetch('./data/india_states.geojson').then((r) => r.json()),
      fetch('./data/gbn_tehsils.geojson').then((r) => r.json())
    ]);
  } catch (e) {
    alert('Could not load data files. Make sure web/data/ is deployed alongside the app. ' + e);
    return;
  }

  // India outline for context
  map.addSource('india', { type: 'geojson', data: india });
  map.addLayer({
    id: 'india-line', type: 'line', source: 'india',
    paint: { 'line-color': '#888', 'line-width': 0.5 }
  });

  // GBN tehsils — fill coloured by the (mock) growth score
  map.addSource('gbn', { type: 'geojson', data: gbn });
  map.addLayer({
    id: 'gbn-fill', type: 'fill', source: 'gbn',
    paint: {
      'fill-color': ['step', ['get', 'mock_score'], '#e74c3c', 45, '#f39c12', 70, '#2ecc71'],
      'fill-opacity': 0.18
    }
  });
  map.addLayer({
    id: 'gbn-line', type: 'line', source: 'gbn',
    paint: { 'line-color': '#111', 'line-width': 1.5 }
  });

  // Tehsil name labels as HTML markers (no glyph/font dependency) + area-selector entries
  for (const ft of gbn.features) {
    const c = polygonCentroid(ft.geometry);
    if (!c) continue;
    const el = document.createElement('div');
    el.className = 'tehsil-label';
    el.textContent = ft.properties.tehsil;
    new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat(c).addTo(map);
    const tb = geomBounds(ft.geometry);
    if (validB(tb) && ft.properties.tehsil) {
      AREAS.push({ group: 'Tehsils', label: ft.properties.tehsil + ' tehsil',
                   bounds: asLngLatBounds(tb), opts: { padding: 40, maxZoom: 13 } });
    }
  }
  map.on('mouseenter', 'gbn-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'gbn-fill', () => { map.getCanvas().style.cursor = ''; });

  // Real catalyst geometry from OpenStreetMap (airport + expressways)
  try {
    const osm = await fetch('./data/catalysts_osm.geojson').then((r) => (r.ok ? r.json() : null));
    if (osm && osm.features && osm.features.length) {
      airportCentroid = osm.meta && osm.meta.airport_centroid;
      if (airportCentroid) {
        const ae = document.createElement('div');
        ae.className = 'airport-pin'; ae.textContent = '✈';
        ae.title = 'Noida International Airport (Jewar)';
        new maplibregl.Marker({ element: ae, anchor: 'center' }).setLngLat(airportCentroid).addTo(map);
      }
      map.addSource('osm-cat', { type: 'geojson', data: osm });
      map.addLayer({ id: 'osm-roads', type: 'line', source: 'osm-cat',
        filter: ['==', ['get', 'kind'], 'road'],
        paint: { 'line-color': '#fb8c00', 'line-opacity': 0.55,
                 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.4, 10, 1.2, 14, 2.6] } });
      map.addLayer({ id: 'osm-airport', type: 'circle', source: 'osm-cat',
        filter: ['==', ['get', 'kind'], 'airport'],
        paint: { 'circle-radius': 11, 'circle-color': '#1d4ed8', 'circle-opacity': 0.35,
                 'circle-stroke-color': '#1d4ed8', 'circle-stroke-width': 2 } });
    }
  } catch (e) { /* no osm catalysts yet */ }

  // Real parcels from Bhu-Naksha + Phase-4 growth scoring
  try {
    const parcels = await fetch('./data/gbn_parcels.geojson').then((r) => (r.ok ? r.json() : null));
    if (parcels && parcels.features && parcels.features.length) {
      origGeo.parcels = parcels;          // pristine baseline for live calibration
      // circle rates (for price + score headroom)
      try {
        const rj = await fetch('./data/circle_rates.json').then((r) => (r.ok ? r.json() : null));
        if (rj) rates = rj.rates || {};
      } catch (e) { /* no rates yet */ }
      const clamp01 = (x) => Math.max(0, Math.min(1, x));

      // ---- Phase-4 v1 growth score (transparent heuristic, NOT a guarantee) ----
      //   65% airport proximity (distance-decay to 40 km) + 35% price headroom
      const seenRates = parcels.features
        .map((f) => (rates[normV(f.properties.village)] || {}).general)
        .filter((v) => v != null);
      const rMin = seenRates.length ? Math.min(...seenRates) : 0;
      const rMax = seenRates.length ? Math.max(...seenRates) : 0;
      for (const ft of parcels.features) {
        const p = ft.properties;
        let prox = null, head = null;
        if (airportCentroid) {
          p.airport_km = Math.round(haversineKm(airportCentroid, featCentroid(ft)) * 10) / 10;
          prox = clamp01(1 - p.airport_km / 40);
        }
        const r = rates[normV(p.village)];
        if (r && rMax > rMin) head = clamp01((rMax - r.general) / (rMax - rMin));
        let score = null;
        if (prox != null && head != null) score = 0.65 * prox + 0.35 * head;
        else if (prox != null) score = prox;
        else if (head != null) score = head;
        if (score != null) p.score = Math.round(score * 100);
      }

      map.addSource('parcels', { type: 'geojson', data: parcels });
      map.addLayer({ id: 'parcels-fill', type: 'fill', source: 'parcels',
        paint: {
          'fill-color': cidxFill(['case', ['has', 'score'],
            ['step', ['get', 'score'], '#e74c3c', 40, '#f39c12', 67, '#2ecc71'], '#9ca3af']),
          // real traced polygons solid; un-traced bbox boxes faint so overlap doesn't muddy the map
          'fill-opacity': ['case', IS_REAL, ifCidx(0.5, 0.6), 0.12]
        } });
      map.addLayer({ id: 'parcels-line', type: 'line', source: 'parcels',
        paint: { 'line-color': ['case', IS_REAL, '#333', '#6d28d9'],
                 'line-width': ['case', IS_REAL, ifCidx(1.1, 0.5), 0.35],
                 'line-opacity': ['case', IS_REAL, 0.9, 0.28] } });
      map.addLayer({ id: 'parcels-highlight', type: 'line', source: 'parcels',
        paint: { 'line-color': '#f59e0b', 'line-width': 3, 'line-opacity': 0.95 },
        filter: ['==', SELECT_KEY, '__none__'] });
      map.addLayer({ id: 'parcels-labels', type: 'symbol', source: 'parcels', minzoom: 15,
        layout: { 'text-field': ['get', 'plot_no'],
                  'text-size': ['interpolate', ['linear'], ['zoom'], 14, 9, 16, 12, 18, 15],
                  'text-font': ['Open Sans Bold'], 'text-allow-overlap': false },
        paint: { 'text-color': '#111827', 'text-halo-color': '#ffffff', 'text-halo-width': 1.8,
                 'text-opacity': ['interpolate', ['linear'], ['zoom'], 14, 0.4, 16, 1] } });

      map.on('mouseenter', 'parcels-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'parcels-fill', () => { map.getCanvas().style.cursor = ''; });

      indexFeatures('parcels', parcels.features, (p) => {
        try { const o = JSON.parse(p.owners); return Array.isArray(o) ? o : []; } catch { return []; }
      });

      const pb = new maplibregl.LngLatBounds();
      for (const ft of parcels.features) for (const c of ft.geometry.coordinates[0]) pb.extend(c);
      parcelBounds = pb;
      { const cc = pb.getCenter(); srcCentroid.parcels = [cc.lng, cc.lat]; }   // rotation pivot
      // Area selector: "all Jewar parcels" + one entry per village
      AREAS.push({ group: 'Overview', label: 'All Jewar parcels', sub: parcels.features.length + ' plots',
                   bounds: () => parcelBounds, opts: { padding: 40, maxZoom: 15 } });
      const pvb = villageBoundsMap(parcels.features);
      const pcount = {};
      for (const f of parcels.features) { const v = f.properties.village; if (v) pcount[v] = (pcount[v] || 0) + 1; }
      for (const [v, b] of Object.entries(pvb)) {
        if (!validB(b)) continue;
        AREAS.push({ group: 'Jewar — live parcels', label: v, sub: (pcount[v] || 0) + ' plots',
                     bounds: asLngLatBounds(b), opts: { padding: 50, maxZoom: 16 } });
      }
      console.log(`parcels loaded + scored: ${parcels.features.length}`);
    }
  } catch (e) { /* no parcels yet — fetcher hasn't run */ }

  // YEIDA live-scheme pins — dropped at each scheme's real sector location.
  try {
    const [schemesD, sectorsD] = await Promise.all([
      fetch('./data/yeida_schemes.json').then((r) => (r.ok ? r.json() : null)),
      fetch('./data/yeida_sectors.json').then((r) => (r.ok ? r.json() : null))
    ]);
    const SLOC = sectorsD && sectorsD.sectors;
    if (schemesD && SLOC) {
      const SCAT = { 'Residential': '#2563eb', 'Industrial': '#7c3aed', 'Institutional': '#0891b2',
                     'Commercial': '#ea580c', 'Mixed land use': '#65a30d', 'Other': '#6b7280' };
      const esc = (t) => (t == null ? '' : String(t)).replace(/[&<>"]/g,
        (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
      for (const s of schemesD.schemes) {
        const toks = ((s.sector || '') + ' ' + ((s.brochure || {}).sectors || '')).match(/\d+[A-Z]?/g) || [];
        const key = toks.find((t) => SLOC[t]);
        if (!key) continue;
        const loc = SLOC[key];
        const b = s.brochure || {};
        const col = SCAT[s.category] || SCAT.Other;
        const price = b.rate_per_sqm ? `₹${ratePsf(b.rate_per_sqm)}/sq ft` : '';
        locatedSchemes.push({ code: s.code, title: s.title, lat: loc.lat, lng: loc.lng });
        const el = document.createElement('div');
        el.className = 'scheme-pin' + (loc.approx ? ' approx' : '');
        el.style.background = col;
        el.title = s.title;
        const schemeHTML = `
          <div class="pop">
            <h3>${esc(s.title)}</h3>
            <div class="ctype" style="color:${col}">${esc(s.category)}${s.code ? ' · ' + esc(s.code) : ''}</div>
            ${price ? `<div class="badge" style="background:#047857">${price}</div>` : ''}
            ${s.deadline ? `<div class="note">⏰ ${esc(s.deadline)}</div>` : ''}
            <div class="mock">${loc.approx ? '~ ' + esc(loc.display_name) + ' (approx)' : 'YEIDA Sector ' + esc(key) + ' · OSM'}</div>
          </div>`;
        const at = [loc.lng, loc.lat];
        const openScheme = () => showPopup(at, schemeHTML, '300px', 16);
        // stopPropagation so a pin click doesn't also fire the map click underneath it.
        el.addEventListener('click', (ev) => { ev.stopPropagation(); openScheme(); });
        new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat(at).addTo(map);
        if (s.code) schemePins[s.code] = { lngLat: at, open: openScheme };
      }
    }
  } catch (e) { /* no scheme pins yet */ }

  // Nalgadha gata register (title reconstruction) — coloured by # of owners (fragmentation).
  try {
    const [ng, ngOwners, ngHist] = await Promise.all([
      fetch('./data/nalgadha_parcels.geojson').then((r) => (r.ok ? r.json() : null)),
      fetch('./data/nalgadha_owners.json').then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
      fetch('./data/nalgadha_history.json').then((r) => (r.ok ? r.json() : null)).catch(() => null)
    ]);
    nalgadhaOwners = ngOwners || {};
    nalgadhaHistory = (ngHist && ngHist.histories) || {};
    if (ng && ng.features && ng.features.length) {
      origGeo.nalgadha = ng;              // pristine baseline for live calibration
      map.addSource('nalgadha', { type: 'geojson', data: ng });
      map.addLayer({
        id: 'nalgadha-fill', type: 'fill', source: 'nalgadha',
        paint: {
          'fill-color': cidxFill(['step', ['get', 'owner_count'],
            '#ddd6fe', 1, '#c4b5fd', 3, '#a78bfa', 6, '#8b5cf6', 10, '#6d28d9']),
          'fill-opacity': ['case', IS_REAL, ifCidx(0.5, 0.8), 0.12]
        }
      });
      map.addLayer({ id: 'nalgadha-line', type: 'line', source: 'nalgadha',
        paint: { 'line-color': ['case', IS_REAL, ifCidx('#333333', '#4c1d95'), '#6d28d9'],
                 'line-width': ['case', IS_REAL, ifCidx(1.1, 0.5), 0.35],
                 'line-opacity': ['case', IS_REAL, 0.9, 0.28] } });
      map.addLayer({ id: 'nalgadha-highlight', type: 'line', source: 'nalgadha',
        paint: { 'line-color': '#f59e0b', 'line-width': 3.5, 'line-opacity': 0.97 },
        filter: ['==', SELECT_KEY, '__none__'] });
      map.addLayer({ id: 'nalgadha-labels', type: 'symbol', source: 'nalgadha', minzoom: 15,
        layout: { 'text-field': ['get', 'plot_no'],
                  'text-size': ['interpolate', ['linear'], ['zoom'], 14, 9, 16, 12, 18, 15],
                  'text-font': ['Open Sans Bold'], 'text-allow-overlap': false },
        paint: { 'text-color': '#1e1b4b', 'text-halo-color': '#ffffff', 'text-halo-width': 1.8,
                 'text-opacity': ['interpolate', ['linear'], ['zoom'], 14, 0.4, 16, 1] } });

      map.on('mouseenter', 'nalgadha-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'nalgadha-fill', () => { map.getCanvas().style.cursor = ''; });

      indexFeatures('nalgadha', ng.features, (p) => nalgadhaOwners[uidOf(p)] || []);

      const nb = new maplibregl.LngLatBounds();
      for (const ft of ng.features) for (const c of ft.geometry.coordinates[0]) nb.extend(c);
      nalgadhaBounds = nb;
      { const cc = nb.getCenter(); srcCentroid.nalgadha = [cc.lng, cc.lat]; }    // rotation pivot
      // Area selector: "all ownership villages" + one entry per village (these have history data)
      const vcount = new Set(ng.features.map((f) => f.properties.village)).size;
      AREAS.push({ group: 'Overview', label: 'All ownership villages', sub: vcount + ' villages',
                   bounds: () => nalgadhaBounds, opts: { padding: 50, maxZoom: 14 } });
      const nvb = villageBoundsMap(ng.features);
      const ncount = {};
      for (const f of ng.features) { const v = f.properties.village; if (v) ncount[v] = (ncount[v] || 0) + 1; }
      for (const [v, b] of Object.entries(nvb)) {
        if (!validB(b)) continue;
        AREAS.push({ group: 'Ownership history', label: v, sub: (ncount[v] || 0) + ' plots',
                     own: true, bounds: asLngLatBounds(b), opts: { padding: 50, maxZoom: 16 } });
      }
    }
  } catch (e) { /* no nalgadha data yet */ }

  // Hide placeholder boxes by default (only real surveyed plots) + build the area menu.
  applyCleanView();
  applySat();                 // satellite-first base map
  applyCalibration();         // apply any saved/seeded alignment offset
  setupAreaSelector();
  setupLayerControls();
  setupCalibration();
  renderLegendExtra();

  // Deep-link restore (after sources/search index exist) — else reveal on the GBN pilot.
  const restored = restoreFromHash();
  if (!restored) setTimeout(() => map.fitBounds(GBN_BOUNDS, { padding: 60, duration: 2200 }), 900);
});

// ---- Controls ------------------------------------------------------------
// Base map: satellite by default (a land tool should show the real ground); the
// button flips to the OSM street map. applySat() keeps layer + icon + label in sync.
let satOn = true;
const satBtn = document.getElementById('btn-sat');
function applySat() {
  if (map.getLayer('esri-sat-layer')) map.setLayoutProperty('esri-sat-layer', 'visibility', satOn ? 'visible' : 'none');
  if (map.getLayer('osm')) map.setLayoutProperty('osm', 'visibility', satOn ? 'none' : 'visible');
  if (satBtn) {
    satBtn.classList.toggle('active', satOn);
    const lbl = satBtn.querySelector('.tb-label'); if (lbl) lbl.textContent = satOn ? 'Street map' : 'Satellite';
    const ico = satBtn.querySelector('.tb-ico'); if (ico) ico.textContent = satOn ? '🗺️' : '🛰️';
  }
}
if (satBtn) satBtn.onclick = () => { satOn = !satOn; applySat(); };

// "Real polygons only" filter: hide un-traced bbox boxes so every visible parcel is a
// real surveyed plot — a click then always lands exactly on the parcel outline.
const CLEAN_TARGETS = ['parcels-fill', 'parcels-line', 'parcels-labels',
                       'nalgadha-fill', 'nalgadha-line', 'nalgadha-labels'];
function applyCleanView() {
  for (const id of CLEAN_TARGETS) {
    if (map.getLayer(id)) map.setFilter(id, cleanView ? REAL_ONLY : null);
  }
  refreshHighlights();   // keep the selection outline consistent with placeholder visibility
}

// ---- Layer / view popover (placeholder toggle + dataset visibility) ------
function setLayerGroupVisible(prefix, on) {
  for (const suf of ['-fill', '-line', '-labels', '-highlight']) {
    const id = prefix + suf;
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
  }
}
function toggleableDropdown(id) {
  const dd = document.getElementById(id); if (!dd) return;
  const btn = dd.querySelector('button');
  const menu = dd.querySelector('.dd-menu');
  if (btn) btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = dd.classList.toggle('open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  if (menu) menu.addEventListener('click', (e) => e.stopPropagation()); // stay open while toggling
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#' + id)) { dd.classList.remove('open'); if (btn) btn.setAttribute('aria-expanded', 'false'); }
  });
}
function setupLayerControls() {
  toggleableDropdown('layers');
  const ph = document.getElementById('lyr-placeholders');
  if (ph) { ph.checked = !cleanView; ph.onchange = () => { cleanView = !ph.checked; applyCleanView(); }; }
  const lp = document.getElementById('lyr-parcels');
  if (lp) lp.onchange = () => setLayerGroupVisible('parcels', lp.checked);
  const ln = document.getElementById('lyr-nalgadha');
  if (ln) ln.onchange = () => setLayerGroupVisible('nalgadha', ln.checked);
}

// ---- "Align to satellite" calibration control ----------------------------
function saveCalib() { try { localStorage.setItem('land_calib', JSON.stringify(CALIB)); } catch (e) { /* */ } }
function nearestDataset() {
  if (!parcelBounds) return 'nalgadha';
  if (!nalgadhaBounds) return 'parcels';
  const c = map.getCenter();
  const d = (b) => { const cc = b.getCenter(); return Math.hypot(cc.lng - c.lng, cc.lat - c.lat); };
  return d(parcelBounds) <= d(nalgadhaBounds) ? 'parcels' : 'nalgadha';
}
function setupCalibration() {
  const tgt = document.getElementById('calib-target'); if (!tgt) return;
  const fmt = () => {
    const c = CALIB[tgt.value] || { dx: 0, dy: 0, rot: 0 };
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('cal-dx', c.dx + ' m'); set('cal-dy', c.dy + ' m'); set('cal-rot', (Math.round(c.rot * 10) / 10) + '°');
  };
  tgt.value = nearestDataset();
  fmt();
  tgt.onchange = fmt;
  let t = null;
  document.querySelectorAll('#layers-menu .calib-row button').forEach((b) => {
    b.onclick = () => {
      const s = tgt.value, k = b.getAttribute('data-k'), d = parseFloat(b.getAttribute('data-d'));
      CALIB[s][k] = Math.round((CALIB[s][k] + d) * 10) / 10;
      fmt(); saveCalib();
      clearTimeout(t); t = setTimeout(() => applyCalibration(s), 120);
    };
  });
  const reset = document.getElementById('cal-reset');
  if (reset) reset.onclick = () => { const s = tgt.value; CALIB[s] = { dx: 0, dy: 0, rot: 0 }; fmt(); saveCalib(); applyCalibration(s); };
}

// ---- Area selector (searchable, grouped: Overview · Tehsils · villages) --
function goToArea(a) {
  const b = typeof a.bounds === 'function' ? a.bounds() : a.bounds;
  if (!b) return;
  map.fitBounds(b, Object.assign({ padding: 60, duration: 1400 }, a.opts || {}));
  const lbl = document.getElementById('area-label'); if (lbl) lbl.textContent = a.label;
}
function setupAreaSelector() {
  const dd = document.getElementById('area-select');
  const btn = document.getElementById('area-btn');
  const search = document.getElementById('area-search');
  const list = document.getElementById('area-list');
  if (!dd || !btn || !list) return;
  const render = (q) => {
    q = (q || '').trim().toLowerCase();
    const groups = {};
    AREAS.forEach((a, i) => {
      if (q && !((a.label + ' ' + (a.sub || '') + ' ' + a.group).toLowerCase().includes(q))) return;
      (groups[a.group] || (groups[a.group] = [])).push(i);
    });
    let html = '';
    for (const g of GROUP_ORDER) {
      const idxs = groups[g]; if (!idxs || !idxs.length) continue;
      html += `<div class="dd-group">${ngEsc(g)}</div>`;
      for (const i of idxs) {
        const a = AREAS[i];
        const sub = a.sub ? `<span class="dd-item-sub${a.own ? ' own' : ''}">${a.own ? '● ' : ''}${ngEsc(a.sub)}</span>` : '';
        html += `<div class="dd-item" data-i="${i}" role="option"><span class="dd-item-label">${ngEsc(a.label)}</span>${sub}</div>`;
      }
    }
    list.innerHTML = html || `<div class="dd-empty">No areas match “${ngEsc(q)}”.</div>`;
  };
  const open = () => { dd.classList.add('open'); btn.setAttribute('aria-expanded', 'true'); if (search) search.value = ''; render(''); setTimeout(() => search && search.focus(), 0); };
  const close = () => { dd.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); };
  btn.addEventListener('click', (e) => { e.stopPropagation(); dd.classList.contains('open') ? close() : open(); });
  if (search) {
    search.addEventListener('input', () => render(search.value));
    search.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { close(); btn.focus(); }
      else if (e.key === 'Enter') { const first = list.querySelector('.dd-item'); if (first) first.click(); }
    });
  }
  list.addEventListener('click', (e) => {
    const it = e.target.closest('.dd-item'); if (!it) return;
    const a = AREAS[+it.getAttribute('data-i')]; if (a) { goToArea(a); close(); }
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('#area-select')) close(); });
  render('');
}

// ---- Legend: only show rows for layers that actually loaded ---------------
function renderLegendExtra() {
  const box = document.getElementById('legend-extra'); if (!box) return;
  const rows = [];
  if (map.getLayer('osm-airport') || map.getLayer('osm-roads'))
    rows.push('<div class="row"><span class="dot"></span> ✈ airport · 🛣 expressways</div>');
  if (locatedSchemes.length)
    rows.push('<div class="row"><span class="schemesw"></span> ◆ YEIDA live schemes <span style="opacity:.6">(◇ approx)</span></div>');
  box.innerHTML = rows.length ? '<hr>' + rows.join('') : '';
}

document.getElementById('drawer-close')?.addEventListener('click', closeDrawer);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
setupSearch();

// ---- Live YEIDA schemes panel (data scraped weekly from the YEIDA portal via Firecrawl) ----
(async function renderSchemes() {
  const panel = document.getElementById('schemes');
  if (!panel) return;
  let data;
  try { data = await fetch('./data/yeida_schemes.json').then((r) => (r.ok ? r.json() : null)); }
  catch (e) { panel.style.display = 'none'; return; }
  if (!data || !Array.isArray(data.schemes) || !data.schemes.length) { panel.style.display = 'none'; return; }

  const CAT = {
    'Residential': '#2563eb', 'Industrial': '#7c3aed', 'Institutional': '#0891b2',
    'Commercial': '#ea580c', 'Mixed land use': '#65a30d', 'Other': '#6b7280'
  };
  const esc = (s) => (s == null ? '' : String(s)).replace(/[&<>"]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  document.getElementById('schemes-list').innerHTML = data.schemes.map((s) => {
    const col = CAT[s.category] || CAT.Other;
    const b = s.brochure || {};
    const docLabel = (s.brochure_or_status_url || '').toLowerCase().endsWith('.pdf') ? '📄 Brochure' : '📄 Status';
    const meta = [];
    if (s.deadline) meta.push(`<span class="deadline">⏰ ${esc(s.deadline)}</span>`);
    const sec = b.sectors || s.sector;
    if (sec) meta.push(`<span class="sector">📍 Sec ${esc(sec)}</span>`);
    const econ = [];
    if (b.rate_per_sqm) econ.push(`<b class="rate">₹${ratePsf(b.rate_per_sqm)}/sq ft</b>`);
    if (Array.isArray(b.plot_sizes_sqm) && b.plot_sizes_sqm.length) {
      const ps = b.plot_sizes_sqm;
      econ.push(`${ps.length} size${ps.length > 1 ? 's' : ''} ${sqft(ps[0])}–${sqft(ps[ps.length - 1])} sq ft`);
    }
    if (b.lease_years) econ.push(`${b.lease_years}-yr lease`);
    const links = [];
    if (s.brochure_or_status_url)
      links.push(`<a href="${esc(s.brochure_or_status_url)}" target="_blank" rel="noopener">${docLabel}</a>`);
    if (s.apply_url)
      links.push(`<a href="${esc(s.apply_url)}" target="_blank" rel="noopener">🔗 Apply / status</a>`);
    return `<div class="scheme" data-code="${esc(s.code || '')}">
      <div class="scheme-top">
        <span class="cat" style="background:${col}">${esc(s.category)}</span>
        ${s.code ? `<span class="code">${esc(s.code)}</span>` : ''}
      </div>
      <div class="scheme-title">${esc(s.title)}</div>
      ${meta.length ? `<div class="scheme-meta">${meta.join('')}</div>` : ''}
      ${econ.length ? `<div class="scheme-econ">${econ.join(' · ')}</div>` : ''}
      ${links.length ? `<div class="scheme-links">${links.join('')}</div>` : ''}
    </div>`;
  }).join('');

  // panel -> map: click a scheme row to fly to its pin (if it's locatable)
  document.querySelectorAll('#schemes-list .scheme').forEach((el) => {
    el.addEventListener('click', (ev) => {
      if (ev.target.closest('a')) return;            // let the real links work
      const pin = schemePins[el.getAttribute('data-code')];
      if (pin) { map.flyTo({ center: pin.lngLat, zoom: 12, duration: 1200 }); pin.open(); }
    });
  });

  document.getElementById('schemes-count').textContent = data.schemes.length + ' live';
  let when = '';
  try { when = new Date(data.fetched_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch (e) { /* keep blank */ }
  document.getElementById('schemes-foot').textContent =
    `Live from the YEIDA portal · via Firecrawl${when ? ' · ' + when : ''}`;

  const head = document.getElementById('schemes-head');
  const tog = document.getElementById('schemes-toggle');
  head.onclick = () => { tog.textContent = panel.classList.toggle('collapsed') ? '▸' : '▾'; };
})();

// ---- Growth Hubs panel (city/district GSDP growth signals; compiled, not live) ----
(async function renderGrowth() {
  const panel = document.getElementById('growth');
  if (!panel) return;
  let data;
  try { data = await fetch('./data/growth_signals.json').then((r) => (r.ok ? r.json() : null)); }
  catch (e) { panel.style.display = 'none'; return; }
  if (!data || !Array.isArray(data.hubs) || !data.hubs.length) { panel.style.display = 'none'; return; }
  const esc = (s) => (s == null ? '' : String(s)).replace(/[&<>"]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const hubs = [...data.hubs].sort((a, b) => b.gsdp_growth - a.gsdp_growth);
  const max = Math.max(...hubs.map((h) => h.gsdp_growth));
  document.getElementById('growth-list').innerHTML = hubs.map((h) => {
    const w = Math.round((h.gsdp_growth / max) * 100);
    const g = `${h.approx ? '~' : ''}${h.gsdp_growth}%`;
    return `<div class="hub${h.focus ? ' focus' : ''}">
      <div class="hub-top"><span class="hub-city">${esc(h.city)}</span><span class="hub-g">${g}</span></div>
      <div class="hub-bar"><span style="width:${w}%"></span></div>
      <div class="hub-note">${esc(h.state)} · ${esc(h.note || '')}</div>
    </div>`;
  }).join('');
  document.getElementById('growth-foot').textContent = `${data.note} (${data.sources || ''})`;
  panel.classList.add('collapsed');
  const ghead = document.getElementById('growth-head');
  const gtog = document.getElementById('growth-toggle');
  ghead.onclick = () => { gtog.textContent = panel.classList.toggle('collapsed') ? '▸' : '▾'; };
})();
