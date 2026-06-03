// LAND — Phase 0 map. The data is placeholder; the mechanism is real.
const INDIA_BOUNDS = [[68.0, 6.5], [97.5, 37.0]];    // home view = India
const GBN_BOUNDS = [[77.28, 28.02], [77.88, 28.66]]; // approx GBN bbox
let parcelBounds = null;
let airportCentroid = null;

const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
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
  bounds: INDIA_BOUNDS,
  fitBoundsOptions: { padding: 20 },
  maxBounds: [[60.0, 2.0], [100.0, 39.0]], // keep the map India-focused
  maxZoom: 18
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');

// rough centroid = mean of the first ring's vertices (good enough for a label)
function polygonCentroid(geometry) {
  let ring;
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

map.on('load', async () => {
  let india, gbn, catalysts;
  try {
    [india, gbn, catalysts] = await Promise.all([
      fetch('./data/india_states.geojson').then((r) => r.json()),
      fetch('./data/gbn_tehsils.geojson').then((r) => r.json()),
      fetch('./data/catalysts.geojson').then((r) => r.json())
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

  // Tehsil name labels as HTML markers (no glyph/font dependency)
  for (const ft of gbn.features) {
    const c = polygonCentroid(ft.geometry);
    if (!c) continue;
    const el = document.createElement('div');
    el.className = 'tehsil-label';
    el.textContent = ft.properties.tehsil;
    new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat(c).addTo(map);
  }

  // Tehsil click → scorecard popup
  map.on('click', 'gbn-fill', (e) => {
    const p = e.features[0].properties;
    new maplibregl.Popup({ maxWidth: '300px' })
      .setLngLat(e.lngLat)
      .setHTML(`
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
        </div>`)
      .addTo(map);
  });
  map.on('mouseenter', 'gbn-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'gbn-fill', () => { map.getCanvas().style.cursor = ''; });

  // Catalyst markers
  for (const ft of catalysts.features) {
    const p = ft.properties;
    const el = document.createElement('div');
    el.className = 'catalyst-pin';
    el.title = p.name;
    const pop = new maplibregl.Popup({ offset: 14 }).setHTML(`
      <div class="pop">
        <h3>${p.name}</h3>
        <div class="ctype">${p.ctype} · ${p.status}</div>
        <div class="note">${p.note}</div>
        <div class="mock">approx. location · Phase-0 placeholder</div>
      </div>`);
    new maplibregl.Marker({ element: el, anchor: 'center' })
      .setLngLat(ft.geometry.coordinates).setPopup(pop).addTo(map);
  }

  // Real catalyst geometry from OpenStreetMap (airport + expressways)
  try {
    const osm = await fetch('./data/catalysts_osm.geojson').then((r) => (r.ok ? r.json() : null));
    if (osm && osm.features && osm.features.length) {
      airportCentroid = osm.meta && osm.meta.airport_centroid;
      map.addSource('osm-cat', { type: 'geojson', data: osm });
      map.addLayer({ id: 'osm-roads', type: 'line', source: 'osm-cat',
        filter: ['==', ['get', 'kind'], 'road'],
        paint: { 'line-color': '#fb8c00', 'line-opacity': 0.55,
                 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.4, 10, 1.2, 14, 2.6] } });
      map.addLayer({ id: 'osm-airport', type: 'circle', source: 'osm-cat',
        filter: ['==', ['get', 'kind'], 'airport'],
        paint: { 'circle-radius': 11, 'circle-color': '#1d4ed8', 'circle-opacity': 0.35,
                 'circle-stroke-color': '#1d4ed8', 'circle-stroke-width': 2 } });
      map.on('click', 'osm-airport', (e) => {
        new maplibregl.Popup().setLngLat(e.lngLat).setHTML(
          `<div class="pop"><h3>${e.features[0].properties.name}</h3>
           <div class="ctype">${e.features[0].properties.status || ''}</div>
           <div class="mock">real footprint · OpenStreetMap</div></div>`).addTo(map);
      });
    }
  } catch (e) { /* no osm catalysts yet */ }

  // Real parcels from Bhu-Naksha + Phase-4 growth scoring
  try {
    const parcels = await fetch('./data/gbn_parcels.geojson').then((r) => (r.ok ? r.json() : null));
    if (parcels && parcels.features && parcels.features.length) {
      // circle rates (for price + score headroom)
      let rates = {};
      try {
        const rj = await fetch('./data/circle_rates.json').then((r) => (r.ok ? r.json() : null));
        if (rj) rates = rj.rates || {};
      } catch (e) { /* no rates yet */ }
      const normV = (s) => (s || '').replace(/\s+/g, '');
      const inr = (v) => (v >= 1e7 ? '₹' + (v / 1e7).toFixed(2) + ' Cr'
                        : v >= 1e5 ? '₹' + (v / 1e5).toFixed(1) + ' L' : '₹' + Math.round(v));
      const clamp01 = (x) => Math.max(0, Math.min(1, x));
      const featCentroid = (ft) => {
        const ring = ft.geometry.coordinates[0];
        let x = 0, y = 0; for (const c of ring) { x += c[0]; y += c[1]; }
        return [x / ring.length, y / ring.length];
      };

      // ---- Phase-4 v1 growth score (transparent heuristic, NOT a guarantee) ----
      //   65% airport proximity (distance-decay to 40 km) + 35% price headroom
      //   (cheaper than the area's range = more room to appreciate near the catalyst)
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
          'fill-color': ['case', ['has', 'score'],
            ['step', ['get', 'score'], '#e74c3c', 40, '#f39c12', 67, '#2ecc71'], '#9ca3af'],
          'fill-opacity': 0.6
        } });
      map.addLayer({ id: 'parcels-line', type: 'line', source: 'parcels',
        paint: { 'line-color': '#333', 'line-width': 0.5 } });

      map.on('click', 'parcels-fill', (e) => {
        const p = e.features[0].properties;
        let owners = p.owners; try { owners = JSON.parse(p.owners); } catch { /* */ }
        const r = rates[normV(p.village)];
        let priceRows = '';
        if (r && p.area_ha != null) {
          priceRows = `<tr><td>Circle value</td><td><b>${inr(p.area_ha * r.general)}</b></td></tr>`
                    + `<tr><td>Rate (general)</td><td>${inr(r.general)}/ha</td></tr>`;
        }
        const distRow = p.airport_km != null ? `<tr><td>✈ Airport</td><td>~${p.airport_km} km</td></tr>` : '';
        const sc = p.score;
        const col = sc == null ? '#9ca3af' : sc >= 67 ? '#2ecc71' : sc >= 40 ? '#f39c12' : '#e74c3c';
        const band = sc == null ? '—' : sc >= 67 ? 'High 🟢' : sc >= 40 ? 'Medium 🟠' : 'Low 🔴';
        const scoreHdr = sc == null ? '' :
          `<div class="badge" style="background:${col}">Growth score ${sc}/100 · ${band}</div>`;
        new maplibregl.Popup({ maxWidth: '320px' }).setLngLat(e.lngLat).setHTML(`
          <div class="pop">
            <h3>Plot ${p.plot_no} <small>${p.village || ''}</small></h3>
            ${scoreHdr}
            <table>
              <tr><td>Khata</td><td>${p.khata_no || '—'}</td></tr>
              <tr><td>Area</td><td>${p.area_ha != null ? p.area_ha + ' ha' : '—'}</td></tr>
              <tr><td>Owners</td><td>${Array.isArray(owners) ? owners.length : (p.owner_count ?? '—')}</td></tr>
              ${priceRows}
              ${distRow}
            </table>
            <div class="driver">score v1 = 65% airport proximity + 35% price headroom · heuristic, not a guarantee</div>
            <div class="mock">parcel: Bhu-Naksha · price: IGRSUP · catalyst: OSM</div>
          </div>`).addTo(map);
      });
      map.on('mouseenter', 'parcels-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'parcels-fill', () => { map.getCanvas().style.cursor = ''; });

      const pb = new maplibregl.LngLatBounds();
      for (const ft of parcels.features) for (const c of ft.geometry.coordinates[0]) pb.extend(c);
      parcelBounds = pb;
      const pbtn = document.getElementById('btn-parcels');
      if (pbtn) { pbtn.style.display = 'inline-block'; pbtn.textContent = `🟣 Live parcels (${parcels.features.length})`; }
      console.log(`parcels loaded + scored: ${parcels.features.length}`);
    }
  } catch (e) { /* no parcels yet — fetcher hasn't run */ }

  // Reveal: open on India, then fly to the GBN pilot
  setTimeout(() => map.fitBounds(GBN_BOUNDS, { padding: 60, duration: 2500 }), 1200);
});

document.getElementById('btn-india').onclick =
  () => map.fitBounds(INDIA_BOUNDS, { padding: 20, duration: 1500 });
document.getElementById('btn-gbn').onclick =
  () => map.fitBounds(GBN_BOUNDS, { padding: 60, duration: 1500 });
document.getElementById('btn-parcels').onclick =
  () => { if (parcelBounds) map.fitBounds(parcelBounds, { padding: 40, maxZoom: 17, duration: 1500 }); };

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
    const docLabel = (s.brochure_or_status_url || '').toLowerCase().endsWith('.pdf') ? '📄 Brochure' : '📄 Status';
    const meta = [];
    if (s.deadline) meta.push(`<span class="deadline">⏰ ${esc(s.deadline)}</span>`);
    if (s.sector) meta.push(`<span class="sector">📍 Sec ${esc(s.sector)}</span>`);
    const links = [];
    if (s.brochure_or_status_url)
      links.push(`<a href="${esc(s.brochure_or_status_url)}" target="_blank" rel="noopener">${docLabel}</a>`);
    if (s.apply_url)
      links.push(`<a href="${esc(s.apply_url)}" target="_blank" rel="noopener">🔗 Apply / status</a>`);
    return `<div class="scheme">
      <div class="scheme-top">
        <span class="cat" style="background:${col}">${esc(s.category)}</span>
        ${s.code ? `<span class="code">${esc(s.code)}</span>` : ''}
      </div>
      <div class="scheme-title">${esc(s.title)}</div>
      ${meta.length ? `<div class="scheme-meta">${meta.join('')}</div>` : ''}
      ${links.length ? `<div class="scheme-links">${links.join('')}</div>` : ''}
    </div>`;
  }).join('');

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
