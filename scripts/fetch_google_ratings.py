#!/usr/bin/env python3
"""
fetch_google_ratings.py

Fetches Google Places star ratings and review counts for all vet practices
using the Google Places API (Find Place from Text).

Prerequisites:
  1. GOOGLE_MAPS_API_KEY set in .env
  2. "Places API" enabled in Google Cloud Console
     (APIs & Services → Library → search "Places API" → Enable)

Cost:
  ~$25 per 1,000 lookups (Atmosphere SKU). 3,223 vets ≈ $81.
  Covered by Google Maps Platform's $200/month free credit.

Outputs:
  data/google_ratings.csv          — all results with ratings
  data/google_ratings_progress.json — resume checkpoint

Usage:
  python3 scripts/fetch_google_ratings.py                    # full run
  python3 scripts/fetch_google_ratings.py --dry-run          # first 10 only
  python3 scripts/fetch_google_ratings.py --update-airtable  # also push to Airtable
  python3 scripts/fetch_google_ratings.py --reset            # clear progress
  python3 scripts/fetch_google_ratings.py --input other.csv  # use different CSV
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INPUT = PROJECT_ROOT / "Veterinarians-Grid view 03162026.csv"
OUTPUT_CSV = DATA_DIR / "google_ratings.csv"
PROGRESS_FILE = DATA_DIR / "google_ratings_progress.json"

# ── Load env ───────────────────────────────────────────────────────────────────
load_dotenv(PROJECT_ROOT / ".env")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ── API settings ───────────────────────────────────────────────────────────────
FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
FIELDS = "place_id,name,formatted_address,rating,user_ratings_total"
REQUEST_TIMEOUT = 10
DELAY = 0.15  # 150ms between requests (~400/min, well under 600/min limit)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Progress tracking ─────────────────────────────────────────────────────────
def load_progress() -> Dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"processed": {}}


def save_progress(progress: Dict) -> None:
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)


# ── Google Places API ──────────────────────────────────────────────────────────
def find_place(practice_name: str, city: str, state: str) -> Optional[Dict]:
    """
    Search Google Places for a business.
    Returns dict with rating info or None if not found.
    """
    query = f"{practice_name}, {city}, {state}"

    params = {
        "input": query,
        "inputtype": "textquery",
        "fields": FIELDS,
        "key": GOOGLE_MAPS_API_KEY,
    }

    try:
        resp = requests.get(FIND_PLACE_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as exc:
        log.error(f"  API request failed: {exc}")
        return None

    status = data.get("status", "")

    if status == "REQUEST_DENIED":
        log.error(f"  API denied: {data.get('error_message', 'unknown')}")
        log.error("  Make sure 'Places API' is enabled in Google Cloud Console.")
        sys.exit(1)

    if status == "INVALID_REQUEST":
        log.error(f"  Invalid request: {data.get('error_message', 'unknown')}")
        return None

    candidates = data.get("candidates", [])
    if not candidates:
        return None

    place = candidates[0]
    place_id = place.get("place_id", "")

    # Build Google Maps URL from place_id
    maps_url = ""
    if place_id:
        encoded_name = urllib.parse.quote(place.get("name", practice_name))
        maps_url = (
            f"https://www.google.com/maps/search/?api=1"
            f"&query={encoded_name}&query_place_id={place_id}"
        )

    return {
        "google_place_id": place_id,
        "google_name": place.get("name", ""),
        "google_address": place.get("formatted_address", ""),
        "google_rating": place.get("rating", ""),
        "google_reviews": place.get("user_ratings_total", 0),
        "google_maps_url": maps_url,
    }


def assess_confidence(
    our_name: str, our_state: str,
    google_name: str, google_address: str
) -> str:
    """
    Compare our record to the Google result.
    Returns HIGH, MEDIUM, or LOW confidence.
    """
    state_match = our_state.upper() in google_address.upper()
    # Simple name similarity: check if key words overlap
    our_words = set(our_name.lower().split())
    google_words = set(google_name.lower().split())
    # Remove common filler words
    filler = {"the", "a", "an", "of", "and", "&", "llc", "inc", "pc", "pllc"}
    our_words -= filler
    google_words -= filler

    if not our_words:
        name_overlap = 0.0
    else:
        overlap = our_words & google_words
        name_overlap = len(overlap) / len(our_words)

    if state_match and name_overlap >= 0.5:
        return "HIGH"
    elif state_match or name_overlap >= 0.3:
        return "MEDIUM"
    else:
        return "LOW"


# ── Airtable update ───────────────────────────────────────────────────────────
def update_airtable(results: List[Dict]) -> None:
    """Push ratings to Airtable for records with HIGH confidence."""
    try:
        from pyairtable import Api
    except ImportError:
        log.error("pyairtable not installed. Run: pip install pyairtable")
        return

    api_key = os.getenv("AIRTABLE_API_KEY", "")
    base_id = os.getenv("AIRTABLE_BASE_ID", "")
    if not api_key or not base_id:
        log.error("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in .env")
        return

    api = Api(api_key)
    table = api.table(base_id, "Veterinarians")

    log.info("Fetching Airtable records to build slug index...")
    all_records = table.all(fields=["Slug"])
    slug_to_id = {}
    for rec in all_records:
        slug = rec["fields"].get("Slug", "")
        if slug:
            slug_to_id[slug] = rec["id"]
    log.info(f"  Indexed {len(slug_to_id)} Airtable records")

    # Filter to high-confidence results with ratings
    updatable = [
        r for r in results
        if r["confidence"] == "HIGH"
        and r["google_rating"]
        and r["slug"] in slug_to_id
    ]
    log.info(f"  {len(updatable)} records to update (HIGH confidence with ratings)")

    updated = 0
    skipped = 0
    for i, r in enumerate(updatable, 1):
        record_id = slug_to_id[r["slug"]]
        fields = {
            "Google Rating": float(r["google_rating"]),
            "Google Reviews": int(r["google_reviews"]),
            "Google Place ID": r["google_place_id"],
            "Google Maps URL": r["google_maps_url"],
        }
        try:
            table.update(record_id, fields)
            updated += 1
            if updated % 50 == 0:
                log.info(f"  Updated {updated}/{len(updatable)}...")
        except Exception as exc:
            log.warning(f"  Failed to update {r['practice_name']}: {exc}")
            skipped += 1

        time.sleep(0.25)  # Airtable rate limit: 5 requests/second

    log.info(f"  Airtable update complete: {updated} updated, {skipped} failed")


# ── Output ─────────────────────────────────────────────────────────────────────
OUTPUT_FIELDS = [
    "Slug", "Practice Name", "City", "State",
    "Google Rating", "Google Reviews", "Google Place ID",
    "Google Name", "Google Address", "Google Maps URL",
    "Confidence", "Status",
]


def write_output(results: List[Dict]) -> None:
    """Write results to CSV, sorted by confidence (LOW first for easy review)."""
    confidence_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "": 3}

    sorted_results = sorted(results, key=lambda r: (
        confidence_order.get(r.get("confidence", ""), 3),
        -float(r.get("google_rating") or 0),
    ))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in sorted_results:
            writer.writerow({
                "Slug": r["slug"],
                "Practice Name": r["practice_name"],
                "City": r["city"],
                "State": r["state"],
                "Google Rating": r.get("google_rating", ""),
                "Google Reviews": r.get("google_reviews", ""),
                "Google Place ID": r.get("google_place_id", ""),
                "Google Name": r.get("google_name", ""),
                "Google Address": r.get("google_address", ""),
                "Google Maps URL": r.get("google_maps_url", ""),
                "Confidence": r.get("confidence", ""),
                "Status": r.get("status", ""),
            })


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Google Places ratings for vet directory")
    parser.add_argument("--dry-run", action="store_true", help="Process first 10 records only")
    parser.add_argument("--reset", action="store_true", help="Clear progress and start fresh")
    parser.add_argument("--update-airtable", action="store_true", help="Push ratings to Airtable")
    parser.add_argument("--input", type=str, default=None, help="Path to input CSV")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    # Validate API key
    if not GOOGLE_MAPS_API_KEY:
        log.error("GOOGLE_MAPS_API_KEY not set in .env")
        log.error("Get one at: https://console.cloud.google.com/apis/credentials")
        sys.exit(1)

    if args.reset and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        log.info("Progress cleared — starting fresh.")

    # Load CSV
    input_path = Path(args.input) if args.input else DEFAULT_INPUT
    if not input_path.exists():
        log.error(f"Input CSV not found: {input_path}")
        sys.exit(1)

    with open(input_path, encoding="utf-8-sig") as f:
        all_rows = list(csv.DictReader(f))
    log.info(f"Loaded {len(all_rows)} records from {input_path.name}")

    if args.dry_run:
        all_rows = all_rows[:10]
        log.info("DRY RUN — processing first 10 records only")

    progress = load_progress()
    processed = progress.get("processed", {})

    results: List[Dict] = []
    api_calls = 0
    found_with_rating = 0
    found_no_rating = 0
    not_found = 0
    errors = 0

    for i, row in enumerate(all_rows, 1):
        slug = row.get("Slug", "").strip()
        practice = row.get("Practice Name", "").strip()
        city = row.get("City", "").strip()
        state = row.get("State", "").strip()

        if not practice or not city:
            continue

        # Already processed?
        if slug in processed:
            results.append(processed[slug])
            prev = processed[slug]
            if prev.get("google_rating"):
                found_with_rating += 1
            elif prev.get("status") == "found_no_rating":
                found_no_rating += 1
            elif prev.get("status") == "not_found":
                not_found += 1
            continue

        # API call
        if i % 25 == 0 or i == 1:
            log.info(f"[{i}/{len(all_rows)}] Processing: {practice}, {city}, {state}")

        place = find_place(practice, city, state)
        api_calls += 1

        if place and (place["google_rating"] or place["google_reviews"]):
            confidence = assess_confidence(
                practice, state,
                place["google_name"], place["google_address"]
            )
            result = {
                "slug": slug,
                "practice_name": practice,
                "city": city,
                "state": state,
                "status": "found",
                "confidence": confidence,
                **place,
            }
            found_with_rating += 1
            if confidence == "LOW":
                log.warning(
                    f"  LOW confidence: '{practice}' matched '{place['google_name']}' "
                    f"({place['google_rating']}★, {place['google_reviews']} reviews)"
                )
        elif place:
            # Found on Google but no rating
            result = {
                "slug": slug,
                "practice_name": practice,
                "city": city,
                "state": state,
                "status": "found_no_rating",
                "confidence": assess_confidence(
                    practice, state,
                    place["google_name"], place["google_address"]
                ),
                **place,
            }
            found_no_rating += 1
        else:
            result = {
                "slug": slug,
                "practice_name": practice,
                "city": city,
                "state": state,
                "status": "not_found",
                "confidence": "",
                "google_place_id": "",
                "google_name": "",
                "google_address": "",
                "google_rating": "",
                "google_reviews": "",
                "google_maps_url": "",
            }
            not_found += 1

        results.append(result)

        if not args.dry_run:
            processed[slug] = result
            # Save progress every 25 records to balance speed and safety
            if api_calls % 25 == 0:
                save_progress({"processed": processed})

        time.sleep(DELAY)

    # Final progress save
    if not args.dry_run:
        save_progress({"processed": processed})

    # Write output
    write_output(results)

    # Summary
    log.info("\n=== RESULTS SUMMARY ===")
    log.info(f"  Total records:      {len(results)}")
    log.info(f"  Found with rating:  {found_with_rating}")
    log.info(f"  Found, no rating:   {found_no_rating}")
    log.info(f"  Not found:          {not_found}")
    log.info(f"  API calls made:     {api_calls}")
    log.info(f"\nOutput: {OUTPUT_CSV}")

    # Confidence breakdown for rated results
    high = sum(1 for r in results if r.get("confidence") == "HIGH" and r.get("google_rating"))
    med = sum(1 for r in results if r.get("confidence") == "MEDIUM" and r.get("google_rating"))
    low = sum(1 for r in results if r.get("confidence") == "LOW" and r.get("google_rating"))
    log.info(f"\nMatch confidence (rated only):")
    log.info(f"  HIGH:   {high}")
    log.info(f"  MEDIUM: {med}")
    log.info(f"  LOW:    {low}  ← review these in the CSV")

    # Airtable update
    if args.update_airtable and not args.dry_run:
        log.info("\n--- Updating Airtable ---")
        update_airtable(results)


if __name__ == "__main__":
    main()
