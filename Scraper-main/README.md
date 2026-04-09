# Distributed Scraper Platform

A production-grade, distributed web scraping platform built with Python, `asyncio`, Redis, PostgreSQL, and Elasticsearch. Designed to handle ~10,000+ pages/day with structured data extraction, automatic content detection, fault tolerance, and deduplication.

## 🧠 System Architecture

```text
                                        +-------------------+
                                        |                   |
                                        |  FastAPI (API)    |
                                        |                   |
                                        +---------+---------+
                                                  |
+-------------------+                   +---------v---------+
|                   |                   |                   |
|  Scheduler (cron) +------------------->    Redis Queue    |
|                   |                   |   (crawl_jobs)    |
+-------------------+                   +---------+---------+
                                                  |
                                        +---------v---------+
                                        |                   |
                                        |  Async Crawlers   | <--- Anti-Bot Layer (UA rotation, Delays)
                                        |   (aiohttp x N)   |
                                        +---------+---------+
                                                  | [Raw HTML]
                                        +---------v---------+
                                        |                   |
                                        |  Data Pipeline    |
                                        |                   |
                                        +---------+---------+
                                                  |
           +--------------------------------------+--------------------------------------+
           |                                      |                                      |
+----------v----------+                +----------v----------+                +----------v----------+
|                     |                |                     |                |                     |
|  Content Detector   |                |  Content Detector   |                |  Content Detector   |
|   (Article)         |                |   (Product)         |                |   (Listing)         |
+----------+----------+                +----------+----------+                +----------+----------+
           |                                      |                                      |
           v                                      v                                      v
+---------------------+                +---------------------+                +---------------------+
|                     |                |                     |                |                     |
|  Article Parser     |                |  Product Parser     |                |  Listing Parser     |
|                     |                |                     |                |                     |
+----------+----------+                +----------+----------+                +----------+----------+
           |                                      |                                      |
           |                           [Structured Data Validation]                      | (child URLs inserted)
           |                                      |                                      +--------> Redis Queue
           +------------------+-------------------+
                              |
                     +--------v---------+
                     |                  |
                     |  Storage Layer   |
                     |                  |
                     +---+-------+---+--+
                         |       |   |
            +------------+       |   +--------------------+
            |                    |                        |
+-----------v-----------+ +------v------+ +---------------v---------------+
|                       | |             | |                               |
| PostgreSQL (Metadata) | | Raw HTML FS | | Elasticsearch (Search Index)  |
|                       | |             | |                               |
+-----------------------+ +-------------+ +-------------------------------+
```

## 🚀 Features

*   **Distributed Async Crawling**: Utilizes `asyncio` and `aiohttp` for high-concurrency non-blocking I/O.
*   **Message Broker queuing**: Uses Redis for task distribution, deduplication, and a Dead-Letter Queue (DLQ).
*   **Auto Content Detection**: Classifies targets dynamically into Product, Listing, Article, or Unknown using DOM heuristics and metadata (JSON-LD).
*   **Modular Parsing Engine**: Strictly separated layer implementing structured schemas (Pydantic).
*   **Multi-layered Storage**:
    *   **PostgreSQL**: Metadata and structured data source of truth.
    *   **Elasticsearch**: Fast text search indexing.
    *   **File System**: Raw HTML dump for archival and re-parsing.
*   **Fault Tolerance & Anti-Bot**: Rotating User-Agents, configurable delays, and robust retry logic.
*   **API Layer**: FastAPI application to insert scraping jobs and query the current status.
*   **Data Preview & Multi-Format Export**: Preview completed jobs and download/convert output as CSV, JSON, JSONL, XLSX, or Parquet.
*   **Dockerized setup**: Easily deployable with `docker-compose`.

## 🛠 Project Structure

```text
/
├── docker-compose.yml       # Infrastructure
├── Dockerfile               # Container build
├── main.py                  # API and App entrypoint
├── requirements.txt         # Dependencies
└── scraper/                 # Core domain
    ├── config/              # Configuration (Pydantic Settings)
    ├── core/                # Queue management, Scheduler
    ├── crawlers/            # Async fetchers, Anti-bot strategies
    ├── parsers/             # Domain specific extractors & Pydantic schemas
    ├── pipelines/           # Execution workflow (Fetch -> Parse -> Store)
    ├── storage/             # PostgreSQL schema, ES index, FS writes
    └── utils/               # Structured logging, hashing for deduplication
```

## ⚙️ Setup Instructions

### 1. Prerequisites
*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/)

### 2. Standup Infrastructure
The application relies on Redis, PostgreSQL, and Elasticsearch.
```bash
docker-compose up -d postgres redis elasticsearch
```

### 3. Run the App
**Via Docker (Recommended)**
```bash
# Run API
docker-compose up -d app

# Run Worker
docker-compose up -d worker
```

**Local Development**
```bash
python -m venv venv
source venv/bin/activate  # (Windows: venv\Scripts\activate)
pip install -r requirements.txt

# Run main API server (Dashboard at http://localhost:8000):
python main.py --api

# Run worker (background job processor):
python main.py --worker

# Run scheduler (periodic job creator):
python main.py --scheduler

# Run CLI scraper (direct from command line):
python main.py "https://example.com" "search query" --pages 5 --format csv
```

## 🔌 API Quick Reference

Base URL: `http://localhost:8000`

*   `POST /api/scrape`
    *   Submit a scraping job (returns `job_id`).
*   `GET /api/status/{job_id}`
    *   Poll a single job state (`queued`, `processing`, `completed`, `failed`).
*   `GET /api/jobs`
    *   List the latest jobs (up to 50).
*   `GET /api/preview/{job_id}?limit=50`
    *   Preview extracted rows in JSON (limit range: 1-500).
*   `GET /api/download/{job_id}?format=csv|json|jsonl|xlsx|parquet`
    *   Download completed output in the requested format.
*   `GET /api/export/{job_id}?target_format=csv|json|jsonl|xlsx|parquet`
    *   Convert completed output to another format and return file.
*   `GET /api/formats/{job_id}`
    *   Get available formats and output metadata for a completed job.

For full request/response examples, see `API_ENDPOINTS.md`.

## 📈 How to Scale
This platform is built with horizontal scaling in mind:

1. **Workers scale linearly**: You can spin up as many worker nodes as needed.
    ```bash
    docker-compose up -d --scale worker=5
    ```
2. **Kubernetes (Future Integration)**: The architecture natively supports Kubernetes deployments. The `worker` containers can be mapped to a Deployment using a Horizontal Pod Autoscaler (HPA) targeting CPU utilization or Queue Depth (using KEDA based on Redis lists length).
3. **Database limits**: Once workers max out PostgreSQL connections, a connection pooler like `PgBouncer` should be placed between the workers and the database.

## 🧭 Future Improvements
*   **Playwright / Puppeteer Headless cluster fallback**: Add an optional layer for rendering dynamic Single-Page Applications (SPAs) before processing the HTML.
*   **Proxy Rotation & Orchestration**: Integrate services like BrightData or proxy rotators when blocking rules get aggressive.
*   **Kubernetes Helm Chart**: Migrate from `docker-compose` to Kubernetes Helm files.
*   **Grafana Dashboard**: Monitor Redis queue lengths and total pages parsed successfully per minute.
