# AdSense Final Polish — 2026-05-06

Polish pass on top of the five-fix AdSense remediation. Triggered by SPL
rejection earlier today and a code-review pass that surfaced three
reviewer-visible defects on HVD that mirror SPL findings.

## What was verified (before fix)

| Finding | Verification | Result |
|---|---|---|
| OG image 404 | `curl -sI https://holisticvetdirectory.com/static/images/og-image.png` | HTTP/2 404 |
| Favicon 404 | `curl -sI https://holisticvetdirectory.com/favicon.ico` | HTTP/2 404 |
| favicon.svg 404 | `curl -sI .../static/images/favicon.svg` | HTTP/2 404 |
| favicon.png 404 | `curl -sI .../static/images/favicon.png` | HTTP/2 404 |
| AggregateRating schema | `grep -rn "[Aa]ggregateRating" templates/` | `templates/vet_detail.html:32-39` confirmed |

The `static/images/` directory did not exist in the repo. `templates/base.html`
references `og-image.png`, `favicon.svg`, and `favicon.png` from that path —
all four of those URLs were 404 on live.

## What was fixed

### 1. Brand assets (new files)

- `static/images/og-image.png` — 1200×630 social card, forest green
  background, white wordmark "Holistic Vet Directory" + tagline + domain.
- `static/images/favicon.png` — 192×192 PNG with rounded forest-green tile
  + white paw mark.
- `static/images/favicon.svg` — vector favicon, same paw mark.
- `static/favicon.ico` — multi-size ICO (16/32/48) shipped to site root via
  the static-asset copy step (next item).
- `scripts/generate_brand_assets.py` — reproducible generator. Re-run any
  time the brand mark changes.

### 2. Ship favicon.ico to dist root — `generate_site.py:2474-2484`

Added a special-case copy step alongside `ads.txt` and `llms.txt`:

```python
favicon_ico_src = static_src / 'favicon.ico'
if favicon_ico_src.exists():
    shutil.copy(favicon_ico_src, self.output_dir / 'favicon.ico')
```

Also added `<link rel="shortcut icon" href="/favicon.ico">` to
`templates/base.html` so all three favicon variants are linked.

### 3. AggregateRating schema removed — `templates/vet_detail.html`

**Before** (lines 32-39):

```jinja
{% if vet.google_rating and vet.google_reviews %}
"aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "{{ vet.google_rating }}",
    "reviewCount": "{{ vet.google_reviews }}",
    "bestRating": "5"
},
{% endif %}
```

**After:** removed entirely.

The on-page rating display (around line 292) was left unchanged — it shows
"Based on X Google reviews" which is honest about source. The schema-level
claim was first-party-typed (`AggregateRating` without source attribution),
which violates Google's structured-data guidelines for ratings sourced
from third parties.

`grep -rn "[Aa]ggregateRating" templates/ generate_site.py` returns zero
matches after the change. `grep -rln "AggregateRating" dist/` after rebuild
also returns zero matches.

## What was deployed

Single commit pushed to `main`:

```
8a0d93a Fix AdSense reviewer-visible defects: missing OG image, favicon,
        third-party AggregateRating schema
```

Files changed:
- `static/favicon.ico` (new)
- `static/images/og-image.png` (new)
- `static/images/favicon.png` (new)
- `static/images/favicon.svg` (new)
- `scripts/generate_brand_assets.py` (new)
- `generate_site.py` (+6 lines: favicon.ico copy step)
- `templates/base.html` (+1 line: shortcut icon link)
- `templates/vet_detail.html` (-8 lines: AggregateRating block)

## Live verification (post-deploy)

| URL | Status |
|---|---|
| `/favicon.ico` | HTTP/2 200 ✅ |
| `/static/images/og-image.png` | HTTP/2 200 ✅ |
| `/static/images/favicon.svg` | HTTP/2 200 ✅ |
| `/static/images/favicon.png` | HTTP/2 200 ✅ |

Sample live vet page (`/vet/integrative-veterinary-health-center/`):
- LocalBusiness JSON-LD parses cleanly with `@type = ['Veterinarian', 'LocalBusiness']`
- `aggregateRating` key absent
- All other LocalBusiness fields intact (`@context`, `address`, `description`,
  `email`, `geo`, `medicalSpecialty`, `name`, `priceRange`, `telephone`, `url`)
- On-page "Google Rating" sidebar still renders

## Optional sample audit — 30 random live vet pages

Pulled 30 random vet detail URLs from the live sitemap and fetched each.

| Check | Count |
|---|---|
| Pages with `AggregateRating` (post-fix regression) | 0 / 30 ✅ |
| Pages with "Frequently Asked Questions" (prior remediation holds) | 0 / 30 ✅ |
| Pages with "Last Verified" (prior remediation holds) | 0 / 30 ✅ |
| Pages with "About Our Specialties" (prior remediation holds) | 0 / 30 ✅ |
| Pages with `noindex` meta tag (quality gate working) | 1 / 30 |
| Pages with visible Google Rating sidebar | 30 / 30 |

No regressions surfaced. The single noindexed page is consistent with the
quality gate raised in commit `b32557f`.

Off-topic listing risk (the SPL pattern of parking lots / restaurants
shipped through a permissive validator) was not audited in depth — HVD's
listing pipeline runs through `scripts/validate_animal_practices.py` which
has materially stricter validation than SPL's `is_thin_pad`. URL slugs in
the sample looked appropriate (animal hospitals, holistic clinics, mobile
vets). No further action recommended.

## Resubmission gate

- [x] OG image returns 200 on live site
- [x] Favicon returns 200 on live site
- [x] No `AggregateRating` JSON-LD anywhere in `dist/`
- [x] On-page rating display still renders
- [x] LocalBusiness JSON-LD parses cleanly with no removed-schema artifacts
- [x] All five original remediation commits still in place
  (`fe800dd`, `4117ab4`, `b32557f`, `03f8da8`, plus the earlier ones)

Gate is green. Ready for AdSense "Request review" when the GSC indexing
metrics described in the prior session also stabilize (target: 5/4–5/7
based on indexed-count plateau and "Excluded by 'noindex' tag" growing
by 400+).
