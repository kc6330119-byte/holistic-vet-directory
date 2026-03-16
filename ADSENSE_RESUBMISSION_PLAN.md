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
- **Current count:** 15 published blog posts (~1,200 words each)
- **Target before resubmission:** 40-50 posts
- **Posts needed:** 25-35 more
- **Content ideas:**
  - [ ] More species-specific articles (birds, exotic pets, farm animals)
  - [ ] Condition-specific guides (arthritis, allergies, cancer support, anxiety)
  - [ ] "What to expect" guides for each modality (acupuncture session, chiropractic visit, etc.)
  - [ ] Regional guides ("Holistic Vet Care in the Pacific Northwest")
  - [ ] Interview/Q&A articles with responding holistic vets
  - [ ] Seasonal content (winter joint care, summer skin issues, holiday stress)
  - [ ] Nutrition deep-dives (raw feeding, supplements, food therapy)
  - [ ] "Holistic vs. conventional" comparison articles for common conditions
- **Goal:** Shift unique-to-templated ratio from 0.5% toward 1.5-2%

### Action 3: Validate Practice Listings
- **Status:** READY TO RUN
- **Script:** `scripts/validate_animal_practices.py`
- **Purpose:** Flag non-veterinary practices (human chiropractors, acupuncturists, etc.) that may have been included in the directory
- **Why it matters for AdSense:** Removing invalid listings improves content accuracy and reduces low-quality pages
- **Run command:** `python3 scripts/validate_animal_practices.py`
- **Output:** `data/validation_flagged.csv` — review and remove non-animal practices

### Action 4: Improve Auto-Generated Descriptions (Future)
- **Status:** NOT STARTED
- **Goal:** Rewrite the auto-description generator to produce more varied, longer, genuinely useful descriptions
- **Current pattern:** Formulaic sentence structure detectable as boilerplate
- **Target:** More natural language variation, 250+ words, unique angles per practice
- **Priority:** Lower — focus on Actions 1-3 first

---

## Resubmission Timeline

| Date | Action | Status |
|------|--------|--------|
| 2026-03-16 | Noindex thin city pages (code change) | DONE |
| 2026-03-16 | Deploy updated site to Netlify | TODO |
| 2026-03-16 | Run practice validation script | TODO |
| 2026-03-17+ | Remove flagged non-vet practices from Airtable | TODO |
| 2026-03-17+ | Begin writing additional blog content (aim for 2-3/week) | TODO |
| ~2026-04-06 | Google recrawl window (2-3 weeks after deploy) | WAIT |
| ~2026-04-06 | Verify noindexed pages are dropping from Google index | TODO |
| ~2026-04-20 | Target: reach 35+ blog posts | TODO |
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

---

## Pre-Resubmission Checklist

Before submitting to AdSense again, verify:

- [ ] Site deployed with noindex changes live
- [ ] Google Search Console shows noindexed pages being excluded (2-3 week lag)
- [ ] 35+ published blog posts with original, substantive content
- [ ] Non-veterinary practices removed from directory (validation script results)
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
