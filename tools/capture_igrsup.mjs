// Drive IGRSUP's property/deed search under Playwright to capture the exact POST recipe:
// district -> tehsil -> village (Nalgadha) -> Khasra -> deed results. Dumps dropdown codes +
// captured POST bodies + the results HTML to _probe/igrsup_capture.json so we can replay it
// per gata with raw requests. Best-effort: logs each step even if a later one fails.
import { chromium } from 'playwright';
import { promises as fs } from 'fs';

const URL = 'https://igrsup.gov.in/igrsup/newPropertySearchAction';
const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36';
const posts = [];
const log = { steps: [] };

const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: UA });
const page = await ctx.newPage();

page.on('request', (req) => {
  if (/newPropertySearchAction|Khasra|Gaon|Tehsil|District|Sro/i.test(req.url())) {
    let pd = ''; try { pd = (req.postData() || '').slice(0, 800); } catch { /* */ }
    if (req.method() === 'POST') posts.push({ url: req.url().slice(0, 130), post: pd });
  }
});

async function opts(id) {
  try { return await page.$eval('#' + id, (s) => [...s.options].map((o) => ({ v: o.value, t: o.text.trim() })).filter((o) => o.v).slice(0, 90)); }
  catch { return null; }
}
async function pick(id, re) {
  const list = await opts(id);
  const hit = (list || []).find((o) => re.test(o.t));
  if (hit) { try { await page.selectOption('#' + id, hit.v); await page.waitForTimeout(4000); } catch (e) { log.steps.push('select ' + id + ' err: ' + e.message); } }
  return { list, hit };
}

try {
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(2500);
  log.inputs = await page.$$eval('input,select', (els) => els.map((e) => ({ tag: e.tagName, name: e.name, id: e.id, type: e.type })).filter((e) => e.name || e.id).slice(0, 60));

  const dist = await pick('districtCode', /गौतम|GAUTAM|Gautam/);
  log.district = dist.hit; log.districts_sample = (dist.list || []).slice(0, 5);
  const teh = await pick('tehsilCode', /गौतमबुद्ध|गौतम बुद्ध|सदर|GAUTAM/);
  log.tehsil = teh.hit; log.tehsils = teh.list;
  let vil = await pick('gaonOderedNEWlist', /नलगढ|नलगड/);
  if (!vil.hit) vil = await pick('villageCode3', /नलगढ|नलगड/);
  log.village = vil.hit; log.villages_sample = (vil.list || []).slice(0, 8);

  // try to enter a khasra + submit the deed search
  for (const sel of ['input[name="Khasra_Number"]', '#Khasra_Number', 'input[name*="hasra"]']) {
    try { await page.fill(sel, '98'); log.khasra_filled = sel; break; } catch { /* */ }
  }
  for (const sel of ['input[name="PropertyDeedSearch"]', 'input[value*="Deed"]', 'button:has-text("Search")', 'input[type="submit"]']) {
    try { await page.click(sel, { timeout: 3000 }); log.searched = sel; await page.waitForTimeout(5000); break; } catch { /* */ }
  }
  log.result_html = (await page.content()).replace(/\s+/g, ' ').slice(0, 2500);
} catch (e) {
  log.fatal = e.message;
}

log.posts = posts;
await fs.mkdir('_probe', { recursive: true }).catch(() => {});
await fs.writeFile('_probe/igrsup_capture.json', JSON.stringify(log, null, 2));
console.log('district:', JSON.stringify(log.district), '| tehsil:', JSON.stringify(log.tehsil), '| village:', JSON.stringify(log.village));
console.log('khasra_filled:', log.khasra_filled, '| searched:', log.searched, '| POSTs:', posts.length, '| fatal:', log.fatal);
await browser.close();
