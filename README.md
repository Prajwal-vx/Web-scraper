# NEXUS SCRAPE AI

> **Production-Oriented AI-Powered Web Scraping & Data Intelligence Platform**

NEXUS SCRAPE AI is an enterprise-grade web data extraction and monitoring platform. It combines traditional rule-based web scraping, headless JavaScript browser rendering via Playwright, zero-dependency heuristic & LLM schema generation, real-time job execution streaming, data cleaning, automated quality scoring, and Scrape-to-RAG vector ingestion.

---

## 🌟 Key Features

- **SSRF Hardening & Target Validation**: Strict validation against loopback (`127.0.0.1`), private RFC1918 subnets, link-local addresses, and cloud instance metadata (`169.254.169.254`). Re-validates every redirect hop.
- **Dual Extraction Modes**:
  - **Fast HTTP**: High-throughput HTTP client with polite delays and streaming response size bounds (10 MB cap).
  - **Browser Worker (Playwright)**: Isolated headless Chromium executing JavaScript with route-level network interception.
- **Compliance & Ethical Crawling**: Automatically queries `robots.txt`, honors `Crawl-delay`, respects `Retry-After` on HTTP 429, discovers XML sitemaps, and limits domain concurrency.
- **Visual Selector Builder**: Test CSS and XPath selectors live against retrieved DOM elements with sample extraction values.
- **AI Schema Autopilot**: Automatically proposes schemas and deterministic CSS selectors based on natural language instructions (e.g. *"Extract article title, author, date, and link"*). Includes a local heuristic engine that works out-of-the-box without paid API keys.
- **Data Intelligence & Cleaning**:
  - Text whitespace trimming, HTML stripping, case conversion.
  - Type normalization (currencies to float, numbers to int, dates to ISO-8601 `YYYY-MM-DD`, relative URLs to canonical absolute URLs).
  - Deduplication by primary key fields or content hashes.
- **Data Quality Score (0–100%)**: Transparent audit scoring based on Completeness (40%), Type Validity (35%), and Record Uniqueness (25%) with letter grades (A–F).
- **Website Change Radar & Diff Viewer**: Compares successive extraction runs and highlights added, removed, and field-level modified records.
- **Scrape-to-RAG Pipeline**: Sliding-window text chunking with metadata preservation, source URLs, content hashes, and cosine similarity query retrieval.
- **Multi-Format Exporter**: One-click download in **CSV**, **JSON**, **Excel (.xlsx)**, or **JSONL**.
- **Live Monitoring & Streaming**: Server-Sent Events (SSE) stream progress percentages and live log output to the client.
- **Smart Retry Advisor**: Analyzes failures (HTTP 403, 429, timeouts, missing JS selectors) and provides actionable recommendations.

---

## 📁 Repository Structure

```
├── backend/
│   ├── nexus_app/
│   │   ├── api/v1/          # REST API endpoints (auth, projects, inspect, jobs, datasets, radar, rag)
│   │   ├── engine/          # Fetcher, Browser, Extractor, Cleaner, Quality, Diff, AI, RAG
│   │   ├── models/          # SQLAlchemy Database Models (User, Project, Job, Dataset, RAG)
│   │   ├── schemas/         # Pydantic v2 validation models
│   │   ├── security/        # SSRF defense, PBKDF2 hashing, JWT & API Key authentication
│   │   ├── tasks/           # Background job runner with SSE queues & scheduler daemon
│   │   ├── config.py        # Centralized Pydantic settings
│   │   ├── database.py      # SQLite / PostgreSQL engine & session maker
│   │   └── main.py          # FastAPI application entrypoint
│   ├── static/              # Embedded production SaaS dashboard (index.html)
│   └── tests/               # 24 automated unit and integration tests
├── frontend/                # Standalone Next.js 14 TypeScript app
├── Dockerfile.backend       # Backend container with Playwright & Chromium
├── Dockerfile.frontend      # Next.js container
├── docker-compose.yml       # Full stack deployment (Backend, Frontend, Postgres, Redis)
├── .env.example             # Configuration template
├── requirements.txt         # Pinned backend dependencies
└── README.md                # Documentation
```

---

## 🚀 Quickstart (Local Development)

### 1. Prerequisites
- Python 3.10+ (Python 3.11+ recommended)
- Node.js 18+ (optional, for standalone Next.js frontend)

### 2. Setup Backend & Start Application
```powershell
# Set up virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run backend (includes built-in production dashboard)
$env:PYTHONPATH="backend"
python -m uvicorn nexus_app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Open the Platform
- **SaaS Dashboard**: Open [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI / Swagger Docs**: Open [http://localhost:8000/docs](http://localhost:8000/docs)

*Note: Default demo credentials (`admin@nexusscrape.ai` / `NexusAdmin2026!`) are automatically configured on first launch.*

---

## 🧪 Running Automated Tests

Run the complete test suite covering SSRF defense, CSS/XPath extraction, cleaning, deduplication, quality scoring, diff radar, RAG chunking, and API integration:

```powershell
$env:PYTHONPATH="backend"
python -m unittest discover -s backend/tests -v
```

All 24 test cases pass cleanly without external network dependencies.

---

## 🐳 Docker Deployment

To run NEXUS SCRAPE AI in production with PostgreSQL, Redis, and Next.js:

```bash
# Copy environment variables
cp .env.example .env

# Build and start services
docker compose up -d --build
```

Services will be accessible at:
- **Frontend Next.js App**: `http://localhost:3000`
- **FastAPI API & Dashboard**: `http://localhost:8000`
- **API Documentation**: `http://localhost:8000/docs`
- **PostgreSQL**: `localhost:5432`
- **Redis**: `localhost:6379`

---

## 🔒 Security & SSRF Protection

NEXUS SCRAPE AI enforces strict security controls:
- **SSRF Defense**: Evaluates resolved IP addresses against IPv4/IPv6 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`), and cloud metadata (`169.254.169.254`, `metadata.google.internal`).
- **Redirect Revalidation**: Validates every redirect location against SSRF boundaries before making subsequent requests.
- **Browser Route Interception**: Playwright routes intercept sub-requests in JavaScript-rendered pages and aborts any internal requests.
- **Tenant Isolation**: Projects and datasets are strictly isolated by authenticated user ID.
- **API Keys**: API tokens are generated with high entropy (`nxs_...`) and stored hashed using SHA-256.

---

## 📄 API Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register new user account |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT Bearer token |
| `POST` | `/api/v1/auth/api-keys` | Generate scoped API Key |
| `POST` | `/api/v1/projects` | Create a tenant-isolated project workspace |
| `POST` | `/api/v1/inspect` | Validate URL against SSRF, inspect robots.txt & DOM |
| `POST` | `/api/v1/inspect/test-selectors` | Test CSS & XPath selectors against live HTML |
| `POST` | `/api/v1/ai/suggest-schema` | Propose schema & selectors using AI Autopilot |
| `POST` | `/api/v1/jobs` | Submit a crawl job to background worker queue |
| `GET` | `/api/v1/jobs/{id}/stream` | Server-Sent Events (SSE) live progress & log stream |
| `GET` | `/api/v1/jobs/{id}/retry-advisor` | Diagnose crawl failures & get smart retry advice |
| `GET` | `/api/v1/datasets/{id}/records` | Paginated, searchable record explorer |
| `GET` | `/api/v1/datasets/{id}/quality` | Auditable Data Quality Report (Completeness/Validity) |
| `GET` | `/api/v1/datasets/{id}/export` | Export to CSV, JSON, Excel (.xlsx), or JSONL |
| `POST` | `/api/v1/radar/diff` | Compare snapshots and view record & field diffs |
| `POST` | `/api/v1/rag/pipelines` | Build sliding-window RAG chunks from dataset |
| `POST` | `/api/v1/rag/pipelines/{id}/query` | Semantic similarity query retrieval with citations |
