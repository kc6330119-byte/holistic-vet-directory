#!/usr/bin/env python3
"""
Holistic Vet Directory - Website Email Scraper

Scrapes vet websites to find email addresses for practices that have
a website but no email in Airtable.

RUNBOOK — How to use this script in the full outreach pipeline:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1: Run this script to scrape emails from vet websites:
            python3 scripts/scrape_emails.py

Step 2: Review the results file:
            data/scraped_emails.csv
        Check that emails look legitimate before importing.
        Remove any rows you don't want to use.

Step 3: Update Airtable manually — for each valid row in the CSV,
        find the practice by Slug or Practice Name and add the
        email to the Email field.

Step 4: Export a fresh CSV from Airtable and save it as:
            data/airtable_vets_export.csv
        (overwrite the existing file)

Step 5: Run the outreach script as normal — it automatically skips
        anyone already contacted and picks up the new emails:
            python3 scripts/send_outreach_emails.py

Notes:
  - Run with --dry-run to preview without making any web requests
  - Run with --limit N to process only N sites (good for testing)
  - Progress is saved after each site — safe to stop and resume
  - Already-scraped sites are skipped on subsequent runs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Usage:
    python3 scripts/scrape_emails.py             # Run full scrape
    python3 scripts/scrape_emails.py --dry-run   # Preview without requests
    python3 scripts/scrape_emails.py --limit 20  # Test with 20 sites
"""

import csv
import json
import re
import time
import argparse
import random
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Configuration ──────────────────────────────────────────────────────────────
DATA_FILE      = Path('data/airtable_vets_export.csv')
RESULTS_FILE   = Path('data/scraped_emails.csv')
PROGRESS_FILE  = Path('data/scrape_progress.json')

# Seconds to wait between requests (randomized within range for politeness)
DELAY_MIN = 2.0
DELAY_MAX = 3.5

# Pages to check on each site (in order)
PAGES_TO_TRY = ['', '/contact', '/contact-us']

# Request timeout in seconds
REQUEST_TIMEOUT = 10

# Large chains and aggregators to skip — not independent holistic practices
SKIP_DOMAINS = {
    'banfield.com',
    'banfield.net',
    'bluepearlvet.com',
    'vcahospitals.com',
    'vca.com',
    'medvet.com',
    'petvetcarecenters.com',
    'carevethealth.com',
    'petsites.com',
    'vetstreet.com',
    'vizisites.com',
    'animalgenl.com',
    'petco.com',
    'petsmart.com',
    'villagevetclinic.com',
    'thrivevet.com',
    'lap-of-love.com',
    'nationalpetpharmacy.com',
    'embrace petinsurance.com',
    'mercola.com',
}

# Email patterns to reject — generic/unlikely to be useful
REJECT_EMAIL_PATTERNS = [
    r'example\.com',
    r'test\.com',
    r'domain\.com',
    r'yoursite\.com',
    r'sentry\.io',
    r'wixpress\.com',
    r'squarespace\.com',
    r'wordpress\.com',
    r'godaddy\.com',
    r'donotreply@',
    r'noreply@',
    r'no-reply@',
    r'privacy@',
    r'postmaster@',
    r'webmaster@',
    r'abuse@',
    r'support@.*(?:software|tech|web|host)',
]

# Request headers to appear as a normal browser visit
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}
# ──────────────────────────────────────────────────────────────────────────────


def load_progress() -> dict:
    """Load scrape progress so runs can resume where they left off."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {'scraped_slugs': [], 'last_run': None}


def save_progress(progress: dict):
    """Persist progress to disk."""
    progress['last_run'] = datetime.now().isoformat()
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2)


def load_results() -> list:
    """Load existing results so we can append to them."""
    if not RESULTS_FILE.exists():
        return []
    with open(RESULTS_FILE, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def save_result(row: dict):
    """Append a single result row to the CSV."""
    fieldnames = ['Practice Name', 'Slug', 'Website', 'Email Found', 'Page Found On', 'Status']
    file_exists = RESULTS_FILE.exists()
    with open(RESULTS_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def is_skippable_domain(website: str) -> bool:
    """Return True if the website belongs to a chain or aggregator to skip."""
    try:
        domain = urlparse(website).netloc.lower().lstrip('www.')
        return any(skip in domain for skip in SKIP_DOMAINS)
    except Exception:
        return False


def extract_emails(html: str, base_url: str) -> list:
    """
    Extract email addresses from HTML content.
    Checks both mailto: links and raw email patterns in text.
    Returns a deduplicated, filtered list of plausible emails.
    """
    emails = set()

    # Method 1: mailto: links (most reliable)
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all('a', href=True):
        href = tag['href']
        if href.startswith('mailto:'):
            email = href[7:].split('?')[0].strip().lower()
            if email:
                emails.add(email)

    # Method 2: regex pattern in raw text (catches plaintext emails)
    pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    for match in re.findall(pattern, html):
        emails.add(match.lower())

    # Filter out obviously bad emails
    filtered = []
    for email in emails:
        if any(re.search(p, email, re.IGNORECASE) for p in REJECT_EMAIL_PATTERNS):
            continue
        # Must have a real-looking domain
        if '.' not in email.split('@')[-1]:
            continue
        filtered.append(email)

    return filtered


def fetch_page(url: str) -> Optional[str]:
    """
    Fetch a page and return HTML, or None on failure.
    Handles redirects, timeouts, and common errors gracefully.
    """
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if response.status_code == 200:
            return response.text
        return None
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.TooManyRedirects:
        return None
    except requests.exceptions.SSLError:
        # Try without SSL verification as fallback
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
                verify=False,
            )
            return response.text if response.status_code == 200 else None
        except Exception:
            return None
    except Exception:
        return None


def scrape_site(website: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Try homepage then /contact page to find an email.
    Returns (email, page_path) or (None, None) if not found.
    """
    # Normalize URL
    if not website.startswith('http'):
        website = 'https://' + website

    base = website.rstrip('/')

    for path in PAGES_TO_TRY:
        url = base + path if path else base
        html = fetch_page(url)

        if html:
            emails = extract_emails(html, url)
            if emails:
                # Prefer emails that match the site's own domain
                domain = urlparse(base).netloc.lower().lstrip('www.')
                domain_emails = [e for e in emails if domain.split('.')[0] in e]
                chosen = domain_emails[0] if domain_emails else emails[0]
                page_label = path if path else '/'
                return chosen, page_label

        # Polite delay between page requests on same site
        time.sleep(0.5)

    return None, None


def main():
    parser = argparse.ArgumentParser(
        description='Scrape vet websites to find missing email addresses.'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview which sites would be scraped without making any requests.'
    )
    parser.add_argument(
        '--limit', type=int, default=0,
        help='Process only N sites (default: all). Useful for testing.'
    )
    args = parser.parse_args()

    # Load state
    progress     = load_progress()
    already_done = set(progress['scraped_slugs'])

    # Read CSV
    if not DATA_FILE.exists():
        print(f'ERROR: Data file not found: {DATA_FILE}')
        return

    with open(DATA_FILE, encoding='utf-8-sig') as f:
        all_rows = list(csv.DictReader(f))

    # Filter: no email, has website, has slug, not already scraped, not a chain
    to_scrape = [
        r for r in all_rows
        if not r.get('Email', '').strip()
        and r.get('Website', '').strip()
        and r.get('Slug', '').strip()
        and r['Slug'].strip() not in already_done
        and not is_skippable_domain(r.get('Website', ''))
    ]

    if args.limit:
        to_scrape = to_scrape[:args.limit]

    # Summary
    print(f'\nHolistic Vet Directory — Email Scraper')
    print(f'{"DRY RUN MODE — no web requests will be made" if args.dry_run else "LIVE MODE"}')
    print(f'{"─" * 55}')
    print(f'  Total vets in CSV          : {len(all_rows)}')
    print(f'  Already have email         : {len([r for r in all_rows if r.get("Email", "").strip()])}')
    print(f'  Already scraped            : {len(already_done)}')
    print(f'  Skipped (chains/no website): {len(all_rows) - len([r for r in all_rows if not r.get("Email","").strip() and r.get("Website","").strip()]) }')
    print(f'  To scrape this run         : {len(to_scrape)}')
    print(f'{"─" * 55}\n')

    if not to_scrape:
        print('Nothing to scrape — all eligible sites have been processed.')
        return

    if args.dry_run:
        print('Sites that would be scraped (first 20):')
        for r in to_scrape[:20]:
            print(f'  {r.get("Practice Name", "")} — {r.get("Website", "")}')
        if len(to_scrape) > 20:
            print(f'  ... and {len(to_scrape) - 20} more')
        return

    # Scrape
    found_count = 0
    not_found_count = 0
    skipped_count = 0

    for i, row in enumerate(to_scrape, 1):
        practice  = row.get('Practice Name', '').strip()
        website   = row.get('Website', '').strip()
        slug      = row.get('Slug', '').strip()

        print(f'  [{i}/{len(to_scrape)}] {practice}')
        print(f'           {website}')

        email, page = scrape_site(website)

        if email:
            found_count += 1
            status = 'found'
            print(f'           ✓ Found: {email} (on {page})')
        else:
            not_found_count += 1
            status = 'not found'
            print(f'           ✗ No email found')

        # Save result
        save_result({
            'Practice Name': practice,
            'Slug': slug,
            'Website': website,
            'Email Found': email or '',
            'Page Found On': page or '',
            'Status': status,
        })

        # Mark as scraped
        progress['scraped_slugs'].append(slug)
        save_progress(progress)

        # Polite delay between sites
        delay = random.uniform(DELAY_MIN, DELAY_MAX)
        time.sleep(delay)

    # Final summary
    print(f'\n{"─" * 55}')
    print(f'  Found emails   : {found_count}')
    print(f'  Not found      : {not_found_count}')
    print(f'  Total scraped  : {found_count + not_found_count}')
    print(f'\n  Results saved to: {RESULTS_FILE}')
    print(f'\nNext step: Review {RESULTS_FILE}, then update Airtable')
    print(f'           with confirmed emails before running outreach.')
    print(f'{"─" * 55}\n')


if __name__ == '__main__':
    main()
