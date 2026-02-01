#!/usr/bin/env python3
"""
Holistic Veterinary Directory - Airtable Data Loader

Fetches data from Airtable for static site generation.
Can be used as a standalone script or imported as a module.

Usage:
    # As module (in generate_site.py):
    from scripts.airtable_loader import AirtableDataLoader
    loader = AirtableDataLoader()
    vets, specialties, states = loader.load_all()

    # As standalone (export to CSV for backup):
    python scripts/airtable_loader.py --export data/
"""

import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv
from slugify import slugify

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import pyairtable
try:
    from pyairtable import Api
    AIRTABLE_AVAILABLE = True
except ImportError:
    AIRTABLE_AVAILABLE = False
    logger.warning("pyairtable not installed. Run: pip install pyairtable")

# Environment variables
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")


@dataclass
class VeterinarianData:
    """Veterinarian data from Airtable."""
    practice_name: str
    veterinarian_names: str = ""
    specialties: List[str] = field(default_factory=list)
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    certification_bodies: List[str] = field(default_factory=list)
    species_treated: List[str] = field(default_factory=list)
    practice_description: str = ""
    year_established: Optional[int] = None
    telehealth_available: bool = False
    featured_listing: bool = False
    image_url: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    slug: str = ""
    status: str = "Active"
    airtable_id: str = ""

    def __post_init__(self):
        if not self.slug and self.practice_name:
            self.slug = slugify(self.practice_name)


@dataclass
class SpecialtyData:
    """Specialty data from Airtable."""
    name: str
    description: str = ""
    related_conditions: str = ""
    slug: str = ""
    airtable_id: str = ""

    def __post_init__(self):
        if not self.slug and self.name:
            self.slug = slugify(self.name)


@dataclass
class StateData:
    """State data from Airtable."""
    name: str
    code: str
    region: str = ""
    featured: bool = False
    slug: str = ""
    airtable_id: str = ""

    def __post_init__(self):
        if not self.slug and self.name:
            self.slug = slugify(self.name)


class AirtableDataLoader:
    """Loads data from Airtable for site generation."""

    def __init__(self, api_key: str = None, base_id: str = None):
        """
        Initialize the Airtable loader.

        Args:
            api_key: Airtable API key (or uses AIRTABLE_API_KEY env var)
            base_id: Airtable base ID (or uses AIRTABLE_BASE_ID env var)
        """
        self.api_key = api_key or AIRTABLE_API_KEY
        self.base_id = base_id or AIRTABLE_BASE_ID

        if not AIRTABLE_AVAILABLE:
            raise ImportError(
                "pyairtable is required. Install with: pip install pyairtable"
            )

        if not self.api_key:
            raise ValueError(
                "AIRTABLE_API_KEY not found. Set it in .env file or pass to constructor."
            )

        if not self.base_id:
            raise ValueError(
                "AIRTABLE_BASE_ID not found. Set it in .env file or pass to constructor."
            )

        self.api = Api(self.api_key)
        self.base = self.api.base(self.base_id)
        logger.info(f"Connected to Airtable base: {self.base_id}")

    def load_veterinarians(self, only_active: bool = True) -> List[VeterinarianData]:
        """Load veterinarians from Airtable."""
        logger.info("Loading veterinarians from Airtable...")
        table = self.base.table("Veterinarians")

        try:
            # Try filtering by Status if requested
            if only_active:
                try:
                    records = table.all(formula="{Status} = 'Active'")
                except Exception:
                    # Status field may not exist, load all records
                    logger.debug("Status field not found, loading all records")
                    records = table.all()
            else:
                records = table.all()
        except Exception as e:
            logger.error(f"Failed to load veterinarians: {e}")
            return []

        vets = []
        for record in records:
            fields = record.get("fields", {})

            vet = VeterinarianData(
                practice_name=fields.get("Practice Name", ""),
                veterinarian_names=fields.get("Veterinarian Name(s)", ""),
                specialties=fields.get("Specialties", []),
                address=fields.get("Address", ""),
                city=fields.get("City", ""),
                state=fields.get("State", ""),
                zip_code=fields.get("ZIP Code", ""),
                phone=fields.get("Phone", ""),
                email=fields.get("Email", ""),
                website=fields.get("Website", ""),
                certification_bodies=fields.get("Certification Bodies", []),
                species_treated=fields.get("Species Treated", []),
                practice_description=fields.get("Practice Description", ""),
                year_established=fields.get("Year Established"),
                telehealth_available=fields.get("Telehealth Available", False),
                featured_listing=fields.get("Featured Listing", False),
                image_url=fields.get("Image URL", ""),
                latitude=fields.get("Latitude"),
                longitude=fields.get("Longitude"),
                slug=fields.get("Slug", ""),
                status=fields.get("Status", "Active"),
                airtable_id=record.get("id", ""),
            )

            if vet.practice_name:
                vets.append(vet)

        logger.info(f"Loaded {len(vets)} veterinarians from Airtable")
        return vets

    def load_specialties(self) -> List[SpecialtyData]:
        """Load specialties from Airtable."""
        logger.info("Loading specialties from Airtable...")
        table = self.base.table("Specialties")

        try:
            records = table.all()
        except Exception as e:
            logger.error(f"Failed to load specialties: {e}")
            return []

        specialties = []
        for record in records:
            fields = record.get("fields", {})

            specialty = SpecialtyData(
                name=fields.get("Specialty Name", ""),
                description=fields.get("Description", ""),
                related_conditions=fields.get("Related Conditions", ""),
                slug=fields.get("Slug", ""),
                airtable_id=record.get("id", ""),
            )

            if specialty.name:
                specialties.append(specialty)

        logger.info(f"Loaded {len(specialties)} specialties from Airtable")
        return specialties

    def load_states(self) -> List[StateData]:
        """Load states from Airtable."""
        logger.info("Loading states from Airtable...")
        table = self.base.table("States")

        try:
            records = table.all()
        except Exception as e:
            logger.error(f"Failed to load states: {e}")
            return []

        states = []
        for record in records:
            fields = record.get("fields", {})

            state = StateData(
                name=fields.get("State Name", ""),
                code=fields.get("State Code", ""),
                region=fields.get("Region", ""),
                featured=fields.get("Featured", False),
                slug=fields.get("Slug", ""),
                airtable_id=record.get("id", ""),
            )

            if state.name and state.code:
                states.append(state)

        logger.info(f"Loaded {len(states)} states from Airtable")
        return states

    def load_all(self) -> Tuple[List[VeterinarianData], List[SpecialtyData], List[StateData]]:
        """Load all data from Airtable."""
        vets = self.load_veterinarians()
        specialties = self.load_specialties()
        states = self.load_states()
        return vets, specialties, states

    def export_to_csv(self, output_dir: str):
        """Export all Airtable data to CSV files for backup."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        vets = self.load_veterinarians(only_active=False)
        vets_file = output_path / f"veterinarians_backup_{timestamp}.csv"
        self._export_vets_csv(vets, vets_file)

        specialties = self.load_specialties()
        specs_file = output_path / f"specialties_backup_{timestamp}.csv"
        self._export_specialties_csv(specialties, specs_file)

        states = self.load_states()
        states_file = output_path / f"states_backup_{timestamp}.csv"
        self._export_states_csv(states, states_file)

        logger.info(f"Exported data to {output_dir}")

    def _export_vets_csv(self, vets: List[VeterinarianData], filepath: Path):
        """Export veterinarians to CSV."""
        fieldnames = [
            "Practice Name", "Veterinarian Name(s)", "Specialties", "Address",
            "City", "State", "ZIP Code", "Phone", "Email", "Website",
            "Certification Bodies", "Species Treated", "Practice Description",
            "Year Established", "Telehealth Available", "Featured Listing",
            "Latitude", "Longitude", "Slug", "Status"
        ]

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for vet in vets:
                writer.writerow({
                    "Practice Name": vet.practice_name,
                    "Veterinarian Name(s)": vet.veterinarian_names,
                    "Specialties": "|".join(vet.specialties),
                    "Address": vet.address,
                    "City": vet.city,
                    "State": vet.state,
                    "ZIP Code": vet.zip_code,
                    "Phone": vet.phone,
                    "Email": vet.email,
                    "Website": vet.website,
                    "Certification Bodies": "|".join(vet.certification_bodies),
                    "Species Treated": "|".join(vet.species_treated),
                    "Practice Description": vet.practice_description,
                    "Year Established": vet.year_established or "",
                    "Telehealth Available": "TRUE" if vet.telehealth_available else "FALSE",
                    "Featured Listing": "TRUE" if vet.featured_listing else "FALSE",
                    "Latitude": vet.latitude or "",
                    "Longitude": vet.longitude or "",
                    "Slug": vet.slug,
                    "Status": vet.status,
                })

        logger.info(f"Exported {len(vets)} veterinarians to {filepath}")

    def _export_specialties_csv(self, specialties: List[SpecialtyData], filepath: Path):
        """Export specialties to CSV."""
        fieldnames = ["Specialty Name", "Description", "Related Conditions", "Slug"]

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for spec in specialties:
                writer.writerow({
                    "Specialty Name": spec.name,
                    "Description": spec.description,
                    "Related Conditions": spec.related_conditions,
                    "Slug": spec.slug,
                })

        logger.info(f"Exported {len(specialties)} specialties to {filepath}")

    def _export_states_csv(self, states: List[StateData], filepath: Path):
        """Export states to CSV."""
        fieldnames = ["State Name", "State Code", "Region", "Featured", "Slug"]

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for state in states:
                writer.writerow({
                    "State Name": state.name,
                    "State Code": state.code,
                    "Region": state.region,
                    "Featured": "TRUE" if state.featured else "FALSE",
                    "Slug": state.slug,
                })

        logger.info(f"Exported {len(states)} states to {filepath}")


def check_airtable_connection() -> bool:
    """Check if Airtable connection is configured and working."""
    if not AIRTABLE_AVAILABLE:
        logger.error("pyairtable not installed")
        return False

    if not AIRTABLE_API_KEY:
        logger.error("AIRTABLE_API_KEY not set")
        return False

    if not AIRTABLE_BASE_ID:
        logger.error("AIRTABLE_BASE_ID not set")
        return False

    try:
        loader = AirtableDataLoader()
        table = loader.base.table("Veterinarians")
        table.all(max_records=1)
        logger.info("Airtable connection successful!")
        return True
    except Exception as e:
        logger.error(f"Airtable connection failed: {e}")
        return False


def main():
    """Main entry point for standalone usage."""
    parser = argparse.ArgumentParser(
        description="Load data from Airtable for site generation"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check Airtable connection"
    )
    parser.add_argument(
        "--export",
        type=str,
        metavar="DIR",
        help="Export Airtable data to CSV files in specified directory"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.check:
        success = check_airtable_connection()
        sys.exit(0 if success else 1)

    if args.export:
        try:
            loader = AirtableDataLoader()
            loader.export_to_csv(args.export)
            print(f"\nData exported to: {args.export}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    try:
        loader = AirtableDataLoader()
        vets, specs, states = loader.load_all()

        print("\nAirtable Data Summary:")
        print(f"  Veterinarians: {len(vets)}")
        print(f"  Specialties: {len(specs)}")
        print(f"  States: {len(states)}")

        if vets:
            print("\nSample veterinarians:")
            for vet in vets[:3]:
                print(f"  - {vet.practice_name} ({vet.city}, {vet.state})")
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure AIRTABLE_API_KEY and AIRTABLE_BASE_ID are set in .env")
        sys.exit(1)


if __name__ == "__main__":
    main()
