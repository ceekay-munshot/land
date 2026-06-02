// Capture the UP Bhu-Naksha API REQUEST + RESPONSE formats under Playwright on a
// free Actions runner: the masterdata/levelvalue request bodies (hierarchy) and
// the plot-identify GetFeatureInfo call (vector geometry) triggered by a map click.
import { chromium } from 'playwright';
import { promises as fs } from 'fs';

const ENTRY = 'https://upbhunaksha.gov.in/';
const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36';
const KEEP = /bhunakshaserver|getfeatureinfo|\/api\//i;
const SKIP = /\.(png|jpe?g|gif|svg|woff2?|ttf|eot|css|ico|map|js)(\?|$)/i;

const seen = [];
const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: UA });
const page = await ctx.newPage();

page.on('response', async (res) => {
  const req = res.request();
  const url = res.url();
  if (SKIP.test(url) || !KEEP.test(url)) return;
  const ct = res.headers()['content-type'] || '';
  let body = '';
  try { if (/json|text|xml/i.test(ct)) body = (await res.text()).slice(0, 700).replace(/\s+/g, ' '); } catch { /* */ }
  let post = '';
  try { post = (req.postData() || '').slice(0, 400); } catch { /* */ }
  seen.push({ method: req.method(), status: res.status(), url, ct, post, body });
});

console.log('goto', ENTRY);
try { await page.goto(ENTRY, { waitUntil: 'networkidle', timeout: 60000 }); }
catch (e) { console.log('goto warning:', e.message); }
await page.waitForTimeout(7000);

// Click the rendered map to trigger a plot GetFeatureInfo / getPlotInfo
try {
  const vp = await page.$('.ol-viewport, canvas, #map, .leaflet-container, .map-container');
  if (vp) {
    const box = await vp.boundingBox();
    if (box) {
      const pts = [[0.5, 0.5], [0.42, 0.46], [0.57, 0.54]];
      for (const [fx, fy] of pts) {
        const x = box.x + box.width * fx, y = box.y + box.height * fy;
        console.log('click map', Math.round(x), Math.round(y));
        await page.mouse.click(x, y);
        await page.waitForTimeout(2500);
      }
    }
  } else { console.log('no map viewport found'); }
} catch (e) { console.log('map click warning:', e.message); }

console.log('\n=== /bhunakshaserver + GetFeatureInfo CALLS (request + response) ===');
for (const r of seen) {
  console.log(`[${r.status}] ${r.method} ${r.url}`);
  if (r.post) console.log(`     REQ: ${r.post}`);
  if (r.body) console.log(`     RES: ${r.body}`);
}
console.log(`\nTOTAL captured: ${seen.length}`);
await fs.writeFile('/tmp/page.html', await page.content()).catch(() => {});
await browser.close();
