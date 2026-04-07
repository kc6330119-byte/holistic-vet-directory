#!/usr/bin/env python3
"""
Holistic Vet Directory - Static Site Generator

Generates a static website from Airtable data or local CSV files.
"""

import os
import sys
import json
import csv
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from collections import defaultdict

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape
from slugify import slugify
import markdown

# Load environment variables
load_dotenv()


@dataclass
class SiteConfig:
    """Site configuration from environment variables."""
    site_name: str = "Holistic Vet Directory"
    site_description: str = "Find holistic and integrative veterinarians near you"
    site_url: str = "https://holisticvetdirectory.com"
    build_env: str = "development"
    enable_adsense: bool = False
    enable_maps: bool = True
    enable_search: bool = True
    listings_per_page: int = 20
    adsense_client_id: str = ""
    adsense_slot_header: str = ""
    adsense_slot_sidebar: str = ""
    adsense_slot_infeed: str = ""
    adsense_slot_footer: str = ""
    
    # Google Analytics
    enable_analytics: bool = False
    analytics_measurement_id: str = ""
    
    google_maps_api_key: str = ""
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.build_env.lower() == 'production'
    
    @classmethod
    def from_env(cls) -> 'SiteConfig':
        return cls(
            site_name=os.getenv('SITE_TITLE', cls.site_name),
            site_description=os.getenv('SITE_DESCRIPTION', cls.site_description),
            site_url=os.getenv('SITE_URL', cls.site_url),
            build_env=os.getenv('BUILD_ENV', cls.build_env),
            enable_adsense=os.getenv('ENABLE_ADSENSE', 'false').lower() == 'true',
            enable_maps=os.getenv('ENABLE_MAPS', 'true').lower() == 'true',
            enable_search=os.getenv('ENABLE_SEARCH', 'true').lower() == 'true',
            listings_per_page=int(os.getenv('LISTINGS_PER_PAGE', '20')),
            adsense_client_id=os.getenv('ADSENSE_CLIENT_ID', ''),
            adsense_slot_header=os.getenv('ADSENSE_SLOT_HEADER', ''),
            adsense_slot_sidebar=os.getenv('ADSENSE_SLOT_SIDEBAR', ''),
            adsense_slot_infeed=os.getenv('ADSENSE_SLOT_INFEED', ''),
            adsense_slot_footer=os.getenv('ADSENSE_SLOT_FOOTER', ''),
            
            enable_analytics=os.getenv('ENABLE_ANALYTICS', 'false').lower() == 'true',
            analytics_measurement_id=os.getenv('GA_MEASUREMENT_ID', ''),
            
            google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY', ''),
        )


@dataclass
class Veterinarian:
    """Veterinarian data model."""
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
    logo_image_url: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    slug: str = ""
    google_rating: Optional[float] = None
    google_reviews: int = 0
    google_place_id: str = ""
    google_maps_url: str = ""
    has_real_description: bool = False

    def __post_init__(self):
        if not self.slug:
            self.slug = slugify(self.practice_name)

        # Ensure list fields are actually lists (handle pipe-delimited strings from Airtable)
        self.specialties = self._ensure_list(self.specialties)
        self.certification_bodies = self._ensure_list(self.certification_bodies)
        self.species_treated = self._ensure_list(self.species_treated)

        # Auto-generate a description only when Airtable has none or a very thin one (<150 chars).
        # Any description 150+ characters is treated as real content and left untouched.
        self.has_real_description = len(self.practice_description.strip()) >= 150
        if not self.has_real_description:
            self.practice_description = self._generate_auto_description()
    
    @staticmethod
    def _ensure_list(value) -> List[str]:
        """Convert a value to a list if it's a pipe-delimited string."""
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value:
            return [item.strip() for item in value.split('|') if item.strip()]
        return []

    def _generate_auto_description(self) -> str:
        """Build a varied, detailed description from available fields."""
        # Use slug hash to deterministically select template variations
        # so the same vet always gets the same description across rebuilds.
        h = int(hashlib.md5(self.slug.encode()).hexdigest(), 16)

        parts = []
        city = self.city
        state = self.state
        name = self.practice_name
        specs = self.specialties
        species = [s.lower() for s in self.species_treated]
        certs = self.certification_bodies
        current_year = datetime.now().year
        years_open = (current_year - self.year_established) if self.year_established else 0

        # ── Specialty descriptions for richer content ──────────────────────
        SPECIALTY_INFO = {
            "Acupuncture": (
                "acupuncture, a time-tested technique that uses fine needles at specific "
                "points on the body to relieve pain, reduce inflammation, and promote "
                "natural healing"
            ),
            "Chiropractic": (
                "chiropractic care, which focuses on the alignment of the spine and "
                "joints to improve mobility, nerve function, and overall structural health"
            ),
            "Herbal Medicine": (
                "herbal medicine, drawing on plant-based formulas to address conditions "
                "ranging from digestive disorders to skin problems and immune support"
            ),
            "Homeopathy": (
                "homeopathy, a gentle system of medicine that uses highly diluted "
                "remedies to stimulate the body's own healing response"
            ),
            "Nutritional Therapy": (
                "nutritional therapy, crafting individualized diet plans and targeted "
                "supplements to support each patient's specific health needs"
            ),
            "Physical Therapy/Rehabilitation": (
                "physical rehabilitation, including therapeutic exercises and manual "
                "therapies to help animals recover from surgery, injury, or chronic "
                "mobility issues"
            ),
            "Traditional Chinese Veterinary Medicine (TCVM)": (
                "Traditional Chinese Veterinary Medicine, a comprehensive system that "
                "integrates acupuncture, herbal formulas, food therapy, and Tui-na "
                "massage to restore balance and wellness"
            ),
            "Laser Therapy": (
                "laser therapy, a non-invasive treatment that uses focused light energy "
                "to reduce pain, decrease inflammation, and accelerate tissue repair"
            ),
            "Massage Therapy": (
                "therapeutic massage, which helps relieve muscle tension, improve "
                "circulation, and reduce stress and anxiety in animals"
            ),
            "Aromatherapy": (
                "aromatherapy, using carefully selected essential oils to support "
                "emotional well-being, respiratory health, and natural healing"
            ),
            "Energy Medicine (Reiki, etc.)": (
                "energy medicine including Reiki, a gentle hands-on practice that "
                "promotes relaxation, stress relief, and energetic balance"
            ),
            "Ozone Therapy": (
                "ozone therapy, an advanced treatment that uses medical-grade ozone "
                "to support immune function, fight infection, and enhance oxygen delivery"
            ),
            "Prolotherapy": (
                "prolotherapy, a regenerative injection technique that stimulates the "
                "body's natural repair process to strengthen weakened joints and connective tissue"
            ),
            "Naturopathy": (
                "naturopathic veterinary care, an approach that emphasizes the body's "
                "inherent ability to heal using natural therapies and minimal intervention"
            ),
        }

        # ── Opening sentence (6 variations) ────────────────────────────────
        variant = h % 6

        if specs and city and state:
            top_spec = specs[0]
            if variant == 0:
                parts.append(
                    f"Located in {city}, {state}, {name} takes an integrative approach "
                    f"to veterinary medicine, combining conventional care with natural "
                    f"healing modalities."
                )
            elif variant == 1:
                parts.append(
                    f"{name} brings holistic and integrative veterinary care to the "
                    f"{city}, {state} community, offering treatments that address "
                    f"the whole animal rather than just individual symptoms."
                )
            elif variant == 2:
                parts.append(
                    f"Pet owners in {city}, {state} looking for a veterinarian who "
                    f"goes beyond conventional medicine will find a comprehensive "
                    f"integrative practice at {name}."
                )
            elif variant == 3:
                parts.append(
                    f"At {name} in {city}, {state}, the focus is on treating the whole "
                    f"patient. The practice blends modern veterinary science with "
                    f"natural therapies to support long-term health and well-being."
                )
            elif variant == 4:
                parts.append(
                    f"{name} is an integrative veterinary practice in {city}, {state}, "
                    f"where conventional diagnostics and treatments work alongside "
                    f"holistic modalities to give patients the best of both worlds."
                )
            else:
                parts.append(
                    f"For pet owners in the {city}, {state} area seeking alternatives "
                    f"to a purely conventional approach, {name} offers holistic "
                    f"veterinary care rooted in both science and natural medicine."
                )
        elif city and state:
            parts.append(
                f"{name} provides holistic veterinary care to the {city}, {state} "
                f"community, focusing on natural approaches that support the whole animal."
            )
        else:
            parts.append(
                f"{name} is a holistic veterinary practice dedicated to integrative "
                f"care that treats the whole animal, not just symptoms."
            )

        # ── Specialty details (up to 3, with rich descriptions) ────────────
        if specs:
            described = []
            for spec in specs[:3]:
                info = SPECIALTY_INFO.get(spec)
                if info:
                    described.append(info)

            if described:
                transition_variant = (h >> 4) % 4
                if transition_variant == 0:
                    intro = "The practice offers "
                elif transition_variant == 1:
                    intro = "Services include "
                elif transition_variant == 2:
                    intro = "Among the treatments available, the practice provides "
                else:
                    intro = "Patients can benefit from "

                if len(described) == 1:
                    parts.append(f"{intro}{described[0]}.")
                elif len(described) == 2:
                    parts.append(f"{intro}{described[0]}. The team also provides {described[1]}.")
                else:
                    parts.append(
                        f"{intro}{described[0]}. Additionally, the practice offers "
                        f"{described[1]}, as well as {described[2]}."
                    )

            # Mention remaining specialties not described in detail
            remaining = [s for s in specs[3:] if s not in [sp for sp in specs[:3]]]
            if remaining:
                if len(remaining) == 1:
                    parts.append(f"The practice also offers {remaining[0].lower()}.")
                else:
                    rem_str = ", ".join(s.lower() for s in remaining[:-1])
                    parts.append(
                        f"Additional services include {rem_str} and "
                        f"{remaining[-1].lower()}."
                    )

        # ── Species treated (varied phrasing) ──────────────────────────────
        if species:
            species_variant = (h >> 8) % 5
            if len(species) == 1:
                sp = species[0]
                if species_variant % 2 == 0:
                    parts.append(f"The practice focuses on holistic care for {sp}.")
                else:
                    parts.append(
                        f"The veterinary team specializes in providing integrative "
                        f"treatment for {sp}."
                    )
            else:
                if len(species) > 2:
                    sp_str = ", ".join(species[:-1]) + f", and {species[-1]}"
                else:
                    sp_str = f"{species[0]} and {species[1]}"

                if species_variant == 0:
                    parts.append(
                        f"The practice welcomes {sp_str}, providing each patient with "
                        f"an individualized care plan tailored to their species and needs."
                    )
                elif species_variant == 1:
                    parts.append(
                        f"Integrative care is available for {sp_str}, with treatment "
                        f"plans designed around the unique physiology and health needs "
                        f"of each animal."
                    )
                elif species_variant == 2:
                    parts.append(
                        f"The team treats {sp_str}, taking a whole-patient approach "
                        f"that considers diet, environment, and lifestyle alongside "
                        f"clinical symptoms."
                    )
                elif species_variant == 3:
                    parts.append(
                        f"Patients include {sp_str}. Each animal receives a "
                        f"comprehensive evaluation to determine the most effective "
                        f"combination of conventional and holistic therapies."
                    )
                else:
                    parts.append(
                        f"Whether your companion is a {species[0]} or a {species[-1]}, "
                        f"the practice offers integrative care tailored to their "
                        f"individual health profile."
                    )

        # ── Certifications (woven into context) ───────────────────────────
        if certs:
            cert_variant = (h >> 12) % 3
            cert_list = certs[:3]
            cert_str = ", ".join(cert_list)

            if cert_variant == 0:
                parts.append(
                    f"The veterinary team holds certifications from {cert_str}, "
                    f"reflecting advanced training in holistic and integrative modalities."
                )
            elif cert_variant == 1:
                parts.append(
                    f"Professional credentials include certification through {cert_str}, "
                    f"demonstrating a commitment to evidence-based integrative practice."
                )
            else:
                parts.append(
                    f"With credentials from {cert_str}, the practitioners bring "
                    f"specialized training that goes beyond what is covered in "
                    f"conventional veterinary programs."
                )

        # ── Google rating ──────────────────────────────────────────────────
        if self.google_rating and self.google_reviews:
            rating_variant = (h >> 16) % 3
            if rating_variant == 0:
                parts.append(
                    f"The practice has earned a {self.google_rating}-star rating on "
                    f"Google from {self.google_reviews} reviews, reflecting the trust "
                    f"and satisfaction of the pet owners they serve."
                )
            elif rating_variant == 1:
                parts.append(
                    f"Pet owners have rated {name} {self.google_rating} out of 5 stars "
                    f"on Google across {self.google_reviews} reviews."
                )
            else:
                parts.append(
                    f"With a {self.google_rating}-star Google rating based on "
                    f"{self.google_reviews} reviews, {name} is well regarded by "
                    f"the local pet-owner community."
                )

        # ── Telehealth ─────────────────────────────────────────────────────
        if self.telehealth_available:
            tele_variant = (h >> 20) % 3
            if tele_variant == 0:
                parts.append(
                    "For pet owners who cannot visit in person, the practice also "
                    "offers telehealth consultations, making it easier to access "
                    "holistic guidance from home."
                )
            elif tele_variant == 1:
                parts.append(
                    "Remote consultations are available through telehealth, allowing "
                    "the veterinary team to provide initial assessments, follow-up "
                    "care, and nutritional guidance virtually."
                )
            else:
                parts.append(
                    "Telehealth appointments are available for clients who prefer "
                    "the convenience of virtual consultations or live outside the "
                    "immediate area."
                )

        # ── Years in practice ──────────────────────────────────────────────
        if years_open > 0:
            year_variant = (h >> 24) % 3
            if year_variant == 0:
                parts.append(
                    f"Established in {self.year_established}, the practice has spent "
                    f"{years_open} years building a reputation for compassionate, "
                    f"integrative animal care."
                )
            elif year_variant == 1:
                parts.append(
                    f"The practice has been serving the community since "
                    f"{self.year_established}, bringing {years_open} years of "
                    f"experience in holistic veterinary medicine."
                )
            else:
                parts.append(
                    f"With {years_open} years in practice since {self.year_established}, "
                    f"the team brings deep experience in blending conventional and "
                    f"natural approaches to animal health."
                )

        # ── Closing sentence (4 variations) ────────────────────────────────
        close_variant = (h >> 28) % 4
        if close_variant == 0 and city:
            parts.append(
                f"Pet owners in the {city} area are encouraged to call or visit "
                f"the website to learn more about the integrative services available."
            )
        elif close_variant == 1:
            parts.append(
                "Whether dealing with a chronic condition, recovering from surgery, "
                "or simply looking for a more natural approach to wellness, this "
                "practice offers options worth exploring."
            )
        elif close_variant == 2:
            parts.append(
                "A consultation is a good first step for pet owners interested "
                "in learning how holistic care might benefit their animal companion."
            )
        else:
            parts.append(
                "The practice welcomes new clients and is happy to discuss how an "
                "integrative approach can support your pet's health and quality of life."
            )

        return " ".join(parts)
    
    @property
    def full_address(self) -> str:
        parts = [self.address, self.city]
        if self.state:
            parts.append(self.state)
        if self.zip_code:
            parts.append(str(self.zip_code))
        return ", ".join(filter(None, parts))
    
    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def quality_score(self) -> int:
        """Score 0-10 indicating listing completeness for index-worthiness.

        Used to decide whether a vet detail page should be noindexed.
        Higher score = more complete, more valuable to searchers.
        """
        score = 0
        if self.has_real_description:
            score += 3          # Real human-written description is the strongest signal
        if self.phone:
            score += 1
        if self.website:
            score += 1
        if self.google_rating and self.google_rating > 0:
            score += 2          # Google rating adds significant trust
        if self.has_coordinates:
            score += 1
        if self.certification_bodies:
            score += 1
        if self.email:
            score += 1
        return score

    @property
    def maps_url(self) -> str:
        if self.has_coordinates:
            return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
        return f"https://www.google.com/maps/search/{self.full_address.replace(' ', '+')}"
    
    @classmethod
    def from_csv_row(cls, row: Dict[str, str]) -> 'Veterinarian':
        def parse_list(value: str) -> List[str]:
            if not value:
                return []
            return [item.strip() for item in value.split('|') if item.strip()]
        
        def parse_bool(value: str) -> bool:
            return value.lower() in ('true', 'yes', '1', 'x')
        
        def parse_int(value: str) -> Optional[int]:
            try:
                return int(value) if value else None
            except ValueError:
                return None
        
        def parse_float(value: str) -> Optional[float]:
            try:
                return float(value) if value else None
            except ValueError:
                return None
        
        return cls(
            practice_name=row.get('Practice Name', ''),
            veterinarian_names=row.get('Veterinarian Name(s)', ''),
            specialties=parse_list(row.get('Specialties', '')),
            address=row.get('Address', ''),
            city=row.get('City', ''),
            state=row.get('State', ''),
            zip_code=row.get('ZIP Code', ''),
            phone=row.get('Phone', ''),
            email=row.get('Email', ''),
            website=row.get('Website', ''),
            certification_bodies=parse_list(row.get('Certification Bodies', '')),
            species_treated=parse_list(row.get('Species Treated', '')),
            practice_description=row.get('Practice Description', ''),
            year_established=parse_int(row.get('Year Established', '')),
            telehealth_available=parse_bool(row.get('Telehealth Available', '')),
            featured_listing=parse_bool(row.get('Featured Listing', '')),
            latitude=parse_float(row.get('Latitude', '')),
            longitude=parse_float(row.get('Longitude', '')),
            slug=row.get('Slug', ''),
            google_rating=parse_float(row.get('Google Rating', '')),
            google_reviews=parse_int(row.get('Google Reviews', '')) or 0,
            google_place_id=row.get('Google Place ID', ''),
            google_maps_url=row.get('Google Maps URL', ''),
        )


@dataclass
class Specialty:
    """Specialty/modality data model."""
    name: str
    description: str = ""
    related_conditions: str = ""
    slug: str = ""
    species: str = ""
    vet_count: int = 0

    def __post_init__(self):
        if not self.slug:
            self.slug = slugify(self.name)

    @classmethod
    def from_csv_row(cls, row: Dict[str, str]) -> 'Specialty':
        return cls(
            name=row.get('Specialty Name', ''),
            description=row.get('Description', ''),
            related_conditions=row.get('Related Conditions', ''),
            slug=row.get('Slug', ''),
            species=row.get('Species', ''),
        )


@dataclass
class State:
    """US State data model."""
    name: str
    code: str
    region: str = ""
    featured: bool = False
    slug: str = ""
    vet_count: int = 0
    
    def __post_init__(self):
        if not self.slug:
            self.slug = slugify(self.name)
    
    @classmethod
    def from_csv_row(cls, row: Dict[str, str]) -> 'State':
        return cls(
            name=row.get('State Name', ''),
            code=row.get('State Code', ''),
            region=row.get('Region', ''),
            featured=row.get('Featured', '').lower() in ('true', 'yes', '1'),
            slug=row.get('Slug', ''),
        )


class DataLoader:
    """Loads data from CSV files or Airtable."""
    
    def __init__(self, data_dir: Path, use_airtable: bool = False):
        self.data_dir = data_dir
        self.use_airtable = use_airtable
        self._airtable_loader = None
        
        if use_airtable:
            self._init_airtable()
    
    def _init_airtable(self):
        """Initialize Airtable connection."""
        try:
            from scripts.airtable_loader import AirtableDataLoader
            self._airtable_loader = AirtableDataLoader()
            print("  Connected to Airtable")
        except ImportError as e:
            print(f"Warning: Could not import Airtable loader: {e}")
            print("  Falling back to CSV data")
            self.use_airtable = False
        except ValueError as e:
            print(f"Warning: Airtable configuration error: {e}")
            print("  Falling back to CSV data")
            self.use_airtable = False
        except Exception as e:
            print(f"Warning: Airtable connection failed: {e}")
            print("  Falling back to CSV data")
            self.use_airtable = False
    
    def load_veterinarians(self) -> List[Veterinarian]:
        if self.use_airtable and self._airtable_loader:
            return self._load_vets_from_airtable()
        return self._load_vets_from_csv()
    
    def _load_vets_from_airtable(self) -> List[Veterinarian]:
        """Load veterinarians from Airtable."""
        airtable_vets = self._airtable_loader.load_veterinarians()
        vets = []
        for av in airtable_vets:
            vet = Veterinarian(
                practice_name=av.practice_name,
                veterinarian_names=av.veterinarian_names,
                specialties=av.specialties,
                address=av.address,
                city=av.city,
                state=av.state,
                zip_code=av.zip_code,
                phone=av.phone,
                email=av.email,
                website=av.website,
                certification_bodies=av.certification_bodies,
                species_treated=av.species_treated,
                practice_description=av.practice_description,
                year_established=av.year_established,
                telehealth_available=av.telehealth_available,
                featured_listing=av.featured_listing,
                image_url=av.image_url,
                logo_image_url=av.logo_image_url,
                latitude=av.latitude,
                longitude=av.longitude,
                slug=av.slug,
                google_rating=av.google_rating,
                google_reviews=av.google_reviews,
                google_place_id=av.google_place_id,
                google_maps_url=av.google_maps_url,
            )
            vets.append(vet)
        return vets
    
    def _load_vets_from_csv(self) -> List[Veterinarian]:
        """Load veterinarians from CSV file."""
        csv_path = self.data_dir / 'veterinarians.csv'
        if not csv_path.exists():
            print(f"Warning: {csv_path} not found")
            return []
        
        vets = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Practice Name'):
                    vets.append(Veterinarian.from_csv_row(row))
        
        return vets
    
    def load_specialties(self) -> List[Specialty]:
        # Always load from CSV — it is the authoritative source for specialty metadata
        # (conditions, species, descriptions). Airtable does not have these fields populated.
        return self._load_specialties_from_csv()
    
    def _load_specialties_from_csv(self) -> List[Specialty]:
        """Load specialties from CSV file."""
        csv_path = self.data_dir / 'specialties.csv'
        if not csv_path.exists():
            print(f"Warning: {csv_path} not found")
            return []
        
        specialties = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Specialty Name'):
                    specialties.append(Specialty.from_csv_row(row))
        
        return specialties
    
    def load_states(self) -> List[State]:
        if self.use_airtable and self._airtable_loader:
            return self._load_states_from_airtable()
        return self._load_states_from_csv()
    
    def _load_states_from_airtable(self) -> List[State]:
        """Load states from Airtable."""
        airtable_states = self._airtable_loader.load_states()
        states = []
        for ast in airtable_states:
            state = State(
                name=ast.name,
                code=ast.code,
                region=ast.region,
                featured=ast.featured,
                slug=ast.slug,
            )
            states.append(state)
        return states
    
    def _load_states_from_csv(self) -> List[State]:
        """Load states from CSV file."""
        csv_path = self.data_dir / 'states.csv'
        if not csv_path.exists():
            print(f"Warning: {csv_path} not found")
            return []
        
        states = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('State Name'):
                    states.append(State.from_csv_row(row))
        
        return states

    def load_blog_posts(self) -> List['BlogPost']:
        """Load blog posts from Airtable or CSV."""
        if self.use_airtable and self._airtable_loader:
            return self._load_blog_posts_from_airtable()
        return self._load_blog_posts_from_csv()
    
    def _load_blog_posts_from_airtable(self) -> List['BlogPost']:
        """Load blog posts from Airtable."""
        try:
            from scripts.airtable_loader import BlogPostData
            airtable_posts = self._airtable_loader.load_blog_posts()
            posts = []
            for ap in airtable_posts:
                post = BlogPost(
                    title=ap.title,
                    content=ap.content,
                    excerpt=ap.excerpt,
                    author=ap.author,
                    published_date=ap.published_date,
                    featured_image=ap.featured_image,
                    meta_description=ap.meta_description,
                    status=ap.status,
                    slug=ap.slug,
                    featured=ap.featured,
                )
                posts.append(post)
            return posts
        except Exception as e:
            print(f"  Warning: Could not load blog posts: {e}")
            return []
    
    def _load_blog_posts_from_csv(self) -> List['BlogPost']:
        """Load blog posts from CSV file."""
        csv_path = self.data_dir / 'blog_posts.csv'
        if not csv_path.exists():
            return []  # Blog is optional
        
        posts = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Title') and row.get('Status', '').lower() == 'published':
                    post = BlogPost(
                        title=row.get('Title', ''),
                        content=row.get('Content', ''),
                        excerpt=row.get('Excerpt', ''),
                        author=row.get('Author', ''),
                        published_date=row.get('Published Date', ''),
                        featured_image=row.get('Featured Image', ''),
                        meta_description=row.get('Meta Description', ''),
                        status=row.get('Status', 'Draft'),
                        slug=row.get('Slug', ''),
                    )
                    posts.append(post)
        
        return posts


@dataclass
class BlogPost:
    """Blog post data model."""
    title: str
    content: str = ""
    content_html: str = ""
    excerpt: str = ""
    author: str = ""
    published_date: str = ""
    featured_image: str = ""
    meta_description: str = ""
    status: str = "Draft"
    slug: str = ""
    featured: bool = False
    
    def __post_init__(self):
        if not self.slug:
            self.slug = slugify(self.title)
        # Convert markdown content to HTML
        if self.content and not self.content_html:
            self.content_html = markdown.markdown(
                self.content,
                extensions=['extra', 'codehilite', 'toc']
            )
        # Auto-generate excerpt if not provided
        if not self.excerpt and self.content:
            plain_text = self.content.replace('#', '').replace('*', '').replace('_', '').replace('\n', ' ')
            self.excerpt = plain_text[:150].strip() + '...' if len(plain_text) > 150 else plain_text
        # Format published date for display
        if self.published_date and len(self.published_date) >= 10:
            try:
                from datetime import datetime
                dt = datetime.strptime(self.published_date[:10], '%Y-%m-%d')
                self.published_date_formatted = dt.strftime('%B %d, %Y')
            except:
                self.published_date_formatted = self.published_date
        else:
            self.published_date_formatted = self.published_date


class DataProcessor:
    """Processes and organizes data for site generation."""
    
    def __init__(self, vets: List[Veterinarian], specialties: List[Specialty], states: List[State], blog_posts: List[BlogPost] = None):
        self.vets = vets
        self.specialties = specialties
        self.states = states
        self.blog_posts = blog_posts or []
        self._process()
    
    def _process(self):
        # Create lookup dictionaries
        self.state_by_code = {s.code: s for s in self.states}
        self.state_by_slug = {s.slug: s for s in self.states}
        self.specialty_by_slug = {s.slug: s for s in self.specialties}
        
        # Count vets per state
        state_counts = defaultdict(int)
        for vet in self.vets:
            if vet.state:
                state_counts[vet.state] += 1
        
        for state in self.states:
            state.vet_count = state_counts.get(state.code, 0)
        
        # Count vets per specialty
        specialty_counts = defaultdict(int)
        for vet in self.vets:
            for spec in vet.specialties:
                spec_slug = slugify(spec)
                specialty_counts[spec_slug] += 1
        
        for specialty in self.specialties:
            specialty.vet_count = specialty_counts.get(specialty.slug, 0)
        
        # Group vets by state
        self.vets_by_state = defaultdict(list)
        for vet in self.vets:
            if vet.state:
                self.vets_by_state[vet.state].append(vet)
        
        # Group vets by city within state
        self.vets_by_city = defaultdict(lambda: defaultdict(list))
        for vet in self.vets:
            if vet.state and vet.city:
                city_slug = slugify(vet.city)
                self.vets_by_city[vet.state][city_slug].append(vet)
        
        # Group vets by specialty
        self.vets_by_specialty = defaultdict(list)
        for vet in self.vets:
            for spec in vet.specialties:
                spec_slug = slugify(spec)
                self.vets_by_specialty[spec_slug].append(vet)
        
        # Get unique cities per state
        self.cities_by_state = {}
        for state_code, city_dict in self.vets_by_city.items():
            cities = []
            for city_slug, city_vets in city_dict.items():
                if city_vets:
                    cities.append({
                        'name': city_vets[0].city,
                        'slug': city_slug,
                        'vet_count': len(city_vets)
                    })
            cities.sort(key=lambda x: x['name'])
            self.cities_by_state[state_code] = cities
    
    def get_featured_states(self, limit: int = 8) -> List[State]:
        featured = [s for s in self.states if s.featured and s.vet_count > 0]
        if len(featured) < limit:
            non_featured = sorted(
                [s for s in self.states if not s.featured and s.vet_count > 0],
                key=lambda s: s.vet_count,
                reverse=True
            )
            featured.extend(non_featured[:limit - len(featured)])
        return featured[:limit]
    
    def get_featured_vets(self, limit: int = 6) -> List[Veterinarian]:
        """Get featured veterinarians for homepage."""
        featured = [v for v in self.vets if v.featured_listing]
        # Sort by practice name for consistency
        featured = sorted(featured, key=lambda v: v.practice_name)
        return featured[:limit]
    
    def get_featured_specialties(self, limit: int = 8) -> List[Specialty]:
        return sorted(
            [s for s in self.specialties if s.vet_count > 0],
            key=lambda s: s.vet_count,
            reverse=True
        )[:limit]
    
    def get_nearby_vets(self, vet: Veterinarian, limit: int = 5) -> List[Veterinarian]:
        if not vet.has_coordinates:
            # Fallback: return vets in same state
            same_state = [v for v in self.vets if v.state == vet.state and v.slug != vet.slug]
            return same_state[:limit]
        
        # Calculate distances
        def haversine(lat1, lon1, lat2, lon2):
            from math import radians, cos, sin, sqrt, atan2
            R = 3959  # Earth's radius in miles
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            return R * c
        
        nearby = []
        for other in self.vets:
            if other.slug != vet.slug and other.has_coordinates:
                dist = haversine(vet.latitude, vet.longitude, other.latitude, other.longitude)
                if dist <= 100:  # Within 100 miles
                    nearby.append((dist, other))
        
        nearby.sort(key=lambda x: x[0])
        return [v for _, v in nearby[:limit]]
    
    def get_search_index(self) -> List[Dict[str, Any]]:
        index = []
        for vet in self.vets:
            index.append({
                'name': vet.practice_name,
                'vets': vet.veterinarian_names,
                'city': vet.city,
                'state': vet.state,
                'zip': vet.zip_code,
                'specialties': vet.specialties,
                'species': vet.species_treated,
                'telehealth': vet.telehealth_available,
                'slug': vet.slug,
                'url': f'/vet/{vet.slug}/',
            })
        return index


class SiteGenerator:
    """Generates the static site."""
    
    def __init__(self, config: SiteConfig, processor: DataProcessor, output_dir: Path):
        self.config = config
        self.processor = processor
        self.output_dir = output_dir
        self.template_dir = Path(__file__).parent / 'templates'
        
        # Set up Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html', 'xml']),
        )
        
        # Add custom filters
        self.env.filters['slugify'] = slugify
        self.env.filters['truncate_words'] = self._truncate_words
        self.env.filters['format_phone'] = self._format_phone
        self.env.filters['pluralize'] = self._pluralize
        
        # Common context
        self.common_context = {
            'config': config,
            'now': datetime.now(),
            'states': sorted([s for s in processor.states if s.vet_count > 0], key=lambda s: s.name),
            'specialties': sorted([s for s in processor.specialties if s.vet_count > 0], key=lambda s: s.name),
            'blog_posts': processor.blog_posts[:3],  # Recent posts for sidebar/footer
            'has_blog': len(processor.blog_posts) > 0,
        }
    
    @staticmethod
    def _truncate_words(text: str, num_words: int = 30) -> str:
        words = text.split()
        if len(words) <= num_words:
            return text
        return ' '.join(words[:num_words]) + '...'
    
    @staticmethod
    def _format_phone(phone: str) -> str:
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        return phone

    @staticmethod
    def _pluralize(value: int, singular: str, plural: str) -> str:
        return singular if value == 1 else plural

    @staticmethod
    def _truncate_meta(text: str, max_length: int = 155) -> str:
        """Truncate text for meta descriptions at a sentence boundary."""
        if not text or len(text) <= max_length:
            return text or ''
        # Try to find a sentence boundary within the limit
        for end in range(min(max_length, len(text)), 80, -1):
            if text[end - 1] in '.!':
                return text[:end]
        # No sentence boundary; truncate at word boundary
        return text[:max_length].rsplit(' ', 1)[0].rstrip('.,') + '.'

    def generate(self):
        """Generate the entire site."""
        print("Starting site generation...")
        
        # Clean and create output directory
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True)
        
        # Generate pages
        self._generate_homepage()
        self._generate_vets_list()
        self._generate_state_pages()
        self._generate_city_pages()
        self._generate_vet_detail_pages()
        self._generate_specialties_list()
        self._generate_specialty_pages()
        self._generate_search_page()
        self._generate_blog_list()
        self._generate_blog_detail_pages()
        self._generate_holistic_care_guide()
        self._generate_static_pages()
        self._generate_search_index()
        self._generate_sitemap()
        self._generate_robots_txt()
        self._copy_static_assets()
        
        print(f"Site generation complete! Output: {self.output_dir}")
    
    def _render_and_write(self, template_name: str, output_path: str, context: Dict[str, Any]):
        template = self.env.get_template(template_name)
        
        # Auto-generate request_path for canonical URLs if not provided
        if 'request_path' not in context:
            # Convert output_path to URL path (e.g., "vets/index.html" -> "/vets/")
            if output_path == 'index.html':
                context['request_path'] = '/'
            elif output_path == '404.html':
                context['request_path'] = '/404.html'
            elif output_path.endswith('/index.html'):
                context['request_path'] = '/' + output_path.replace('/index.html', '/').replace('index.html', '')
            else:
                context['request_path'] = '/' + output_path
        
        full_context = {**self.common_context, **context}
        html = template.render(**full_context)
        
        output_file = self.output_dir / output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html, encoding='utf-8')
        print(f"  Generated: {output_path}")
    
    def _generate_homepage(self):
        print("Generating homepage...")
        published_posts = [p for p in self.processor.blog_posts if p.status == 'Published']
        featured_post = next((p for p in published_posts if p.featured), None)
        if not featured_post and published_posts:
            featured_post = published_posts[0]
        self._render_and_write('index.html', 'index.html', {
            'page_title': 'Find a Holistic Veterinarian Near You',
            'page_description': 'The largest directory of holistic and integrative veterinarians in the U.S. Search 3,200+ practitioners offering acupuncture, herbal medicine, chiropractic, TCVM, and natural pet care — with Google ratings and reviews.',
            'featured_states': self.processor.get_featured_states(8),
            'featured_specialties': self.processor.get_featured_specialties(8),
            'featured_vets': self.processor.get_featured_vets(6),
            'recent_vets': sorted(self.processor.vets, key=lambda v: v.practice_name)[:6],
            'total_vets': len(self.processor.vets),
            'total_states': len([s for s in self.processor.states if s.vet_count > 0]),
            'total_posts': len(published_posts),
            'featured_post': featured_post,
        })
    
    def _generate_vets_list(self):
        print("Generating vets listing...")
        vets = sorted(self.processor.vets, key=lambda v: (v.state, v.city, v.practice_name))
        self._render_and_write('vets_list.html', 'vets/index.html', {
            'page_title': 'Find Holistic Veterinarians Near You',
            'page_description': 'Search 3,200+ holistic vets by state, city, or specialty. Find acupuncture, chiropractic & herbal medicine near you. Start your search today.',
            'vets': vets,
            'total_count': len(vets),
            'current_page': 1,
            'total_pages': 1,
            'has_prev': False,
            'has_next': False,
        })
    
    # Unique editorial paragraphs for each state page
    STATE_EDITORIAL = {
        "AL": (
            "Alabama's warm, humid climate creates year-round challenges for pets, "
            "including persistent flea and tick pressure, skin allergies triggered by "
            "mold and pollen, and heat-related joint inflammation in older dogs. "
            "Holistic veterinarians in Alabama frequently combine acupuncture and "
            "herbal medicine to manage these chronic conditions with fewer "
            "pharmaceutical side effects. The state's growing equine community in "
            "the northern hill country has also driven demand for integrative horse "
            "care, particularly chiropractic and Traditional Chinese Veterinary Medicine."
        ),
        "AK": (
            "Alaska presents unique challenges for pet health care. The extreme cold "
            "and long winters take a toll on joints, making arthritis management a "
            "top concern for working sled dogs, hunting companions, and aging pets "
            "alike. Holistic veterinarians in Alaska often specialize in acupuncture "
            "and chiropractic care for musculoskeletal conditions exacerbated by the "
            "climate. The state's vast geography also means many pet owners rely on "
            "telehealth consultations with integrative practitioners, particularly "
            "in rural areas where the nearest holistic vet may be hundreds of miles away."
        ),
        "AZ": (
            "Arizona's desert climate brings its own set of health challenges for "
            "pets, from Valley Fever — a fungal infection endemic to the Sonoran "
            "Desert — to heat stress and chronic dehydration. Holistic veterinarians "
            "in Arizona are often experienced in managing Valley Fever with integrative "
            "protocols that combine conventional antifungals with immune-supporting "
            "herbs and nutritional therapy. The state's large population of active "
            "outdoor dogs also drives demand for chiropractic care and rehabilitation "
            "for injuries sustained on desert trails and rocky terrain."
        ),
        "AR": (
            "Arkansas pet owners benefit from a growing holistic veterinary community "
            "that serves both companion animals and the state's significant livestock "
            "and equine populations. The humid subtropical climate contributes to "
            "chronic skin conditions, ear infections, and environmental allergies in "
            "dogs, making herbal medicine and nutritional therapy popular integrative "
            "approaches. Many Arkansas holistic vets have training in Traditional "
            "Chinese Veterinary Medicine, reflecting a broader trend toward whole-body "
            "approaches to animal health care across the rural South."
        ),
        "CA": (
            "California is home to one of the largest and most established holistic "
            "veterinary communities in the country. From San Diego to the Bay Area, "
            "pet owners have access to practitioners offering everything from "
            "acupuncture and TCVM to raw diet consultations and veterinary "
            "homeopathy. The state's year-round outdoor lifestyle means active dogs "
            "frequently need integrative support for sports injuries, joint health, "
            "and environmental allergies triggered by the diverse plant life. "
            "California also leads in equine integrative medicine, with many "
            "practitioners serving the state's large horse community."
        ),
        "CO": (
            "Colorado's active, outdoor-oriented culture extends to its pets — and "
            "finding the right holistic veterinarian in Colorado has never been more "
            "important. Dogs here hike fourteeners, run trails at altitude, and play "
            "hard in every season, and their bodies show it. Whether you're searching "
            "for a holistic vet near me in Colorado or looking for a specialist in "
            "acupuncture, chiropractic, or physical rehabilitation, the state's "
            "integrative vet community is well-equipped to help. Colorado's dry "
            "climate and high altitude create unique health considerations including "
            "increased UV exposure, joint stress from rocky terrain, and respiratory "
            "adjustments for pets relocating from lower elevations. From Denver to "
            "Colorado Springs to the mountain communities, holistic veterinarians "
            "in Colorado offer a full range of integrative care modalities for dogs, "
            "cats, horses, and more."
        ),
        "CT": (
            "Connecticut's holistic veterinary community serves a pet-owning "
            "population that values both conventional excellence and integrative "
            "options. The state's proximity to leading veterinary schools has "
            "fostered a well-educated practitioner base with strong credentials in "
            "acupuncture, herbal medicine, and rehabilitation. Seasonal allergies "
            "driven by the Northeast's heavy pollen seasons and tick-borne diseases "
            "like Lyme disease are common reasons Connecticut pet owners seek "
            "holistic care for immune support and chronic symptom management."
        ),
        "DE": (
            "Delaware may be small, but its pet owners have access to integrative "
            "veterinary care that addresses the region's common health challenges. "
            "The mid-Atlantic climate brings seasonal allergies, tick-borne diseases, "
            "and humidity-related skin conditions that respond well to holistic "
            "treatment approaches. Delaware's holistic practitioners often serve "
            "pet owners from neighboring states as well, reflecting the broader "
            "demand for integrative veterinary options in the region."
        ),
        "FL": (
            "Florida's subtropical environment creates persistent health challenges "
            "for pets that make holistic care especially relevant. Year-round flea "
            "and tick pressure, intense humidity, mold-driven allergies, and heat "
            "stress are daily realities for Florida pets. The state also has one of "
            "the largest senior pet populations in the country, driving demand for "
            "integrative approaches to arthritis, cognitive decline, and age-related "
            "organ support. Florida's thriving equine industry — from polo in "
            "Wellington to racing statewide — also supports a strong community of "
            "integrative equine practitioners."
        ),
        "GA": (
            "Georgia's warm climate and rich biodiversity mean that pets here face "
            "year-round environmental allergens, heartworm risk, and tick-borne "
            "diseases. Holistic veterinarians in Georgia frequently use acupuncture "
            "and herbal medicine to support immune function and manage chronic "
            "conditions that the climate exacerbates. The Atlanta metro area has a "
            "particularly active integrative veterinary community, with practitioners "
            "offering modalities ranging from TCVM and homeopathy to laser therapy "
            "and veterinary rehabilitation."
        ),
        "HI": (
            "Hawaii's tropical climate and island geography create a unique context "
            "for pet health care. Pets here contend with year-round flea pressure, "
            "humidity-driven skin conditions, and limited access to veterinary "
            "specialists due to the state's isolation. Holistic veterinarians in "
            "Hawaii play a particularly important role, often serving as the primary "
            "source of integrative and specialized care. The state's strong cultural "
            "connection to natural healing traditions aligns well with holistic "
            "veterinary approaches, and many Hawaii practitioners incorporate "
            "locally sourced herbs and traditional practices into their care."
        ),
        "ID": (
            "Idaho's rural landscape and active outdoor culture create a pet "
            "population that benefits significantly from integrative veterinary "
            "care. Working ranch dogs, hunting companions, and trail-running pets "
            "frequently need chiropractic, acupuncture, and rehabilitation support "
            "for musculoskeletal injuries. Idaho's holistic practitioners also serve "
            "the state's horse community, offering equine acupuncture and "
            "chiropractic care for performance and pleasure horses navigating "
            "the state's rugged terrain."
        ),
        "IL": (
            "Illinois offers pet owners a strong network of holistic veterinarians, "
            "particularly in the Chicago metropolitan area. The state's harsh winters "
            "and dramatic seasonal shifts contribute to joint stiffness, seasonal "
            "allergies, and immune stress in pets. Acupuncture for pain management "
            "and herbal medicine for chronic conditions are among the most sought-after "
            "integrative services. Illinois is also home to several veterinary schools "
            "and research institutions that have advanced the evidence base for "
            "integrative veterinary medicine."
        ),
        "IN": (
            "Indiana pet owners are increasingly seeking holistic alternatives for "
            "chronic conditions that conventional medicine manages but does not always "
            "resolve. The state's agricultural landscape means that pets and livestock "
            "alike benefit from integrative veterinary care. Nutritional therapy and "
            "herbal medicine are particularly popular among Indiana pet owners who "
            "value a whole-body approach to animal health. The state's equine "
            "community, centered around racing and recreational riding, also drives "
            "demand for chiropractic and acupuncture services."
        ),
        "IA": (
            "Iowa's strong agricultural heritage has fostered a veterinary community "
            "that understands both companion animal and large animal health. Holistic "
            "practitioners in Iowa frequently work with dogs, cats, horses, and "
            "livestock, offering acupuncture, chiropractic care, and herbal medicine "
            "across species. The state's cold winters and hot, humid summers create "
            "seasonal health challenges — from arthritis flare-ups in winter to skin "
            "allergies and insect-related conditions in summer — that respond well "
            "to integrative management."
        ),
        "KS": (
            "Kansas pet owners seeking holistic veterinary care often look for "
            "practitioners who understand the health challenges of the Great Plains "
            "climate — extreme temperature swings, high winds, and allergen-heavy "
            "seasons. Chiropractic and acupuncture are popular modalities for the "
            "state's active farm dogs and working breeds, while nutritional therapy "
            "and herbal medicine serve pets with chronic skin and digestive conditions. "
            "Kansas also has a dedicated equine community that values integrative "
            "approaches to horse health and performance."
        ),
        "KY": (
            "Kentucky is horse country, and the state's holistic veterinary community "
            "reflects that. Equine acupuncture, chiropractic care, and herbal medicine "
            "are widely available, serving everything from Thoroughbred racehorses to "
            "pleasure mounts and therapy horses. But Kentucky's integrative "
            "practitioners serve companion animals with equal dedication, offering "
            "holistic approaches to the chronic allergies, joint disease, and "
            "tick-borne illnesses common in the state's warm, humid climate."
        ),
        "LA": (
            "Louisiana's hot, humid climate and rich ecosystem create unique health "
            "challenges for pets. Persistent flea and mosquito pressure, heartworm "
            "risk, fungal skin infections, and heat-related conditions are everyday "
            "concerns. Holistic veterinarians in Louisiana often focus on immune "
            "support, herbal parasite management, and nutritional therapy to build "
            "resilience against these environmental stressors. The state's cultural "
            "appreciation for traditional healing aligns naturally with holistic "
            "veterinary philosophy."
        ),
        "ME": (
            "Maine's rugged outdoors and active pet culture drive strong demand for "
            "integrative veterinary care. Tick-borne diseases — particularly Lyme "
            "disease — are a major concern, and holistic practitioners frequently "
            "use acupuncture, herbal immune support, and nutritional therapy alongside "
            "conventional treatment. Maine's cold winters also mean arthritis and "
            "joint stiffness are common in senior pets, making chiropractic care and "
            "laser therapy popular year-round modalities. The state's relatively "
            "small size fosters close relationships between holistic practitioners "
            "and the communities they serve."
        ),
        "MD": (
            "Maryland's location in the mid-Atlantic corridor gives pet owners access "
            "to a well-established network of holistic veterinarians, particularly "
            "in the Baltimore-Washington metro area. The state's mix of urban, "
            "suburban, and rural communities means practitioners serve everything "
            "from apartment cats to farm dogs to competition horses. Tick-borne "
            "diseases, seasonal allergies, and the stress of high-density living "
            "are common drivers for integrative care, with acupuncture and "
            "behavioral support being especially sought after."
        ),
        "MA": (
            "Massachusetts has one of the most established holistic veterinary "
            "communities in New England, concentrated in the Boston metro area but "
            "extending throughout the state. The proximity to major veterinary "
            "academic institutions has produced a practitioner base that blends "
            "strong conventional training with advanced integrative credentials. "
            "Chronic conditions exacerbated by New England's harsh winters — "
            "arthritis, respiratory issues, and seasonal depression in pets — are "
            "common reasons Massachusetts pet owners seek holistic care."
        ),
        "MI": (
            "Michigan's four-season climate and Great Lakes geography create a diverse "
            "range of health challenges for pets. Long, cold winters exacerbate "
            "arthritis and joint disease, while humid summers bring skin allergies "
            "and insect-borne conditions. Michigan's holistic veterinary community "
            "is well equipped to address these seasonal patterns with acupuncture, "
            "chiropractic care, and herbal medicine. The state also has a notable "
            "equine population, and integrative equine practitioners serve horse "
            "owners throughout the state's rural areas."
        ),
        "MN": (
            "Minnesota's extreme winters and active outdoor culture make integrative "
            "veterinary care particularly relevant. Arthritis management is a year-round "
            "concern for pets dealing with cold-weather joint stiffness, and many "
            "Minnesota holistic vets specialize in acupuncture, laser therapy, and "
            "rehabilitation for mobility support. The Twin Cities metro area offers "
            "a strong concentration of integrative practitioners, while rural Minnesota "
            "is served by mobile holistic vets and telehealth consultations that "
            "extend integrative care to farming and lake communities."
        ),
        "MS": (
            "Mississippi's warm, humid climate means that pets face persistent "
            "environmental challenges including flea and tick infestations, heartworm "
            "risk, and heat-related conditions throughout much of the year. Holistic "
            "veterinarians in Mississippi bring integrative approaches to these common "
            "issues, using herbal medicine, nutritional therapy, and acupuncture to "
            "build systemic resilience. The state's rural character also means that "
            "many holistic practitioners serve both companion animals and livestock, "
            "bringing a broad perspective to integrative animal care."
        ),
        "MO": (
            "Missouri sits at the crossroads of the Midwest and the South, and its "
            "holistic veterinary community reflects that diversity. The St. Louis and "
            "Kansas City metro areas offer strong concentrations of integrative "
            "practitioners, while rural Missouri is served by mobile veterinarians "
            "and equine specialists. The state's variable climate — cold winters, hot "
            "humid summers — creates seasonal allergy patterns and arthritis "
            "challenges that respond well to acupuncture, chiropractic care, and "
            "herbal medicine."
        ),
        "MT": (
            "Montana's vast landscapes and ranching culture create a pet and livestock "
            "population that benefits greatly from integrative veterinary care. Working "
            "dogs, ranch horses, and outdoor companions face musculoskeletal demands "
            "that make chiropractic and acupuncture essential modalities. Montana's "
            "holistic veterinary practitioners are often experienced across multiple "
            "species, serving dogs, cats, horses, and livestock alike. The state's "
            "limited number of practitioners means many work across large territories, "
            "and telehealth has become an increasingly important tool for extending "
            "holistic care to remote communities."
        ),
        "NE": (
            "Nebraska's agricultural heartland has fostered a veterinary community "
            "that values practical, whole-animal approaches to health care. Holistic "
            "practitioners in Nebraska frequently serve both companion animals and "
            "livestock, bringing integrative perspectives to conditions ranging from "
            "chronic pain and digestive disorders in dogs to performance and fertility "
            "issues in horses and cattle. The state's extreme seasonal temperature "
            "swings create recurring patterns of joint stiffness and skin conditions "
            "that benefit from year-round integrative management."
        ),
        "NV": (
            "Nevada's desert environment and extreme heat present unique challenges "
            "for pet health. Dehydration, heat stress, dry skin conditions, and "
            "exposure to desert-specific hazards like rattlesnakes and Valley Fever "
            "are common concerns. Holistic veterinarians in Nevada — concentrated "
            "primarily in the Las Vegas and Reno metro areas — offer acupuncture, "
            "herbal medicine, and nutritional therapy tailored to the demands of "
            "desert living. The state's growing pet-owner population has driven "
            "increasing demand for integrative options beyond conventional care."
        ),
        "NH": (
            "New Hampshire's rugged terrain and outdoor recreation culture produce "
            "active dogs that frequently benefit from integrative musculoskeletal "
            "care. Tick-borne diseases are a significant concern throughout the state, "
            "and holistic veterinarians often use acupuncture and herbal immune "
            "support as part of comprehensive Lyme disease management. The state's "
            "cold winters also drive demand for arthritis care and pain management "
            "modalities that reduce reliance on long-term pharmaceutical use."
        ),
        "NJ": (
            "New Jersey's dense population and proximity to major metropolitan areas "
            "give pet owners access to a wide range of holistic veterinary specialists. "
            "The state's diverse geography — from shore communities to suburban towns "
            "to rural farmland — means practitioners serve varied animal populations "
            "with different health needs. Tick-borne diseases, environmental allergies, "
            "and the stress-related conditions common in high-density living "
            "environments are frequent drivers for integrative care. New Jersey's "
            "equine community, centered in the horse country of Hunterdon and "
            "Somerset counties, also supports a strong base of integrative equine practitioners."
        ),
        "NM": (
            "New Mexico's high desert climate and unique ecology create health "
            "considerations that holistic veterinarians are well positioned to "
            "address. Valley Fever, dry skin conditions, foxtail injuries, and the "
            "effects of intense UV exposure at altitude are common concerns. The "
            "state's deep cultural roots in traditional healing practices align "
            "naturally with holistic veterinary philosophy, and many New Mexico "
            "practitioners incorporate indigenous herbal traditions alongside "
            "conventional integrative modalities like acupuncture and TCVM."
        ),
        "NY": (
            "New York offers one of the most diverse holistic veterinary landscapes "
            "in the country. New York City's dense urban environment drives demand "
            "for anxiety management, stress-related digestive conditions, and "
            "nutritional optimization for apartment-dwelling pets. Upstate New York's "
            "rural communities, meanwhile, support holistic practitioners who serve "
            "farm animals, horses, and companion animals with conditions shaped by "
            "the region's cold winters and heavy tick populations. The state's overall "
            "concentration of veterinary expertise makes it a leader in integrative "
            "animal medicine."
        ),
        "NC": (
            "North Carolina's diverse geography — from the Blue Ridge Mountains to "
            "the coastal plain — supports a varied pet population with distinct "
            "health needs. Mountain communities seek integrative care for active, "
            "trail-running dogs, while coastal pet owners deal with humidity-driven "
            "skin conditions and persistent flea pressure. The Research Triangle "
            "area has a particularly strong holistic veterinary community, and the "
            "state's prominent veterinary school at NC State has contributed to a "
            "well-trained practitioner base with both conventional and integrative expertise."
        ),
        "ND": (
            "North Dakota's harsh winters and agricultural landscape shape the "
            "health needs of its pet and livestock populations. Extreme cold "
            "exacerbates arthritis and joint conditions in working dogs and aging "
            "pets, making acupuncture and chiropractic care valuable modalities. "
            "The state's limited number of holistic practitioners means that many "
            "pet owners rely on telehealth consultations with integrative "
            "veterinarians, and mobile practitioners who travel across the state's "
            "vast distances to bring holistic care to rural communities."
        ),
        "OH": (
            "Ohio has a well-established holistic veterinary community, particularly "
            "in the Cleveland, Columbus, and Cincinnati metro areas. The state's "
            "four-season climate contributes to seasonal allergy patterns, winter "
            "joint stiffness, and tick-borne disease risk that respond well to "
            "integrative management. Ohio's strong tradition in veterinary education "
            "— anchored by The Ohio State University College of Veterinary Medicine — "
            "has produced a practitioner base that values evidence-based integrative "
            "approaches to animal health care."
        ),
        "OK": (
            "Oklahoma's climate and landscape create health challenges for pets that "
            "span extreme heat, severe storms, and allergen-heavy seasons. Holistic "
            "veterinarians in Oklahoma commonly treat anxiety and noise phobia — "
            "understandable in a state that sits squarely in Tornado Alley — alongside "
            "chronic skin conditions, digestive issues, and musculoskeletal problems "
            "in working dogs and horses. The state's equine community is well served "
            "by integrative practitioners offering chiropractic, acupuncture, and "
            "herbal medicine for performance and recreational horses."
        ),
        "OR": (
            "Oregon has one of the most progressive holistic veterinary communities "
            "in the Pacific Northwest. The Portland metro area is particularly well "
            "served, with practitioners offering everything from classical homeopathy "
            "and TCVM to raw diet consultations and veterinary rehabilitation. "
            "Oregon's damp climate contributes to chronic ear infections, fungal "
            "skin conditions, and joint issues that benefit from integrative "
            "management. The state's culture of environmental consciousness and "
            "natural living aligns closely with the philosophy behind holistic "
            "veterinary medicine."
        ),
        "PA": (
            "Pennsylvania offers a strong and diverse holistic veterinary community "
            "spanning the Philadelphia and Pittsburgh metro areas and the rural "
            "communities between them. The state's significant horse population — "
            "particularly in Chester and Lancaster counties — supports a robust "
            "equine integrative practice community. For companion animals, "
            "Pennsylvania's seasonal climate drives demand for arthritis management, "
            "allergy support, and tick-borne disease treatment using acupuncture, "
            "herbal medicine, and nutritional therapy."
        ),
        "RI": (
            "Rhode Island may be the smallest state, but its pet owners have access "
            "to integrative veterinary care that addresses the region's common health "
            "concerns. Tick-borne diseases, seasonal allergies driven by New England's "
            "intense pollen seasons, and cold-weather joint conditions are frequent "
            "reasons pet owners seek holistic alternatives. Rhode Island's compact "
            "geography means that practitioners are readily accessible throughout "
            "the state, and the proximity to veterinary resources in Massachusetts "
            "and Connecticut extends the available options further."
        ),
        "SC": (
            "South Carolina's warm, humid climate and coastal environment create "
            "persistent health challenges for pets, including year-round flea and "
            "tick pressure, heartworm risk, and skin conditions aggravated by "
            "humidity and heat. Holistic veterinarians in South Carolina use "
            "acupuncture, herbal medicine, and nutritional therapy to build systemic "
            "resilience against these environmental stressors. The state's growing "
            "equine community along the coast and in the Aiken area also benefits "
            "from integrative equine practitioners."
        ),
        "SD": (
            "South Dakota's wide open spaces and ranching culture produce pets and "
            "working animals that benefit from integrative veterinary care. Cold "
            "winters and physically demanding work take a toll on joints and muscles, "
            "making chiropractic care and acupuncture particularly relevant. The "
            "state's limited number of holistic practitioners means that those who "
            "practice integrative medicine often serve large geographic areas, and "
            "telehealth has become an important way to extend holistic care to "
            "remote communities across the state."
        ),
        "TN": (
            "Tennessee's location in the upper South gives its pets a climate that "
            "combines warm summers with genuine winters, producing a range of health "
            "challenges from seasonal allergies to cold-weather joint stiffness. "
            "The Nashville and Memphis metro areas have growing holistic veterinary "
            "communities, and the state's Walking Horse and equine traditions support "
            "integrative equine practitioners. Tennessee's holistic vets frequently "
            "use acupuncture, herbal medicine, and TCVM to address chronic conditions "
            "in both companion animals and horses."
        ),
        "TX": (
            "Texas is vast, and its holistic veterinary community reflects that "
            "scale. From Houston to Dallas to Austin and San Antonio, pet owners "
            "across the state have access to integrative practitioners offering "
            "acupuncture, TCVM, chiropractic, and herbal medicine. The state's "
            "intense heat, large insect populations, and Valley Fever risk in "
            "West Texas create health demands that benefit from holistic management. "
            "Texas also has one of the largest equine populations in the country, "
            "and integrative equine care — particularly acupuncture and chiropractic — "
            "is widely available."
        ),
        "UT": (
            "Utah's dramatic landscapes and outdoor recreation culture produce an "
            "active pet population with significant demand for integrative "
            "musculoskeletal care. Dogs that hike red rock canyons, run mountain "
            "trails, and endure cold, dry winters frequently benefit from "
            "chiropractic, acupuncture, and rehabilitation services. Utah's dry "
            "climate also contributes to skin and respiratory conditions that "
            "respond to herbal medicine and nutritional therapy. The Salt Lake "
            "City area has the state's strongest concentration of holistic "
            "veterinary practitioners."
        ),
        "VT": (
            "Vermont's commitment to sustainable living and natural approaches to "
            "health extends to how its residents care for their animals. The state's "
            "holistic veterinary practitioners serve a community that values "
            "whole-body, minimally invasive care for their pets. Cold winters, "
            "tick-borne diseases, and the physical demands placed on farm and "
            "working dogs make acupuncture, chiropractic care, and herbal medicine "
            "particularly relevant. Vermont's small-scale farming community also "
            "supports holistic practitioners who work across species, from "
            "companion animals to goats, sheep, and horses."
        ),
        "VA": (
            "Virginia's diverse geography — from the Chesapeake Bay to the Blue "
            "Ridge Mountains to the Shenandoah Valley — supports a varied pet "
            "population with distinct health needs. The Northern Virginia suburbs "
            "of Washington, D.C. have a strong concentration of holistic "
            "veterinarians, while the state's horse country in Loudoun, Fauquier, "
            "and Albemarle counties supports a thriving integrative equine practice "
            "community. Tick-borne diseases, seasonal allergies, and performance-related "
            "musculoskeletal conditions are common drivers for integrative care "
            "across the state."
        ),
        "WA": (
            "Washington State has a thriving holistic veterinary community, anchored "
            "by the Seattle metro area but extending throughout the Puget Sound "
            "region and beyond. The state's damp, mild climate contributes to "
            "chronic ear infections, skin allergies, and fungal conditions that "
            "benefit from integrative management. Washington's culture of "
            "environmental awareness and natural health aligns closely with holistic "
            "veterinary philosophy, and many practitioners here are at the forefront "
            "of integrative approaches including TCVM, veterinary rehabilitation, "
            "and evidence-based herbal medicine."
        ),
        "WV": (
            "West Virginia's mountainous terrain and rural character create a pet "
            "population that relies on hardy, working animals and benefits from "
            "practical integrative care. Musculoskeletal conditions from the "
            "physical demands of mountain living, tick-borne diseases, and limited "
            "access to veterinary specialists make holistic practitioners especially "
            "valuable in this state. West Virginia's holistic vets often serve "
            "large geographic areas, bringing acupuncture, chiropractic, and herbal "
            "medicine to communities that might otherwise lack access to these "
            "modalities."
        ),
        "WI": (
            "Wisconsin's cold winters and active outdoor culture make integrative "
            "veterinary care a natural fit. Arthritis management, cold-weather joint "
            "support, and rehabilitation for active hunting and sporting dogs are "
            "among the most common reasons pet owners seek holistic care. The "
            "Milwaukee and Madison metro areas offer strong concentrations of "
            "integrative practitioners, and the state's dairy farming heritage has "
            "produced veterinarians with broad experience across companion animals, "
            "horses, and livestock."
        ),
        "WY": (
            "Wyoming's rugged landscape, extreme winters, and ranching culture "
            "produce animals — both companion and working — with significant "
            "musculoskeletal and endurance demands. Holistic veterinarians in "
            "Wyoming often work across species, offering chiropractic, acupuncture, "
            "and herbal medicine to dogs, horses, and livestock. The state's sparse "
            "population and vast distances mean that many practitioners travel "
            "extensively, and telehealth consultations have become an important way "
            "to provide integrative care to pet owners in remote areas."
        ),
        "DC": (
            "Washington, D.C.'s urban environment creates a pet population that "
            "faces the health challenges of city living — stress and anxiety, limited "
            "exercise space, environmental toxin exposure, and the digestive and "
            "behavioral issues that accompany high-density living. Holistic "
            "veterinarians in the D.C. area are well equipped to address these "
            "concerns with acupuncture for anxiety, nutritional therapy for "
            "sensitive digestive systems, and herbal medicine for chronic conditions "
            "that benefit from a gentler, whole-body approach."
        ),
    }

    # State-specific page title overrides for high-impression, low-click pages
    STATE_TITLE_OVERRIDES = {
        "CO": "Find a Holistic Veterinarian in Colorado | Integrative Vets Near Me",
    }

    # State-specific meta description overrides
    STATE_DESCRIPTION_OVERRIDES = {
        "CO": (
            "Looking for a holistic veterinarian in Colorado? Browse our directory of "
            "integrative and holistic vets near you in Denver, Colorado Springs, and "
            "across the state. Find practitioners offering acupuncture, chiropractic, "
            "herbal medicine, and physical rehabilitation for dogs, cats, and horses."
        ),
    }

    # Key: "STATE_CODE:city-slug"
    CITY_EDITORIAL = {
        "CO:denver": (
            "Denver's active, outdoor-oriented culture means pets here often share the "
            "same high-altitude lifestyle as their owners — hiking, trail running, and "
            "year-round mountain adventures. Holistic veterinarians in Denver understand "
            "these unique demands, offering acupuncture and rehabilitation therapy for "
            "athletic dogs recovering from joint stress, herbal medicine for respiratory "
            "support at elevation, and nutritional therapy tailored to high-energy working "
            "breeds. Denver's progressive pet-care culture has also made integrative "
            "medicine more mainstream here than in most U.S. cities, with owners actively "
            "seeking alternatives to over-vaccination and long-term pharmaceutical dependency."
        ),
        "TX:houston": (
            "Houston's subtropical climate creates year-round challenges for pets: "
            "persistent flea, tick, and heartworm pressure, seasonal allergies from "
            "Gulf Coast pollen, and heat-related inflammation in brachycephalic breeds. "
            "Holistic veterinarians in Houston offer acupuncture, herbal medicine, and "
            "Traditional Chinese Veterinary Medicine to address these chronic conditions "
            "with fewer pharmaceutical side effects. Houston's large and diverse pet-owning "
            "community — from the Heights to the Energy Corridor — has driven growing "
            "demand for integrative vet care that treats the root cause of illness rather "
            "than masking symptoms. Whether your pet needs pain management, immune "
            "support, or natural anxiety relief, Houston's holistic vets offer "
            "evidence-based complementary therapies alongside conventional care."
        ),
    }

    CITY_META_OVERRIDES = {
        "CO:denver": (
            "Find holistic veterinarians in Denver, Colorado specializing in acupuncture, "
            "herbal medicine & integrative pet care. Browse holistic vets near you in Denver CO."
        ),
        "TX:houston": (
            "Find holistic veterinarians in Houston, Texas offering acupuncture, herbal "
            "medicine & integrative care. Browse holistic vets in Houston TX near you."
        ),
    }

    def _generate_state_pages(self):
        print("Generating state pages...")
        for state in self.processor.states:
            if state.vet_count == 0:
                continue

            state_vets = self.processor.vets_by_state.get(state.code, [])
            cities = self.processor.cities_by_state.get(state.code, [])
            editorial = self.STATE_EDITORIAL.get(state.code, "")

            page_title = self.STATE_TITLE_OVERRIDES.get(
                state.code,
                f'Holistic Veterinarians in {state.name}'
            )
            page_description = self.STATE_DESCRIPTION_OVERRIDES.get(
                state.code,
                f'Find {state.vet_count} holistic, homeopathic, and integrative veterinarians in {state.name}. Browse certified practitioners offering acupuncture, herbal medicine, chiropractic and natural pet care near you.'
            )

            self._render_and_write('state_list.html', f'vets/{state.slug}/index.html', {
                'page_title': page_title,
                'page_description': page_description,
                'state': state,
                'vets': sorted(state_vets, key=lambda v: (v.city, v.practice_name)),
                'cities': cities,
                'state_editorial': editorial,
            })
    
    # Minimum number of vets for a city page to be indexed.
    # City pages with fewer vets are thin doorway pages that dilute quality signals.
    CITY_NOINDEX_MIN_VETS = 3

    def _generate_city_pages(self):
        print("Generating city pages...")
        city_indexed = 0
        city_noindexed = 0

        for state_code, city_dict in self.processor.vets_by_city.items():
            state = self.processor.state_by_code.get(state_code)
            if not state:
                continue

            for city_slug, city_vets in city_dict.items():
                if not city_vets:
                    continue

                city_name = city_vets[0].city
                city_key = f"{state_code}:{city_slug}"
                city_editorial = self.CITY_EDITORIAL.get(city_key, "")

                # Noindex thin city pages unless they have custom editorial content
                noindex = len(city_vets) < self.CITY_NOINDEX_MIN_VETS and not city_editorial
                if noindex:
                    city_noindexed += 1
                else:
                    city_indexed += 1

                # Find dominant specialty for editorial intro
                specialty_counts = {}
                for v in city_vets:
                    for spec in v.specialties:
                        specialty_counts[spec] = specialty_counts.get(spec, 0) + 1
                dominant_specialty = max(specialty_counts, key=specialty_counts.get) if specialty_counts else None

                city_meta = self.CITY_META_OVERRIDES.get(city_key, "")
                page_description = city_meta or f'Find {len(city_vets)} holistic and integrative veterinarians in {city_name}, {state.name}. Discover homeopathic, naturopathic, and holistic vets offering natural pet care near you.'

                self._render_and_write('city_list.html', f'vets/{state.slug}/{city_slug}/index.html', {
                    'page_title': f'Holistic Veterinarians in {city_name}, {state.name}',
                    'page_description': page_description,
                    'state': state,
                    'city': city_name,
                    'city_name': city_name,
                    'city_slug': city_slug,
                    'vets': sorted(city_vets, key=lambda v: v.practice_name),
                    'noindex': noindex,
                    'dominant_specialty': dominant_specialty,
                    'listing_count': len(city_vets),
                    'city_editorial': city_editorial,
                })

        print(f"  City pages: {city_indexed} indexed, {city_noindexed} noindexed (min vets: {self.CITY_NOINDEX_MIN_VETS})")

    # Minimum quality score for a vet page to be indexed.
    # Score is 0-10 based on: real description (+3), phone (+1), website (+1),
    # Google rating (+2), coordinates (+1), certifications (+1), email (+1).
    VET_NOINDEX_THRESHOLD = 5

    def _generate_vet_detail_pages(self):
        print("Generating vet detail pages...")
        indexed_count = 0
        noindexed_count = 0

        for vet in self.processor.vets:
            state = self.processor.state_by_code.get(vet.state)
            nearby_vets = self.processor.get_nearby_vets(vet, limit=5)

            # Get specialty details for this vet
            specialty_details = []
            for spec_name in vet.specialties:
                spec_slug = slugify(spec_name)
                spec = self.processor.specialty_by_slug.get(spec_slug)
                if spec:
                    specialty_details.append(spec)

            # Noindex thin vet pages to improve overall site quality signals.
            # Pages still exist at the same URL (no redirects) but tell Google
            # not to include them in search results until content is enriched.
            noindex = vet.quality_score < self.VET_NOINDEX_THRESHOLD
            if noindex:
                noindexed_count += 1
            else:
                indexed_count += 1

            # Build a meta description that ends at a sentence boundary
            vet_meta_desc = f'{vet.practice_name} offers holistic veterinary care in {vet.city}, {vet.state}.'
            if vet.practice_description:
                # Try to find a sentence boundary within 155 chars
                desc = vet.practice_description
                for end in range(min(155, len(desc)), 80, -1):
                    if desc[end - 1] in '.!':
                        vet_meta_desc = desc[:end]
                        break
                else:
                    # No sentence boundary found; truncate at word boundary and add suffix
                    vet_meta_desc = desc[:120].rsplit(' ', 1)[0].rstrip('.,') + f'. Holistic vet in {vet.city}, {vet.state}.'

            self._render_and_write('vet_detail.html', f'vet/{vet.slug}/index.html', {
                'page_title': f'Holistic Vet in {vet.city}, {vet.state} | {vet.practice_name}',
                'page_description': vet_meta_desc,
                'noindex': noindex,
                'vet': vet,
                'state': state,
                'nearby_vets': nearby_vets,
                'specialty_details': specialty_details,
            })

        print(f"  Vet pages: {indexed_count} indexed, {noindexed_count} noindexed (threshold: {self.VET_NOINDEX_THRESHOLD})")
    
    def _generate_specialties_list(self):
        print("Generating specialties list...")

        # Build top-rated vets (4.7+) per specialty for the specialties overview page
        top_rated_by_specialty = {}
        for specialty in self.processor.specialties:
            spec_vets = self.processor.vets_by_specialty.get(specialty.slug, [])
            top = sorted(
                [v for v in spec_vets if v.google_rating and v.google_rating >= 4.7],
                key=lambda v: (-v.google_rating, -v.google_reviews)
            )[:3]
            if top:
                top_rated_by_specialty[specialty.slug] = top

        self._render_and_write('specialties_list.html', 'specialties/index.html', {
            'page_title': 'Holistic Veterinary Specialties',
            'page_description': 'Learn about holistic veterinary modalities including acupuncture, herbal medicine, chiropractic care, and more.',
            'specialties': sorted(self.processor.specialties, key=lambda s: s.name),
            'top_rated_by_specialty': top_rated_by_specialty,
        })
    
    def _generate_specialty_pages(self):
        print("Generating specialty pages...")
        for specialty in self.processor.specialties:
            spec_vets = self.processor.vets_by_specialty.get(specialty.slug, [])

            # Group vets by state for sidebar
            vets_by_state = defaultdict(list)
            for vet in spec_vets:
                vets_by_state[vet.state].append(vet)

            self._render_and_write('specialty_detail.html', f'specialty/{specialty.slug}/index.html', {
                'page_title': f'{specialty.name} - Holistic Veterinary Care',
                'page_description': self._truncate_meta(f'Find veterinarians offering {specialty.name}. {specialty.description}') if specialty.description else f'Find veterinarians offering {specialty.name}.',
                'specialty': specialty,
                'vets': sorted(spec_vets, key=lambda v: (v.state, v.city, v.practice_name)),
                'vets_by_state': dict(vets_by_state),
            })
    
    def _generate_search_page(self):
        print("Generating search page...")
        self._render_and_write('search.html', 'search/index.html', {
            'page_title': 'Find Holistic Vets Near Me | Search by Location',
            'page_description': 'Search for holistic veterinarians by city, state, or ZIP code. Filter by specialty — acupuncture, herbal medicine, chiropractic, TCVM, and more. Find integrative pet care near you.',
            'noindex': True,
        })
    
    def _generate_blog_list(self):
        """Generate blog listing page."""
        if not self.processor.blog_posts:
            print("Skipping blog list (no published posts)...")
            return
            
        print("Generating blog list...")
        self._render_and_write(
            'blog_list.html',
            'blog/index.html',
            {
                'page_title': 'Blog - Holistic Pet Care Articles',
                'page_description': 'Expert articles on holistic veterinary care, natural pet health, and integrative medicine for your pets.',
                'posts': self.processor.blog_posts,
                'request_path': '/blog/',
            }
        )
        print("  Generated: blog/index.html")

    def _generate_blog_detail_pages(self):
        """Generate individual blog post pages."""
        if not self.processor.blog_posts:
            print("Skipping blog detail pages (no published posts)...")
            return
            
        print("Generating blog post pages...")
        for post in self.processor.blog_posts:
            self._render_and_write(
                'blog_detail.html',
                f'blog/{post.slug}/index.html',
                {
                    'page_title': f'{post.title} | Holistic Vet Directory Blog',
                    'page_description': post.meta_description or self._truncate_meta(post.excerpt) if post.excerpt else f'{post.title} — Expert holistic pet care advice from Holistic Vet Directory.',
                    'post': post,
                    'request_path': f'/blog/{post.slug}/',
                    'related_posts': [p for p in self.processor.blog_posts if p.slug != post.slug][:3],
                }
            )
            print(f"  Generated: blog/{post.slug}/index.html")

    def _generate_holistic_care_guide(self):
        print("Generating holistic care guide...")
        self._render_and_write('holistic_care_guide.html', 'holistic-care-guide/index.html', {
            'page_title': 'Holistic Pet Care Guide — Conditions, Specialties & Certifications',
            'page_description': 'Find the right holistic treatment for your pet. Match conditions to specialties, understand vet certifications like AHVMA, IVAS, and Chi Institute, and make informed choices about integrative veterinary care.',
            'specialties': self.processor.specialties,
            'total_vets': len(self.processor.vets),
            'request_path': '/holistic-care-guide/',
        })

    def _generate_static_pages(self):
        print("Generating static pages...")
        
        self._render_and_write('about.html', 'about/index.html', {
            'page_title': 'About Holistic Vet Directory',
            'page_description': 'Learn about our mission to connect pet owners with holistic and integrative veterinary care.',
        })
        
        self._render_and_write('submit.html', 'submit/index.html', {
            'page_title': 'Submit Your Practice',
            'page_description': 'Submit your holistic veterinary practice to our directory.',
        })
        
        self._render_and_write('privacy.html', 'privacy/index.html', {
            'page_title': 'Privacy Policy',
            'page_description': 'Privacy policy for Holistic Vet Directory.',
        })
        
        self._render_and_write('terms.html', 'terms/index.html', {
            'page_title': 'Terms of Service',
            'page_description': 'Terms of service for Holistic Vet Directory.',
        })
        
        self._render_and_write('contact.html', 'contact/index.html', {
            'page_title': 'Contact Us',
            'page_description': 'Contact us with questions about holistic veterinary care or to suggest a veterinarian.',
        })
        
        self._render_and_write('success.html', 'success/index.html', {
            'page_title': 'Thank You',
            'page_description': 'Your message has been sent successfully.',
        })
        
        self._render_and_write('404.html', '404.html', {
            'page_title': 'Page Not Found',
            'page_description': 'The page you requested could not be found.',
        })
    
    def _generate_search_index(self):
        print("Generating search index...")
        index = self.processor.get_search_index()
        output_file = self.output_dir / 'search-index.json'
        output_file.write_text(json.dumps(index, indent=2), encoding='utf-8')
        print(f"  Generated: search-index.json ({len(index)} entries)")
    
    def _generate_sitemap(self):
        print("Generating sitemap...")
        today = datetime.now().strftime('%Y-%m-%d')
        
        urls = [
            {'loc': '/', 'priority': '1.0', 'changefreq': 'daily'},
            {'loc': '/vets/', 'priority': '0.9', 'changefreq': 'daily'},
            {'loc': '/specialties/', 'priority': '0.8', 'changefreq': 'weekly'},
            {'loc': '/holistic-care-guide/', 'priority': '0.8', 'changefreq': 'weekly'},
            {'loc': '/about/', 'priority': '0.5', 'changefreq': 'monthly'},
            {'loc': '/submit/', 'priority': '0.5', 'changefreq': 'monthly'},
        ]
        
        # Add state pages
        for state in self.processor.states:
            if state.vet_count > 0:
                urls.append({'loc': f'/vets/{state.slug}/', 'priority': '0.7', 'changefreq': 'weekly'})

        # Add city pages (only those above vet count threshold or with editorial)
        for state_code, city_dict in self.processor.vets_by_city.items():
            state = self.processor.state_by_code.get(state_code)
            if not state:
                continue
            for city_slug, city_vets in city_dict.items():
                if not city_vets:
                    continue
                city_key = f"{state_code}:{city_slug}"
                has_editorial = bool(self.CITY_EDITORIAL.get(city_key, ""))
                if len(city_vets) >= self.CITY_NOINDEX_MIN_VETS or has_editorial:
                    urls.append({'loc': f'/vets/{state.slug}/{city_slug}/', 'priority': '0.6', 'changefreq': 'weekly'})

        # Add specialty pages
        for specialty in self.processor.specialties:
            if specialty.vet_count > 0:
                urls.append({'loc': f'/specialty/{specialty.slug}/', 'priority': '0.7', 'changefreq': 'weekly'})
        
        # Add vet detail pages (only those above quality threshold)
        for vet in self.processor.vets:
            if vet.quality_score >= self.VET_NOINDEX_THRESHOLD:
                urls.append({'loc': f'/vet/{vet.slug}/', 'priority': '0.6', 'changefreq': 'monthly'})
        
        # Add blog pages
        if self.processor.blog_posts:
            urls.append({'loc': '/blog/', 'priority': '0.7', 'changefreq': 'weekly'})
            for post in self.processor.blog_posts:
                urls.append({'loc': f'/blog/{post.slug}/', 'priority': '0.6', 'changefreq': 'monthly'})
        
        sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        
        for url in urls:
            sitemap_xml += '  <url>\n'
            sitemap_xml += f'    <loc>{self.config.site_url}{url["loc"]}</loc>\n'
            sitemap_xml += f'    <lastmod>{today}</lastmod>\n'
            sitemap_xml += f'    <changefreq>{url["changefreq"]}</changefreq>\n'
            sitemap_xml += f'    <priority>{url["priority"]}</priority>\n'
            sitemap_xml += '  </url>\n'
        
        sitemap_xml += '</urlset>'
        
        output_file = self.output_dir / 'sitemap.xml'
        output_file.write_text(sitemap_xml, encoding='utf-8')
        print(f"  Generated: sitemap.xml ({len(urls)} URLs)")
    
    def _generate_robots_txt(self):
        print("Generating robots.txt...")
        robots = f"""User-agent: *
Allow: /

Sitemap: {self.config.site_url}/sitemap.xml
"""
        output_file = self.output_dir / 'robots.txt'
        output_file.write_text(robots, encoding='utf-8')
        print("  Generated: robots.txt")
    
    def _copy_static_assets(self):
        print("Copying static assets...")
        static_src = Path(__file__).parent / 'static'
        static_dst = self.output_dir / 'static'
        
        if static_src.exists():
            shutil.copytree(static_src, static_dst)
            print(f"  Copied: static/")
        
        # Copy ads.txt to root for AdSense
        ads_txt_src = static_src / 'ads.txt'
        if ads_txt_src.exists():
            shutil.copy(ads_txt_src, self.output_dir / 'ads.txt')
            print(f"  Copied: ads.txt")

        # Copy llms.txt to root for AI/LLM visibility
        llms_txt_src = static_src / 'llms.txt'
        if llms_txt_src.exists():
            shutil.copy(llms_txt_src, self.output_dir / 'llms.txt')
            print(f"  Copied: llms.txt")


def main():
    # Configuration
    config = SiteConfig.from_env()
    project_dir = Path(__file__).parent
    data_dir = project_dir / 'data'
    output_dir = project_dir / 'dist'
    
    # Check data source configuration
    data_source = os.getenv('DATA_SOURCE', 'csv').lower()
    use_airtable = data_source == 'airtable'
    
    print(f"Configuration:")
    print(f"  Site: {config.site_name}")
    print(f"  Environment: {config.build_env}")
    print(f"  Data Source: {'Airtable' if use_airtable else 'CSV files'}")
    print(f"  AdSense: {'Enabled' if config.enable_adsense else 'Disabled'}")
    print(f"  Analytics: {'Enabled' if config.enable_analytics else 'Disabled'}")
    print(f"  Maps: {'Enabled' if config.enable_maps else 'Disabled'}")
    print()
    
    # Load data
    print("Loading data...")
    loader = DataLoader(data_dir, use_airtable=use_airtable)
    vets = loader.load_veterinarians()
    specialties = loader.load_specialties()
    states = loader.load_states()
    blog_posts = loader.load_blog_posts()
    
    print(f"  Loaded {len(vets)} veterinarians")
    print(f"  Loaded {len(specialties)} specialties")
    print(f"  Loaded {len(states)} states")
    print(f"  Loaded {len(blog_posts)} blog posts")
    print()
    
    if not vets:
        print("Warning: No veterinarian data found. Site will be generated with empty listings.")
    
    # Process data
    processor = DataProcessor(vets, specialties, states, blog_posts)
    
    # Generate site
    generator = SiteGenerator(config, processor, output_dir)
    generator.generate()
    
    # Summary
    print()
    print("=" * 50)
    print("Build Summary:")
    print(f"  Total pages: {len(list(output_dir.rglob('*.html')))}")
    print(f"  Total files: {len(list(output_dir.rglob('*')))}")
    print(f"  Output directory: {output_dir}")
    print("=" * 50)


if __name__ == '__main__':
    main()
