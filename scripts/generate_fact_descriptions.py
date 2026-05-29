#!/usr/bin/env python3
"""
generate_fact_descriptions.py — Phase 1 fact-grounded listing descriptions.

Replaces the spun/templated approaches (the build-time spinner that used to live
in generate_site.Veterinarian._generate_auto_description, now removed, and the
hash-seeded scripts/enrich_vet_descriptions.py). Each description is assembled
ONLY from facts that are true for that specific practice, drawn from its Airtable
record: practice/vet names, city/state, holistic specialties, species treated,
holistic credentials, telehealth, year established, and Google rating/reviews.

Variation between listings comes from real differing facts, not shuffled
synonyms — which is what removes Google's "scaled content abuse" signal. There is
NO length padding: a description that comes out under the build's index gate is
left short on purpose, and generate_site.py noindexes it. That deliberately
shrinks the indexed surface to genuinely fact-rich pages.

It ONLY UPDATES existing Airtable records (never inserts). Dry-run by default;
--apply writes the "Practice Description" field. Before the first write it dumps
a timestamped backup of every current description keyed by record id.

Usage:
  python3 scripts/generate_fact_descriptions.py            # dry run: stats + samples + review file
  python3 scripts/generate_fact_descriptions.py --limit 50 # dry run on a sample
  python3 scripts/generate_fact_descriptions.py --apply     # write Practice Description in Airtable
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Reuse the build's exact gate logic so the projection matches production.
from generate_site import Veterinarian  # noqa: E402

# override=True so a real key in .env wins over a stale/empty shell export.
load_dotenv(PROJECT_ROOT / ".env", override=True)

DESC_FIELD = "Practice Description"
BACKUP_DIR = PROJECT_ROOT / "data"
REVIEW_FILE = PROJECT_ROOT / "data" / "fact_descriptions_sample.md"

# Build the same index decision the site generator uses.
VET_NOINDEX_THRESHOLD = 7  # mirrors SiteConfig.VET_NOINDEX_THRESHOLD


def require_env(name: str) -> str:
    """Return a non-empty env var or exit. Guards the empty-shadow gotcha."""
    val = (os.environ.get(name) or "").strip()
    if not val:
        sys.exit(f"{name} is missing or empty in .env — required to read/write Airtable.")
    return val


# ── fact parsing / normalization ───────────────────────────────────────────────

# Some source records are double-encoded (cp1252 text decoded as UTF-8), so common
# punctuation shows up as mojibake. These are deterministic, so we restore them.
_MOJIBAKE = {
    "‚Äô": "’", "‚Äì": "–", "‚Äî": "—",
    "‚Äú": "“", "‚Äù": "”", "‚Ä¶": "…",
    "√©": "é", "√±": "ñ",
}


def fix_mojibake(s: str) -> str:
    if not s:
        return s
    for bad, good in _MOJIBAKE.items():
        s = s.replace(bad, good)
    return s


# Free-text fields use inconsistent delimiters (|, comma, &) and contain typos.
_SPLIT = re.compile(r"[|,&]")


def _clean(token: str) -> str:
    return re.sub(r"\s+", " ", token).strip().strip(".").strip()


def split_multi(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        parts = []
        for item in raw:
            parts.extend(_SPLIT.split(str(item)))
    else:
        parts = _SPLIT.split(str(raw))
    out = []
    for p in parts:
        c = _clean(p)
        if c:
            out.append(c)
    return out


SPECIALTY_CANON = {
    "acupuncture": "Acupuncture",
    "acupunture": "Acupuncture",
    "acupuncutre": "Acupuncture",
    "chiropractic": "Chiropractic",
    "chriopractic": "Chiropractic",
    "herbal medicine": "Herbal Medicine",
    "nutritional therapy": "Nutritional Therapy",
    "nutrition therapy": "Nutritional Therapy",
    "laser therapy": "Laser Therapy",
    "therapeutic laser": "Laser Therapy",
    "physical therapy/rehabilitation": "Physical Therapy and Rehabilitation",
    "traditional chinese veterinary medicine": "Traditional Chinese Veterinary Medicine",
    "homeopathy": "Homeopathy",
    "ozone therapy": "Ozone Therapy",
    "integrative medicine": "Integrative Medicine",
    "integrative care": "Integrative Medicine",
    "holistic medicine": "Holistic Medicine",
}


def normalize_specialties(raw) -> list[str]:
    out = []
    for item in split_multi(raw):
        key = re.sub(r"[^a-z/ ]", "", item.lower())
        key = re.sub(r"\bttraditional\b", "traditional", key)
        key = re.sub(r"\bt raditional\b", "traditional", key)
        key = re.sub(r"\s+", " ", key).strip()
        canon = SPECIALTY_CANON.get(key)
        if not canon:
            continue  # skip unrecognized noise rather than emit garbage
        if canon not in out:
            out.append(canon)
    return out


SPECIES_CANON = {
    "dog": "dogs", "dogs": "dogs",
    "cat": "cats", "cats": "cats",
    "horse": "horses", "horses": "horses",
    "exotic": "exotics", "exotics": "exotics", "exotic pets": "exotics",
    "bird": "birds", "birds": "birds",
    "reptile": "reptiles", "reptiles": "reptiles",
    "rabbit": "rabbits", "rabbits": "rabbits",
    "ferret": "ferrets", "ferrets": "ferrets",
    "rodent": "rodents", "rodents": "rodents",
    "donkey": "donkeys", "donkeys": "donkeys",
    "small mammal": "small mammals", "small mammals": "small mammals",
    "small animal": "small animals", "small animals": "small animals",
    "farm animal": "farm animals", "farm animals": "farm animals",
}


def normalize_species(raw) -> list[str]:
    out = []
    for item in split_multi(raw):
        canon = SPECIES_CANON.get(item.lower())
        if not canon:
            continue
        if canon not in out:
            out.append(canon)
    return out


# Holistic credentials held by a practitioner (the base DVM/VMD degree and other
# generic tokens are not differentiating, so they are excluded from prose).
PERSONAL_CREDENTIAL = {
    "CVA": "Certified Veterinary Acupuncturist (CVA)",
    "CVCH": "Certified Veterinary Chinese Herbalist (CVCH)",
    "CVFT": "Certified Veterinary Food Therapist (CVFT)",
    "DACVSMR": "Diplomate of the American College of Veterinary Sports Medicine and Rehabilitation (DACVSMR)",
    "CCRT": "Certified Canine Rehabilitation Therapist (CCRT)",
    "CCRP": "Certified Canine Rehabilitation Practitioner (CCRP)",
}
# Holistic organizations / training bodies the practice is affiliated with.
AFFILIATION = {
    "AHVMA": "the American Holistic Veterinary Medical Association",
    "IVAS": "the International Veterinary Acupuncture Society",
    "AVCA": "the American Veterinary Chiropractic Association",
    "IVCA": "the International Veterinary Chiropractic Association",
    "AAVA": "the American Academy of Veterinary Acupuncture",
    "Chi Institute": "the Chi Institute",
    "Chi University": "the Chi Institute",
}


def _dedupe(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def normalize_credentials(raw) -> tuple[list[str], list[str]]:
    """Return (personal credentials, organizational affiliations), each deduped."""
    personal, affil = [], []
    for item in split_multi(raw):
        p = PERSONAL_CREDENTIAL.get(item) or PERSONAL_CREDENTIAL.get(item.upper())
        if p:
            personal.append(p)
            continue
        a = AFFILIATION.get(item) or AFFILIATION.get(item.upper())
        if a:
            affil.append(a)
    return _dedupe(personal), _dedupe(affil)


def oxford(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _parse_year(value):
    try:
        y = int(value) if value not in (None, "") else None
    except (ValueError, TypeError):
        return None
    if y and 1800 <= y <= datetime.now().year:
        return y
    return None


def truthy(value) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "x", "checked")
    return False


# ── compose ─────────────────────────────────────────────────────────────────

def compose(f: dict) -> str:
    name = fix_mojibake((f.get("Practice Name") or "").strip())
    city = fix_mojibake((f.get("City") or "").strip())
    state = (f.get("State") or "").strip()
    loc = ", ".join(p for p in (city, state) if p)

    specialties = normalize_specialties(f.get("Specialties"))
    species = normalize_species(f.get("Species Treated"))
    personal_creds, affiliations = normalize_credentials(f.get("Certification Bodies"))

    sentences = []

    # 1. opening (always) — name + identity + location
    sentences.append(
        f"{name} is a holistic and integrative veterinary practice"
        + (f" in {loc}." if loc else ".")
    )

    # 2. species treated
    if species:
        sentences.append(f"The practice treats {oxford(species)}.")

    # 3. holistic services
    if specialties:
        sentences.append(f"Holistic and integrative services include {oxford(specialties)}.")

    # 4. holistic credentials and affiliations
    if personal_creds:
        sentences.append(f"Its veterinarians hold credentials including {oxford(personal_creds)}.")
    if affiliations:
        sentences.append(f"The practice is affiliated with {oxford(affiliations)}.")

    # 5. telehealth
    if truthy(f.get("Telehealth Available")):
        sentences.append("Telehealth consultations are available.")

    # 6. year established
    year = _parse_year(f.get("Year Established"))
    if year:
        sentences.append(f"The practice has served the area since {year}.")

    # 7. social proof (last) — attributed to Google, never emitted as schema
    rating = f.get("Google Rating")
    reviews = f.get("Google Reviews")
    try:
        rn = int(reviews) if reviews not in (None, "") else 0
    except (ValueError, TypeError):
        rn = 0
    if rating and rn > 0:
        rating_str = f"{float(rating):g}"
        sentences.append(
            f"It holds a {rating_str}-star rating across {rn:,} Google review"
            + ("s" if rn != 1 else "") + "."
        )

    return " ".join(sentences)


# ── projection (reuse build gate) ─────────────────────────────────────────────

def project_index(f: dict, new_desc: str) -> tuple[bool, int]:
    """Return (indexed, quality_score) using generate_site's exact logic."""
    vet = Veterinarian(
        practice_name=f.get("Practice Name", "") or "x",
        practice_description=new_desc,
        phone=f.get("Phone", "") or "",
        email=f.get("Email", "") or "",
        website=f.get("Website", "") or "",
        certification_bodies=f.get("Certification Bodies", "") or "",
        latitude=f.get("Latitude"),
        longitude=f.get("Longitude"),
        google_rating=f.get("Google Rating"),
        google_reviews=f.get("Google Reviews") or 0,
        specialties=f.get("Specialties", "") or "",
        year_established=_parse_year(f.get("Year Established")),
    )
    indexed = (
        vet.has_real_description
        and vet.quality_score >= VET_NOINDEX_THRESHOLD
        and vet.has_differentiating_facts
    )
    return indexed, vet.quality_score


GATE_FIELDS = [
    "Practice Name", "Veterinarian Name(s)", "City", "State",
    "Specialties", "Species Treated", "Certification Bodies",
    "Telehealth Available", "Year Established",
    "Phone", "Email", "Website", "Latitude", "Longitude",
    "Google Rating", "Google Reviews",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="process only the first N records (0 = all)")
    ap.add_argument("--apply", action="store_true", help="write Practice Description to Airtable")
    args = ap.parse_args()

    api_key = require_env("AIRTABLE_API_KEY")
    base_id = require_env("AIRTABLE_BASE_ID")
    table_name = (os.environ.get("AIRTABLE_TABLE_NAME") or "Veterinarians").strip()

    from pyairtable import Api
    table = Api(api_key).table(base_id, table_name)
    # Fetch DESC_FIELD too so the pre-write backup captures the current text.
    recs = table.all(fields=GATE_FIELDS + [DESC_FIELD])
    if args.limit:
        recs = recs[: args.limit]

    results = []  # (rec_id, name, current_desc, new_desc, length, indexed, score)
    for r in recs:
        f = r["fields"]
        new_desc = compose(f)
        indexed, score = project_index(f, new_desc)
        results.append((
            r["id"], f.get("Practice Name", ""), f.get(DESC_FIELD, "") or "",
            new_desc, len(new_desc), indexed, score,
        ))

    n = len(results)
    if not n:
        sys.exit("No records returned from Airtable.")

    lengths = sorted(x[4] for x in results)
    def pct(p): return lengths[min(n - 1, int(p * n))]
    real_count = sum(1 for x in results if Veterinarian(
        practice_name="x", practice_description=x[3]).has_real_description)
    idx_count = sum(1 for x in results if x[5])

    print(f"Composed {n} fact-grounded descriptions ({'APPLY' if args.apply else 'DRY RUN'}).")
    print(f"  length: min={lengths[0]} p25={pct(.25)} median={pct(.5)} "
          f"p75={pct(.75)} p90={pct(.9)} max={lengths[-1]}")
    print(f"  pass description text gate (has_real_description): {real_count} ({100*real_count/n:.1f}%)")
    print(f"  PROJECTED INDEXED (real desc AND quality>=7): {idx_count} ({100*idx_count/n:.1f}%)  "
          f"noindexed: {n-idx_count} ({100*(n-idx_count)/n:.1f}%)")

    # samples across the information-density spectrum
    by_len = sorted(results, key=lambda x: x[4])
    picks = [by_len[int(p * (n - 1))] for p in (0.10, 0.35, 0.55, 0.75, 0.90, 0.99)]
    review_lines = ["# Phase 1 fact-grounded description samples\n"]
    print("\n===== SAMPLES (low -> high information density) =====")
    for _id, name, _cur, text, L, indexed, score in picks:
        tag = "INDEX" if indexed else "noindex"
        print(f"\n[{L} chars | q{score} | {tag}] {name}\n{text}")
        review_lines.append(f"## {name}  _({L} chars, q{score}, {tag})_\n\n{text}\n")
    REVIEW_FILE.write_text("\n".join(review_lines), encoding="utf-8")
    print(f"\nWrote review file: {REVIEW_FILE.relative_to(PROJECT_ROOT)}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to write Airtable.")
        return

    # Back up current descriptions before the first write.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"practice_description_backup_{stamp}.json"
    backup = {rid: cur for rid, _n, cur, _d, _L, _i, _s in results}
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nBacked up {len(backup)} current descriptions to {backup_path.relative_to(PROJECT_ROOT)}")

    updates = [{"id": rid, "fields": {DESC_FIELD: text}}
               for rid, _n, _cur, text, _L, _i, _s in results]
    print(f"--apply: updating {len(updates)} existing records (no inserts)...")
    for i in range(0, len(updates), 10):
        table.batch_update(updates[i:i + 10])
        print(f"  updated {min(i + 10, len(updates))}/{len(updates)}")
    print("Done.")


if __name__ == "__main__":
    main()
