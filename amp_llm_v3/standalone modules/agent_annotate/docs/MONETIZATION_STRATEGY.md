# Agent Annotate — Monetization Strategy

## Executive Summary

Agent Annotate is a locally-run, multi-agent clinical trial annotation pipeline that produces publication-grade structured annotations for antimicrobial peptide (AMP) trials. It uses 12 research agents querying 17+ free databases, 5 annotation agents, and 3-model blind verification — all running on local hardware via Ollama with **zero external API costs**.

The core value proposition: **what costs $200-400/trial with human annotators and takes weeks is done in 3-5 minutes for ~$0.15/trial**. On the Outcome field, agents scored 72.7% agreement vs a 55.6% human inter-rater baseline — meaning the system is measurably *more consistent* than trained humans.

This doc evaluates five monetization models, ranked by fit.

---

## Cost Baseline

Understanding what it costs to run Agent Annotate is critical for pricing any model.

| Component | Cost | Notes |
|-----------|------|-------|
| LLM inference | $0 | All models local via Ollama |
| External APIs | $0 | All 17+ sources are free-tier |
| Hardware (dev) | ~$2,000 one-time | Mac Mini M4, 16GB — sufficient for 8b models |
| Hardware (server) | ~$8,000-15,000 one-time | 48+ GB RAM enables premium models (Kimi K2 Thinking) |
| Per-trial compute | ~$0.10-0.30 | Electricity only (3-5 min GPU time) |
| 100-trial batch | ~$10-30 | ~5-8 hours wall time on Mac Mini |
| 5,000 trials/year | ~$500-1,500/year | Electricity at ~80-300W draw |

**Human annotator comparison:** ~$200-400/trial loaded cost ($100k+ salary for 250-500 trials/year). Agent Annotate delivers a **1,000-4,000x cost reduction**.

---

## Option 1: SaaS — Per-Trial Pricing

**Model:** Hosted platform. Customers submit NCT IDs via web UI or API, receive annotated results with full evidence chains.

### Pricing

| Tier | Price/Trial | Includes |
|------|------------|----------|
| Pay-as-you-go | $2.00 | Standard CSV output, 5-field annotation + evidence citations |
| Volume (500+/year) | $1.00 | Full JSON with verification metadata, priority queue |
| Enterprise (5,000+/year) | $0.50 | Dedicated queue, custom fields, API integration, SLA |

### Cost/Benefit

| | Details |
|---|---|
| **Revenue potential** | 5,000 trials/year at blended $1.00 = $5,000/year from a single mid-size client. 10 clients = $50K ARR. Enterprise deals could push this to $100K+. |
| **Gross margin** | 95%+ (compute cost ~$0.15/trial, selling at $0.50-2.00) |
| **Startup cost** | $8-15K for a proper server; ~$500/year hosting/tunnel infrastructure |
| **Pros** | Lowest friction for customers. Recurring revenue. Network effects — more trials = better EDAM. Can upsell from pay-as-you-go to volume. |
| **Cons** | Requires always-on infrastructure and support. Pharma customers may resist sending trial IDs to external servers (even though all data is from public registries). Competitive pressure on price. |
| **Fit** | **Good for academic and small biotech customers** who want results without running infrastructure. |

### Risk: Data Sensitivity

Clinical trial NCT IDs are public, but the *pattern* of which trials a company is annotating could reveal competitive intelligence (e.g., a pharma company bulk-annotating a competitor's pipeline). Mitigate with strict privacy policies and no cross-customer data sharing.

---

## Option 2: On-Premise License

**Model:** One-time or annual license fee. Customer runs Agent Annotate on their own hardware. Amphoraxe provides the software, documentation, and model configs.

### Pricing

| Tier | Price | Includes |
|------|-------|----------|
| Academic license | $5,000/year | Full system, community support, quarterly updates |
| Commercial license | $25,000/year | Full system, priority support, monthly updates, custom field development |
| Enterprise perpetual | $75,000-150,000 one-time | Perpetual license, 1 year support, on-site installation assistance |

### Cost/Benefit

| | Details |
|---|---|
| **Revenue potential** | 5 commercial licenses = $125K/year. One enterprise deal = $75-150K. |
| **Gross margin** | Near 100% (customer provides hardware; Amphoraxe delivers software) |
| **Startup cost** | Packaging, documentation, installation tooling (~2-4 weeks of work). Ongoing support overhead. |
| **Pros** | Addresses pharma data-sovereignty concerns (nothing leaves their network). High-value contracts. Aligns with existing local-inference architecture — this is *already* how the system works. No infrastructure scaling burden on Amphoraxe. |
| **Cons** | Longer sales cycle. Requires customer to have Ollama-capable hardware. Support burden (customer environments vary). Harder to capture EDAM improvements across deployments. |
| **Fit** | **Best for pharma and large biotech** with in-house compute and strict data governance. This is the highest-margin model and plays directly to Agent Annotate's architectural strength (fully local, no cloud dependencies). |

---

## Option 3: Annotation-as-a-Service (Consulting/Contract)

**Model:** Amphoraxe runs annotation jobs for clients as a service engagement. Client sends a list of NCT IDs and annotation requirements; Amphoraxe delivers a complete annotated dataset with evidence citations.

### Pricing

| Engagement | Price | Includes |
|------------|-------|----------|
| Pilot (25-50 trials) | Free / $500 | Demonstrate accuracy vs human baseline, build trust |
| Systematic review package (100-500 trials) | $2,000-5,000 | Full annotation, evidence report, methodology section for publication |
| Pipeline analysis (500-2,000 trials) | $5,000-15,000 | Competitive landscape mapping, trend analysis, structured dataset |
| Custom annotation schema | $10,000-25,000 | New fields, new disease area adaptation, validation against client ground truth |

### Cost/Benefit

| | Details |
|---|---|
| **Revenue potential** | 10 systematic review engagements/year at $3,500 avg = $35K. 2-3 pipeline analyses = $20-45K. Custom work = $10-25K each. Total potential: $65-105K/year. |
| **Gross margin** | 80-90% (mostly labor for QA, client communication, and custom work) |
| **Startup cost** | Minimal — already have the system. Need client-facing deliverable templates. |
| **Pros** | Fastest path to revenue. No product packaging needed. Free pilot is a powerful sales tool (let the accuracy numbers sell). Builds case studies for other models. Captures domain expertise as a competitive moat. |
| **Cons** | Doesn't scale linearly (labor-bound for custom work). Revenue is lumpy/project-based. Client may expect ongoing support after engagement ends. |
| **Fit** | **Best as a go-to-market strategy** — use consulting engagements to build relationships and case studies, then upsell to SaaS or on-premise licenses. |

---

## Option 4: Research Data Product

**Model:** Sell pre-annotated, continuously updated datasets. Maintain a living database of all AMP-related clinical trials with structured annotations, updated as new trials are registered.

### Pricing

| Product | Price | Includes |
|---------|-------|----------|
| AMP Trial Database (annual) | $10,000-25,000/year | All AMP trials (~5,000-10,000), quarterly re-annotation, CSV/JSON export, evidence citations |
| Custom disease-area dataset | $15,000-40,000/year | Adapted pipeline for oncology/endocrinology/neuro peptide trials |
| API access to live database | $2,000-5,000/month | Real-time query access, webhook notifications for new trial annotations |

### Cost/Benefit

| | Details |
|---|---|
| **Revenue potential** | 5 database subscribers at $15K = $75K/year. API access adds $24-60K/year per subscriber. |
| **Gross margin** | 90%+ after initial annotation run (incremental cost is only new trials, ~500/year) |
| **Startup cost** | Need to run full annotation on all ~5,000-10,000 existing AMP trials (estimated 2-4 weeks compute on Mac Mini, or 3-5 days on server). Data validation/QA pass. |
| **Pros** | Recurring revenue with minimal incremental cost. Creates a proprietary data asset that appreciates over time. Subscribers get value immediately (no onboarding). Competitive moat — hard to replicate the full annotated dataset. |
| **Cons** | Requires upfront investment to annotate the full corpus. Competes with free ClinicalTrials.gov data (differentiation is the structured annotation layer). Needs ongoing maintenance as annotation schema evolves. |
| **Fit** | **Strong long-term play.** Particularly valuable for pharma competitive intelligence teams who want structured, queryable trial data rather than raw registry text. |

---

## Option 5: Open-Core / Freemium

**Model:** Open-source the core annotation engine. Monetize through premium features, hosted service, and support.

### Pricing

| Tier | Price | Includes |
|------|-------|----------|
| Community (open-source) | Free | Core pipeline, basic annotation, single-model verification |
| Pro | $500/month | Multi-model verification, EDAM learning, premium model configs, agreement analytics |
| Enterprise | $2,000+/month | Custom fields, API, priority support, on-premise deployment assistance |

### Cost/Benefit

| | Details |
|---|---|
| **Revenue potential** | Slow initial revenue. If 2% of 1,000 community users convert to Pro = 20 users x $500 = $10K/month = $120K/year. Enterprise adds $24K+/year per customer. |
| **Gross margin** | 85%+ (SaaS hosted) to 95%+ (self-hosted Pro licenses) |
| **Startup cost** | Significant — need to split codebase into open/premium, build licensing system, write public documentation, manage community. ~4-8 weeks. |
| **Pros** | Builds community and brand recognition. Attracts contributors who improve the core. Academic adoption drives citations and credibility. Funnel to paid tiers is organic. |
| **Cons** | Gives away the core technology. Competitors can fork. Community management overhead. Slow revenue ramp. Risk of free tier being "good enough" for most users. |
| **Fit** | **Best if the goal is market dominance and academic credibility** over near-term revenue. Pairs well with publishing the PAPER.md — open-source + paper = rapid adoption in research community. |

---

## Recommendation: Phased Approach

### Phase 1 — Prove It (Months 1-3)
**Model: Consulting/Contract (Option 3)**

- Run 3-5 free pilot engagements (25-50 trials each) with AMP research groups
- Use pilots to generate case studies and accuracy benchmarks
- Target: academic collaborators and small biotech
- Revenue: $0 (investment phase) to $10K from early paid engagements
- Deliverable: 2-3 case studies showing accuracy vs human annotation

### Phase 2 — Productize (Months 4-8)
**Model: SaaS (Option 1) + Data Product (Option 4)**

- Launch hosted SaaS with per-trial pricing
- Begin full-corpus annotation run for the AMP Trial Database
- Publish the PAPER.md to establish academic credibility
- Target: systematic review authors, CROs, mid-size biotech
- Revenue: $20-50K ARR from SaaS + early database subscribers

### Phase 3 — Scale (Months 9-18)
**Model: On-Premise License (Option 2) + expanded Data Products**

- Offer on-premise licensing to pharma companies identified during Phase 1-2
- Expand annotation pipeline to adjacent disease areas (oncology peptides, GLP-1 agonists)
- Build API access tier for the data product
- Target: large pharma, regulatory consultants
- Revenue: $100-250K ARR (blended across all models)

### Phase 4 — Optionally Open (Month 18+)
**Model: Evaluate Open-Core (Option 5)**

- Only if market position is strong enough that open-sourcing the core builds a moat rather than eroding one
- Decision criteria: >$200K ARR, >3 enterprise customers, published paper with citations

---

## Competitive Landscape

| Competitor | Model | Price | Weakness Agent Annotate Exploits |
|-----------|-------|-------|------|
| **Manual annotation** (CROs, academic labs) | Labor | $200-400/trial | 1,000x cost, weeks of delay, 48-91% inter-rater agreement |
| **TrialTrove / Cortellis** | SaaS subscription | $10-50/trial equiv. | Fixed schema, black-box, cloud-only, no evidence citations |
| **Single-LLM approaches** (GPT/Claude API) | Per-token API | $0.50-5.00/trial | No verification, hallucination risk, data leaves network, no multi-source research |
| **ClinicalTrials.gov raw** | Free | $0 | Unstructured, no annotation layer, stale status fields, no literature cross-reference |

**Agent Annotate's structural moats:**
1. **Local inference** — no data leaves the network (pharma-friendly)
2. **Zero API costs** — all 17+ data sources are free-tier
3. **Blind multi-model verification** — catches errors single-pass systems miss
4. **EDAM self-learning** — improves with every trial annotated
5. **Deterministic-first** — 80% of trials resolved without LLM (faster, cheaper, more reliable)
6. **Evidence traceability** — every annotation cites sources with PMIDs and URLs
7. **Published methodology** — PAPER.md provides academic credibility competitors lack

---

## Key Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Market too small (AMP trials only) | Medium | High | Expand to adjacent peptide therapeutics (GLP-1, calcitonin, oncology peptides) — pipeline architecture is disease-agnostic |
| Free LLM tools become "good enough" | Medium | Medium | Verification layer + evidence traceability are hard to replicate; single-LLM accuracy ceiling is well below multi-agent |
| Customer acquisition is slow | High | Medium | Free pilots lower barrier; academic publishing drives inbound; partner with AMP research consortia |
| Hardware requirements deter customers | Low | Medium | Mac Mini sufficient for dev; cloud GPU options (Lambda, RunPod) for customers without hardware |
| Regulatory changes to API access | Low | High | All APIs are public government/academic resources; diversified across 17+ sources |

---

## Bottom Line

The strongest near-term path is **consulting engagements (Option 3) to build case studies**, transitioning to **SaaS + data products (Options 1+4) for recurring revenue**, with **on-premise licensing (Option 2) as the high-margin enterprise play**. The local-inference architecture is not a limitation — it's the key selling point for pharma customers who won't send data to cloud APIs.

**Conservative 18-month target:** $100-150K ARR
**Aggressive 18-month target:** $200-300K ARR (requires 2+ enterprise on-premise deals)

The unit economics are exceptional: 95%+ gross margin at any scale, with compute costs under $0.30/trial against pricing of $0.50-2.00/trial (SaaS) or $25K+/year (license). The constraint is not margin — it's market access and sales velocity.
