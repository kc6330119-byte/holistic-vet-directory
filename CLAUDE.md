# Holistic Veterinary Directory Site - Project Requirements

## Project Overview

### Purpose
Build a directory website for veterinarians who provide holistic/integrative medicine practices to treat animals. The site will generate revenue through Google AdSense placement.

### Target Audience
- Pet owners seeking alternative/complementary veterinary care
- People with pets having chronic health issues
- Natural/organic lifestyle consumers with pets
- Those interested in acupuncture, herbal medicine, chiropractic care, nutrition therapy, etc. for their animals

### Revenue Model
- Primary: Google AdSense (contextual ads on listing pages, search results, detail pages)
- Future: Featured listings for veterinarians, affiliate links to natural pet products

### Success Metrics
- High-quality directory of holistic veterinarians across the US
- Mobile-friendly, fast-loading pages
- Good SEO for searches like "holistic vet near me," "integrative veterinarian [city]"
- Strategic ad placement for optimal revenue without harming UX

### Reference Site
The technical architecture should follow patterns from: https://smart-investor-financial-tools.com
- Static site generation using Python
- Airtable as CMS/database
- Netlify hosting and deployment

## Technical Stack

### Core Technologies
- **Python 3.9+** for static site generation
- **Airtable** as CMS/database (via API)
- **Jinja2** for HTML templating
- **Netlify** for hosting and deployment
- **GitHub** for version control

### Key Python Libraries
```
airtable-python-wrapper
jinja2
python-dotenv
requests
```

### Additional Tools
- CSV generation for initial Airtable data import
- Geocoding for address lat/long (Google Maps API or similar)
- Markdown for content pages

## Airtable Database Schema

### Table 1: Veterinarians (Main Directory Table)

**Fields:**

| Field Name | Type | Description | Options/Validation |
|------------|------|-------------|-------------------|
| Practice Name | Single line text | Official practice/clinic name | Required |
| Veterinarian Name(s) | Long text | Name(s) of holistic vets at practice | Required |
| Specialties | Multiple select | Holistic modalities offered | See Specialties list below |
| Address | Single line text | Street address | Required |
| City | Single line text | City name | Required |
| State | Single select | US State | Two-letter abbreviation |
| ZIP Code | Single line text | 5-digit ZIP | Format: 00000 |
| Phone | Phone number | Contact phone | Format: (000) 000-0000 |
| Email | Email | Practice email | Valid email format |
| Website | URL | Practice website | Valid URL with https:// |
| Certification Bodies | Multiple select | Professional certifications | AHVMA, Chi Institute, CIVT, VBMA, etc. |
| Species Treated | Multiple select | Types of animals treated | Dogs, Cats, Horses, Exotic, Farm Animals, Birds, Reptiles |
| Practice Description | Long text | Description of practice and approach | 200-500 words ideal |
| Year Established | Number | Year practice started | 4-digit year |
| Telehealth Available | Checkbox | Offers remote consultations | Boolean |
| Featured Listing | Checkbox | Premium placement (future monetization) | Boolean |
| Status | Single select | Listing status | Active, Pending Review, Inactive |
| Date Added | Date | When added to directory | Auto-populated |
| Last Updated | Date | Last modification date | Auto-updated |
| Latitude | Number | Geocoded latitude | Decimal degrees |
| Longitude | Number | Geocoded longitude | Decimal degrees |
| Slug | Single line text | URL-friendly identifier | Auto-generated from practice name |

**Specialties Options:**
- Acupuncture
- Chiropractic
- Herbal Medicine
- Homeopathy
- Nutritional Therapy
- Physical Therapy/Rehabilitation
- Traditional Chinese Veterinary Medicine (TCVM)
- Aromatherapy
- Massage Therapy
- Laser Therapy
- Energy Medicine (Reiki, etc.)
- Prolotherapy
- Ozone Therapy
- Naturopathy

**Certification Bodies Options:**
- AHVMA (American Holistic Veterinary Medical Association)
- Chi Institute
- CIVT (College of Integrative Veterinary Therapies)
- VBMA (Veterinary Botanical Medicine Association)
- IVAS (International Veterinary Acupuncture Society)
- AVCA (American Veterinary Chiropractic Association)
- Academy of Veterinary Homeopathy

### Table 2: Specialties Reference

**Fields:**
- Specialty Name (Primary field) - Single line text
- Description - Long text (what this modality is, how it helps animals)
- Icon/Image - Attachment (visual representation)
- Related Conditions - Long text (what conditions this treats)
- Vet Count - Rollup (count of vets offering this specialty)
- Slug - Single line text (URL-friendly)

### Table 3: States

**Fields:**
- State Name - Single line text (e.g., "California")
- State Code - Single line text (e.g., "CA")
- Region - Single select (Northeast, Southeast, Midwest, Southwest, West, Pacific Northwest)
- Vet Count - Rollup (count of vets in state)
- Featured - Checkbox (highlight on homepage)
- Slug - Single line text (e.g., "california")

### Table 4: Cities (Optional - can be generated dynamically)

**Fields:**
- City Name - Single line text
- State - Link to States table
- Vet Count - Rollup
- Slug - Single line text

### Table 5: Blog Posts (Future - for content marketing and SEO)

**Fields:**
- Title - Single line text
- Slug - Single line text
- Content - Long text (Markdown format)
- Author - Single line text
- Published Date - Date
- Status - Single select (Draft, Published)
- Featured Image - Attachment
- Meta Description - Single line text (for SEO)

## Site Architecture

### URL Structure

```
/                           # Homepage with search
/vets/                      # All listings (paginated)
/vets/{state}/              # State-specific listings (e.g., /vets/california/)
/vets/{state}/{city}/       # City-specific listings (e.g., /vets/california/san-francisco/)
/vet/{slug}/                # Individual vet detail page (e.g., /vet/holistic-paws-sf/)
/specialties/               # All specialties overview
/specialty/{slug}/          # Specialty-specific listings (e.g., /specialty/acupuncture/)
/search/                    # Search results page
/about/                     # About the directory
/submit/                    # Vet submission form (future)
/blog/                      # Blog homepage (future)
/blog/{slug}/               # Individual blog post (future)
```

### Page Types to Generate

1. **Homepage (index.html)**
   - Hero section with search bar
   - Featured specialties (top 6-8)
   - Featured states with vet counts
   - Recent additions
   - AdSense placement: header, sidebar, below featured sections

2. **All Vets Listing (/vets/index.html)**
   - Full directory with filters (state, specialty, species)
   - Pagination (20-30 per page)
   - Map view option
   - AdSense: between every 5-7 listings, sidebar

3. **State Listing Pages (/vets/{state}/index.html)**
   - All vets in specific state
   - City breakdown within state
   - State map with pins
   - AdSense: sidebar, between listings

4. **City Listing Pages (/vets/{state}/{city}/index.html)**
   - All vets in specific city
   - Neighborhood information
   - Local map
   - AdSense: sidebar, between listings

5. **Vet Detail Page (/vet/{slug}/index.html)**
   - Complete practice information
   - Specialties with descriptions
   - Contact information with map
   - Nearby vets (3-5 within 25 miles)
   - AdSense: sidebar, below description, after nearby vets

6. **Specialty Pages (/specialty/{slug}/index.html)**
   - Explanation of the specialty
   - All vets offering this specialty (sortable by state)
   - Related specialties
   - AdSense: sidebar, between listings

7. **Search Results Page (/search/index.html)**
   - JavaScript-powered client-side search
   - Filter by location, specialty, species
   - Map integration
   - AdSense: sidebar

8. **Static Pages**
   - About (/about/index.html)
   - Submit Listing (/submit/index.html) - links to Google Form initially
   - Privacy Policy (/privacy/index.html)
   - Terms (/terms/index.html)

## Core Features

### Search & Filtering

**Location-Based Search:**
- "Find vets near me" with geolocation
- Search by city, state, or ZIP code
- Radius search (10, 25, 50, 100 miles)

**Filters:**
- Specialty (checkboxes, multiple selection)
- Species treated (checkboxes)
- Telehealth available (toggle)
- Certification bodies (checkboxes)

**Sort Options:**
- Distance (when location provided)
- Alphabetical (practice name)
- Recently added
- Featured listings first

### Map Integration

- Integrate Google Maps or Leaflet/OpenStreetMap
- Show vet locations as pins
- Click pin to see practice name and link to detail page
- Cluster pins when zoomed out

### Mobile Responsiveness

- Mobile-first design approach
- Touch-friendly navigation
- Fast loading on mobile networks
- Click-to-call phone numbers
- Click-to-map addresses

### SEO Requirements

**Per-Page SEO:**
- Unique title tags: "{Practice Name} - Holistic Veterinarian in {City}, {State}"
- Meta descriptions: 150-160 characters, include specialty and location
- H1 tags: Practice name on detail pages, "Holistic Vets in {Location}" on listing pages
- Schema.org markup: LocalBusiness, Veterinarian, Place

**Site-Wide SEO:**
- XML sitemap generation
- Robots.txt
- Canonical URLs
- Open Graph tags for social sharing
- Fast page load times (< 3 seconds)
- Clean, semantic HTML

**Content Strategy:**
- Location-based pages: "Find holistic vets in [City], [State]"
- Specialty pages: "What is [specialty]? Find certified practitioners"
- Blog content (future): "Benefits of holistic vet care," "When to see a holistic vet," etc.

### AdSense Placement Strategy

**Homepage:**
- 728x90 leaderboard below hero
- 300x250 medium rectangle in sidebar
- 336x280 large rectangle below featured sections

**Listing Pages:**
- 728x90 leaderboard at top
- 300x250 in sidebar (sticky)
- In-feed ads between every 5-7 listings
- 728x90 at bottom pagination

**Detail Pages:**
- 728x90 at top
- 300x600 half-page in sidebar
- 336x280 below practice description
- 300x250 after "nearby vets" section

**Ad Units to Create:**
- Responsive display ads for automatic sizing
- Link ads in navigation areas
- Matched content (if available after approval)

**AdSense Best Practices:**
- Ads clearly labeled
- Not intrusive to user experience
- Mobile-optimized ad units
- Fast loading (async ad scripts)

## Data Collection & Import

### Phase 1: CSV Template Creation

Create CSV templates matching Airtable schema for manual data entry or import:

**veterinarians.csv:**
```csv
Practice Name,Veterinarian Name(s),Specialties,Address,City,State,ZIP Code,Phone,Email,Website,Certification Bodies,Species Treated,Practice Description,Year Established,Telehealth Available,Status
"Holistic Paws Veterinary Clinic","Dr. Jane Smith, Dr. Bob Johnson","Acupuncture|Herbal Medicine|Nutritional Therapy","123 Main St","San Francisco","CA","94102","(415) 555-1234","info@holisticpaws.com","https://holisticpaws.com","AHVMA|Chi Institute","Dogs|Cats|Exotic","Integrative veterinary practice combining Eastern and Western medicine...",2015,TRUE,Active
```

**Notes on CSV Format:**
- Multiple select fields use pipe delimiter: `Option1|Option2|Option3`
- Checkboxes: TRUE or FALSE
- Dates: YYYY-MM-DD format
- URLs: Include full URL with https://

**specialties.csv:**
```csv
Specialty Name,Description,Related Conditions
"Acupuncture","Traditional Chinese Medicine technique using fine needles to stimulate specific points...","Pain management, arthritis, digestive issues, anxiety"
"Herbal Medicine","Use of plant-based medicines to treat and prevent disease...","Chronic conditions, immune support, digestive health"
```

**states.csv:**
```csv
State Name,State Code,Region,Featured
"Alabama","AL","Southeast",FALSE
"Alaska","AK","West",FALSE
"Arizona","AZ","Southwest",TRUE
...
```

### Phase 2: Initial Data Research & Collection

**Data Sources:**
1. AHVMA Member Directory (https://ahvma.org)
2. Chi Institute Certified Practitioners
3. CIVT Graduate Directory
4. IVAS Certified Practitioners
5. Manual Google searches for "holistic vet [city]"

**Data Collection Script Requirements:**
- Scrape public directories (respecting robots.txt and ToS)
- Extract: practice name, address, phone, website, specialties
- Geocode addresses to get lat/long
- Validate phone numbers and emails
- Format data into CSV for Airtable import
- Handle duplicates (check by phone number or address)

**Initial Target:**
- 100-200 practices across top 50 US metro areas
- Good geographic distribution
- Variety of specialties represented
- All data validated and complete

### Phase 3: Airtable Import

- Import CSVs into respective Airtable tables
- Set up field types and validations
- Create views: Active Listings, By State, By Specialty, Featured
- Test API access and permissions

### Phase 4: Data Enhancement

After initial import:
- Add missing geocodes
- Write/enhance practice descriptions
- Add certifications from practitioner websites
- Populate specialty descriptions
- Take/find representative images for specialties

## Static Site Generation

### Build Process

**Script: `generate_site.py`**

1. **Connect to Airtable API**
   - Load credentials from `.env` file
   - Authenticate and fetch all tables

2. **Fetch Data**
   - Pull all active veterinarians
   - Pull specialties reference data
   - Pull states data
   - Cache API responses to avoid rate limits

3. **Process Data**
   - Generate slugs for URLs
   - Group vets by state, city, specialty
   - Calculate vet counts for states/cities/specialties
   - Sort and paginate listings
   - Prepare search index (JSON)

4. **Generate HTML Pages**
   - Use Jinja2 templates
   - Create homepage with featured content
   - Generate all listing pages (states, cities, specialties)
   - Generate individual vet detail pages
   - Generate search page with JSON data
   - Create XML sitemap
   - Create robots.txt

5. **Copy Static Assets**
   - CSS files
   - JavaScript files
   - Images
   - Fonts

6. **Output**
   - Write all files to `dist/` or `public/` directory
   - Ready for Netlify deployment

### Template Structure

```
templates/
├── base.html                 # Base template with header, footer, AdSense
├── index.html               # Homepage
├── vets_list.html           # Generic listing page
├── vet_detail.html          # Individual vet page
├── specialty_list.html      # Specialty page
├── search.html              # Search page
├── about.html               # About page
├── partials/
│   ├── header.html          # Site header/navigation
│   ├── footer.html          # Site footer
│   ├── vet_card.html        # Vet listing card component
│   ├── search_filters.html  # Search filter sidebar
│   └── adsense_unit.html    # AdSense ad units
```

### Jinja2 Template Features

- Template inheritance from base.html
- Macros for repeated components (vet cards, filters)
- Custom filters: slugify, truncate, format_phone
- Conditional AdSense placement based on page type
- Schema.org JSON-LD generation

### Environment Variables (.env)

```
AIRTABLE_API_KEY=your_api_key_here
AIRTABLE_BASE_ID=your_base_id_here
GOOGLE_MAPS_API_KEY=your_maps_key_here
ADSENSE_CLIENT_ID=ca-pub-xxxxxxxxxx
ADSENSE_SLOT_HEADER=xxxxxxxxxx
ADSENSE_SLOT_SIDEBAR=xxxxxxxxxx
ADSENSE_SLOT_INFEED=xxxxxxxxxx
```

## Deployment to Netlify

### Repository Setup

```
holistic-vet-directory/
├── .env.example              # Template for environment variables
├── .gitignore               # Ignore .env, dist/, __pycache__, etc.
├── README.md                # Project documentation
├── requirements.txt         # Python dependencies
├── generate_site.py         # Main build script
├── netlify.toml             # Netlify build configuration
├── templates/               # Jinja2 templates
├── static/                  # CSS, JS, images
│   ├── css/
│   ├── js/
│   └── images/
├── scripts/                 # Helper scripts
│   ├── fetch_data.py        # Data collection script
│   ├── geocode.py           # Geocoding utility
│   └── csv_import.py        # CSV generation
└── dist/                    # Generated site (not in git)
```

### netlify.toml Configuration

```toml
[build]
  command = "python generate_site.py"
  publish = "dist"

[build.environment]
  PYTHON_VERSION = "3.9"

[[redirects]]
  from = "/search"
  to = "/search/index.html"
  status = 200

[[redirects]]
  from = "/*"
  to = "/404.html"
  status = 404

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-XSS-Protection = "1; mode=block"
    X-Content-Type-Options = "nosniff"

[[headers]]
  for = "/static/*"
  [headers.values]
    Cache-Control = "public, max-age=31536000, immutable"
```

### Build Command

```bash
python generate_site.py
```

### Environment Variables in Netlify

Set these in Netlify dashboard under Site Settings > Build & Deploy > Environment:
- `AIRTABLE_API_KEY`
- `AIRTABLE_BASE_ID`
- `GOOGLE_MAPS_API_KEY`
- `ADSENSE_CLIENT_ID`
- `ADSENSE_SLOT_HEADER`
- `ADSENSE_SLOT_SIDEBAR`
- `ADSENSE_SLOT_INFEED`

### Deployment Triggers

**Automatic:**
- Git push to main branch (GitHub webhook)

**Manual:**
- Netlify dashboard "Trigger deploy" button

**Scheduled:**
- Use Netlify's build hooks with external cron service (e.g., cron-job.org)
- Rebuild daily at 2am to pull latest Airtable data
- Build hook URL: https://api.netlify.com/build_hooks/{hook_id}

### Custom Domain Setup

1. Purchase domain (e.g., holisticvetfinder.com)
2. Add custom domain in Netlify dashboard
3. Configure DNS:
   - A record: @ → Netlify's load balancer IP
   - CNAME record: www → {site-name}.netlify.app
4. Enable HTTPS (Let's Encrypt, automatic)
5. Force HTTPS redirect

## Design & User Experience

### Design Principles

- Clean, trustworthy aesthetic (this is about pet health)
- Nature/wellness color palette (greens, blues, earth tones)
- High readability and accessibility
- Fast loading times
- Mobile-first, responsive design

### Color Palette Suggestions

- Primary: #2D6A4F (forest green) - trust, nature, health
- Secondary: #52B788 (sage green) - calming, holistic
- Accent: #F4A261 (warm orange) - friendly, energetic
- Background: #F8F9FA (off-white)
- Text: #212529 (near-black)

### Typography

- Headings: Clean sans-serif (e.g., "Inter", "Poppins")
- Body: Readable sans-serif (e.g., "Open Sans", "Lato")
- Font sizes: 16px base, scale up for headings
- Line height: 1.6 for readability

### Component Library

**Navigation Bar:**
- Logo/site name (left)
- Main nav: Find a Vet, Specialties, About, Submit Listing
- Search icon (triggers modal or goes to search page)
- Mobile: Hamburger menu

**Vet Card Component:**
```
┌─────────────────────────────────────┐
│ Practice Name (H3)                  │
│ City, State                         │
│ ⭐⭐⭐ Specialties (badges)          │
│ 🐕🐈 Species icons                  │
│ 📞 Phone  🌐 Website                │
│ [View Details] button               │
└─────────────────────────────────────┘
```

**Search Filters (Sidebar):**
- Location input (autocomplete)
- Radius slider (10-100 mi)
- Specialty checkboxes (collapsible)
- Species checkboxes
- Telehealth toggle
- [Apply Filters] button

**Map View:**
- Embedded map (full width or 50/50 split with list)
- Clustered pins
- Click pin → popup with practice name & link
- Toggle between map/list view (mobile)

### Accessibility

- WCAG 2.1 AA compliance
- Semantic HTML5
- ARIA labels where needed
- Keyboard navigation
- Alt text for all images
- Color contrast ratios: 4.5:1 minimum
- Focus indicators on interactive elements
- Skip to content link

## Content Guidelines

### Practice Descriptions

If not provided by the vet:
- 200-300 words
- Include specialties offered
- Mention years in practice, credentials
- Describe philosophy/approach
- List species treated
- Mention any unique services

### Specialty Descriptions

For each specialty page:
- What is this modality? (150-200 words)
- How does it work?
- What conditions does it treat?
- What to expect in a session
- How to find a qualified practitioner

### Homepage Copy

**Hero Headline:**
"Find Holistic & Integrative Veterinarians Near You"

**Subheadline:**
"Discover compassionate vets who combine conventional medicine with natural healing modalities for your pet's optimal health"

**Value Propositions:**
- Comprehensive directory of certified holistic vets
- Search by location and specialty
- Natural approaches to pet wellness
- Acupuncture, herbal medicine, chiropractic & more

## Future Enhancements (Phase 2+)

### Features to Add Later

1. **User Reviews/Ratings**
   - 5-star rating system
   - Written reviews with moderation
   - Helpful/not helpful voting

2. **Vet Submission System**
   - Online form for vets to add/claim listings
   - Admin approval workflow
   - Email notifications

3. **Featured Listings (Monetization)**
   - Premium placement for vets (paid monthly/yearly)
   - Enhanced profiles with photos, videos
   - Priority in search results

4. **Blog/Resource Section**
   - Educational articles about holistic pet care
   - SEO content for long-tail keywords
   - Guest posts from holistic vets

5. **Email Newsletter**
   - Weekly/monthly digest of new listings
   - Featured articles
   - Holistic pet health tips
   - Mailchimp or ConvertKit integration

6. **Advanced Search**
   - Save searches
   - Email alerts for new vets in area
   - Compare vets side-by-side

7. **Telehealth Integration**
   - Filter for telehealth availability
   - Booking integration (Calendly, etc.)

8. **Mobile App**
   - Native iOS/Android apps
   - GPS-based "vets near me"
   - Push notifications

9. **Community Features**
   - Pet owner forums
   - Q&A section
   - Success stories

10. **Analytics Dashboard**
    - Track page views, searches
    - Most popular specialties
    - Geographic heatmaps
    - Google Analytics integration

## Testing & Quality Assurance

### Pre-Launch Checklist

**Functionality:**
- [ ] All pages generate correctly
- [ ] Links work (no 404s)
- [ ] Search functionality works
- [ ] Filters apply correctly
- [ ] Maps display and are clickable
- [ ] Phone numbers are clickable (mobile)
- [ ] Addresses link to maps
- [ ] Forms submit successfully

**Performance:**
- [ ] Page load < 3 seconds
- [ ] Images optimized
- [ ] CSS/JS minified
- [ ] Lighthouse score > 90

**SEO:**
- [ ] Title tags unique and descriptive
- [ ] Meta descriptions present
- [ ] H1 tags on every page
- [ ] XML sitemap generated
- [ ] Robots.txt configured
- [ ] Schema markup validates
- [ ] Canonical URLs set

**AdSense:**
- [ ] Ads display correctly
- [ ] Ads are not intrusive
- [ ] Mobile ad units work
- [ ] Ad code validates
- [ ] Ads comply with policies

**Browser Testing:**
- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Edge (latest)
- [ ] Mobile Safari (iOS)
- [ ] Mobile Chrome (Android)

**Accessibility:**
- [ ] WAVE tool validation
- [ ] Keyboard navigation
- [ ] Screen reader testing
- [ ] Color contrast check

## Project Timeline

### Phase 1: Foundation (Week 1-2)
- Set up Airtable base with schema
- Create CSV templates
- Research and collect initial 100 vets
- Import data to Airtable

### Phase 2: Site Generation (Week 3-4)
- Build static site generator script
- Create Jinja2 templates
- Implement search functionality
- Design and style all pages

### Phase 3: Content & SEO (Week 5)
- Write specialty descriptions
- Write homepage and about page copy
- Implement Schema markup
- Generate sitemap

### Phase 4: AdSense Integration (Week 6)
- Apply for AdSense account
- Implement ad units in templates
- Test ad placement and display
- Optimize for revenue

### Phase 5: Testing & Launch (Week 7-8)
- Comprehensive QA testing
- Fix bugs and issues
- Set up custom domain
- Deploy to Netlify
- Monitor performance and ads

### Phase 6: Growth (Ongoing)
- Add more vet listings (goal: 500+ in 6 months)
- Monitor analytics
- Optimize for SEO
- Create blog content
- Build backlinks

## Success Metrics

### Initial Goals (3 months)
- 200+ vet listings
- 1,000+ monthly organic visits
- Page 1 Google rankings for 10+ keywords
- AdSense approval and activation
- $100+ monthly AdSense revenue

### 6-Month Goals
- 500+ vet listings
- 5,000+ monthly organic visits
- Page 1 rankings for 50+ keywords
- $500+ monthly AdSense revenue
- 10+ featured listings sold

### 12-Month Goals
- 1,000+ vet listings
- 20,000+ monthly organic visits
- $2,000+ monthly revenue (AdSense + featured listings)
- Established authority in holistic vet directory space

## Key Contacts & Resources

### Professional Associations
- AHVMA: https://ahvma.org
- Chi Institute: https://tcvm.com
- CIVT: https://www.civtedu.org
- IVAS: https://ivas.org
- AVCA: https://animalchiropractic.org

### Development Resources
- Airtable API: https://airtable.com/api
- Netlify Docs: https://docs.netlify.com
- Google AdSense: https://adsense.google.com
- Google Maps API: https://developers.google.com/maps

### SEO Tools
- Google Search Console
- Google Analytics
- Ahrefs or SEMrush (keyword research)
- Screaming Frog (site audits)

## Notes for Claude Code

### Development Priorities
1. **Start with data infrastructure:** CSV templates and Airtable schema are foundational
2. **Then build generator:** The Python script that creates the static site
3. **Design comes third:** HTML/CSS templates after functionality works
4. **AdSense last:** Add after site is functional and approved

### Code Style Preferences
- Python: PEP 8 style guide
- Clear comments and docstrings
- Modular code (separate functions for each task)
- Error handling for API calls
- Logging for debugging

### Testing Approach
- Test with small dataset first (10-20 vets)
- Validate CSV imports before bulk loading
- Check generated HTML for validity
- Test locally before Netlify deployment

### Reference Architecture
- Follow patterns from smart-investor-financial-tools.com
- Similar Airtable → Python → Static HTML → Netlify workflow
- Adapt AdSense placement strategies
- Use proven template structure

---

**End of CLAUDE.md**

Last Updated: January 2026
Project: Holistic Veterinary Directory
Created by: Kevin
For use with: Claude Code
