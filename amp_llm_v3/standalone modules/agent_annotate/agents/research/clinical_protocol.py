"""
Clinical Protocol Research Agent.

Fetches structured trial data from ClinicalTrials.gov (via NCT lookup service)
and OpenFDA.
"""

import sys
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from app.models.research import ResearchResult, SourceCitation
from app.config import NCT_SERVICE_URL

# Add nct_lookup to path for direct imports if needed
_NCT_LOOKUP_DIR = Path(__file__).resolve().parent.parent.parent.parent / "nct_lookup"
if _NCT_LOOKUP_DIR.exists():
    sys.path.insert(0, str(_NCT_LOOKUP_DIR))


class ClinicalProtocolAgent(BaseResearchAgent):
    """Retrieves clinical protocol data from ClinicalTrials.gov and OpenFDA."""

    agent_name = "clinical_protocol"
    sources = ["clinicaltrials_gov", "openfda"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # 1. ClinicalTrials.gov via NCT lookup service
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{NCT_SERVICE_URL}/api/nct/{nct_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    raw_data["clinicaltrials_gov"] = data
                    citations.append(SourceCitation(
                        source_name="clinicaltrials_gov",
                        source_url=f"https://clinicaltrials.gov/study/{nct_id}",
                        identifier=nct_id,
                        title=data.get("brief_title", data.get("official_title", "")),
                        snippet=self._build_ct_snippet(data),
                        quality_score=self.compute_quality_score("clinicaltrials_gov"),
                        retrieved_at=datetime.utcnow().isoformat(),
                    ))
        except Exception as e:
            raw_data["clinicaltrials_gov_error"] = str(e)

        # 2. OpenFDA (drug/device lookups)
        try:
            interventions = metadata.get("interventions", []) if metadata else []
            for intervention in interventions[:3]:  # Limit to 3 lookups
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        "https://api.fda.gov/drug/label.json",
                        params={"search": f'openfda.generic_name:"{intervention}"', "limit": 1},
                    )
                    if resp.status_code == 200:
                        fda_data = resp.json()
                        results = fda_data.get("results", [])
                        if results:
                            raw_data[f"openfda_{intervention}"] = results[0]
                            citations.append(SourceCitation(
                                source_name="openfda",
                                source_url="https://api.fda.gov",
                                identifier=intervention,
                                title=f"FDA Label: {intervention}",
                                snippet=results[0].get("description", [""])[0][:500] if results[0].get("description") else "",
                                quality_score=self.compute_quality_score("openfda"),
                                retrieved_at=datetime.utcnow().isoformat(),
                            ))
        except Exception as e:
            raw_data["openfda_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    def _build_ct_snippet(self, data: dict) -> str:
        """Build a concise snippet from ClinicalTrials.gov data."""
        parts = []
        if data.get("brief_title"):
            parts.append(f"Title: {data['brief_title']}")
        if data.get("overall_status"):
            parts.append(f"Status: {data['overall_status']}")
        if data.get("phase"):
            parts.append(f"Phase: {data['phase']}")
        if data.get("conditions"):
            conds = data["conditions"] if isinstance(data["conditions"], list) else [data["conditions"]]
            parts.append(f"Conditions: {', '.join(conds[:5])}")
        if data.get("interventions"):
            intv = data["interventions"] if isinstance(data["interventions"], list) else [data["interventions"]]
            parts.append(f"Interventions: {', '.join(str(i) for i in intv[:5])}")
        if data.get("brief_summary"):
            parts.append(f"Summary: {data['brief_summary'][:300]}")
        return " | ".join(parts)
