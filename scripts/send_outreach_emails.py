#!/usr/bin/env python3
"""
Holistic Vet Directory - Veterinarian Outreach Email Script

Sends personalized emails to listed veterinarians inviting them to
claim/review their profile and optionally link back to it.

Tracks sent emails in data/outreach_sent.json to avoid duplicates
across runs. Sends up to 150 emails per run to stay within Gmail limits.

Usage:
    python scripts/send_outreach_emails.py --dry-run   # Preview without sending
    python scripts/send_outreach_emails.py             # Send up to 150 emails
    python scripts/send_outreach_emails.py --limit 50  # Send up to 50 emails
"""

import csv
import json
import smtplib
import ssl
import os
import argparse
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
DATA_FILE    = Path('data/airtable_vets_export.csv')
LOG_FILE     = Path('data/outreach_sent.json')
FAILED_FILE  = Path('data/outreach_failed.json')
DAILY_LIMIT  = 80
SITE_URL     = 'https://holisticvetdirectory.com'
FROM_NAME    = 'Kevin'
# ──────────────────────────────────────────────────────────────────────────────


def load_sent_log() -> dict:
    """Load the JSON log of emails already sent."""
    if LOG_FILE.exists():
        with open(LOG_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {'sent': [], 'total_sent': 0, 'last_run': None}


def save_sent_log(log: dict):
    """Persist the sent log to disk."""
    log['last_run'] = datetime.now().isoformat()
    log['total_sent'] = len(log['sent'])
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, indent=2)


def load_failed_log() -> set:
    """Load the set of emails that have permanently failed."""
    if FAILED_FILE.exists():
        with open(FAILED_FILE, encoding='utf-8') as f:
            data = json.load(f)
            return set(data.get('failed', []))
    return set()


def log_failed(email: str, practice: str, error: str):
    """Append a permanently failed email to the failed log."""
    data = {'failed': []}
    if FAILED_FILE.exists():
        with open(FAILED_FILE, encoding='utf-8') as f:
            data = json.load(f)
    if email not in data['failed']:
        data['failed'].append(email)
    data['total_failed'] = len(data['failed'])
    data['last_updated'] = datetime.now().isoformat()
    with open(FAILED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def parse_pipe_list(value: str) -> list:
    """Split a pipe-delimited or comma-delimited Airtable multi-select field."""
    if not value or not value.strip():
        return []
    if '|' in value:
        return [s.strip() for s in value.split('|') if s.strip()]
    return [s.strip() for s in value.split(',') if s.strip()]


def build_greeting(vet_names: str, practice_name: str) -> str:
    """
    Extract a clean greeting name from the Veterinarian Name(s) field.
    e.g. 'Dr. Kellie Lindquist, DVM, CVA' -> 'Dr. Kellie Lindquist'
    Falls back to 'the team at {practice_name}' if no name available.
    """
    if not vet_names or not vet_names.strip():
        return f'the team at {practice_name}'

    # Take only the first vet when multiple are listed (separated by ' and ' or newlines)
    first = vet_names.replace(' and ', '|').replace('\n', '|').split('|')[0].strip()

    # Strip credential suffixes — everything after the first comma following the name
    # e.g. 'Dr. Kellie Lindquist, DVM, CVA' -> 'Dr. Kellie Lindquist'
    parts = first.split(',')
    name = parts[0].strip()

    return name if name else f'the team at {practice_name}'


def build_specialty_string(specialties: list) -> str:
    """Format a specialties list into readable prose."""
    if not specialties:
        return 'integrative veterinary care'
    if len(specialties) == 1:
        return specialties[0]
    if len(specialties) == 2:
        return f'{specialties[0]} and {specialties[1]}'
    # Show up to 3, summarise the rest
    shown = specialties[:3]
    remainder = len(specialties) - 3
    base = ', '.join(shown[:-1]) + f' and {shown[-1]}'
    if remainder > 0:
        base += f', among other modalities'
    return base


def build_email(row: dict) -> tuple[str, str]:
    """
    Build the subject and plain-text body for one vet's outreach email.
    Returns (subject, body).
    """
    practice_name = row.get('Practice Name', '').strip()
    vet_names     = row.get('Veterinarian Name(s)', '').strip()
    city          = row.get('City', '').strip()
    state         = row.get('State', '').strip()
    slug          = row.get('Slug', '').strip()
    specialties   = parse_pipe_list(row.get('Specialties', ''))

    greeting      = build_greeting(vet_names, practice_name)
    spec_str      = build_specialty_string(specialties)
    profile_url   = f'{SITE_URL}/vet/{slug}/'

    subject = f'Your practice is listed on Holistic Vet Directory'

    body = f"""Hi {greeting},

I wanted to let you know that {practice_name} is now featured in the Holistic Vet Directory:

    {profile_url}

Your listing highlights your work in {spec_str} for pet owners in {city}, {state} who are actively searching for integrative and holistic veterinary care.

If you'd like to update your listing, add more detail, or make any corrections, just reply to this email and I'll take care of it personally.

One small favor — if you find the directory helpful, adding a link from your website to your profile page helps pet owners in {city} find you more easily when searching online for holistic veterinary care. It's a simple way to increase your visibility with people already looking for what you offer.

Thank you for the important work you do,

Kevin
Holistic Vet Directory
{SITE_URL}
"""

    return subject, body


def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str,
    app_password: str,
    dry_run: bool = False,
) -> bool:
    """Send a single plain-text email via Gmail SMTP. Returns True on success."""
    if dry_run:
        print(f"\n{'─' * 60}")
        print(f"  TO      : {to_email}")
        print(f"  SUBJECT : {subject}")
        print(f"  BODY    :\n")
        for line in body.splitlines():
            print(f"    {line}")
        print(f"{'─' * 60}")
        return True

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f'{FROM_NAME} <{from_email}>'
    msg['To']      = to_email
    msg.attach(MIMEText(body, 'plain'))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as server:
        server.login(from_email, app_password)
        server.sendmail(from_email, to_email, msg.as_string())

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Send personalized outreach emails to listed veterinarians.'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview emails to the console without sending anything.'
    )
    parser.add_argument(
        '--limit', type=int, default=DAILY_LIMIT,
        help=f'Max emails to send this run (default: {DAILY_LIMIT}).'
    )
    args = parser.parse_args()

    # Validate credentials before doing any work (skip in dry-run)
    gmail_address  = os.getenv('OUTREACH_EMAIL', '').strip()
    gmail_password = os.getenv('OUTREACH_APP_PASSWORD', '').strip()

    if not args.dry_run:
        if not gmail_address or not gmail_password:
            print(
                'ERROR: Set OUTREACH_EMAIL and OUTREACH_APP_PASSWORD '
                'in your .env file before sending.'
            )
            return

    # Load progress logs
    log           = load_sent_log()
    already_sent  = set(log['sent'])
    already_failed = load_failed_log()

    # Read and filter CSV
    if not DATA_FILE.exists():
        print(f'ERROR: Data file not found: {DATA_FILE}')
        return

    with open(DATA_FILE, encoding='utf-8-sig') as f:
        all_rows = list(csv.DictReader(f))

    vets_with_email = [r for r in all_rows if r.get('Email', '').strip()]
    to_contact      = [
        r for r in vets_with_email
        if r['Email'].strip() not in already_sent
        and r['Email'].strip() not in already_failed
        and r.get('Slug', '').strip()
    ]

    # Summary
    print(f'\nHolistic Vet Directory — Outreach Email Script')
    print(f'{"DRY RUN MODE — no emails will be sent" if args.dry_run else "LIVE MODE"}')
    print(f'{"─" * 50}')
    print(f'  Total vets in CSV        : {len(all_rows)}')
    print(f'  Vets with email          : {len(vets_with_email)}')
    print(f'  Already contacted        : {len(already_sent)}')
    print(f'  Permanently skipped      : {len(already_failed)}')
    print(f'  Remaining to contact     : {len(to_contact)}')
    print(f'  Sending this run (max)   : {args.limit}')
    print(f'{"─" * 50}\n')

    if not to_contact:
        print('Nothing to do — all vets with email addresses have been contacted.')
        return

    sent_count = 0
    error_count = 0

    for row in to_contact[:args.limit]:
        email   = row['Email'].strip()
        subject, body = build_email(row)

        try:
            send_email(
                to_email=email,
                subject=subject,
                body=body,
                from_email=gmail_address,
                app_password=gmail_password,
                dry_run=args.dry_run,
            )
            sent_count += 1

            if not args.dry_run:
                log['sent'].append(email)
                save_sent_log(log)  # Save after every send so a crash never loses progress
                print(f'  ✓ ({sent_count}/{args.limit}) {row.get("Practice Name", email)} <{email}>')

        except Exception as e:
            error_count += 1
            if not args.dry_run:
                log_failed(email, row.get('Practice Name', ''), str(e))
            print(f'  ✗ FAILED — {row.get("Practice Name", email)} <{email}>: {e}')

    # Final summary
    print(f'\n{"─" * 50}')
    print(f'  {"Previewed" if args.dry_run else "Sent"}     : {sent_count}')
    print(f'  Errors   : {error_count}')
    if not args.dry_run:
        print(f'  Total contacted to date : {len(log["sent"])}')
        remaining = len(to_contact) - sent_count
        print(f'  Still remaining         : {remaining}')
        if remaining > 0:
            days_left = -(-remaining // args.limit)  # ceiling division
            print(f'  Est. days to complete   : {days_left} more run(s) of {args.limit}')
    print(f'{"─" * 50}\n')


if __name__ == '__main__':
    main()
