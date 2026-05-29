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

Blog posts are loaded in priority order: Airtable → `data/blog_posts.csv` → fallback to `content/blog/*.md` (numbered Markdown files with YAML frontmatter). In CSV mode with no `blog_posts.csv`, the Markdown files are the source of truth.

## Architecture

There is no test suite, linter, or type checker configured. Validate changes by running `python generate_site.py` and inspecting the output in `dist/`.

**Single-file generator**: `generate_site.py` (~2650 lines) is the entire build system. It contains:
- `SiteConfig` — env-based configuration dataclass
- `Veterinarian`, `Specialty`, `State`, `BlogPost` — data models (dataclasses)
- `DataLoader` — reads from CSV or Airtable, handles pipe-delimited fields
- `DataProcessor` — groups vets by state/city/specialty, builds search index, handles pagination
- `SiteGenerator` — Jinja2 rendering for all page types, copies static assets to `dist/`

**Template system**: Jinja2 templates in `templates/` with `base.html` inheritance. Partials in `templates/partials/`. Custom filters: `slugify`, `truncate_words`, `format_phone`, `pluralize`, `meta_trunc`.

**URL structure**: `/vets/{state}/` → `/vets/{state}/{city}/` → `/vet/{slug}/` for listings. `/specialty/{slug}/` for specialties. `/blog/{slug}/` for posts.

## Scripts

Helper scripts in `scripts/`:
- `airtable_loader.py` — sync data from Airtable
- `csv_import.py` — import CSV data to Airtable
- `geocode.py` — geocode addresses to lat/long
- `fetch_google_ratings.py` — pull Google ratings for listings
- `scrape_emails.py` / `send_outreach_emails.py` / `update_airtable_emails.py` — outreach pipeline
- `validate_animal_practices.py` — validate listing data

## Listing Description Remediation

Listing descriptions are remediated for Google's "scaled content abuse" / AdSense "Low Value Content" signal. The old hash-seeded spintax generator was removed from the build (`generate_site.Veterinarian` now only classifies descriptions for the index gate; it does not synthesize copy). Descriptions are written to Airtable offline by two scripts, in order:

1. `scripts/generate_fact_descriptions.py` — **Phase 1, fallback layer.** Composes each description from ONLY-TRUE Airtable facts (specialties, species, credentials, year, Google rating). Variation comes from real differing facts, never synonym shuffling. No length padding — sub-gate descriptions stay short and get noindexed on purpose.
2. `scripts/website_descriptions.py` — **Phase 2, primary value layer.** Crawls each practice's own website (homepage + an about/services page, trafilatura extraction), has Claude Haiku write an ORIGINAL fact-grounded description, and **falls back to the Phase 1 composer** when a site is dead/JS-rendered/boilerplate. Caches every crawl and LLM response under `data/site_cache/`. Never copies site prose verbatim; never invents facts. ~76% of listings yield website-derived copy; full-corpus Haiku cost is ~$5–7.

Both scripts: dry-run by default, `--apply` to write, `--limit N` to sample. They **only update existing records, never insert**, and dump a timestamped `data/practice_description_backup_*.json` before the first write.

**Deps:** Phase 2 needs `anthropic` + `trafilatura`, kept in `requirements-scripts.txt` (NOT `requirements.txt`, so Netlify builds stay lean). Install with `pip install -r requirements.txt -r requirements-scripts.txt`. Requires a valid `ANTHROPIC_API_KEY` in `.env` (scripts `load_dotenv(override=True)` and guard against empty shell-exported keys).

**Index gate** (in `generate_site.py`): a vet page is indexed only if `has_real_description AND quality_score >= VET_NOINDEX_THRESHOLD (7) AND has_differentiating_facts`. Listings below the gate are noindexed and their ads suppressed, deliberately shrinking the indexed surface to genuinely fact-rich pages (~56% indexed).

### After ANY Airtable data refresh

Re-run the remediation so new/changed listings get the same treatment, then rebuild:

```bash
source venv/bin/activate
python3 scripts/website_descriptions.py --limit 0          # dry run: check website/fallback split + cost
python3 scripts/website_descriptions.py --limit 0 --apply  # write (backs up first; Phase 1 is the built-in fallback)
DATA_SOURCE=airtable python3 generate_site.py              # rebuild and verify dist/ before deploy
```

(If a Search Console export later becomes available, add a protected-URLs grandfather step here so already-ranking pages can't be noindexed by a future gate change — not yet built.)

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

## Note

`AGENTS.md` is a near-identical mirror of this file for Codex. Keep the two in sync when editing shared guidance.
