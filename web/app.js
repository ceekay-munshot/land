// LAND — Phase 0 map. The data is placeholder; the mechanism is real.
const INDIA_CENTER = [79.0, 22.5];
const GBN_BOUNDS = [[77.28, 28.02], [77.88, 28.66]]; // approx GBN bbox

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
  center: INDIA_CENTER,
  zoom: 3.6,
  maxZoom: 16
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

const scoreColor = (s) => (s >= 70 ? '#2ecc71' : s >= 45 ? '#f39c12' : '#e74c3c');

map.on('load', async () => {
  let india, gbn, catalysts;
  try {
    [india, gbn, catalysts] = await Promise.all([
      fetch('../data/india_states.geojson').then((r) => r.json()),
      fetch('../data/gbn_tehsils.geojson').then((r) => r.json()),
      fetch('../data/catalysts.geojson').then((r) => r.json())
    ]);
  } catch (e) {
    alert('Could not load data. Serve the repo root over http (see README): ' + e);
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

  // Reveal: open on India, then fly to the GBN pilot
  setTimeout(() => map.fitBounds(GBN_BOUNDS, { padding: 60, duration: 2500 }), 1200);
});

document.getElementById('btn-india').onclick =
  () => map.flyTo({ center: INDIA_CENTER, zoom: 3.6, duration: 1500 });
document.getElementById('btn-gbn').onclick =
  () => map.fitBounds(GBN_BOUNDS, { padding: 60, duration: 1500 });
