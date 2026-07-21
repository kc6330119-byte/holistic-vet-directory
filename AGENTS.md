# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

**CSV files in `data/` are the source of truth** (`DATA_SOURCE=csv`, the default, also pinned in `netlify.toml [build.environment]`). Airtable was retired as the build source on 2026-07-20 (paid plan dropped; Veterinarians table data deleted). The Airtable code path (`DATA_SOURCE=airtable`) still exists but must not be used — the table is empty and a build against it would generate an empty site.

Key CSV files in `data/` (all committed — Netlify builds from them):
- `veterinarians.csv` — main directory listings, 3,226 records exported from the Airtable API at full precision, **including every remediated Practice Description** (pipe-delimited multi-select fields; row order preserved from Airtable and load-bearing for "first N" listing widgets — append new rows, don't re-sort)
- `blog_posts.csv` — all 40 blog posts (consolidated authorship, Published Date, Featured flag, empty Reviewer fields), sorted date-desc; takes priority over the stale `content/blog/*.md` markdown fallback
- `specialties.csv` — specialty reference data (was already CSV-authoritative in both modes)
- `states.csv` — US states with regions

The CSV→build path was verified byte-identical to the final Airtable build (5,276/5,277 files; the one diff is the search-index zip field serialized as string vs number, which renders identically). CSV readers use `utf-8-sig` so BOM-prefixed exports (Airtable/Excel) load correctly. A raw Airtable grid export plus the API-derived CSVs and timestamped description backups exist locally (gitignored) as belt-and-braces.

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

## Listing Description Remediation

Listing descriptions are remediated for Google's "scaled content abuse" / AdSense "Low Value Content" signal. The old hash-seeded spintax generator was removed from the build (`generate_site.Veterinarian` now only classifies descriptions for the index gate; it does not synthesize copy). Descriptions are written to Airtable offline by two scripts, in order:

1. `scripts/generate_fact_descriptions.py` — **Phase 1, fallback layer.** Composes each description from ONLY-TRUE Airtable facts (specialties, species, credentials, year, Google rating). Variation comes from real differing facts, never synonym shuffling. No length padding — sub-gate descriptions stay short and get noindexed on purpose.
2. `scripts/website_descriptions.py` — **Phase 2, primary value layer.** Crawls each practice's own website (homepage + an about/services page, trafilatura extraction), has Claude Haiku write an ORIGINAL fact-grounded description, and **falls back to the Phase 1 composer** when a site is dead/JS-rendered/boilerplate. Caches every crawl and LLM response under `data/site_cache/`. Never copies site prose verbatim; never invents facts. ~76% of listings yield website-derived copy; full-corpus Haiku cost is ~$5–7.

**Thin-fallback set & the cheap win (not Playwright):** of the ~24% that fall back to Phase 1, only ~85 sites are *responded-but-thin* (the rest are dead domains, social-only, or LLM-judged-insufficient). Most of those 85 are stale-cache false-thins (a plain `--refresh` re-crawl already extracts 1,000+ chars) or dead/expired sites; the remainder are template-builder homepages that `trafilatura(favor_precision=True)` in `_extract` throws away. A `favor_recall` fallback in `_extract` (when precision yields < `MIN_SITE_TEXT`) would rescue those **without a headless browser**. Playwright/JS rendering was tested and does NOT help here — the content is already in the plain HTML, so the bottleneck is the extractor, not rendering. Low priority; fold into the next data refresh.

Both scripts: dry-run by default, `--apply` to write, `--limit N` to sample. They **only update existing records, never insert**, and dump a timestamped `data/practice_description_backup_*.json` before the first write.

**Deps:** Phase 2 needs `anthropic` + `trafilatura`, kept in `requirements-scripts.txt` (NOT `requirements.txt`, so Netlify builds stay lean). Install with `pip install -r requirements.txt -r requirements-scripts.txt`. Requires a valid `ANTHROPIC_API_KEY` in `.env` (scripts `load_dotenv(override=True)` and guard against empty shell-exported keys).

**Index gate** (in `generate_site.py`): a vet page is indexed only if `has_real_description AND quality_score >= VET_NOINDEX_THRESHOLD (7) AND has_differentiating_facts` (protected URLs short-circuit to indexed before the gate runs). One extra rule guards the Phase-1 fallback: a description that still leads with the fact-template opening (`is_gbp_restatement`) restates the Google Business Profile and adds no original prose, so it indexes only when its facts are *strongly* differentiating (`has_strong_differentiating_facts` — 2+ distinct modalities or a recognized holistic credential), not a single specialty + year established alone. Website-derived (original) copy is unaffected; only the pure GBP-restatements (~21 pages) drop out. Listings below the gate are noindexed and their ads suppressed, deliberately shrinking the indexed surface to genuinely fact-rich pages (~56%, ~1,807 of 3,226 indexed). The same logic is mirrored in `scripts/generate_fact_descriptions.project_index` so offline dry-runs match the build.

**Protected URLs (grandfather list)**: `data/protected_urls.txt` lists URL paths that stay indexable regardless of the gate, so pages with proven Search traction can't be deindexed by a future gate change. It is seeded from a Google Search Console export (paths with clicks>=1 OR impressions>=10). At build time `generate_site.py` loads it: `_is_indexable_vet` ORs in protection (covers vet page noindex + sitemap + counts), `_render_and_write` flips `noindex` off for any other protected page type (city/state/specialty/guide), and protected paths are force-added to the sitemap. To refresh: re-export GSC Pages and regenerate the file (one path per line; `#` comments and blank lines ignored). Edit by hand to add/remove protections.

**Blog footprint & reactivation plan**: only the 3 slugs in `SiteGenerator.INDEXABLE_BLOG_SLUGS` (founder story + two practical how-tos) appear on `/blog/`, are indexed, and are in the sitemap. The other 37 posts still build at their URLs but are `noindex`, ad-free, off the listing, and out of the sitemap — *parked, not deleted*, to keep the AdSense review surface tight (the 37 are unreviewed AI-written YMYL content). 3 strong posts is intentional and is NOT a low-value signal — a directory's value is its listings, and fewer good pages beats many weak ones. **Follow-up, only after AdSense approval:** reactivate in waves, not all at once. Triage the 37 by risk:
- *Lower-risk (logistics/definitional — candidates to re-index sooner):* the `what-to-expect-*` set, `first-holistic-vet-visit-what-to-expect`, `holistic-vs-conventional-when-to-consider-integrative-care`, `when-to-consider-a-holistic-vet-for-your-pet`, `naturopathic-vs-holistic-vet-differences`, `what-is-holistic-veterinary-medicine`, `understanding-tcvm-*`, `holistic-vet-dog-allergies-how-to-find`, `pet-insurance-holistic-vet-coverage-2025`, `managing-rising-veterinary-costs-insurance-nutrition`.
- *Higher-risk (condition/treatment/diagnosis medical advice — HOLD until a real DVM reviews them and the `Reviewer` field is set):* the allergy/arthritis/anxiety/fungal/valley-fever/vitamin-A/symptoms/remedies/herbal-safety/homeopathy/chiropractic/acupuncture-benefits posts.

(Slug-based first pass; confirm by reading each post before re-indexing. To reactivate one: add its slug to `INDEXABLE_BLOG_SLUGS` — that re-lists it, indexes it, and adds it to the sitemap in one step.)

### Remediation status (verified 2026-05-29, live on Netlify)

The description pipeline and index gate are deployed. Current verified state:
- **Indexed surface:** ~1,807 of 3,226 vet pages indexed (~56%); the rest are noindexed and ad-free.
- **Description provenance:** ~76% of listings carry original, website-derived Haiku copy; ~24% use the Phase 1 fact composer (the fallback).
- **Latest gate change (commit `29fe6a3`):** pure GBP-restatement listings (Phase 1 template + single specialty + year only, non-protected) now noindex — net −21 pages vs. the prior gate. See **Index gate** above.
- **Playwright evaluated and rejected:** JS rendering does not help the thin fallback set — the content is already in the plain HTML, so the bottleneck is `trafilatura` precision extraction, not rendering. The deferred cheap win is a `favor_recall` fallback in `_extract`. See **Thin-fallback set** above.

Open items: confirm GSC → Manual Actions is clean; after AdSense approval, reactivate the 37 parked blog posts in waves; set a blog `Reviewer` only once a real DVM reviews the content; re-check `data/protected_urls.txt` against a fresh GSC export on the next data refresh.

### Updating listing data (post-Airtable)

Listing data now lives in `data/veterinarians.csv` — edit it directly (or append rows) and rebuild with `python generate_site.py`. Notes:

- **The remediated descriptions exist ONLY in this CSV** (and the local gitignored backups). Do not regenerate or overwrite the `Practice Description` column wholesale.
- The description scripts (`generate_fact_descriptions.py`, `website_descriptions.py`) still read/write **Airtable** and are inoperable against the emptied table. If a batch of new listings ever needs descriptions, the scripts' compose/crawl logic is reusable but their I/O must be repointed at the CSV first.
- New rows: append at the end (row order feeds "first N" widgets), give each a unique `Slug`, and leave `Practice Description` empty rather than pasting website text — an empty description simply noindexes the page via the gate.
- After any data change, re-check the protected-URLs grandfather list (`data/protected_urls.txt`) against a fresh GSC export so newly-ranking pages keep their protection.

## Authorship & Medical Review (E-E-A-T)

YMYL site, so authorship/review signals matter. Two pieces, both in `generate_site.py`:

- **Author registry** — `SiteGenerator.AUTHORS` (keyed by `author_slug`). Each entry renders an `/author/{slug}/` page (`templates/author.html`, ProfilePage + Person schema). Blog bylines link to the author page and inject `author.url` into BlogPosting schema **only when** the post's `author_slug` is in `AUTHORS`, so legacy/unknown author names never make a 404 link. **Only add real people** — fabricated authors are a trust risk in manual review. Blog posts currently all credit "Kevin Collins" (Founder & Editor, not a vet).
- **Medical reviewer hook** — `BlogPost.reviewer` / `reviewer_credentials` (read from the `Reviewer` / `Reviewer Credentials` Airtable/CSV/markdown fields, default empty). When set, `blog_detail.html` renders a visible "Medically reviewed by …" line and a `reviewedBy` Person in the schema. Left empty until a **real licensed DVM** reviews the content — do not populate with a placeholder.

## Deployment

Hosted on Netlify. Push to `main` triggers automatic deploy. Config in `netlify.toml` includes redirects (including 301s for fixed blog slug typos), security headers, and cache rules. The `dist/` directory is gitignored.

**Bot/scraper geo-fence:** `netlify/edge-functions/geo-guard.ts` (Netlify Edge Function, runs on `/*` except `/static/*`) returns 403 to traffic from datacenter regions listed in its `BLOCKED_COUNTRIES` set — currently `SG` only, after GA showed a Singapore scraper was ~75% of all "users" (~1 hit per listing page, direct/no-referrer). Legitimate search crawlers (Googlebot/Bingbot/DuckDuckBot/Applebot/etc., matched by user-agent) are always allowed through so indexing is never harmed, and the function fails open when `context.geo` is absent (local dev). Edit `BLOCKED_COUNTRIES` to add/remove regions; blocks are logged to the Netlify edge-function logs. For heavier abuse, the more robust option is Cloudflare in front (managed bot challenges), which needs a DNS change.

## SEO Considerations

This is an AdSense-monetized directory site. SEO is critical:
- Every page needs unique title tags and meta descriptions
- Schema.org markup (LocalBusiness, Veterinarian) on detail pages
- XML sitemap generated automatically
- `sitemap.xml` has `X-Robots-Tag: noindex` header (Netlify config)
- Blog content targets long-tail holistic vet keywords

## Project Requirements

Full PRD with Airtable schema, design specs, AdSense placement strategy, and content guidelines is in the original AGENTS.md git history (commit before this change). Key points:
- Color palette: forest green (#2D6A4F) primary, sage (#52B788) secondary, warm orange (#F4A261) accent
- Mobile-first, accessible design (WCAG 2.1 AA)
- AdSense placements: header leaderboard, sticky sidebar, in-feed between listings, footer
- Target: holistic/integrative vet directory for US pet owners
