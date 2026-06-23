#!/usr/bin/env python3
"""Feasibility probe for the records layers (deeds / EC / Girdawari):
  - IGRSUP property search (registered deeds, ~2005+)
  - UP Bhulekh (Khatauni / Girdawari)
For each: reachable from a US Actions runner (or geo-fenced like YEIDA)? captcha-gated?
what form fields? Writes _probe/records_sources.json. Resilient: retries + always writes.
"""
import os
import re
import json
import time
import requests

requests.packages.urllib3.disable_warnings()
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
TARGETS = {
    "igrsup_home": "https://igrsup.gov.in/",
    "igrsup_property_search": "https://igrsup.gov.in/igrsup/newPropertySearchAction",
    "bhulekh_home": "https://upbhulekh.gov.in/",
    "bhulekh_public_ror": "https://upbhulekh.gov.in/public/public_ror/publicRor.jsp",
}


def get(url):
    for i in range(4):
        try:
            return requests.get(url, headers={"User-Agent": UA}, timeout=45, verify=False)
        except Exception as e:
            if i == 3:
                return e
            time.sleep(2 * (i + 1))


out = []
for name, url in TARGETS.items():
    rec = {"name": name, "url": url}
    r = get(url)
    if isinstance(r, Exception):
        rec["error"] = str(r)[:200]
    else:
        t = r.text or ""
        rec.update(status=r.status_code, ct=r.headers.get("content-type"), length=len(t),
                   captcha=bool(re.search(r"captcha|कैप्चा", t, re.I)),
                   indicators=sorted(set(re.findall(
                       r"(?i)captcha|khasra|gata|khatauni|girdawari|encumbrance|"
                       r"district|tehsil|village|registration", t)))[:25],
                   form_fields=sorted(set(re.findall(r'name=["\']([a-zA-Z_]{3,30})["\']', t)))[:30],
                   head=re.sub(r"\s+", " ", t[:400]))
    out.append(rec)

os.makedirs("_probe", exist_ok=True)
json.dump(out, open("_probe/records_sources.json", "w"), ensure_ascii=False, indent=2)
for r in out:
    print(r["name"], "|", r.get("status", r.get("error")), "| captcha:", r.get("captcha"),
          "| len:", r.get("length"))
