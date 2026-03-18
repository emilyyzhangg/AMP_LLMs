"""
RCSB Protein Data Bank Research Agent.

Queries the RCSB PDB (https://www.rcsb.org) for 3D structure data,
including resolution, experimental method, and citation metadata
for peptides and molecules from clinical trial interventions.
"""

import json
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_ENTRY_URL = "https://data.rcsb.org/rest/v1/core/entry"


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


class RCSBPDBClient(BaseResearchAgent):
    """Queries RCSB PDB for 3D structure metadata and citations."""

    agent_name = "rcsb_pdb"
    sources = ["rcsb_pdb"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Extract intervention names to search for structures
        interventions = _extract_intervention_names(metadata)

        if not interventions:
            return ResearchResult(
                agent_name=self.agent_name,
                nct_id=nct_id,
                citations=[],
                raw_data={"note": "No interventions to search"},
            )

        async with httpx.AsyncClient(timeout=15) as client:
            for intervention in interventions[:3]:
                try:
                    # Search RCSB using the full-text search API
                    # Use text search with struct.title and entity names —
                    # full_text search returns too many irrelevant hits for
                    # drug names. The struct_keywords group targets title,
                    # entity descriptions, and compound names.
                    search_query = {
                        "query": {
                            "type": "group",
                            "logical_operator": "or",
                            "nodes": [
                                {
                                    "type": "terminal",
                                    "service": "full_text",
                                    "parameters": {
                                        "value": f'"{intervention}"',
                                    },
                                },
                                {
                                    "type": "terminal",
                                    "service": "text",
                                    "parameters": {
                                        "attribute": "struct.title",
                                        "operator": "contains_words",
                                        "value": intervention,
                                    },
                                },
                                {
                                    "type": "terminal",
                                    "service": "text",
                                    "parameters": {
                                        "attribute": "rcsb_entity_source_organism.rcsb_gene_name.value",
                                        "operator": "exact_match",
                                        "value": intervention,
                                    },
                                },
                            ],
                        },
                        "return_type": "entry",
                        "request_options": {
                            "results_content_type": ["experimental"],
                            "pager": {
                                "start": 0,
                                "rows": 5,
                            },
                            "scoring_strategy": "combined",
                            "sort": [
                                {
                                    "sort_by": "score",
                                    "direction": "desc",
                                }
                            ],
                        },
                    }

                    resp = await client.post(
                        RCSB_SEARCH_URL,
                        json=search_query,
                        headers={"Content-Type": "application/json"},
                        timeout=15,
                    )

                    if resp.status_code == 204:
                        # No results
                        raw_data[f"rcsb_{intervention}"] = {"count": 0}
                        continue

                    if resp.status_code != 200:
                        raw_data[f"rcsb_{intervention}_status"] = resp.status_code
                        continue

                    search_data = resp.json()
                    result_set = search_data.get("result_set", [])
                    total_count = search_data.get("total_count", 0)
                    raw_data[f"rcsb_{intervention}_count"] = total_count

                    # Fetch detailed entry data for each PDB ID
                    for result in result_set[:3]:
                        pdb_id = result.get("identifier", "")
                        if not pdb_id:
                            continue

                        entry_citation = await self._fetch_entry_details(
                            client, pdb_id, intervention, raw_data
                        )
                        if entry_citation:
                            citations.append(entry_citation)

                except Exception as e:
                    raw_data[f"rcsb_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _fetch_entry_details(
        self,
        client: httpx.AsyncClient,
        pdb_id: str,
        intervention: str,
        raw_data: dict,
    ) -> Optional[SourceCitation]:
        """Fetch detailed entry metadata from RCSB PDB."""
        try:
            resp = await resilient_get(
                f"{RCSB_ENTRY_URL}/{pdb_id}",
                client=client,
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                raw_data[f"rcsb_entry_{pdb_id}_status"] = resp.status_code
                return None

            entry = resp.json()

            # Extract structure metadata
            struct = entry.get("struct", {}) or {}
            title = struct.get("title", "")

            # Experimental method and resolution
            exptl = entry.get("exptl", [])
            method = ""
            if isinstance(exptl, list) and exptl:
                method = exptl[0].get("method", "")

            # Resolution from refine or reflns
            resolution = ""
            refine = entry.get("refine", [])
            if isinstance(refine, list) and refine:
                resolution = refine[0].get("ls_d_res_high", "")
            if not resolution:
                reflns = entry.get("reflns", [])
                if isinstance(reflns, list) and reflns:
                    resolution = reflns[0].get("d_resolution_high", "")

            # Citation info
            rcsb_citations = entry.get("citation", [])
            primary_citation = ""
            citation_doi = ""
            if isinstance(rcsb_citations, list) and rcsb_citations:
                primary = rcsb_citations[0]
                authors = primary.get("rcsb_authors", [])
                journal = primary.get("journal_abbrev", "")
                year = primary.get("year", "")
                citation_title = primary.get("title", "")
                citation_doi = primary.get("pdbx_database_id_DOI", "")

                cite_parts = []
                if citation_title:
                    cite_parts.append(citation_title)
                if authors:
                    auth_str = ", ".join(authors[:3])
                    if len(authors) > 3:
                        auth_str += " et al."
                    cite_parts.append(auth_str)
                if journal or year:
                    cite_parts.append(f"{journal} ({year})" if year else journal)
                primary_citation = ". ".join(cite_parts)

            # Entry audit dates
            audit = entry.get("rcsb_accession_info", {}) or {}
            deposit_date = audit.get("deposit_date", "")
            release_date = audit.get("initial_release_date", "")

            # Build snippet
            snippet_parts = [f"PDB ID: {pdb_id}"]
            if title:
                snippet_parts.append(f"Title: {title}")
            if method:
                snippet_parts.append(f"Method: {method}")
            if resolution:
                snippet_parts.append(f"Resolution: {resolution} A")
            if deposit_date:
                snippet_parts.append(f"Deposited: {deposit_date[:10]}")
            if release_date:
                snippet_parts.append(f"Released: {release_date[:10]}")
            if primary_citation:
                snippet_parts.append(f"Citation: {primary_citation}")

            has_content = bool(title or method or resolution)
            return SourceCitation(
                source_name="rcsb_pdb",
                source_url=f"https://www.rcsb.org/structure/{pdb_id}",
                identifier=f"PDB:{pdb_id}",
                title=title or f"PDB Structure {pdb_id}",
                snippet="\n".join(snippet_parts),
                quality_score=self.compute_quality_score("rcsb_pdb", has_content=has_content),
                retrieved_at=datetime.utcnow().isoformat(),
            )

        except Exception as e:
            raw_data[f"rcsb_entry_{pdb_id}_error"] = str(e)
            return None
