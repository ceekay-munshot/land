#!/usr/bin/env python3
"""Reverse-engineer IGRSUP's property/deed search so we can pull per-gata transfer history.
Extracts form actions, dropdown-cascade AJAX endpoints, and the deed-search submission from
the page + its JS. Writes _probe/igrsup_deedsearch.json. Resilient + always writes.
"""
import os
import re
import json
import time
import requests

requests.packages.urllib3.disable_warnings()
BASE = "https://igrsup.gov.in"
URL = BASE + "/igrsup/newPropertySearchAction"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
ENDPOINT_RE = re.compile(
    r"(?i)[\"']([^\"']*(?:Action|\.action|propertySearch|DeedSearch|[Kk]hasra|getTehsil|"
    r"getGaon|getVillage|getDistrict|getSro|getMauja|fillTehsil|fillGaon|search)[^\"']*)[\"']")


def get(u):
    for i in range(4):
        try:
            return requests.get(u, headers={"User-Agent": UA}, timeout=45, verify=False)
        except Exception:
            time.sleep(2 * (i + 1))
    return None


out = {}
try:
    r = get(URL)
    html = r.text if r else ""
    out["page_len"] = len(html)
    out["form_actions"] = re.findall(r'<form[^>]*action=["\']([^"\']+)["\']', html, re.I)[:10]
    out["selects"] = re.findall(r'<select[^>]*\bid=["\']([^"\']+)["\']', html, re.I)[:20]
    out["onchange"] = sorted(set(re.findall(r'onchange=["\']([^"\']+)["\']', html, re.I)))[:20]
    out["onclick"] = sorted(set(re.findall(r'onclick=["\']([^"\']+)["\']', html, re.I)))[:25]
    out["ajax_urls"] = sorted(set(re.findall(r'url\s*:\s*["\']([^"\']+)["\']', html)))[:30]
    out["endpoints_in_html"] = sorted(set(m.group(1) for m in ENDPOINT_RE.finditer(html)))[:40]
    jsf = set(re.findall(r'<script[^>]*src=["\']([^"\']+\.js)["\']', html, re.I))
    out["js_files"] = sorted(jsf)
    out["js_scan"] = []
    for j in sorted(jsf):
        ju = j if j.startswith("http") else BASE + "/" + j.lstrip("/")
        rj = get(ju)
        if rj and rj.status_code == 200:
            t = rj.text
            out["js_scan"].append({"url": ju, "len": len(t),
                                   "endpoints": sorted(set(m.group(1) for m in ENDPOINT_RE.finditer(t)))[:40],
                                   "ajax": sorted(set(re.findall(r'url\s*:\s*["\']([^"\']+)["\']', t)))[:20]})
except Exception as e:
    out["fatal_error"] = repr(e)[:300]

os.makedirs("_probe", exist_ok=True)
json.dump(out, open("_probe/igrsup_deedsearch.json", "w"), ensure_ascii=False, indent=2)
print("page_len:", out.get("page_len"), "| form_actions:", out.get("form_actions"))
print("onchange:", out.get("onchange"))
print("ajax_urls:", out.get("ajax_urls"))
print("endpoints_in_html:", out.get("endpoints_in_html"))
print("js_files:", out.get("js_files"))
print("fatal_error:", out.get("fatal_error"))
