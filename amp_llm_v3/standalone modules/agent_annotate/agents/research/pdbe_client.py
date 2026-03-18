"""
PDBe (Protein Data Bank in Europe) Research Agent.

Queries the PDBe API (https://www.ebi.ac.uk/pdbe/api/) for protein/peptide
structural data including resolution, R-factor, experimental method,
citations, and ligand information. Free, no authentication required.

Complements the RCSB PDB agent by providing EBI-specific validation metrics
and European-curated annotations.
"""

from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation


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


PDBE_SEARCH_URL = "https://www.ebi.ac.uk/pdbe/search/pdb/select"
PDBE_ENTRY_URL = "https://www.ebi.ac.uk/pdbe/api/pdb/entry/summary"
PDBE_MOLECULES_URL = "https://www.ebi.ac.uk/pdbe/api/pdb/entry/molecules"

# Fields to request from the Solr search endpoint
_SEARCH_FIELDS = ",".join([
    "pdb_id",
    "title",
    "experimental_method",
    "resolution",
    "r_factor",
    "r_free",
    "citation_title",
    "citation_author",
    "molecule_name",
    "molecule_type",
    "organism_scientific_name",
    "deposition_date",
    "release_date",
    "number_of_bound_entities",
])


class PDBEClient(BaseResearchAgent):
    """Queries PDBe for protein structure quality metrics and metadata."""

    agent_name = "pdbe"
    sources = ["pdbe"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        # Extract intervention names to search for structures
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
                    # Step 1: Search PDBe Solr index
                    resp = await resilient_get(
                        PDBE_SEARCH_URL,
                        client=client,
                        params={
                            "q": intervention,
                            "rows": 5,
                            "wt": "json",
                            "fl": _SEARCH_FIELDS,
                        },
                        headers={"Accept": "application/json"},
                    )
                    if resp.status_code != 200:
                        raw_data[f"pdbe_{intervention}_status"] = resp.status_code
                        continue

                    search_data = resp.json()
                    response = search_data.get("response", {})
                    num_found = response.get("numFound", 0)
                    docs = response.get("docs", [])
                    raw_data[f"pdbe_{intervention}_count"] = num_found

                    if not docs:
                        continue

                    # Step 2: Build citations from search results, enriching
                    # with entry summary for top hits
                    for doc in docs[:3]:
                        pdb_id = doc.get("pdb_id", "")
                        if not pdb_id:
                            continue

                        # Enrich with entry summary (ligands, assemblies)
                        summary = await self._fetch_entry_summary(
                            client, pdb_id, raw_data
                        )

                        citation = self._build_citation(
                            pdb_id, doc, summary, intervention
                        )
                        if citation:
                            citations.append(citation)

                except Exception as e:
                    raw_data[f"pdbe_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _fetch_entry_summary(
        self,
        client: httpx.AsyncClient,
        pdb_id: str,
        raw_data: dict,
    ) -> dict:
        """Fetch the PDBe entry summary for additional metadata."""
        try:
            resp = await resilient_get(
                f"{PDBE_ENTRY_URL}/{pdb_id}",
                client=client,
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                raw_data[f"pdbe_summary_{pdb_id}_status"] = resp.status_code
                return {}

            data = resp.json()
            # PDBe returns {pdb_id: [entry_dict]}
            entries = data.get(pdb_id, [])
            if isinstance(entries, list) and entries:
                return entries[0]
            return {}

        except Exception as e:
            raw_data[f"pdbe_summary_{pdb_id}_error"] = str(e)
            return {}

    def _build_citation(
        self,
        pdb_id: str,
        doc: dict,
        summary: dict,
        intervention: str,
    ) -> Optional[SourceCitation]:
        """Build a SourceCitation from PDBe search doc and entry summary."""
        title = doc.get("title", "")

        # Structure quality metrics from Solr
        resolution = doc.get("resolution")
        r_factor = doc.get("r_factor")
        r_free = doc.get("r_free")

        # Experimental method
        methods = doc.get("experimental_method", [])
        method_str = ", ".join(methods) if isinstance(methods, list) else str(methods)

        # Molecule info
        mol_names = doc.get("molecule_name", [])
        mol_type = doc.get("molecule_type", "")
        organisms = doc.get("organism_scientific_name", [])

        # Dates
        deposition_date = doc.get("deposition_date", "")
        release_date = doc.get("release_date", "")

        # Citation from search
        citation_title = doc.get("citation_title", "")
        citation_authors = doc.get("citation_author", [])

        # Ligand count from search
        num_ligands = doc.get("number_of_bound_entities")

        # Enrichments from entry summary
        num_entities = summary.get("number_of_entities", {})
        assemblies = summary.get("assemblies", [])
        entry_authors = summary.get("entry_authors", [])

        # Build snippet
        snippet_parts = [f"PDB ID: {pdb_id}"]
        if title:
            snippet_parts.append(f"Title: {title}")
        if method_str:
            snippet_parts.append(f"Experimental method: {method_str}")

        # Quality metrics block
        quality_parts = []
        if resolution is not None:
            quality_parts.append(f"Resolution: {resolution} A")
        if r_factor is not None:
            quality_parts.append(f"R-factor: {r_factor:.4f}")
        if r_free is not None:
            quality_parts.append(f"R-free: {r_free:.4f}")
        if quality_parts:
            snippet_parts.append("Quality: " + ", ".join(quality_parts))

        # Molecule info
        if mol_names:
            names = mol_names if isinstance(mol_names, list) else [mol_names]
            snippet_parts.append(f"Molecules: {', '.join(names[:5])}")
        if mol_type:
            snippet_parts.append(f"Molecule type: {mol_type}")
        if organisms:
            org_list = organisms if isinstance(organisms, list) else [organisms]
            snippet_parts.append(f"Organisms: {', '.join(org_list[:3])}")

        # Ligand info
        if num_ligands is not None and num_ligands > 0:
            snippet_parts.append(f"Bound entities: {num_ligands}")
        elif isinstance(num_entities, dict) and num_entities.get("ligand", 0) > 0:
            snippet_parts.append(f"Ligands: {num_entities['ligand']}")

        # Assembly info from summary
        if assemblies:
            assembly = assemblies[0]
            assembly_name = assembly.get("name", "")
            assembly_form = assembly.get("form", "")
            if assembly_name or assembly_form:
                snippet_parts.append(f"Assembly: {assembly_name} ({assembly_form})")

        # Dates
        if deposition_date:
            dep_str = deposition_date[:10] if isinstance(deposition_date, str) else str(deposition_date)
            snippet_parts.append(f"Deposited: {dep_str}")
        if release_date:
            rel_str = release_date[:10] if isinstance(release_date, str) else str(release_date)
            snippet_parts.append(f"Released: {rel_str}")

        # Citation
        if citation_title:
            cite_parts = [citation_title]
            if citation_authors:
                auth_list = citation_authors if isinstance(citation_authors, list) else [citation_authors]
                auth_str = ", ".join(auth_list[:3])
                if len(auth_list) > 3:
                    auth_str += " et al."
                cite_parts.append(auth_str)
            snippet_parts.append(f"Citation: {'. '.join(cite_parts)}")

        has_content = bool(title or resolution is not None or method_str)
        return SourceCitation(
            source_name="pdbe",
            source_url=f"https://www.ebi.ac.uk/pdbe/entry/pdb/{pdb_id}",
            identifier=f"PDB:{pdb_id}",
            title=title or f"PDBe Structure {pdb_id}",
            snippet="\n".join(snippet_parts),
            quality_score=self.compute_quality_score("pdbe", has_content=has_content),
            retrieved_at=datetime.utcnow().isoformat(),
        )
