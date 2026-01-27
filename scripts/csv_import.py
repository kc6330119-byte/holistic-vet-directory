#!/usr/bin/env python3
"""
Holistic Veterinary Directory - CSV Import & Validation Utility

Validates CSV data, normalizes formats, and prepares data for Airtable import.
Can also directly upload to Airtable via API.

Usage:
    python scripts/csv_import.py --validate data/veterinarians.csv
    python scripts/csv_import.py --normalize data/collected_vets.csv --output data/normalized_vets.csv
    python scripts/csv_import.py --upload data/veterinarians.csv --table Veterinarians
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv
from slugify import slugify
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import pyairtable (optional for validation-only mode)
try:
    from pyairtable import Api, Table
    AIRTABLE_AVAILABLE = True
except ImportError:
    AIRTABLE_AVAILABLE = False
    logger.warning("pyairtable not installed. Airtable upload disabled.")

# Constants
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")

# Valid values for multiple select fields
VALID_SPECIALTIES = [
    "Acupuncture",
    "Chiropractic",
    "Herbal Medicine",
    "Homeopathy",
    "Nutritional Therapy",
    "Physical Therapy/Rehabilitation",
    "Traditional Chinese Veterinary Medicine (TCVM)",
    "Aromatherapy",
    "Massage Therapy",
    "Laser Therapy",
    "Energy Medicine (Reiki)",
    "Prolotherapy",
    "Ozone Therapy",
    "Naturopathy",
]

VALID_CERTIFICATION_BODIES = [
    "AHVMA",
    "Chi Institute",
    "CIVT",
    "VBMA",
    "IVAS",
    "AVCA",
    "Academy of Veterinary Homeopathy",
]

VALID_SPECIES = [
    "Dogs",
    "Cats",
    "Horses",
    "Exotic",
    "Farm Animals",
    "Birds",
    "Reptiles",
]

VALID_STATUSES = ["Active", "Pending Review", "Inactive"]

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
}


@dataclass
class ValidationError:
    """Represents a validation error."""
    row_number: int
    field: str
    value: str
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class ValidationResult:
    """Result of CSV validation."""
    is_valid: bool
    total_rows: int
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    def add_error(self, row: int, field: str, value: str, message: str):
        self.errors.append(ValidationError(row, field, value, message, "error"))
        self.is_valid = False

    def add_warning(self, row: int, field: str, value: str, message: str):
        self.warnings.append(ValidationError(row, field, value, message, "warning"))

    def summary(self) -> str:
        lines = [
            f"Validation {'PASSED' if self.is_valid else 'FAILED'}",
            f"Total rows: {self.total_rows}",
            f"Errors: {len(self.errors)}",
            f"Warnings: {len(self.warnings)}",
        ]
        return "\n".join(lines)


class CSVValidator:
    """Validates CSV data against the schema."""

    def __init__(self):
        self.result = ValidationResult(is_valid=True, total_rows=0)

    def validate_file(self, filepath: str) -> ValidationResult:
        """Validate a CSV file."""
        logger.info(f"Validating: {filepath}")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:
            self.result.add_error(0, "file", filepath, f"Could not read file: {e}")
            return self.result

        self.result.total_rows = len(rows)

        for i, row in enumerate(rows, start=2):  # Start at 2 (header is row 1)
            self._validate_row(i, row)

        return self.result

    def _validate_row(self, row_num: int, row: Dict[str, str]):
        """Validate a single row."""
        # Required fields
        practice_name = row.get("Practice Name", "").strip()
        if not practice_name:
            self.result.add_error(row_num, "Practice Name", "", "Practice Name is required")

        # State validation
        state = row.get("State", "").strip().upper()
        if state and state not in US_STATES:
            self.result.add_error(row_num, "State", state, f"Invalid state code: {state}")

        # ZIP code validation
        zip_code = row.get("ZIP Code", "").strip()
        if zip_code and not re.match(r'^\d{5}(-\d{4})?$', zip_code):
            self.result.add_warning(row_num, "ZIP Code", zip_code, "Invalid ZIP code format")

        # Phone validation
        phone = row.get("Phone", "").strip()
        if phone:
            digits = re.sub(r'\D', '', phone)
            if len(digits) not in [10, 11]:
                self.result.add_warning(row_num, "Phone", phone, "Phone should have 10 digits")

        # Email validation
        email = row.get("Email", "").strip()
        if email and not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            self.result.add_error(row_num, "Email", email, "Invalid email format")

        # Website validation
        website = row.get("Website", "").strip()
        if website and not website.startswith(('http://', 'https://')):
            self.result.add_warning(row_num, "Website", website, "Website should start with https://")

        # Specialties validation
        specialties = row.get("Specialties", "").strip()
        if specialties:
            for spec in specialties.split("|"):
                spec = spec.strip()
                if spec and spec not in VALID_SPECIALTIES:
                    self.result.add_warning(
                        row_num, "Specialties", spec,
                        f"Unknown specialty: {spec}. Valid: {', '.join(VALID_SPECIALTIES[:5])}..."
                    )

        # Certification bodies validation
        certs = row.get("Certification Bodies", "").strip()
        if certs:
            for cert in certs.split("|"):
                cert = cert.strip()
                if cert and cert not in VALID_CERTIFICATION_BODIES:
                    self.result.add_warning(
                        row_num, "Certification Bodies", cert,
                        f"Unknown certification: {cert}"
                    )

        # Species validation
        species = row.get("Species Treated", "").strip()
        if species:
            for sp in species.split("|"):
                sp = sp.strip()
                if sp and sp not in VALID_SPECIES:
                    self.result.add_warning(
                        row_num, "Species Treated", sp,
                        f"Unknown species: {sp}"
                    )

        # Status validation
        status = row.get("Status", "").strip()
        if status and status not in VALID_STATUSES:
            self.result.add_warning(row_num, "Status", status, f"Invalid status: {status}")

        # Year validation
        year = row.get("Year Established", "").strip()
        if year:
            try:
                year_int = int(year)
                if year_int < 1900 or year_int > 2030:
                    self.result.add_warning(row_num, "Year Established", year, "Year seems invalid")
            except ValueError:
                self.result.add_warning(row_num, "Year Established", year, "Year should be a number")

        # Coordinate validation
        lat = row.get("Latitude", "").strip()
        lng = row.get("Longitude", "").strip()
        if lat:
            try:
                lat_f = float(lat)
                if not (-90 <= lat_f <= 90):
                    self.result.add_error(row_num, "Latitude", lat, "Latitude must be between -90 and 90")
            except ValueError:
                self.result.add_error(row_num, "Latitude", lat, "Latitude must be a number")
        if lng:
            try:
                lng_f = float(lng)
                if not (-180 <= lng_f <= 180):
                    self.result.add_error(row_num, "Longitude", lng, "Longitude must be between -180 and 180")
            except ValueError:
                self.result.add_error(row_num, "Longitude", lng, "Longitude must be a number")


class CSVNormalizer:
    """Normalizes CSV data to match Airtable schema."""

    def __init__(self):
        self.state_map = self._build_state_map()

    def _build_state_map(self) -> Dict[str, str]:
        """Build a mapping of state names to abbreviations."""
        return {
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

    def normalize_file(self, input_path: str, output_path: str) -> int:
        """Normalize a CSV file and write to output."""
        logger.info(f"Normalizing: {input_path}")

        with open(input_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames

        # Add Slug field if not present
        if "Slug" not in fieldnames:
            fieldnames = list(fieldnames) + ["Slug"]

        normalized_rows = []
        for row in tqdm(rows, desc="Normalizing"):
            normalized = self._normalize_row(row)
            normalized_rows.append(normalized)

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(normalized_rows)

        logger.info(f"Normalized {len(normalized_rows)} rows to {output_path}")
        return len(normalized_rows)

    def _normalize_row(self, row: Dict[str, str]) -> Dict[str, str]:
        """Normalize a single row."""
        normalized = dict(row)

        # Normalize state
        state = row.get("State", "").strip()
        if state:
            state_lower = state.lower()
            if state_lower in self.state_map:
                normalized["State"] = self.state_map[state_lower]
            elif len(state) == 2:
                normalized["State"] = state.upper()

        # Normalize phone
        phone = row.get("Phone", "").strip()
        if phone:
            normalized["Phone"] = self._normalize_phone(phone)

        # Normalize website
        website = row.get("Website", "").strip()
        if website:
            normalized["Website"] = self._normalize_url(website)

        # Normalize email
        email = row.get("Email", "").strip()
        if email:
            normalized["Email"] = email.lower()

        # Normalize ZIP code
        zip_code = row.get("ZIP Code", "").strip()
        if zip_code:
            # Extract just the 5-digit ZIP
            match = re.search(r'\d{5}', zip_code)
            if match:
                normalized["ZIP Code"] = match.group()

        # Normalize boolean fields
        telehealth = row.get("Telehealth Available", "").strip().upper()
        normalized["Telehealth Available"] = "TRUE" if telehealth in ["TRUE", "YES", "1", "Y"] else "FALSE"

        # Set default status
        if not row.get("Status", "").strip():
            normalized["Status"] = "Pending Review"

        # Generate slug
        practice_name = row.get("Practice Name", "").strip()
        if practice_name:
            normalized["Slug"] = slugify(practice_name)

        # Normalize specialties (ensure proper delimiter)
        specialties = row.get("Specialties", "").strip()
        if specialties:
            # Handle various delimiters
            specs = re.split(r'[,;|]', specialties)
            specs = [s.strip() for s in specs if s.strip()]
            normalized["Specialties"] = "|".join(specs)

        # Normalize certification bodies
        certs = row.get("Certification Bodies", "").strip()
        if certs:
            certs_list = re.split(r'[,;|]', certs)
            certs_list = [c.strip() for c in certs_list if c.strip()]
            normalized["Certification Bodies"] = "|".join(certs_list)

        # Normalize species
        species = row.get("Species Treated", "").strip()
        if species:
            species_list = re.split(r'[,;|]', species)
            species_list = [s.strip() for s in species_list if s.strip()]
            normalized["Species Treated"] = "|".join(species_list)

        return normalized

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone to (XXX) XXX-XXXX format."""
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        return phone

    def _normalize_url(self, url: str) -> str:
        """Normalize URL to include https://."""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        return url


class AirtableUploader:
    """Uploads CSV data to Airtable."""

    def __init__(self):
        if not AIRTABLE_AVAILABLE:
            raise ImportError("pyairtable is required for Airtable upload")
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
            raise ValueError(
                "AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in .env"
            )

        self.api = Api(AIRTABLE_API_KEY)
        self.base = self.api.base(AIRTABLE_BASE_ID)

    def upload_veterinarians(self, filepath: str, batch_size: int = 10) -> Tuple[int, int]:
        """
        Upload veterinarians CSV to Airtable.

        Args:
            filepath: Path to CSV file
            batch_size: Number of records per batch

        Returns:
            Tuple of (success_count, error_count)
        """
        logger.info(f"Uploading to Airtable: {filepath}")

        table = self.base.table("Veterinarians")

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        success = 0
        errors = 0

        # Process in batches
        for i in tqdm(range(0, len(rows), batch_size), desc="Uploading"):
            batch = rows[i:i + batch_size]
            records = [self._row_to_airtable_record(row) for row in batch]

            try:
                table.batch_create(records)
                success += len(records)
            except Exception as e:
                logger.error(f"Batch upload error: {e}")
                errors += len(records)

        logger.info(f"Upload complete: {success} success, {errors} errors")
        return success, errors

    def _row_to_airtable_record(self, row: Dict[str, str]) -> Dict[str, Any]:
        """Convert CSV row to Airtable record format."""
        record = {}

        # Simple text fields
        text_fields = [
            ("Practice Name", "Practice Name"),
            ("Veterinarian Name(s)", "Veterinarian Name(s)"),
            ("Address", "Address"),
            ("City", "City"),
            ("State", "State"),
            ("ZIP Code", "ZIP Code"),
            ("Phone", "Phone"),
            ("Email", "Email"),
            ("Website", "Website"),
            ("Practice Description", "Practice Description"),
            ("Slug", "Slug"),
        ]

        for csv_field, airtable_field in text_fields:
            value = row.get(csv_field, "").strip()
            if value:
                record[airtable_field] = value

        # Multiple select fields (pipe-delimited)
        multiselect_fields = [
            ("Specialties", "Specialties"),
            ("Certification Bodies", "Certification Bodies"),
            ("Species Treated", "Species Treated"),
        ]

        for csv_field, airtable_field in multiselect_fields:
            value = row.get(csv_field, "").strip()
            if value:
                record[airtable_field] = [v.strip() for v in value.split("|") if v.strip()]

        # Number fields
        year = row.get("Year Established", "").strip()
        if year:
            try:
                record["Year Established"] = int(year)
            except ValueError:
                pass

        lat = row.get("Latitude", "").strip()
        if lat:
            try:
                record["Latitude"] = float(lat)
            except ValueError:
                pass

        lng = row.get("Longitude", "").strip()
        if lng:
            try:
                record["Longitude"] = float(lng)
            except ValueError:
                pass

        # Checkbox field
        telehealth = row.get("Telehealth Available", "").strip().upper()
        record["Telehealth Available"] = telehealth in ["TRUE", "YES", "1", "Y"]

        # Single select field
        status = row.get("Status", "").strip()
        if status in VALID_STATUSES:
            record["Status"] = status
        else:
            record["Status"] = "Pending Review"

        return record

    def upload_specialties(self, filepath: str) -> Tuple[int, int]:
        """Upload specialties CSV to Airtable."""
        logger.info(f"Uploading specialties: {filepath}")

        table = self.base.table("Specialties")

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        success = 0
        errors = 0

        for row in tqdm(rows, desc="Uploading specialties"):
            record = {
                "Specialty Name": row.get("Specialty Name", "").strip(),
                "Description": row.get("Description", "").strip(),
                "Related Conditions": row.get("Related Conditions", "").strip(),
                "Slug": row.get("Slug", "").strip(),
            }

            try:
                table.create(record)
                success += 1
            except Exception as e:
                logger.error(f"Error uploading specialty: {e}")
                errors += 1

        return success, errors

    def upload_states(self, filepath: str) -> Tuple[int, int]:
        """Upload states CSV to Airtable."""
        logger.info(f"Uploading states: {filepath}")

        table = self.base.table("States")

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        success = 0
        errors = 0

        for row in tqdm(rows, desc="Uploading states"):
            featured = row.get("Featured", "").strip().upper()
            record = {
                "State Name": row.get("State Name", "").strip(),
                "State Code": row.get("State Code", "").strip(),
                "Region": row.get("Region", "").strip(),
                "Featured": featured in ["TRUE", "YES", "1", "Y"],
                "Slug": row.get("Slug", "").strip(),
            }

            try:
                table.create(record)
                success += 1
            except Exception as e:
                logger.error(f"Error uploading state: {e}")
                errors += 1

        return success, errors


def print_validation_report(result: ValidationResult):
    """Print a detailed validation report."""
    print("\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)
    print(result.summary())

    if result.errors:
        print("\n--- ERRORS ---")
        for err in result.errors[:20]:  # Limit output
            print(f"  Row {err.row_number}: [{err.field}] {err.message}")
            if err.value:
                print(f"    Value: '{err.value}'")
        if len(result.errors) > 20:
            print(f"  ... and {len(result.errors) - 20} more errors")

    if result.warnings:
        print("\n--- WARNINGS ---")
        for warn in result.warnings[:20]:  # Limit output
            print(f"  Row {warn.row_number}: [{warn.field}] {warn.message}")
            if warn.value:
                print(f"    Value: '{warn.value}'")
        if len(result.warnings) > 20:
            print(f"  ... and {len(result.warnings) - 20} more warnings")

    print("\n" + "=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate, normalize, and upload CSV data to Airtable"
    )
    parser.add_argument(
        "--validate",
        type=str,
        metavar="FILE",
        help="Validate a CSV file"
    )
    parser.add_argument(
        "--normalize",
        type=str,
        metavar="FILE",
        help="Normalize a CSV file"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for normalization (default: input_normalized.csv)"
    )
    parser.add_argument(
        "--upload",
        type=str,
        metavar="FILE",
        help="Upload CSV to Airtable"
    )
    parser.add_argument(
        "--table",
        choices=["Veterinarians", "Specialties", "States"],
        default="Veterinarians",
        help="Airtable table to upload to"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validation mode
    if args.validate:
        if not Path(args.validate).exists():
            print(f"Error: File not found: {args.validate}")
            sys.exit(1)

        validator = CSVValidator()
        result = validator.validate_file(args.validate)
        print_validation_report(result)
        sys.exit(0 if result.is_valid else 1)

    # Normalization mode
    if args.normalize:
        if not Path(args.normalize).exists():
            print(f"Error: File not found: {args.normalize}")
            sys.exit(1)

        output_path = args.output
        if not output_path:
            input_path = Path(args.normalize)
            output_path = str(input_path.with_stem(input_path.stem + "_normalized"))

        normalizer = CSVNormalizer()
        count = normalizer.normalize_file(args.normalize, output_path)
        print(f"\nNormalized {count} rows to: {output_path}")
        return

    # Upload mode
    if args.upload:
        if not Path(args.upload).exists():
            print(f"Error: File not found: {args.upload}")
            sys.exit(1)

        try:
            uploader = AirtableUploader()
        except (ImportError, ValueError) as e:
            print(f"Error: {e}")
            sys.exit(1)

        if args.table == "Veterinarians":
            success, errors = uploader.upload_veterinarians(args.upload)
        elif args.table == "Specialties":
            success, errors = uploader.upload_specialties(args.upload)
        elif args.table == "States":
            success, errors = uploader.upload_states(args.upload)

        print(f"\nUpload complete: {success} success, {errors} errors")
        return

    # No action specified
    parser.print_help()


if __name__ == "__main__":
    main()
