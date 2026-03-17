# Agent Annotate — Comprehensive UI/UX Overhaul Plan

**Date:** 2026-03-16
**Goal:** Transform the agent-annotate frontend into a publication-grade scientific annotation platform with full concordance analytics, inter-run comparison, and researcher-friendly workflows.

---

## Status Overview

### Completed
- **Phase 7.1 (partial)**: Concordance Analysis Methodology documented in METHODOLOGY.md (Section 8), including blank handling protocol, value normalization rules, and inter-annotator reliability assessment.
- **Phase 7.2 (partial)**: Error analysis expanded in PAPER.md (Sections 4.3--4.6.1) with value distribution problems, verifier parsing failure root cause analysis, and retroactive fix results.
- **Phase 7.3 (partial)**: USER_GUIDE.md updated with maintenance scripts section (retroactive_fix.py, concordance_test.py, concordance_jobs.py).
- **Verifier value normalization fix (v4.1)**: Field-aware normalization in verification pipeline. Retroactive fix capability via `retroactive_fix.py`. Documented in METHODOLOGY.md Section 6.5 and IMPROVEMENT_STRATEGY.md Section 7.5.

### Pending
- **Phase 1**: Data Foundation (Backend) -- Review/Export integration, concordance engine service, concordance API, primary annotator reasoning, research coverage metadata.
- **Phase 2**: Concordance Dashboard (Frontend) -- New /concordance page with 4 tabs, chart library.
- **Phase 3**: Results Page Overhaul -- Dashboard view, inline evidence preview.
- **Phase 4**: Review Page Enhancement -- Primary annotator context, batch operations, keyboard shortcuts, guidelines reference, review impact preview.
- **Phase 5**: Pipeline & Submit Improvements -- Partial results streaming, research coverage in pipeline view, submit page enhancements.
- **Phase 6**: Settings & Configuration UI -- Model configuration, evidence threshold editor, consensus threshold slider.

---

## Phase 1: Data Foundation (Backend)

### 1.1 Review → Export Integration
**Problem:** Manual review decisions (approve/override/skip) don't update exported CSV/JSON.
**Changes:**
- `output_service.py`: When generating CSV/JSON, check review_service for decisions on each field
- If field was overridden: use reviewer_value as final_value, mark `review_status: "overridden"`
- If approved: mark `review_status: "approved"` (value unchanged)
- Add `reviewer_note` to output metadata
- New columns in full CSV: `{field}_review_status`, `{field}_reviewer_value`, `{field}_reviewer_note`
- Regenerate CSV/JSON on-demand after review changes (not cached from job completion)

### 1.2 Concordance Engine (New Backend Service)
**Problem:** No programmatic concordance calculation. Scripts exist but aren't integrated.
**Changes:**
- New file: `app/services/concordance_service.py`
- Loads human annotations from Excel file (path configurable in config.yaml)
- Calculates per-field: raw agreement %, Cohen's kappa, confusion matrix
- Supports comparisons: Agent vs R1, Agent vs R2, R1 vs R2
- Supports multi-version comparison: Job A vs Job B (same NCT IDs, different agent versions)
- Handles blank exclusion rules (blank=skip for all fields except reason_for_failure where blank=valid "no failure")
- Value normalization (case-insensitive, alias mapping)
- Returns structured results: per-field stats, per-trial matrix, disagreement list, value distributions

**Concordance Metrics (to be documented in METHODOLOGY.md and PAPER.md):**
- **Raw Agreement Rate**: % of overlapping, non-blank annotations where values match exactly (after normalization)
- **Cohen's Kappa (κ)**: Chance-corrected agreement. Formula: κ = (P_o - P_e) / (1 - P_e) where P_o = observed agreement, P_e = expected agreement by chance. Interpretation per Landis & Koch (1977): <0 Poor, 0–0.20 Slight, 0.21–0.40 Fair, 0.41–0.60 Moderate, 0.61–0.80 Substantial, 0.81–1.00 Almost Perfect
- **Confusion Matrix**: Per-field NxN matrix showing how agent values map to human values
- **Value Distribution Comparison**: Side-by-side frequency counts (Agent vs R1 vs R2) to detect systematic bias
- **Blank Handling Protocol**: For all fields except reason_for_failure, blank human annotations are excluded (blank = not annotated, not a value choice). For reason_for_failure, blank = "no failure reason" and IS included in comparisons
- **Normalization Rules**: Case-insensitive matching, alias resolution (e.g., "IV" = "Intravenous", "Active" = "Active, not recruiting"), multi-value delivery modes sorted alphabetically before comparison

### 1.3 Concordance API Endpoints
**New router:** `app/routers/concordance.py`
- `GET /api/concordance/jobs/{job_id}` — concordance of a job against human annotations
- `GET /api/concordance/compare/{job_id_a}/{job_id_b}` — inter-version comparison
- `GET /api/concordance/history` — concordance trends across all jobs
- `GET /api/concordance/human` — R1 vs R2 human inter-rater agreement
- All endpoints return structured JSON with stats, matrices, disagreements

### 1.4 Primary Annotator Reasoning in Review Items
**Problem:** Review page shows verifier opinions but not primary annotator reasoning.
**Changes:**
- `app/models/job.py`: Add `primary_reasoning` and `primary_confidence` to ReviewItem
- `app/services/orchestrator.py`: Populate these when flagging items for review
- Review API returns the full chain-of-thought from the primary annotator

### 1.5 Research Coverage Metadata
**Problem:** No visibility into which research agents returned useful data.
**Changes:**
- `app/services/orchestrator.py`: Track per-trial research coverage
- Store: agent_name → {citations_count, has_data: bool, quality_avg: float}
- Include in trial output JSON and expose via results API

---

## Phase 2: Concordance Dashboard (Frontend)

### 2.1 New Page: Concordance (`/concordance`)
**Layout:** Full-width dashboard with tabs

**Tab 1: Agent vs Human**
- Job selector dropdown (completed jobs only)
- Summary table: Field | N | Agent vs R1 (%) | κ | Agent vs R2 (%) | κ | R1 vs R2 (%) | κ
- Color-coded cells: green (>0.6κ), yellow (0.2–0.6), red (<0.2)
- Per-field expandable sections:
  - Confusion matrix (heatmap)
  - Value distribution bar chart (Agent / R1 / R2 side-by-side)
  - Disagreement list: NCT ID | Agent Value | Human Value | Evidence snippet

**Tab 2: Version Comparison**
- Two job selector dropdowns (Job A vs Job B)
- Field-by-field diff: which annotations changed between versions
- Summary: X improved, Y regressed, Z unchanged
- Highlight regressions in red, improvements in green
- Concordance delta table: how κ changed per field

**Tab 3: Human Inter-Rater**
- R1 vs R2 agreement table (no job dependency)
- Shows baseline human reliability per field
- Highlights fields where humans disagree most (context for agent evaluation)

**Tab 4: Trends**
- Line chart: κ per field over time (x-axis = job date, y-axis = kappa)
- Shows improvement trajectory as agents are refined
- Separate lines for Agent vs R1 and Agent vs R2

### 2.2 Chart Library
- Use **Recharts** (lightweight, React-native, already compatible with Vite)
- Chart types needed: bar charts (value distributions), heatmaps (confusion matrices), line charts (trends)
- Install: `npm install recharts`

---

## Phase 3: Results Page Overhaul

### 3.1 Results Dashboard View
**Replace** the simple results table with a rich dashboard when viewing a specific job.

**Header:** Job ID, timing metadata, version info, export buttons

**Section 1: Summary Cards**
- Total trials | Successful | Failed | Flagged for Review
- Per-field consensus rate (mini donut charts)
- Overall confidence distribution

**Section 2: Annotation Table (enhanced)**
- Columns: NCT ID | Classification | Delivery Mode | Outcome | Failure Reason | Peptide | Status
- Each cell shows the value + a confidence indicator (green/yellow/red dot)
- Expandable row showing:
  - Primary annotator reasoning (full chain-of-thought)
  - Evidence citations with source links
  - Verifier opinions (compact: "3/3 agree" or "1/3 agree → reconciled")
  - Research coverage (which agents contributed)
- Sortable and filterable by any column
- Filter by: status (OK/Review), field value, confidence range

**Section 3: Field Analytics**
- Per-field value distribution (bar chart)
- Confidence distribution (histogram)
- Consensus rate breakdown (agreed / reconciled / manual review)
- Model disagreement matrix (which verifier disagrees most on which field)

**Section 4: Export**
- Download CSV (Standard) — with review decisions integrated
- Download CSV (Full) — complete traceability
- Download JSON — raw data
- Copy concordance summary as formatted table (for papers)

### 3.2 Inline Evidence Preview
- Hover/click on any annotation value shows a tooltip/popover with:
  - Top 3 evidence citations (source name, snippet, URL)
  - Annotator model name
  - Confidence score
  - Verifier summary

---

## Phase 4: Review Page Enhancement

### 4.1 Primary Annotator Context
- Show the primary annotator's full reasoning alongside verifier opinions
- Display the evidence citations that the primary annotator used
- Show confidence score prominently

### 4.2 Batch Operations
- "Approve all where ≥2/3 verifiers agree" button
- "Approve all in this job" button (with confirmation)
- Field-specific filter: only show review items for a specific field
- Status filter: pending / decided / all

### 4.3 Keyboard Shortcuts
- `a` = Approve current item
- `o` = Focus override dropdown
- `s` = Skip current item
- `r` = Retry current item
- `n` / `↓` = Next item
- `p` / `↑` = Previous item
- Display shortcut hints on buttons

### 4.4 Annotation Guidelines Reference
- Collapsible sidebar showing valid values with definitions
- For each field, show:
  - Valid values list
  - One-line definition per value
  - Decision rules (when to pick which value)
- Pulled from the agent's VALID_VALUES and prompt definitions

### 4.5 Review Impact Preview
- Before approving/overriding, show how the decision affects the concordance
- "This override would change agent agreement with R1 from 29% to 31%"

---

## Phase 5: Pipeline & Submit Improvements

### 5.1 Partial Results Streaming
- While job is running, show completed trials in a "live results" tab
- Use polling (2s interval) to fetch completed trial annotations
- New endpoint: `GET /api/results/{job_id}/partial` — returns trials completed so far

### 5.2 Research Coverage in Pipeline View
- During Phase 1, show which research agents completed per trial
- Grid: NCT ID rows × Agent columns, cells show ✓/✗/⏳
- Helps identify API failures early

### 5.3 Submit Page Enhancements
- File upload (CSV/text with NCT IDs)
- Paste from clipboard with auto-detection
- Show count + preview of valid/invalid IDs before submit
- Option to select hardware profile (mac_mini / server)

---

## Phase 6: Settings & Configuration UI

### 6.1 Model Configuration
- Dropdown selectors for each model role (primary, verifier_1, verifier_2, verifier_3, reconciler)
- Populated from `/api/status/models` (available Ollama models)
- Save via PUT /api/settings
- Show current hardware profile with explanation

### 6.2 Evidence Threshold Editor
- Slider for each field's min_sources and min_quality
- Live preview: "With these settings, X of last 70 trials would have been flagged"

### 6.3 Consensus Threshold
- Slider: 0.33 (any 1 verifier) to 1.0 (unanimous)
- Impact preview: "At 0.67, X fewer items would need review"

---

## Phase 7: Documentation Updates

### 7.1 METHODOLOGY.md
- New section: "Concordance Analysis Methodology"
  - Mathematical formulation of Cohen's kappa with worked example
  - Blank handling protocol with rationale
  - Value normalization rules with full alias table
  - Multi-version comparison methodology
  - Statistical interpretation guidelines (Landis & Koch scale)
- New section: "Inter-Rater Reliability Assessment"
  - How human R1 vs R2 disagreement contextualizes agent performance
  - Fields where human agreement is low (Peptide, Outcome) vs high (Classification)

### 7.2 PAPER.md
- Expanded Results section with concordance tables and figures
- Error analysis methodology: how value distribution comparison reveals systematic bias
- Version comparison methodology: measuring improvement between agent iterations
- Visualization descriptions matching the UI charts

### 7.3 USER_GUIDE.md
- Updated with all new UI pages and workflows
- Concordance dashboard guide
- Review workflow with keyboard shortcuts
- Export options and format descriptions

---

## Implementation Order

| Priority | Phase | Estimated Scope | Depends On |
|----------|-------|-----------------|------------|
| 1 | 1.1 Review→Export | Small (output_service.py) | Nothing |
| 2 | 1.2 Concordance Engine | Medium (new service) | Nothing |
| 3 | 1.3 Concordance API | Small (new router) | 1.2 |
| 4 | 2.1 Concordance Dashboard | Large (new page + charts) | 1.3 |
| 5 | 2.2 Chart Library | Small (npm install) | Nothing |
| 6 | 3.1 Results Dashboard | Large (rewrite ResultsPage) | 1.1 |
| 7 | 3.2 Evidence Preview | Medium (tooltips/popovers) | 3.1 |
| 8 | 1.4 Primary Reasoning | Small (model + orchestrator) | Nothing |
| 9 | 4.1-4.5 Review Enhancements | Medium (ReviewPage updates) | 1.4 |
| 10 | 5.1-5.3 Pipeline Improvements | Medium (new endpoint + UI) | Nothing |
| 11 | 6.1-6.3 Settings UI | Medium (SettingsPage rewrite) | Nothing |
| 12 | 1.5 Research Coverage | Small (orchestrator metadata) | Nothing |
| 13 | 7.1-7.3 Documentation | Medium (3 doc files) | All above |

**Critical path:** 1.2 → 1.3 → 2.1 (concordance engine → API → dashboard)

---

## Technical Stack Additions

- **Recharts** — React charting (bar, line, heatmap via custom cells)
- No other new dependencies needed
- All new pages follow existing dark theme design system
- All new API endpoints protected by auth middleware (except concordance/human which is read-only reference data)
