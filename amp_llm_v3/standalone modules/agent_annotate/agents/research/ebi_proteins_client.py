"""
EBI Proteins API Research Agent.

Queries the EBI Proteins API (https://www.ebi.ac.uk/proteins/api/),
backed by UniProt, for protein/peptide data including sequences,
ClinVar/COSMIC variants, domain annotations, and function descriptions.
"""

from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.drug_cache import drug_cache
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

EBI_PROTEINS_BASE = "https://www.ebi.ac.uk/proteins/api"
EBI_PROTEINS_URL = f"{EBI_PROTEINS_BASE}/proteins"
EBI_VARIATION_URL = f"{EBI_PROTEINS_BASE}/variation"


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


class EBIProteinsClient(BaseResearchAgent):
    """Queries EBI Proteins API for sequences, variants, and annotations."""

    agent_name = "ebi_proteins"
    sources = ["ebi_proteins"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Extract intervention names to search for proteins/peptides
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
        """Fetch EBI Proteins data for one intervention. Pure function of intervention name."""
        citations: list = []
        raw_data: dict = {}
        # 1. Search proteins by name
        try:
            resp = await resilient_get(
                EBI_PROTEINS_URL,
                client=client,
                params={
                    "offset": 0,
                    "size": 5,
                    "protein": intervention,
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                proteins = resp.json()
                if not isinstance(proteins, list):
                    proteins = [proteins] if proteins else []

                raw_data[f"ebi_proteins_{intervention}_count"] = len(proteins)

                # v14: Store structured entries in raw_data for the
                # sequence agent (sequence removed from snippets)
                ebi_entries = []

                for entry in proteins[:3]:
                    if not isinstance(entry, dict):
                        continue

                    accession = entry.get("accession", "")
                    protein_obj = entry.get("protein", {}) or {}

                    # Extract protein name
                    rec_name = protein_obj.get("recommendedName", {}) or {}
                    full_name = rec_name.get("fullName", {}) or {}
                    protein_name = full_name.get("value", "")
                    if not protein_name:
                        # Try submittedName fallback
                        sub_names = protein_obj.get("submittedName", [])
                        if isinstance(sub_names, list) and sub_names:
                            protein_name = sub_names[0].get("fullName", {}).get("value", "")

                    # Extract organism
                    organism_obj = entry.get("organism", {}) or {}
                    organism_names = organism_obj.get("names", [])
                    organism = ""
                    if isinstance(organism_names, list):
                        for n in organism_names:
                            if isinstance(n, dict) and n.get("type") == "scientific":
                                organism = n.get("value", "")
                                break

                    # Extract sequence
                    sequence_obj = entry.get("sequence", {}) or {}
                    sequence = sequence_obj.get("sequence", "")
                    seq_length = sequence_obj.get("length", "")
                    seq_mass = sequence_obj.get("mass", "")

                    # Extract function from comments
                    function_text = ""
                    comments = entry.get("comments", [])
                    if isinstance(comments, list):
                        for comment in comments:
                            if isinstance(comment, dict) and comment.get("type") == "FUNCTION":
                                texts = comment.get("text", [])
                                if isinstance(texts, list) and texts:
                                    func_entry = texts[0]
                                    if isinstance(func_entry, dict):
                                        function_text = func_entry.get("value", "")
                                    elif isinstance(func_entry, str):
                                        function_text = func_entry
                                break

                    # Extract domain annotations from features
                    domains = []
                    features = entry.get("features", [])
                    if isinstance(features, list):
                        for feat in features:
                            if isinstance(feat, dict) and feat.get("type") in ("DOMAIN", "REGION", "MOTIF"):
                                desc = feat.get("description", "")
                                if desc:
                                    domains.append(desc)

                    # v14: Store structured entry for sequence agent
                    ebi_entries.append({
                        "accession": accession,
                        "protein_name": protein_name,
                        "sequence": sequence,
                        "seq_length": seq_length,
                        "features": [
                            f for f in (features if isinstance(features, list) else [])
                            if isinstance(f, dict) and f.get("type") in ("CHAIN", "PEPTIDE", "Chain", "Peptide")
                        ],
                    })

                    # v27c: Extract mature chain info from CHAIN/PEPTIDE features
                    mature_chains = []
                    if isinstance(features, list):
                        for feat in features:
                            if isinstance(feat, dict) and feat.get("type") in ("CHAIN", "PEPTIDE", "Chain", "Peptide"):
                                loc = feat.get("location", {})
                                start = loc.get("start", {}).get("value") if isinstance(loc.get("start"), dict) else None
                                end = loc.get("end", {}).get("value") if isinstance(loc.get("end"), dict) else None
                                desc = feat.get("description", "")
                                if start is not None and end is not None:
                                    chain_len = int(end) - int(start) + 1
                                    mature_chains.append((desc, chain_len))

                    # v14: Snippet no longer contains sequence characters
                    # to prevent Phase 4 re-extraction of precursor proteins.
                    snippet_parts = [f"Protein: {protein_name or accession}"]
                    if organism:
                        snippet_parts.append(f"Organism: {organism}")
                    if mature_chains:
                        total_mature = sum(cl for _, cl in mature_chains)
                        chain_desc = ", ".join(f"{d} {cl} aa" for d, cl in mature_chains)
                        snippet_parts.append(f"Precursor length: {seq_length} aa")
                        snippet_parts.append(f"Mature form: {chain_desc} ({total_mature} aa total)")
                    elif seq_length:
                        snippet_parts.append(f"Length: {seq_length} aa")
                    if seq_mass:
                        snippet_parts.append(f"Mass: {seq_mass} Da")
                    if function_text:
                        snippet_parts.append(f"Function: {function_text[:300]}")
                    if domains:
                        snippet_parts.append(f"Domains: {', '.join(domains[:5])}")

                    citations.append(SourceCitation(
                        source_name="ebi_proteins",
                        source_url=f"https://www.ebi.ac.uk/proteins/api/proteins/{accession}" if accession else "https://www.ebi.ac.uk/proteins/api/",
                        identifier=accession or protein_name,
                        title=f"{protein_name or accession} - EBI Proteins",
                        snippet="\n".join(snippet_parts),
                        quality_score=self.compute_quality_score("ebi_proteins"),
                        retrieved_at=datetime.utcnow().isoformat(),
                    ))

                    # 2. Fetch variation data if we have an accession
                    if accession:
                        await self._fetch_variation(
                            client, accession, protein_name, citations, raw_data
                        )

                # v14: Store structured entries in raw_data
                if ebi_entries:
                    raw_data[f"ebi_proteins_{intervention}_entries"] = ebi_entries

            else:
                raw_data[f"ebi_proteins_{intervention}_status"] = resp.status_code

        except Exception as e:
            raw_data[f"ebi_proteins_{intervention}_error"] = str(e)

        return {"citations": citations, "raw_data": raw_data}

    async def _fetch_variation(
        self,
        client: httpx.AsyncClient,
        accession: str,
        protein_name: str,
        citations: list[SourceCitation],
        raw_data: dict,
    ) -> None:
        """Fetch ClinVar/COSMIC variant data for a protein accession."""
        try:
            resp = await resilient_get(
                f"{EBI_VARIATION_URL}/{accession}",
                client=client,
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])
                if not isinstance(features, list):
                    features = []

                raw_data[f"ebi_variation_{accession}_count"] = len(features)

                # Summarize variants by source (ClinVar, COSMIC, etc.)
                clinvar_variants = []
                cosmic_variants = []
                other_variants = []

                for feat in features[:50]:
                    if not isinstance(feat, dict):
                        continue
                    xrefs = feat.get("xrefs", [])
                    description = feat.get("description", "")
                    consequence = feat.get("consequenceType", "")
                    clinical_sig = ""

                    for xref in (xrefs if isinstance(xrefs, list) else []):
                        if isinstance(xref, dict):
                            db = xref.get("name", "").lower()
                            if "clinvar" in db:
                                clinvar_variants.append(f"{description} ({consequence})" if description else consequence)
                                break
                            elif "cosmic" in db:
                                cosmic_variants.append(f"{description} ({consequence})" if description else consequence)
                                break
                    else:
                        if description or consequence:
                            other_variants.append(f"{description} ({consequence})" if description else consequence)

                if clinvar_variants or cosmic_variants:
                    variant_parts = [f"Variants for {protein_name or accession}:"]
                    if clinvar_variants:
                        variant_parts.append(f"ClinVar: {len(clinvar_variants)} variants - {', '.join(clinvar_variants[:3])}")
                    if cosmic_variants:
                        variant_parts.append(f"COSMIC: {len(cosmic_variants)} variants - {', '.join(cosmic_variants[:3])}")

                    citations.append(SourceCitation(
                        source_name="ebi_proteins",
                        source_url=f"https://www.ebi.ac.uk/proteins/api/variation/{accession}",
                        identifier=f"{accession}_variants",
                        title=f"Variants for {protein_name or accession} - EBI Proteins",
                        snippet="\n".join(variant_parts),
                        quality_score=self.compute_quality_score("ebi_proteins"),
                        retrieved_at=datetime.utcnow().isoformat(),
                    ))

        except Exception as e:
            raw_data[f"ebi_variation_{accession}_error"] = str(e)
