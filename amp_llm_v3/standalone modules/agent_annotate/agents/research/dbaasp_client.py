"""
DBAASP Research Agent.

Queries the Database of Antimicrobial Activity and Structure of Peptides
(https://dbaasp.org) for peptide activity data, MIC values, target organisms,
and structural information.

The public search endpoint is ``GET /peptides`` with query parameters
``name.value`` (substring) and ``name.comparator=like``.  The older
``/api/v2/peptides`` path returns empty responses and is not usable.

v14 changes:
  - Add name-match filtering to prevent floods of unrelated hits
  - Store sequences structurally in raw_data (not only in snippets)
  - Remove noise words (Synthesis, Complexity) from snippets

v17 changes:
  - Fix abbreviation collision in _name_matches: short names (<=4 chars) like
    "BNP" and "ANP" were substring-matching unrelated peptides (BnPRP1, HANP).
    Now uses word-boundary matching for short intervention names.
"""

import logging
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.drug_cache import drug_cache
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.dbaasp")

# Correct endpoint discovered from DBAASP frontend JS (search-base.js).
# The /api/v2/peptides path returns content-length: 0 for all queries.
DBAASP_SEARCH_URL = "https://dbaasp.org/peptides"


def _extract_intervention_names(metadata: dict | None) -> list[str]:
    """Extract plain-string intervention names from metadata.

    Handles both list-of-dicts (``[{"name": "Nisin"}]``) and
    list-of-strings (``["Nisin"]``) formats.
    """
    if not metadata:
        return []
    raw = metadata.get("interventions", [])
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("intervention_name") or ""
            if name:
                names.append(str(name))
        elif isinstance(item, str) and item:
            names.append(item)
    return names


def _name_matches(intervention: str, peptide_name: str) -> bool:
    """Check if a DBAASP peptide name is relevant to the intervention.

    v17: For short intervention names (<=4 chars like "BNP", "ANP"), use
    word-boundary matching to prevent abbreviation collisions. "BNP" was
    substring-matching "BnPRP1" (a proline-rich AMP), and "ANP" was matching
    "HANP" (human alpha-neutrophil peptide / defensin). These are completely
    different protein families from the clinical trial drugs.

    For longer names, bidirectional substring matching is safe.
    """
    import re as _re

    iv = intervention.lower().strip()
    pn = peptide_name.lower().strip()
    if not iv or not pn:
        return False

    # Short intervention names (<=4 chars): require word-boundary match
    # to prevent "BNP" matching "BnPRP1" or "ANP" matching "HANP-1"
    if len(iv) <= 4:
        # Exact match or word-boundary match in peptide name
        if iv == pn:
            return True
        return bool(_re.search(r'\b' + _re.escape(iv) + r'\b', pn))

    # Longer names: bidirectional substring is safe
    return iv in pn or pn in iv


class DBAASPClient(BaseResearchAgent):
    """Queries DBAASP for antimicrobial peptide activity and structure data."""

    agent_name = "dbaasp"
    sources = ["dbaasp"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Extract intervention names to search for peptides
        interventions = _extract_intervention_names(metadata)

        if not interventions:
            return ResearchResult(
                agent_name=self.agent_name,
                nct_id=nct_id,
                citations=[],
                raw_data={"note": "No interventions to search"},
            )

        async with httpx.AsyncClient(timeout=20) as client:
            for intervention in interventions[:3]:
                async def compute(intv=intervention):
                    return await self._fetch_intervention(client, intv)

                if drug_cache.is_enabled():
                    per_intervention = await drug_cache.get_or_compute(
                        self.agent_name, intervention, compute,
                    )
                else:
                    per_intervention = await compute()

                citations.extend(per_intervention["citations"])
                raw_data.update(per_intervention["raw_data"])

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _fetch_intervention(
        self, client: httpx.AsyncClient, intervention: str,
    ) -> dict:
        """Fetch DBAASP data for one intervention. Pure function of the drug name.

        Returns {"citations": [...], "raw_data": {...}}. raw_data keys are
        intervention-prefixed for collision-free merge across interventions.
        """
        citations: list = []
        raw_data: dict = {}
        try:
            # Try EXACT match first (comparator=eq), fall back to substring (like)
            # only if exact match returns no results. This prevents "Peptide T"
            # from matching every peptide in the database via substring.
            peptides = []
            total = 0
            for comparator in ("eq", "like"):
                resp = await resilient_get(
                    DBAASP_SEARCH_URL,
                    client=client,
                    params={
                        "name.value": intervention,
                        "name.comparator": comparator,
                        "offset": 0,
                        "limit": 5,
                    },
                    headers={"Accept": "application/json"},
                )
                if resp.status_code != 200:
                    continue

                body = resp.text.strip()
                if not body:
                    continue

                data = resp.json()
                peptides = data.get("data", []) if isinstance(data, dict) else []
                if isinstance(data, list):
                    peptides = data
                if not isinstance(peptides, list):
                    peptides = [peptides] if peptides else []
                total = data.get("totalCount", len(peptides)) if isinstance(data, dict) else len(peptides)

                if peptides:
                    raw_data[f"dbaasp_{intervention}_match"] = comparator
                    break  # Use exact match results if available

            if not peptides:
                raw_data[f"dbaasp_{intervention}"] = {"found": False}
                return {"citations": citations, "raw_data": raw_data}

            # v14: Filter by name relevance — only keep entries whose name
            # matches the intervention. Prevents "ANP" from returning dozens
            # of unrelated antimicrobial peptides.
            filtered = [e for e in peptides if isinstance(e, dict)
                        and _name_matches(intervention, e.get("name", ""))]
            if not filtered:
                # None matched by name — the intervention isn't in DBAASP
                raw_data[f"dbaasp_{intervention}"] = {
                    "found": False,
                    "unfiltered_count": len(peptides),
                    "note": "No name-matched entries",
                }
                return {"citations": citations, "raw_data": raw_data}

            raw_data[f"dbaasp_{intervention}"] = {
                "total": total,
                "entries": filtered[:5],
            }

            # v14: Store sequences structurally for the sequence agent
            raw_data[f"dbaasp_{intervention}_sequences"] = [
                {
                    "name": e.get("name", intervention),
                    "sequence": e.get("sequence", ""),
                    "length": e.get("sequenceLength", ""),
                    "dbaasp_id": str(e.get("dbaaspId", e.get("id", ""))),
                }
                for e in filtered[:3]
                if e.get("sequence")
            ]

            for entry in filtered[:5]:
                if not isinstance(entry, dict):
                    continue

                dbaasp_id = str(entry.get("dbaaspId", entry.get("id", "")))
                peptide_name = entry.get("name", intervention)
                sequence = entry.get("sequence", "")
                seq_length = entry.get("sequenceLength", "")
                pubchem = entry.get("pubchemCid", "")
                pdb = entry.get("pdb", "")

                # v14: Snippet contains only the peptide name, sequence,
                # length, and identifiers. Noise words like Synthesis and
                # Complexity removed (they get false-positive matched as
                # AA sequences by downstream agents).
                snippet_parts = [f"Peptide: {peptide_name}"]
                if sequence:
                    snippet_parts.append(f"Sequence: {sequence[:80]}")
                if seq_length:
                    snippet_parts.append(f"Length: {seq_length} aa")
                if pubchem:
                    snippet_parts.append(f"PubChem CID: {pubchem}")
                if pdb:
                    snippet_parts.append(f"PDB: {pdb}")

                # Build URL — DBAASP uses /peptide-card?id=DBAASPX_NNN
                detail_url = (
                    f"https://dbaasp.org/peptide-card?id={dbaasp_id}"
                    if dbaasp_id
                    else "https://dbaasp.org/"
                )

                citations.append(SourceCitation(
                    source_name="dbaasp",
                    source_url=detail_url,
                    identifier=f"DBAASP:{dbaasp_id}" if dbaasp_id else peptide_name,
                    title=f"{peptide_name} - DBAASP",
                    snippet="\n".join(snippet_parts),
                    quality_score=self.compute_quality_score("dbaasp"),
                    retrieved_at=datetime.utcnow().isoformat(),
                ))
        except Exception as e:
            logger.warning("DBAASP search failed for %s: %s", intervention, e)
            raw_data[f"dbaasp_{intervention}_error"] = str(e)

        return {"citations": citations, "raw_data": raw_data}
