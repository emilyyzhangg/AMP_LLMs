"""
IUPHAR/BPS Guide to Pharmacology Research Agent.

Queries the IUPHAR Guide to Pharmacology REST API
(https://www.guidetopharmacology.org/services/) for ligand and target data.

This is a well-documented, free, open API with no authentication required.
It provides pharmacological classification, mechanism of action, clinical use,
and approval status for drugs and ligands including peptides.
"""

import logging
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.iuphar")

IUPHAR_API_BASE = "https://www.guidetopharmacology.org/services"
IUPHAR_LIGANDS_URL = f"{IUPHAR_API_BASE}/ligands"


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


class IUPHARClient(BaseResearchAgent):
    """Queries the IUPHAR Guide to Pharmacology for ligand/drug data."""

    agent_name = "iuphar"
    sources = ["iuphar"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Extract intervention names to search for ligands/drugs
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
                    # Search ligands by name — try original casing first,
                    # then lowercase, since the API can be case-sensitive.
                    ligands = None
                    for variant in dict.fromkeys([intervention, intervention.lower()]):
                        resp = await resilient_get(
                            IUPHAR_LIGANDS_URL,
                            client=client,
                            params={"name": variant},
                            headers={"Accept": "application/json"},
                        )
                        if resp.status_code == 200:
                            ligands = resp.json()
                            break

                    if ligands is None:
                        raw_data[f"iuphar_{intervention}"] = {"found": False}
                        continue

                    if not isinstance(ligands, list):
                        ligands = [ligands] if ligands else []

                    # Filter: only keep ligands whose name actually matches
                    # the intervention. IUPHAR's name search is substring-based,
                    # so "Peptide T" returns "peptide YY", "glucagon-like peptide 1", etc.
                    intervention_lower = intervention.lower()
                    filtered_ligands = [
                        lig for lig in ligands
                        if isinstance(lig, dict) and (
                            intervention_lower in (lig.get("name") or "").lower()
                            or (lig.get("name") or "").lower() in intervention_lower
                            or intervention_lower in (lig.get("abbreviation") or "").lower()
                            or intervention_lower in (lig.get("inn") or "").lower()
                        )
                    ]

                    raw_data[f"iuphar_{intervention}"] = filtered_ligands[:5]

                    if not filtered_ligands and ligands:
                        logger.info(
                            "IUPHAR: %d results for '%s' but none matched name — skipping noise",
                            len(ligands), intervention,
                        )

                    for ligand in filtered_ligands[:3]:
                        if not isinstance(ligand, dict):
                            continue

                        ligand_id = ligand.get("ligandId", "")
                        name = ligand.get("name", intervention)
                        lig_type = ligand.get("type", "")
                        abbreviation = ligand.get("abbreviation", "")
                        inn = ligand.get("inn", "")
                        approved = ligand.get("approved", False)
                        approval_source = ligand.get("approvalSource", "")
                        species = ligand.get("species", "")

                        snippet_parts = [f"Ligand: {name}"]
                        if lig_type:
                            snippet_parts.append(f"Type: {lig_type}")
                        if abbreviation:
                            snippet_parts.append(f"Abbreviation: {abbreviation}")
                        if inn:
                            snippet_parts.append(f"INN: {inn}")
                        if approved:
                            approval_text = "Approved: Yes"
                            if approval_source:
                                approval_text += f" ({approval_source})"
                            snippet_parts.append(approval_text)
                        if species:
                            snippet_parts.append(f"Species: {species}")

                        # Fetch additional details for each ligand
                        detail_data = await self._fetch_ligand_details(
                            client, ligand_id
                        )
                        if detail_data:
                            raw_data[f"iuphar_{intervention}_detail_{ligand_id}"] = detail_data
                            if detail_data.get("mechanism"):
                                snippet_parts.append(f"Mechanism: {detail_data['mechanism']}")
                            if detail_data.get("clinical_use"):
                                snippet_parts.append(f"Clinical use: {detail_data['clinical_use']}")

                        source_url = (
                            f"https://www.guidetopharmacology.org/GRAC/LigandDisplayForward?ligandId={ligand_id}"
                            if ligand_id
                            else "https://www.guidetopharmacology.org/"
                        )

                        citations.append(SourceCitation(
                            source_name="iuphar",
                            source_url=source_url,
                            identifier=f"GtoPdb:{ligand_id}" if ligand_id else name,
                            title=f"{name} - Guide to Pharmacology",
                            snippet="\n".join(snippet_parts),
                            quality_score=self.compute_quality_score("iuphar"),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))

                except Exception as e:
                    logger.warning("IUPHAR search failed for %s: %s", intervention, e)
                    raw_data[f"iuphar_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _fetch_ligand_details(
        self, client: httpx.AsyncClient, ligand_id: int | str
    ) -> dict:
        """Fetch additional detail for a single ligand (mechanism, clinical use)."""
        if not ligand_id:
            return {}
        try:
            resp = await resilient_get(
                f"{IUPHAR_LIGANDS_URL}/{ligand_id}",
                client=client,
                headers={"Accept": "application/json"},
                max_retries=1,
            )
            if resp.status_code == 200:
                data = resp.json()
                detail = {}
                # The full ligand object may contain additional fields
                if data.get("bioactivityComments"):
                    detail["mechanism"] = str(data["bioactivityComments"])[:200]
                if data.get("clinicalUse"):
                    detail["clinical_use"] = str(data["clinicalUse"])[:200]
                if data.get("mechanismOfAction"):
                    detail["mechanism"] = str(data["mechanismOfAction"])[:200]
                return detail
        except Exception as e:
            logger.debug("IUPHAR detail fetch failed for ligand %s: %s", ligand_id, e)
        return {}
