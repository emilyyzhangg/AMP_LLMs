"""
APD (Antimicrobial Peptide Database) Research Agent.

Queries the APD database (https://aps.unmc.edu) for antimicrobial peptide
information including activity data, source organisms, and sequence details.

The APD does not provide a REST API; this agent submits a POST form to the
database search endpoint and parses the HTML response. Because the server-side
search may require a live browser session, results are best-effort and the
agent falls back gracefully when no data can be extracted.

v14 changes:
  - Fetch detail pages for each APD ID to extract actual sequences
  - Store sequences structurally in raw_data for the sequence agent
  - Include sequence in citation snippets (APD is peptide-specific)
"""

import logging
import re
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.drug_cache import drug_cache
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

        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            for intervention in interventions[:3]:
                async def compute(intv=intervention):
                    return await self._fetch_intervention(client, intv)

                if drug_cache.is_enabled():
                    per_intervention = await drug_cache.get_or_compute(
                        self.agent_name, intervention, compute,
                    )
                else:
                    per_intervention = await compute()

                citations.extend(per_intervention["citations"])
                raw_data.update(per_intervention["raw_data"])

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _fetch_intervention(
        self, client: httpx.AsyncClient, intervention: str,
    ) -> dict:
        """Fetch APD data for one intervention. Pure function of intervention name."""
        citations: list = []
        raw_data: dict = {}
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
                    # v8: Do NOT emit a citation for negative results —
                    # "no exact match" wastes an LLM citation slot without
                    # adding information. The raw_data records the search.
                    return {"citations": citations, "raw_data": raw_data}

                # Try to extract peptide data from the HTML response
                extracted = self._parse_apd_results(html, intervention)
                raw_data[f"apd_{intervention}"] = extracted

                # v14: Fetch detail pages to get actual sequences
                apd_sequences = []
                if extracted.get("peptides"):
                    for pep in extracted["peptides"][:3]:
                        apd_id = pep.get("apd_id", "")
                        if not apd_id:
                            continue

                        detail = await self._fetch_apd_detail(client, apd_id)
                        if detail.get("sequence"):
                            pep["sequence"] = detail["sequence"]
                            pep["length"] = detail.get("length", len(detail["sequence"]))
                            pep["source_organism"] = detail.get("source_organism", "")
                            apd_sequences.append({
                                "apd_id": apd_id,
                                "name": pep.get("name", intervention),
                                "sequence": detail["sequence"],
                                "length": detail.get("length", len(detail["sequence"])),
                            })

                    # v14: Store sequences structurally in raw_data
                    if apd_sequences:
                        raw_data[f"apd_{intervention}_sequences"] = apd_sequences

                    for pep in extracted["peptides"][:3]:
                        snippet_parts = [f"Peptide: {pep.get('name', intervention)}"]
                        if pep.get("source_organism"):
                            snippet_parts.append(f"Source: {pep['source_organism']}")
                        elif pep.get("source"):
                            snippet_parts.append(f"Source: {pep['source']}")
                        if pep.get("sequence"):
                            snippet_parts.append(f"Sequence: {pep['sequence'][:80]}")
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

        return {"citations": citations, "raw_data": raw_data}

    async def _fetch_apd_detail(self, client: httpx.AsyncClient, apd_id: str) -> dict:
        """Fetch an APD detail page and extract sequence data.

        Returns dict with keys: sequence, length, source_organism (all optional).
        Returns empty dict on failure.
        """
        try:
            resp = await client.get(
                f"{APD_BASE_URL}/peptide/{apd_id}",
                timeout=10,
                headers={"Referer": "https://aps.unmc.edu/database"},
            )
            if resp.status_code != 200:
                return {}
            return self._parse_apd_detail(resp.text)
        except Exception as e:
            logger.debug("APD detail fetch failed for %s: %s", apd_id, e)
            return {}

    @staticmethod
    def _parse_apd_detail(html: str) -> dict:
        """Parse an APD peptide detail page for sequence and metadata.

        APD detail pages have labeled fields in table rows or divs.
        This is best-effort parsing — HTML structure may vary.
        """
        result: dict = {}

        # Try multiple patterns for sequence extraction:
        seq_patterns = [
            # Table cell: <td>Sequence</td><td>GIGKFLH...</td>
            re.compile(
                r'(?:Sequence|Amino\s*acid\s*sequence)\s*(?:</[^>]+>\s*<[^>]+>|:\s*)'
                r'\s*([A-Z]{3,})',
                re.IGNORECASE,
            ),
            # Plain text after label
            re.compile(
                r'(?:Sequence|sequence)\s*[:=]\s*([A-Z]{3,})',
            ),
            # Standalone block of uppercase AA after any "sequence" mention
            re.compile(
                r'[Ss]equence[^A-Z]{0,50}([A-Z]{5,})',
            ),
        ]

        for pattern in seq_patterns:
            match = pattern.search(html)
            if match:
                seq = match.group(1).strip()
                # Validate: must be mostly valid AA characters
                valid_aa = set("ACDEFGHIKLMNPQRSTVWY")
                if len(seq) >= 3 and sum(1 for c in seq if c in valid_aa) / len(seq) > 0.8:
                    result["sequence"] = seq
                    result["length"] = len(seq)
                    break

        # Try to extract source organism
        source_patterns = [
            re.compile(r'[Ss]ource\s*(?:organism)?\s*[:=]\s*([^<\n]{3,50})'),
            re.compile(r'<td[^>]*>\s*Source\s*</td>\s*<td[^>]*>\s*([^<]+)', re.IGNORECASE),
        ]
        for pattern in source_patterns:
            match = pattern.search(html)
            if match:
                result["source_organism"] = match.group(1).strip()
                break

        return result

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
