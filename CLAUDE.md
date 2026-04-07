# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

```bash
# Install dependencies (use venv)
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Generate the static site (outputs to dist/)
python generate_site.py

# Preview locally
cd dist && python -m http.server 8000
```

The Netlify build command is: `pip install -r requirements.txt && python generate_site.py`

## Data Source

Set `DATA_SOURCE=csv` (default) or `DATA_SOURCE=airtable` in `.env`. CSV mode reads from `data/` directory; Airtable mode fetches via API. See `.env.example` for all config options.

Key CSV files in `data/`:
- `veterinarians.csv` — main directory listings (pipe-delimited multi-select fields)
- `specialties.csv` — specialty reference data
- `states.csv` — US states with regions

Blog posts live in `content/blog/` as numbered Markdown files with YAML frontmatter.

## Architecture

**Single-file generator**: `generate_site.py` (~2000 lines) is the entire build system. It contains:
- `SiteConfig` — env-based configuration dataclass
- `Veterinarian`, `Specialty`, `State`, `BlogPost` — data models (dataclasses)
- `DataLoader` — reads from CSV or Airtable, handles pipe-delimited fields
- `DataProcessor` — groups vets by state/city/specialty, builds search index, handles pagination
- `SiteGenerator` — Jinja2 rendering for all page types, copies static assets to `dist/`

**Template system**: Jinja2 templates in `templates/` with `base.html` inheritance. Partials in `templates/partials/`. Custom filters: `slugify`, `truncate_words`, `format_phone`, `pluralize`.

**URL structure**: `/vets/{state}/` → `/vets/{state}/{city}/` → `/vet/{slug}/` for listings. `/specialty/{slug}/` for specialties. `/blog/{slug}/` for posts.

## Scripts

Helper scripts in `scripts/`:
- `airtable_loader.py` — sync data from Airtable
- `csv_import.py` — import CSV data to Airtable
- `geocode.py` — geocode addresses to lat/long
- `fetch_google_ratings.py` — pull Google ratings for listings
- `scrape_emails.py` / `send_outreach_emails.py` / `update_airtable_emails.py` — outreach pipeline
- `validate_animal_practices.py` — validate listing data

## Deployment

Hosted on Netlify. Push to `main` triggers automatic deploy. Config in `netlify.toml` includes redirects (including 301s for fixed blog slug typos), security headers, and cache rules. The `dist/` directory is gitignored.

## SEO Considerations

This is an AdSense-monetized directory site. SEO is critical:
- Every page needs unique title tags and meta descriptions
- Schema.org markup (LocalBusiness, Veterinarian) on detail pages
- XML sitemap generated automatically
- `sitemap.xml` has `X-Robots-Tag: noindex` header (Netlify config)
- Blog content targets long-tail holistic vet keywords

## Project Requirements

Full PRD with Airtable schema, design specs, AdSense placement strategy, and content guidelines is in the original CLAUDE.md git history (commit before this change). Key points:
- Color palette: forest green (#2D6A4F) primary, sage (#52B788) secondary, warm orange (#F4A261) accent
- Mobile-first, accessible design (WCAG 2.1 AA)
- AdSense placements: header leaderboard, sticky sidebar, in-feed between listings, footer
- Target: holistic/integrative vet directory for US pet owners
