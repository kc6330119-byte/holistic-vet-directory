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
    
    def __post_init__(self):
        if not self.slug:
            self.slug = slugify(self.practice_name)

        # Ensure list fields are actually lists (handle pipe-delimited strings from Airtable)
        self.specialties = self._ensure_list(self.specialties)
        self.certification_bodies = self._ensure_list(self.certification_bodies)
        self.species_treated = self._ensure_list(self.species_treated)

        # Auto-generate a description only when Airtable has none or a very thin one (<150 chars).
        # Any description 150+ characters is treated as real content and left untouched.
        if len(self.practice_description.strip()) < 150:
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
        if self.use_airtable and self._airtable_loader:
            return self._load_specialties_from_airtable()
        return self._load_specialties_from_csv()
    
    def _load_specialties_from_airtable(self) -> List[Specialty]:
        """Load specialties from Airtable."""
        airtable_specs = self._airtable_loader.load_specialties()
        specialties = []
        for asp in airtable_specs:
            spec = Specialty(
                name=asp.name,
                description=asp.description,
                related_conditions=asp.related_conditions,
                slug=asp.slug,
            )
            specialties.append(spec)
        return specialties
    
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
            'page_title': 'Browse Holistic Veterinarians by State',
            'page_description': 'Browse 3,200+ holistic and integrative veterinarians across all 50 states. Find practitioners offering acupuncture, chiropractic, herbal medicine, and natural pet care with verified Google ratings.',
            'vets': vets,
            'total_count': len(vets),
            'current_page': 1,
            'total_pages': 1,
            'has_prev': False,
            'has_next': False,
        })
    
    def _generate_state_pages(self):
        print("Generating state pages...")
        for state in self.processor.states:
            if state.vet_count == 0:
                continue
            
            state_vets = self.processor.vets_by_state.get(state.code, [])
            cities = self.processor.cities_by_state.get(state.code, [])
            
            self._render_and_write('state_list.html', f'vets/{state.slug}/index.html', {
                'page_title': f'Holistic Veterinarians in {state.name}',
                'page_description': f'Find {state.vet_count} holistic, homeopathic, and integrative veterinarians in {state.name}. Browse certified practitioners offering acupuncture, herbal medicine, chiropractic and natural pet care near you.',
                'state': state,
                'vets': sorted(state_vets, key=lambda v: (v.city, v.practice_name)),
                'cities': cities,
            })
    
    def _generate_city_pages(self):
        print("Generating city pages...")
        for state_code, city_dict in self.processor.vets_by_city.items():
            state = self.processor.state_by_code.get(state_code)
            if not state:
                continue
            
            for city_slug, city_vets in city_dict.items():
                if not city_vets:
                    continue
                
                city_name = city_vets[0].city
                noindex = len(city_vets) < 3
                self._render_and_write('city_list.html', f'vets/{state.slug}/{city_slug}/index.html', {
                    'page_title': f'Holistic Veterinarians in {city_name}, {state.name}',
                    'page_description': f'Find {len(city_vets)} holistic and integrative veterinarians in {city_name}, {state.name}. Discover homeopathic, naturopathic, and holistic vets offering natural pet care near you.',
                    'state': state,
                    'city_name': city_name,
                    'city_slug': city_slug,
                    'vets': sorted(city_vets, key=lambda v: v.practice_name),
                    'noindex': noindex,
                })
    
    def _generate_vet_detail_pages(self):
        print("Generating vet detail pages...")
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
            
            self._render_and_write('vet_detail.html', f'vet/{vet.slug}/index.html', {
                'page_title': f'{vet.practice_name} - Holistic Veterinarian in {vet.city}, {vet.state}',
                'page_description': f'{vet.practice_name} offers holistic veterinary care in {vet.city}, {vet.state}. Services include {", ".join(vet.specialties[:3])}.',
                'vet': vet,
                'state': state,
                'nearby_vets': nearby_vets,
                'specialty_details': specialty_details,
            })
    
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
                'page_description': f'Find veterinarians offering {specialty.name}. {specialty.description[:150]}...' if specialty.description else f'Find veterinarians offering {specialty.name}.',
                'specialty': specialty,
                'vets': sorted(spec_vets, key=lambda v: (v.state, v.city, v.practice_name)),
                'vets_by_state': dict(vets_by_state),
            })
    
    def _generate_search_page(self):
        print("Generating search page...")
        self._render_and_write('search.html', 'search/index.html', {
            'page_title': 'Find Holistic Vets Near Me | Search by Location',
            'page_description': 'Search for holistic veterinarians by city, state, or ZIP code. Filter by specialty — acupuncture, herbal medicine, chiropractic, TCVM, and more. Find integrative pet care near you.',
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
                    'page_description': post.meta_description or post.excerpt,
                    'post': post,
                    'request_path': f'/blog/{post.slug}/',
                    'related_posts': [p for p in self.processor.blog_posts if p.slug != post.slug][:3],
                }
            )
            print(f"  Generated: blog/{post.slug}/index.html")

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
            {'loc': '/search/', 'priority': '0.8', 'changefreq': 'monthly'},
            {'loc': '/about/', 'priority': '0.5', 'changefreq': 'monthly'},
            {'loc': '/submit/', 'priority': '0.5', 'changefreq': 'monthly'},
        ]
        
        # Add state pages
        for state in self.processor.states:
            if state.vet_count > 0:
                urls.append({'loc': f'/vets/{state.slug}/', 'priority': '0.7', 'changefreq': 'weekly'})
        
        # Add specialty pages
        for specialty in self.processor.specialties:
            if specialty.vet_count > 0:
                urls.append({'loc': f'/specialty/{specialty.slug}/', 'priority': '0.7', 'changefreq': 'weekly'})
        
        # Add vet detail pages
        for vet in self.processor.vets:
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
