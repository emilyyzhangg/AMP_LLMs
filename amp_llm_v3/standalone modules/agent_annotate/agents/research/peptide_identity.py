"""
Peptide Identity Research Agent.

Looks up peptide/protein information from UniProt and DRAMP databases.
"""

from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
DRAMP_SEARCH_URL = "http://dramp.cpu-bioinfor.org/browse/search.php"


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


class PeptideIdentityAgent(BaseResearchAgent):
    """Identifies peptide/protein entities from UniProt and DRAMP."""

    agent_name = "peptide_identity"
    sources = ["uniprot", "dramp"]

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
            # 1. UniProt search — use protein_name field + human organism filter
            # to avoid returning scorpion/bacterial homologs for human drug queries.
            # Try exact protein name first, then broader query as fallback.
            for intervention in interventions[:3]:
                try:
                    # Structured query: search protein name in human proteome first
                    structured_query = f'(protein_name:"{intervention}") AND (organism_id:9606)'
                    resp = await resilient_get(
                        UNIPROT_SEARCH_URL,
                        client=client,
                        params={
                            "query": structured_query,
                            "format": "json",
                            "fields": "accession,protein_name,organism_name,sequence",
                            "size": 3,
                        },
                        headers={"Accept": "application/json"},
                    )
                    results = []
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])

                    # If no human results, try broader search (any organism)
                    # but still use protein_name field, not free text
                    if not results:
                        broader_query = f'(protein_name:"{intervention}")'
                        resp = await resilient_get(
                            UNIPROT_SEARCH_URL,
                            client=client,
                            params={
                                "query": broader_query,
                                "format": "json",
                                "fields": "accession,protein_name,organism_name,sequence",
                                "size": 3,
                            },
                            headers={"Accept": "application/json"},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            results = data.get("results", [])

                    # Last resort: free text but only if structured searches failed
                    if not results:
                        resp = await resilient_get(
                            UNIPROT_SEARCH_URL,
                            client=client,
                            params={
                                "query": f"{intervention} AND (organism_id:9606)",
                                "format": "json",
                                "fields": "accession,protein_name,organism_name,sequence",
                                "size": 2,
                            },
                            headers={"Accept": "application/json"},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            results = data.get("results", [])

                    raw_data[f"uniprot_{intervention}"] = results[:3]
                    for entry in results[:2]:
                        accession = entry.get("primaryAccession", "")
                        protein_name = ""
                        if entry.get("proteinDescription", {}).get("recommendedName"):
                            protein_name = entry["proteinDescription"]["recommendedName"].get("fullName", {}).get("value", "")
                        organism = entry.get("organism", {}).get("scientificName", "")
                        length = entry.get("sequence", {}).get("length", "")

                        # v12: Include full sequence for sequence annotation agent
                        full_seq = entry.get("sequence", {}).get("value", "")
                        snippet = f"Organism: {organism}. Protein: {protein_name}. Accession: {accession}"
                        if length:
                            snippet += f". Length: {length} aa"
                        if full_seq:
                            snippet += f". Sequence: {full_seq[:200]}"

                        citations.append(SourceCitation(
                            source_name="uniprot",
                            source_url=f"https://www.uniprot.org/uniprotkb/{accession}",
                            identifier=accession,
                            title=protein_name or accession,
                            snippet=snippet,
                            quality_score=self.compute_quality_score("uniprot"),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))
                except Exception as e:
                    raw_data[f"uniprot_{intervention}_error"] = str(e)

            # 2. DRAMP search (antimicrobial peptide database)
            for intervention in interventions[:2]:
                try:
                    resp = await resilient_get(
                        DRAMP_SEARCH_URL,
                        client=client,
                        params={"keyword": intervention},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        # DRAMP returns HTML; we note the search was attempted
                        raw_data[f"dramp_{intervention}"] = {"searched": True, "status": resp.status_code}
                        citations.append(SourceCitation(
                            source_name="dramp",
                            source_url=f"http://dramp.cpu-bioinfor.org/",
                            identifier=intervention,
                            title=f"DRAMP search: {intervention}",
                            snippet=f"DRAMP antimicrobial peptide database search for: {intervention}",
                            quality_score=self.compute_quality_score("dramp", has_content=False),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))
                except Exception as e:
                    raw_data[f"dramp_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )
