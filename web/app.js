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
      'fill-opacity': 0.55
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
        paint: { 'line-color': '#ff6d00', 'line-width': 2, 'line-opacity': 0.75 } });
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

  // Real parcels from Bhu-Naksha (rendered only once the fetcher has produced them)
  try {
    const parcels = await fetch('./data/gbn_parcels.geojson').then((r) => (r.ok ? r.json() : null));
    if (parcels && parcels.features && parcels.features.length) {
      map.addSource('parcels', { type: 'geojson', data: parcels });
      map.addLayer({ id: 'parcels-fill', type: 'fill', source: 'parcels',
        paint: { 'fill-color': '#7c3aed', 'fill-opacity': 0.28 } });
      map.addLayer({ id: 'parcels-line', type: 'line', source: 'parcels',
        paint: { 'line-color': '#5b21b6', 'line-width': 0.6 } });
      // circle-rate price layer (client-side join by village name)
      let rates = {};
      try {
        const rj = await fetch('./data/circle_rates.json').then((r) => (r.ok ? r.json() : null));
        if (rj) rates = rj.rates || {};
      } catch (e) { /* no rates yet */ }
      const normV = (s) => (s || '').replace(/\s+/g, '');
      const inr = (v) => (v >= 1e7 ? '₹' + (v / 1e7).toFixed(2) + ' Cr'
                        : v >= 1e5 ? '₹' + (v / 1e5).toFixed(1) + ' L' : '₹' + Math.round(v));

      map.on('click', 'parcels-fill', (e) => {
        const p = e.features[0].properties;
        let owners = p.owners; try { owners = JSON.parse(p.owners); } catch { /* */ }
        const r = rates[normV(p.village)];
        let priceRows = '';
        if (r && p.area_ha != null) {
          const val = p.area_ha * r.general;
          priceRows = `<tr><td>Circle value</td><td><b>${inr(val)}</b></td></tr>`
                    + `<tr><td>Rate (general)</td><td>${inr(r.general)}/ha</td></tr>`;
        }
        let distRow = '';
        if (airportCentroid) {
          const km = haversineKm(airportCentroid, e.lngLat.toArray());
          distRow = `<tr><td>✈ Airport</td><td>~${km.toFixed(1)} km</td></tr>`;
        }
        new maplibregl.Popup({ maxWidth: '320px' }).setLngLat(e.lngLat).setHTML(`
          <div class="pop">
            <h3>Plot ${p.plot_no} <small>${p.village || ''}</small></h3>
            <table>
              <tr><td>Khata</td><td>${p.khata_no || '—'}</td></tr>
              <tr><td>Area</td><td>${p.area_ha != null ? p.area_ha + ' ha' : '—'}</td></tr>
              <tr><td>Owners</td><td>${Array.isArray(owners) ? owners.length : (p.owner_count ?? '—')}</td></tr>
              ${priceRows}
              ${distRow}
            </table>
            ${Array.isArray(owners) && owners.length ? `<div class="driver">${owners.join(', ')}</div>` : ''}
            <div class="mock">parcel: Bhu-Naksha · price: IGRSUP circle rate</div>
          </div>`).addTo(map);
      });
      map.on('mouseenter', 'parcels-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'parcels-fill', () => { map.getCanvas().style.cursor = ''; });
      const pb = new maplibregl.LngLatBounds();
      for (const ft of parcels.features) for (const c of ft.geometry.coordinates[0]) pb.extend(c);
      parcelBounds = pb;
      const pbtn = document.getElementById('btn-parcels');
      if (pbtn) { pbtn.style.display = 'inline-block'; pbtn.textContent = `🟣 Live parcels (${parcels.features.length})`; }
      console.log(`parcels loaded: ${parcels.features.length}`);
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
