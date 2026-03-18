# Google AdSense Resubmission Plan

## Rejection History

| Submission | Date | Result | Reason |
|------------|------|--------|--------|
| 1st | ~Feb 2026 | Rejected | Low value content |
| 2nd | ~Mar 2026 | Rejected | Low value content — thin content, doorway pages |

## Root Cause Analysis

Google flagged the site for **"Low value content"** citing:
- Thin content with little or no added value
- Doorway pages
- Scraped/templated content

### What Google Was Seeing

| Metric | Count | Problem |
|--------|-------|---------|
| Total indexed pages | ~5,364 | — |
| City pages with 1-2 vets | 1,742 (32%) | **Doorway pages** — templated, minimal unique content |
| Auto-generated vet descriptions | 415 (12.6%) | Formulaic, detectable as boilerplate |
| Original editorial content (blog) | 15 posts | Too few to offset 5,300+ templated pages |
| Unique-to-templated content ratio | 0.5% to 99.5% | Far too low |

### Why City Pages Were the Core Problem

A city page with 1 vet contained:
- ~50 words of unique template text
- 1 vet card with ~150-word auto-generated description
- ~200 words of identical sidebar/navigation boilerplate

Google classifies these as **doorway pages** — pages created primarily for search rankings, not user value.

---

## Remediation Actions

### Action 1: Noindex Thin City Pages
- **Status:** COMPLETED (2026-03-16)
- **Change:** Added `<meta name="robots" content="noindex, follow">` to city pages with fewer than 3 vets
- **Files modified:**
  - `templates/base.html` — conditional noindex meta tag (line 10)
  - `generate_site.py` — passes `noindex=True` for cities with < 3 vets (line 849)
- **Impact:** ~1,742 doorway pages removed from Google's index
- **Note:** Pages still exist for site navigation; `follow` directive ensures linked vet detail pages are still crawled
- **Deploy needed:** Yes — rebuild and push to Netlify

### Action 2: Increase Original Blog Content
- **Status:** IN PROGRESS
- **Status:** COMPLETED (2026-03-17) — TARGET REACHED
- **Current count:** 40 published blog posts (up from 15 at rejection — 167% increase)
- **Added 2026-03-16 ("What to Expect" series — 5 articles, 12,032 words):**
  - [x] What to Expect at Your Pet's First Acupuncture Session (2,181 words)
  - [x] What to Expect at a Veterinary Chiropractic Appointment (2,571 words)
  - [x] What to Expect from Veterinary Herbal Medicine (2,307 words)
  - [x] Your Pet's First TCVM Consultation: What to Know (2,293 words)
  - [x] What to Expect from Veterinary Laser Therapy (2,680 words)
- **Added 2026-03-17 (6 articles, 15,718 words):**
  - [x] What to Expect from Veterinary Homeopathy (2,417 words)
  - [x] What to Expect from Veterinary Massage Therapy (2,176 words)
  - [x] What to Expect from Veterinary Nutritional Therapy (2,227 words)
  - [x] Holistic Approaches to Dog Arthritis: A Complete Guide (2,154 words)
  - [x] Holistic Approaches to Pet Anxiety (2,770 words) — replaced redundant allergy article
  - [x] Holistic vs. Conventional: When to Consider Integrative Care (1,886 words)
- **Note:** Original #39 (pet allergies) was scrapped — 7 allergy articles already existed. Replaced with pet anxiety article.
- **Total new content:** 25 blog posts, ~27,750 words of original content added since rejection
- **Future content ideas (post-approval):**
  - [ ] More species-specific articles (birds, exotic pets, farm animals)
  - [ ] Condition-specific guides (cancer support, digestive/gut health, senior wellness)
  - [ ] Regional guides ("Holistic Vet Care in the Pacific Northwest")
  - [ ] Interview/Q&A articles with responding holistic vets
  - [ ] Seasonal content (winter joint care, summer skin issues, holiday stress)

### Action 3: Validate Practice Listings
- **Status:** COMPLETED (2026-03-14)
- **Script:** `scripts/validate_animal_practices.py`
- **Results:**
  - LIKELY HUMAN: 60
  - REVIEW NEEDED: 21
  - NO WEBSITE: 2
  - LIKELY ANIMAL: 3,211
- **Action taken:** Removed 71 non-veterinary practices (human chiropractors, acupuncturists, etc.)
- **Directory count:** 3,294 → 3,223 active listings

### Action 4: Improve Auto-Generated Descriptions
- **Status:** COMPLETED (2026-03-16)
- **Change:** Rewrote `_generate_auto_description()` in `generate_site.py` with deterministic template variation
- **How it works:** Uses MD5 hash of each vet's slug to select from multiple sentence patterns, so descriptions read naturally and vary across practices but rebuild identically every time
- **Improvements over original:**
  - 6 opening sentence variations (was 1 fixed pattern)
  - Rich specialty descriptions explaining what each modality does and treats (14 specialties covered)
  - Varied phrasing for species, certifications, telehealth, and years in practice
  - Google rating data woven into descriptions when available
  - 4 closing sentence variations
  - Target 150-250 words (was ~100 words)
- **Scope:** Applies to 415 vets with thin/empty Airtable descriptions (< 150 chars). Existing good descriptions remain untouched.

### Action 5: Add Interactive Map to State Pages
- **Status:** COMPLETED (2026-03-16)
- **Change:** Added an interactive Leaflet/OpenStreetMap map to the sidebar of every state listing page
- **File modified:** `templates/state_list.html`
- **Features:**
  - All vet locations displayed as custom green pins
  - Marker clustering for states with many listings (prevents clutter)
  - Click a pin → popup with practice name (linked to detail page), city, and star rating
  - Map auto-zooms to fit all vets in the state
  - Scroll-wheel zoom disabled to prevent accidental scrolling
- **Cost:** Zero — Leaflet + OpenStreetMap is completely free
- **Impact:** Adds unique, interactive content to every state page; improves user engagement and time on page

### Action 6: Add Google Ratings to Vet Pages
- **Status:** COMPLETED (2026-03-16)
- **Script:** `scripts/fetch_google_ratings.py`
- **Results:**
  - 3,157 vets found with ratings (98%)
  - 3,127 HIGH confidence matches pushed to Airtable
  - 30 MEDIUM confidence records excluded (address mismatches)
  - 0 LOW confidence matches
- **Site changes:**
  - `templates/vet_detail.html` — star rating display in sidebar + Google Maps link
  - `templates/vet_detail.html` — AggregateRating schema markup (enables star snippets in Google search results)
  - `generate_site.py` — Veterinarian dataclass reads Google Rating, Google Reviews, Google Place ID, Google Maps URL fields
  - `scripts/airtable_loader.py` — VeterinarianData dataclass reads Google fields from Airtable API
- **Airtable fields added:** Google Rating (number), Google Reviews (number), Google Place ID (text), Google Maps URL (URL)
- **Cost:** ~$81, covered by Google Maps Platform $200/month free credit
- **Maintenance:** Re-run monthly to refresh ratings (Google requires data not be cached beyond 30 days)
- **Update (2026-03-16):** Added star rating and review count to vet cards (`templates/partials/vet_card.html`) — now visible on homepage Featured/Recently Added cards and all listing pages (state, city, specialty)

---

## Resubmission Timeline

| Date | Action | Status |
|------|--------|--------|
| 2026-03-16 | Noindex thin city pages (code change) | DONE |
| 2026-03-16 | Deploy site with noindex changes | DONE |
| 2026-03-14 | Run practice validation script | DONE |
| 2026-03-14 | Removed 71 non-vet practices from Airtable | DONE |
| 2026-03-16 | Fetch Google ratings for 3,223 vets (3,127 pushed to Airtable) | DONE |
| 2026-03-16 | Rewrite auto-description generator (415 thin descriptions) | DONE |
| 2026-03-16 | Add Google rating display + AggregateRating schema to vet pages | DONE |
| 2026-03-16 | Deploy site with ratings + descriptions | DONE |
| 2026-03-16 | Write 5 "What to Expect" blog articles (12,032 words) | DONE |
| 2026-03-16 | Add interactive map to all state pages (Leaflet/OSM) | DONE |
| 2026-03-16 | Deploy all changes (ratings, descriptions, map, blog posts) | DONE |
| 2026-03-17 | Write 6 more blog articles (15,718 words) | DONE |
| 2026-03-17 | All 40 blog posts published — target reached | DONE |
| 2026-03-17 | Fixed 3 blog slug typos + added 301 redirects in netlify.toml | DONE |
| 2026-03-17 | Analyzed Google Search Console data (Pages + Queries reports) | DONE |
| 2026-03-17 | Optimized title tags and meta descriptions for homepage, /vets/, and search page | DONE |
| 2026-03-17 | Top-rated practitioners added to specialty cards on /specialties/ page | DONE |
| 2026-03-17 | Updated About page "How to Use" section with maps, ratings, and blog guides | DONE |
| 2026-03-17 | Deploy all changes | DONE |
| ~2026-04-06 | Export fresh Search Console reports (Pages + Queries) to compare against baseline | TODO |
| ~2026-04-06 | Google recrawl window (2-3 weeks after deploy) | WAIT |
| ~2026-04-06 | Verify noindexed pages are dropping from Google index | TODO |
| ~2026-04-27 | **Resubmit to AdSense** (6 weeks after deploy) | TODO |

## How to Check Progress

### Verify Noindex is Working
1. Google Search Console → Coverage/Indexing report
2. Look for "Excluded by 'noindex' tag" count increasing
3. Search `site:holisticvetdirectory.com` in Google — total results should decrease over 2-3 weeks

### Track Blog Content
- Current blog count: check `content/blog/` directory
- Target: 40-50 posts before resubmission

### Monitor Search Console
- Watch for "Indexed, not submitted in sitemap" count decreasing
- Watch average position and impressions trends
- Ensure core vet detail pages and state pages remain indexed

### Compare Search Console Reports (~April 6)
- Export fresh Pages and Queries reports from Search Console
- Compare against March 8-14 baseline (saved in `data/Pages.csv` and `data/Queries.csv`)
- Key metrics to compare:
  - Total impressions and clicks (should increase)
  - Average position for "holistic vet" queries (should improve)
  - CTR on page 1 results (should improve with new titles/descriptions)
  - Number of pages with impressions (should decrease as noindexed pages drop)
  - Blog post visibility (new articles should begin appearing)

---

## Pre-Resubmission Checklist

Before submitting to AdSense again, verify:

- [x] Site deployed with noindex changes live
- [x] Google ratings added to 3,127 vet pages with AggregateRating schema
- [x] Star ratings added to vet cards on homepage and listing pages
- [x] Auto-description generator rewritten with varied, richer content
- [x] Non-veterinary practices removed from directory (71 removed)
- [x] Interactive map added to all state pages
- [x] 5 "What to Expect" blog articles published (12,032 words)
- [x] Deploy site with all changes
- [x] Fixed 3 blog slug typos with 301 redirects
- [x] Optimized homepage, /vets/, and search page title tags and meta descriptions
- [x] Top-rated practitioners added to specialty cards
- [x] About page updated with new feature descriptions
- [ ] Export fresh Search Console reports (Pages + Queries) ~April 6 to compare against March 8-14 baseline
- [ ] Google Search Console shows noindexed pages being excluded (2-3 week lag)
- [x] 40 published blog posts with original, substantive content
- [ ] Site loads fast (< 3 seconds, Lighthouse score > 90)
- [ ] No broken links or 404 errors
- [ ] Mobile-friendly test passes
- [ ] All pages have unique meta descriptions (no duplicates on indexed pages)
- [ ] Schema markup validates (test with Google Rich Results Test)
- [ ] Privacy Policy and Terms pages are present and linked

---

## Notes

- **Do NOT resubmit early.** Google needs time to recrawl and drop noindexed pages. Resubmitting before the index cleans up will likely result in another rejection.
- **Quality over quantity for blog posts.** Each post should be 1,000+ words of genuinely useful, original content. Google can detect filler.
- **Dogs Naturally Magazine pitch** submitted (2026-03-16) — if accepted, the backlink from a 2M-visitor/month site would significantly boost domain authority before resubmission.
- AdSense reviewers look at the site holistically. The combination of fewer indexed pages + more original content + cleaner listings will present a much stronger case.
- **Blog content strategy going forward:** 40 posts is sufficient for AdSense resubmission. Hold off on writing more until the April Search Console data reveals which queries are gaining traction — then write targeted articles based on actual performance data rather than guessing. Exception: if a vet offers a guest article or interview, publish it immediately — third-party content is high-value for credibility.

---

## Progress Summary (2026-03-16)

**Completed in one day:**
- 7 major site improvements implemented and deployed
- 71 non-veterinary practices removed from directory
- 3,127 Google ratings added to vet pages and cards
- 415 auto-generated descriptions rewritten with varied, natural language
- 1,742 thin city pages noindexed
- Interactive maps added to all 53 state pages
- 5 original blog articles written (12,032 words)
- Blog count: 15 → 40 (167% increase) — TARGET REACHED
- Total new content: 25 blog posts, ~27,750 words of original content since rejection
- Redundant allergy article caught and replaced with pet anxiety article

**Additional improvements (2026-03-17):**
- 3 blog slug typos fixed (missing first letters) with 301 redirects preserving SEO value
- Google Search Console baseline established (March 8-14 data: Pages + Queries reports)
- Homepage, /vets/, and search page title tags and meta descriptions optimized based on actual query data
- Top-rated practitioners (4.7+ stars) added to specialty cards on /specialties/ page
- About page "How to Use This Directory" section updated with maps, Google ratings, and blog guide links
- Key finding: directory-intent queries already on page 1 (position 3-4.5); high-volume "near me" queries at positions 45-62 with room to improve

---

## Post-Approval Features (or If Rejected in April)

### User Review System
- **Status:** PLANNED
- **Priority:** Build after AdSense approval, OR as a contingency if rejected again in April
- **Concept:** Allow pet owners to submit reviews for listed veterinarians
- **Implementation approach (fits existing infrastructure):**
  - New "Reviews" table in Airtable (fields: Practice Name/Slug, Reviewer Name, Rating, Review Text, Date, Status)
  - Netlify Forms or free form service to capture submissions (no backend needed)
  - Manual moderation in Airtable (set Status to "Approved" before reviews go live)
  - `generate_site.py` picks up approved reviews during site rebuild
  - Homepage carousel displaying latest approved reviews
  - Individual reviews displayed on vet detail pages
- **Why it helps SEO:** User-generated content is unique, original content that Google values highly — no other site has these reviews
- **Why wait:** Need a critical mass of 10-15 reviews before it adds value; an empty or sparse carousel hurts more than it helps
- **Seeding strategy:** Ask vets who responded positively to outreach to encourage their clients to leave reviews
