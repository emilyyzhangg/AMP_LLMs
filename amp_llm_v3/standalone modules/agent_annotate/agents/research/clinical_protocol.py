"""
Clinical Protocol Research Agent.

Fetches structured trial data directly from ClinicalTrials.gov API v2
and drug safety data from OpenFDA.
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.clinical_protocol")

CT_GOV_API = "https://clinicaltrials.gov/api/v2/studies"


class ClinicalProtocolAgent(BaseResearchAgent):
    """Retrieves clinical protocol data from ClinicalTrials.gov and OpenFDA."""

    agent_name = "clinical_protocol"
    sources = ["clinicaltrials_gov", "openfda"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # 1. Fetch directly from ClinicalTrials.gov API v2
        protocol = {}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{CT_GOV_API}/{nct_id}")
                if resp.status_code == 200:
                    ct_data = resp.json()
                    protocol = ct_data.get("protocolSection", {})
                    raw_data["protocol_section"] = protocol

                    # Extract structured citations from protocol
                    citations.extend(self._extract_protocol_citations(nct_id, protocol))
                    logger.info(f"  ClinicalTrials.gov: {len(citations)} citations for {nct_id}")
                else:
                    raw_data["clinicaltrials_error"] = f"HTTP {resp.status_code}"
                    logger.warning(f"  ClinicalTrials.gov: HTTP {resp.status_code} for {nct_id}")
        except Exception as e:
            raw_data["clinicaltrials_error"] = str(e)
            logger.error(f"  ClinicalTrials.gov fetch failed for {nct_id}: {e}")

        # 2. OpenFDA drug safety lookup using intervention names
        interventions = []
        arms_mod = protocol.get("armsInterventionsModule", {})
        for interv in arms_mod.get("interventions", []):
            name = interv.get("name", "")
            if name:
                interventions.append(name)

        for intervention in interventions[:3]:
            try:
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
                            route = ""
                            if results[0].get("openfda", {}).get("route"):
                                route = ", ".join(results[0]["openfda"]["route"])
                            citations.append(SourceCitation(
                                source_name="openfda",
                                source_url="https://api.fda.gov",
                                identifier=intervention,
                                title=f"FDA Label: {intervention}",
                                snippet=f"Route: {route}" if route else f"FDA label found for {intervention}",
                                quality_score=self.compute_quality_score("openfda"),
                                retrieved_at=datetime.utcnow().isoformat(),
                            ))
            except Exception as e:
                raw_data[f"openfda_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    def _extract_protocol_citations(self, nct_id: str, protocol: dict) -> list[SourceCitation]:
        """Extract structured citations from ClinicalTrials.gov protocolSection."""
        citations = []
        base_url = f"https://clinicaltrials.gov/study/{nct_id}"
        ident = protocol.get("identificationModule", {})
        status_mod = protocol.get("statusModule", {})
        desc = protocol.get("descriptionModule", {})
        cond_mod = protocol.get("conditionsModule", {})
        arms_mod = protocol.get("armsInterventionsModule", {})
        design_mod = protocol.get("designModule", {})

        title = ident.get("officialTitle") or ident.get("briefTitle", "")
        if title:
            citations.append(SourceCitation(
                source_name="clinicaltrials_gov", identifier=nct_id,
                source_url=base_url, title=title,
                snippet=f"Title: {title}",
                quality_score=self.compute_quality_score("clinicaltrials_gov"),
                retrieved_at=datetime.utcnow().isoformat(),
            ))

        summary = desc.get("briefSummary", "")
        if summary:
            citations.append(SourceCitation(
                source_name="clinicaltrials_gov", identifier=nct_id,
                source_url=base_url, title="Brief Summary",
                snippet=summary[:500],
                quality_score=self.compute_quality_score("clinicaltrials_gov"),
                retrieved_at=datetime.utcnow().isoformat(),
            ))

        overall_status = status_mod.get("overallStatus", "")
        if overall_status:
            why_stopped = status_mod.get("whyStopped", "")
            snippet = f"Status: {overall_status}"
            if why_stopped:
                snippet += f" | Why stopped: {why_stopped}"
            citations.append(SourceCitation(
                source_name="clinicaltrials_gov", identifier=nct_id,
                source_url=base_url, title="Study Status",
                snippet=snippet,
                quality_score=self.compute_quality_score("clinicaltrials_gov"),
                retrieved_at=datetime.utcnow().isoformat(),
            ))

        conditions = cond_mod.get("conditions", [])
        keywords = cond_mod.get("keywords", [])
        if conditions or keywords:
            snippet = f"Conditions: {', '.join(conditions)}"
            if keywords:
                snippet += f" | Keywords: {', '.join(keywords)}"
            citations.append(SourceCitation(
                source_name="clinicaltrials_gov", identifier=nct_id,
                source_url=base_url, title="Conditions & Keywords",
                snippet=snippet,
                quality_score=self.compute_quality_score("clinicaltrials_gov"),
                retrieved_at=datetime.utcnow().isoformat(),
            ))

        for interv in arms_mod.get("interventions", []):
            name = interv.get("name", "")
            itype = interv.get("type", "")
            idesc = interv.get("description", "")
            snippet = f"{itype}: {name}"
            if idesc:
                snippet += f" - {idesc[:300]}"
            citations.append(SourceCitation(
                source_name="clinicaltrials_gov", identifier=nct_id,
                source_url=base_url, title=f"Intervention: {name}",
                snippet=snippet,
                quality_score=self.compute_quality_score("clinicaltrials_gov"),
                retrieved_at=datetime.utcnow().isoformat(),
            ))

        phases = design_mod.get("phases", [])
        if phases:
            citations.append(SourceCitation(
                source_name="clinicaltrials_gov", identifier=nct_id,
                source_url=base_url, title="Phase",
                snippet=f"Phase: {', '.join(phases)}",
                quality_score=self.compute_quality_score("clinicaltrials_gov"),
                retrieved_at=datetime.utcnow().isoformat(),
            ))

        return citations
