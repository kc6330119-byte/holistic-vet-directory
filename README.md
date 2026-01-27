# Holistic Veterinary Directory

A static directory website for holistic and integrative veterinarians across the United States. Built with Python, Airtable, and deployed on Netlify.

## Features

- **Comprehensive Directory**: Searchable database of holistic veterinarians
- **Location-Based Search**: Find vets by city, state, or ZIP code
- **Specialty Filtering**: Filter by modalities (acupuncture, herbal medicine, chiropractic, etc.)
- **Species Filtering**: Find vets who treat specific animals
- **Interactive Maps**: Visual vet locations with Google Maps integration
- **Mobile-Friendly**: Responsive design for all devices
- **SEO Optimized**: Schema markup, sitemaps, and optimized meta tags

## Tech Stack

- **Static Site Generator**: Python 3.9+
- **Database/CMS**: Airtable
- **Templating**: Jinja2
- **Hosting**: Netlify
- **Maps**: Google Maps API

## Project Structure

```
holistic-vet-directory/
├── .env.example           # Environment variables template
├── .gitignore             # Git ignore rules
├── CLAUDE.md              # Project requirements document
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── netlify.toml           # Netlify configuration
├── generate_site.py       # Main static site generator
├── templates/             # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html
│   ├── vets_list.html
│   ├── vet_detail.html
│   ├── specialty_list.html
│   ├── search.html
│   └── partials/
│       ├── header.html
│       ├── footer.html
│       ├── vet_card.html
│       └── ...
├── static/                # Static assets
│   ├── css/
│   ├── js/
│   └── images/
├── scripts/               # Helper scripts
│   ├── fetch_data.py      # Data collection
│   ├── geocode.py         # Address geocoding
│   └── csv_import.py      # CSV generation
├── data/                  # CSV templates and data files
│   ├── veterinarians.csv
│   ├── specialties.csv
│   └── states.csv
└── dist/                  # Generated site (not in git)
```

## Setup Instructions

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- An Airtable account
- A Google Cloud account (for Maps API)
- A Netlify account

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/holistic-vet-directory.git
cd holistic-vet-directory
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your actual credentials:

- **AIRTABLE_API_KEY**: Get from [Airtable Account](https://airtable.com/account)
- **AIRTABLE_BASE_ID**: Get from [Airtable API Docs](https://airtable.com/api) (select your base)
- **GOOGLE_MAPS_API_KEY**: Get from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
- **ADSENSE_CLIENT_ID**: Get from [Google AdSense](https://adsense.google.com) (after approval)

### 5. Set Up Airtable

1. Create a new Airtable base
2. Import the CSV templates from the `data/` directory:
   - `veterinarians.csv` → Veterinarians table
   - `specialties.csv` → Specialties table
   - `states.csv` → States table
3. Configure field types according to CLAUDE.md schema
4. Copy your Base ID from the API documentation

### 6. Generate the Site Locally

```bash
python generate_site.py
```

The generated site will be in the `dist/` directory.

### 7. Preview Locally

```bash
# Using Python's built-in server
cd dist
python -m http.server 8000
```

Visit `http://localhost:8000` in your browser.

## Deployment to Netlify

### Option 1: Netlify CLI

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Login to Netlify
netlify login

# Deploy
netlify deploy --prod
```

### Option 2: GitHub Integration

1. Push your repository to GitHub
2. Log in to [Netlify](https://netlify.com)
3. Click "New site from Git"
4. Select your repository
5. Configure build settings:
   - Build command: `pip install -r requirements.txt && python generate_site.py`
   - Publish directory: `dist`
6. Add environment variables in Site Settings > Build & Deploy > Environment

### Environment Variables in Netlify

Set these in Netlify Dashboard:

| Variable | Description |
|----------|-------------|
| `AIRTABLE_API_KEY` | Your Airtable API key |
| `AIRTABLE_BASE_ID` | Your Airtable base ID |
| `GOOGLE_MAPS_API_KEY` | Google Maps API key |
| `ADSENSE_CLIENT_ID` | AdSense publisher ID |
| `ADSENSE_SLOT_*` | AdSense slot IDs |
| `BUILD_ENV` | Set to `production` |

## Data Management

### Adding New Veterinarians

1. Add entries directly in Airtable
2. Or use the CSV import feature with `data/veterinarians.csv` template
3. Trigger a rebuild on Netlify (automatic with webhooks, or manual)

### Scheduled Rebuilds

Set up a cron job to hit Netlify's build hook daily:

```bash
# Using cron-job.org or similar service
# URL: https://api.netlify.com/build_hooks/YOUR_HOOK_ID
# Schedule: Daily at 2:00 AM
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
flake8
```

### Building for Development

```bash
BUILD_ENV=development python generate_site.py
```

This disables AdSense and enables debug output.

## CSV Data Format

### Veterinarians CSV

- Multiple select fields use pipe (`|`) delimiter: `Acupuncture|Herbal Medicine`
- Checkboxes: `TRUE` or `FALSE`
- Dates: `YYYY-MM-DD` format
- URLs: Include full URL with `https://`

### Example Row

```csv
"Holistic Paws","Dr. Jane Smith","Acupuncture|Herbal Medicine","123 Main St","San Francisco","CA","94102","(415) 555-1234","info@example.com","https://example.com","AHVMA","Dogs|Cats","Description...",2015,TRUE,Active
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -am 'Add my feature'`
4. Push to branch: `git push origin feature/my-feature`
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

For questions or issues, please open a GitHub issue.

## Acknowledgments

- [AHVMA](https://ahvma.org) - American Holistic Veterinary Medical Association
- [Chi Institute](https://tcvm.com) - TCVM Education
- All the holistic veterinarians helping animals naturally
