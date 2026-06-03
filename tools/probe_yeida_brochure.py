#!/usr/bin/env python3
"""One-off probe: can Firecrawl extract YEIDA brochure PDFs as TEXT?

The live schemes link to brochure PDFs that contain YEIDA's reserve price (Rs/sqm) by
sector — the signal that actually drives a buy decision. This checks whether that table
is machine-readable text (buildable) or an image scan (would need OCR — pivot).

Scrapes the RPS10/2026 residential brochure and dumps the result to _probe/.
Needs FIRECRAWL_API_KEY. Runs on GitHub Actions.
"""
import os
import re
import sys
import json
import urllib.request

KEY = os.environ.get("FIRECRAWL_API_KEY")
os.makedirs("_probe", exist_ok=True)
SUMMARY = "_probe/yeida_brochure_probe.json"

if not KEY:
    json.dump([{"status": "no key yet"}], open(SUMMARY, "w"))
    sys.exit(0)

PDFS = {
    "rps10_residential": "https://www.yamunaexpresswayauthority.com/web/wp-content/uploads/2026/04/FINAL_YEIDA-brochure-A4-_04-04-26.pdf",
}

PRICE_RE = re.compile(
    r"(?i)(reserve price|allotment rate|premium|per\s*sq\.?\s*m|/\s*sqm|sq\.?\s*mtr|"
    r"rate of|₹|rs\.?\s*[0-9][0-9,]*|sector[- ]?\d+)")


def scrape(u):
    body = json.dumps({"url": u, "formats": ["markdown"], "proxy": "stealth",
                       "location": {"country": "IN"}, "parsePDF": True,
                       "timeout": 120000}).encode()
    req = urllib.request.Request("https://api.firecrawl.dev/v1/scrape", data=body,
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=180)).get("data", {}) or {}


summary = []
for name, u in PDFS.items():
    rec = {"name": name, "url": u}
    try:
        d = scrape(u)
        md = d.get("markdown") or ""
        open(f"_probe/yeida_brochure_{name}.md", "w").write(md)
        hits = PRICE_RE.findall(md)
        rec.update(ok=True, md_len=len(md), price_sector_hits=len(hits),
                   sample=list(dict.fromkeys(hits))[:15],
                   pages=(d.get("metadata") or {}).get("numPages"))
    except Exception as e:
        rec.update(ok=False, error=str(e)[:250])
    summary.append(rec)
    print(json.dumps(rec, ensure_ascii=False)[:600])

json.dump(summary, open(SUMMARY, "w"), ensure_ascii=False, indent=2)
