#!/usr/bin/env python3
"""
Enrich weak veterinarian descriptions from practice websites.

This is intentionally a no-extra-cost workflow:
  - no paid scraping API
  - no paid LLM/API calls
  - no direct Airtable writes

Default behavior:
  - read data/Veterinarians-Grid view.enriched.csv if it exists
  - otherwise seed from data/Veterinarians-Grid view.csv
  - process up to 10 weak/unprocessed records
  - write the working CSV plus a small review CSV

Usage:
  python3 scripts/enrich_vet_descriptions.py
  python3 scripts/enrich_vet_descriptions.py --limit 10
  python3 scripts/enrich_vet_descriptions.py --dry-run --limit 3
  python3 scripts/enrich_vet_descriptions.py --fresh
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from generate_site import Veterinarian  # noqa: E402


SOURCE_CSV = PROJECT_ROOT / "data" / "Veterinarians-Grid view.csv"
WORKING_CSV = PROJECT_ROOT / "data" / "Veterinarians-Grid view.enriched.csv"
REVIEW_CSV = PROJECT_ROOT / "data" / "description_enrichment_review.csv"

REQUEST_TIMEOUT = 14
MAX_CONTENT_BYTES = 500_000
DELAY_MIN = 1.5
DELAY_MAX = 3.0
MAX_PAGES_PER_SITE = 4

TRACKING_COLUMNS = [
    "Description Enrichment Status",
    "Description Updated",
    "Description Enriched At",
    "Description Source URL",
    "Website Valid",
    "Website Final URL",
    "Website HTTP Status",
    "Holistic Vet Signal",
    "Holistic Evidence",
    "Description Quality Score",
    "Enrichment Notes",
    "Original Practice Description",
]

REVIEW_COLUMNS = [
    "Processed At",
    "Status",
    "Description Updated",
    "Practice Name",
    "City",
    "State",
    "Website",
    "Website Valid",
    "Website HTTP Status",
    "Website Final URL",
    "Description Source URL",
    "Holistic Vet Signal",
    "Holistic Evidence",
    "Description Quality Score",
    "Old Description",
    "New Description",
    "Notes",
    "Slug",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SKIP_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
    "youtube.com",
    "yelp.com",
    "google.com",
    "maps.google.com",
    "yellowpages.com",
    "vetstreet.com",
    "petsites.com",
    "petdesk.com",
}

ANIMAL_PATTERNS = [
    (r"\bveterinar\w*", "veterinary"),
    (r"\bDVM\b|\bVMD\b", "DVM/VMD"),
    (r"\banimal\s+(hospital|clinic|care|health|wellness|medical)", "animal care"),
    (r"\bpet\s+(care|health|wellness|owner|patient|hospital|clinic)", "pet care"),
    (r"\b(dog|dogs|cat|cats|horse|horses|equine|canine|feline)\b", "species language"),
]

HOLISTIC_PATTERNS = [
    (r"\bholistic\b", "holistic"),
    (r"\bintegrative\b", "integrative"),
    (r"\bcomplementary\b", "complementary"),
    (r"\balternative\b", "alternative"),
    (r"\bacupuncture\b", "acupuncture"),
    (r"\bchiropractic\b", "chiropractic"),
    (r"\bherbal\b|\bbotanical\b", "herbal medicine"),
    (r"\bhomeopath\w*", "homeopathy"),
    (r"\bTCVM\b|traditional chinese veterinary medicine", "TCVM"),
    (r"\bChinese herbal\b", "Chinese herbal medicine"),
    (r"\bnutrition(al)? therapy\b|\btherapeutic nutrition\b", "nutritional therapy"),
    (r"\brehabilitation\b|\bphysical therapy\b|\bhydrotherapy\b", "rehabilitation"),
    (r"\blaser therapy\b|\bphotobiomodulation\b", "laser therapy"),
    (r"\bmassage therapy\b|\bTui-na\b|\btuina\b", "massage therapy"),
    (r"\bozone therapy\b", "ozone therapy"),
]

SERVICE_LABELS = [
    ("acupuncture", r"\bacupuncture\b"),
    ("chiropractic care", r"\bchiropractic\b"),
    ("herbal medicine", r"\bherbal\b|\bbotanical\b|Chinese herbal"),
    ("homeopathy", r"\bhomeopath\w*"),
    ("TCVM", r"\bTCVM\b|traditional chinese veterinary medicine"),
    ("nutritional therapy", r"\bnutrition(al)? therapy\b|\btherapeutic nutrition\b"),
    ("physical rehabilitation", r"\brehabilitation\b|\bphysical therapy\b|\bhydrotherapy\b"),
    ("laser therapy", r"\blaser therapy\b|\bphotobiomodulation\b"),
    ("massage therapy", r"\bmassage therapy\b|\bTui-na\b|\btuina\b"),
    ("ozone therapy", r"\bozone therapy\b"),
]

RECOGNIZED_CERT_LABELS = [
    "AHVMA",
    "IVAS",
    "Chi Institute",
    "AVCA",
    "CIVT",
    "VBMA",
    "CuraCore",
]

LINK_HINTS = [
    "about",
    "services",
    "holistic",
    "integrative",
    "acupuncture",
    "chiropractic",
    "rehab",
    "therapy",
    "nutrition",
    "tcvm",
]


@dataclass
class PageFetch:
    requested_url: str
    final_url: str = ""
    status_code: str = ""
    title: str = ""
    meta_description: str = ""
    text: str = ""
    ok: bool = False


@dataclass
class EnrichmentResult:
    status: str
    updated: bool
    website_valid: str
    website_status: str
    website_final_url: str
    source_url: str
    holistic_signal: str
    holistic_evidence: str
    quality_score: int
    new_description: str
    notes: str
    pages: list[PageFetch] = field(default_factory=list)


def normalize_url(raw_url: str) -> str:
    raw_url = (raw_url or "").strip()
    if not raw_url:
        return ""
    if raw_url.startswith(("http://", "https://")):
        return raw_url.rstrip("/")
    return f"https://{raw_url}".rstrip("/")


def domain_is_skippable(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return True
    return not domain or any(skip == domain or domain.endswith("." + skip) for skip in SKIP_DOMAINS)


def read_limited_content(response: requests.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_CONTENT_BYTES:
            break
    return b"".join(chunks)


def fetch_page(session: requests.Session, url: str) -> PageFetch:
    result = PageFetch(requested_url=url)
    try:
        response = session.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        result.final_url = response.url
        result.status_code = str(response.status_code)
        content_type = response.headers.get("content-type", "")
        if response.status_code >= 400 or "text/html" not in content_type.lower():
            return result

        html = read_limited_content(response)
        soup = BeautifulSoup(html, "lxml")
        result.title = (soup.title.get_text(" ", strip=True) if soup.title else "").strip()
        meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if meta and meta.get("content"):
            result.meta_description = re.sub(r"\s+", " ", meta["content"]).strip()

        for tag in soup(["script", "style", "noscript", "svg", "form", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        result.text = re.sub(r"\s+", " ", text).strip()
        result.ok = bool(result.text)
        return result
    except requests.exceptions.SSLError:
        return result
    except Exception as exc:
        result.status_code = f"error: {type(exc).__name__}"
        return result


def discover_candidate_links(home: PageFetch, base_url: str) -> list[str]:
    if not home.ok:
        return []

    try:
        response = requests.get(home.final_url or base_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code >= 400 or "text/html" not in response.headers.get("content-type", "").lower():
            return []
        soup = BeautifulSoup(response.text, "lxml")
    except Exception:
        return []

    base_domain = urlparse(home.final_url or base_url).netloc.lower().lstrip("www.")
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(home.final_url or base_url, href).split("#")[0].rstrip("/")
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        link_domain = parsed.netloc.lower().lstrip("www.")
        if link_domain != base_domain or absolute in seen:
            continue

        label = f"{anchor.get_text(' ', strip=True)} {parsed.path}".lower()
        score = sum(1 for hint in LINK_HINTS if hint in label)
        if score:
            ranked.append((score, absolute))
            seen.add(absolute)

    ranked.sort(key=lambda item: (-item[0], len(item[1])))
    return [url for _, url in ranked[: MAX_PAGES_PER_SITE - 1]]


def fetch_site_pages(website: str) -> list[PageFetch]:
    url = normalize_url(website)
    if not url or domain_is_skippable(url):
        return []

    session = requests.Session()
    home = fetch_page(session, url)

    if not home.ok and url.startswith("https://"):
        home = fetch_page(session, "http://" + url[len("https://") :])

    pages = [home]
    if home.ok:
        for link in discover_candidate_links(home, url):
            if len(pages) >= MAX_PAGES_PER_SITE:
                break
            time.sleep(random.uniform(0.35, 0.8))
            page = fetch_page(session, link)
            if page.ok:
                pages.append(page)

    return pages


def unique_labels(patterns: Iterable[tuple[str, str]], text: str) -> list[str]:
    labels: list[str] = []
    for pattern, label in patterns:
        if re.search(pattern, text, re.IGNORECASE) and label not in labels:
            labels.append(label)
    return labels


def split_multi(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[|,]", value) if part.strip()]


def service_labels_from_text(text: str) -> list[str]:
    labels: list[str] = []
    for label, pattern in SERVICE_LABELS:
        if re.search(pattern, text, re.IGNORECASE):
            labels.append(label)
    return labels


def merge_services(row: dict, source_text: str) -> list[str]:
    from_site = service_labels_from_text(source_text)
    csv_specialties = [s.lower() for s in split_multi(row.get("Specialties", ""))]

    mapped: list[str] = []
    for specialty in csv_specialties:
        specialty = specialty.replace("physical therapy/rehabilitation", "physical rehabilitation")
        specialty = specialty.replace("traditional chinese veterinary medicine", "TCVM")
        if specialty:
            mapped.append(specialty)

    services: list[str] = []
    for item in from_site + mapped:
        normalized = item.strip()
        if normalized and normalized not in services:
            services.append(normalized)
    return services[:5]


def recognized_certs(row: dict) -> list[str]:
    certs = split_multi(row.get("Certification Bodies", ""))
    recognized: list[str] = []
    for cert in certs:
        if re.search(r"\b(DVM|VMD)\b", cert, re.IGNORECASE):
            continue
        if cert not in recognized:
            recognized.append(cert)

    # Keep unknown certification text out of generated copy unless it resembles
    # one of the holistic credentialing organizations already used on the site.
    filtered: list[str] = []
    for cert in recognized:
        if any(label.lower() in cert.lower() for label in RECOGNIZED_CERT_LABELS):
            filtered.append(cert)
    return filtered


def phrase_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def stable_choice(row: dict, options: list[str]) -> str:
    key = row.get("Slug") or row.get("Practice Name") or row.get("Website") or ""
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return options[int(digest[:8], 16) % len(options)]


def species_phrase(row: dict) -> str:
    species = split_multi(row.get("Species Treated", ""))
    if not species:
        return ""
    lowered = [s.lower() for s in species[:4]]
    return f" for {phrase_list(lowered)}"


def practice_subject(row: dict) -> tuple[str, str]:
    practice = (row.get("Practice Name") or "This veterinary listing").strip()
    lower = practice.lower()
    person_like = bool(re.search(r"\b(dr\.?|dvm|vmd)\b", lower)) and not any(
        word in lower for word in ("clinic", "hospital", "center", "practice", "care", "services")
    )
    if person_like:
        return practice, "is listed as a veterinary provider"
    return practice, "is a veterinary practice"


def evidence_text(pages: list[PageFetch]) -> str:
    parts: list[str] = []
    for page in pages:
        if page.meta_description:
            parts.append(page.meta_description)
        if page.title:
            parts.append(page.title)
        if page.text:
            parts.append(page.text)
    return " ".join(parts)


def build_description(row: dict, pages: list[PageFetch], services: list[str]) -> str:
    practice, subject_phrase = practice_subject(row)
    practice_object = practice.rstrip(".")
    city = (row.get("City") or "").strip()
    state = (row.get("State") or "").strip()
    location = ", ".join(part for part in [city, state] if part)
    service_text = phrase_list(services)
    species = species_phrase(row)

    if location and service_text:
        first_options = [
            f"{practice} {subject_phrase} in {location} offering {service_text}{species}.",
            f"{practice} serves the {location} area with veterinary services that include {service_text}{species}.",
            f"Pet owners in {location} can find {service_text}{species} listed for {practice_object}.",
        ]
    elif location:
        first_options = [
            f"{practice} {subject_phrase} in {location}{species}.",
            f"{practice} serves pet owners in the {location} area{species}.",
            f"This listing connects pet owners with {practice} in {location}{species}.",
        ]
    elif service_text:
        first_options = [
            f"{practice} offers veterinary services including {service_text}{species}.",
            f"This listing references veterinary services from {practice}, including {service_text}{species}.",
            f"Pet owners can find {service_text}{species} listed for {practice_object}.",
        ]
    else:
        first_options = [
            f"{practice} {subject_phrase}{species}.",
            f"This listing helps pet owners learn more about {practice}{species}.",
            f"{practice} is included as a veterinary listing{species}.",
        ]
    first = stable_choice(row, first_options)

    certs = recognized_certs(row)
    if certs:
        second_options = [
            f"The listing references training or membership signals from {phrase_list(certs[:3])}.",
            f"Credential notes for this listing include {phrase_list(certs[:3])}.",
            f"Public listing details include credential or membership references from {phrase_list(certs[:3])}.",
        ]
    else:
        second_options = [
            "Pet owners should contact the practice directly to confirm current services, credentials, and appointment availability.",
            "Before scheduling, confirm the current practitioner, service availability, and whether the clinic is accepting new patients.",
            "Because services can change, contact the clinic to verify current offerings and appointment options.",
        ]
    second = stable_choice(row, second_options)

    third = stable_choice(row, [
        "This directory summary is based on public practice information and should be verified with the clinic before booking care.",
        "The directory uses public practice details as a starting point and recommends confirming care details directly.",
        "This summary is intended to help with initial research, not to replace direct confirmation from the veterinary team.",
    ])

    return " ".join([first, second, third])


def quality_score(row: dict, pages: list[PageFetch], animal_labels: list[str], holistic_labels: list[str], services: list[str]) -> int:
    score = 0
    if pages and pages[0].ok:
        score += 2
    if animal_labels:
        score += 2
    if holistic_labels:
        score += 2
    if len(services) >= 2:
        score += 2
    elif services:
        score += 1
    if split_multi(row.get("Species Treated", "")):
        score += 1
    if recognized_certs(row):
        score += 1
    return min(score, 10)


def already_processed(row: dict) -> bool:
    status = (row.get("Description Enrichment Status") or "").strip().lower()
    return status in {"updated", "kept existing", "skipped", "failed", "review needed"}


def needs_description(row: dict, force: bool = False) -> bool:
    if force:
        return True
    description = row.get("Practice Description") or ""
    return not Veterinarian._looks_like_real_description(description)


def enrich_row(row: dict) -> EnrichmentResult:
    website = row.get("Website", "")
    normalized = normalize_url(website)
    if not normalized:
        return EnrichmentResult(
            status="skipped",
            updated=False,
            website_valid="no",
            website_status="",
            website_final_url="",
            source_url="",
            holistic_signal="unknown",
            holistic_evidence="",
            quality_score=0,
            new_description=row.get("Practice Description", ""),
            notes="No website URL.",
        )

    if domain_is_skippable(normalized):
        return EnrichmentResult(
            status="skipped",
            updated=False,
            website_valid="no",
            website_status="skipped domain",
            website_final_url=normalized,
            source_url="",
            holistic_signal="unknown",
            holistic_evidence="",
            quality_score=0,
            new_description=row.get("Practice Description", ""),
            notes="Skipped social, search, or aggregator domain.",
        )

    pages = fetch_site_pages(normalized)
    ok_pages = [page for page in pages if page.ok]
    if not ok_pages:
        status = pages[0].status_code if pages else "no response"
        return EnrichmentResult(
            status="failed",
            updated=False,
            website_valid="no",
            website_status=status,
            website_final_url=pages[0].final_url if pages else normalized,
            source_url="",
            holistic_signal="unknown",
            holistic_evidence="",
            quality_score=0,
            new_description=row.get("Practice Description", ""),
            notes="Could not fetch usable website text.",
            pages=pages,
        )

    text = evidence_text(ok_pages)
    animal_labels = unique_labels(ANIMAL_PATTERNS, text)
    holistic_labels = unique_labels(HOLISTIC_PATTERNS, text)
    services = merge_services(row, text)
    score = quality_score(row, ok_pages, animal_labels, holistic_labels, services)

    if animal_labels and holistic_labels:
        signal = "yes"
    elif animal_labels and services:
        signal = "yes - CSV/service supported"
    elif animal_labels:
        signal = "review"
    else:
        signal = "no"

    evidence_items: list[str] = []
    for item in animal_labels + holistic_labels + services:
        if item not in evidence_items:
            evidence_items.append(item)
    evidence = ", ".join(evidence_items[:12])
    source_url = ok_pages[0].final_url or ok_pages[0].requested_url

    if score < 6 or not animal_labels:
        return EnrichmentResult(
            status="review needed",
            updated=False,
            website_valid="yes",
            website_status=ok_pages[0].status_code,
            website_final_url=ok_pages[0].final_url,
            source_url=source_url,
            holistic_signal=signal,
            holistic_evidence=evidence,
            quality_score=score,
            new_description=row.get("Practice Description", ""),
            notes="Fetched website, but evidence was not strong enough to update automatically.",
            pages=ok_pages,
        )

    description = build_description(row, ok_pages, services)
    return EnrichmentResult(
        status="updated",
        updated=True,
        website_valid="yes",
        website_status=ok_pages[0].status_code,
        website_final_url=ok_pages[0].final_url,
        source_url=source_url,
        holistic_signal=signal,
        holistic_evidence=evidence,
        quality_score=score,
        new_description=description,
        notes=f"Updated from {len(ok_pages)} fetched page(s).",
        pages=ok_pages,
    )


def load_rows(path: Path) -> tuple[list[dict], list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_review_rows(path: Path, review_rows: list[dict]) -> None:
    if not review_rows:
        return
    file_exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(review_rows)


def ensure_columns(fieldnames: list[str]) -> list[str]:
    output = list(fieldnames)
    for column in TRACKING_COLUMNS:
        if column not in output:
            output.append(column)
    return output


def update_row(row: dict, result: EnrichmentResult, processed_at: str) -> None:
    original_description = row.get("Practice Description", "")
    if not row.get("Original Practice Description"):
        row["Original Practice Description"] = original_description

    row["Description Enrichment Status"] = result.status
    row["Description Updated"] = "yes" if result.updated else "no"
    row["Description Enriched At"] = processed_at
    row["Description Source URL"] = result.source_url
    row["Website Valid"] = result.website_valid
    row["Website Final URL"] = result.website_final_url
    row["Website HTTP Status"] = result.website_status
    row["Holistic Vet Signal"] = result.holistic_signal
    row["Holistic Evidence"] = result.holistic_evidence
    row["Description Quality Score"] = str(result.quality_score)
    row["Enrichment Notes"] = result.notes

    if result.updated:
        row["Practice Description"] = result.new_description


def review_row(row: dict, result: EnrichmentResult, processed_at: str, old_description: str) -> dict:
    return {
        "Processed At": processed_at,
        "Status": result.status,
        "Description Updated": "yes" if result.updated else "no",
        "Practice Name": row.get("Practice Name", ""),
        "City": row.get("City", ""),
        "State": row.get("State", ""),
        "Website": row.get("Website", ""),
        "Website Valid": result.website_valid,
        "Website HTTP Status": result.website_status,
        "Website Final URL": result.website_final_url,
        "Description Source URL": result.source_url,
        "Holistic Vet Signal": result.holistic_signal,
        "Holistic Evidence": result.holistic_evidence,
        "Description Quality Score": str(result.quality_score),
        "Old Description": old_description,
        "New Description": result.new_description,
        "Notes": result.notes,
        "Slug": row.get("Slug", ""),
    }


def select_candidates(rows: list[dict], limit: int, force: bool) -> list[int]:
    selected: list[int] = []
    for index, row in enumerate(rows):
        if already_processed(row):
            continue
        if not needs_description(row, force=force):
            row["Description Enrichment Status"] = "kept existing"
            row["Description Updated"] = "no"
            row["Enrichment Notes"] = "Existing description passed quality gate."
            continue
        if not (row.get("Website") or "").strip():
            row["Description Enrichment Status"] = "skipped"
            row["Description Updated"] = "no"
            row["Website Valid"] = "no"
            row["Enrichment Notes"] = "No website URL."
            continue
        selected.append(index)
        if len(selected) >= limit:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich weak vet descriptions from practice websites.")
    parser.add_argument("--source", type=Path, default=SOURCE_CSV, help="Fresh Airtable export CSV.")
    parser.add_argument("--output", type=Path, default=WORKING_CSV, help="Working enriched CSV to write.")
    parser.add_argument("--review", type=Path, default=REVIEW_CSV, help="Append-only review CSV.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum records to process this run.")
    parser.add_argument("--fresh", action="store_true", help="Ignore existing output CSV and seed from source.")
    parser.add_argument("--force", action="store_true", help="Process records even if existing description looks real.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report, but do not write CSV files.")
    args = parser.parse_args()

    input_path = args.source
    if args.output.exists() and not args.fresh:
        input_path = args.output

    if not input_path.exists():
        raise SystemExit(f"Input CSV not found: {input_path}")

    rows, fieldnames = load_rows(input_path)
    fieldnames = ensure_columns(fieldnames)
    for row in rows:
        for column in TRACKING_COLUMNS:
            row.setdefault(column, "")

    candidates = select_candidates(rows, args.limit, force=args.force)
    print(f"Loaded {len(rows)} rows from {input_path}")
    print(f"Selected {len(candidates)} candidate(s) for this run")

    processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    review_rows: list[dict] = []
    updated_count = 0

    for position, row_index in enumerate(candidates, 1):
        row = rows[row_index]
        old_description = row.get("Practice Description", "")
        practice = row.get("Practice Name", "")
        website = row.get("Website", "")
        print(f"[{position}/{len(candidates)}] {practice} - {website}")

        result = enrich_row(row)
        if result.updated:
            updated_count += 1
        print(
            f"  {result.status}; website={result.website_valid}; "
            f"holistic={result.holistic_signal}; score={result.quality_score}"
        )

        update_row(row, result, processed_at)
        review_rows.append(review_row(row, result, processed_at, old_description))

        if position < len(candidates):
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    if not args.dry_run:
        write_rows(args.output, rows, fieldnames)
        append_review_rows(args.review, review_rows)
        print(f"Wrote working CSV: {args.output}")
        print(f"Appended review CSV: {args.review}")
    else:
        print("Dry run: no files written")

    print(f"Updated descriptions this run: {updated_count}/{len(candidates)}")


if __name__ == "__main__":
    main()
