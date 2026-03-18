"""
dbAMP 3.0 Research Agent.

Queries the dbAMP database (https://yylab.jnu.edu.cn/dbAMP/) for antimicrobial
peptide sequences, functional activity, and structural annotations.

Note: The dbAMP server at yylab.jnu.edu.cn may be slow or intermittently
unavailable. This agent uses a short timeout and degrades gracefully.
"""

import logging
import re
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.dbamp")

DBAMP_SEARCH_URL = "https://yylab.jnu.edu.cn/dbAMP/Search.php"
DBAMP_BASE_URL = "https://yylab.jnu.edu.cn/dbAMP"


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


class DbAMPClient(BaseResearchAgent):
    """Queries dbAMP 3.0 for antimicrobial peptide data."""

    agent_name = "dbamp"
    sources = ["dbamp"]

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

        # dbAMP server can be slow/unreliable — use a short timeout
        async with httpx.AsyncClient(timeout=12) as client:
            for intervention in interventions[:3]:
                try:
                    resp = await resilient_get(
                        DBAMP_SEARCH_URL,
                        client=client,
                        params={"keyword": intervention},
                        timeout=12,
                        max_retries=1,
                    )
                    if resp.status_code == 200:
                        html = resp.text
                        extracted = self._parse_dbamp_results(html, intervention)
                        raw_data[f"dbamp_{intervention}"] = extracted

                        if extracted.get("peptides"):
                            for pep in extracted["peptides"][:3]:
                                snippet_parts = [f"Peptide: {pep.get('name', intervention)}"]
                                if pep.get("sequence"):
                                    snippet_parts.append(f"Sequence: {pep['sequence'][:80]}")
                                if pep.get("activity"):
                                    snippet_parts.append(f"Activity: {pep['activity']}")
                                if pep.get("structure"):
                                    snippet_parts.append(f"Structure: {pep['structure']}")

                                citations.append(SourceCitation(
                                    source_name="dbamp",
                                    source_url=pep.get("url", f"{DBAMP_BASE_URL}/"),
                                    identifier=pep.get("dbamp_id", intervention),
                                    title=f"{pep.get('name', intervention)} - dbAMP",
                                    snippet="\n".join(snippet_parts),
                                    quality_score=self.compute_quality_score("dbamp"),
                                    retrieved_at=datetime.utcnow().isoformat(),
                                ))
                        else:
                            # Record that the search was attempted
                            citations.append(SourceCitation(
                                source_name="dbamp",
                                source_url=f"{DBAMP_BASE_URL}/",
                                identifier=intervention,
                                title=f"dbAMP search: {intervention}",
                                snippet=f"dbAMP database search for: {intervention}",
                                quality_score=self.compute_quality_score("dbamp", has_content=False),
                                retrieved_at=datetime.utcnow().isoformat(),
                            ))
                    else:
                        raw_data[f"dbamp_{intervention}_status"] = resp.status_code
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    logger.info("dbAMP server unreachable for %s: %s", intervention, type(e).__name__)
                    raw_data[f"dbamp_{intervention}_error"] = f"Server unreachable: {type(e).__name__}"
                except Exception as e:
                    logger.warning("dbAMP search failed for %s: %s", intervention, e)
                    raw_data[f"dbamp_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    @staticmethod
    def _parse_dbamp_results(html: str, query: str) -> dict:
        """Best-effort extraction from dbAMP HTML search results.

        dbAMP returns search results as an HTML table. We extract peptide IDs,
        names, sequences, and activity annotations where available.
        """
        results: dict = {"searched": True, "peptides": []}

        # Look for dbAMP ID patterns like dbAMP_00001 or DBAMP00001
        id_pattern = re.compile(r'((?:dbAMP|DBAMP)[_]?\d{3,8})', re.IGNORECASE)
        dbamp_ids = id_pattern.findall(html)
        if dbamp_ids:
            results["dbamp_ids"] = list(set(dbamp_ids))

        # Try to extract table data
        # dbAMP typically has columns: ID, Name, Sequence, Activity, Source
        row_pattern = re.compile(
            r'<tr[^>]*>.*?<td[^>]*>.*?((?:dbAMP|DBAMP)[_]?\d+).*?</td>'
            r'.*?<td[^>]*>([^<]*)</td>'
            r'.*?<td[^>]*>([^<]*)</td>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in row_pattern.finditer(html):
            pep = {
                "dbamp_id": match.group(1).strip(),
                "name": match.group(2).strip() or query,
                "sequence": match.group(3).strip(),
                "url": f"{DBAMP_BASE_URL}/peptide/{match.group(1).strip()}",
            }
            results["peptides"].append(pep)

        # Fallback: if we found IDs but couldn't parse full rows
        if not results["peptides"] and dbamp_ids:
            for dbamp_id in list(set(dbamp_ids))[:3]:
                results["peptides"].append({
                    "dbamp_id": dbamp_id,
                    "name": query,
                    "url": f"{DBAMP_BASE_URL}/peptide/{dbamp_id}",
                })

        return results
