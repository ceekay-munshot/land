#!/usr/bin/env python3
"""Scrape the (Cloudflare-protected) YEIDA portal via Firecrawl — India proxy + stealth —
to get live scheme / public-notice signals for the Jewar development area.

Runs on GitHub Actions (egress). Needs the FIRECRAWL_API_KEY repo secret.
v1 = probe: dump what Firecrawl returns so we can confirm Cloudflare is beaten and
then build the notice parser. No key set yet -> exits cleanly.
"""
import os
import sys
import json
import urllib.request

KEY = os.environ.get("FIRECRAWL_API_KEY")
OUT = "_probe/yeida_firecrawl.json"
os.makedirs("_probe", exist_ok=True)

if not KEY:
    print("FIRECRAWL_API_KEY secret not set — add it in repo Settings > Secrets and "
          "variables > Actions, then re-run this workflow.")
    json.dump({"status": "no key yet"}, open(OUT, "w"))
    sys.exit(0)

URLS = [
    "https://www.yamunaexpresswayauthority.com/",
    "https://www.yamunaexpresswayauthority.com/web/property/schemes/schemes-archives/",
    "https://www.yamunaexpresswayauthority.com/taxonomy/term/1.html",
]


def scrape(u):
    body = json.dumps({
        "url": u,
        "formats": ["markdown", "links"],
        "proxy": "stealth",                 # beat Cloudflare bot challenge
        "location": {"country": "IN"},      # India egress for any geo-fence
        "onlyMainContent": True,
        "timeout": 90000,
    }).encode()
    req = urllib.request.Request("https://api.firecrawl.dev/v1/scrape", data=body,
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json"})
    res = json.load(urllib.request.urlopen(req, timeout=150))
    d = res.get("data", {}) or {}
    md = d.get("markdown") or ""
    return {"url": u, "success": res.get("success"), "md_len": len(md),
            "title": (d.get("metadata") or {}).get("title"),
            "md_head": md[:2000], "links": (d.get("links") or [])[:40]}


out = []
for u in URLS:
    try:
        out.append(scrape(u))
    except Exception as e:
        out.append({"url": u, "success": False, "error": str(e)[:400]})

json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=2)
for o in out:
    print(o.get("url"), "| ok:", o.get("success"), "| md_len:", o.get("md_len"),
          "| title:", o.get("title"), "| err:", o.get("error", ""))
