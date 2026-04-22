"""
bioRxiv / medRxiv Preprint Research Agent (v42 Phase 6).

Queries Europe PMC's preprint corpus (source filter ``SRC:PPR``) for
bioRxiv + medRxiv preprints related to a clinical trial. Targets the
Phase 5 Cat 1 evidence gaps where R1 relied on a preprint that a
peer-review-only search (PubMed, PMC) missed.

Free, no API key, no rate limit beyond normal courtesy. Europe PMC
indexes ~700k+ life-science preprints from bioRxiv, medRxiv, and a
dozen smaller servers — searching through Europe PMC (rather than
bioRxiv's own API) gives us a unified interface and broader reach.

Strategy (mirrors the LiteratureAgent two-pass pattern):
  1. NCT ID search  — "SRC:PPR AND nct_id"
  2. Metadata fallback — title keywords + intervention names, for trials
     where the preprint predates or doesn't reference the NCT id
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.biorxiv")

EUROPE_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

# Europe PMC source codes for bioRxiv and medRxiv. SRC:PPR is the general
# preprint filter; we also accept specific ids in case preprints are
# republished with new source codes.
_PREPRINT_SOURCE_FILTER = "SRC:PPR"

# v42.6.5: Increased from 10 to 25. Europe PMC ranking surfaces relevant
# preprints within the top 25; limiting to 10 was missing trial-specific
# papers when several generic matches ranked ahead.
_MAX_RESULTS_PER_QUERY = 25

# Generic terms excluded from fallback drug-name queries AND the prefilter
# match set. These appear in many unrelated medical papers, so including
# them as search anchors or match keywords produces garbage citations.
_GENERIC_INTERVENTION_TERMS = {
    "placebo", "control", "standard of care", "standard care",
    "vehicle", "saline", "water", "sugar", "sham",
    "best supportive care", "no treatment",
    "matching placebo", "comparator", "active comparator",
    "normal saline", "usual care",
}


class BioRxivClient(BaseResearchAgent):
    """Preprint-specific literature agent (bioRxiv / medRxiv via Europe PMC)."""

    agent_name = "biorxiv"
    sources = ["biorxiv_medrxiv"]

    async def research(
        self,
        nct_id: str,
        metadata: Optional[dict] = None,
    ) -> ResearchResult:
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        async with httpx.AsyncClient(timeout=20) as client:
            nct_hits = await self._search_nct(nct_id, client)
            citations.extend(nct_hits)
            raw_data["biorxiv_nct_hits"] = len(nct_hits)

            if not nct_hits and metadata:
                title = (metadata.get("title") or "").strip()
                interventions = self._extract_interventions(metadata)
                if title or interventions:
                    fallback = await self._search_fallback(
                        title, interventions, client
                    )
                    citations.extend(fallback)
                    raw_data["biorxiv_fallback_hits"] = len(fallback)

        # v42.6.5 Eff #5: drug-name prefilter. If the config flag is on AND
        # we have drug names to check, drop citations that contain zero
        # intervention-name occurrences. Avoids burning Tier 1b LLM cycles
        # on clearly off-topic preprints that slipped through the keyword
        # search. NCT-hits always kept (they explicitly mention the trial).
        if metadata is not None:
            prefiltered = await self._maybe_prefilter(
                citations, nct_hits, metadata,
            )
            if prefiltered is not None:
                raw_data["biorxiv_prefilter_dropped"] = len(citations) - len(prefiltered)
                citations = prefiltered

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _maybe_prefilter(
        self,
        citations: list[SourceCitation],
        nct_hits: list[SourceCitation],
        metadata: dict,
    ) -> Optional[list[SourceCitation]]:
        """Return a pruned citation list or None if prefilter is off.

        Reads ``orchestrator.biorxiv_drug_name_prefilter`` at call time so
        tests/scripts that construct this agent directly can still disable
        the filter. Keeps NCT-hit citations (they already prove the
        preprint explicitly mentions this trial).
        """
        try:
            from app.services.config_service import config_service
            cfg = config_service.get()
            if not getattr(cfg.orchestrator, "biorxiv_drug_name_prefilter", True):
                return None
        except Exception:
            return None

        # Exclude generic terms (see module-level _GENERIC_INTERVENTION_TERMS
        # comment). Without this, a citation about soybeans passes the filter
        # because both "placebo" and the soybean paper happen to share that
        # word.
        raw = [
            n.lower().strip() for n in self._extract_interventions(metadata)
            if isinstance(n, str) and len(n) >= 3
        ]
        interventions = [n for n in raw if n not in _GENERIC_INTERVENTION_TERMS]
        if not interventions:
            return None

        nct_hit_ids = {c.identifier for c in nct_hits}
        out: list[SourceCitation] = []
        for c in citations:
            if c.identifier in nct_hit_ids:
                out.append(c)
                continue
            blob = f"{c.title or ''} {c.snippet or ''}".lower()
            if any(drug in blob for drug in interventions):
                out.append(c)
        return out

    # ---- queries --------------------------------------------------------- #

    async def _search_nct(
        self,
        nct_id: str,
        client: httpx.AsyncClient,
    ) -> list[SourceCitation]:
        query = f'{_PREPRINT_SOURCE_FILTER} AND "{nct_id}"'
        return await self._query(query, client, tag=f"nct:{nct_id}")

    async def _search_fallback(
        self,
        title: str,
        interventions: list[str],
        client: httpx.AsyncClient,
    ) -> list[SourceCitation]:
        """Metadata-based fallback — issues one query per non-generic
        intervention name plus one title query, dedupes by DOI/identifier.

        v42.6.5 rewrite: previous version used only the shortest intervention
        name, which reliably picked 'Placebo' and returned garbage. Now:
        - Query each non-generic intervention separately (parallel)
        - Query the trial title as a fallback if no intervention hits
        - Dedupe results by identifier so overlapping queries don't inflate
        - Rank by ordering (most relevant surfaces first when deduped)

        Hard cap: up to 6 per-intervention queries per trial to avoid
        hammering Europe PMC on multi-arm trials with many interventions.
        """
        # Filter generics and dedupe (preserve order — first occurrence wins)
        seen = set()
        targets: list[str] = []
        for name in interventions or []:
            n = (name or "").strip()
            if len(n) < 3 or n.lower() in _GENERIC_INTERVENTION_TERMS:
                continue
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            targets.append(n)
        # Prefer longer (more specific) intervention names first — these
        # tend to be brand names or full drug descriptors.
        targets.sort(key=len, reverse=True)
        targets = targets[:6]

        tasks = []
        for t in targets:
            query = f'{_PREPRINT_SOURCE_FILTER} AND "{t}"'
            tasks.append(self._query(query, client, tag=f"fb:{t[:20]}"))

        if not tasks and title:
            # Last-resort: title keywords (truncated).
            query = f'{_PREPRINT_SOURCE_FILTER} AND "{title[:60]}"'
            tasks.append(self._query(query, client, tag=f"fb-title:{title[:20]}"))

        if not tasks:
            return []

        import asyncio
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Dedupe across queries by identifier; keep first occurrence.
        seen_ids: set[str] = set()
        merged: list[SourceCitation] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            for c in r:
                if c.identifier and c.identifier in seen_ids:
                    continue
                seen_ids.add(c.identifier)
                merged.append(c)
        return merged

    async def _query(
        self,
        query: str,
        client: httpx.AsyncClient,
        tag: str,
    ) -> list[SourceCitation]:
        params = {
            "query": query,
            "format": "json",
            "pageSize": str(_MAX_RESULTS_PER_QUERY),
            "resultType": "lite",
        }
        try:
            resp = await resilient_get(
                EUROPE_PMC_URL, client=client, params=params, timeout=15,
            )
        except Exception as e:
            logger.warning("biorxiv %s fetch failed: %s", tag, e)
            return []
        if resp.status_code != 200:
            return []
        try:
            payload = resp.json()
        except Exception:
            return []

        hits = (payload.get("resultList", {}) or {}).get("result", []) or []
        citations: list[SourceCitation] = []
        for hit in hits[:_MAX_RESULTS_PER_QUERY]:
            ident = self._pick_identifier(hit)
            if not ident:
                continue
            title = (hit.get("title") or "").strip()
            abstract = (hit.get("abstractText") or "").strip()
            year = (hit.get("pubYear") or "")
            journal = (hit.get("source") or "") + (
                f" ({hit.get('bookOrReportDetails') or ''})" if hit.get("bookOrReportDetails") else ""
            )
            snippet = abstract[:600] if abstract else (journal or year)
            citations.append(SourceCitation(
                source_name="biorxiv_medrxiv",
                source_url=self._url_for(hit),
                identifier=ident,
                title=title or ident,
                snippet=snippet,
                quality_score=self.compute_quality_score(
                    "biorxiv_medrxiv",
                    has_content=bool(abstract or title),
                ),
                retrieved_at=datetime.utcnow().isoformat(),
            ))
        return citations

    @staticmethod
    def _pick_identifier(hit: dict) -> str:
        """Prefer DOI (preprint servers use DOI as canonical ID); fall back to
        Europe PMC id if DOI missing."""
        doi = (hit.get("doi") or "").strip()
        if doi:
            return f"DOI:{doi}"
        pmcid = (hit.get("pmcid") or "").strip()
        if pmcid:
            return pmcid
        pmid = (hit.get("pmid") or "").strip()
        if pmid:
            return f"PMID:{pmid}"
        eid = (hit.get("id") or "").strip()
        return f"EuropePMC:{eid}" if eid else ""

    @staticmethod
    def _url_for(hit: dict) -> str:
        doi = (hit.get("doi") or "").strip()
        if doi:
            return f"https://doi.org/{doi}"
        eid = (hit.get("id") or "").strip()
        if eid:
            return f"https://europepmc.org/abstract/ppr/{eid}"
        return "https://europepmc.org/"

    @staticmethod
    def _extract_interventions(metadata: dict) -> list[str]:
        """Extract drug names from whatever metadata shape the orchestrator
        hands us.

        The orchestrator passes interventions as a list of dicts shaped like
        ``[{"name": "drug_a", "resolved": ["drug_a_synonym"]}, ...]`` (see
        ``_run_research`` and ``_resolve_drug_names``). Earlier probe code
        used plain strings. Accept both. Also flatten ``resolved`` aliases
        so synonym hits count.
        """
        out: list[str] = []
        interv = metadata.get("interventions")
        if isinstance(interv, list):
            for entry in interv:
                if isinstance(entry, dict):
                    name = (entry.get("name") or "").strip()
                    if name:
                        out.append(name)
                    for resolved in (entry.get("resolved") or []):
                        r = (str(resolved) or "").strip()
                        if r:
                            out.append(r)
                elif isinstance(entry, str):
                    s = entry.strip()
                    if s:
                        out.append(s)
            if out:
                return out
        # Fallback: walk the raw protocol_section if present.
        proto = metadata.get("protocol_section") or metadata.get("protocolSection") or {}
        arms = proto.get("armsInterventionsModule", {}) if isinstance(proto, dict) else {}
        for entry in arms.get("interventions", []) or []:
            name = (entry.get("name") or "").strip() if isinstance(entry, dict) else ""
            if name:
                out.append(name)
        return out
