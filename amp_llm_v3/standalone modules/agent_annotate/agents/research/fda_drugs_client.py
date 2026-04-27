"""
FDA Drugs@FDA Research Agent (v42.7.0, 2026-04-25).

Queries openFDA's Drugs@FDA database for drug application records,
including approval submissions, labels, and approval letters. A drug
with an "AP" (Approved) submission status for a specific indication
is the strongest possible Positive-outcome signal: regulatory bodies
have reviewed the trial data and granted approval.

Why this matters for the pipeline:
  Strengthens v42.6.14's "FDA approved" strong-efficacy gate. The gate
  currently relies on pub-text matching for phrases like "FDA approved"
  — easily false-positive on review articles. This API gives a
  structured, authoritative answer: is this drug FDA-approved? What
  application number? When? What indication?

API:
  https://api.fda.gov/drug/drugsfda.json?search=openfda.generic_name:<name>
  Documentation: https://open.fda.gov/apis/drug/drugsfda/

Free, no key (rate-limited to 240 req/min, 1000 req/hour without key —
plenty for our use case).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx

from agents.base import BaseResearchAgent
from agents.research.drug_cache import drug_cache
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.fda_drugs")

FDA_DRUGS_URL = "https://api.fda.gov/drug/drugsfda.json"
# v42.7.12 (2026-04-27): label endpoint for indications_and_usage text.
# Used to surface "drug X is approved for indication Y" so the outcome agent
# can disambiguate "drug approved for X, trial tested Y" — the over-call
# pattern Job #92 surfaced (calcitonin/exenatide/etc. approved for one
# indication but tested off-label for another).
FDA_LABEL_URL = "https://api.fda.gov/drug/label.json"


def _extract_intervention_names(metadata: Optional[dict]) -> list[str]:
    if not metadata:
        return []
    raw = metadata.get("interventions", [])
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    _SKIP = {"placebo", "saline", "vehicle", "normal saline", "standard of care"}
    for item in raw:
        if isinstance(item, dict):
            name = (item.get("name") or item.get("intervention_name") or "").strip()
            itype = (item.get("type") or "").upper()
            if itype in ("DRUG", "BIOLOGICAL") and name and name.lower() not in _SKIP:
                names.append(name)
        elif isinstance(item, str) and item.strip().lower() not in _SKIP:
            names.append(item.strip())
    return names


class FDADrugsClient(BaseResearchAgent):
    """Query openFDA Drugs@FDA database for drug approval records."""

    agent_name = "fda_drugs"
    sources = ["fda_drugs"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations: list = []
        raw_data: dict = {}
        interventions = _extract_intervention_names(metadata)

        if not interventions:
            return ResearchResult(
                agent_name=self.agent_name, nct_id=nct_id,
                citations=[], raw_data={"note": "No interventions to search"},
            )

        async with httpx.AsyncClient(timeout=20) as client:
            for intervention in interventions[:3]:
                async def compute(intv=intervention):
                    return await self._fetch_intervention(client, intv)

                if drug_cache.is_enabled():
                    per = await drug_cache.get_or_compute(
                        self.agent_name, intervention, compute,
                    )
                else:
                    per = await compute()

                citations.extend(per["citations"])
                raw_data.update(per["raw_data"])

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _fetch_intervention(self, client: httpx.AsyncClient, intervention: str) -> dict:
        """Search Drugs@FDA for one drug name. Pure function of name."""
        citations: list = []
        raw_data: dict = {}
        # openFDA full-text search. Quote the term to handle multi-word drug
        # names (e.g. "Glucagon-like peptide 1"). FDA API uses Lucene syntax.
        # Use literal spaces around OR; httpx URL-encodes as '+' which the API
        # parses as whitespace. Hand-coding '+OR+' gets double-encoded.
        #
        # v42.7.9 (2026-04-27): older Drugs@FDA records (e.g. NDA021481
        # Fuzeon/enfuvirtide, approved 2003) have empty `openfda.*` blocks
        # but the drug names ARE present in `products[].brand_name` and
        # `products[].active_ingredients[].name`. Restricting search to
        # openfda.* misses every pre-2010 approval. The fix: query both
        # field families. The first hit on either path returns the record.
        clean = intervention.replace('"', "")
        query = (
            f'openfda.brand_name:"{clean}" OR '
            f'openfda.generic_name:"{clean}" OR '
            f'openfda.substance_name:"{clean}" OR '
            f'products.brand_name:"{clean}" OR '
            f'products.active_ingredients.name:"{clean}"'
        )
        params = {"search": query, "limit": 5}
        try:
            resp = await resilient_get(FDA_DRUGS_URL, client=client, params=params)
            if resp.status_code == 404:
                # 404 from openFDA means "no results" — not an error
                raw_data[f"fda_drugs_{intervention}_count"] = 0
                return {"citations": citations, "raw_data": raw_data}
            if resp.status_code != 200:
                raw_data[f"fda_drugs_{intervention}_status"] = resp.status_code
                return {"citations": citations, "raw_data": raw_data}

            data = resp.json()
            results = data.get("results", []) or []
            total = data.get("meta", {}).get("results", {}).get("total", len(results))
            raw_data[f"fda_drugs_{intervention}_count"] = total

            for record in results[:3]:
                app_no = record.get("application_number", "")
                sponsor = record.get("sponsor_name", "Unknown sponsor")
                openfda = record.get("openfda", {}) or {}
                brand_names = openfda.get("brand_name", []) or []
                generic_names = openfda.get("generic_name", []) or []
                routes = openfda.get("route", []) or []
                substance = openfda.get("substance_name", []) or []
                products = record.get("products", []) or []
                product_lines = []
                for p in products[:3]:
                    pname = p.get("brand_name") or "Unknown product"
                    dosage_form = p.get("dosage_form", "")
                    pmarket_status = p.get("marketing_status", "")
                    product_lines.append(
                        f"{pname} ({dosage_form}, {pmarket_status})"
                    )

                # Find any APPROVED submission status
                submissions = record.get("submissions", []) or []
                approval_dates = []
                approved = False
                for s in submissions:
                    if s.get("submission_status") == "AP":
                        approved = True
                        d = s.get("submission_status_date", "")
                        if d and len(d) == 8:
                            approval_dates.append(f"{d[:4]}-{d[4:6]}-{d[6:8]}")

                snippet_parts = [
                    f"Drug: {brand_names[0] if brand_names else (generic_names[0] if generic_names else clean)}",
                    f"Sponsor: {sponsor}",
                    f"Application: {app_no}",
                    f"FDA approved: {'YES' if approved else 'No (or not yet)'}",
                ]
                if approval_dates:
                    snippet_parts.append(f"Approval dates: {', '.join(approval_dates[:3])}")
                if generic_names:
                    snippet_parts.append(f"Generic name(s): {', '.join(generic_names[:2])}")
                if substance:
                    snippet_parts.append(f"Active substance: {', '.join(substance[:2])}")
                if routes:
                    snippet_parts.append(f"Route: {', '.join(routes[:2])}")
                if product_lines:
                    snippet_parts.append(f"Products: {'; '.join(product_lines)}")

                fda_url = (
                    f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_no}"
                    if app_no else "https://www.accessdata.fda.gov/scripts/cder/daf/"
                )
                citations.append(SourceCitation(
                    source_name="fda_drugs",
                    source_url=fda_url,
                    identifier=f"FDA:{app_no}" if app_no else f"FDA:{clean}",
                    title=f"{brand_names[0] if brand_names else clean} - Drugs@FDA",
                    snippet="\n".join(snippet_parts),
                    quality_score=self.compute_quality_score("fda_drugs"),
                    retrieved_at=datetime.utcnow().isoformat(),
                ))
            # Save approved-yes structurally for downstream agents to consume
            is_approved = any(
                s.get("submission_status") == "AP"
                for r in results for s in (r.get("submissions") or [])
            )
            raw_data[f"fda_drugs_{intervention}_approved"] = is_approved

            # v42.7.12: when the drug is approved, fetch the label
            # indications_and_usage text. This is the canonical "what is
            # this drug approved to treat" string and lets downstream
            # disambiguate cross-indication trials (Job #92's over-call
            # pattern). One extra API call per approved drug.
            if is_approved:
                indication = await self._fetch_label_indication(client, clean)
                if indication:
                    raw_data[f"fda_drugs_{intervention}_indication"] = indication

        except Exception as e:
            logger.warning(f"openFDA Drugs@FDA failed for {intervention!r}: {e}")
            raw_data[f"fda_drugs_{intervention}_error"] = str(e)

        return {"citations": citations, "raw_data": raw_data}

    async def _fetch_label_indication(self, client: httpx.AsyncClient, drug_name: str) -> str:
        """Fetch the FDA label's indications_and_usage text for a drug.

        Returns the first ~500 characters of the indication text, or empty
        string if no label record found. Older drugs and non-prescription
        products may not have label records — in that case we return empty
        and the dossier just says "FDA approved" without indication detail.
        """
        try:
            # Field-scoped query first (most precise, avoids matching drugs
            # whose labels merely mention this drug name as comparator).
            params = {
                "search": (
                    f'openfda.generic_name:"{drug_name}" OR '
                    f'openfda.brand_name:"{drug_name}" OR '
                    f'openfda.substance_name:"{drug_name}"'
                ),
                "limit": 1,
            }
            resp = await resilient_get(FDA_LABEL_URL, client=client, params=params)
            if resp.status_code == 404:
                return ""
            if resp.status_code != 200:
                return ""
            data = resp.json()
            results = data.get("results", []) or []
            if not results:
                return ""
            iu = results[0].get("indications_and_usage", []) or []
            if not iu:
                return ""
            # First entry, capped at 500 chars to keep dossier compact
            text = (iu[0] or "").strip()
            return text[:500]
        except Exception as e:
            logger.debug(f"label fetch failed for {drug_name!r}: {e}")
            return ""
