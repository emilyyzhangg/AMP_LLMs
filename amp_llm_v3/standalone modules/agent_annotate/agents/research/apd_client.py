"""
APD (Antimicrobial Peptide Database) Research Agent.

Queries the APD database (https://aps.unmc.edu) for antimicrobial peptide
information including activity data, source organisms, and sequence details.

The APD does not provide a REST API; this agent submits a POST form to the
database search endpoint and parses the HTML response. Because the server-side
search may require a live browser session, results are best-effort and the
agent falls back gracefully when no data can be extracted.
"""

import logging
import re
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.apd")

APD_SEARCH_URL = "https://aps.unmc.edu/database/result"
APD_BASE_URL = "https://aps.unmc.edu"


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


class APDClient(BaseResearchAgent):
    """Queries the Antimicrobial Peptide Database for peptide data."""

    agent_name = "apd"
    sources = ["apd"]

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

        async with httpx.AsyncClient(timeout=15) as client:
            for intervention in interventions[:3]:
                try:
                    # APD uses a POST form search; submit with the Name field
                    resp = await client.post(
                        APD_SEARCH_URL,
                        data={
                            "ID": "",
                            "Name": intervention,
                            "Name2": "",
                            "Name3": "",
                            "source": "",
                            "Sequence": "",
                            "Sequence2": "",
                            "Length": "0",
                            "Netcharge": "0",
                            "HydrophobicPer": "0",
                            "Location": "0",
                            "LocationID": "",
                            "Type": "0",
                            "Method": "0",
                        },
                        headers={
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Referer": "https://aps.unmc.edu/database",
                        },
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        html = resp.text

                        # Check if results were found
                        if "No Results Found" in html:
                            raw_data[f"apd_{intervention}"] = {"searched": True, "found": False}
                            # Still record that we searched
                            citations.append(SourceCitation(
                                source_name="apd",
                                source_url=f"{APD_BASE_URL}/database",
                                identifier=intervention,
                                title=f"APD search: {intervention}",
                                snippet=f"APD antimicrobial peptide database search for: {intervention} (no exact match)",
                                quality_score=self.compute_quality_score("apd", has_content=False),
                                retrieved_at=datetime.utcnow().isoformat(),
                            ))
                            continue

                        # Try to extract peptide data from the HTML response
                        extracted = self._parse_apd_results(html, intervention)
                        raw_data[f"apd_{intervention}"] = extracted

                        if extracted.get("peptides"):
                            for pep in extracted["peptides"][:3]:
                                snippet_parts = [f"Peptide: {pep.get('name', intervention)}"]
                                if pep.get("source"):
                                    snippet_parts.append(f"Source: {pep['source']}")
                                if pep.get("length"):
                                    snippet_parts.append(f"Length: {pep['length']} aa")
                                if pep.get("activity"):
                                    snippet_parts.append(f"Activity: {pep['activity']}")

                                citations.append(SourceCitation(
                                    source_name="apd",
                                    source_url=pep.get("url", f"{APD_BASE_URL}/database"),
                                    identifier=pep.get("apd_id", intervention),
                                    title=f"{pep.get('name', intervention)} - APD",
                                    snippet="\n".join(snippet_parts),
                                    quality_score=self.compute_quality_score("apd"),
                                    retrieved_at=datetime.utcnow().isoformat(),
                                ))
                        else:
                            # Search returned HTML but we couldn't parse structured data
                            citations.append(SourceCitation(
                                source_name="apd",
                                source_url=f"{APD_BASE_URL}/database",
                                identifier=intervention,
                                title=f"APD search: {intervention}",
                                snippet=f"APD database returned results for: {intervention} (HTML response, limited extraction)",
                                quality_score=self.compute_quality_score("apd", has_content=False),
                                retrieved_at=datetime.utcnow().isoformat(),
                            ))
                    else:
                        raw_data[f"apd_{intervention}_status"] = resp.status_code
                except Exception as e:
                    logger.warning("APD search failed for %s: %s", intervention, e)
                    raw_data[f"apd_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    @staticmethod
    def _parse_apd_results(html: str, query: str) -> dict:
        """Best-effort extraction of peptide data from APD HTML response.

        APD result pages use simple HTML tables. We try to extract APD IDs,
        peptide names, source organisms, lengths, and activity annotations.
        """
        results: dict = {"searched": True, "found": True, "peptides": []}

        # Look for APD ID patterns like AP00001
        apd_ids = re.findall(r'(AP\d{4,6})', html)
        if apd_ids:
            results["apd_ids"] = list(set(apd_ids))

        # Try to extract table rows with peptide info
        # APD typically renders results in a table with columns for ID, Name, etc.
        row_pattern = re.compile(
            r'<tr[^>]*>.*?<td[^>]*>(AP\d+)</td>.*?<td[^>]*>([^<]+)</td>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in row_pattern.finditer(html):
            pep = {
                "apd_id": match.group(1).strip(),
                "name": match.group(2).strip(),
                "url": f"{APD_BASE_URL}/peptide/{match.group(1).strip()}",
            }
            results["peptides"].append(pep)

        # If no table rows found, try simpler extraction
        if not results["peptides"] and apd_ids:
            for apd_id in list(set(apd_ids))[:3]:
                results["peptides"].append({
                    "apd_id": apd_id,
                    "name": query,
                    "url": f"{APD_BASE_URL}/peptide/{apd_id}",
                })

        return results
