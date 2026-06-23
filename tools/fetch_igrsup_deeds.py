#!/usr/bin/env python3
"""SCAFFOLD / EXPERIMENTAL — pull real deed/transfer history per gata from IGRSUP.

This does NOT yet produce registry-verified data. It is the wiring for the real
source that will eventually REPLACE the reconstructed history written by
tools/gen_nalgadha_history.py. It writes the IDENTICAL schema
(web/data/nalgadha_history.json: {meta, histories}) but with
confidence="registry" once a deed parser is implemented.

Reverse-engineered form (see tools/probe_igrsup_deedsearch.py, tools/capture_igrsup.mjs,
_probe/igrsup_deedsearch.json): IGRSUP property search at
  https://igrsup.gov.in/igrsup/newPropertySearchAction
with fields districtCode=141 (Gautam Buddh Nagar), sroCode (SRO, env-overridable),
gaonOderedNEWlist/villageCode=120241 (Nalgadha), Khasra_Number=<plot_no>, and the
submit action PropertyDeedSearch. The portal is captcha/session gated, so a live
sweep needs captcha handling + session (jsessionid) management that is NOT built yet.

SAFETY: by default this runs in --dry-run mode — it makes ZERO network calls,
builds the request bodies, validates it can read the parcels, and writes a
schema-valid STUB to _probe/ (it does NOT clobber the shipped reconstructed
web/data/nalgadha_history.json). Use --live to attempt real requests (best-effort),
and --force to overwrite the shipped history file.

Usage:
  python3 tools/fetch_igrsup_deeds.py              # safe dry-run (no network)
  IGRSUP_DRYRUN=1 python3 tools/fetch_igrsup_deeds.py
  python3 tools/fetch_igrsup_deeds.py --live --force   # experimental, needs captcha
"""
import os
import sys
import json
import time
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARCELS = os.path.join(ROOT, "web", "data", "nalgadha_parcels.geojson")
LIVE_OUT = os.path.join(ROOT, "web", "data", "nalgadha_history.json")
DRY_OUT = os.path.join(ROOT, "_probe", "igrsup_deeds_dryrun.json")

BASE = "https://igrsup.gov.in"
URL = BASE + "/igrsup/newPropertySearchAction"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

DISTRICT_CODE = os.environ.get("IGRSUP_DISTRICT", "141")    # Gautam Buddh Nagar
VILLAGE_CODE = os.environ.get("IGRSUP_VILLAGE", "120241")   # Nalgadha
SRO_CODE = os.environ.get("IGRSUP_SRO", "")                 # SRO Sadar — TODO confirm


def load_plots():
    geo = json.load(open(PARCELS, encoding="utf-8"))
    return [str(f["properties"]["plot_no"]) for f in geo.get("features", [])]


def request_body(plot_no):
    """The exact form payload IGRSUP expects for a per-khasra deed search."""
    return {
        "districtCode": DISTRICT_CODE,
        "sroCode": SRO_CODE,
        "gaonOderedNEWlist": VILLAGE_CODE,
        "villageCode3": VILLAGE_CODE,
        "Khasra_Number": plot_no,
        "PropertyDeedSearch": "Search",
    }


def parse_deeds(html, plot_no):
    """TODO: parse the IGRSUP results table into transfer events.

    Each row should map to the shared schema event:
      {date, deed_no, type, from[], to[], share, consideration_inr,
       source:"IGRSUP", confidence:"registry"}
    Not implemented — IGRSUP returns a captcha-gated results page first.
    """
    return []  # no parser yet


def fetch_live(plots, budget_s=600):
    import requests  # only needed in live mode
    requests.packages.urllib3.disable_warnings()
    histories = {}
    t0 = time.time()
    for plot_no in plots:
        if time.time() - t0 > budget_s:
            print(f"  budget reached; stopped at gata {plot_no}", file=sys.stderr)
            break
        body = request_body(plot_no)
        events = []
        for attempt in range(3):
            try:
                r = requests.post(URL, data=body, headers={"User-Agent": UA},
                                  timeout=45, verify=False)
                events = parse_deeds(r.text, plot_no)
                break
            except Exception:
                time.sleep(2 * (attempt + 1))
        if events:
            histories[plot_no] = {"plot_no": plot_no, "events": events}
        time.sleep(0.1)  # be polite to the govt portal
    return histories


def wrap(histories, mode):
    return {
        "meta": {
            "village": "नलगढ़ा",
            "village_code": VILLAGE_CODE,
            "district_code": DISTRICT_CODE,
            "generated_by": "tools/fetch_igrsup_deeds.py",
            "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "schema_version": 1,
            "source": "IGRSUP newPropertySearchAction (SCAFFOLD)",
            "mode": mode,
            "disclaimer": ("Experimental IGRSUP deed fetch. Deed parser + captcha "
                           "handling NOT yet implemented; histories is empty until "
                           "then. Schema matches tools/gen_nalgadha_history.py so "
                           "real registry data (confidence='registry') can replace "
                           "the reconstructed seed."),
        },
        "histories": histories,
    }


def main():
    args = set(sys.argv[1:])
    live = ("--live" in args) and (os.environ.get("IGRSUP_DRYRUN") != "1")
    force = "--force" in args

    plots = load_plots()
    print(f"loaded {len(plots)} gata plot numbers from {os.path.relpath(PARCELS, ROOT)}")
    # always show we can build a valid request body
    print("sample request body:", json.dumps(request_body(plots[0]), ensure_ascii=False))

    if not live:
        out = wrap({}, "dry-run")
        os.makedirs(os.path.dirname(DRY_OUT), exist_ok=True)
        json.dump(out, open(DRY_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"DRY-RUN (no network): wrote schema-valid stub to "
              f"{os.path.relpath(DRY_OUT, ROOT)} ({len(plots)} plots prepared, 0 deeds)")
        print("note: shipped web/data/nalgadha_history.json (reconstructed) left untouched.")
        return

    histories = fetch_live(plots)
    if not histories:
        print("LIVE: 0 deeds parsed (parser/captcha not implemented). "
              "Refusing to overwrite shipped history with an empty file.", file=sys.stderr)
        out = wrap({}, "live-empty")
        os.makedirs(os.path.dirname(DRY_OUT), exist_ok=True)
        json.dump(out, open(DRY_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return
    if os.path.exists(LIVE_OUT) and not force:
        print(f"{os.path.relpath(LIVE_OUT, ROOT)} exists; pass --force to overwrite "
              f"with registry data.", file=sys.stderr)
        return
    json.dump(wrap(histories, "live"), open(LIVE_OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"LIVE: wrote {len(histories)} gata histories to {os.path.relpath(LIVE_OUT, ROOT)}")


if __name__ == "__main__":
    main()
