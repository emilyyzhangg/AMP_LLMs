"""
WHO International Clinical Trials Registry Platform (ICTRP) Research Agent.

Queries the WHO ICTRP (https://trialsearch.who.int) for international clinical
trial registrations. ICTRP indexes ClinicalTrials.gov plus registries from
Europe (EudraCT/EUCTR), Japan (JPRN), China (ChiCTR), and others.

This agent looks up trials by NCT ID and extracts registration status,
countries, conditions, interventions, phase, and study type from the HTML
response (the ICTRP does not provide a public REST API).
"""

import logging
import re
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.who_ictrp")

ICTRP_TRIAL_URL = "https://trialsearch.who.int/Trial2.aspx"


class WHOICTRPClient(BaseResearchAgent):
    """Queries the WHO ICTRP for international clinical trial data."""

    agent_name = "who_ictrp"
    sources = ["who_ictrp"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        if not nct_id:
            return ResearchResult(
                agent_name=self.agent_name,
                nct_id=nct_id,
                citations=[],
                raw_data={"note": "No NCT ID provided"},
            )

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await resilient_get(
                    ICTRP_TRIAL_URL,
                    client=client,
                    params={"TrialID": nct_id},
                    max_retries=2,
                )
                if resp.status_code == 200:
                    html = resp.text
                    extracted = self._parse_ictrp_response(html, nct_id)
                    raw_data["ictrp_data"] = extracted

                    if extracted.get("found"):
                        snippet_parts = []
                        if extracted.get("public_title"):
                            snippet_parts.append(f"Title: {extracted['public_title']}")
                        if extracted.get("recruitment_status"):
                            snippet_parts.append(f"Status: {extracted['recruitment_status']}")
                        if extracted.get("phase"):
                            snippet_parts.append(f"Phase: {extracted['phase']}")
                        if extracted.get("countries"):
                            snippet_parts.append(f"Countries: {', '.join(extracted['countries'])}")
                        if extracted.get("conditions"):
                            snippet_parts.append(f"Conditions: {', '.join(extracted['conditions'])}")
                        if extracted.get("interventions"):
                            snippet_parts.append(f"Interventions: {', '.join(extracted['interventions'])}")
                        if extracted.get("study_type"):
                            snippet_parts.append(f"Study type: {extracted['study_type']}")

                        citations.append(SourceCitation(
                            source_name="who_ictrp",
                            source_url=f"{ICTRP_TRIAL_URL}?TrialID={nct_id}",
                            identifier=nct_id,
                            title=extracted.get("public_title", f"ICTRP: {nct_id}"),
                            snippet="\n".join(snippet_parts) if snippet_parts else f"WHO ICTRP record for {nct_id}",
                            quality_score=self.compute_quality_score("who_ictrp"),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))
                    else:
                        raw_data["ictrp_note"] = "Trial not found in ICTRP"
                else:
                    raw_data["ictrp_status"] = resp.status_code
            except Exception as e:
                logger.warning("WHO ICTRP lookup failed for %s: %s", nct_id, e)
                raw_data["ictrp_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    @staticmethod
    def _parse_ictrp_response(html: str, nct_id: str) -> dict:
        """Extract structured trial data from the ICTRP Trial2.aspx HTML.

        The ICTRP page uses ASP.NET server controls with predictable span IDs
        like DataList3_ctl01_Public_titleLabel, DataList3_ctl01_PhaseLabel, etc.
        """
        result: dict = {"found": False, "nct_id": nct_id}

        # Map of span ID suffixes to our field names
        field_map = {
            "Public_titleLabel": "public_title",
            "Scientific_titleLabel": "scientific_title",
            "Recruitment_statusLabel": "recruitment_status",
            "PhaseLabel": "phase",
            "Study_typeLabel": "study_type",
            "Study_designLabel": "study_design",
        }

        for span_suffix, field_name in field_map.items():
            pattern = re.compile(
                rf'id="DataList3_ctl01_{span_suffix}"[^>]*>([^<]+)<',
                re.IGNORECASE,
            )
            match = pattern.search(html)
            if match:
                value = match.group(1).strip()
                if value:
                    result[field_name] = value
                    result["found"] = True

        # Extract countries (DataList2_ctl0N_Country_Label)
        countries = []
        country_pattern = re.compile(
            r'id="DataList2_ctl\d+_Country_Label"[^>]*>([^<]+)<',
            re.IGNORECASE,
        )
        for match in country_pattern.finditer(html):
            country = match.group(1).strip()
            if country:
                countries.append(country)
        if countries:
            result["countries"] = countries
            result["found"] = True

        # Extract conditions (DataList8_ctl0N_Condition_FreeTextLabel)
        conditions = []
        condition_pattern = re.compile(
            r'id="DataList8_ctl\d+_Condition_FreeTextLabel"[^>]*>([^<]+)<',
            re.IGNORECASE,
        )
        for match in condition_pattern.finditer(html):
            condition = match.group(1).strip()
            if condition:
                conditions.append(condition)
        if conditions:
            result["conditions"] = conditions
            result["found"] = True

        # Extract interventions (DataList10_ctl0N_Intervention_FreeTextLabel)
        interventions = []
        intervention_pattern = re.compile(
            r'id="DataList10_ctl\d+_Intervention_FreeTextLabel"[^>]*>([^<]+)<',
            re.IGNORECASE,
        )
        for match in intervention_pattern.finditer(html):
            intervention = match.group(1).strip()
            if intervention:
                interventions.append(intervention)
        if interventions:
            result["interventions"] = interventions
            result["found"] = True

        return result
