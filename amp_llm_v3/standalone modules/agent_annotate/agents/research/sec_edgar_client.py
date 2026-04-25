"""
SEC EDGAR Research Agent (v42.7.0, 2026-04-25).

Searches the SEC EDGAR full-text index for filings (10-K, 10-Q, 8-K)
that reference a drug name or NCT ID. Pharma sponsors are required by
US securities law to disclose material trial events — failures, drug
discontinuations, write-offs of program assets — in their periodic
filings. SEC EDGAR is the public record of those disclosures.

Why this matters for the pipeline:
  Job #83 surfaced trials where GT annotators called outcome=Failed
  but CT.gov said COMPLETED with no whyStopped — humans knew the
  trial failed because they read the press release. SEC EDGAR is
  that press release in primary source form.

API:
  Full-text search: https://efts.sec.gov/LATEST/search-index?q=<term>
  Documentation:    https://www.sec.gov/edgar/search/

User-Agent header is REQUIRED by SEC's fair-access policy.

Free, no key. Standard rate limit ~10 req/sec — we make at most 1 req/trial
during the per-intervention loop, so no rate-limit risk.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import httpx

from agents.base import BaseResearchAgent
from agents.research.drug_cache import drug_cache
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.sec_edgar")

SEC_EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

# SEC requires a meaningful User-Agent identifying the requester.
_SEC_USER_AGENT = "Amphoraxe Annotation Pipeline amphoraxe@amphoraxe.ca"

# Forms most likely to disclose trial outcomes:
#   10-K  Annual report (Risk Factors + MD&A often discuss trial pipeline)
#   10-Q  Quarterly report (Same as above, more recent)
#   8-K   Material events (most likely to announce a specific trial result)
_FORMS = "10-K,10-Q,8-K"


def _extract_intervention_names(metadata: Optional[dict]) -> list[str]:
    """Extract DRUG/BIOLOGICAL intervention names. Skip placebo/saline."""
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


class SECEdgarClient(BaseResearchAgent):
    """Search SEC EDGAR full-text index for sponsor disclosures referencing
    a drug name or NCT ID."""

    agent_name = "sec_edgar"
    sources = ["sec_edgar"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations: list = []
        raw_data: dict = {}
        interventions = _extract_intervention_names(metadata)

        # Always also search for the NCT ID directly — sometimes sponsor
        # 8-K filings reference the registry NCT explicitly.
        search_terms: list[str] = [nct_id]
        search_terms.extend(interventions[:3])

        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": _SEC_USER_AGENT, "Accept": "application/json"},
        ) as client:
            for term in search_terms:
                async def compute(t=term):
                    return await self._fetch_term(client, t)

                if drug_cache.is_enabled():
                    per_term = await drug_cache.get_or_compute(
                        self.agent_name, term, compute,
                    )
                else:
                    per_term = await compute()

                citations.extend(per_term["citations"])
                raw_data.update(per_term["raw_data"])

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _fetch_term(self, client: httpx.AsyncClient, term: str) -> dict:
        """Search SEC EDGAR for one drug/NCT term. Pure function of term."""
        citations: list = []
        raw_data: dict = {}

        # Date range: last 5 years. Older filings are unlikely to be relevant
        # for currently-active drugs; restricting to recent improves signal.
        end_dt = datetime.utcnow().date()
        start_dt = end_dt - timedelta(days=365 * 5)
        params = {
            "q": f'"{term}"',
            "forms": _FORMS,
            "dateRange": "custom",
            "startdt": start_dt.isoformat(),
            "enddt": end_dt.isoformat(),
        }

        try:
            resp = await resilient_get(
                SEC_EDGAR_SEARCH_URL,
                client=client,
                params=params,
            )
            if resp.status_code != 200:
                raw_data[f"sec_edgar_{term}_status"] = resp.status_code
                return {"citations": citations, "raw_data": raw_data}

            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            total = data.get("hits", {}).get("total", {}).get("value", 0)
            raw_data[f"sec_edgar_{term}_total"] = total

            # Deduplicate by accession number (one filing can match in multiple
            # docs); keep first hit per filing.
            seen_adsh: set[str] = set()
            kept: list[dict] = []
            for h in hits[:20]:
                src = h.get("_source", {}) or {}
                adsh = src.get("adsh", "")
                if adsh in seen_adsh:
                    continue
                seen_adsh.add(adsh)
                kept.append(h)
                if len(kept) >= 5:
                    break

            for h in kept:
                src = h.get("_source", {}) or {}
                adsh = src.get("adsh", "")
                form = src.get("form", "")
                file_date = src.get("file_date", "")
                names = src.get("display_names", []) or []
                sponsor = names[0] if names else "Unknown sponsor"
                # Build the canonical filing URL from accession + filename.
                # h["_id"] is "<adsh>:<filename>"; we want the filing index page.
                filing_id = h.get("_id", "")
                # Strip dashes from adsh for archives URL: 0001387131-23-006702 → 0001387131-23-006702
                # The URL pattern is /Archives/edgar/data/<cik>/<adsh-no-dashes>/<adsh>-index.htm
                ciks = src.get("ciks") or [""]
                cik_clean = ciks[0].lstrip("0") if ciks else ""
                adsh_clean = adsh.replace("-", "")
                if cik_clean and adsh_clean:
                    filing_url = (
                        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                        f"&CIK={ciks[0]}&type={form}"
                    )
                    # Direct filing URL (more useful):
                    direct_url = (
                        f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/"
                        f"{adsh_clean}/{adsh}-index.htm"
                    )
                else:
                    filing_url = "https://www.sec.gov/edgar/search/"
                    direct_url = filing_url

                snippet_parts = [
                    f"Filing: {form}",
                    f"Sponsor: {sponsor}",
                    f"Date: {file_date}",
                    f"Search term: '{term}'",
                ]
                if total > 1:
                    snippet_parts.append(f"({total} total hits for '{term}' in 10-K/10-Q/8-K)")

                citations.append(SourceCitation(
                    source_name="sec_edgar",
                    source_url=direct_url,
                    identifier=f"SEC:{adsh}",
                    title=f"{sponsor} {form} ({file_date}) — references '{term}'",
                    snippet="\n".join(snippet_parts),
                    quality_score=self.compute_quality_score("sec_edgar"),
                    retrieved_at=datetime.utcnow().isoformat(),
                ))

        except Exception as e:
            logger.warning(f"SEC EDGAR search failed for {term!r}: {e}")
            raw_data[f"sec_edgar_{term}_error"] = str(e)

        return {"citations": citations, "raw_data": raw_data}
