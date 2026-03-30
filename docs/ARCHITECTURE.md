# Architecture: Creative Automation Pipeline

## What It Does

Generates social ad campaign creatives from a YAML/JSON brief. For each product and language, it produces culturally tailored images paired with AI-generated social media post messages — ready for publishing across Instagram, TikTok, YouTube, Facebook, and LinkedIn.

## System Overview

```
              ┌──────────────────────┐
              │   Campaign Brief     │
              │   (YAML / JSON)      │
              └──────────┬───────────┘
                         │
            ┌────────────┼────────────┐
            │                          │
  ┌─────────▼──────────┐   ┌─────────▼──────────┐
  │   Web UI (FastAPI) │   │  CLI Layer (Click)  │
  │   Upload + Preview │   │  generate | validate│
  │   Download + Regen │   │  web                │
  └─────────┬──────────┘   └─────────┬──────────┘
            │                          │
            └────────────┬─────────────┘
                         │
              ┌──────────▼───────────┐
              │  Pipeline Orchestrator│
              │  Cumulative LLM Chain │
              │  Versioned Output     │
              └──────────┬───────────┘
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                     │
  ┌─▼──────┐       ┌────▼───┐         ┌──────▼─┐
  │Product A│       │Product B│        │Product N│
  │(parallel)│      │(parallel)│       │(parallel)│
  └──┬──────┘       └────┬───┘         └──────┬─┘
     │                    │                     │
     └────────────────────┼─────────────────────┘
                          │
            Per Product: Cumulative LLM Chain
            (see Pipeline Detail below)
```

## Cumulative LLM Pipeline (Per Product)

This is the core innovation. Each stage builds on ALL previous outputs, creating a coherent chain where images visually match their post messages.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Campaign Brief                                                         │
│  ┌───────────────────────────────────────────────────┐                  │
│  │ campaign_message: "Stay Fresh. Stay Green."       │                  │
│  │ product: "Eco Bottle" + description               │                  │
│  │ region: "Latin America"                           │                  │
│  │ audience: "Health-conscious millennials 25-35"    │                  │
│  └─────────────────────────┬─────────────────────────┘                  │
│                            │                                             │
│                            ▼                                             │
│  ┌─────────────────────────────────────────────┐                        │
│  │ STAGE A: Creative Director (GPT-4o-mini)    │                        │
│  │ Structured output: json_schema (strict)     │                        │
│  │                                             │                        │
│  │ Input:  original message + product +        │                        │
│  │         audience + region +                 │                        │
│  │         VERSION HISTORY (if v2+)            │                        │
│  │                                             │                        │
│  │ Output: CreativeDirection                   │                        │
│  │   ├── visual_style                          │                        │
│  │   ├── lighting                              │                        │
│  │   ├── composition                           │                        │
│  │   ├── scene_setting                         │                        │
│  │   ├── mood                                  │                        │
│  │   ├── color_palette_hint                    │                        │
│  │   ├── copy_tone                             │                        │
│  │   ├── copy_hook                             │                        │
│  │   └── cultural_angle                        │                        │
│  └─────────────────────────┬───────────────────┘                        │
│                            │                                             │
│                            ▼                                             │
│  ┌─────────────────────────────────────────────┐                        │
│  │ STAGE B: Post Messages (GPT-4o-mini)        │                        │
│  │ Structured output: json_schema (strict)     │                        │
│  │                                             │                        │
│  │ Input:  original message +                  │                        │
│  │         ALL creative direction fields +     │                        │
│  │         VERSION HISTORY (if v2+)            │                        │
│  │                                             │                        │
│  │ 1 LLM call per ratio returns ALL languages: │                        │
│  │   { "variants": [                           │                        │
│  │     {lang: "en", ratio: "1:1", text: "..."} │                        │
│  │     {lang: "es", ratio: "1:1", text: "..."} │                        │
│  │   ]}                                        │                        │
│  │                                             │                        │
│  │ Output: dict[(lang, ratio)] → PostMessage   │                        │
│  └────────────┬────────────────────────────────┘                        │
│               │                                                          │
│               ▼                                                          │
│  ┌─────────────────────────────────────────────┐                        │
│  │ STAGE C: Image Generation (GPT Image 1.5)     │                        │
│  │ ONE IMAGE PER LANGUAGE (culturally tailored) │                        │
│  │                                             │                        │
│  │ Input per language:                         │                        │
│  │   ├── ALL 9 creative direction fields       │                        │
│  │   ├── language/cultural tailoring hint      │                        │
│  │   ├── product-hero framing constraints      │                        │
│  │   └── no-text enforcement rules             │                        │
│  │                                             │                        │
│  │ Fallback: GPT Image 1.5 → DALL-E 2 →         │                        │
│  │           placeholder                       │                        │
│  │                                             │                        │
│  │  ┌────────────┐    ┌────────────┐           │                        │
│  │  │ en image   │    │ es image   │  ...      │                        │
│  │  │ (US visual │    │ (LatAm    │           │                        │
│  │  │  cues)     │    │  visual   │           │                        │
│  │  └─────┬──────┘    │  cues)    │           │                        │
│  │        │           └─────┬─────┘           │                        │
│  └────────┼─────────────────┼──────────────────┘                        │
│           │                 │                                            │
│           ▼                 ▼                                            │
│  ┌─────────────────────────────────────────────┐                        │
│  │ STAGE D: Resize + Text Overlay              │                        │
│  │                                             │                        │
│  │ Per language, per ratio (sequential):        │                        │
│  │   1. Resize hero to target (1080x1080, etc) │                        │
│  │   2. Overlay translated campaign message    │                        │
│  │   3. Composite brand logo                   │                        │
│  │   4. Save as creative_{lang}.png            │                        │
│  │                                             │                        │
│  │  en/1:1  en/9:16  en/16:9                   │                        │
│  │  es/1:1  es/9:16  es/16:9                   │                        │
│  └─────────────────────────┬───────────────────┘                        │
│                            │                                             │
│                            ▼                                             │
│  ┌─────────────────────────────────────────────┐                        │
│  │ STAGE E: Brand Compliance + Legal + Report  │                        │
│  │   • Logo presence check                     │                        │
│  │   • Dominant color analysis vs brand palette│                        │
│  │   • Prohibited words scan                   │                        │
│  │   • JSON report with all post messages      │                        │
│  └─────────────────────────────────────────────┘                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why Cumulative Matters

Each stage receives ALL previous outputs as input:

| Stage | Receives | Produces |
|-------|----------|----------|
| **A. Creative Director** | Brief + history | mood, style, scene, tone, cultural angle (9 fields, schema-enforced) |
| **B. Post Messages** | Brief + direction from A + history | localized copy per lang/ratio (schema-enforced) |
| **C. Image Gen** | Direction from A + language/cultural hints | culturally tailored image per language |
| **D. Overlay** | Image from C + translated message | final creative |

If any stage were skipped or run in isolation, the outputs would drift. The chain ensures an image of a "vibrant beach scene" isn't paired with a post about "cozy winter warmth."

### Sequence Diagram — Full Call Stack for a New Campaign

This traces the actual module calls from when a user uploads a brief to when creatives are saved. Follow the arrows left to right — each vertical bar is a module in the codebase.

```
 User     web/routes    web/utils     Pipeline        History      Director       MsgGen        ImgGen       ImgProc     TextRend      Storage
  │        jobs.py        .py       orchestrator       │         creative_       message_      image_       image_       text_           │
  │           │            │            .py            │         director.py    generator.py  generator.py processor.py renderer.py      │
  │           │            │            │               │             │              │             │            │            │            │
  │ POST brief│            │            │               │             │              │             │            │            │            │
  │──────────>│            │            │               │             │              │             │            │            │            │
  │           │ parse_     │            │               │             │              │             │            │            │            │
  │           │ brief()    │            │               │             │              │             │            │            │            │
  │           │───────────>│            │               │             │              │             │            │            │            │
  │           │ CampaignBrief          │               │             │              │             │            │            │            │
  │           │<───────────│            │               │             │              │             │            │            │            │
  │           │            │            │               │             │              │             │            │            │            │
  │           │ start_pipeline_task()   │               │             │              │             │            │            │            │
  │           │───────────>│            │               │             │              │             │            │            │            │
  │           │            │ Pipeline() │               │             │              │             │            │            │            │
  │           │            │───────────>│               │             │              │             │            │            │            │
  │           │            │            │               │             │              │             │            │            │            │
  │           │            │  run()     │               │             │              │             │            │            │            │
  │           │            │───────────>│               │             │              │             │            │            │            │
  │           │            │            │               │             │              │             │            │            │            │
  │           │            │            │ load_version  │             │              │             │            │            │            │
  │           │            │            │ _history()    │             │              │             │            │            │            │
  │           │            │            │──────────────>│             │              │             │            │            │            │
  │           │            │            │ [v1,v2 data]  │             │              │             │            │            │            │
  │           │            │            │<──────────────│             │              │             │            │            │            │
  │           │            │            │               │             │              │             │            │            │            │
  │           │            │            │ legal_check() │             │              │             │            │            │            │
  │           │            │            │──┐            │             │              │             │            │            │            │
  │           │            │            │<─┘ PASSED     │             │              │             │            │            │            │
  │           │            │            │               │             │              │             │            │            │            │
  │      ═══ FOR EACH PRODUCT (parallel via asyncio.gather) ════════════════════════════════════════════════════════════════             │
  │      ║    │            │            │               │             │              │             │            │            │            │
  │      ║    │   STAGE A  │            │               │             │              │             │            │            │            │
  │      ║    │            │            │ derive()      │             │              │             │            │            │            │
  │      ║    │            │            │──────────────────────────── >│              │             │            │            │            │
  │      ║    │            │            │               │             │ GPT-4o-mini  │             │            │            │            │
  │      ║    │            │            │               │             │ json_schema  │             │            │            │            │
  │      ║    │            │            │               │             │ (strict)     │             │            │            │            │
  │      ║    │            │            │ CreativeDirection           │              │             │            │            │            │
  │      ║    │            │            │ (9 fields,    │             │              │             │            │            │            │
  │      ║    │            │            │  schema-enforced)           │              │             │            │            │            │
  │      ║    │            │            │<─────────────────────────── │              │             │            │            │            │
  │      ║    │            │            │               │             │              │             │            │            │            │
  │      ║    │   STAGE B  │            │               │             │              │             │            │            │            │
  │      ║    │            │            │ generate_all()│             │              │             │            │            │            │
  │      ║    │            │            │ (per ratio)   │             │              │             │            │            │            │
  │      ║    │            │            │──────────────────────────────────────────> │             │            │            │            │
  │      ║    │            │            │               │             │              │ GPT-4o-mini │            │            │            │
  │      ║    │            │            │               │             │              │ json_schema │            │            │            │
  │      ║    │            │            │               │             │              │ (strict)    │            │            │            │
  │      ║    │            │            │ {(en,1:1): PostMessage,     │              │             │            │            │            │
  │      ║    │            │            │  (es,1:1): PostMessage,...} │              │             │            │            │            │
  │      ║    │            │            │<──────────────────────────────────────────│             │            │            │            │
  │      ║    │            │            │               │             │              │             │            │            │            │
  │      ║    │   STAGE C (per language)│               │             │              │             │            │            │            │
  │      ║    │            │            │               │             │              │             │            │            │            │
  │      ║    │  ┌── en ───│            │ generate()    │             │              │             │            │            │            │
  │      ║    │  │         │            │ (direction    │             │              │             │            │            │            │
  │      ║    │  │         │            │  + no-text rules)           │              │             │            │            │            │
  │      ║    │  │         │            │─────────────────────────────────────────────────────────>│            │            │            │
  │      ║    │  │         │            │               │             │              │ GPT Image 1.5 │            │            │            │
  │      ║    │  │         │            │ en hero image │             │              │             │            │            │            │
  │      ║    │  │         │            │<─────────────────────────────────────────────────────────│            │            │            │
  │      ║    │  │         │            │               │             │              │             │            │            │            │
  │      ║    │  ┌── es ───│            │ generate()    │             │              │             │            │            │            │
  │      ║    │  │         │            │ (direction    │             │              │             │            │            │            │
  │      ║    │  │         │            │  + "Spanish audience")      │              │             │            │            │            │
  │      ║    │  │         │            │─────────────────────────────────────────────────────────>│            │            │            │
  │      ║    │  │         │            │ es hero image (culturally different)       │             │            │            │            │
  │      ║    │  │         │            │<─────────────────────────────────────────────────────────│            │            │            │
  │      ║    │            │            │               │             │              │             │            │            │            │
  │      ║    │   STAGE D (per ratio, per language — sequential)     │             │            │            │            │
  │      ║    │            │            │               │             │              │             │            │            │            │
  │      ║    │  ┌─ en/1:1 │            │ resize_and_crop(en_hero, 1:1)             │             │            │            │            │
  │      ║    │  │         │            │────────────────────────────────────────────────────────────────────── >│            │            │
  │      ║    │  │         │            │ 1080x1080 image             │              │             │            │            │            │
  │      ║    │  │         │            │<──────────────────────────────────────────────────────────────────────│            │            │
  │      ║    │  │         │            │               │             │              │             │            │            │            │
  │      ║    │  │         │            │ render_text_overlay(image, "Stay Fresh...", logo)        │            │            │            │
  │      ║    │  │         │            │──────────────────────────────────────────────────────────────────────────────────> │            │
  │      ║    │  │         │            │ creative_en.png             │              │             │            │            │            │
  │      ║    │  │         │            │<─────────────────────────────────────────────────────────────────────────────────  │            │
  │      ║    │  │         │            │               │             │              │             │            │            │            │
  │      ║    │  ┌─ es/1:1 │            │ (same flow with translated message)       │             │            │            │            │
  │      ║    │  │         │            │               │             │              │             │            │            │            │
  │      ║    │  (repeats for 9:16 and 16:9)            │              │             │            │            │            │
  │      ║    │            │            │               │             │              │             │            │            │            │
  │      ║    │   STAGE E  │            │               │             │              │             │            │            │            │
  │      ║    │            │            │ brand_check() │             │              │             │            │            │            │
  │      ║    │            │            │──┐            │             │              │             │            │            │            │
  │      ║    │            │            │<─┘ PASS       │             │              │             │            │            │            │
  │      ║    │            │            │               │             │              │             │            │            │            │
  │      ═══ END PRODUCT LOOP ════════════════════════════════════════════════════════════════════════════════════════════════           │
  │           │            │            │               │             │              │             │            │            │            │
  │           │            │ save_report()              │             │              │             │            │            │            │
  │           │            │───────────>│               │             │              │             │            │            │            │
  │           │            │            │               │             │              │             │            │            │            │
  │           │            │ sync_to_storage()          │             │              │             │            │            │            │
  │           │            │─────────────────────────────────────────────────────────────────────────────────────────────────────────── >│
  │           │            │            │               │             │              │             │            │            │            │
  │           │            │ cleanup upload dir         │             │              │             │            │            │            │
  │           │            │──┐         │               │             │              │             │            │            │            │
  │           │            │<─┘         │               │             │              │             │            │            │            │
  │           │            │            │               │             │              │             │            │            │            │
  │  200 OK   │            │            │               │             │              │             │            │            │            │
  │  (job_id) │            │            │               │             │              │             │            │            │            │
  │<──────────│            │            │               │             │              │             │            │            │            │
```

**Key call patterns to note:**
- Products run in **parallel** (`asyncio.gather`) — Eco Bottle and Sport Cap process simultaneously
- Within each product, the chain is **sequential** — each stage needs the previous stage's output
- Creative direction is passed as a parameter (not shared state) to avoid race conditions between parallel products
- Languages render **sequentially** within each ratio — PIL is not thread-safe
- Ratios can process in **parallel** since each has independent images by this point
- The History module is only called once at pipeline start (not per-product)
- Storage sync and upload cleanup happen in `web/utils.py` after pipeline completes

## Version History & Creative Memory

Each pipeline run produces a versioned output directory:

```
data/output/summer-splash-2026/
├── v1/                          # First generation
│   ├── eco-bottle/
│   │   ├── 1x1/creative_en.png
│   │   ├── 1x1/creative_es.png  # Different image than en (culturally tailored)
│   │   ├── 9x16/...
│   │   └── 16x9/...
│   ├── sport-cap/...
│   ├── report.json              # Full results + post messages + direction
│   └── pipeline.log             # Debug log
├── v2/                          # Regeneration — guaranteed different
│   └── ...
└── v3/                          # Uses v1 + v2 as negative examples
    └── ...
```

On regeneration, the pipeline loads ALL previous version `report.json` files and injects them as context:

```
Creative Director (v3):
  "Previous creative directions (DO NOT repeat):
    v1: post='Dive into crystal clear hydration this summer!...'
    v2: post='Your eco-conscious companion for every adventure...'"

Post Messages (v3):
  "Post messages from previous versions (write COMPLETELY DIFFERENT):
    v1 (en/1:1): 'Dive into crystal clear hydration...'
    v1 (es/1:1): 'Sumérgete en la hidratación cristalina...'
    v2 (en/1:1): 'Your eco-conscious companion...'
    v2 (es/1:1): 'Tu compañero eco-consciente...'"
```

This ensures each version explores genuinely new creative territory.

## Module Map

| Package | Module | Responsibility | Key Interface |
|---------|--------|---------------|---------------|
| **shared/** | `models.py` | Data contracts | `CampaignBrief`, `BrandConfig`, `PipelineResult`, `PostMessage` |
| | `config.py` | Env-based settings (pydantic-settings, no prefix) | `Settings`, `get_settings()` |
| | `exceptions.py` | Exception hierarchy | `PipelineError` base, 7 specific types |
| **service/** | `pipeline/orchestrator.py` | Async orchestrator + cumulative chain | `Pipeline.run(dry_run, skip_genai, force_regenerate)` |
| | `pipeline/asset_manager.py` | Find existing hero images | `AssetManager.resolve()` -> `Path \| None` |
| | `pipeline/image_processor.py` | Resize/crop to ratio | `resize_and_crop(image, ratio)` -> `Image` |
| | `pipeline/text_renderer.py` | Text overlay + logo | `render_text_overlay(image, msg, logo)` -> `Image` |
| | `pipeline/report.py` | JSON report writer | `save_report(result, dir)` -> `Path` |
| | `integrations/creative_director.py` | AI creative direction (Stage A) | `CreativeDirector.derive()` -> `CreativeDirection` |
| | `integrations/message_generator.py` | AI post messages (Stage B) | `MessageGenerator.generate_all()` -> `dict[PostMessage]` |
| | `integrations/image_generator.py` | GPT Image 1.5 + fallback (Stage C) | `ImageGenerator.generate()` -> `(Path, source)` |
| | `integrations/storage.py` | Storage (local + S3) | `create_storage()`, `sync_to_storage()`, `delete_from_storage()` |
| | `integrations/localizer.py` | Translation (Google Translate) | `translate_text(text, lang)` -> `str` |
| | `compliance/legal_checker.py` | Prohibited words scan | `check_legal_content(msg, words)` -> `LegalCheckResult` |
| | `compliance/brand_checker.py` | Color + logo compliance | `check_brand_compliance(dir, config)` -> `BrandComplianceResult` |
| | `core/colors.py` | Shared color utilities | `hex_to_rgb(hex)` -> `(r, g, b)` |
| | `core/logger.py` | Dual console/file logging | `setup_logging(level, file)` |
| **web/** | `app.py` | FastAPI factory + middleware + static mounts | `create_app()` |
| | `state.py` | In-memory job tracking | `jobs` dict, `background_tasks` set |
| | `utils.py` | Brief parsing, asset handling, pipeline runner, serializers | `parse_uploaded_brief()`, `run_pipeline_job()`, etc. |
| | `routes/ui.py` | HTML UI + health check | `GET /`, `GET /health` |
| | `routes/jobs.py` | Job-scoped API (validate, generate, status, regen) | `POST /api/generate`, `GET /api/jobs/{id}`, etc. |
| | `routes/campaigns.py` | Campaign-scoped API (browse, download, delete) | `GET /api/campaigns`, etc. |
| **cli** | `cli.py` | Click CLI entry point | `generate()`, `validate()`, `web()` |

### Dependency Direction (Microservice Boundary)

```
  web/  ──────▶  shared/  ◀──────  service/
  (imports service/ via utils.py for Pipeline execution)
```

`shared/` is the contract layer. On microservice split:
- `shared/` becomes a published package or protobuf definitions
- `service/` becomes a standalone gRPC/HTTP service with its own Dockerfile
- `web/` becomes a BFF (backend-for-frontend) that calls the service API instead of importing Pipeline directly

## LLM Integration Map

Three LLM touchpoints, each with a distinct role. Stages A and B use OpenAI's structured outputs (`json_schema` with `strict: true`) to enforce exact response schemas at the API level.

| Stage | Model | Calls per product | Purpose | Temperature | Response Format |
|-------|-------|-------------------|---------|-------------|-----------------|
| **Creative Director** | GPT-4o-mini | 1 | Derive mood/style/tone/cultural direction | 1.2 | `json_schema` (strict, 9 required fields) |
| **Post Messages** | GPT-4o-mini | 1 per ratio | Generate all language variants | 0.8 (1.2 on regen) | `json_schema` (strict, variants array) |
| **Image Generation** | GPT Image 1.5 | 1 per language | Culturally tailored product hero image | N/A | b64 PNG (images API) |

For 2 products, 3 ratios, 2 languages: **2 director calls + 6 message calls + 4 image calls = 12 API calls total.**

### Structured Output Schemas

**Creative Director** — enforces all 9 fields as required strings:
```json
{
  "type": "json_schema",
  "json_schema": {
    "name": "creative_direction",
    "strict": true,
    "schema": {
      "properties": {
        "visual_style": {"type": "string"},
        "lighting": {"type": "string"},
        "composition": {"type": "string"},
        "scene_setting": {"type": "string"},
        "mood": {"type": "string"},
        "color_palette_hint": {"type": "string"},
        "copy_tone": {"type": "string"},
        "copy_hook": {"type": "string"},
        "cultural_angle": {"type": "string"}
      },
      "required": ["visual_style", "lighting", "composition", "scene_setting",
                    "mood", "color_palette_hint", "copy_tone", "copy_hook", "cultural_angle"],
      "additionalProperties": false
    }
  }
}
```

**Post Messages** — enforces variants array with typed fields:
```json
{
  "type": "json_schema",
  "json_schema": {
    "name": "post_messages",
    "strict": true,
    "schema": {
      "properties": {
        "variants": {
          "type": "array",
          "items": {
            "properties": {
              "language": {"type": "string"},
              "aspect_ratio": {"type": "string"},
              "platform": {"type": "string"},
              "text": {"type": "string"},
              "hashtags": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["language", "aspect_ratio", "platform", "text", "hashtags"],
            "additionalProperties": false
          }
        }
      },
      "required": ["variants"],
      "additionalProperties": false
    }
  }
}
```

**Image Generation** — cannot use structured outputs (images API returns binary data, not JSON). Text-in-image is mitigated via prompt engineering: no-text rules at top and bottom of prompt, campaign copy excluded from image prompts entirely.

### Image Generation Model Selection (2026)

We use OpenAI's **GPT Image 1.5** (`gpt-image-1.5`) as the primary image model. It replaced DALL-E 3 in 2025 and leads quality benchmarks for product photography. Configurable via the `IMAGE_MODEL` env var.

| Model | Provider | Price/Image | Quality (Elo) | Best For |
|-------|----------|-------------|---------------|----------|
| **GPT Image 1.5** | OpenAI | $0.04 | 1,264 | Production default (used here) |
| GPT Image 1 | OpenAI | $0.04 | ~1,200 | Previous default, still supported |
| **Flux 2 Pro v1.1** | Black Forest Labs | ~$0.03 | 1,265 | Comparable quality, different provider |
| **Imagen 4 Standard** | Google | $0.04 | ~1,200 | Good text rendering, Google ecosystem |
| **Imagen 4 Fast** | Google | $0.02 | ~1,150 | Best price/quality for high volume |
| DALL-E 3 (legacy) | OpenAI | $0.04 | ~1,100 | Deprecated — replaced by GPT Image 1.5 |
| Stable Diffusion 3.5 | Stability AI | Free | ~1,050 | Self-hosted, fine-tunable |

**Why GPT Image 1.5**: Same OpenAI SDK and API key we already use for chat completion — zero infrastructure change. Higher quality than DALL-E 3 for product photography. Fallback chain: GPT Image 1.5 -> DALL-E 2 -> local placeholder.

### GenAI Fallback Chain (Images)

```
GPT Image 1.5  ──(3 retries)──▶  DALL-E 2  ──(1 attempt)──▶  Placeholder
  │                                │                            │
  │ $0.04/img                      │ $0.02/img                  │ Free
  │ Highest quality                │ Good quality               │ Gradient + text
  │ Native ratios                  │ Square only                │ Brand colors
  └────────────────────────────────┴────────────────────────────┘
                    Pipeline ALWAYS produces output
```

## Web UI & REST API

FastAPI application factory (`src/web/app.py`) with route-based architecture. Routes are organized into separate modules using `APIRouter` and settings are injected via `Depends(get_settings)`.

```
src/web/
├── app.py              # Factory: middleware, static mounts, router registration
├── state.py            # Shared in-memory state (jobs dict, background tasks set)
├── utils.py            # Brief parsing, asset handling, pipeline runner, serializers
├── routes/
│   ├── ui.py           # GET / (HTML), GET /health
│   ├── jobs.py         # /api/validate, /api/generate, /api/jobs/...
│   └── campaigns.py    # /api/campaigns/...
├── templates/          # Jinja2 HTML templates
└── static/             # CSS, JS
```

### Job-Based Endpoints (In-Memory, Current Session)

```
POST /api/validate                        Validate brief (no generation)
POST /api/generate                        Upload brief + assets, start job
GET  /api/jobs/{id}                       Poll status + get results
GET  /api/jobs/{id}/versions              List versions for this job's campaign
GET  /api/jobs/{id}/versions/N/download   Download version as zip
DELETE /api/jobs/{id}/versions/N          Delete a version (local + S3)
POST /api/jobs/{id}/regenerate            Create new version with fresh AI content
GET  /api/jobs                            List all jobs
```

### Campaign-Based Endpoints (Disk-Based, Survive Restarts)

These read directly from `data/output/` and work independently of in-memory job state. They survive server restarts, making them the primary API for integrations.

```
GET    /api/campaigns                              List all campaigns on disk
GET    /api/campaigns/{slug}                       Campaign detail + all versions
GET    /api/campaigns/{slug}/versions/{n}          Full results for a version
DELETE /api/campaigns/{slug}/versions/{n}          Delete a version (local + S3)
GET    /api/campaigns/{slug}/versions/{n}/download Download version as zip
```

### Static Content

```
GET  /                                    HTML upload page + campaign browser
GET  /static/...                          CSS, JS
GET  /output/...                          Serve generated creative images
GET  /health                              Health check
GET  /docs                                Swagger UI (auto-generated by FastAPI)
```

### Web UI Features

- **Campaign browser** — "My Campaigns" panel lists all campaigns on disk with version buttons. Auto-refreshes after generation. Works across server restarts.
- **Preview** — creative images paired with AI-generated post messages and platform icons
- **Version switching** — dropdown to view any version of any campaign
- **Download** — zip package per version with images + post message text files
- **Regenerate** — creates new version with fresh AI content (version history context ensures no repetition)
- **Delete** — remove any version locally and from S3 (with confirmation)

### Headless API Usage (No UI Required)

```python
import httpx

# Generate with product hero images
resp = httpx.post("/api/generate",
    files={"brief_file": open("brief.json", "rb")},
    data={"product_asset_thermal-mug": open("mug.png", "rb")}
)
job_id = resp.json()["job_id"]

# Poll
while httpx.get(f"/api/jobs/{job_id}").json()["status"] == "running":
    time.sleep(2)

# Browse all campaigns (works after restart)
campaigns = httpx.get("/api/campaigns").json()

# View version
result = httpx.get("/api/campaigns/summer-splash-2026/versions/1").json()

# Download zip
httpx.get("/api/campaigns/summer-splash-2026/versions/1/download")

# Regenerate
httpx.post(f"/api/jobs/{job_id}/regenerate")
```

## Storage

Pluggable storage backend via `StorageBackend` abstract class:

```
StorageBackend (ABC)
├── save(local_path, destination_key) → str
├── list_assets(prefix) → list[str]
├── delete(prefix) → int
├── get_uri(key) → str
│
├── LocalStorage — saves to data/output/ directory (default)
└── S3Storage    — uploads to AWS S3 bucket (credentials from .env)
```

**Shared utilities** ensure consistent behavior across CLI and web:
- `create_storage(settings)` — factory returning the correct backend
- `sync_to_storage(settings, result)` — uploads assets after pipeline run (no-op for local)
- `delete_from_storage(settings, campaign_slug, version)` — removes assets on version delete (no-op for local)

Both CLI and web use `sync_to_storage` after generation and `delete_from_storage` on version deletion. AWS credentials are read from `.env` and passed directly to boto3.

## Concurrency Model

```
Products ──────── asyncio.gather() ──────── parallel
  │
  └─ Per product (sequential cumulative chain):
       Stage A: Creative Director ──────── 1 LLM call (json_schema strict)
       Stage B: Post Messages ──────────── 1 LLM call per ratio (json_schema strict)
       Stage C: Image Gen per language ──── 1 GPT Image 1.5 call per language (sequential)
       Stage D: Resize + overlay ────────── sequential per language (PIL not thread-safe)
       Stage E: Compliance + report ─────── synchronous
```

Products run in parallel. Within each product, the cumulative chain is sequential by design — each stage needs the previous stage's output. Creative direction is passed as a parameter (not shared instance state) to prevent race conditions between parallel products.

## Configuration

All settings via environment variables (no prefix), loaded from `.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | (required) | OpenAI API key (GPT Image 1.5 + GPT-4o-mini) |
| `IMAGE_MODEL` | `gpt-image-1.5` | Primary image generation model |
| `DALLE_QUALITY` | `standard` | Image quality: `standard` or `hd` |
| `IMAGE_STYLE` | `vivid` | Image style: `vivid` or `natural` |
| `LOG_LEVEL` | `INFO` | Console log level |
| `MAX_RETRIES` | `3` | API retry attempts |
| `STORAGE_BACKEND` | `local` | `local` or `s3` |
| `AWS_ACCESS_KEY_ID` | | AWS access key for S3 |
| `AWS_SECRET_ACCESS_KEY` | | AWS secret key for S3 |
| `S3_BUCKET` | | S3 bucket name |
| `S3_PREFIX` | `campaigns/` | S3 key prefix |
| `S3_REGION` | `us-east-1` | AWS region |
| `WEB_HOST` | `0.0.0.0` | Web server bind host |
| `WEB_PORT` | `8080` | Web UI server port |
| `CORS_ORIGINS` | `*` | CORS allowed origins |

## Logging

Dual-handler: Rich console (INFO) for user progress + file handler (DEBUG) for full diagnostics including LLM prompts and creative direction outputs. API keys are never logged. File goes to `data/output/<campaign>/v<N>/pipeline.log`.

## Testing

126 tests, all GenAI and S3 calls mocked. Tests run during Docker build — broken code never ships.

```bash
pytest tests/ -v --cov=src
```

## Docker

```
Dockerfile          → Multi-stage: test stage (runs pytest) + production stage
docker-compose.yml  → Two services: web (default), pipeline (cli profile)
.dockerignore       → Excludes .env, venv, .git, output, uploads
```

- Tests gate the build: `COPY --from=test` ensures production image can't build if tests fail
- Runs as non-root `appuser` (UID 1000)
- Health check at `/health`
- Single `./data` volume mount for all I/O

## Scalability & Microservice Transition

### Current State (Monolith)

Single process. Web UI and pipeline engine share memory.

```
┌─────────────────────────────────────────────┐
│              Single Process                 │
│   web/ ──▶ shared/ ◀── service/             │
│   FastAPI     Contracts    Pipeline Engine   │
└─────────────────────────────────────────────┘
```

### Target State (Microservices)

```
┌──────────────┐    HTTP/gRPC     ┌──────────────────┐
│   Web BFF    │ ───────────────▶ │  Pipeline Service │
│  (FastAPI)   │                  │  (async workers)  │
│  src/web/    │                  │  src/service/     │
└──────┬───────┘                  └────────┬──────────┘
       │              ┌────────┐            │
       └─────────────▶│ shared │◀───────────┘
                      │ models │
                      └────┬───┘
              ┌────────────┼────────────┐
        ┌─────▼──┐   ┌────▼────┐  ┌────▼────┐
        │  S3    │   │  Redis  │  │ Postgres│
        │ Assets │   │  Queue  │  │  Jobs   │
        └────────┘   └─────────┘  └─────────┘
```

### Transition Steps

1. **Shared contracts** — already done (`src/shared/`)
2. **Message queue** — replace `Pipeline.run()` call with queue enqueue
3. **Deploy service/** — standalone worker consuming from queue
4. **Deploy web/** — standalone BFF calling queue
5. **Scale independently** — web behind load balancer, workers scale on queue depth

| Component | Changes on split | Stays the same |
|-----------|-----------------|----------------|
| `shared/` | Published as package or proto | Models, config, exceptions |
| `service/` | Gets queue consumer, own Dockerfile | All pipeline + LLM chain logic |
| `web/` | Calls queue instead of Pipeline | Routes, templates, static assets |
| Storage | Already decoupled (S3) | Interface unchanged |

## Key Design Decisions

1. **Cumulative LLM chain** — Creative Director → Post Messages → Image Generation. Each stage builds on all previous outputs for coherent creatives.
2. **Structured LLM outputs** — All chat completions use OpenAI's `json_schema` response format with `strict: true`, enforcing exact schemas at the API level. No `.get()` fallbacks needed.
3. **Per-language images** — different audiences respond to different visual cues. Each language gets its own culturally tailored image via GPT Image 1.5.
4. **No-text-in-image enforcement** — campaign copy is excluded from image prompts entirely. Text rules are placed at top and bottom of every prompt. Text overlay is done programmatically via PIL.
5. **Single-call structured messages** — one GPT-4o-mini call returns ALL language/ratio variants in JSON. Eliminates language drift and reduces API costs.
6. **Version history as negative examples** — previous versions' outputs are fed to LLM prompts so regeneration produces genuinely different creative angles.
7. **Product-hero framing** — every image prompt enforces product as 60%+ of frame. Prevents lifestyle scenes where the product gets lost.
8. **Three-tier image fallback** — GPT Image 1.5 → DALL-E 2 → placeholder. Pipeline always produces output.
9. **FastAPI dependency injection** — settings injected via `Depends(get_settings)` across all routes. Route-based architecture with `APIRouter` modules.
10. **Unified storage operations** — `sync_to_storage()` and `delete_from_storage()` are called from both CLI and web, keeping local and S3 state consistent.
11. **Dual API layers** — job-based endpoints for active sessions + campaign-based endpoints for persistent disk access. Campaign endpoints survive server restarts and power headless integrations.
12. **Race condition prevention** — creative direction is passed as a parameter through the chain, not stored as shared instance state, preventing cross-contamination between parallel product pipelines.
13. **Upload cleanup** — temporary upload directories are removed in a `finally` block after pipeline completion, whether the job succeeds or fails.
14. **Microservice-ready** — `shared/` contract layer, clean dependency direction, no circular imports.
