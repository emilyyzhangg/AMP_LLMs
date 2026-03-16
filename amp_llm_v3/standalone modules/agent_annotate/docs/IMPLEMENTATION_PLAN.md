# Agent Annotate — Implementation Plan

## Context

AMP LLM currently annotates clinical trials using a single monolithic LLM call that handles all 5 annotation fields simultaneously. This produces results that are not rigorous enough for scientific publication — there's no independent verification, no evidence thresholds, and no source citations.

Agent Annotate replaces this with a network of specialized AI agents: 4 research agents gather data in parallel, 5 annotation agents each handle one field with mandatory evidence thresholds, and a multi-model blind verification pipeline ensures publication-grade accuracy. Every claim is traceable to specific sources with identifiers.

**Service:** Standalone FastAPI + React/TypeScript on port 9005 (dev) / 8005 (prod)
**Location:** `dev-llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/`
**Branch:** `dev` only — merges to `main` trigger auto-deploy to prod

---

## Phase 0: Project Scaffolding (Foundation)

**Goal:** FastAPI shell + React scaffold, builds and runs on port 9005, all endpoints return stubs.

### 0.1 Directory Structure

```
agent_annotate/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app, SPA catch-all, lifespan
│   ├── config.py                        # Settings (reads .env, loads YAML)
│   ├── auth_client.py                   # Cookie auth via auth.amphoraxe.ca
│   ├── models/
│   │   ├── __init__.py
│   │   ├── job.py                       # AnnotationJob, JobStatus, JobProgress
│   │   ├── research.py                  # ResearchResult, SourceCitation
│   │   ├── annotation.py               # FieldAnnotation, AnnotationResult
│   │   ├── verification.py             # ModelOpinion, ConsensusResult
│   │   ├── config_models.py            # Pydantic mirror of YAML config
│   │   └── output.py                   # CSVRow, JSONOutput, AuditTrail
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── jobs.py                      # POST /jobs, GET /jobs, GET /jobs/{id}
│   │   ├── status.py                    # GET /jobs/{id}/status (polling)
│   │   ├── results.py                   # GET /results, CSV/JSON download
│   │   ├── review.py                    # GET /review/queue, POST /review/{id}/decide
│   │   ├── settings.py                  # GET/PUT /settings, GET /settings/models
│   │   └── health.py                    # GET /health
│   ├── services/
│   │   ├── __init__.py
│   │   ├── orchestrator.py              # Main pipeline coordinator (stub)
│   │   ├── ollama_client.py             # Ollama HTTP client (stub)
│   │   ├── config_service.py            # Load/save/validate YAML config
│   │   ├── version_service.py           # Git hash, semantic version, config snapshot
│   │   ├── output_service.py            # JSON + CSV generation (stub)
│   │   └── review_service.py            # Manual review queue (stub)
│   └── static/
│       └── spa/                         # Vite build output
├── agents/                              # Already exists
│   ├── __init__.py
│   ├── base.py                          # BaseResearchAgent, BaseAnnotationAgent ABCs
│   ├── research/
│   │   ├── __init__.py
│   │   ├── clinical_protocol.py
│   │   ├── literature.py
│   │   ├── peptide_identity.py
│   │   └── web_context.py
│   ├── annotation/
│   │   ├── __init__.py
│   │   ├── classification.py
│   │   ├── delivery_mode.py
│   │   ├── outcome.py
│   │   ├── failure_reason.py
│   │   └── peptide.py
│   └── verification/
│       ├── __init__.py
│       ├── verifier.py
│       ├── reconciler.py
│       └── consensus.py
├── config/
│   └── default_config.yaml              # Already exists
├── docs/
│   └── USER_GUIDE.md                    # Already exists
├── frontend/
│   ├── index.html
│   ├── package.json                     # React 19, Vite, TypeScript
│   ├── tsconfig.json
│   ├── vite.config.ts                   # Builds to ../app/static/spa/
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   └── client.ts               # Centralized fetch client
│       ├── types/
│       │   └── index.ts                # TypeScript interfaces
│       ├── context/
│       │   ├── JobContext.tsx
│       │   └── SettingsContext.tsx
│       ├── components/
│       │   ├── AuthGate.tsx
│       │   ├── Header.tsx
│       │   ├── SubmitPage.tsx
│       │   ├── PipelinePage.tsx
│       │   ├── ReviewPage.tsx
│       │   ├── ResultsPage.tsx
│       │   ├── SettingsPage.tsx
│       │   └── HistoryPage.tsx
│       ├── hooks/
│       │   ├── useToast.ts
│       │   └── useSSE.ts
│       └── styles/
│           └── index.css
├── logs/                                # Already exists
├── results/                             # Already exists
│   ├── json/
│   └── csv/
└── requirements.txt
```

### 0.2 Configuration System

**`app/config.py`** — Load `.env` from parent `webapp/.env` (same search pattern as nct_config.py):
- `AGENT_ANNOTATE_PORT=9005`
- `OLLAMA_HOST`, `OLLAMA_PORT`
- `NCT_SERVICE_PORT` (to call existing NCT Lookup clients)
- API keys: `SERPAPI_KEY`, `NCBI_API_KEY`, etc.
- Paths: `RESULTS_DIR`, `LOGS_DIR`

**`app/models/config_models.py`** — Pydantic models mirroring `default_config.yaml`:
- `VerificationConfig` (num_verifiers, consensus_threshold, models list)
- `EvidenceThresholds` (per-field min_sources + min_quality_score)
- `ResearchAgentConfig`, `AnnotationAgentDef`, `OrchestratorConfig`, `OllamaConfig`
- Top-level `AnnotationConfig` composing all of the above

### 0.3 Pydantic Models

**`models/job.py`** — `AnnotationJob` with:
- `job_id` (UUID), `nct_ids`, `status` (queued/researching/annotating/verifying/reviewing/completed/failed)
- `config_snapshot` (frozen copy of AnnotationConfig at job creation)
- `git_commit`, `version`, `created_at`
- `JobProgress` (total_trials, completed_trials, current_phase, agents_status dict)

**`models/research.py`** — `SourceCitation` with:
- `database`, `identifier`, `field_path`, `excerpt`, `fetch_timestamp`
- `ResearchResult` (agent_name, sources_queried, findings list, raw_data, duration)

**`models/annotation.py`** — `FieldAnnotation` with:
- `field`, `value`, `evidence` (list of SourceCitation), `quality_score`
- `meets_threshold`, `requires_manual_review`, `review_reason`

**`models/verification.py`** — `ModelOpinion` with:
- `model_name`, `ollama_model`, `value`, `evidence_used`, `raw_response`
- `ConsensusResult` (consensus_reached, final_value, all opinions, status)

### 0.4 FastAPI Application Shell

**`app/main.py`** — Tasker pattern:
- Mount all routers at `/api/v1` prefix
- Root `/api/health` endpoint
- SPA catch-all: mount `/assets`, then `/{path:path}` serves `index.html`
- Lifespan: initialize config, Ollama client, aiohttp session

### 0.5 Stub Routers

All endpoints defined with full Pydantic types, returning mock data. Validates API contract.

### 0.6 Frontend Scaffold

Replicate Tasker pattern: Vite builds to `../app/static/spa/`, proxy `/api` to `localhost:9005`, React Router, AuthGate, minimal shell.

### 0.7 LaunchDaemon Plist

`services/com.amplm.annotate.dev.plist` — port 9005, KeepAlive, logs to `amp_llm_v3/logs/`

### Phase 0 Verification
- `uvicorn app.main:app --port 9005` starts
- `curl localhost:9005/api/health` returns OK
- All stub endpoints return 200
- `cd frontend && npm install && npm run build` produces SPA
- `curl localhost:9005/` returns React HTML

---

## Phase 1: Research Agents (Data Acquisition)

**Goal:** 4 research agents gather data from external sources in parallel.
**Depends on:** Phase 0

### 1.1 Base Agent Abstract Classes

**`agents/base.py`**:
```python
class BaseResearchAgent(ABC):
    agent_name: str              # "clinical_protocol", "literature", etc.
    source_ids: list[str]        # Which data sources this agent queries

    async def research(self, nct_id: str, trial_data: dict) -> ResearchResult
    def _create_citation(self, database, identifier, field_path, excerpt) -> SourceCitation
```

Research agents make **direct HTTP calls** to external APIs via `httpx`. Agent Annotate is fully independent — zero dependency on other AMP LLM microservices (NCT Lookup, Runner, etc.).

### 1.2 Clinical Protocol Agent

**`agents/research/clinical_protocol.py`**
- Sources: ClinicalTrials.gov API v2 (direct) + OpenFDA
- Fetches trial protocol data + drug safety signals
- Extracts: briefTitle, briefSummary, conditions, interventions, overallStatus, whyStopped, phases, arms, eligibility
- Returns citations pointing to specific JSON paths

### 1.3 Literature Agent

**`agents/research/literature.py`**
- Sources: PubMedClient + PMCClient + PMCBioClient
- Searches by: references from protocolSection, PMID, NCT ID, title+authors
- Returns citations with PMIDs/PMCIDs and relevant excerpts

### 1.4 Peptide Identity Agent

**`agents/research/peptide_identity.py`**
- Sources: UniProtClient + DBAASPClient
- Searches by drug/intervention names
- Returns protein/peptide entries with accession numbers, family, keywords, sequences

### 1.5 Web Context Agent

**`agents/research/web_context.py`**
- Sources: DuckDuckGoClient + SerpAPIClient + GoogleScholarClient
- Constructs queries from title + intervention + condition
- Returns web results with URLs and excerpts
- Marks reliability as supplementary

### Phase 1 Verification
- Each agent tested with known NCT ID (e.g., NCT04043065)
- Returns valid ResearchResult with populated SourceCitations
- Edge case: trial with no publications, no UniProt matches
- Rate limiting works under concurrent execution
- Graceful handling when external API is unreachable

---

## Phase 2: Orchestrator + Annotation Agents (Intelligence)

**Goal:** Orchestrator dispatches research, feeds annotation agents, handles retry logic.
**Depends on:** Phase 1

### 2.1 Orchestrator Core

**`app/services/orchestrator.py`** — The hub of the system:

```python
class PipelineOrchestrator:
    async def run_pipeline(self, job_id: str, nct_ids: list[str]) -> None:
        for nct_id in nct_ids:
            research_data = await self._run_research(nct_id)      # Phase 1 agents, parallel
            annotations = await self._run_annotation(nct_id, research_data)  # Phase 2 agents
            verified = await self._run_verification(nct_id, annotations)     # Phase 3
            self._save_result(nct_id, verified)
```

**Research dispatch:** `asyncio.gather()` runs all 4 research agents concurrently.

**Annotation retry loop:** For each annotation agent:
1. Provide primary research data
2. Agent annotates → checks evidence threshold
3. If threshold not met → orchestrator provides secondary research data
4. Agent re-annotates with enriched data
5. If still insufficient → flag "Requires Manual Review"
6. No arbitrary retry cap — continues until all sources exhausted

**Status tracking:** In-memory `self.jobs` dict (same pattern as NCT lookup's `search_status_db`). Polled by `/api/v1/jobs/{id}/status`.

### 2.2 Base Annotation Agent

**`agents/base.py`** (extend):
```python
class BaseAnnotationAgent(ABC):
    field_name: str
    valid_values: list[str]

    async def annotate(self, nct_id, research_data, config) -> FieldAnnotation
    def _check_threshold(self, evidence, threshold) -> bool
    def _calculate_quality_score(self, evidence, field) -> float
```

Quality score: two-layer weighted system (source availability weight * field relevance weight). Uses weights from QUALITY_SCORES.md.

### 2.3–2.7 Five Annotation Agents

Each in `agents/annotation/`. Values match the human annotation Excel data validation.

| Agent | File | Valid Values | Strategy |
|-------|------|-------------|----------|
| Classification | `classification.py` | AMP(infection), AMP(other), Other | Single-pass, two-step prompt (Is it AMP? If so, infection or other?) |
| Delivery Mode | `delivery_mode.py` | 18 specific values (IV, IM, SC, Oral subtypes, Topical subtypes, etc.) | Single-pass with extensive fuzzy matching |
| Outcome | `outcome.py` | Positive, Withdrawn, Terminated, Failed - completed trial, Recruiting, Unknown, Active not recruiting | **Two-pass investigative** (see below) |
| Failure Reason | `failure_reason.py` | Business Reason, Ineffective for purpose, Toxic/Unsafe, Due to covid, Recruitment issues, or empty | **Two-pass investigative** (see below) |
| Peptide | `peptide.py` | True, False | Single-pass |

**Single-pass agents** (Classification, Delivery Mode, Peptide):
1. Receive relevant research data
2. Call Ollama with a task-specific prompt
3. Parse response, validate against valid_values
4. Check evidence threshold
5. Return FieldAnnotation with full citation chain

**Two-pass investigative agents** (Outcome, Failure Reason):

Designed from analysis of 617 human annotations that revealed ClinicalTrials.gov status is often stale/incomplete. 15 UNKNOWN-status trials had positive results in literature; 49/99 failure reasons came from COMPLETED trials where whyStopped was blank.

Pass 1 — **Fact extraction**: Extract registry status, search ALL evidence for published results/adverse events/failure signals. Asks structured questions.
Pass 2 — **Determination**: Given all extracted facts, make the decision. Published literature explicitly overrides registry status. "Unknown" and empty are last resorts, not defaults.

Failure Reason agent has a **smart short-circuit**: if Pass 1 determines the trial did not fail, skips Pass 2 entirely (saves an Ollama call for ~80% of trials).

### 2.8 Ollama Client

**`app/services/ollama_client.py`**:
- `generate(model, prompt) -> str` — non-streaming via POST /api/chat
- `list_models() -> list[dict]` — query /api/tags
- `health_check() -> bool`
- **`asyncio.Lock()`** — global lock ensures one model loaded at a time (16GB constraint)

### Phase 2 Verification
- Each annotation agent tested with mock research data
- Quality score calculation verified with known source combinations
- Threshold pass/fail at boundary values
- Retry flow: agent requests more data → orchestrator provides secondary research
- Full Research → Annotation pipeline for single NCT ID
- Ollama lock: no concurrent model calls

---

## Phase 3: Verification Pipeline (Quality Assurance)

**Goal:** Multi-model blind verification with consensus and reconciliation.
**Depends on:** Phase 2

### 3.1 Blind Verifier

**`agents/verification/verifier.py`**:
- Receives ONLY raw trial data — **never** the primary annotator's answer
- Generates its own prompt, annotates the field independently
- Returns `ModelOpinion` with value, evidence citations, raw response

### 3.2 Consensus Checker

**`agents/verification/consensus.py`**:
- Compares primary + all verifier opinions
- Case-insensitive value matching
- `agreement_ratio >= consensus_threshold` → consensus reached
- Else → needs reconciliation

### 3.3 Reconciliation Agent

**`agents/verification/reconciler.py`**:
- Receives ALL opinions + their evidence + raw data
- Uses larger model (qwen2.5:14b) for superior reasoning
- Makes final judgment OR flags as unresolvable → manual review

### 3.4 Verification Integration in Orchestrator

```python
async def _run_verification(self, nct_id, annotations, research_data):
    for field, annotation in annotations.items():
        if annotation.requires_manual_review:
            continue  # Already flagged

        # Verifiers run SEQUENTIALLY (one Ollama model at a time)
        verifier_opinions = []
        for verifier_config in self.config.verification.models:
            if verifier_config.role == "verifier":
                opinion = await verifier.verify(
                    nct_id, field, research_data, verifier_config
                )
                verifier_opinions.append(opinion)

        consensus = consensus_checker.check(primary, verifier_opinions, threshold)

        if not consensus.consensus_reached:
            reconciler_opinion = await reconciler.reconcile(...)
            if still_disagree:
                flag_manual_review("Model Disagreement")
```

**Default pipeline (5 sequential Ollama calls per field, 25 total per trial):**
1. Primary (llama3.1:8b) annotates
2. Verifier 1 (gemma2:9b) blind-verifies
3. Verifier 2 (qwen2:latest) blind-verifies
4. Verifier 3 (mistral:latest) blind-verifies
5. Reconciler (qwen2.5:14b) only if disagreement

### Phase 3 Verification
- Verifier prompt contains NO primary answer (inspect prompt content)
- Consensus: all agree, majority agree, all disagree scenarios
- Reconciliation: resolved vs. unresolved
- No concurrent Ollama calls (lock enforced)
- End-to-end: single NCT through full pipeline
- Audit trail captures every model's opinion and evidence

---

## Phase 4: Output + Manual Review (Data Export)

**Goal:** JSON/CSV output with audit trails, manual review queue.
**Depends on:** Phase 3

### 4.1 JSON Output

**`app/services/output_service.py`**:
- Saved to `results/json/{job_id}.json`
- Contains: version, git_commit, config_snapshot, generated_at
- Per trial: nct_id, metadata, per-field annotations with evidence chains, verification details, manual review data

### 4.2 Standard CSV (24 columns)

Matches existing annotation format exactly:
NCT ID, Study Title, Study Status, Brief Summary, Conditions, Drug, Phase, Enrollment, Start Date, Completion Date, Classification, Classification Evidence, Delivery Mode, Delivery Mode Evidence, Outcome, Outcome Evidence, Reason for Failure, Reason for Failure Evidence, Peptide, Peptide Evidence, Sequence, Sequence Evidence, Study ID, Comments

### 4.3 Full CSV

Standard 24 columns PLUS per field:
- `{field}_evidence_chain` — full citation chain
- `{field}_verification_status` — Verified / Manual Review / Error
- `{field}_confidence` — High / Medium / Low
- `{field}_quality_score` — 0.00–1.00
- `{field}_verifier_details` — which models verified, their conclusions
- `{field}_manual_review_flag` — yes/no + decision notes
- `{field}_retry_rounds` — how many research retries occurred

### 4.4 Version Service

**`app/services/version_service.py`**:
- `SEMANTIC_VERSION = "1.0.0"`
- `get_git_commit_id()` via subprocess (existing pattern from llm_assistant.py)
- `snapshot_config()` — immutable copy of AnnotationConfig for reproducibility
- Config hash for quick comparison

### 4.5 Manual Review Queue

**`app/services/review_service.py`**:
- In-memory queue of items flagged for review
- `GET /review/queue` — all pending items with full evidence from all models
- `POST /review/{id}/decide` — body: `{action: "decide"|"retry", value: str, notes: str}`
  - "decide": records manual answer with timestamp, notes, user
  - "retry": sends back to orchestrator for deeper search with specific instructions
- All decisions recorded in audit trail

### Phase 4 Verification
- JSON output structure validated
- Standard CSV has exactly 24 columns matching existing format
- Full CSV has all additional evidence columns
- Version stamp present in all outputs
- Manual review flow: flag → queue → decide → recorded
- CSV download: correct Content-Type and Content-Disposition

---

## Phase 5: React Frontend (User Interface)

**Goal:** Full React/TypeScript SPA with all settings configurable via UI.
**Depends on:** Phase 0 (API contract), Phase 4 (all APIs functional)
**Can be developed in parallel with Phases 1–4 using stub endpoints**

### 5.1 App Shell

- AuthGate (cookie auth via auth.amphoraxe.ca)
- Header: Submit | Pipeline | Review | Results | Settings | History
- React Router routes
- Toast notifications
- Secret agent themed design (spy/agent visual motif)

### 5.2 Submit Page

- Text input for NCT IDs (comma/newline separated, regex validation)
- CSV file upload with drag-and-drop
- "Start Annotation" button → POST /api/v1/jobs
- Job confirmation with job_id

### 5.3 Pipeline Visualization Page

- Real-time 3-phase pipeline view: Research → Annotation → Verification
- Per-agent status indicators (running/completed/failed)
- Per-trial progress in batch
- Poll GET /api/v1/jobs/{id}/status every 2 seconds

### 5.4 Manual Review Page

- List of items needing review
- Side-by-side model opinion comparison
- Per model: conclusion, evidence citations, raw reasoning
- Actions: pick answer (radio buttons) OR send back for deeper search
- Notes field for reviewer comments

### 5.5 Results Page

- List of completed jobs
- Click into job → full result view
- JSON viewer (collapsible tree)
- CSV export: "Download Standard CSV" / "Download Full CSV"
- Preview toggle between standard and full

### 5.6 Settings Page

- **Model Configuration**: dropdowns populated from `GET /settings/models` (live Ollama query)
  - Primary annotator model
  - Verifier models (add/remove dynamically)
  - Reconciler model
- **Evidence Thresholds**: number inputs per field (min_sources, min_quality_score)
- **Consensus**: threshold slider, require_consensus toggle
- **Research Agents**: enable/disable toggles per agent
- **Orchestrator**: parallel toggles, max retry rounds
- **Ollama**: host, port, timeout, temperature
- Save / Reset to Defaults buttons

### 5.7 History Page

- Chronological list of all annotation jobs
- Version, git commit, config used, NCT count
- Click to view results
- Filter/search

### Phase 5 Verification
- Build succeeds without TypeScript errors
- All pages render without console errors
- Auth flow works (redirect when unauthenticated)
- All CRUD operations work through UI
- Settings changes persist via API

---

## Phase 6: Infrastructure + Integration (Deployment)

**Goal:** Production-ready deployment.
**Depends on:** Phase 5

### 6.1 LaunchDaemon Plists

- Dev: `services/com.amplm.annotate.dev.plist` (port 9005)
- Prod: `services/com.amplm.annotate.plist` (port 8005)
- Pattern matches existing `com.amplm.assistant.dev.plist`

### 6.2 Auto-Update

No changes needed — existing `amp_autoupdate_dev.sh`:
- `for req_file in "$REPO_DIR/amp_llm_v3/standalone modules"/**/requirements.txt` picks up our requirements
- `for plist_file in "$PLIST_DIR"/com.amplm.*.dev.plist` picks up our plist
- Must add React build step for agent_annotate frontend (check if `frontend/package.json` exists, run `npm ci && npm run build`)

### 6.3 Main Menu Tile

Add to `webapp/templates/index.html` in the `.menu-grid`:
```html
<div class="menu-item" onclick="window.location.href='https://dev-llm.amphoraxe.ca/agent-annotate/'">
    <div class="menu-item-icon">🕵️</div>
    <div class="menu-item-title">Agent Annotate</div>
    <div class="menu-item-desc">Publication-grade annotation with AI agents</div>
</div>
```

### 6.4 Cloudflare Tunnel

Add ingress rule for path-based routing:
```yaml
- hostname: dev-llm.amphoraxe.ca
  path: /agent-annotate/*
  service: http://localhost:9005
```

### 6.5 Active Jobs Check

Expose `GET /api/jobs/active` for the auto-update script's graceful restart:
```python
@app.get("/api/jobs/active")
def active_jobs():
    return {"active": count_of_running_jobs}
```

### 6.6 Update Infrastructure Docs

- AMPHORAXE_INFRASTRUCTURE.md — add Agent Annotate as Service 6 under AMP LLM
- master_docs/API_MAP.md — add agent-annotate inter-service calls
- master_docs/CROSS_SERVICE_PATTERNS.md — note React build in auto-update
- master_docs/DEPLOYMENT_CHECKLIST.md — update port map
- master_docs/ENV_AND_SECRETS.md — add AGENT_ANNOTATE_PORT

### Phase 6 Verification
- LaunchDaemon starts on boot
- Auto-update detects code changes and restarts
- Main menu tile visible and links correctly
- Cloudflare tunnel routes properly
- Health check accessible from webapp proxy

---

## Phase 7: Hardening (Error Handling + Edge Cases)

**Goal:** Handle all failure modes gracefully.
**Depends on:** All phases

### Error Handling Matrix

| Scenario | Handling |
|----------|----------|
| Ollama unreachable | 503 on job submit; retry with backoff during pipeline |
| External API down | Mark that research agent as failed, continue with others |
| Invalid NCT ID | Return 400 immediately |
| NCT not found | Pipeline completes with empty CT data, all fields → manual review |
| Ollama model not found | Try `ollama pull`, if fails → skip that verifier, log warning |
| All verifiers fail | Use primary annotation only, flag "verification unavailable" |
| Timeout on Ollama | Retry once, then mark field as failed |
| Disk full | Return 500 with clear message |
| Concurrent jobs | Queue: max 1 active job, others queued (hardware constraint) |

### Memory Management (16GB M4)

- `asyncio.Lock()` ensures one Ollama model loaded at a time
- Process one trial at a time in batch; write results to disk incrementally
- Max batch size: 500 trials per job
- Research data per trial: ~1–5MB, discarded after annotation

### Logging

- Per-job log: `logs/{job_id}.log`
- Main service log: `logs/agent_annotate.log`
- RotatingFileHandler (10MB, 10 backups)
- Structured: agent decisions at INFO, API calls at DEBUG, errors at ERROR

---

## Dependency Graph

```
Phase 0 (Foundation)
    │
    ├── Phase 1 (Research Agents)
    │       │
    │       └── Phase 2 (Orchestrator + Annotation)
    │               │
    │               └── Phase 3 (Verification)
    │                       │
    │                       └── Phase 4 (Output + Review)
    │                               │
    └── Phase 5 (Frontend — can start after Phase 0 using stubs)
            │                       │
            └───────────────────────┘
                                    │
                              Phase 6 (Infrastructure)
                                    │
                              Phase 7 (Hardening)
```

Phase 5 (frontend) can be developed in parallel with Phases 1–4 since stub endpoints from Phase 0 provide the API contract.

---

## Patterns Referenced (Agent Annotate is fully independent)

Agent Annotate has **zero runtime dependencies** on other AMP LLM microservices. All research agents make direct HTTP calls to external APIs. The following patterns were referenced during development but no code is imported at runtime:

| Pattern | Referenced From | How Used |
|---------|----------------|----------|
| .env loading | `nct_lookup/nct_config.py` | Same parent-search pattern in `app/config.py` |
| Git commit tracking | `llm_assistant/llm_assistant.py` | Same subprocess pattern in `version_service.py` |
| Ollama API format | `llm_assistant/llm_assistant.py` | Same `/api/generate` call in `ollama_client.py` |
| Auth client | `tasker.amphoraxe.ca/app/auth_client.py` | Copied to `app/auth_client.py` |
| SPA serving | `tasker.amphoraxe.ca/app/main.py` | Same catch-all pattern in `app/main.py` |
| React scaffold | `tasker.amphoraxe.ca/frontend/` | Same Vite + Router pattern |
| Human annotation validation | `docs/clinical_trials-with-sequences.xlsx` | All valid values match Excel data validation rules |

---

## Files Modified (Not Created)

| File | Change |
|------|--------|
| `webapp/templates/index.html` | Add Agent Annotate tile to menu grid |
| `webapp/.env` | Add `AGENT_ANNOTATE_PORT=9005` |
| `.env` | Add `AGENT_ANNOTATE_PORT=9005` |
| Cloudflare tunnel config | Add ingress rule |
| `AMPHORAXE_INFRASTRUCTURE.md` | Add Agent Annotate section |
| `master_docs/*` | Update API map, port map, env vars |

---

## Ollama Model Assignments

| Role | Model | Size | Purpose |
|------|-------|------|---------|
| Primary Annotator | llama3.1:8b | 4.9 GB | Best general reasoning |
| Verifier 1 | gemma2:9b | 5.4 GB | Google architecture — different training |
| Verifier 2 | qwen2:latest | 4.4 GB | Alibaba architecture — different corpus |
| Verifier 3 | mistral:latest | 4.4 GB | Mistral architecture — different reasoning |
| Reconciler | qwen2.5:14b | 9.0 GB | Largest model for dispute resolution |

All sequential (one at a time) due to 16GB RAM.

---

## Phase 8: Accuracy Improvements — Surpassing Human Annotators

**Goal:** Fix agent errors and exploit structural advantages to exceed human inter-rater agreement on every field.
**Depends on:** Phases 0-7 (service must be running)
**See:** `docs/IMPROVEMENT_STRATEGY.md` for full analysis with error tables and human quality audit.

**Context:** Human annotators achieve only 48-92% inter-rater agreement depending on the field (Peptide: 48%, Outcome: 56%, Delivery Mode: 68%). ~50% of rows are unannotated. The agent's goal is not just to match humans but to surpass them through consistency, completeness, recency, and full evidence trails.

### 8.1 CSV Citation Columns (DONE)

Standard CSV now includes per-field evidence columns (`Classification Evidence`, etc.) with PMIDs, URLs, and database identifiers. Full CSV adds `{field}_evidence_sources`, `{field}_evidence_urls`, and `{field}_reasoning`. Previously zero citation data reached the CSV.

### 8.2 Output Validation & Cross-Field Consistency

Hard validation in `_parse_value()` — return `None` for unrecognizable values. Cross-field consistency in orchestrator:
- peptide=False → classification="Other"
- Positive outcome → empty failure reason
- Failed outcome + empty failure reason → flag for review

Verifier value normalization: "Intravenous"→"IV", "Active"→"Active, not recruiting", bare "AMP"→ambiguous.

### 8.3 Few-Shot Prompt Engineering

Replace instruction-heavy prompts with worked examples. 8B models follow examples far better than rules. Key additions:
- Peptide: 8 examples (Aviptadil=True, Kate Farm=False, semaglutide=True, pembrolizumab=False)
- Classification: Three-step tree (peptide? → AMP? → infection?) with examples. Fix: VIP/GLP-1/somatostatin are peptides but NOT AMPs → "Other"
- Delivery mode: Negative examples. Verifier prompt parity with primary.

### 8.4 Recency-Aware Literature Search

Sort PubMed/PMC by date descending. Add rule: "newest publication wins" to outcome/failure Pass 2 prompts. Include publication year in evidence output. Search for regulatory decisions and press releases.

### 8.5 Peptide Cascade Protection

If peptide flips during verification, re-run classification. Classification agent independently sanity-checks peptide when intervention contains "nutritional"/"formula".

### Phase 8 Targets

| Field | Human Agreement | Target Agent Accuracy |
|-------|-----------------|----------------------|
| Classification | 91.6% | >95% |
| Delivery Mode | 68.2% | >90% |
| Outcome | 55.6% | >90% |
| Reason for Failure | 91.3% | >95% |
| Peptide | 48.4% | >90% |
