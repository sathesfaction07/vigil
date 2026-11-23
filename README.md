# Vigil

Scans product listings across marketplaces, flags policy-violating content using multilingual keyword matching, entity detection, and LLM-based reasoning (Bedrock Claude), and hands an explainable verdict to a human reviewer. Supports multimodal classification (product images alongside text), batch CSV workflows, and configurable enrichment backends. Advisory-only — never auto-enforces.

---

## The Problem

An e-commerce catalog with millions of listings across 10+ countries. Some violate content policies — restricted language, wrong age targeting, deceptive descriptions in various languages, unicode tricks to evade keyword filters. Manually reviewing each takes ~7 minutes. At scale, that's thousands of reviewer-hours per week. Worse: keyword lists are finite. A new violation pattern in Thai or a Cyrillic brand-fuzzing attempt bypasses lists that were built for English.

Vigil combines three detection layers — keyword matching, entity detection, and LLM reasoning — so violations get caught regardless of whether someone anticipated the specific pattern.

---

## How It Works

```
Client → Flask API → Redis Queue → Worker(s) → Result
                  ↑                           ↓
                  └───── SSE stream ──────────┘
```

**Inside each worker:**

1. **Catalog fetch** — pull product data (title, description, bullets, attributes, image URLs) across marketplaces
2. **Keyword detection** — 8-language NFKC-normalized scan (catches unicode evasion)
3. **Entity enrichment** (optional) — Amazon Comprehend or local regex detects ages, PII, product types that keywords don't cover
4. **Language detection** — auto-identifies content language (no need to specify which languages to scan)
5. **LLM classification** — sends product data + keyword matches + entities + images (if multimodal) to Claude. Returns: classification, confidence, reasoning, evidence.
6. **Result storage** — cached in Redis, streamed to client via SSE

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│ Flask API                                                      │
│  POST /api/analyze       (single product)                      │
│  POST /api/batch         (JSON list, up to 100)                │
│  POST /api/batch/csv     (upload CSV file)                     │
│  GET  /api/results/csv   (export completed results as CSV)     │
│  GET  /api/stream/<id>   (SSE progress)                        │
│  GET  /api/result/<id>   (poll result)                         │
│  GET  /health            (service health + metrics)             │
└──────────────────────────────┬────────────────────────────────┘
                               │ Redis
                               ▼
┌───────────────────────────────────────────────────────────────┐
│ Worker (N instances)                                           │
│                                                               │
│  ┌──────────┐  ┌───────────────┐  ┌───────────────────────┐  │
│  │ Keywords │  │ Entity Enrich │  │ Classifier (Claude)   │  │
│  │ (NFKC,   │  │ (Comprehend   │  │ - Text attributes     │  │
│  │  8 langs) │  │  or local)    │  │ - Keyword signals     │  │
│  └──────────┘  └───────────────┘  │ - Entities            │  │
│                                    │ - Images (multimodal) │  │
│                                    └───────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
vigil/
├── src/content_guard/
│   ├── api/app.py              Endpoints (analyze, batch, CSV, stream, health)
│   ├── config.py               Settings (enricher, multimodal, Redis, Bedrock)
│   ├── observability.py        Structured logging, metrics, @timed decorator
│   ├── core/
│   │   ├── keywords.py         8-language NFKC keyword detection
│   │   ├── classifier.py       Bedrock invocation (text + multimodal), parse, confidence
│   │   └── prompts.py          15-rule security-hardened system prompt
│   ├── enrichment/
│   │   ├── base.py             EntityEnricher interface
│   │   ├── comprehend.py       AWS Comprehend (entities + language detection)
│   │   └── local.py            Regex-based (age patterns, PII, zero deps)
│   ├── queue/
│   │   ├── jobs.py             Redis queue (enqueue, dequeue, pubsub, TTL)
│   │   └── worker.py           Background processor (keywords → entities → classify)
│   └── services/catalog.py     Product data fetcher (httpx)
├── frontend/
│   ├── index.html              Entry point (React 18 + Tailwind)
│   └── src/App.jsx             Single/batch mode, SSE progress, result viewer
├── tests/                      45 tests (unit + integration + e2e)
├── data/keywords.json          8 languages × red/green categories
├── data/sample_products.json
├── Dockerfile
├── docker-compose.yml          API + Worker + Redis
└── pyproject.toml
```

---

## Running

**With Docker (backend + worker + Redis):**
```bash
docker compose up
```

**Manually:**
```bash
pip install -e ".[dev]"
redis-server &
python -m content_guard.queue.worker &
python -m content_guard.api.app
```

**Web UI (open in browser):**
```bash
python -m http.server 3000 --directory frontend
# Open http://localhost:3000
```

The frontend connects to the API at `localhost:5050`. Submit a product ID, watch progress stream in real-time, see the classification result with confidence badge, reasoning, evidence citations, keyword matches, and entity detections — all rendered live.

With entity enrichment:
```bash
CG_ENRICHER=comprehend docker compose up      # AWS Comprehend
CG_ENRICHER=local docker compose up           # Regex-based (free, offline)
```

With multimodal (send product images to Claude):
```bash
CG_MULTIMODAL=true docker compose up
```

---

## Usage

```bash
# Single product
curl -X POST localhost:5050/api/analyze \
  -d '{"product_id": "SKU-001", "marketplaces": ["US", "DE"]}'

# Batch (JSON)
curl -X POST localhost:5050/api/batch \
  -d '{"product_ids": ["SKU-001", "SKU-002", "SKU-003"]}'

# Batch (CSV upload)
curl -X POST localhost:5050/api/batch/csv -F "file=@products.csv"

# Export results as CSV
curl "localhost:5050/api/results/csv?job_ids=abc,def,ghi" > results.csv

# Stream progress
curl localhost:5050/api/stream/<job_id>

# Health
curl localhost:5050/health
```

---

## Testing

```bash
pytest tests/ -v              # 45 tests
pytest tests/ --cov=src       # coverage
```

---

## Configuration

| Variable | Default | What it controls |
|:--|:--|:--|
| `CG_REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `CG_BEDROCK_MODEL` | `claude-haiku-4-5` | Classification model |
| `CG_BEDROCK_REGION` | `us-east-1` | AWS region |
| `CG_ENRICHER` | `none` | Entity detection: `none`, `local`, `comprehend` |
| `CG_MULTIMODAL` | `false` | Send product images to Claude alongside text |
| `CG_MAX_MARKETPLACES` | `10` | Marketplaces to scan per product |
| `CG_WORKER_CONCURRENCY` | `5` | Concurrent jobs per worker |
| `CG_RESULT_TTL_SECONDS` | `3600` | Result cache lifetime |

---

## Tradeoffs and Decisions I Made Along the Way

**Three detection layers instead of just LLM**

I could send everything to Claude and skip keywords/entities entirely. But: (1) keywords are instant and free — they catch 80% of violations before the API call, (2) entity detection catches patterns I haven't explicitly listed as keywords (age ranges, PII leaking into descriptions), (3) the LLM gets better input — it sees "keyword engine found 3 RED signals + Comprehend detected AGE entity 'ages 3-8'" which gives it stronger evidence to base its classification on. Each layer catches things the others miss.

**Entity enrichment as optional, not mandatory**

Comprehend costs money per API call. The local regex enricher is free but only catches simple patterns (age numbers, email addresses). Making it configurable means: development runs fast with `none`, testing uses `local`, production uses `comprehend`. The worker code doesn't change — it just checks `if self.enricher: ...`.

**Multimodal behind a flag**

Sending images to Claude increases token cost 5-10x per request (images are expensive in tokens). Most violations are detectable from text alone. Multimodal is valuable for the subset of products where text is ambiguous but images clarify intent (e.g., "action figure" that shows a child playing with it). Keeping it behind a flag means you opt in when the use case warrants the cost.

**CSV batch upload for operations teams**

The JSON batch endpoint works for programmatic integrations. But operations teams live in spreadsheets. The CSV upload accepts a file with `product_id` (or `id` or `sku`) and optional `marketplaces` columns, enqueues everything, and returns job IDs. The CSV export endpoint lets them download results back into a spreadsheet format. No custom tooling needed on their side.

**SSE break on both "complete" and "failed"**

The original version only broke SSE on "complete" — a failed job would leave the client hanging. Now the stream breaks on both event types, and `mark_failed` publishes a "failed" event. The client always gets a terminal signal.

**Language auto-detection instead of per-keyword-language scanning**

The keyword engine scans all 8 languages on every product regardless. That's fine at 64 keywords. But Comprehend's `detect_dominant_language` tells us what language the listing is in, which gets passed to the classifier as context ("this listing is in German, so German keywords are expected — but the English keyword 'adult' appearing in a German listing is suspicious"). The language signal adds classification intelligence beyond what keyword matches alone provide.

---

## Stack

Flask, Redis (queue + PubSub), boto3/Bedrock (Claude Haiku), boto3/Comprehend (optional), httpx, Pydantic Settings, pytest, Docker Compose.
