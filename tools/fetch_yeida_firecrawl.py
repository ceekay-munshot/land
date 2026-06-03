#!/usr/bin/env python3
"""Scrape the Cloudflare-protected YEIDA portal via Firecrawl (India proxy + stealth).

CONFIRMED: stealth + IN beats Cloudflare (homepage + schemes archive returned full
content). This version (a) targets the real notices page instead of the dead legacy
URL, (b) saves FULL page markdown so we can refine the parser against real text, and
(c) takes a first pass at parsing the homepage "Live Scheme" section into a structured
feed at web/data/yeida_schemes.json.

Runs on GitHub Actions (egress). Needs the FIRECRAWL_API_KEY repo secret.
"""
import os
import sys
import re
import json
import datetime
import urllib.request

KEY = os.environ.get("FIRECRAWL_API_KEY")
os.makedirs("_probe", exist_ok=True)
os.makedirs("web/data", exist_ok=True)
SUMMARY = "_probe/yeida_firecrawl.json"

if not KEY:
    print("FIRECRAWL_API_KEY secret not set — add it in repo Settings > Secrets and "
          "variables > Actions, then re-run this workflow.")
    json.dump({"status": "no key yet"}, open(SUMMARY, "w"))
    sys.exit(0)

URLS = {
    "home": "https://www.yamunaexpresswayauthority.com/",
    "notifications": "https://www.yamunaexpresswayauthority.com/web/notifications/",
    "schemes_archive": "https://www.yamunaexpresswayauthority.com/web/property/schemes/schemes-archives/",
}
print(f"FIRECRAWL_API_KEY detected (len={len(KEY)}); scraping {len(URLS)} YEIDA URLs via stealth + IN")


def scrape(u):
    body = json.dumps({"url": u, "formats": ["markdown", "links"],
                       "proxy": "stealth", "location": {"country": "IN"},
                       "onlyMainContent": True, "timeout": 90000}).encode()
    req = urllib.request.Request("https://api.firecrawl.dev/v1/scrape", data=body,
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json"})
    res = json.load(urllib.request.urlopen(req, timeout=150))
    return res.get("data", {}) or {}


def parse_live_schemes(md):
    """Best-effort extraction of the homepage 'Live Scheme' list -> structured items.
    First pass; refined against the full markdown saved in _probe/."""
    m = re.search(r"##\s*Live Scheme(.*?)(?:\n#{1,2}\s|\Z)", md, re.S)
    if not m:
        return []
    block = m.group(1)
    out = []
    for chunk in re.split(r"\n\s*-\s+(?=\[)", block):
        links = re.findall(r"\[([^\]]*)\]\(([^)]+)\)", chunk)
        scheme, apply_url = None, None
        for raw_text, url in links:
            txt = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", raw_text).replace("\\", " ")
            txt = re.sub(r"\s+", " ", txt).strip()
            u = url.strip()
            if re.search(r"apply now|check status", raw_text, re.I):
                apply_url = u
                continue
            if not txt or u.endswith("#") or "blink" in u:
                continue
            if scheme is None:
                scheme = (txt, u)
        if not scheme:
            continue
        title, url = scheme
        low = title.lower()
        code = re.search(r"([A-Z]{2,6}[-/][A-Za-z0-9()./-]*\d|[A-Z]{2,5}\d+/\d{4})", title)
        deadline = re.search(r"Extended\s*-\s*([0-9]{1,2}-[0-9]{1,2}-[0-9]{4}[^\n]*)", chunk)
        if any(k in low for k in ("residential", "rps")):
            cat = "Residential"
        elif any(k in low for k in ("industrial", "mdp", "ind-")):
            cat = "Industrial"
        elif any(k in low for k in ("institution", "hospital", "nursery", "school",
                                    "welfare", "maternity", "creche")):
            cat = "Institutional"
        elif any(k in low for k in ("hotel", "commercial", "shop")):
            cat = "Commercial"
        elif any(k in low for k in ("mlu", "mixed")):
            cat = "Mixed land use"
        else:
            cat = "Other"
        out.append({"title": title, "code": code.group(1) if code else None,
                    "category": cat, "deadline": deadline.group(1).strip() if deadline else None,
                    "brochure_or_status_url": url, "apply_url": apply_url})
    return out


now = datetime.datetime.utcnow().isoformat() + "Z"
summary = {"fetched_at": now, "pages": []}
home_md = ""
for slug, u in URLS.items():
    rec = {"slug": slug, "url": u}
    try:
        d = scrape(u)
        md = d.get("markdown") or ""
        open(f"_probe/yeida_{slug}.md", "w").write(md)
        json.dump(d.get("links") or [], open(f"_probe/yeida_{slug}_links.json", "w"), indent=1)
        rec.update(success=True, md_len=len(md), n_links=len(d.get("links") or []),
                   title=(d.get("metadata") or {}).get("title"),
                   has_live_scheme=("Live Scheme" in md))
        if slug == "home":
            home_md = md
    except Exception as e:
        rec.update(success=False, error=str(e)[:300])
    summary["pages"].append(rec)
    print(slug, "| ok:", rec.get("success"), "| md_len:", rec.get("md_len"),
          "| err:", rec.get("error", ""))

schemes = parse_live_schemes(home_md)
json.dump({"source": "YEIDA official portal — Live Scheme section, via Firecrawl (stealth + IN)",
           "url": URLS["home"], "fetched_at": now, "count": len(schemes), "schemes": schemes},
          open("web/data/yeida_schemes.json", "w"), ensure_ascii=False, indent=2)
summary["live_schemes_parsed"] = len(schemes)
json.dump(summary, open(SUMMARY, "w"), ensure_ascii=False, indent=2)
print(f"parsed {len(schemes)} live schemes -> web/data/yeida_schemes.json")
