#!/usr/bin/env python3
"""Locate 'Nalgadha' (Noida side) in UP Bhu-Naksha for Gautam Buddh Nagar — find its
tehsil + village code so we can pull its gata register (the spine of the title history).

Dumps every tehsil + village (so we can eyeball it even if the Hindi spelling differs) and
flags name matches to _probe/nalgadha_locate.json. Free: runs from a GitHub Actions US runner.
"""
import os
import json
import requests

BASE = "https://upbhunaksha.gov.in/bhunakshaserver"
HOME = "https://upbhunaksha.gov.in/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
NEEDLES = ["नलगढ", "नलगड", "नलगढ़", "नल गढ"]

s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": HOME, "Origin": "https://upbhunaksha.gov.in",
                  "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/plain, */*"})
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def level(n, codes=""):
    return s.post(f"{BASE}/masterdata/levelvalue", data={"level": n, "codes": codes},
                  headers=FORM, timeout=40).json()


def find(items, needle):
    return next((it for it in items if needle in (it.get("value") or "")), None)


s.get(HOME, timeout=40)
d = find(level(1, ""), "गौतम")
if not d:
    raise SystemExit("Gautam Buddh Nagar district not found")

out = {"district": d, "tehsils": [], "matches": []}
for t in level(2, d["code"]):
    villages = level(3, f'{d["code"]},{t["code"]}')
    out["tehsils"].append({"tehsil": t["value"], "code": t["code"], "village_count": len(villages),
                           "villages": [{"code": v["code"], "value": v["value"]} for v in villages]})
    for v in villages:
        if any(n in (v["value"] or "") for n in NEEDLES):
            out["matches"].append({"tehsil": t["value"], "tehsil_code": t["code"],
                                   "village": v["value"], "village_code": v["code"]})

os.makedirs("_probe", exist_ok=True)
json.dump(out, open("_probe/nalgadha_locate.json", "w"), ensure_ascii=False, indent=2)
print("DISTRICT:", d["value"], d["code"])
for x in out["tehsils"]:
    print(f'  tehsil {x["tehsil"]} ({x["code"]}): {x["village_count"]} villages')
print("MATCHES:", json.dumps(out["matches"], ensure_ascii=False))
