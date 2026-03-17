"""
IntAct Molecular Interactions Research Agent.

Queries the EMBL-EBI IntAct database REST API
(https://www.ebi.ac.uk/intact/ws/) for protein-protein and
protein-molecule interaction data.

Free, open API, no authentication required. Returns interactor
information including interaction partners, interaction type,
species, and detection methods.
"""

import logging
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.intact")

INTACT_INTERACTOR_URL = "https://www.ebi.ac.uk/intact/ws/interactor/findInteractor"


class IntActClient(BaseResearchAgent):
    """Queries IntAct for molecular interaction data."""

    agent_name = "intact"
    sources = ["intact"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Extract intervention names to search for interactors
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

        async with httpx.AsyncClient(timeout=15) as client:
            for intervention in interventions[:3]:
                try:
                    # IntAct interactor search: /findInteractor/{query}
                    search_url = f"{INTACT_INTERACTOR_URL}/{intervention}"
                    resp = await resilient_get(
                        search_url,
                        client=client,
                        params={"page": 0, "pageSize": 10},
                        headers={"Accept": "application/json"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        interactors = data.get("content", [])
                        total = data.get("totalElements", 0)

                        raw_data[f"intact_{intervention}"] = {
                            "total_elements": total,
                            "interactors": interactors[:5],
                        }

                        for entry in interactors[:5]:
                            if not isinstance(entry, dict):
                                continue

                            ac = entry.get("interactorAc", "")
                            name = entry.get("interactorName", "")
                            description = entry.get("interactorDescription", "")
                            preferred_id = entry.get("interactorPreferredIdentifier", "")
                            species = entry.get("interactorSpecies", "")
                            int_type = entry.get("interactorType", "")
                            interaction_count = entry.get("interactionCount", 0)

                            snippet_parts = []
                            if name:
                                snippet_parts.append(f"Interactor: {name}")
                            if description:
                                snippet_parts.append(f"Description: {description}")
                            if preferred_id:
                                snippet_parts.append(f"UniProt: {preferred_id}")
                            if species:
                                snippet_parts.append(f"Species: {species}")
                            if int_type:
                                snippet_parts.append(f"Type: {int_type}")
                            if interaction_count:
                                snippet_parts.append(f"Interactions: {interaction_count}")

                            source_url = (
                                f"https://www.ebi.ac.uk/intact/details/interactor/{ac}"
                                if ac
                                else "https://www.ebi.ac.uk/intact/"
                            )

                            citations.append(SourceCitation(
                                source_name="intact",
                                source_url=source_url,
                                identifier=f"IntAct:{ac}" if ac else preferred_id or name,
                                title=f"{name or description or intervention} - IntAct",
                                snippet="\n".join(snippet_parts) if snippet_parts else f"IntAct interactor for: {intervention}",
                                quality_score=self.compute_quality_score("intact"),
                                retrieved_at=datetime.utcnow().isoformat(),
                            ))

                    elif resp.status_code == 404:
                        raw_data[f"intact_{intervention}"] = {"found": False}
                    else:
                        raw_data[f"intact_{intervention}_status"] = resp.status_code
                except Exception as e:
                    logger.warning("IntAct search failed for %s: %s", intervention, e)
                    raw_data[f"intact_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )
