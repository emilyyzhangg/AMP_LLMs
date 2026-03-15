"""
Peptide Identity Research Agent.

Looks up peptide/protein information from UniProt and DRAMP databases.
"""

from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from app.models.research import ResearchResult, SourceCitation

UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
DRAMP_SEARCH_URL = "http://dramp.cpu-bioinfor.org/browse/search.php"


class PeptideIdentityAgent(BaseResearchAgent):
    """Identifies peptide/protein entities from UniProt and DRAMP."""

    agent_name = "peptide_identity"
    sources = ["uniprot", "dramp"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Extract intervention names to search for peptides
        interventions = []
        if metadata:
            interventions = metadata.get("interventions", [])
            if isinstance(interventions, list):
                interventions = [str(i) for i in interventions]

        if not interventions:
            return ResearchResult(
                agent_name=self.agent_name,
                nct_id=nct_id,
                citations=[],
                raw_data={"note": "No interventions to search"},
            )

        # 1. UniProt search
        for intervention in interventions[:3]:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.get(
                        UNIPROT_SEARCH_URL,
                        params={
                            "query": intervention,
                            "format": "json",
                            "size": 3,
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

                            citations.append(SourceCitation(
                                source_name="uniprot",
                                source_url=f"https://www.uniprot.org/uniprotkb/{accession}",
                                identifier=accession,
                                title=protein_name or accession,
                                snippet=f"Organism: {organism}. Protein: {protein_name}. Accession: {accession}",
                                quality_score=self.compute_quality_score("uniprot"),
                                retrieved_at=datetime.utcnow().isoformat(),
                            ))
            except Exception as e:
                raw_data[f"uniprot_{intervention}_error"] = str(e)

        # 2. DRAMP search (antimicrobial peptide database)
        for intervention in interventions[:2]:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        DRAMP_SEARCH_URL,
                        params={"keyword": intervention},
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
