"""
ChEMBL Research Agent.

Queries the ChEMBL database (https://www.ebi.ac.uk/chembl/) for molecule
data, clinical phase information, bioactivity, and mechanism of action.
Focuses on peptide-type compounds relevant to antimicrobial peptide trials.
"""

from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.drug_cache import drug_cache
from agents.research.http_utils import resilient_get
from agents.research.resolved_names import extract_interventions, query_names
from app.models.research import ResearchResult, SourceCitation

CHEMBL_API_BASE = "https://www.ebi.ac.uk/chembl/api/data"
CHEMBL_MOLECULE_SEARCH_URL = f"{CHEMBL_API_BASE}/molecule/search"
CHEMBL_MECHANISM_URL = f"{CHEMBL_API_BASE}/mechanism"
CHEMBL_ACTIVITY_URL = f"{CHEMBL_API_BASE}/activity"


def _coerce_phase(value) -> Optional[int]:
    """Normalize a ChEMBL max_phase to an int in [0, 4], or None if absent.

    ChEMBL returns max_phase as int (4), float (4.0), or numeric string ("4"),
    and uses null / "" / "None" for "no clinical phase recorded". Phase 0
    (preclinical) is a VALID value and must not be dropped as falsy.
    """
    if value is None or value == "":
        return None
    try:
        phase = int(float(value))
    except (ValueError, TypeError):
        return None
    if 0 <= phase <= 4:
        return phase
    return None


class ChEMBLClient(BaseResearchAgent):
    """Queries ChEMBL for molecule data, clinical phases, and bioactivity."""

    agent_name = "chembl"
    sources = ["chembl"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # v14: Fixed intervention extraction — was converting dicts to strings.
        # v42.9 (P1): also surface Lever-4 resolved canonical names so a trial
        # code like "AMG 334" falls back to "erenumab" when the code returns
        # nothing from ChEMBL (codes are rarely indexed; canonical names are).
        interventions = extract_interventions(metadata)

        if not interventions:
            return ResearchResult(
                agent_name=self.agent_name,
                nct_id=nct_id,
                citations=[],
                raw_data={"note": "No interventions to search"},
            )

        async with httpx.AsyncClient(timeout=15) as client:
            for interv in interventions[:3]:
                # Query the raw trial name first; only fall back to resolved
                # canonical names if it found nothing. Each name is cached
                # independently (response is a pure function of the drug name).
                per_intervention = None
                for nm in query_names(interv):
                    async def compute(intv=nm):
                        return await self._fetch_intervention(client, intv)

                    if drug_cache.is_enabled():
                        candidate = await drug_cache.get_or_compute(
                            self.agent_name, nm, compute,
                        )
                    else:
                        candidate = await compute()

                    per_intervention = candidate
                    if candidate["citations"]:
                        break  # raw name or first resolved name that hits wins

                if per_intervention:
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
        """Fetch ChEMBL data for one intervention. Pure function of intervention name.

        Returns {"citations": [...], "raw_data": {...}}. The raw_data keys are
        already intervention-prefixed, so merging results from multiple
        interventions into a per-NCT raw_data dict is collision-free.
        """
        citations: list = []
        raw_data: dict = {}
        try:
            # 1. Search molecules by name
            resp = await resilient_get(
                CHEMBL_MOLECULE_SEARCH_URL,
                client=client,
                params={
                    "q": intervention,
                    "format": "json",
                    "limit": 5,
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                raw_data[f"chembl_{intervention}_status"] = resp.status_code
                return {"citations": citations, "raw_data": raw_data}

            data = resp.json()
            molecules = data.get("molecules", [])
            raw_data[f"chembl_{intervention}_count"] = len(molecules)

            # Filter: only keep molecules whose name matches the intervention.
            # ChEMBL's q= parameter is a full-text search that returns fuzzy
            # matches. "Peptide T" returns botulinum toxin, random small molecules.
            intervention_lower = intervention.lower()
            relevant_mols = []
            for mol in molecules:
                if not isinstance(mol, dict):
                    continue
                pref = (mol.get("pref_name") or "").lower()
                synonyms = " ".join(
                    str(s.get("molecule_synonym", ""))
                    for s in (mol.get("molecule_synonyms") or [])
                ).lower() if mol.get("molecule_synonyms") else ""
                combined = f"{pref} {synonyms}"
                if (intervention_lower in combined
                        or pref in intervention_lower
                        or any(word in combined for word in intervention_lower.split() if len(word) > 3)):
                    relevant_mols.append(mol)

            # Fall back to top results if nothing matched (rare drug names)
            if not relevant_mols:
                relevant_mols = [m for m in molecules[:2] if isinstance(m, dict)]

            # v14: Store molecule entries and HELM structurally in raw_data
            mol_entries = []
            for mol in relevant_mols[:3]:
                if not isinstance(mol, dict):
                    continue

                chembl_id = mol.get("molecule_chembl_id", "")
                pref_name = mol.get("pref_name", "")
                mol_type = mol.get("molecule_type", "")
                # v42.9 (P1): ChEMBL returns max_phase as int, float, or numeric
                # string; the old `mol.get("max_phase", "")` + falsy check dropped
                # a valid phase 0 (preclinical) and stored inconsistent types,
                # leaving drug_max_phase null even for approved (phase 4) drugs.
                # Normalize to an int in [0, 4], or None when truly absent.
                max_phase = _coerce_phase(mol.get("max_phase"))
                helm_notation = mol.get("helm_notation", "")
                first_approval = mol.get("first_approval", "")

                mol_entries.append({
                    "chembl_id": chembl_id,
                    "pref_name": pref_name,
                    "mol_type": mol_type,
                    "helm_notation": helm_notation,
                    "max_phase": max_phase,
                })
                if helm_notation:
                    raw_data[f"chembl_{intervention}_helm"] = helm_notation

                # Extract molecular properties
                mol_props = mol.get("molecule_properties", {}) or {}
                mw = mol_props.get("full_mwt", "")
                alogp = mol_props.get("alogp", "")

                snippet_parts = [f"Molecule: {pref_name or chembl_id}"]
                if mol_type:
                    snippet_parts.append(f"Type: {mol_type}")
                if max_phase is not None:
                    snippet_parts.append(f"Max clinical phase: {max_phase}")
                if helm_notation:
                    snippet_parts.append(f"HELM: {helm_notation[:100]}")
                if mw:
                    snippet_parts.append(f"Molecular weight: {mw}")
                if first_approval:
                    snippet_parts.append(f"First approval: {first_approval}")

                # 2. Fetch mechanism of action if we have a ChEMBL ID
                moa_snippet = await self._fetch_mechanism(client, chembl_id, raw_data)
                if moa_snippet:
                    snippet_parts.append(f"Mechanism: {moa_snippet}")

                # 3. Fetch bioactivity summary
                activity_snippet = await self._fetch_activity_summary(
                    client, chembl_id, raw_data
                )
                if activity_snippet:
                    snippet_parts.append(f"Bioactivity: {activity_snippet}")

                citations.append(SourceCitation(
                    source_name="chembl",
                    source_url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/" if chembl_id else "https://www.ebi.ac.uk/chembl/",
                    identifier=chembl_id or pref_name,
                    title=f"{pref_name or chembl_id} - ChEMBL",
                    snippet="\n".join(snippet_parts),
                    quality_score=self.compute_quality_score("chembl"),
                    retrieved_at=datetime.utcnow().isoformat(),
                ))

            # v14: Store structured molecule entries in raw_data
            if mol_entries:
                raw_data[f"chembl_{intervention}_molecules"] = mol_entries

        except Exception as e:
            raw_data[f"chembl_{intervention}_error"] = str(e)

        return {"citations": citations, "raw_data": raw_data}

    async def _fetch_mechanism(
        self, client: httpx.AsyncClient, chembl_id: str, raw_data: dict
    ) -> str:
        """Fetch mechanism of action for a ChEMBL molecule."""
        if not chembl_id:
            return ""
        try:
            resp = await resilient_get(
                CHEMBL_MECHANISM_URL,
                client=client,
                params={
                    "molecule_chembl_id": chembl_id,
                    "format": "json",
                    "limit": 5,
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                mechanisms = data.get("mechanisms", [])
                if mechanisms:
                    moa_parts = []
                    for mech in mechanisms[:3]:
                        action = mech.get("action_type", "")
                        target = mech.get("target_chembl_id", "")
                        description = mech.get("mechanism_of_action", "")
                        if description:
                            moa_parts.append(description)
                        elif action and target:
                            moa_parts.append(f"{action} on {target}")
                    return "; ".join(moa_parts)
        except Exception as e:
            raw_data[f"chembl_mechanism_{chembl_id}_error"] = str(e)
        return ""

    async def _fetch_activity_summary(
        self, client: httpx.AsyncClient, chembl_id: str, raw_data: dict
    ) -> str:
        """Fetch a summary of bioactivity data for a ChEMBL molecule."""
        if not chembl_id:
            return ""
        try:
            resp = await resilient_get(
                CHEMBL_ACTIVITY_URL,
                client=client,
                params={
                    "molecule_chembl_id": chembl_id,
                    "format": "json",
                    "limit": 10,
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                activities = data.get("activities", [])
                if activities:
                    activity_parts = []
                    for act in activities[:5]:
                        assay_type = act.get("standard_type", "")
                        value = act.get("standard_value", "")
                        units = act.get("standard_units", "")
                        target = act.get("target_pref_name", "")
                        if assay_type and value:
                            part = f"{assay_type}={value}"
                            if units:
                                part += f" {units}"
                            if target:
                                part += f" ({target})"
                            activity_parts.append(part)
                    return "; ".join(activity_parts)
        except Exception as e:
            raw_data[f"chembl_activity_{chembl_id}_error"] = str(e)
        return ""
