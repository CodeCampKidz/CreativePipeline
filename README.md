# Creative Automation Pipeline

A GenAI-powered tool that automates social ad campaign creative generation. Given a campaign brief with products, target audience, and messaging, it produces sized, branded image assets paired with AI-generated social media post messages — ready for publishing.

**Built for**: Global consumer goods companies launching hundreds of localized social ad campaigns monthly.

**What it solves**: Manual content creation overload, inconsistent brand quality, and slow approval cycles by automating the creative-to-publish pipeline.

## Features

- Web UI for marketing teams — upload briefs, preview creatives + post messages, download package
- AI-generated social media post copy (GPT-4o-mini) paired with each creative image
- Product images via OpenAI GPT Image 1.5 with automatic fallback (DALL-E 2 -> placeholder)
- AI Creative Director — derives mood, style, tone, and cultural angle per product before generation
- Cumulative creative chain — each stage builds on the previous (direction -> copy -> image -> overlay)
- Three social media aspect ratios: 1:1 (Feed), 9:16 (Stories/TikTok), 16:9 (YouTube)
- Campaign message text overlay with brand logo compositing
- Localization — translates messages and post copy to target languages
- Per-language culturally tailored images — different audiences get different visual treatments
- Legal compliance (prohibited words) and brand compliance (color/logo) checks
- Async pipeline — products processed in parallel with sequential cumulative chain per product
- Version history awareness — regenerated creatives avoid repeating previous creative directions
- Regenerate creatives if you don't like the results
- Download all creatives + post messages as a zip package
- Pluggable storage — local filesystem or AWS S3 (sync on generate, cleanup on delete)
- Full test suite runs during Docker build — broken code never ships

---

## Quick Start (Docker)

The fastest way to get running. Tests execute during the build — if they fail, the image won't build.

### Prerequisites

- **Docker** with Docker Compose — [Install Docker](https://docs.docker.com/get-docker/)
- **Git** — [Install Git](https://git-scm.com/downloads)
- **OpenAI API key** (optional) — [Get one here](https://platform.openai.com/api-keys). Without one, the app runs in placeholder mode.
- **AWS credentials** (optional) — `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and an S3 bucket name. Only needed if using S3 storage instead of local filesystem.

### 1. Clone and configure

```bash
git clone https://github.com/CodeCampKidz/CreativePipeline.git
cd CreativePipeline
cp .env.example .env
```

Edit `.env` and set your keys:

```bash
# Required for AI image generation (skip for placeholder mode)
OPENAI_API_KEY=sk-your-key-here

# Optional: AWS S3 storage (default is local filesystem)
AWS_ACCESS_KEY_ID=your-access-key-here
AWS_SECRET_ACCESS_KEY=your-secret-key-here
S3_BUCKET=your-bucket-name-here
STORAGE_BACKEND=s3
```

> **No API key?** Leave `OPENAI_API_KEY` as-is — the app works without one using placeholder images.

### 2. Build and run

```bash
docker compose up --build
```

This will:
- Install all dependencies
- **Run the full test suite** (126 tests) — build fails if any test fails
- Start the web server

> **Note:** Docker caches build layers. After the first build, unchanged code won't re-run tests. To force tests on every build:
> ```bash
> docker compose build --no-cache && docker compose up
> ```

### 3. Open the app

Point your browser to **http://localhost:8080**

From there you can:
1. Upload a campaign brief (YAML or JSON) — sample briefs are in `data/briefs/`
2. Optionally upload product hero images — test heroes for Thermal Mug and Cozy Beanie are in `data/input_assets/thermal_mug/` and `data/input_assets/cozy_beanie/`
3. Click **Generate Creatives** — watch images and post messages appear
4. **Preview** each creative paired with its AI-generated post message
5. **Download All** — zip package with images + post text files
6. **Regenerate** — don't like the results? One click for fresh AI content

To stop: `Ctrl+C` then `docker compose down`.

---

## Local Development Setup

For development without Docker.

### Prerequisites

- **Python 3.11+** — [Download](https://www.python.org/downloads/)
- **Git** — [Install Git](https://git-scm.com/downloads)
- **OpenAI API key** (optional) — [Get one here](https://platform.openai.com/api-keys). Without one, the app runs in placeholder mode.
- **AWS credentials** (optional) — `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and an S3 bucket name. Only needed if using S3 storage instead of local filesystem.

### Setup

```bash
# 1. Clone
git clone https://github.com/<your-username>/creative-automation-pipeline.git
cd creative-automation-pipeline

# 2. Virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env — add your OPENAI_API_KEY and optionally AWS/S3 credentials

# 5. Launch the web UI
python -m src.cli web
# Open http://localhost:8080
```

### CLI Usage (Power Users / CI)

```bash
# Validate a brief without generating
python -m src.cli validate data/briefs/sample_brief.yaml

# Dry run — show the execution plan, generate nothing
python -m src.cli generate data/briefs/sample_brief.yaml --dry-run

# Placeholder mode (no API key needed)
python -m src.cli generate data/briefs/sample_brief.yaml --skip-genai

# Full pipeline with AI image generation
python -m src.cli generate data/briefs/sample_brief.yaml
```

| Option | Short | Description |
|--------|-------|-------------|
| `--output-dir` | `-o` | Custom output directory (default: `data/output`) |
| `--input-dir` | `-i` | Custom input assets directory (default: `data/input_assets`) |
| `--brand-config` | `-b` | Custom brand config YAML file |
| `--dry-run` | | Validate and plan, don't generate |
| `--skip-genai` | | Use placeholders instead of GenAI |
| `--verbose` | `-v` | Enable DEBUG-level console output |

### API Integration

The web server exposes a REST API that can be called from any external application. Start the server with `python -m src.cli web` (or via Docker), then explore the full API documentation at:

**http://localhost:8080/docs** (Swagger UI)

Example — submit a brief with product hero images and poll for results:

```bash
# Start a generation job with uploaded hero images
curl -X POST http://localhost:8080/api/generate \
  -F "brief=@data/briefs/test_brief.json" \
  -F "product_asset_thermal-mug=@data/input_assets/thermal_mug/hero.png" \
  -F "product_asset_cozy-beanie=@data/input_assets/cozy_beanie/hero.png"

# Poll job status (returns results when complete)
curl http://localhost:8080/api/jobs/<job-id>
```

Product asset field names follow the pattern `product_asset_<product-slug>`, where the slug is the lowercased, hyphenated product name from the brief (e.g., "Thermal Mug" becomes `thermal-mug`).

---

## Campaign Brief Format

Create a YAML or JSON file with your campaign details. Example (`data/briefs/sample_brief.yaml`):

```yaml
campaign_name: "Summer Splash 2026"
products:
  - name: "Eco Bottle"
    description: "Sustainable reusable water bottle, sleek matte finish, ocean blue"
    asset_folder: "data/input_assets/eco_bottle"
  - name: "Sport Cap"
    description: "Lightweight breathable sports cap, neon green accent, athletic style"
    asset_folder: "data/input_assets/sport_cap"
target_region: "Latin America"
target_audience: "Health-conscious millennials 25-35"
campaign_message: "Stay Fresh. Stay Green. Summer Splash 2026"
languages:
  - "en"
  - "es"
aspect_ratios:
  - "1:1"
  - "9:16"
  - "16:9"
```

**Required fields**: `campaign_name`, `products` (min 2), `target_region`, `target_audience`, `campaign_message`

**Optional fields**: `languages` (default: `["en"]`), `aspect_ratios` (default: all three)

A sample JSON brief is also available at `data/briefs/test_brief.json`.

## Output

Generated creatives are versioned under `data/output/<campaign-slug>/v<N>/`:

```
data/output/summer-splash-2026/
├── v1/
│   ├── eco-bottle/
│   │   ├── 1x1/
│   │   │   ├── creative_en.png        # Creative image
│   │   │   └── creative_es.png        # Localized variant
│   │   ├── 9x16/...
│   │   └── 16x9/...
│   ├── sport-cap/...
│   ├── report.json                    # Full results with post messages
│   └── pipeline.log                   # Debug log
├── v2/...                             # Regenerated version
```

Each creative in `report.json` includes its paired post message with text, hashtags, and platform hint.

---

## Running the Test Suite

All tests use mocked GenAI calls — no API key needed.

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=src --cov-report=term-missing

# Specific module
pytest tests/test_models.py -v
pytest tests/test_message_generator.py -v
```

**Expected**: 126 passed, ~87% coverage

> Tests also run automatically during `docker build` — broken code never makes it into the image.

---

## Project Structure

```
├── src/                        # Application code
│   ├── shared/                 # Contracts — models, config, exceptions
│   ├── service/                # Pipeline engine (microservice-ready)
│   │   ├── pipeline/           # Orchestrator, image processing, text overlay
│   │   ├── integrations/       # GPT Image 1.5, GPT-4o-mini messages, S3, translation
│   │   ├── compliance/         # Brand + legal checks
│   │   └── core/               # Logger, color utilities
│   ├── web/                    # FastAPI web UI + REST API
│   ├── assets/fonts/           # Bundled Roboto fonts
│   └── cli.py                  # CLI entry point
├── tests/                      # 126 tests (positive + negative)
├── data/                       # Sample data + runtime output
│   ├── briefs/                 # Sample campaign briefs (YAML + JSON)
│   ├── brand/                  # Brand config + logo
│   └── input_assets/           # Product hero images for reuse
├── docs/                       # Architecture docs
│   └── ARCHITECTURE.md         # System design + microservice transition plan
└── (Dockerfile, docker-compose.yml, requirements.txt, pyproject.toml)
```

**Microservice-ready**: `shared/` defines the contract. `service/` and `web/` depend on `shared/` but never on each other. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the microservice transition plan.

## Cloud Storage (S3)

By default, generated assets save to `data/output/`. To use AWS S3, set these in your `.env`:

```bash
STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=your-access-key-here
AWS_SECRET_ACCESS_KEY=your-secret-key-here
S3_BUCKET=your-bucket-name
S3_PREFIX=campaigns/
S3_REGION=us-east-1
```

When S3 is enabled:
- Assets are uploaded after each pipeline run (both CLI and web)
- Deleting a version through the UI also removes its assets from S3
- AWS credentials are passed directly to boto3 from your `.env` — no need to configure AWS CLI separately

The `StorageBackend` interface is extensible to Azure Blob or GCS.

## Docker Details

- **Multi-stage build**: Stage 1 runs tests, Stage 2 produces slim production image (no test code)
- **Tests gate the build**: If any test fails, `docker build` fails — broken code never ships
- **Non-root user**: Runs as `appuser` (UID 1000)
- **Health check**: `/health` endpoint, 30s interval
- **Port**: 8080 (configurable via `WEB_PORT` env var)
- **Volume**: Mount `./data` to persist output and supply input assets

### Docker Compose services

| Service | Purpose | Command |
|---------|---------|---------|
| `web` (default) | Web UI at port 8080 | `docker compose up --build` |
| `pipeline` (cli profile) | One-shot CLI job | `docker compose run --rm pipeline generate data/briefs/sample_brief.yaml` |

## Design Decisions

1. **GPT Image 1.5** — primary image model (replaced DALL-E 3 in 2025). Native 1:1 size, highest quality product photography. Three-tier fallback: GPT Image 1.5 -> DALL-E 2 -> placeholder ensures the pipeline always produces output.
2. **AI Creative Director** — GPT-4o-mini derives mood, style, lighting, composition, cultural angle, and copy tone per product before any generation happens. This gives the pipeline coherent creative direction rather than ad-hoc prompts.
3. **Cumulative creative chain** — each stage builds on the previous: creative direction informs post copy, post copy informs image generation, images get resized and overlaid. The chain ensures visual and textual coherence.
4. **Per-language image generation** — different audiences get culturally tailored images, not just translated text on the same image. A Latin American audience sees different visual cues than a Northern European one.
5. **"No text in image" enforcement** — AI-generated text in images is unreliable and uncontrollable. Campaign text is excluded from image prompts and overlaid programmatically via PIL for pixel-perfect brand control.
6. **GPT-4o-mini for post messages** — fast, cheap, structured JSON output. Each creative gets a localized, platform-aware social media post with hashtags.
7. **Async pipeline** — `asyncio.gather()` parallelizes products. Within each product, the cumulative chain runs sequentially by design (each stage needs the previous stage's output).
8. **Version history** — regenerated campaigns load previous versions' creative directions and post messages, instructing the AI to produce something genuinely different each time.
9. **Pydantic validation** — fail fast with clear errors before spending API credits.
10. **Web UI + CLI** — marketing teams use the browser; power users and CI use the CLI. Both paths share the same pipeline and storage logic.
11. **Unified storage layer** — `sync_to_storage()` and `delete_from_storage()` are called from both CLI and web, keeping local and remote state consistent.
12. **Microservice-ready architecture** — `shared/` contract layer, clean dependency direction. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
13. **Tests in Docker build** — quality gate at the container level.

## Assumptions & Limitations

- **PoC scope**: Not production-hardened for hundreds of concurrent campaigns. Production needs rate limiting, job queuing, and persistent storage.
- **Translation**: Google Translate free tier. Production would use a paid API with quality review.
- **Brand compliance**: RGB Euclidean distance for color matching. Production would use Delta-E in LAB color space.
- **Post messages**: GPT-4o-mini. Production might use GPT-4o for higher quality or add human approval workflow.
- **Image model**: GPT Image 1.5 at "standard" quality. Set `DALLE_QUALITY=hd` for higher quality at increased cost.
- **Text in AI images**: Despite strong prompt engineering, generative models occasionally render text into images. The pipeline mitigates this by excluding literal campaign copy from image prompts, but cannot guarantee text-free output 100% of the time.
- **S3 storage**: Credentials are read from `.env` and passed directly to boto3. Production would use IAM roles or instance profiles instead of static keys.
- **Single-node**: The web UI runs jobs in-process with `asyncio`. Production would use a task queue (Celery, SQS) for background processing and horizontal scaling.

## License

MIT
