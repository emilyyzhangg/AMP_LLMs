"""
DBAASP Research Agent.

Queries the Database of Antimicrobial Activity and Structure of Peptides
(https://dbaasp.org) for peptide activity data, MIC values, target organisms,
and structural information.
"""

from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

DBAASP_API_BASE = "https://dbaasp.org/api/v2"
DBAASP_SEARCH_URL = f"{DBAASP_API_BASE}/peptides"


class DBAASPClient(BaseResearchAgent):
    """Queries DBAASP for antimicrobial peptide activity and structure data."""

    agent_name = "dbaasp"
    sources = ["dbaasp"]

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

        async with httpx.AsyncClient(timeout=15) as client:
            for intervention in interventions[:3]:
                try:
                    resp = await resilient_get(
                        DBAASP_SEARCH_URL,
                        client=client,
                        params={
                            "name": intervention,
                            "format": "json",
                        },
                        headers={"Accept": "application/json"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # DBAASP may return a list of peptide entries
                        peptides = data if isinstance(data, list) else data.get("peptides", data.get("results", []))
                        if not isinstance(peptides, list):
                            peptides = [peptides] if peptides else []

                        raw_data[f"dbaasp_{intervention}"] = peptides[:5]

                        for entry in peptides[:3]:
                            if not isinstance(entry, dict):
                                continue

                            dbaasp_id = str(entry.get("id", entry.get("dbaaspId", "")))
                            peptide_name = entry.get("name", entry.get("peptideName", intervention))
                            sequence = entry.get("sequence", "")
                            activities = entry.get("activities", entry.get("activity", []))
                            target_organisms = entry.get("targetOrganisms", entry.get("targets", []))
                            structure = entry.get("structure", entry.get("structureInfo", ""))

                            # Build MIC summary from activity data
                            mic_parts = []
                            if isinstance(activities, list):
                                for act in activities[:5]:
                                    if isinstance(act, dict):
                                        organism = act.get("targetOrganism", act.get("organism", ""))
                                        mic = act.get("mic", act.get("value", ""))
                                        unit = act.get("unit", "ug/mL")
                                        if organism and mic:
                                            mic_parts.append(f"{organism}: MIC {mic} {unit}")
                            mic_summary = "; ".join(mic_parts) if mic_parts else "No MIC data available"

                            # Build target organisms summary
                            target_summary = ""
                            if isinstance(target_organisms, list):
                                target_names = []
                                for t in target_organisms[:5]:
                                    if isinstance(t, dict):
                                        target_names.append(t.get("name", t.get("organism", str(t))))
                                    elif isinstance(t, str):
                                        target_names.append(t)
                                target_summary = ", ".join(target_names)

                            snippet_parts = [f"Peptide: {peptide_name}"]
                            if sequence:
                                snippet_parts.append(f"Sequence: {sequence[:80]}")
                            snippet_parts.append(f"MIC data: {mic_summary}")
                            if target_summary:
                                snippet_parts.append(f"Target organisms: {target_summary}")
                            if structure:
                                struct_str = structure if isinstance(structure, str) else str(structure)
                                snippet_parts.append(f"Structure: {struct_str[:100]}")

                            citations.append(SourceCitation(
                                source_name="dbaasp",
                                source_url=f"https://dbaasp.org/peptide/{dbaasp_id}" if dbaasp_id else "https://dbaasp.org/",
                                identifier=f"DBAASP:{dbaasp_id}" if dbaasp_id else peptide_name,
                                title=f"{peptide_name} - DBAASP",
                                snippet="\n".join(snippet_parts),
                                quality_score=self.compute_quality_score("dbaasp"),
                                retrieved_at=datetime.utcnow().isoformat(),
                            ))
                    else:
                        raw_data[f"dbaasp_{intervention}_status"] = resp.status_code
                except Exception as e:
                    raw_data[f"dbaasp_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )
