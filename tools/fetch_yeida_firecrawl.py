#!/usr/bin/env python3
"""Scrape the Cloudflare-protected YEIDA portal via Firecrawl (India proxy + stealth).

CONFIRMED: stealth + IN beats Cloudflare. Saves full page markdown to _probe/ and parses
the homepage "Live Scheme" section into a structured feed at web/data/yeida_schemes.json.

The parser is importable and runs against saved markdown, so it can be iterated locally
WITHOUT spending Firecrawl credits:
    python3 -c "from tools.fetch_yeida_firecrawl import parse_live_schemes as p, json; \
                print(json.dumps(p(open('_probe/yeida_home.md').read()), indent=2))"

Runs on GitHub Actions (egress). Needs the FIRECRAWL_API_KEY repo secret.
"""
import os
import sys
import re
import json
import datetime
import urllib.request

# Only the homepage carries live, text-structured signal (the "Live Scheme" list).
# The notices page is image-based (WhatsApp screenshots → no extractable text) and the
# schemes archive is static history, so the weekly scrape targets the homepage only —
# cheaper (~1 page) and no junk. Re-add others here if we ever add OCR / archive diffing.
URLS = {
    "home": "https://www.yamunaexpresswayauthority.com/",
}


def categorize(title):
    low = title.lower()
    if any(k in low for k in ("residential", "rps")):
        return "Residential"
    if any(k in low for k in ("industrial", "mdp", "ind-", "ind8000", "/ind")):
        return "Industrial"
    if any(k in low for k in ("institution", "hospital", "nursery", "school",
                              "welfare", "maternity", "creche")):
        return "Institutional"
    if any(k in low for k in ("hotel", "commercial", "footprint", "shop", "chp", "cfp", "cscm")):
        return "Commercial"
    if any(k in low for k in ("mlu", "mix land", "mixed")):
        return "Mixed land use"
    return "Other"


def parse_live_schemes(md):
    """Extract the homepage 'Live Scheme' list -> structured items.

    YEIDA markup per item:  - [Name \\ \\ CODE Brochure](brochure_or_status_url)![](blink.gif)
    optionally followed by  Extended - DD-MM-YYYY [- H:MMPM]  and a nested
    [![](arrow) Apply now|Check Status](portal_url) link.
    """
    m = re.search(r"##\s*Live Scheme(.*?)(?:\n#{1,2}\s|\Z)", md, re.S)
    if not m:
        return []
    block = m.group(1)
    out = []
    for chunk in re.split(r"\n\s*-\s+(?=\[)", block):
        sm = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", chunk)
        if not sm:
            continue
        raw_text, url = sm.group(1), sm.group(2).strip()
        if "blink" in url or url.endswith("#"):
            continue
        title = re.sub(r"\s+", " ", raw_text.replace("\\", " ")).strip()
        if not title or re.match(r"(apply now|check status)$", title, re.I):
            continue
        # code = last backslash-delimited segment of the link text, cleaned
        segs = [s.strip() for s in raw_text.split("\\") if s.strip()]
        code_line = segs[-1] if segs else title
        code = re.sub(r"\b(Brochure|Scheme|Plots?|Applications?)\b", "", code_line, flags=re.I)
        code = re.sub(r"^\s*\d+\s+", "", code).strip(" ,")
        code = re.sub(r"\s+", " ", code) or None
        # application / status portal (handles nested image-in-link markup)
        am = re.search(r"(?:Apply now|Check Status)\]\((https?://[^)]+)\)", chunk, re.I)
        # deadline (stop at the date/time; don't swallow the trailing apply link)
        dm = re.search(r"Extended\s*-\s*([0-9]{1,2}-[0-9]{1,2}-[0-9]{4}"
                       r"(?:\s*-\s*\d{1,2}:\d{2}\s*[AP]M)?)", chunk)
        secm = re.search(r"Sec-?\s*([0-9]+(?:\s*,\s*[0-9]+)*)", title)
        out.append({
            "title": title,
            "code": code,
            "category": categorize(title),
            "sector": secm.group(1) if secm else None,
            "deadline": dm.group(1).strip() if dm else None,
            "brochure_or_status_url": url,
            "apply_url": am.group(1) if am else None,
        })
    return out


def scrape(u, key):
    body = json.dumps({"url": u, "formats": ["markdown", "links"],
                       "proxy": "stealth", "location": {"country": "IN"},
                       "onlyMainContent": True, "timeout": 90000}).encode()
    req = urllib.request.Request("https://api.firecrawl.dev/v1/scrape", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    res = json.load(urllib.request.urlopen(req, timeout=150))
    return res.get("data", {}) or {}


def main():
    key = os.environ.get("FIRECRAWL_API_KEY")
    os.makedirs("_probe", exist_ok=True)
    os.makedirs("web/data", exist_ok=True)
    summary_path = "_probe/yeida_firecrawl.json"
    if not key:
        print("FIRECRAWL_API_KEY secret not set — add it in repo Settings > Secrets and "
              "variables > Actions, then re-run this workflow.")
        json.dump({"status": "no key yet"}, open(summary_path, "w"))
        return
    print(f"FIRECRAWL_API_KEY detected (len={len(key)}); scraping {len(URLS)} YEIDA URLs via stealth + IN")

    now = datetime.datetime.utcnow().isoformat() + "Z"
    summary = {"fetched_at": now, "pages": []}
    home_md = ""
    for slug, u in URLS.items():
        rec = {"slug": slug, "url": u}
        try:
            d = scrape(u, key)
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
    json.dump(summary, open(summary_path, "w"), ensure_ascii=False, indent=2)
    print(f"parsed {len(schemes)} live schemes -> web/data/yeida_schemes.json")


if __name__ == "__main__":
    main()
