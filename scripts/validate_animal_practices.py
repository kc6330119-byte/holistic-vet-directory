#!/usr/bin/env python3
"""
validate_animal_practices.py

Reads the Airtable veterinarians CSV export and validates whether each
practice is genuinely an animal/veterinary practice by analyzing their
website content.

Logic:
  1. Pre-score each record from CSV data (vet name, species, certifications).
  2. High-confidence animal practices (pre-score >= 25) are marked LIKELY ANIMAL
     without hitting their website — this skips ~80% of records and runs fast.
  3. Remaining records have their website fetched (homepage + /about if needed)
     and scored against animal vs. human keyword lists.
  4. Progress is saved after every web fetch so the script can be safely
     interrupted and resumed.

Outputs:
  data/validation_results.csv  — every record with scores and classification
  data/validation_flagged.csv  — only REVIEW NEEDED and LIKELY HUMAN records
  data/validation_progress.json — resume checkpoint (delete to start fresh)

Usage:
  python scripts/validate_animal_practices.py
  python scripts/validate_animal_practices.py --dry-run   # first 20 records only
  python scripts/validate_animal_practices.py --reset     # clear progress and restart
"""

import argparse
import csv
import json
import logging
import random
import re
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
INPUT_CSV = PROJECT_ROOT / "Veterinarians-Grid view 03122026.csv"
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_CSV = DATA_DIR / "validation_results.csv"
FLAGGED_CSV = DATA_DIR / "validation_flagged.csv"
PROGRESS_FILE = DATA_DIR / "validation_progress.json"

# ── Request settings ───────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 12       # seconds per HTTP request
DELAY_MIN = 1.5            # seconds between site fetches
DELAY_MAX = 3.0
MAX_CONTENT_BYTES = 400_000  # stop reading after 400 KB

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Keyword scoring tables ─────────────────────────────────────────────────────
# Format: (regex_pattern, score_per_match, display_label)
# score is capped at 3× per keyword type to avoid single-word domination

ANIMAL_KEYWORDS: list[tuple[str, int, str]] = [
    # Definitive veterinary terms
    (r"\bveterinar\w*",                10, "veterinary"),
    (r"\b(DVM|VMD)\b",                 10, "DVM/VMD"),
    (r"\bvet\b",                        4, "vet"),
    # Species — definitive
    (r"\bcanine\b",                     8, "canine"),
    (r"\bfeline\b",                     8, "feline"),
    (r"\bequine\b",                     8, "equine"),
    (r"\bbovine\b",                     6, "bovine"),
    (r"\bavian\b",                      6, "avian"),
    (r"\bporcine\b",                    6, "porcine"),
    # Common animal words
    (r"\b(dog|dogs)\b",                 4, "dogs"),
    (r"\b(cat|cats)\b",                 4, "cats"),
    (r"\b(horse|horses|mare|gelding)\b",4, "horses"),
    (r"\b(bird|birds|parrot)\b",        3, "birds"),
    (r"\b(rabbit|bunny|guinea pig)\b",  3, "small animals"),
    (r"\b(reptile|lizard|snake|turtle)\b",3,"reptiles"),
    (r"\b(puppy|puppies|kitten|kittens|foal)\b",5,"young animals"),
    (r"\bfarm animal\b",                4, "farm animals"),
    (r"\blivestock\b",                  4, "livestock"),
    # Pet-owner phrasing
    (r"\byour\s+(dog|cat|horse|pet|animal)\b", 5, "your pet"),
    (r"\bpet\s+(owner|health|care|wellness|patient|hospital|clinic)\b", 6, "pet care"),
    (r"\banimal\s+(hospital|clinic|care|health|patient|center)\b",       6, "animal clinic"),
    (r"\b(paw|paws)\b",                 4, "paws"),
    (r"\bfur\s+(baby|babies|kid|friend|parent)\b", 4, "fur baby"),
    (r"\bpet\b",                        2, "pet"),
    (r"\banimal\b",                     2, "animal"),
    (r"\bspecies\b",                    2, "species"),
    # Animal-specific certifications
    (r"\bAHVMA\b",                      8, "AHVMA"),
    (r"\bIVAS\b",                       8, "IVAS"),
    (r"\bAVCA\b",                       8, "AVCA"),
    (r"\bChi\s+Institute\b",            8, "Chi Institute"),
    (r"\bCIVT\b",                       8, "CIVT"),
    (r"\bCVA\b",                        5, "CVA"),     # Certified Veterinary Acupuncturist
    (r"\bCVMT\b",                       5, "CVMT"),
    (r"\bVSMT\b",                       5, "VSMT"),
]

HUMAN_KEYWORDS: list[tuple[str, int, str]] = [
    # Human medical credentials (very strong)
    (r"\b(physician|MD)\b",            -8, "physician/MD"),
    (r"\bchiropractor.*?\bDC\b",       -6, "human chiro DC"),
    (r"\bDC\b.*?chiropract",           -6, "human chiro DC"),
    (r"\bLMT\b",                       -4, "massage therapist LMT"),
    (r"\bLAc\b",                       -4, "licensed acupuncturist"),
    # Human-only conditions
    (r"\b(fertility|pregnancy|prenatal|postnatal|obstetric)\b",  -8, "pregnancy/fertility"),
    (r"\b(pediatric|pediatrician|children.s health)\b",          -6, "pediatric"),
    (r"\b(men.s health|women.s health|gynecolog)\b",             -6, "gendered health"),
    (r"\b(sciatica|herniated disc|slipped disc)\b",              -5, "human spine"),
    (r"\bspine\s+(center|clinic|specialist|institute)\b",        -5, "spine center"),
    (r"\bmental health\b",             -4, "mental health"),
    (r"\bhuman\s+patient",             -5, "human patient"),
    # Phrasing that implies human clients
    (r"\b(our patients|your health|your body|your spine|your back)\b", -3, "human phrasing"),
    (r"\b(health insurance|insurance accepted|insurance plans)\b",     -3, "human insurance"),
]


# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Progress helpers ───────────────────────────────────────────────────────────
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"processed": {}}


def save_progress(progress: dict) -> None:
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# ── Web fetching ───────────────────────────────────────────────────────────────
def fetch_text(url: str) -> Optional[str]:
    """Fetch a URL and return visible text, or None on failure."""
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=REQUEST_TIMEOUT,
            allow_redirects=True, stream=True
        )
        resp.raise_for_status()

        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=8192):
            chunks.append(chunk)
            total += len(chunk)
            if total >= MAX_CONTENT_BYTES:
                break

        soup = BeautifulSoup(b"".join(chunks), "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text)
    except Exception as exc:
        log.debug(f"  fetch failed {url}: {exc}")
        return None


def normalise_url(raw: str) -> str:
    """Ensure URL has a scheme."""
    raw = raw.strip().rstrip("/")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def fetch_site_text(website: str) -> Tuple[str, str]:
    """
    Fetch homepage. If content is thin or animal signals are weak,
    also try /about and /about-us.
    Returns (combined_text, pages_label).
    """
    base = normalise_url(website)
    home = fetch_text(base) or ""
    pages = "homepage"

    # Check whether homepage already has strong animal signals
    strong_animal = any(
        re.search(pat, home, re.IGNORECASE)
        for pat, score, _ in ANIMAL_KEYWORDS
        if score >= 8
    )

    if not strong_animal or len(home) < 300:
        for path in ("/about", "/about-us", "/services"):
            about = fetch_text(base + path) or ""
            if about:
                home = home + " " + about
                pages += f" + {path}"
                break  # one extra page is enough

    return home, pages


# ── Scoring ────────────────────────────────────────────────────────────────────
def score_text(text: str) -> Tuple[int, list, list]:
    """
    Score text content for animal vs. human signals.
    Returns (net_score, animal_match_labels, human_match_labels).
    """
    animal_hits: list[str] = []
    human_hits: list[str] = []
    score = 0

    for pattern, pts, label in ANIMAL_KEYWORDS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            contribution = min(pts * len(matches), pts * 3)  # cap at 3×
            score += contribution
            animal_hits.append(f"{label}({len(matches)})")

    for pattern, pts, label in HUMAN_KEYWORDS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            contribution = max(pts * len(matches), pts * 3)  # cap negative at 3×
            score += contribution
            human_hits.append(f"{label}({len(matches)})")

    return score, animal_hits, human_hits


def pre_score_from_csv(row: dict) -> Tuple[int, list]:
    """
    Quick score from Airtable fields only — no web request.
    Returns (score, signal_labels).
    """
    score = 0
    signals: list[str] = []

    vet_name = row.get("Veterinarian Name(s)", "")
    if re.search(r"\b(DVM|VMD)\b", vet_name, re.IGNORECASE):
        score += 15
        signals.append("DVM/VMD in name")

    species = row.get("Species Treated", "").strip()
    if species:
        score += 8
        signals.append(f"species: {species[:40]}")

    certs = row.get("Certification Bodies", "")
    animal_certs = ["AHVMA", "IVAS", "AVCA", "Chi Institute", "CIVT", "VBMA"]
    for c in animal_certs:
        if c in certs:
            score += 10
            signals.append(f"cert: {c}")
            break  # one cert is enough for pre-score

    description = row.get("Practice Description", "")
    if len(description) > 50:
        desc_score, anim, _ = score_text(description)
        score += desc_score // 2  # half-weight for description
        if anim:
            signals.append(f"desc_signals: {','.join(anim[:3])}")

    return score, signals


def classify(score: int) -> str:
    if score >= 10:
        return "LIKELY ANIMAL"
    elif score >= 0:
        return "REVIEW NEEDED"
    else:
        return "LIKELY HUMAN"


# ── CSV output ─────────────────────────────────────────────────────────────────
FIELDNAMES = [
    "Classification", "Practice Name", "City", "State",
    "Website", "Vet Name", "Pre-Score", "Web Score", "Total Score",
    "Animal Signals", "Human Signals", "Pages Checked", "Slug",
]

CLASSIFICATION_ORDER = {
    "LIKELY HUMAN": 0,
    "REVIEW NEEDED": 1,
    "NO WEBSITE": 2,
    "LIKELY ANIMAL": 3,
}


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Validate animal practices in directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process only the first 20 records (no web fetches written)")
    parser.add_argument("--reset", action="store_true",
                        help="Delete progress file and start fresh")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    if args.reset and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        log.info("Progress file cleared — starting fresh.")

    if not INPUT_CSV.exists():
        log.error(f"CSV not found: {INPUT_CSV}")
        sys.exit(1)

    with open(INPUT_CSV, encoding="utf-8-sig") as f:
        all_rows = list(csv.DictReader(f))
    log.info(f"Loaded {len(all_rows)} records from CSV")

    if args.dry_run:
        all_rows = all_rows[:20]
        log.info("DRY RUN — processing first 20 records only")

    progress = load_progress()
    processed: dict = progress.get("processed", {})

    results: list[dict] = []
    web_fetches = 0

    for i, row in enumerate(all_rows, 1):
        slug = row.get("Slug", "").strip()
        practice = row.get("Practice Name", "").strip()
        website = row.get("Website", "").strip()

        # ── No website ──────────────────────────────────────────────────────
        if not website:
            results.append({
                "Practice Name": practice,
                "City": row.get("City", ""),
                "State": row.get("State", ""),
                "Slug": slug,
                "Website": "",
                "Vet Name": row.get("Veterinarian Name(s)", ""),
                "Pre-Score": 0, "Web Score": 0, "Total Score": 0,
                "Animal Signals": "",
                "Human Signals": "",
                "Pages Checked": "no website",
                "Classification": "NO WEBSITE",
            })
            continue

        # ── Already in progress cache ───────────────────────────────────────
        if slug in processed and not args.dry_run:
            results.append(processed[slug])
            continue

        # ── Pre-score from CSV fields ───────────────────────────────────────
        pre_score, pre_signals = pre_score_from_csv(row)

        # ── Skip web fetch for high-confidence animal practices ─────────────
        HIGH_CONFIDENCE_THRESHOLD = 25
        if pre_score >= HIGH_CONFIDENCE_THRESHOLD:
            result = {
                "Practice Name": practice,
                "City": row.get("City", ""),
                "State": row.get("State", ""),
                "Slug": slug,
                "Website": website,
                "Vet Name": row.get("Veterinarian Name(s)", ""),
                "Pre-Score": pre_score,
                "Web Score": 0,
                "Total Score": pre_score,
                "Animal Signals": ", ".join(pre_signals),
                "Human Signals": "",
                "Pages Checked": "skipped — high pre-score",
                "Classification": "LIKELY ANIMAL",
            }
            results.append(result)
            if not args.dry_run:
                processed[slug] = result
            if i % 200 == 0:
                log.info(f"  [{i}/{len(all_rows)}] high-confidence skip: {practice}")
            continue

        # ── Fetch and analyse website ───────────────────────────────────────
        log.info(f"[{i}/{len(all_rows)}] Checking: {practice} — {website}")
        site_text, pages_checked = fetch_site_text(website)
        web_fetches += 1

        if site_text:
            web_score, animal_matches, human_matches = score_text(site_text)
        else:
            web_score, animal_matches, human_matches = 0, [], []
            pages_checked = "unreachable"

        total_score = pre_score + web_score
        classification = classify(total_score)

        if classification != "LIKELY ANIMAL":
            log.warning(
                f"  *** FLAGGED [{classification}] score={total_score}: {practice} | {website}"
            )

        result = {
            "Practice Name": practice,
            "City": row.get("City", ""),
            "State": row.get("State", ""),
            "Slug": slug,
            "Website": website,
            "Vet Name": row.get("Veterinarian Name(s)", ""),
            "Pre-Score": pre_score,
            "Web Score": web_score,
            "Total Score": total_score,
            "Animal Signals": ", ".join(pre_signals + animal_matches),
            "Human Signals": ", ".join(human_matches),
            "Pages Checked": pages_checked,
            "Classification": classification,
        }

        results.append(result)

        if not args.dry_run:
            processed[slug] = result
            save_progress({"processed": processed})

        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # ── Sort and write output ───────────────────────────────────────────────
    results.sort(key=lambda r: (
        CLASSIFICATION_ORDER.get(r["Classification"], 4),
        r.get("Total Score", 0)
    ))

    if not args.dry_run:
        write_csv(RESULTS_CSV, results)
        flagged = [r for r in results if r["Classification"] in ("LIKELY HUMAN", "REVIEW NEEDED")]
        write_csv(FLAGGED_CSV, flagged)

    # ── Summary ─────────────────────────────────────────────────────────────
    counts: dict[str, int] = {}
    for r in results:
        counts[r["Classification"]] = counts.get(r["Classification"], 0) + 1

    log.info("\n=== VALIDATION SUMMARY ===")
    for label in ["LIKELY HUMAN", "REVIEW NEEDED", "NO WEBSITE", "LIKELY ANIMAL"]:
        if label in counts:
            log.info(f"  {label}: {counts[label]}")
    log.info(f"  Web fetches performed: {web_fetches}")

    if not args.dry_run:
        flagged_count = counts.get("LIKELY HUMAN", 0) + counts.get("REVIEW NEEDED", 0)
        log.info(f"\nAll results  → {RESULTS_CSV}")
        log.info(f"Flagged only → {FLAGGED_CSV}  ({flagged_count} records to review)")


if __name__ == "__main__":
    main()
