#!/usr/bin/env python3
"""Generate a RECONSTRUCTED (synthetic) chain-of-title for each gata in the
ownership layer (Nalgadha + neighbouring villages).

This is HONEST PLACEHOLDER data, in the same spirit as the rest of the repo
("the data is placeholder; the mechanism is real"). It does NOT represent real
registered transfers. Real deed history is to be sourced from IGRSUP
(see tools/fetch_igrsup_deeds.py), which writes the IDENTICAL schema with
confidence="registry".

Design choices that keep it honest:
  * Every event is flagged confidence="reconstructed".
  * Parties we cannot know are NEUTRAL placeholders ("मूल खातेदार (original
    holder)", "पूर्व खातेदार N (prior holder)") — we never invent realistic
    person names. Only the *current* owners (already public, from Bhu-Naksha)
    appear as the final transferees.
  * Records are keyed by uid = "<village>|<plot_no>" because gata numbers
    repeat across villages; the seed is the uid, so re-runs produce clean diffs
    and the file is rewritten only when the reconstructed content changes.

Usage:  python3 tools/gen_nalgadha_history.py
Writes: web/data/nalgadha_history.json
"""
import os
import json
import hashlib
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARCELS = os.path.join(ROOT, "web", "data", "nalgadha_parcels.geojson")
OWNERS = os.path.join(ROOT, "web", "data", "nalgadha_owners.json")
OUT = os.path.join(ROOT, "web", "data", "nalgadha_history.json")

THIS_YEAR = 2026
# Tokens that mark a "non-person" register entry (roads, ponds, fallow, civic).
# Plots whose owners are ALL non-person get no transfer history.
NON_PERSON = ["मार्ग", "नोएडा", "गड्ढे", "परती", "चक", "तालाब", "नाला",
              "खाद", "आबादी", "विद्यालय", "देवस्थान", "रास्ता", "नहर", "पोखर"]

ORIGINAL = "मूल खातेदार (original holder)"
def prior(n):
    return f"पूर्व खातेदार {n} (prior holder)"


def is_person(name):
    return not any(tok in name for tok in NON_PERSON)


def uid_of(village, plot_no):
    return f"{(village or '').strip()}|{plot_no}"


def rng_for(uid):
    """Deterministic PRNG seeded from the uid (stable diffs across villages)."""
    import random
    seed = int(hashlib.sha1(str(uid).encode("utf-8")).hexdigest(), 16) & 0xFFFFFFFF
    return random.Random(seed)


def rate_per_ha(year):
    """Synthetic land-rate curve (₹/ha) — clearly fabricated, ~13%/yr from 2005."""
    return 1_200_000 * (1.13 ** (year - 2005))


def value_for(area_ha, year, r):
    base = (area_ha or 0.5) * rate_per_ha(year)
    jitter = r.uniform(0.8, 1.25)
    v = base * jitter
    return int(round(v / 10000.0)) * 10000  # round to nearest ₹10k


def dstr(year, r):
    m = r.randint(1, 12)
    d = r.randint(1, 28)
    return f"{year:04d}-{m:02d}-{d:02d}"


def build_chain(uid, plot_no, khata_no, area_ha, owners):
    """Return a list of synthetic transfer events, oldest -> newest."""
    people = [o for o in owners if is_person(o)]
    if not people:
        return []  # common / civic land — no ownership transfers to show
    r = rng_for(uid)
    events = []
    n = 1

    # 1) Original holding (inheritance from an unknown original khatedar)
    y0 = THIS_YEAR - r.randint(11, 24)
    prior_idx = 1
    events.append(dict(date=dstr(y0, r), deed_no=f"RECON-{plot_no}-{n}",
                       type="inheritance", **{"from": [ORIGINAL]}, to=[prior(prior_idx)],
                       share="1/1", consideration_inr=0))
    n += 1
    last_holder = prior(prior_idx)
    last_year = y0

    # 2) Optional intermediate sale(s) between unknown prior holders
    hops = r.choice([0, 0, 1, 1, 2])
    for _ in range(hops):
        y = min(THIS_YEAR - 1, last_year + r.randint(2, 6))
        prior_idx += 1
        nxt = prior(prior_idx)
        events.append(dict(date=dstr(y, r), deed_no=f"RECON-{plot_no}-{n}",
                           type="sale", **{"from": [last_holder]}, to=[nxt],
                           share="1/1", consideration_inr=value_for(area_ha, y, r)))
        n += 1
        last_holder, last_year = nxt, y

    # 3) Final transfer(s) ending at the real current owner set
    yN = min(THIS_YEAR, last_year + r.randint(2, 7))
    if len(people) == 1:
        events.append(dict(date=dstr(yN, r), deed_no=f"RECON-{plot_no}-{n}",
                           type="sale", **{"from": [last_holder]}, to=[people[0]],
                           share="1/1", consideration_inr=value_for(area_ha, yN, r)))
    else:
        # a prior holder partitions/wills the holding among the current co-owners
        ttype = r.choice(["partition", "inheritance"])
        share = f"1/{len(people)} each"
        events.append(dict(date=dstr(yN, r), deed_no=f"RECON-{plot_no}-{n}",
                           type=ttype, **{"from": [last_holder]}, to=people,
                           share=share, consideration_inr=0))

    for e in events:
        e["source"] = "reconstructed (synthetic)"
        e["confidence"] = "reconstructed"
    return events


def main():
    parcels = json.load(open(PARCELS, encoding="utf-8"))
    owners = json.load(open(OWNERS, encoding="utf-8"))
    histories = {}
    villages = {}  # village name -> gata count (for meta)
    plots_with_events = 0
    total_events = 0
    for ft in parcels.get("features", []):
        p = ft.get("properties", {})
        plot_no = str(p.get("plot_no"))
        village = (p.get("village") or "").strip()
        uid = p.get("uid") or uid_of(village, plot_no)
        khata_no = p.get("khata_no")
        area_ha = p.get("area_ha")
        villages[village] = villages.get(village, 0) + 1
        evs = build_chain(uid, plot_no, khata_no, area_ha, owners.get(uid, []))
        if not evs:
            continue
        histories[uid] = {"uid": uid, "plot_no": plot_no, "village": village,
                          "khata_no": khata_no, "events": evs}
        plots_with_events += 1
        total_events += len(evs)

    # Churn-free: if the reconstructed content is identical to what's on disk,
    # keep the previous generated_at so the file (and the git diff) stays stable.
    generated_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding="utf-8"))
            if prev.get("histories") == histories:
                generated_at = prev.get("meta", {}).get("generated_at", generated_at)
        except Exception:
            pass

    out = {
        "meta": {
            "villages": sorted(villages.keys()),
            "village_count": len(villages),
            "district_code": "141",
            "generated_by": "tools/gen_nalgadha_history.py",
            "generated_at": generated_at,
            "schema_version": 2,
            "disclaimer": ("RECONSTRUCTED / SYNTHETIC chain-of-title for UX "
                           "demonstration. NOT registry-verified. Parties shown "
                           "as 'prior holder' are placeholders; only current "
                           "owners are real (public Bhu-Naksha data). Real deeds "
                           "to come from IGRSUP newPropertySearchAction "
                           "(districtCode=141, Khasra_Number=<plot_no>)."),
        },
        "histories": histories,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {OUT}: {plots_with_events} plots, {total_events} events, "
          f"{len(villages)} village(s)")


if __name__ == "__main__":
    main()
