# Fonsica.se — Personal Brand Website

## Project Overview
Personal consulting website for Adam Fonsica, iGaming & Lottery consultant.

**Domain:** fonsica.se (hosted at Loopia)
**Status:** Design refinement phase

## Tech Stack
- Single HTML file (`index.html`)
- Google Fonts: Instrument Serif, Space Mono, Inter
- No frameworks — vanilla CSS/JS
- Hosting: GitHub Pages (planned)

## Design Direction
- **Style:** Modern editorial, typography-driven
- **Colors:** High-contrast B&W base + single accent color
- **Current accent:** Teal `#14b8a6`
- **Typography:** Mix of serif headlines, monospace labels, sans-serif body

## Site Structure
1. **Hero** — Bold tagline "Bridging gaming and gambling"
2. **About** — 15+ years experience, expertise tags
3. **Services** — Product Strategy, Market Entry, Advisory
4. **Speaking & Media** — Conference talks, podcasts, interviews
5. **Contact** — Email, LinkedIn, booking

## Available Images
| File | Use Case |
|------|----------|
| `images/BA3823E9...(1).jpeg` | B&W professional portrait — ideal for About section |
| `images/BA3823E9...jpeg` | Same portrait in color |
| `images/FullSizeRender.jpeg` | Casual waterfront portrait |
| `images/IMG_5139.jpeg` | Speaking/presentation shot |

## Current Tasks
- [x] Finalize accent color (Teal #14b8a6)
- [x] Integrate profile photo into About section
- [x] Add keynote image to Speaking section
- [x] Fix mobile menu (fullscreen overlay)
- [x] Update email to adam@fonsica.se
- [x] Review logo options (keeping Space Mono + blend mode)
- [ ] Test mobile responsiveness
- [ ] Set up GitHub repo
- [ ] Configure GitHub Pages + custom domain

## Accent Color Options (Under Consideration)
| Color | Hex | Vibe |
|-------|-----|------|
| Coral (current) | `#ff5c35` | Warm, energetic |
| Amber | `#f59e0b` | Refined, premium |
| Burnt Orange | `#d97706` | Sophisticated |
| Electric Blue | `#3b82f6` | Tech-forward |
| Violet | `#8b5cf6` | Creative, distinctive |

## Insights & Pipelines

Public analysis pages live in `insights/<topic>/index.html`. Each has a corresponding data pipeline in `_pipeline/<topic>/` that is gitignored (data stays local).

### `_pipeline/` Convention

```
_pipeline/
├── <topic>/
│   ├── scrape.mjs          # Data fetcher
│   ├── categorize.mjs      # Optional analysis step
│   ├── deploy.mjs          # Build HTML + git push
│   ├── *.plist              # macOS launchd schedules
│   └── data/                # Scraped data (gitignored)
└── logs/                    # Launchd log output (gitignored)
```

**Adding a new analysis:**
1. Create `_pipeline/<topic>/` with scrape + deploy scripts
2. Create `insights/<topic>/index.html` for the public page
3. Add a launchd plist, symlink to `~/Library/LaunchAgents/`
4. Data and logs are automatically gitignored via `_pipeline/*/data/` and `_pipeline/logs/`

### Active Pipelines

| Pipeline | Schedule | Public URL |
|----------|----------|------------|
| Stake Engine | Daily 08:00 (scrape) + 09:00 (deploy) | `/insights/stake-engine/` |

## Notes
- Keep Random State separate from personal brand
- Focus on personal consulting services
- No blog for now
