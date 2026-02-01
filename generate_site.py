#!/usr/bin/env python3
"""
Holistic Vet Directory - Static Site Generator

Generates a static website from Airtable data or local CSV files.
"""

import os
import sys
import json
import csv
import shutil
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from collections import defaultdict

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape
from slugify import slugify

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
            site_name=os.getenv('SITE_NAME', cls.site_name),
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
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    slug: str = ""
    
    def __post_init__(self):
        if not self.slug:
            self.slug = slugify(self.practice_name)
        
        # Ensure list fields are actually lists (handle pipe-delimited strings from Airtable)
        self.specialties = self._ensure_list(self.specialties)
        self.certification_bodies = self._ensure_list(self.certification_bodies)
        self.species_treated = self._ensure_list(self.species_treated)
    
    @staticmethod
    def _ensure_list(value) -> List[str]:
        """Convert a value to a list if it's a pipe-delimited string."""
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value:
            return [item.strip() for item in value.split('|') if item.strip()]
        return []
    
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
                latitude=av.latitude,
                longitude=av.longitude,
                slug=av.slug,
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


class DataProcessor:
    """Processes and organizes data for site generation."""
    
    def __init__(self, vets: List[Veterinarian], specialties: List[Specialty], states: List[State]):
        self.vets = vets
        self.specialties = specialties
        self.states = states
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
        self._generate_static_pages()
        self._generate_search_index()
        self._generate_sitemap()
        self._generate_robots_txt()
        self._copy_static_assets()
        
        print(f"Site generation complete! Output: {self.output_dir}")
    
    def _render_and_write(self, template_name: str, output_path: str, context: Dict[str, Any]):
        template = self.env.get_template(template_name)
        full_context = {**self.common_context, **context}
        html = template.render(**full_context)
        
        output_file = self.output_dir / output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html, encoding='utf-8')
        print(f"  Generated: {output_path}")
    
    def _generate_homepage(self):
        print("Generating homepage...")
        self._render_and_write('index.html', 'index.html', {
            'page_title': 'Find Holistic Vets Near Me | Holistic Veterinarian Directory',
            'page_description': 'Find holistic vets near you. Browse our directory of integrative veterinarians offering acupuncture, herbal medicine, chiropractic care and natural treatments for pets.',
            'featured_states': self.processor.get_featured_states(8),
            'featured_specialties': self.processor.get_featured_specialties(8),
            'featured_vets': self.processor.get_featured_vets(6),
            'recent_vets': sorted(self.processor.vets, key=lambda v: v.practice_name)[:6],
            'total_vets': len(self.processor.vets),
        })
    
    def _generate_vets_list(self):
        print("Generating vets listing...")
        vets = sorted(self.processor.vets, key=lambda v: (v.state, v.city, v.practice_name))
        self._render_and_write('vets_list.html', 'vets/index.html', {
            'page_title': 'Find a Holistic Veterinarian',
            'page_description': 'Browse our directory of holistic and integrative veterinarians across the United States.',
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
                'page_description': f'Find {state.vet_count} holistic and integrative veterinarians in {state.name}.',
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
                self._render_and_write('city_list.html', f'vets/{state.slug}/{city_slug}/index.html', {
                    'page_title': f'Holistic Veterinarians in {city_name}, {state.name}',
                    'page_description': f'Find {len(city_vets)} holistic veterinarians in {city_name}, {state.name}.',
                    'state': state,
                    'city_name': city_name,
                    'city_slug': city_slug,
                    'vets': sorted(city_vets, key=lambda v: v.practice_name),
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
        self._render_and_write('specialties_list.html', 'specialties/index.html', {
            'page_title': 'Holistic Veterinary Specialties',
            'page_description': 'Learn about holistic veterinary modalities including acupuncture, herbal medicine, chiropractic care, and more.',
            'specialties': sorted(self.processor.specialties, key=lambda s: s.name),
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
            'page_description': 'Search for holistic veterinarians near you. Find integrative vets by city, state, ZIP code, or specialty. Locate natural pet care in your area.',
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
    
    print(f"  Loaded {len(vets)} veterinarians")
    print(f"  Loaded {len(specialties)} specialties")
    print(f"  Loaded {len(states)} states")
    print()
    
    if not vets:
        print("Warning: No veterinarian data found. Site will be generated with empty listings.")
    
    # Process data
    processor = DataProcessor(vets, specialties, states)
    
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
