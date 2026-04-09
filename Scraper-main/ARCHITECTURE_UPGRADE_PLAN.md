# Enterprise Upgrade Blueprint: Self-Learning Distributed Extraction Platform

## 1. New Architecture Diagram

System topology:

1. Control Plane
- API Gateway and FastAPI API service
- Auth and rate limiting middleware
- Job Orchestrator service
- Webhook Dispatcher service
- Tenant and Quota service

2. Data Plane
- Browser Worker pool
- API Extractor Worker pool
- DOM Parser Worker pool
- LLM Structurer Worker pool
- Export Worker pool

3. Knowledge Plane
- Site Profile Registry
- Layout Fingerprint Index
- Strategy Templates Store
- Failure Cluster Store

4. Platform Services
- Redis Streams for job and stage queues
- PostgreSQL for job state, profiles, metrics, contracts
- Elasticsearch for logs and search analytics
- Object storage for HTML snapshots, traces, exported files

5. Observability Plane
- Metrics collector and aggregator
- Domain success tracker
- Failure clustering service
- Dashboards and alerts

Request path:
- Client submits scrape request to API service.
- API writes job row and enqueues orchestrator message.
- Orchestrator creates stage tasks and enqueues worker-specific messages.
- Workers process stage tasks and write task_runs and stage outputs.
- Orchestrator performs multi-pass logic and re-queues field-recovery tasks when needed.
- Contract engine validates final records.
- Export worker writes output and updates artifact metadata.
- Webhook dispatcher notifies client when terminal state reached.

## 2. Updated Folder Structure

Proposed structure while preserving existing modules:

src/
  api/
    app.py
    routers/
      scrape.py
      jobs.py
      exports.py
      webhooks.py
    middleware/
      auth.py
      ratelimit.py
      request_id.py
  orchestrator/
    coordinator.py
    pass_controller.py
    retry_policy.py
    idempotency.py
  workers/
    browser_worker/
      runner.py
      behavior_simulator.py
      stealth_profile.py
    api_worker/
      runner.py
    dom_worker/
      runner.py
      parser_registry.py
    llm_worker/
      structurer.py
      prompt_library.py
      budget_controller.py
    export_worker/
      runner.py
  knowledge/
    site_profiles/
      registry.py
      versioning.py
      rollback.py
    fingerprint/
      dom_fingerprint.py
      cluster_index.py
    strategy_reuse/
      matcher.py
      bootstrap.py
  contracts/
    engine.py
    schemas/
      ecommerce.yaml
      article.yaml
      directory.yaml
      custom/
  queue/
    bus.py
    schemas.py
    producers.py
    consumers.py
  persistence/
    models.py
    repositories/
      jobs_repo.py
      tasks_repo.py
      profiles_repo.py
      metrics_repo.py
      deltas_repo.py
    migrations/
  anti_bot/
    session_store.py
    proxy_manager.py
    detector.py
  analytics/
    metrics_service.py
    failure_clustering.py
    domain_scorecard.py
  compatibility/
    legacy_api_adapter.py
    legacy_pipeline_bridge.py

Current code mapping for backward compatibility:
- Keep [agents/universal_agent.py](agents/universal_agent.py) as legacy orchestrator adapter.
- Keep [pipelines/data_stream.py](pipelines/data_stream.py) and [pipelines/quality_guard.py](pipelines/quality_guard.py) as compatibility execution path.
- Keep [api.py](api.py) operational with a feature flag to switch from in-memory jobs to PostgreSQL plus Redis queue.

## 3. Key Module Designs

### 3.1 Site Profile Registry

Purpose:
- Persist per-domain extraction memory and anti-bot behavior outcomes.

Stored profile fields:
- domain
- site_type
- platform_type
- selectors by field
- successful api endpoints and payload paths
- anti_bot_signatures and mitigation actions
- layout fingerprints
- pass success rates
- confidence statistics
- profile version and status

Rules:
- Auto-create profile when a job finishes with confidence above threshold.
- Create new profile version when selector set or API path changes.
- Rollback to previous stable version after N consecutive failures.

Integration points:
- Read profile before first pass in orchestrator.
- Update profile after each successful pass.
- Attach profile_id and profile_version to task_runs.

### 3.2 Multi-Pass Pipeline

Pass design:
- Pass 1 Broad extraction:
  - Use site profile selectors and known API paths.
  - Execute fast deterministic extractors.
- Pass 2 Missing-field recovery:
  - Detect field-level nulls required by contracts.
  - Trigger targeted retries for missing fields only.
- Pass 3 Targeted extraction:
  - Field-specific extraction jobs with high-cost paths allowed.
  - Apply LLM-assisted structuring only for ambiguous fields.

Field-level retry triggers:
- required field missing
- confidence below field threshold
- cross-field inconsistency

Retry limits:
- per field max 2 retries
- per pass hard timeout
- terminate with partial flag if contract allows soft-fail

### 3.3 LLM-Assisted Structuring

Design principles:
- LLM does not parse raw full HTML by default.
- LLM receives candidate field values, source traces, and normalization intent.
- LLM returns normalized fields plus rationale tags and confidence adjustments.

Prompt contract:
- Input: record candidate object, source traces, contract requirements, allowed enums.
- Output: strict JSON schema with no extra keys.

Batching and cost control:
- Group by domain and schema shape.
- Max token budget per tenant per hour.
- Skip LLM when deterministic confidence already above threshold.
- Cache normalized outputs by stable hash of candidate fields.

### 3.4 Platform Detection Layer

Detected platforms:
- Shopify
- WooCommerce
- Magento
- React
- Next.js

Heuristics:
- Shopify:
  - script or assets containing cdn.shopify.com
  - window.Shopify object
  - /products/*.js endpoints
- WooCommerce:
  - wp-content/plugins/woocommerce
  - wc-ajax endpoints
- Magento:
  - /static/version*/frontend/*
  - mage-cache-storage keys
- React:
  - data-reactroot or React hydration signatures
- Next.js:
  - __NEXT_DATA__ script
  - /_next/static paths

StrategyFactory integration:
- Add platform_type argument and platform strategy override table.
- If platform strategy exists, prioritize it before generic site-type strategy.

### 3.5 Layout Fingerprinting

Fingerprint algorithm:
- Build reduced DOM tree sketch from stable nodes:
  - tag sequence
  - class tokens normalized and sorted
  - depth histogram
  - repeated container signatures
- Create canonical string and hash with SHA256.
- Store vectorized feature embedding for nearest-neighbor lookup.

Clustering:
- Use MinHash or SimHash for quick candidate lookup.
- Use cosine similarity on feature vectors for final grouping.
- If similarity above threshold, bootstrap profile from nearest successful cluster.

### 3.6 Distributed Queue and Orchestration

Queue technology:
- Redis Streams consumer groups for stage-specific queues.

Stream names:
- scrape.jobs
- scrape.stage.browser
- scrape.stage.api
- scrape.stage.dom
- scrape.stage.llm
- scrape.stage.export
- scrape.dlq

Job lifecycle:
- queued -> scheduled -> running -> pass1_done -> pass2_done -> pass3_done -> validating -> exporting -> completed
- terminal failures: failed, cancelled, timed_out

Idempotency strategy:
- idempotency_key derived from tenant, url, normalized request, time bucket
- dedupe window in Redis and PostgreSQL unique constraint

Retry strategy:
- exponential backoff per stage
- max retries stage-specific
- poison messages move to DLQ with error snapshot

### 3.7 Worker Split and Communication

Worker types:
- Browser worker:
  - navigation, page interaction, API interception, snapshot capture
- API extractor worker:
  - payload extraction from captured endpoints
- DOM parser worker:
  - deterministic DOM selector and clustering extraction
- LLM processor worker:
  - record structuring and ambiguity resolution
- Exporter worker:
  - format conversion and artifact publication

Communication model:
- Orchestrator writes stage task messages to stream.
- Worker reads and acknowledges only after durable task_run write.
- Worker emits stage_result event to scrape.jobs stream.

Scaling policy:
- Scale browser workers by CPU and memory envelope.
- Scale API and DOM workers by queue lag.
- Scale LLM workers by token budget and provider latency.
- Scale exporter workers by artifact throughput.

### 3.8 Persistent Job Store

Core tables:
- jobs
- task_runs
- job_metrics
- site_profiles and profile_versions
- layout_fingerprints
- extraction_deltas

Details in section 5.

### 3.9 Anti-Bot Redesign

New capabilities:
- Stealth profile variants:
  - canvas noise
  - webgl vendor override
  - font fingerprint randomization
- Residential proxy support with per-domain pools.
- Session persistence by domain and tenant.
- Human behavior simulation:
  - scroll cadence
  - mouse trajectories
  - random reading pauses

Control loop:
- Detect bot challenge signatures.
- Increase mitigation level progressively.
- Persist successful mitigation pattern in site profile.

### 3.10 Contract Engine

Contract model:
- Site-type default contracts plus per-domain overrides.
- Required fields, type checks, regex rules, enum constraints, cross-field rules.

Validation outcomes:
- pass
- soft_fail with warnings
- hard_fail with retry triggers

Pipeline integration:
- Validate after each pass.
- Generate missing_field_set for pass 2 and pass 3.

### 3.11 Observability and Intelligence

Metrics dimensions:
- tenant
- domain
- platform
- site_type
- worker_type
- pass_number

Core metrics:
- extraction_success_rate
- contract_pass_rate
- field_level_fill_rate
- average confidence by field
- retries per stage
- bot challenge rate
- median cost per 1k records
- queue lag and stage latency

Failure clustering:
- Group by normalized exception signature plus domain/platform fingerprint.
- Link clusters to profile version and deployment version.

### 3.12 Incremental and Delta Scraping

Delta model:
- record_identity_hash
- first_seen_at
- last_seen_at
- changed_fields
- previous_value and new_value

Enhancement path:
- Promote change_log into extraction_deltas table.
- Compute diff against latest stable snapshot.
- Expose delta export endpoint.

## 4. Critical Pseudocode and Code Skeletons

### 4.1 Orchestrator with Multi-Pass and Field Recovery

Python pseudocode:

class PassController:
    def run_job(self, job):
        profile = profile_registry.resolve(job.domain)
        context = JobContext(job=job, profile=profile)

        pass1 = self.run_pass(context, pass_no=1, mode="broad")
        missing = contract_engine.missing_required(pass1.records, job.contract)

        if missing:
            pass2 = self.run_pass(context, pass_no=2, mode="recover", fields=missing)
            merged = merge_records(pass1.records, pass2.records)
        else:
            merged = pass1.records

        low_conf = contract_engine.low_confidence_fields(merged, job.contract)
        if low_conf:
            pass3 = self.run_pass(context, pass_no=3, mode="targeted", fields=low_conf)
            merged = merge_records(merged, pass3.records)

        structured = llm_structurer.normalize_if_needed(merged, job.contract)
        verdict = contract_engine.validate(structured, job.contract)

        if verdict.hard_fail and job.can_retry():
            return self.retry_job(job, verdict)

        artifact = exporter.export(structured, job.output_format)
        profile_registry.learn(job.domain, context, structured, verdict)
        return complete_job(job, artifact, verdict)

### 4.2 Site Profile Versioning and Rollback

Python pseudocode:

class SiteProfileRegistry:
    def learn(self, domain, context, records, verdict):
        current = repo.get_active_profile(domain)
        candidate = build_profile_candidate(current, context, records)

        if significant_change(current, candidate):
            new_ver = repo.create_profile_version(domain, candidate)
            repo.activate_version(domain, new_ver)

    def on_failure(self, domain, error_signature):
        profile = repo.get_active_profile(domain)
        repo.bump_failure_counter(profile.id)
        if profile.consecutive_failures >= 3:
            prev = repo.get_previous_stable_version(domain)
            if prev:
                repo.activate_version(domain, prev.version)

### 4.3 Platform Detection Integration

Python pseudocode:

def detect_platform(page_html, script_urls, api_urls):
    if "cdn.shopify.com" in any(script_urls) or "window.Shopify" in page_html:
        return "shopify"
    if "woocommerce" in any(script_urls) or "/wc-ajax/" in any(api_urls):
        return "woocommerce"
    if "/_next/static" in any(script_urls) or "__NEXT_DATA__" in page_html:
        return "nextjs"
    if "data-reactroot" in page_html or "react" in any(script_urls):
        return "react"
    if "mage-cache-storage" in page_html or "/frontend/" in any(script_urls):
        return "magento"
    return "unknown"

### 4.4 Redis Stream Message Schema

JSON message body:

{
  "event_type": "stage_task",
  "job_id": "uuid",
  "tenant_id": "uuid",
  "stage": "dom",
  "pass_no": 2,
  "attempt": 1,
  "idempotency_key": "sha256",
  "domain": "example.com",
  "platform_type": "shopify",
  "site_type": "ecommerce",
  "required_fields": ["price", "currency"],
  "profile_id": "uuid",
  "profile_version": 5,
  "payload_ref": "s3://.../job_context.json",
  "trace_id": "uuid",
  "created_at": "timestamp"
}

### 4.5 Contract Engine Interface

Python interface:

class ContractEngine:
    def validate(self, records, contract):
        # returns ValidationVerdict with hard_fail, soft_fail, missing_fields, low_confidence
        ...

    def missing_required(self, records, contract):
        ...

    def low_confidence_fields(self, records, contract):
        ...

## 5. Database Schemas

### 5.1 jobs

SQL:

CREATE TABLE jobs (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  source_url TEXT NOT NULL,
  domain TEXT NOT NULL,
  site_type TEXT,
  platform_type TEXT,
  status TEXT NOT NULL,
  priority INT NOT NULL DEFAULT 5,
  request_payload JSONB NOT NULL,
  output_format TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  contract_id TEXT,
  profile_id UUID,
  profile_version INT,
  retry_count INT NOT NULL DEFAULT 0,
  max_retries INT NOT NULL DEFAULT 3,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_code TEXT,
  error_message TEXT,
  artifact_uri TEXT,
  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_domain ON jobs(domain);
CREATE INDEX idx_jobs_tenant_status ON jobs(tenant_id, status);

### 5.2 task_runs

CREATE TABLE task_runs (
  id UUID PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  pass_no INT NOT NULL,
  attempt INT NOT NULL,
  worker_type TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  status TEXT NOT NULL,
  input_ref TEXT,
  output_ref TEXT,
  records_in INT DEFAULT 0,
  records_out INT DEFAULT 0,
  latency_ms INT,
  cost_usd NUMERIC(12,6) DEFAULT 0,
  tokens_in INT DEFAULT 0,
  tokens_out INT DEFAULT 0,
  profile_id UUID,
  profile_version INT,
  error_signature TEXT,
  error_detail TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX idx_task_runs_job_stage ON task_runs(job_id, stage, pass_no);
CREATE INDEX idx_task_runs_status ON task_runs(status);

### 5.3 job_metrics

CREATE TABLE job_metrics (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL,
  domain TEXT NOT NULL,
  platform_type TEXT,
  site_type TEXT,
  metric_name TEXT NOT NULL,
  metric_value DOUBLE PRECISION NOT NULL,
  metric_tags JSONB,
  measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_job_metrics_job ON job_metrics(job_id);
CREATE INDEX idx_job_metrics_domain_time ON job_metrics(domain, measured_at);

### 5.4 site_profiles and profile_versions

CREATE TABLE site_profiles (
  id UUID PRIMARY KEY,
  domain TEXT NOT NULL UNIQUE,
  tenant_scope TEXT NOT NULL DEFAULT 'global',
  active_version INT NOT NULL,
  stable_version INT,
  platform_type TEXT,
  site_type TEXT,
  consecutive_failures INT NOT NULL DEFAULT 0,
  last_success_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE site_profile_versions (
  id UUID PRIMARY KEY,
  profile_id UUID NOT NULL REFERENCES site_profiles(id) ON DELETE CASCADE,
  version INT NOT NULL,
  status TEXT NOT NULL,
  selector_map JSONB NOT NULL,
  api_patterns JSONB,
  anti_bot_signatures JSONB,
  layout_fingerprint TEXT,
  success_rate DOUBLE PRECISION,
  avg_confidence DOUBLE PRECISION,
  created_by TEXT NOT NULL DEFAULT 'system',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (profile_id, version)
);

### 5.5 layout_fingerprints

CREATE TABLE layout_fingerprints (
  id UUID PRIMARY KEY,
  domain TEXT NOT NULL,
  fingerprint_hash TEXT NOT NULL,
  feature_vector JSONB NOT NULL,
  cluster_id TEXT,
  profile_id UUID,
  profile_version INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_layout_fingerprint_hash ON layout_fingerprints(fingerprint_hash);
CREATE INDEX idx_layout_cluster ON layout_fingerprints(cluster_id);

### 5.6 extraction_deltas

CREATE TABLE extraction_deltas (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  domain TEXT NOT NULL,
  entity_key TEXT NOT NULL,
  change_type TEXT NOT NULL,
  changed_fields JSONB NOT NULL,
  before_state JSONB,
  after_state JSONB,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  job_id UUID REFERENCES jobs(id)
);

CREATE INDEX idx_extraction_deltas_domain_time ON extraction_deltas(domain, observed_at);
CREATE INDEX idx_extraction_deltas_entity ON extraction_deltas(entity_key);

## 6. End-to-End Data Flow

1. Submit job
- API authenticates tenant.
- API validates payload and computes idempotency key.
- API inserts jobs row with status queued.
- API pushes message to scrape.jobs stream.

2. Plan stages
- Orchestrator consumes queued event.
- Loads domain profile and platform detection hints.
- Enqueues pass 1 browser or API tasks.

3. Execute pass 1
- Browser and API workers emit candidate records.
- DOM worker parses and normalizes deterministic fields.
- Task outputs persisted and metrics emitted.

4. Contract check and pass 2
- Contract engine computes missing required fields.
- Orchestrator enqueues targeted recovery tasks for pass 2.

5. Pass 3 targeted extraction
- For unresolved low-confidence fields, enqueue targeted tasks.
- LLM structurer only normalizes ambiguity and entity forms.

6. Final validation
- Contract engine validates merged records.
- If hard fail and retries remain, orchestrator re-queues job with backoff.

7. Export and completion
- Export worker writes artifact and metadata.
- Job marked completed with artifact_uri.
- Webhook dispatcher sends callback if configured.

8. Learning update
- Profile registry records successful selectors and signatures.
- Fingerprint index updated and cluster association recalculated.
- Delta tracker records changes versus previous run.

## 7. Migration Plan from Current System

Phase 1: Persistence and queue foundation
- Add PostgreSQL schema and repositories.
- Add Redis Streams bus and producer consumer utilities.
- Keep [api.py](api.py) endpoints unchanged, but write jobs to DB in parallel with existing in-memory map.
- Introduce feature flag: USE_DISTRIBUTED_JOBS.

Phase 2: Orchestrator extraction split
- Wrap [agents/universal_agent.py](agents/universal_agent.py) as legacy execution adapter worker.
- Introduce orchestrator with stage events.
- Route a small percentage of traffic to distributed path.

Phase 3: Site profiles and fingerprinting
- Start profile write-only mode.
- Enable profile read mode for selected domains.
- Add rollback policy and version activation.

Phase 4: Multi-pass and contract enforcement
- Add contract engine in soft-fail mode first.
- Enable pass 2 and pass 3 on domains with stable baseline.
- Promote hard-fail contract rules per tenant policy.

Phase 5: LLM structuring and budget controls
- Replace raw-html fallback usage with record structuring flow.
- Add token budgets and cache.

Phase 6: Worker specialization and scaling
- Split workers by responsibility.
- Add autoscaling by queue lag and stage latency.

Phase 7: Full cutover and deprecation
- Default API path to distributed orchestrator.
- Retain legacy path behind LEGACY_EXECUTION_ENABLED for rollback window.
- Remove in-memory job map after proven stability period.

Backward compatibility commitments:
- Existing API endpoints and response shapes preserved.
- Existing export formats preserved.
- Existing dashboard remains functional; it reads persisted job status instead of RAM map.
- Existing modules remain callable through compatibility adapters.

## 8. Deployment and Container Fixes

Required deployment changes:
- Fix Docker CMD to run api app entrypoint.
- Separate API and worker containers with independent scale controls.
- Add orchestrator container.
- Add queue and DB readiness checks before startup.

Compose service split:
- api service
- orchestrator service
- browser-worker service
- api-worker service
- dom-worker service
- llm-worker service
- exporter-worker service
- webhook-dispatcher service

Operational flags:
- WORKER_TYPE
- QUEUE_STREAM
- TENANT_SHARD
- MAX_CONCURRENCY
- LLM_BUDGET_LIMIT

## 9. Concrete Integration with Current Files

Immediate refactor targets:
- [api.py](api.py): replace in-memory jobs map with repository plus queue producer.
- [agents/universal_agent.py](agents/universal_agent.py): expose stage-level methods for browser, api, dom, llm outputs.
- [pipelines/data_stream.py](pipelines/data_stream.py): add contract validation hooks and delta emitter.
- [pipelines/quality_guard.py](pipelines/quality_guard.py): move contract checks into separate contracts engine but keep current normalizers.
- [core/browser_manager.py](core/browser_manager.py): add stealth profile manager, proxy manager, session persistence service.
- [docker-compose.yml](docker-compose.yml): split worker roles and correct app command target.
- [Dockerfile](Dockerfile): set runtime command to api entrypoint and parameterize role.

## 10. High-Impact First Implementation Sprint

Sprint scope that yields production uplift quickly:
1. PostgreSQL persistent jobs and task_runs tables.
2. Redis Streams queue and orchestrator skeleton.
3. Profile registry write path and read fallback.
4. Platform detection and strategy override hooks.
5. Multi-pass pass controller with field-level retries.
6. Contract engine in soft-fail mode.
7. Docker compose role split and corrected API command.

Expected outcomes:
- Durable job tracking and resumability.
- Horizontal worker scaling.
- Better extraction accuracy via profile reuse and multi-pass recovery.
- Reduced repeated failures via rollback to stable profile versions.
- Lower LLM cost by limiting model use to structuring tasks.
