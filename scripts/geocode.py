#!/usr/bin/env python3
"""
Holistic Veterinary Directory - Geocoding Utility

Converts addresses to latitude/longitude coordinates using various geocoding services.
Supports Google Maps API, OpenStreetMap Nominatim, and batch processing.

Usage:
    python scripts/geocode.py --input data/veterinarians.csv --output data/veterinarians_geocoded.csv
    python scripts/geocode.py --input data/collected_vets.csv --provider google
    python scripts/geocode.py --address "123 Main St, San Francisco, CA 94102"
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from dotenv import load_dotenv
from geopy.geocoders import GoogleV3, Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderQuotaExceeded
from ratelimit import limits, sleep_and_retry
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
NOMINATIM_USER_AGENT = "HolisticVetDirectory/1.0"
CACHE_FILE = "data/geocode_cache.json"


@dataclass
class GeocodingResult:
    """Result of a geocoding operation."""
    latitude: float
    longitude: float
    formatted_address: str
    provider: str
    confidence: float = 1.0
    raw_response: Dict[str, Any] = None

    def __post_init__(self):
        if self.raw_response is None:
            self.raw_response = {}


class GeocodingCache:
    """Simple file-based cache for geocoding results."""

    def __init__(self, cache_file: str = CACHE_FILE):
        self.cache_file = Path(cache_file)
        self.cache: Dict[str, Dict] = {}
        self._load_cache()

    def _load_cache(self):
        """Load cache from file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded {len(self.cache)} cached geocoding results")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load cache: {e}")
                self.cache = {}

    def _save_cache(self):
        """Save cache to file."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def get(self, address: str) -> Optional[GeocodingResult]:
        """Get cached result for an address."""
        key = address.lower().strip()
        if key in self.cache:
            data = self.cache[key]
            return GeocodingResult(
                latitude=data['latitude'],
                longitude=data['longitude'],
                formatted_address=data.get('formatted_address', ''),
                provider=data.get('provider', 'cache'),
                confidence=data.get('confidence', 1.0)
            )
        return None

    def set(self, address: str, result: GeocodingResult):
        """Cache a geocoding result."""
        key = address.lower().strip()
        self.cache[key] = {
            'latitude': result.latitude,
            'longitude': result.longitude,
            'formatted_address': result.formatted_address,
            'provider': result.provider,
            'confidence': result.confidence
        }
        self._save_cache()

    def clear(self):
        """Clear the cache."""
        self.cache = {}
        if self.cache_file.exists():
            self.cache_file.unlink()


class Geocoder:
    """Multi-provider geocoder with caching and rate limiting."""

    def __init__(self, provider: str = "nominatim", use_cache: bool = True):
        self.provider = provider.lower()
        self.cache = GeocodingCache() if use_cache else None

        # Initialize the appropriate geocoder
        if self.provider == "google":
            if not GOOGLE_MAPS_API_KEY:
                raise ValueError(
                    "GOOGLE_MAPS_API_KEY environment variable not set. "
                    "Use --provider nominatim for free geocoding."
                )
            self.geocoder = GoogleV3(api_key=GOOGLE_MAPS_API_KEY)
            logger.info("Using Google Maps Geocoding API")
        else:
            self.geocoder = Nominatim(user_agent=NOMINATIM_USER_AGENT)
            logger.info("Using OpenStreetMap Nominatim (free, rate-limited)")

    @sleep_and_retry
    @limits(calls=1, period=1)  # Nominatim: max 1 request per second
    def _geocode_nominatim(self, address: str) -> Optional[GeocodingResult]:
        """Geocode using Nominatim with rate limiting."""
        return self._do_geocode(address)

    @sleep_and_retry
    @limits(calls=50, period=1)  # Google: 50 QPS for standard tier
    def _geocode_google(self, address: str) -> Optional[GeocodingResult]:
        """Geocode using Google with rate limiting."""
        return self._do_geocode(address)

    def _do_geocode(self, address: str) -> Optional[GeocodingResult]:
        """Perform the actual geocoding."""
        try:
            location = self.geocoder.geocode(address, timeout=10)
            if location:
                return GeocodingResult(
                    latitude=location.latitude,
                    longitude=location.longitude,
                    formatted_address=location.address,
                    provider=self.provider,
                    raw_response=location.raw if hasattr(location, 'raw') else {}
                )
            return None
        except GeocoderTimedOut:
            logger.warning(f"Geocoding timed out for: {address}")
            return None
        except GeocoderQuotaExceeded:
            logger.error("Geocoding quota exceeded!")
            raise
        except GeocoderServiceError as e:
            logger.error(f"Geocoding service error: {e}")
            return None

    def geocode(self, address: str, use_cache: bool = True) -> Optional[GeocodingResult]:
        """
        Geocode an address.

        Args:
            address: The address to geocode
            use_cache: Whether to use cached results

        Returns:
            GeocodingResult or None if geocoding failed
        """
        if not address or not address.strip():
            return None

        address = address.strip()

        # Check cache first
        if use_cache and self.cache:
            cached = self.cache.get(address)
            if cached:
                logger.debug(f"Cache hit for: {address}")
                return cached

        # Perform geocoding
        logger.debug(f"Geocoding: {address}")

        if self.provider == "google":
            result = self._geocode_google(address)
        else:
            result = self._geocode_nominatim(address)

        # Cache the result
        if result and self.cache:
            self.cache.set(address, result)

        return result

    def geocode_batch(
        self,
        addresses: List[str],
        progress: bool = True
    ) -> List[Tuple[str, Optional[GeocodingResult]]]:
        """
        Geocode multiple addresses.

        Args:
            addresses: List of addresses to geocode
            progress: Whether to show progress bar

        Returns:
            List of (address, result) tuples
        """
        results = []
        iterator = tqdm(addresses, desc="Geocoding") if progress else addresses

        for address in iterator:
            result = self.geocode(address)
            results.append((address, result))

            # Small delay to be respectful
            if self.provider == "nominatim":
                time.sleep(0.1)

        return results


def build_full_address(
    address: str = "",
    city: str = "",
    state: str = "",
    zip_code: str = ""
) -> str:
    """Build a full address string from components."""
    parts = []
    if address:
        parts.append(address)
    if city:
        parts.append(city)
    if state:
        if zip_code:
            parts.append(f"{state} {zip_code}")
        else:
            parts.append(state)
    elif zip_code:
        parts.append(zip_code)

    return ", ".join(parts)


def process_csv(
    input_file: str,
    output_file: str,
    provider: str = "nominatim",
    skip_existing: bool = True
) -> Dict[str, int]:
    """
    Process a CSV file and add geocoding data.

    Args:
        input_file: Path to input CSV
        output_file: Path to output CSV
        provider: Geocoding provider to use
        skip_existing: Skip rows that already have coordinates

    Returns:
        Statistics dictionary
    """
    geocoder = Geocoder(provider=provider)
    stats = {
        "total": 0,
        "geocoded": 0,
        "skipped": 0,
        "failed": 0
    }

    # Read input file
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    stats["total"] = len(rows)

    # Ensure lat/long columns exist
    if "Latitude" not in fieldnames:
        fieldnames = list(fieldnames) + ["Latitude"]
    if "Longitude" not in fieldnames:
        fieldnames = list(fieldnames) + ["Longitude"]

    # Process each row
    processed_rows = []
    for row in tqdm(rows, desc="Processing"):
        # Check if already geocoded
        existing_lat = row.get("Latitude", "").strip()
        existing_lng = row.get("Longitude", "").strip()

        if skip_existing and existing_lat and existing_lng:
            try:
                float(existing_lat)
                float(existing_lng)
                stats["skipped"] += 1
                processed_rows.append(row)
                continue
            except ValueError:
                pass  # Invalid coordinates, re-geocode

        # Build address
        full_address = build_full_address(
            address=row.get("Address", ""),
            city=row.get("City", ""),
            state=row.get("State", ""),
            zip_code=row.get("ZIP Code", "")
        )

        if not full_address:
            stats["failed"] += 1
            processed_rows.append(row)
            continue

        # Geocode
        result = geocoder.geocode(full_address)

        if result:
            row["Latitude"] = str(result.latitude)
            row["Longitude"] = str(result.longitude)
            stats["geocoded"] += 1
            logger.info(
                f"Geocoded: {row.get('Practice Name', 'Unknown')} -> "
                f"({result.latitude}, {result.longitude})"
            )
        else:
            stats["failed"] += 1
            logger.warning(f"Failed to geocode: {full_address}")

        processed_rows.append(row)

    # Write output file
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed_rows)

    logger.info(f"\nGeocoding complete!")
    logger.info(f"  Total records: {stats['total']}")
    logger.info(f"  Geocoded: {stats['geocoded']}")
    logger.info(f"  Skipped (existing): {stats['skipped']}")
    logger.info(f"  Failed: {stats['failed']}")

    return stats


def geocode_single(address: str, provider: str = "nominatim") -> None:
    """Geocode a single address and print the result."""
    geocoder = Geocoder(provider=provider)
    result = geocoder.geocode(address)

    if result:
        print(f"\nAddress: {address}")
        print(f"Latitude: {result.latitude}")
        print(f"Longitude: {result.longitude}")
        print(f"Formatted: {result.formatted_address}")
        print(f"Provider: {result.provider}")
    else:
        print(f"\nFailed to geocode: {address}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Geocode veterinarian addresses"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Input CSV file to process"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output CSV file (defaults to input with _geocoded suffix)"
    )
    parser.add_argument(
        "--address",
        type=str,
        help="Single address to geocode (for testing)"
    )
    parser.add_argument(
        "--provider",
        choices=["nominatim", "google"],
        default="nominatim",
        help="Geocoding provider (default: nominatim - free, rate-limited)"
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Re-geocode all records, even those with existing coordinates"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the geocoding cache before processing"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Clear cache if requested
    if args.clear_cache:
        cache = GeocodingCache()
        cache.clear()
        print("Geocoding cache cleared.")

    # Single address mode
    if args.address:
        geocode_single(args.address, args.provider)
        return

    # Batch processing mode
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: Input file not found: {args.input}")
            sys.exit(1)

        # Generate output filename if not provided
        if args.output:
            output_path = args.output
        else:
            output_path = str(input_path.with_stem(input_path.stem + "_geocoded"))

        stats = process_csv(
            input_file=args.input,
            output_file=output_path,
            provider=args.provider,
            skip_existing=not args.no_skip
        )

        print(f"\nOutput written to: {output_path}")
        return

    # No input provided
    parser.print_help()


if __name__ == "__main__":
    main()
