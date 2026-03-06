#!/usr/bin/env python3
"""
Holistic Vet Directory - Airtable Email Updater

Reads scraped_emails.csv and updates the Email field in Airtable
for any vet record that was found during scraping but has no email yet.

SAFETY RULES:
  - Only updates records where Email field is currently empty in Airtable
  - Only processes rows where Status = 'found' in the CSV
  - Never overwrites an existing email address
  - Logs every action for full auditability

Usage:
    python3 scripts/update_airtable_emails.py --dry-run   # Preview without updating
    python3 scripts/update_airtable_emails.py             # Apply updates to Airtable
"""

import csv
import json
import os
import argparse
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pyairtable import Api

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
SCRAPED_FILE = Path('data/scraped_emails.csv')
LOG_FILE     = Path('data/airtable_update_log.json')
TABLE_NAME   = 'Veterinarians'

# Airtable rate limit is 5 requests/second — stay safely under it
REQUEST_DELAY = 0.25
# ──────────────────────────────────────────────────────────────────────────────


def load_log() -> dict:
    """Load the update log."""
    if LOG_FILE.exists():
        with open(LOG_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {'updated': [], 'skipped': [], 'failed': [], 'last_run': None}


def save_log(log: dict):
    """Persist the update log."""
    log['last_run'] = datetime.now().isoformat()
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, indent=2)


def load_scraped_emails() -> list:
    """
    Load scraped_emails.csv and return only rows where:
      - Status is 'found'
      - Email Found is not empty
      - Slug is not empty
    """
    if not SCRAPED_FILE.exists():
        print(f'ERROR: Scraped emails file not found: {SCRAPED_FILE}')
        return []

    rows = []
    with open(SCRAPED_FILE, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if (
                row.get('Status', '').strip().lower() == 'found'
                and row.get('Email Found', '').strip()
                and row.get('Slug', '').strip()
            ):
                rows.append(row)

    return rows


def build_slug_index(table) -> dict:
    """
    Fetch all Airtable records and build a dict keyed by Slug.
    Returns: { slug: {'record_id': ..., 'has_email': bool} }
    """
    print('  Fetching all records from Airtable...')
    index = {}
    records = table.all(fields=['Slug', 'Email'])

    for record in records:
        fields = record.get('fields', {})
        slug = fields.get('Slug', '').strip()
        if slug:
            index[slug] = {
                'record_id': record['id'],
                'has_email': bool(fields.get('Email', '').strip()),
                'existing_email': fields.get('Email', '').strip(),
            }

    print(f'  Loaded {len(index)} records from Airtable.')
    return index


def main():
    parser = argparse.ArgumentParser(
        description='Update Airtable Email field from scraped_emails.csv'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview updates without writing anything to Airtable.'
    )
    args = parser.parse_args()

    # Validate credentials
    api_key = os.getenv('AIRTABLE_API_KEY', '').strip()
    base_id = os.getenv('AIRTABLE_BASE_ID', '').strip()

    if not api_key or not base_id:
        print('ERROR: Set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in your .env file.')
        return

    # Load scraped data
    scraped = load_scraped_emails()
    if not scraped:
        print('No valid scraped emails found to process.')
        return

    # Load log to avoid re-processing
    log          = load_log()
    already_done = set(log['updated'] + log['skipped'] + log['failed'])

    # Filter out already processed slugs
    to_process = [r for r in scraped if r['Slug'].strip() not in already_done]

    print(f'\nHolistic Vet Directory — Airtable Email Updater')
    print(f'{"DRY RUN MODE — no changes will be made to Airtable" if args.dry_run else "LIVE MODE"}')
    print(f'{"─" * 55}')
    print(f'  Scraped emails (found)     : {len(scraped)}')
    print(f'  Already processed          : {len(already_done)}')
    print(f'  To process this run        : {len(to_process)}')
    print(f'{"─" * 55}\n')

    if not to_process:
        print('Nothing to do — all scraped emails have been processed.')
        return

    # Connect to Airtable
    print('Connecting to Airtable...')
    try:
        api   = Api(api_key)
        table = api.table(base_id, TABLE_NAME)
    except Exception as e:
        print(f'ERROR: Could not connect to Airtable: {e}')
        return

    # Build slug index from Airtable
    slug_index = build_slug_index(table)
    print()

    updated_count = 0
    skipped_count = 0
    failed_count  = 0

    for i, row in enumerate(to_process, 1):
        slug     = row['Slug'].strip()
        email    = row['Email Found'].strip()
        practice = row.get('Practice Name', slug)

        print(f'  [{i}/{len(to_process)}] {practice}')
        print(f'           Email: {email}')

        # Check if slug exists in Airtable
        if slug not in slug_index:
            print(f'           ✗ Slug not found in Airtable — skipping')
            log['skipped'].append(slug)
            skipped_count += 1
            save_log(log)
            continue

        record = slug_index[slug]

        # Safety check — never overwrite an existing email
        if record['has_email']:
            print(f'           ✗ Already has email ({record["existing_email"]}) — skipping')
            log['skipped'].append(slug)
            skipped_count += 1
            save_log(log)
            continue

        if args.dry_run:
            print(f'           ✓ Would update record {record["record_id"]}')
            updated_count += 1
            continue

        # Apply the update
        try:
            table.update(record['record_id'], {'Email': email})
            print(f'           ✓ Updated successfully')
            log['updated'].append(slug)
            updated_count += 1
            save_log(log)
            time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f'           ✗ Failed: {e}')
            log['failed'].append(slug)
            failed_count += 1
            save_log(log)

    # Final summary
    print(f'\n{"─" * 55}')
    print(f'  {"Would update" if args.dry_run else "Updated"}  : {updated_count}')
    print(f'  Skipped  : {skipped_count}')
    print(f'  Failed   : {failed_count}')
    if not args.dry_run:
        print(f'\n  Total updated to date: {len(log["updated"])}')
        print(f'\nNext steps:')
        print(f'  1. Export fresh CSV from Airtable')
        print(f'     → Save as data/airtable_vets_export.csv')
        print(f'  2. Run the outreach script:')
        print(f'     python3 scripts/send_outreach_emails.py')
    print(f'{"─" * 55}\n')


if __name__ == '__main__':
    main()
