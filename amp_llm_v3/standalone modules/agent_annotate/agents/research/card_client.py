"""
CARD Research Agent.

Queries the Comprehensive Antibiotic Resistance Database
(https://card.mcmaster.ca) for antibiotic resistance ontology data,
resistance mechanisms, associated antibiotics, and pathogen targets.

CARD uses internal AJAX endpoints (livesearch + load/json) rather than
a formal REST API. Both are free with no authentication.
"""

import re
import logging
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.card")

CARD_BASE = "https://card.mcmaster.ca"
CARD_LIVESEARCH_URL = f"{CARD_BASE}/livesearch"

# Regex to extract ontology IDs and names from livesearch HTML.
# The JSON response escapes forward slashes (e.g. ``https:\/\/``),
# so we accept both ``/`` and ``\/`` in the URL.
_LIVESEARCH_RE = re.compile(
    r"<a\s+href=['\"]"
    r"https?:(?:\\?/){2}card\.mcmaster\.ca(?:\\?/)ontology(?:\\?/)(\d+)"
    r"['\"]>"
    r"([^<]+)</a>",
    re.IGNORECASE,
)


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


class CARDClient(BaseResearchAgent):
    """Queries CARD for antibiotic resistance mechanisms and ontology data."""

    agent_name = "card"
    sources = ["card"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        # Extract intervention names to search for resistance-related terms
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
                try:
                    # livesearch to find matching ontology entries
                    matches = await self._livesearch(client, intervention, raw_data)
                    raw_data[f"card_{intervention}_matches"] = len(matches)

                    if not matches:
                        continue

                    # Build citations directly from livesearch results.
                    # The old approach downloaded the full 3 MB ARO JSON
                    # index and looked up each ID, but that frequently
                    # timed out.  Livesearch gives us names and ARO IDs
                    # which is enough for a useful citation.
                    for aro_id, aro_name in matches[:5]:
                        citations.append(SourceCitation(
                            source_name="card",
                            source_url=f"{CARD_BASE}/ontology/{aro_id}",
                            identifier=f"ARO:{aro_id}",
                            title=f"{aro_name} - CARD",
                            snippet=(
                                f"ARO term: {aro_name}\n"
                                f"ARO ID: {aro_id}\n"
                                f"Search term: {intervention}\n"
                                f"Source: Comprehensive Antibiotic Resistance Database"
                            ),
                            quality_score=self.compute_quality_score("card"),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))

                except Exception as e:
                    logger.warning("CARD search failed for %s: %s", intervention, e)
                    raw_data[f"card_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _livesearch(
        self,
        client: httpx.AsyncClient,
        query: str,
        raw_data: dict,
    ) -> list[tuple[str, str]]:
        """Search CARD via livesearch and return (aro_id, name) tuples."""
        try:
            resp = await resilient_get(
                CARD_LIVESEARCH_URL,
                client=client,
                params={"query": query},
                headers={
                    "Accept": "application/json, text/html, */*",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            if resp.status_code != 200:
                raw_data[f"card_livesearch_{query}_status"] = resp.status_code
                return []

            body = resp.text.strip()
            if not body:
                return []

            data = resp.json()

            # Response shape: {"error": false, "response": "<li>...HTML...</li>"}
            html_content = data.get("response", "")
            if not html_content:
                return []

            # Parse ontology IDs and names from the HTML response
            matches = _LIVESEARCH_RE.findall(html_content)
            raw_data[f"card_livesearch_{query}_html_len"] = len(html_content)
            return matches

        except Exception as e:
            logger.warning("CARD livesearch failed for %s: %s", query, e)
            raw_data[f"card_livesearch_{query}_error"] = str(e)
            return []
