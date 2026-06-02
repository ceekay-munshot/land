// Passive network capture of the UP Bhu-Naksha Angular app, run under Playwright
// on a GitHub Actions runner (free, unrestricted egress). Goal: reveal the real
// API base, district/tehsil/village endpoints, and the GeoServer WMS base.
import { chromium } from 'playwright';
import { promises as fs } from 'fs';

const ENTRY = 'https://upbhunaksha.gov.in/';
const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36';
const INTERESTING = /(\/api\/|geoserver|\/wms|\/wfs|getfeatureinfo|getcapabilities|\.json|bhunaksha|scalar|district|tehsil|village|plot|captcha)/i;
const SKIP = /\.(png|jpe?g|gif|svg|woff2?|ttf|eot|css|ico|map)(\?|$)/i;

const seen = [];
const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: UA });
const page = await ctx.newPage();

page.on('response', async (res) => {
  const url = res.url();
  if (SKIP.test(url) || !INTERESTING.test(url)) return;
  const ct = res.headers()['content-type'] || '';
  let body = '';
  try {
    if (/json|text|xml/i.test(ct)) body = (await res.text()).slice(0, 500).replace(/\s+/g, ' ');
  } catch { /* ignore */ }
  seen.push({ method: res.request().method(), status: res.status(), ct, url, body });
});

console.log('goto', ENTRY);
try {
  await page.goto(ENTRY, { waitUntil: 'networkidle', timeout: 60000 });
} catch (e) {
  console.log('goto warning:', e.message);
}
await page.waitForTimeout(6000);

// best-effort: open the first dropdown to trigger option-loading API calls
try {
  const combo = await page.$('mat-select, select, [role=combobox], .mat-mdc-select');
  if (combo) {
    console.log('clicking a combobox to trigger hierarchy calls...');
    await combo.click({ timeout: 3000 });
    await page.waitForTimeout(4000);
  } else {
    console.log('no obvious combobox found');
  }
} catch (e) {
  console.log('combo click warning:', e.message);
}

try {
  const controls = await page.$$eval('select, mat-select, [role=combobox], .mat-mdc-select',
    els => els.slice(0, 8).map(e => (e.getAttribute('formcontrolname') || e.id || e.className || e.tagName)));
  console.log('=== CONTROLS ===', JSON.stringify(controls));
} catch { /* ignore */ }

await page.screenshot({ path: '/tmp/shot.png', fullPage: true }).catch(() => {});
await fs.writeFile('/tmp/page.html', await page.content()).catch(() => {});

console.log('\n=== CAPTURED NETWORK (interesting only) ===');
for (const r of seen) {
  console.log(`[${r.status}] ${r.method} ${r.url}  (${r.ct})`);
  if (r.body) console.log(`      body: ${r.body}`);
}
console.log(`\nTOTAL interesting calls: ${seen.length}`);

await browser.close();
