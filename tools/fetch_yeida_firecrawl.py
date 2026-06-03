#!/usr/bin/env python3
"""Scrape the Cloudflare-protected YEIDA portal via Firecrawl (India proxy + stealth).

CONFIRMED: stealth + IN beats Cloudflare. Parses the homepage "Live Scheme" list into
web/data/yeida_schemes.json and enriches each scheme with the buy-decision economics
(rate Rs/sqm, sectors, plot sizes) extracted from its brochure PDF.

Brochures are static, so their raw text is cached under _probe/brochures/ and only NEW
brochures are scraped — and only when SCRAPE_BROCHURES=1 (so the weekly run never spends
brochure credits unless we ask it to). Enrichment from cache is free.

The parser/extractor are importable and run against saved markdown, so they iterate
locally WITHOUT spending Firecrawl credits.

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
    """Extract the homepage 'Live Scheme' list -> structured items."""
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
        segs = [s.strip() for s in raw_text.split("\\") if s.strip()]
        code_line = segs[-1] if segs else title
        code = re.sub(r"\b(Brochure|Scheme|Plots?|Applications?)\b", "", code_line, flags=re.I)
        code = re.sub(r"^\s*\d+\s+", "", code).strip(" ,")
        code = re.sub(r"\s+", " ", code) or None
        am = re.search(r"(?:Apply now|Check Status)\]\((https?://[^)]+)\)", chunk, re.I)
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


def brochure_cache_path(url):
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", url.rsplit("/", 1)[-1])[:90]
    return f"_probe/brochures/{slug}.md"


def extract_brochure_fields(md):
    """Pull the buy-decision economics out of a scheme brochure (best-effort, null on miss)."""
    out = {"rate_per_sqm": None, "sectors": None, "plot_sizes_sqm": None,
           "rera": None, "lease_years": None}
    nums = []
    for r in re.findall(r"([\d,]{4,}(?:\.\d+)?)\s*(?:/-)?\s*per\s*sq\.?\s*m", md, re.I):
        try:
            nums.append(float(r.replace(",", "")))
        except ValueError:
            pass
    if nums:
        out["rate_per_sqm"] = int(max(nums))
    sm = (re.search(r"(?:allotment|invites application|scheme)[^.]{0,140}?"
                    r"Sector[- ]?([0-9A-Za-z][0-9A-Za-z,\s&/-]*?)\s+(?:of size|along|under|,?\s*RERA)",
                    md, re.I)
          or re.search(r"in\s+Sector[- ]?([0-9A-Za-z][0-9A-Za-z,\s&/-]*?)\s+of\s+size", md, re.I))
    if sm:
        secs = list(dict.fromkeys(re.findall(r"\d+[A-Z]?", sm.group(1))))
        if secs:
            out["sectors"] = ", ".join(secs)
    pm = re.search(r"of\s+size\s+([0-9][0-9,\s&]*?)\s*Sq\.?\s*Mtr", md, re.I)
    if pm:
        sizes = [int(x) for x in re.findall(r"\d+", pm.group(1))]
        if sizes:
            out["plot_sizes_sqm"] = sizes
    rm = re.search(r"(UPRERA[A-Z0-9/]+)", md)
    if rm:
        out["rera"] = rm.group(1)
    lm = re.search(r"lease\s+(?:of\s+)?(\d{2,3})\s*years", md, re.I)
    if lm:
        out["lease_years"] = int(lm.group(1))
    return out


def enrich_with_brochures(schemes, key, allow_scrape):
    """Attach brochure economics to each scheme. Reads cached brochure text for free;
    scrapes a not-yet-cached brochure only when allow_scrape is True."""
    os.makedirs("_probe/brochures", exist_ok=True)
    for s in schemes:
        url = s.get("brochure_or_status_url") or ""
        if not url.lower().endswith(".pdf"):
            continue
        path = brochure_cache_path(url)
        md = ""
        if os.path.exists(path):
            md = open(path).read()
        elif allow_scrape and key:
            try:
                md = scrape(url, key).get("markdown") or ""
                open(path, "w").write(md)
                print("scraped brochure:", url, "->", len(md), "chars")
            except Exception as e:
                s["brochure"] = {"error": str(e)[:150]}
                continue
        else:
            continue  # not cached and scraping disabled — leave unenriched
        if md:
            s["brochure"] = extract_brochure_fields(md)


def scrape(u, key):
    body = json.dumps({"url": u, "formats": ["markdown", "links"],
                       "proxy": "stealth", "location": {"country": "IN"},
                       "onlyMainContent": True, "parsePDF": True, "timeout": 120000}).encode()
    req = urllib.request.Request("https://api.firecrawl.dev/v1/scrape", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    res = json.load(urllib.request.urlopen(req, timeout=180))
    return res.get("data", {}) or {}


def main():
    key = os.environ.get("FIRECRAWL_API_KEY")
    allow_scrape_brochures = os.environ.get("SCRAPE_BROCHURES") == "1"
    os.makedirs("_probe", exist_ok=True)
    os.makedirs("web/data", exist_ok=True)
    summary_path = "_probe/yeida_firecrawl.json"
    if not key:
        print("FIRECRAWL_API_KEY secret not set — add it in repo Settings > Secrets and "
              "variables > Actions, then re-run this workflow.")
        json.dump({"status": "no key yet"}, open(summary_path, "w"))
        return
    print(f"FIRECRAWL_API_KEY detected (len={len(key)}); scraping {len(URLS)} YEIDA URLs via stealth + IN"
          f" | brochure scraping: {'ON' if allow_scrape_brochures else 'cache-only'}")

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
    enrich_with_brochures(schemes, key, allow_scrape_brochures)
    n_priced = sum(1 for s in schemes if (s.get("brochure") or {}).get("rate_per_sqm"))
    json.dump({"source": "YEIDA official portal — Live Scheme section, via Firecrawl (stealth + IN)",
               "url": URLS["home"], "fetched_at": now, "count": len(schemes), "schemes": schemes},
              open("web/data/yeida_schemes.json", "w"), ensure_ascii=False, indent=2)
    summary["live_schemes_parsed"] = len(schemes)
    summary["schemes_priced"] = n_priced
    json.dump(summary, open(summary_path, "w"), ensure_ascii=False, indent=2)
    print(f"parsed {len(schemes)} live schemes ({n_priced} with brochure price) -> web/data/yeida_schemes.json")


if __name__ == "__main__":
    main()
