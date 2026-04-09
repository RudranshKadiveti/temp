# Technical Dossier: Distributed Scraper Platform

## 1) Project Purpose and Operating Model
This codebase implements a universal web extraction platform that can run as:
- A CLI scraper.
- A FastAPI service with dashboard UI.
- A browser-extension-triggered extraction flow via native messaging.

Primary goal:
- Extract structured records from heterogeneous websites with a layered strategy.
- Normalize and validate records.
- Export records to multiple formats.
- Provide preview/download APIs and a browser dashboard.

## 2) Repository Topology and Responsibilities
Top-level concerns:
- Orchestration and interfaces: main.py, api.py.
- Agent and extraction logic: agents/, extractors/, strategies/.
- Runtime controls: core/.
- Data quality and streaming pipeline: pipelines/.
- Output formatting: exporters/, utils/data_converter.py.
- Frontend UI: templates/index.html.
- Browser extension bridge: extension/.
- Infrastructure and deployment: docker-compose.yml, Dockerfile.
- Storage folders: data/output, data/raw_html, data/logs.

Important directories:
- agents/: High-level task orchestrator (universal agent).
- core/: Browser lifecycle, classification, pagination, rate control, runtime models.
- extractors/: JSON-LD/meta extraction, DOM clustering, LLM fallback, rule engines.
- pipelines/: Data streaming and quality guard.
- exporters/: Multi-format writer and append/version behavior.
- scraper/: Legacy distributed crawler sub-system (queue, parser, storage stack).

## 3) Runtime Entrypoints
### main.py
Modes:
- API server: python main.py --api
- CLI single run: python main.py URL QUERY --pages N --format csv|json|jsonl|xlsx|parquet
- Config-file run: python main.py --config config.yaml
- Scheduled loop: python main.py URL QUERY --schedule N

Key behavior:
- Loads .env via dotenv.
- Builds UniversalScraperAgent.
- Normalizes missing/placeholder API keys.
- Runs async extraction task.
- Exposes --reload-api to explicitly enable uvicorn reload for development.

### api.py
FastAPI app with in-memory job tracking and background processing.
- POST /api/scrape
- GET /api/status/{job_id}
- GET /api/jobs
- GET /api/preview/{job_id}
- GET /api/download/{job_id}
- GET /api/export/{job_id}
- GET /api/formats/{job_id}
- GET /

Operational model:
- Jobs are queued in RAM dictionary.
- Background task executes agent.run_task in a fresh event loop.
- Completed status is set only when output file exists and total_records > 0.
- Failed status is set for extraction with zero rows or missing output artifact.

## 4) Core Extraction Architecture
### Universal agent orchestration
File: agents/universal_agent.py
Pipeline loop per page:
1. Navigate and classify site type.
2. Apply strategy-level query/filters.
3. Attempt Layer 1 extraction (field engine: JSON-LD/meta).
4. If no emission, attempt API discovery extraction.
5. If no emission, attempt Layer 2 extraction (DOM clustering and parsing).
6. If no emission, attempt Layer 3 extraction (LLM fallback).
7. Send candidate records to DataPipeline (quality, dedupe, export).
8. Rate-control update and pagination step.

Returned task payload includes:
- total_records
- pages_visited
- api_discovery_log
- metrics
- site_type
- quality_report
- output_path

### Site classification
File: core/site_classifier.py
Classification methods:
- URL keyword hints for ecommerce/directory/article/dashboard.
- DOM signal fallback:
  - price-related terms
  - article terms
  - cards/tables/forms count heuristics

### Strategy layer
File: strategies/ecommerce.py
StrategyFactory maps SiteType to strategy class.
Strategy responsibilities:
- Build extraction schema for site-type.
- Apply URL-level filter params.
- Optional DOM-level filtering by query keyword.
- Safety guard in DOM filter avoids hiding almost all candidate blocks.

## 5) Extraction Layers in Detail
### Layer 1: deterministic field extraction
File: extractors/field_engine.py
Sources and weighting:
- json_ld: high confidence.
- microdata/meta/dom/regex: descending confidence.

Capabilities:
- Parse JSON-LD script blocks and @graph nodes.
- Parse meta tags for og/twitter/product fields.
- Derive price/currency/rating/reviews/availability.
- Compute row confidence with field-level weighted score.
- Add source trace metadata per field.

### API discovery path
Files: core/browser_manager.py + agents/universal_agent.py
- Captures fetch/xhr requests and JSON responses from page traffic.
- Stores discovered API events with URL/status/content-type.
- Attempts extraction from discovered payload envelopes.

### Layer 2: DOM clustering and parsing
File: extractors/dom_clustering.py
- JS in page context clusters repeated containers.
- Scores container groups by links/images/price-hints/text density.
- Produces candidate rows with text, links, images, table cells.
- parse_item uses schema keys and regex hints to map candidate values.

### Layer 3: LLM fallback
File: extractors/llm_fallback.py
- Triggered only when deterministic layers emit zero rows.
- Uses provided schema JSON and raw HTML text windows.
- Intended as ambiguity/failure fallback.

### Optional Groq structuring
File: extractors/groq_structurer.py
- Batches records for product-name/brand cleanup.
- Used for ecommerce records when key is available.

## 6) Browser, Anti-Bot, and Pagination
### Browser manager
File: core/browser_manager.py
- Playwright chromium lifecycle.
- Anti-bot launch args and navigator spoof.
- Rotating user agents and varied viewport profiles.
- Tracks API network events.
- Retries navigation with backoff.
- Stores persistent session state optionally.

### Rate control
File: core/rate_control.py
- Maintains adaptive delays based on:
  - observed response times
  - bot-signal detection
- Adds jitter to reduce repeatable timing patterns.

### Pagination
File: core/pagination.py
- Next button selectors.
- Fallback handling for varied pagination UIs.
- Stops when no further navigation action succeeds.

## 7) Data Pipeline and Quality Controls
### Data pipeline
File: pipelines/data_stream.py
Responsibilities:
- Accept batch records from extraction layers.
- Invoke QualityGuard for normalization/validation.
- Maintain dedupe set and total_processed counter.
- Persist fixed canonical schema file.
- Append/write records through ExportManager.
- Track price-change style log entries.

Artifacts written:
- data/output/latest_schema.json
- data/output/change_log.jsonl
- exported session file(s)

### Quality guard
File: pipelines/quality_guard.py
Canonical columns:
- name, price, currency, rating, reviews_count, availability,
  url, image_url, source, scraped_at, confidence

Validation and cleaning:
- Normalizes currency and availability.
- Parses numeric values and strips noisy text.
- Cleans titles (sponsored/deal/noise stripping).
- Confidence baseline inference when confidence not provided:
  - name + (price or url) => high baseline.
  - name only => medium baseline.
- Enforces minimum confidence threshold.
- Deduplicates by URL or name+price fallback key hash.

Quality metrics:
- extraction_success_rate
- avg_confidence_score
- duplicate_rate
- null_field_percentage per canonical field

Quality artifacts:
- data/output/failed_rows.json
- data/output/extraction_report.json
- data/output/clean_sample.json

## 8) Export and Conversion Subsystem
### Export manager
File: exporters/manager.py
Supported write formats:
- csv
- json
- jsonl
- xlsx (internally excel mode)
- parquet

Behavior:
- Session-based filename prefix: scrape_session_YYYYMMDD_HHMMSS
- Auto-version suffix if file exists or lock conflict.
- Append mode for each format with specific implementation.
- Chunked write path for larger payloads.

### Data converter
File: utils/data_converter.py
Features:
- Convert source output to target format for download/export endpoint.
- CSV and JSON preview helpers with row limit.
- JSON-safe conversion for preview payloads (NaN/NaT -> null).
- Conversion paths include CSV, JSON, JSONL, XLSX, Parquet.

## 9) API Layer: Contracts and Semantics
### POST /api/scrape
Request body:
- url
- query
- pages
- format
- min_price
- max_price
- brand
- min_rating
- headless
- debug_snapshots

Response:
- job_id

### GET /api/status/{job_id}
Returns job metadata including state, counters, metrics, and output path.

### GET /api/jobs
Returns last 50 jobs, sorted by created_at descending.

### GET /api/preview/{job_id}?limit=1..500
Returns:
- columns
- row_count
- data[]
- total_columns
- job_id
- site_type

### GET /api/download/{job_id}?format=...
- Validates completed job + output file existence.
- Returns original file if format matches.
- Converts then returns when format differs.

### GET /api/export/{job_id}?target_format=...
- Explicit conversion endpoint.

### GET /api/formats/{job_id}
Returns available format list and metadata.

## 10) Dashboard Frontend
File: templates/index.html
Main UI capabilities:
- Submit scrape jobs.
- Poll and render recent job list.
- Show status badges and totals.
- Preview modal with table rendering.
- Download menu with per-format options.

Client flow:
- startExtraction sends POST /api/scrape.
- refreshJobs polls /api/jobs every 5 seconds.
- previewData calls /api/preview/{job_id}.
- downloadData calls /api/download/{job_id}?format=...

## 11) Browser Extension Integration
Files:
- extension/manifest.json
- extension/background.js
- extension/popup.js
- extension/popup.html

Flow:
- Popup collects query/filters/format.
- Sends message to background worker.
- Background uses chrome.runtime.connectNative("com.ai_scraper.host").
- Payload is forwarded to native Python host.

Notes:
- Requires native messaging host to be installed and running.
- Returns async response back to popup.

## 12) Infrastructure and Deployment
### docker-compose.yml
Services:
- app
- worker
- postgres
- redis
- elasticsearch

Health checks:
- postgres via pg_isready
- redis via redis-cli ping
- elasticsearch via curl on 9200

### Dockerfile
- Base: python:3.10-slim
- Installs dependencies from requirements.txt
- Default CMD is uvicorn main:app

Important technical mismatch:
- main.py currently does not expose app object for uvicorn main:app.
- Recommended container CMD target should be api:app unless main.py defines app.

## 13) Configuration and Environment Variables
### Runtime config loader
File: core/config_loader.py
- Supports YAML or JSON config files.
- Maps raw keys into RuntimeConfig and FilterConfig.

### .env categories
File: .env
Contains sections for:
- LLM providers and models
- Database and Redis and Elasticsearch
- Scraper controls
- anti-bot toggles
- LLM fallback toggles
- logging controls
- API host/port and CORS
- feature flags

Security observation:
- .env currently stores plaintext API key material.
- Production-safe handling should rotate exposed keys and move secrets to secure secret manager.

## 14) Logging and Observability
File: utils/logger.py
- Creates named logger with INFO level.
- Writes to stdout and data/logs/scraper_engine.log.
- Format: timestamp | level | logger | message.

Agent metrics emitted in result and job payload:
- records_per_sec
- llm_calls
- dom_batches
- fallback_batches
- api_batches
- errors
- extraction_success_rate
- avg_confidence_score
- duplicate_rate

## 15) Data and Artifact Inventory
### Primary output files
- data/output/scrape_session_*.csv|json|jsonl|xlsx|parquet

### Quality files
- data/output/clean_sample.json
- data/output/clean_sample_10_rows.json
- data/output/failed_rows.json
- data/output/extraction_report.json
- data/output/latest_schema.json
- data/output/change_log.jsonl

### Raw cache
- data/raw_html/*.html

### Session/log files
- data/logs/scraper_engine.log
- data/logs/sessions/* when persistent session enabled

## 16) Failure Modes and Recovery Behavior
Common failure classes:
- Site returns anti-bot or challenge pages.
- No extraction layer emits valid records.
- Output write blocked by file lock.
- Preview serialization errors from NaN payloads.
- Missing keys for optional LLM paths.

Recovery behavior in code:
- Navigation retry with exponential backoff.
- Layered fallback order to maximize non-LLM extraction first.
- Adaptive delay increase under suspected bot pressure.
- Versioned output write on lock conflicts.
- Job status forced to failed when no data/no file.

## 17) Current Functional Feature Set
Implemented features:
- Universal site classification with multiple site-type strategies.
- Layered extraction (JSON-LD/meta -> API discovery -> DOM -> LLM fallback).
- Quality normalization, dedupe, confidence gating.
- Multi-format output and conversion.
- FastAPI with job status polling and data preview/download.
- Dashboard with live queue and modal preview.
- Extension pathway through native messaging.
- Dockerized supporting services for Redis/Postgres/Elasticsearch.

## 18) Current Constraints and Gaps
Known technical constraints:
- Job metadata storage is in-memory only.
- Restart of API process drops current job table.
- Distributed worker path in compose is present, but operational queue integration in api.py path is limited.
- Dockerfile default command target likely mismatched with code structure.
- Some legacy scraper/ submodules are present but not the primary execution path for current API flow.

## 19) Recent Stabilization Changes Reflected in Code
Stabilization improvements now present:
- Completed/failed job state logic tightened around zero-record runs.
- Output-path existence checks before completed state.
- JSON and JSONL exporter behavior separated correctly.
- DOM keyword filtering guard to avoid over-filtering page content.
- Preview NaN-safe conversion path for DataFrame-derived responses.
- API default startup without auto-reload unless --reload-api is used.

## 20) Practical Operator Playbook
Recommended run sequence:
1. Start infra if needed: docker-compose up -d postgres redis elasticsearch
2. Start API: python main.py --api
3. Open dashboard: http://localhost:8000
4. Submit URL/query and monitor /api/jobs or dashboard row status.
5. After completion, use preview and download endpoints.

Direct API quick checks:
- POST /api/scrape -> get job_id
- Poll GET /api/status/{job_id}
- On completed, call GET /api/preview/{job_id}?limit=50
- Download with GET /api/download/{job_id}?format=csv|json|jsonl|xlsx|parquet

## 21) Technical Summary
This platform is a layered, deterministic-first extraction engine with LLM fallback and data-quality enforcement, exposed through both API and UI, with strong export/preview ergonomics and practical anti-bot controls. The system is modular and production-oriented in design, with remaining hardening opportunities around persistent job state, full distributed queue wiring, and container command alignment.
