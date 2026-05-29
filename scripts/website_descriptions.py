#!/usr/bin/env python3
"""
website_descriptions.py — Phase 2 website-enrichment crawler.

Adds ORIGINAL, per-page value beyond each practice's Google Business Profile by
mining its OWN website. This is the part of the AdSense "Low Value Content"
remediation that genuinely differentiates pages; Phase 1
(generate_fact_descriptions.py) only restated structured data and is the
fallback layer here.

Pipeline (per listing):
  1. crawl    — fetch homepage + an about/services page, extract clean main text
                (trafilatura). Cached to disk so re-runs and tuning never refetch.
  2. compose  — Claude Haiku extracts distinguishing facts from the site text and
                writes an ORIGINAL 2-4 sentence description, grounded ONLY in those
                facts + structured data. It must NOT copy site prose verbatim
                (scraped/copyright problem) and must NOT invent facts. Returns
                sufficient=false for pure navigation/cookie/error/empty pages.
                Cached to disk so re-runs never re-bill.
  3. fallback — sites that are dead / JS-rendered / boilerplate fall back to the
                Phase 1 fact-grounded description (compose() from
                generate_fact_descriptions).
  4. gate+write — run the SAME build index gate and write Airtable
                  "Practice Description" (updates only, never inserts).

SAFETY: dry-run by default, small --limit (25) by default, crawl + LLM cached.
Nothing is written without --apply. JS-rendered sites (Wix/Squarespace/app
builders) return near-empty text and simply fall through to the Phase 1
fallback; a Playwright renderer is a documented future hook, not wired up.

Usage:
  python3 scripts/website_descriptions.py                 # dry run, first 25
  python3 scripts/website_descriptions.py --limit 200     # dry run, larger batch
  python3 scripts/website_descriptions.py --limit 200 --apply
  python3 scripts/website_descriptions.py --refresh       # ignore caches, refetch
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Reuse Phase 1's fallback composer, the build gate, and shared helpers so the
# two phases stay consistent (same field names, same index decision).
import generate_fact_descriptions as p1  # noqa: E402
from generate_fact_descriptions import (  # noqa: E402
    DESC_FIELD,
    GATE_FIELDS,
    compose as gbp_compose,
    project_index,
    require_env,
)
from generate_site import Veterinarian  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env", override=True)

CACHE_DIR = PROJECT_ROOT / "data" / "site_cache"
CRAWL_CACHE = CACHE_DIR / "crawl"
LLM_CACHE = CACHE_DIR / "llm"
for _d in (CRAWL_CACHE, LLM_CACHE):
    _d.mkdir(parents=True, exist_ok=True)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
UA = ("Mozilla/5.0 (compatible; HolisticVetDirectoryBot/1.0; "
      "+https://holisticvetdirectory.com/about)")
TIMEOUT = 8
MIN_SITE_TEXT = 250        # below this, treat the site as having no usable content
CRAWL_DELAY = 0.5          # politeness pause between requests to the same host

# Not the practice's own site — booking/social/aggregator/chain domains.
SOCIAL = (
    "facebook.", "m.facebook", "fb.com", "instagram.", "twitter.", "x.com",
    "tiktok.", "youtube.", "youtu.be", "linktr.ee", "linktree", "yelp.",
    "google.com", "sites.google", "business.site", "booksy.", "vagaro.",
    "petdesk.", "vetster.", "thrivepetcare.com", "vcahospitals.com",
    "banfield.com",
)

ABOUT_HINTS = ("about", "our-story", "who-we-are", "services", "philosophy",
               "approach", "integrative", "holistic")


# ── crawl stage ───────────────────────────────────────────────────────────────

_robots_cache: dict = {}


def _host(url: str) -> str:
    u = url if url.startswith("http") else "http://" + url
    h = urlparse(u).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def robots_allows(url: str) -> bool:
    """Best-effort robots.txt check, cached per host. Fails open on error."""
    try:
        parts = urlparse(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in _robots_cache:
            rp = robotparser.RobotFileParser()
            rp.set_url(urljoin(base, "/robots.txt"))
            try:
                rp.read()
            except Exception:
                rp = None
            _robots_cache[base] = rp
        rp = _robots_cache[base]
        return rp.can_fetch(UA, url) if rp else True
    except Exception:
        return True


def _fetch(url: str):
    if not url.startswith("http"):
        url = "https://" + url
    if not robots_allows(url):
        return None, "robots-disallow", None
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT,
                         allow_redirects=True)
        return r.status_code, r.text, r.url
    except Exception as e:
        return None, type(e).__name__, None


def _extract(html: str) -> str:
    if not html:
        return ""
    txt = trafilatura.extract(html, include_comments=False, include_tables=False,
                              favor_precision=True)
    return (txt or "").strip()


def _find_secondary(html: str, base_url: str, host: str) -> list[str]:
    """Return up to 2 same-host about/services URLs to deepen context."""
    found: list[str] = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            txt = (a.get_text() or "").strip().lower()
            href = a["href"].lower()
            if any(h in txt or h in href for h in ABOUT_HINTS):
                full = urljoin(base_url, a["href"])
                if _host(full) == host and full not in found:
                    found.append(full)
            if len(found) >= 2:
                break
    except Exception:
        pass
    return found


def crawl_site(url: str, use_cache: bool = True) -> dict:
    """Fetch homepage + up to 2 secondary pages, return cleaned combined text.

    JS-rendered sites (Wix/Squarespace/app builders) return near-empty text and
    are left to fall through to the Phase 1 fallback. A Playwright renderer is a
    documented future hook, intentionally not implemented.
    """
    host = _host(url)
    cache_path = CRAWL_CACHE / f"{hashlib.md5(url.encode()).hexdigest()}.json"
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text())

    result = {"url": url, "host": host, "text": "", "status": None}
    if not host or any(s in host for s in SOCIAL):
        result["status"] = "social/skip"
        cache_path.write_text(json.dumps(result))
        return result

    code, html, final = _fetch(url)
    result["status"] = code
    if isinstance(code, int) and code < 400 and html:
        parts = [_extract(html)]
        for sec in _find_secondary(html, final or url, host):
            time.sleep(CRAWL_DELAY)
            sc, sh, _ = _fetch(sec)
            if isinstance(sc, int) and sc < 400:
                parts.append(_extract(sh))
        result["text"] = "\n".join(p for p in parts if p).strip()
    cache_path.write_text(json.dumps(result))
    return result


# ── compose stage (Haiku) ───────────────────────────────────────────────────

_client = None


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(
            api_key=require_env("ANTHROPIC_API_KEY"), timeout=40.0)
    return _client


LLM_SYSTEM = (
    "You write factual directory descriptions for holistic and integrative "
    "veterinary practices. You are given raw text scraped from the practice's own "
    "website. Extract concrete, practice-specific facts: holistic/integrative "
    "modalities offered (acupuncture, Chinese herbal medicine, chiropractic, "
    "homeopathy, nutritional therapy, rehabilitation, etc.), species treated, the "
    "veterinarians' names and credentials, years of experience, the practice's "
    "stated philosophy or approach to integrative care, and any conditions they "
    "focus on. Then write an ORIGINAL 2-4 sentence description in your own words "
    "grounded ONLY in those facts plus the structured data provided. "
    "Rules: never copy sentences or distinctive phrases from the source text — "
    "paraphrase into your own words; never invent facts not present in the text or "
    "structured data; no filler words like 'nestled', 'boasting', 'dedicated team', "
    "'state-of-the-art', 'passionate'. Set sufficient=true whenever the text "
    "contains ANY concrete information about THIS practice (modalities, species, "
    "vets, approach, conditions, or experience). Only set sufficient=false when the "
    "text is purely navigation links, cookie/legal notices, an error page, or says "
    "nothing specific about this practice. Respond with strict JSON only."
)

LLM_SCHEMA_HINT = (
    'Return ONLY this JSON, nothing else: '
    '{"sufficient": true|false, '
    '"description": "the 2-4 sentence original description (empty string if not sufficient)"}'
)


def gbp_summary(f: dict) -> str:
    """Structured facts already known — given to the LLM to avoid contradiction."""
    bits = []
    specs = p1.normalize_specialties(f.get("Specialties"))
    species = p1.normalize_species(f.get("Species Treated"))
    personal, affil = p1.normalize_credentials(f.get("Certification Bodies"))
    if species:
        bits.append("species: " + ", ".join(species))
    if specs:
        bits.append("modalities: " + ", ".join(specs))
    if personal:
        bits.append("credentials: " + ", ".join(personal))
    if affil:
        bits.append("affiliations: " + ", ".join(affil))
    year = p1._parse_year(f.get("Year Established"))
    if year:
        bits.append(f"established: {year}")
    if f.get("Google Rating") and f.get("Google Reviews"):
        bits.append(f"{f['Google Rating']} stars / {f['Google Reviews']} Google reviews")
    return "; ".join(bits)


def llm_compose(name, city, state, summary, site_text, use_cache=True) -> dict:
    key = hashlib.md5(f"{name}|{city}|{state}|{site_text[:4000]}".encode()).hexdigest()
    cache_path = LLM_CACHE / f"{key}.json"
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text())

    user = (
        f"Practice: {name}\nLocation: {city}, {state}\n"
        f"Structured data (already known, do not contradict): {summary}\n\n"
        f"Website text (raw, may contain navigation/boilerplate):\n"
        f'"""\n{site_text[:6000]}\n"""\n\n{LLM_SCHEMA_HINT}'
    )
    try:
        msg = client().messages.create(
            model=HAIKU_MODEL,
            max_tokens=600,
            system=LLM_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
        data = json.loads(raw)
        data["_usage"] = {"in": msg.usage.input_tokens, "out": msg.usage.output_tokens}
    except Exception as e:
        data = {"sufficient": False, "description": "", "error": str(e)}
    cache_path.write_text(json.dumps(data))
    return data


# ── gate helper ───────────────────────────────────────────────────────────────

def desc_is_real(text: str) -> bool:
    """The build's text-quality gate on a candidate description, in isolation."""
    return Veterinarian(practice_name="x", practice_description=text).has_real_description


# ── orchestration ─────────────────────────────────────────────────────────────

def process_record(rec: dict, use_cache: bool) -> dict:
    f = rec["fields"]
    url = (f.get("Website") or "").strip()
    out = {
        "id": rec["id"], "name": f.get("Practice Name", ""),
        "source": "fallback", "description": "", "site_chars": 0,
        "in_tok": 0, "out_tok": 0,
    }

    crawl = crawl_site(url, use_cache=use_cache) if url else {"text": ""}
    site_text = crawl.get("text", "")
    out["site_chars"] = len(site_text)

    if len(site_text) >= MIN_SITE_TEXT:
        result = llm_compose(f.get("Practice Name", ""), f.get("City", ""),
                             f.get("State", ""), gbp_summary(f), site_text,
                             use_cache=use_cache)
        usage = result.get("_usage") or {}
        out["in_tok"], out["out_tok"] = usage.get("in", 0), usage.get("out", 0)
        desc = p1.fix_mojibake((result.get("description") or "").strip())
        if result.get("sufficient") and desc_is_real(desc):
            out["source"] = "website"
            out["description"] = desc

    if not out["description"]:
        out["description"] = gbp_compose(f)  # Phase 1 fact-grounded fallback

    out["indexed"], out["score"] = project_index(f, out["description"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25, help="number of listings (0 = all)")
    ap.add_argument("--apply", action="store_true", help="write Practice Description to Airtable")
    ap.add_argument("--refresh", action="store_true", help="ignore crawl/LLM caches")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    use_cache = not args.refresh

    api_key = require_env("AIRTABLE_API_KEY")
    base_id = require_env("AIRTABLE_BASE_ID")
    require_env("ANTHROPIC_API_KEY")  # fail fast before crawling if missing/empty
    table_name = (os.environ.get("AIRTABLE_TABLE_NAME") or "Veterinarians").strip()

    from pyairtable import Api
    table = Api(api_key).table(base_id, table_name)
    # Fetch DESC_FIELD too so the pre-write backup captures the current text.
    recs = table.all(fields=GATE_FIELDS + [DESC_FIELD])
    batch = recs if not args.limit else recs[: args.limit]
    print(f"Processing {len(batch)} of {len(recs)} listings "
          f"({'APPLY' if args.apply else 'DRY RUN'}, cache={'on' if use_cache else 'off'})...\n")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_record, r, use_cache): r for r in batch}
        for i, fut in enumerate(as_completed(futs), 1):
            results.append(fut.result())
            if i % 25 == 0:
                print(f"  ...{i}/{len(batch)}")

    src = Counter(r["source"] for r in results)
    n = len(results)
    web = [r for r in results if r["source"] == "website"]
    idx_count = sum(1 for r in results if r["indexed"])
    in_tok = sum(r["in_tok"] for r in results)
    out_tok = sum(r["out_tok"] for r in results)

    print("\n=== RESULTS ===")
    print(f"  website-derived (original): {src['website']} ({100*src['website']/n:.0f}%)")
    print(f"  Phase 1 fallback:           {src['fallback']} ({100*src['fallback']/n:.0f}%)")
    print(f"  PROJECTED INDEXED:          {idx_count} ({100*idx_count/n:.0f}%)  "
          f"noindexed: {n-idx_count} ({100*(n-idx_count)/n:.0f}%)")

    # Cost: count only LLM calls actually billed this run (cache hits report 0).
    billed = sum(1 for r in results if r["in_tok"] or r["out_tok"])
    # Haiku 4.5 list price ≈ $1.00 / MTok input, $5.00 / MTok output (verify current).
    est = in_tok / 1e6 * 1.00 + out_tok / 1e6 * 5.00
    print(f"\n=== LLM USAGE (this run, uncached calls only) ===")
    print(f"  billed calls: {billed}   in_tokens: {in_tok:,}   out_tokens: {out_tok:,}")
    print(f"  est. cost this run: ${est:.2f}  (assumed Haiku $1/$5 per MTok — verify)")
    if billed and len(batch) < len(recs):
        per = est / billed
        print(f"  ~${per:.4f}/billed-call -> rough full-corpus ({len(recs)}) ceiling: "
              f"${per*len(recs):.2f} (only listings with usable site text get billed)")

    print("\n=== SAMPLE WEBSITE-DERIVED DESCRIPTIONS ===")
    for r in web[:8]:
        tag = "INDEX" if r["indexed"] else "noindex"
        print(f"\n[{r['name']}] (site {r['site_chars']} chars | q{r['score']} | {tag})\n{r['description']}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to write Airtable.")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = PROJECT_ROOT / "data" / f"practice_description_backup_{stamp}.json"
    by_id = {r["id"]: r for r in batch}
    backup = {r["id"]: (by_id[r["id"]]["fields"].get(DESC_FIELD, "") or "") for r in results}
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nBacked up {len(backup)} current descriptions to {backup_path.relative_to(PROJECT_ROOT)}")

    updates = [{"id": r["id"], "fields": {DESC_FIELD: r["description"]}}
               for r in results if r["description"]]
    print(f"--apply: updating {len(updates)} existing records (no inserts)...")
    for i in range(0, len(updates), 10):
        table.batch_update(updates[i:i + 10])
        print(f"  updated {min(i + 10, len(updates))}/{len(updates)}")
    print("Done.")


if __name__ == "__main__":
    main()
