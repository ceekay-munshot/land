// LAND — Phase 0 map. The data is placeholder; the mechanism is real.
const NCR_BOUNDS = [[76.65, 27.55], [78.05, 28.95]]; // Delhi-NCR down to Jewar — the working area
const GBN_BOUNDS = [[77.28, 28.02], [77.88, 28.66]]; // approx GBN bbox
let parcelBounds = null;
let airportCentroid = null;
let locatedSchemes = [];   // YEIDA schemes we could place (pins + parcel proximity)
const schemePins = {};     // scheme code -> Marker (panel <-> map linking)
const SQFT = 10.7639;      // 1 m² in sq ft — plot rates/sizes shown in sq ft (familiar unit)
const sqft = (m2) => Math.round(m2 * SQFT).toLocaleString('en-IN');
const ratePsf = (psm) => Math.round(psm / SQFT).toLocaleString('en-IN');

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
  bounds: NCR_BOUNDS,
  fitBoundsOptions: { padding: 20 },
  maxBounds: [[76.2, 27.1], [78.6, 29.4]], // lock to the NCR/GBN region — no empty world map
  minZoom: 8,
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

  // (Phase-0 placeholder catalyst pins removed — the real OSM airport + expressways render below.)

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
        let schemeRow = '';
        if (locatedSchemes.length) {
          const cc = featCentroid(e.features[0]);
          let best = null, bd = Infinity;
          for (const s2 of locatedSchemes) { const d = haversineKm(cc, [s2.lng, s2.lat]); if (d < bd) { bd = d; best = s2; } }
          if (best) schemeRow = `<tr><td>◆ Live scheme</td><td>${best.code || best.title} · ${bd.toFixed(1)} km</td></tr>`;
        }
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
              ${schemeRow}
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

  // YEIDA live-scheme pins — dropped at each scheme's real sector location (OSM where exact,
  // Dankaur-area approx for the residential cluster). Schemes with no locatable sector stay
  // in the side panel only — no fake placement.
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
        const pop = new maplibregl.Popup({ offset: 16 }).setHTML(`
          <div class="pop">
            <h3>${esc(s.title)}</h3>
            <div class="ctype" style="color:${col}">${esc(s.category)}${s.code ? ' · ' + esc(s.code) : ''}</div>
            ${price ? `<div class="badge" style="background:#047857">${price}</div>` : ''}
            ${s.deadline ? `<div class="note">⏰ ${esc(s.deadline)}</div>` : ''}
            <div class="mock">${loc.approx ? '~ ' + esc(loc.display_name) + ' (approx)' : 'YEIDA Sector ' + esc(key) + ' · OSM'}</div>
          </div>`);
        const mk = new maplibregl.Marker({ element: el, anchor: 'center' })
          .setLngLat([loc.lng, loc.lat]).setPopup(pop).addTo(map);
        if (s.code) schemePins[s.code] = mk;
      }
    }
  } catch (e) { /* no scheme pins yet */ }

  // Reveal: open on the NCR region, then settle on the GBN pilot
  setTimeout(() => map.fitBounds(GBN_BOUNDS, { padding: 60, duration: 2200 }), 900);
});

document.getElementById('btn-india').onclick =
  () => map.fitBounds(NCR_BOUNDS, { padding: 20, duration: 1500 });
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
      const mk = schemePins[el.getAttribute('data-code')];
      if (mk) { map.flyTo({ center: mk.getLngLat(), zoom: 12, duration: 1200 }); mk.togglePopup(); }
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
