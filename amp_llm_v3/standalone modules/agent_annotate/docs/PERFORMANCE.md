# Agent Annotate — Performance & Scale

Operational guide for running Agent Annotate at scale (hundreds to tens of thousands of NCTs). Written 2026-04-21 as part of the v42.6 efficiency pack.

## Per-trial cost model (Mac Mini, qwen3:14b stack)

| Trial path | LLM calls | Wall time |
|---|---|---|
| peptide=False (cascaded) | 1 peptide annotator + 3 verifiers | ~2.5 min |
| peptide=True (full) | ~15–25 LLM calls (varies by pub count) | ~7–10 min |

Pub-count bottlenecks: outcome_atomic Tier 1b fires once per trial-specific/ambiguous pub. Capped by `outcome_atomic_max_voting_pubs` (default 20). Most trials have 2–8 candidate pubs after Tier 1a pre-filtering.

## Napkin scaling for a 30k-NCT job

Assuming 60% peptide=False / 40% peptide=True, no efficiency flags:

- 18k peptide=False × 2.5 min = **750 hours sequential** (~31 days)
- 12k peptide=True × 8.5 min = **1,700 hours sequential** (~71 days)
- **Sequential total ~100 days on current Mac Mini** — unworkable.

The v42.6 efficiency pack cuts this substantially. All flags are OFF by default (safe) and can be enabled per-job.

## v42.6 efficiency flags (orchestrator config)

### Eff #1 — `skip_legacy_when_atomic: bool`

When `prefer_atomic_classification` or `prefer_atomic_failure_reason` is on, the legacy agent runs alongside the atomic one and its output lives under `<field>_legacy` for audit. Legacy is a two-pass LLM (~60s) + 3 verifiers (~90s) = ~2.5 min per peptide=True trial.

Turn this on after you're confident in the atomic agent. Saves **~3–4 min per peptide=True trial**. Cost: loses the legacy audit column.

### Eff #2 — `deterministic_peptide_pregate: bool`

Before the peptide LLM call, inspect clinical_protocol interventions. If intervention type is a non-peptide category (Drug small-molecule, Device, Behavioral, Procedure, etc.) AND no UniProt/DRAMP/APD/DBAASP hit AND no known-sequence match, declare `peptide=False` without the LLM + 3 verifiers.

No drug-name cheat sheets; decision is structural. Saves **~2 min per ~40% of trials**.

### Eff #3 — `skip_amp_research_for_non_peptides: bool`

When `clinical_protocol` indicates a clearly non-peptide intervention (Device, Procedure, etc.), skip DBAASP, APD, RCSB_PDB, PDBe, EBI_proteins research agents. These only contribute AMP-specific evidence.

Saves **~20s per ~40% of trials**. Conservative: defers on `Biological` and `Drug` types (ambiguous).

### Eff #4 — `skip_verification_on_legacy: bool` (default **true**)

When the prefer_atomic swap creates a shadow `<field>_legacy`, mark it `skip_verification=True` so it doesn't burn 3 verifier LLM calls on an audit-only column. Default **on** — audit data rarely benefits from blind verification.

Saves **~2 min per peptide=True trial**.

### Eff #5 — `biorxiv_drug_name_prefilter: bool` (default **true**)

Drop bioRxiv/medRxiv preprints whose title+snippet contain zero mentions of any intervention name. Reduces Tier 1a "ambiguous" bucket, avoiding wasted Tier 1b LLM calls on off-topic preprints.

Safe; small win (~5s/trial on average).

### Eff #7 — `verifier_fast_models: list[str]`

Replace the three verifier models with smaller/faster alternatives (e.g., `["llama3.2:3b", "qwen3:1.7b", "gemma3:4b"]`). 3–5x verifier throughput.

Trade-off: verifier consensus quality may degrade on edge cases. The reconciler stays on qwen3:14b, so final values on disagreements are unchanged. Recommended for high-volume throughput runs where verifier-level disagreements feeding the reconciler is acceptable.

Empty list = use `verification.models` (current default verifier_1/2/3).

## Recommended configurations

### High-throughput 30k-NCT job (accuracy/speed balanced)

```yaml
orchestrator:
  # Full atomic cut-over
  prefer_atomic_classification: true
  prefer_atomic_failure_reason: true
  skip_legacy_when_atomic: true
  skip_verification_on_legacy: true   # (default)
  # Skip LLM for obvious non-peptides
  deterministic_peptide_pregate: true
  # Skip AMP-only research for clearly non-peptide interventions
  skip_amp_research_for_non_peptides: true
  # Cap Tier 1b pub scanning
  outcome_atomic_max_voting_pubs: 15
```

Projected saving: **~40–50% wall-clock** vs default config.

### Maximum throughput (accept slightly lower verifier quality)

Add to above:
```yaml
  verifier_fast_models:
    - "llama3.2:3b"
    - "qwen3:1.7b"
    - "gemma3:4b"
```

Projected saving: **~55–65% wall-clock**.

### Audit / validation run (no efficiency, full data)

All flags OFF. Use this when comparing atomic vs legacy is the goal (which it was through Phase 5).

## Eff #6 — Parallelism (infra)

The Mac Mini runs one Ollama instance with a global `asyncio.Lock()` — only one LLM generates at a time. For 30k-NCT jobs this is the throughput ceiling.

Options ranked by effort/reward:

1. **Multi-worker split** (low effort, ~3x). Split the NCT list across 3 independent workers each running on different hardware (Mac Mini + 2 cloud instances). Each worker has its own Ollama + agent-annotate service. Merge output at end via NCT-ID union of annotation JSONs.

2. **Concurrent Ollama models** (medium, 2x+). Run multiple model instances on a larger server (A100/H100 GPU with ≥80GB VRAM can host gemma3:12b, qwen3:14b, qwen3:8b, llama3.1:8b simultaneously). Remove the global asyncio lock, let verifier + annotator run in parallel.

3. **Batched generation** (high, 1.5x). Many Ollama-compatible runtimes (vLLM, SGLang) support batched inference natively. Queue 4–8 Tier 1b atomic pub assessments per batch; throughput goes up linearly until GPU memory-bound.

For 30k NCTs, **option 1 is most pragmatic** — no code changes, sub-week deploy.

## Eff #8 — Batch research across NCTs (infra refactor)

Currently each NCT runs 16 research agents independently. Many of those agents make identical or near-identical API calls:

- `chembl`: each NCT queries by drug name. Many NCTs share interventions (e.g., 200+ trials test semaglutide). A single ChEMBL batch call for 50 drug names at once would replace 50 individual calls.
- `openalex`: NCT-ID search is already batchable — OpenAlex accepts comma-separated IDs.
- `semantic_scholar`: supports bulk paper lookup.
- `crossref`: supports batch DOI lookup.

Estimated savings: ~30–50% of research phase time (which is 15–30s/NCT out of 7–10min total, so the end effect is single-digit percent of total wall-clock, but meaningful at 30k scale).

Scope: significant refactor. Would need:
- Research agents gain a `batch_research(nct_ids, metadatas)` method
- Orchestrator collects all NCTs' metadata, pre-dispatches batch calls, distributes results back
- Graceful fallback to per-NCT when batch call fails

**Not worth building unless you're running 10k+ NCT jobs regularly.** Option 1 (multi-worker split) gets you further for less engineering.

## Monitoring

- `curl -H "Authorization: Bearer $TOKEN" http://localhost:8005/api/jobs/<id>` — status + progress + warnings/errors
- `results/annotations/<job_id>/NCT*.json` — per-NCT annotations (persisted as they complete)
- `LEARNING_RUN_PLAN.md` — track every job with commit hash, NCT count, outcome metrics

## Reference: per-NCT LLM call breakdown (all flags off)

| Phase | LLM calls | Notes |
|---|---|---|
| peptide annotator | 2 (2-pass) | ~60s |
| peptide verifiers | 3 | ~90s |
| peptide reconciliation (if disagreement) | 1 | ~30s |
| classification 2-pass | 2 | ~60s |
| classification verifiers | 3 | ~90s |
| classification_atomic | 1 | ~30s |
| delivery_mode | 1 | ~30s |
| delivery_mode verifiers | 3 | ~90s |
| outcome 2-pass | 2 | ~60s |
| outcome verifiers | 3 | ~90s |
| outcome_atomic Tier 1b | N (per pub) | ~30s each |
| reason_for_failure (gated) | 0–2 | ~30-60s |
| reason_for_failure_atomic | 0–1 | ~30s |

With `skip_legacy_when_atomic + skip_verification_on_legacy + deterministic_peptide_pregate`, peptide=True trials drop from ~15–25 LLM calls to ~8–10, roughly half.
