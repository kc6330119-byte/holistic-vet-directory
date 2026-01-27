#!/usr/bin/env python3
"""
Holistic Veterinary Directory - Data Collection Script

Fetches veterinarian data from public directories and professional associations.
Respects robots.txt and rate limits to be a good web citizen.

Data Sources:
- AHVMA (American Holistic Veterinary Medical Association) member directory
- Chi Institute certified practitioners
- IVAS (International Veterinary Acupuncture Society) directory
- Manual Google searches compilation

Usage:
    python scripts/fetch_data.py --source ahvma --output data/collected_vets.csv
    python scripts/fetch_data.py --source all --output data/collected_vets.csv
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from ratelimit import limits, sleep_and_retry
from slugify import slugify
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('data_collection.log')
    ]
)
logger = logging.getLogger(__name__)

# Constants
USER_AGENT = (
    "HolisticVetDirectory/1.0 "
    "(Educational project; contact@example.com)"
)
REQUEST_TIMEOUT = 30
CALLS_PER_MINUTE = 20  # Rate limit: 20 requests per minute


@dataclass
class VeterinarianRecord:
    """Data class representing a veterinarian record."""
    practice_name: str
    veterinarian_names: str = ""
    specialties: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    certification_bodies: str = ""
    species_treated: str = ""
    practice_description: str = ""
    year_established: str = ""
    telehealth_available: str = "FALSE"
    status: str = "Pending Review"
    latitude: str = ""
    longitude: str = ""
    source: str = ""
    source_url: str = ""
    date_collected: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV export."""
        return asdict(self)

    def generate_slug(self) -> str:
        """Generate URL-friendly slug from practice name."""
        return slugify(self.practice_name)


class DataCollector:
    """Base class for data collection from various sources."""

    def __init__(self, output_dir: str = "data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        self.collected_records: List[VeterinarianRecord] = []
        self.seen_practices: set = set()  # For deduplication

    @sleep_and_retry
    @limits(calls=CALLS_PER_MINUTE, period=60)
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a web page with rate limiting."""
        try:
            logger.debug(f"Fetching: {url}")
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return BeautifulSoup(response.text, "lxml")
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def check_robots_txt(self, base_url: str, path: str) -> bool:
        """Check if scraping is allowed by robots.txt."""
        try:
            robots_url = urljoin(base_url, "/robots.txt")
            response = self.session.get(robots_url, timeout=10)
            if response.status_code == 200:
                # Simple check - look for Disallow rules
                for line in response.text.split("\n"):
                    if line.lower().startswith("disallow:"):
                        disallowed = line.split(":", 1)[1].strip()
                        if disallowed and path.startswith(disallowed):
                            logger.warning(f"Path {path} is disallowed by robots.txt")
                            return False
            return True
        except Exception as e:
            logger.warning(f"Could not check robots.txt: {e}")
            return True  # Proceed with caution if can't check

    def normalize_phone(self, phone: str) -> str:
        """Normalize phone number to (XXX) XXX-XXXX format."""
        if not phone:
            return ""
        # Remove all non-digits
        digits = re.sub(r'\D', '', phone)
        # Handle 10-digit US numbers
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        # Handle 11-digit with country code
        elif len(digits) == 11 and digits[0] == '1':
            return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        return phone  # Return original if can't normalize

    def normalize_state(self, state: str) -> str:
        """Normalize state to two-letter abbreviation."""
        state_map = {
            "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
            "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
            "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
            "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
            "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
            "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
            "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
            "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
            "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
            "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
            "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
            "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
            "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC"
        }
        state_lower = state.lower().strip()
        if state_lower in state_map:
            return state_map[state_lower]
        # Already abbreviated
        if len(state) == 2 and state.upper() in state_map.values():
            return state.upper()
        return state

    def normalize_url(self, url: str) -> str:
        """Ensure URL has proper format with https://."""
        if not url:
            return ""
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        # Upgrade http to https
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        return url

    def is_duplicate(self, record: VeterinarianRecord) -> bool:
        """Check if this practice has already been collected."""
        # Create a unique key from practice name and location
        key = f"{record.practice_name.lower()}|{record.city.lower()}|{record.state.lower()}"
        if key in self.seen_practices:
            return True
        self.seen_practices.add(key)
        return False

    def add_record(self, record: VeterinarianRecord) -> bool:
        """Add a record if it's not a duplicate."""
        if self.is_duplicate(record):
            logger.debug(f"Skipping duplicate: {record.practice_name}")
            return False
        self.collected_records.append(record)
        logger.info(f"Added: {record.practice_name} in {record.city}, {record.state}")
        return True

    def export_to_csv(self, filename: str) -> str:
        """Export collected records to CSV file."""
        filepath = self.output_dir / filename
        if not self.collected_records:
            logger.warning("No records to export")
            return ""

        fieldnames = [
            "Practice Name", "Veterinarian Name(s)", "Specialties", "Address",
            "City", "State", "ZIP Code", "Phone", "Email", "Website",
            "Certification Bodies", "Species Treated", "Practice Description",
            "Year Established", "Telehealth Available", "Status",
            "Latitude", "Longitude", "Source", "Source URL", "Date Collected"
        ]

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for record in self.collected_records:
                row = {
                    "Practice Name": record.practice_name,
                    "Veterinarian Name(s)": record.veterinarian_names,
                    "Specialties": record.specialties,
                    "Address": record.address,
                    "City": record.city,
                    "State": record.state,
                    "ZIP Code": record.zip_code,
                    "Phone": record.phone,
                    "Email": record.email,
                    "Website": record.website,
                    "Certification Bodies": record.certification_bodies,
                    "Species Treated": record.species_treated,
                    "Practice Description": record.practice_description,
                    "Year Established": record.year_established,
                    "Telehealth Available": record.telehealth_available,
                    "Status": record.status,
                    "Latitude": record.latitude,
                    "Longitude": record.longitude,
                    "Source": record.source,
                    "Source URL": record.source_url,
                    "Date Collected": record.date_collected,
                }
                writer.writerow(row)

        logger.info(f"Exported {len(self.collected_records)} records to {filepath}")
        return str(filepath)


class AHVMACollector(DataCollector):
    """Collector for AHVMA (American Holistic Veterinary Medical Association) directory."""

    BASE_URL = "https://www.ahvma.org"
    DIRECTORY_URL = "https://www.ahvma.org/find-a-holistic-veterinarian/"
    SOURCE_NAME = "AHVMA"

    def __init__(self, output_dir: str = "data"):
        super().__init__(output_dir)
        self.specialties_map = {
            "acupuncture": "Acupuncture",
            "chiropractic": "Chiropractic",
            "herbs": "Herbal Medicine",
            "herbal": "Herbal Medicine",
            "homeopathy": "Homeopathy",
            "nutrition": "Nutritional Therapy",
            "tcvm": "Traditional Chinese Veterinary Medicine (TCVM)",
            "chinese medicine": "Traditional Chinese Veterinary Medicine (TCVM)",
            "rehabilitation": "Physical Therapy/Rehabilitation",
            "physical therapy": "Physical Therapy/Rehabilitation",
            "laser": "Laser Therapy",
            "ozone": "Ozone Therapy",
            "prolotherapy": "Prolotherapy",
        }

    def collect(self) -> List[VeterinarianRecord]:
        """
        Collect veterinarian data from AHVMA directory.

        Note: This is a template implementation. The actual scraping logic
        will depend on the current structure of the AHVMA website.
        Always check robots.txt and terms of service before scraping.
        """
        logger.info(f"Starting collection from {self.SOURCE_NAME}")

        # Check if scraping is allowed
        if not self.check_robots_txt(self.BASE_URL, "/find-a-holistic-veterinarian/"):
            logger.error("Scraping not allowed by robots.txt")
            return []

        # Fetch the directory page
        soup = self.fetch_page(self.DIRECTORY_URL)
        if not soup:
            logger.error("Failed to fetch AHVMA directory page")
            return []

        # Note: The actual parsing logic depends on the website structure
        # This is a template that should be adapted based on the actual HTML
        logger.info(
            "AHVMA directory structure may require manual review. "
            "Please check the website and update parsing logic as needed."
        )

        # Look for common directory patterns
        # Many directories use cards, tables, or list items
        listings = self._find_listings(soup)

        for listing in tqdm(listings, desc="Processing AHVMA listings"):
            record = self._parse_listing(listing)
            if record:
                self.add_record(record)
            time.sleep(0.5)  # Be respectful with requests

        logger.info(f"Collected {len(self.collected_records)} records from AHVMA")
        return self.collected_records

    def _find_listings(self, soup: BeautifulSoup) -> List[Any]:
        """Find listing elements on the page."""
        # Try common patterns for directory listings
        patterns = [
            ('div', {'class': re.compile(r'member|listing|card|vet', re.I)}),
            ('article', {}),
            ('li', {'class': re.compile(r'member|listing', re.I)}),
            ('tr', {'class': re.compile(r'member|listing', re.I)}),
        ]

        for tag, attrs in patterns:
            listings = soup.find_all(tag, attrs)
            if listings:
                logger.info(f"Found {len(listings)} listings using pattern: {tag}, {attrs}")
                return listings

        logger.warning("No listings found with common patterns. Manual review needed.")
        return []

    def _parse_listing(self, listing: BeautifulSoup) -> Optional[VeterinarianRecord]:
        """Parse a single listing element into a VeterinarianRecord."""
        try:
            # Extract text content - adapt based on actual HTML structure
            text = listing.get_text(separator=' ', strip=True)

            # Try to find practice name (usually in heading or strong tag)
            name_elem = listing.find(['h2', 'h3', 'h4', 'strong', 'a'])
            practice_name = name_elem.get_text(strip=True) if name_elem else ""

            if not practice_name:
                return None

            # Try to find contact info
            phone = ""
            email = ""
            website = ""

            # Look for phone pattern
            phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
            if phone_match:
                phone = self.normalize_phone(phone_match.group())

            # Look for email
            email_elem = listing.find('a', href=re.compile(r'^mailto:'))
            if email_elem:
                email = email_elem.get('href', '').replace('mailto:', '')

            # Look for website
            website_elem = listing.find('a', href=re.compile(r'^https?://(?!.*ahvma)', re.I))
            if website_elem:
                website = self.normalize_url(website_elem.get('href', ''))

            # Try to extract address components
            address, city, state, zip_code = self._parse_address(text)

            # Extract specialties
            specialties = self._extract_specialties(text)

            return VeterinarianRecord(
                practice_name=practice_name,
                phone=phone,
                email=email,
                website=website,
                address=address,
                city=city,
                state=state,
                zip_code=zip_code,
                specialties=specialties,
                certification_bodies="AHVMA",
                source=self.SOURCE_NAME,
                source_url=self.DIRECTORY_URL,
            )
        except Exception as e:
            logger.error(f"Error parsing listing: {e}")
            return None

    def _parse_address(self, text: str) -> tuple:
        """Extract address components from text."""
        # Look for common address patterns
        # Pattern: City, ST ZIP or City, State ZIP
        address_pattern = r'([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)'
        match = re.search(address_pattern, text)

        if match:
            city = match.group(1).strip()
            state = match.group(2)
            zip_code = match.group(3)
            return ("", city, state, zip_code)

        return ("", "", "", "")

    def _extract_specialties(self, text: str) -> str:
        """Extract specialties from text."""
        found_specialties = []
        text_lower = text.lower()

        for keyword, specialty in self.specialties_map.items():
            if keyword in text_lower and specialty not in found_specialties:
                found_specialties.append(specialty)

        return "|".join(found_specialties)


class IVASCollector(DataCollector):
    """Collector for IVAS (International Veterinary Acupuncture Society) directory."""

    BASE_URL = "https://www.ivas.org"
    SOURCE_NAME = "IVAS"

    def collect(self) -> List[VeterinarianRecord]:
        """Collect veterinarian data from IVAS directory."""
        logger.info(f"Starting collection from {self.SOURCE_NAME}")
        logger.info(
            "IVAS collector is a template. "
            "Please review the website structure and implement parsing logic."
        )
        return self.collected_records


class ChiInstituteCollector(DataCollector):
    """Collector for Chi Institute certified practitioners."""

    BASE_URL = "https://tcvm.com"
    SOURCE_NAME = "Chi Institute"

    def collect(self) -> List[VeterinarianRecord]:
        """Collect veterinarian data from Chi Institute directory."""
        logger.info(f"Starting collection from {self.SOURCE_NAME}")
        logger.info(
            "Chi Institute collector is a template. "
            "Please review the website structure and implement parsing logic."
        )
        return self.collected_records


class ManualDataLoader(DataCollector):
    """Load and validate manually collected data from CSV files."""

    SOURCE_NAME = "Manual"

    def load_from_csv(self, filepath: str) -> List[VeterinarianRecord]:
        """Load records from an existing CSV file."""
        logger.info(f"Loading data from {filepath}")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    record = VeterinarianRecord(
                        practice_name=row.get("Practice Name", ""),
                        veterinarian_names=row.get("Veterinarian Name(s)", ""),
                        specialties=row.get("Specialties", ""),
                        address=row.get("Address", ""),
                        city=row.get("City", ""),
                        state=self.normalize_state(row.get("State", "")),
                        zip_code=row.get("ZIP Code", ""),
                        phone=self.normalize_phone(row.get("Phone", "")),
                        email=row.get("Email", ""),
                        website=self.normalize_url(row.get("Website", "")),
                        certification_bodies=row.get("Certification Bodies", ""),
                        species_treated=row.get("Species Treated", ""),
                        practice_description=row.get("Practice Description", ""),
                        year_established=row.get("Year Established", ""),
                        telehealth_available=row.get("Telehealth Available", "FALSE"),
                        status=row.get("Status", "Pending Review"),
                        latitude=row.get("Latitude", ""),
                        longitude=row.get("Longitude", ""),
                        source=row.get("Source", self.SOURCE_NAME),
                        source_url=row.get("Source URL", ""),
                    )
                    self.add_record(record)

            logger.info(f"Loaded {len(self.collected_records)} records from {filepath}")
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")

        return self.collected_records


def merge_data_sources(collectors: List[DataCollector]) -> List[VeterinarianRecord]:
    """Merge data from multiple collectors, removing duplicates."""
    all_records = []
    seen = set()

    for collector in collectors:
        for record in collector.collected_records:
            key = f"{record.practice_name.lower()}|{record.city.lower()}|{record.state.lower()}"
            if key not in seen:
                seen.add(key)
                all_records.append(record)

    logger.info(f"Merged {len(all_records)} unique records from {len(collectors)} sources")
    return all_records


def main():
    """Main entry point for data collection."""
    parser = argparse.ArgumentParser(
        description="Collect holistic veterinarian data from various sources"
    )
    parser.add_argument(
        "--source",
        choices=["ahvma", "ivas", "chi", "manual", "all"],
        default="all",
        help="Data source to collect from"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Input CSV file for manual data loading"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="collected_vets.csv",
        help="Output CSV filename"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data",
        help="Output directory"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    collectors = []

    # Initialize collectors based on source argument
    if args.source in ["ahvma", "all"]:
        collector = AHVMACollector(args.output_dir)
        collector.collect()
        collectors.append(collector)

    if args.source in ["ivas", "all"]:
        collector = IVASCollector(args.output_dir)
        collector.collect()
        collectors.append(collector)

    if args.source in ["chi", "all"]:
        collector = ChiInstituteCollector(args.output_dir)
        collector.collect()
        collectors.append(collector)

    if args.source == "manual" and args.input:
        collector = ManualDataLoader(args.output_dir)
        collector.load_from_csv(args.input)
        collectors.append(collector)

    # Merge and export
    if collectors:
        # Use the first collector to export merged data
        master_collector = DataCollector(args.output_dir)
        master_collector.collected_records = merge_data_sources(collectors)

        if master_collector.collected_records:
            output_path = master_collector.export_to_csv(args.output)
            print(f"\nData collection complete!")
            print(f"Total records: {len(master_collector.collected_records)}")
            print(f"Output file: {output_path}")
        else:
            print("\nNo records collected. Please check the logs for details.")
            print("You may need to:")
            print("1. Review the website structure and update parsing logic")
            print("2. Use manual data entry with the CSV template")
            print("3. Check if the website allows automated access")
    else:
        print("No collectors initialized. Use --help for usage information.")


if __name__ == "__main__":
    main()
