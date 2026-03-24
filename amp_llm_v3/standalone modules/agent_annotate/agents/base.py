"""
Abstract base classes for research and annotation agents.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

# Source reliability weights - used to compute quality scores
SOURCE_WEIGHTS = {
    "clinicaltrials_gov": 0.95,
    "openfda": 0.85,
    "pubmed": 0.90,
    "pmc": 0.85,
    "pmc_bioc": 0.80,
    "europe_pmc": 0.90,
    "semantic_scholar": 0.80,
    "uniprot": 0.95,
    "dramp": 0.80,
    "duckduckgo": 0.40,
    "dbaasp": 0.85,
    "chembl": 0.85,
    "rcsb_pdb": 0.80,
    "ebi_proteins": 0.85,
    "apd": 0.85,
    "who_ictrp": 0.80,
    "iuphar": 0.80,
    "pdbe": 0.80,
}

# How relevant each research agent is to each annotation field (0-1)
FIELD_RELEVANCE = {
    "classification": {
        "clinical_protocol": 0.95,
        "literature": 0.80,
        "peptide_identity": 0.80,
        "web_context": 0.50,
        "dbaasp": 0.90,
        "chembl": 0.70,
        "rcsb_pdb": 0.50,
        "ebi_proteins": 0.75,
        "apd": 0.90,
        "who_ictrp": 0.50,
        "iuphar": 0.80,
        "pdbe": 0.50,
    },
    "delivery_mode": {
        "clinical_protocol": 0.90,
        "literature": 0.85,
        "peptide_identity": 0.40,
        "web_context": 0.45,
        "dbaasp": 0.20,
        "chembl": 0.40,
        "rcsb_pdb": 0.15,
        "ebi_proteins": 0.20,
        "apd": 0.15,
        "who_ictrp": 0.60,
        "iuphar": 0.30,
        "pdbe": 0.15,
    },
    "outcome": {
        "clinical_protocol": 0.90,
        "literature": 0.75,
        "peptide_identity": 0.20,
        "web_context": 0.60,
        "dbaasp": 0.30,
        "chembl": 0.50,
        "rcsb_pdb": 0.20,
        "ebi_proteins": 0.25,
        "apd": 0.25,
        "who_ictrp": 0.70,
        "iuphar": 0.30,
        "pdbe": 0.15,
    },
    "reason_for_failure": {
        "clinical_protocol": 0.60,
        "literature": 0.70,
        "peptide_identity": 0.15,
        "web_context": 0.80,
        "dbaasp": 0.15,
        "chembl": 0.30,
        "rcsb_pdb": 0.10,
        "ebi_proteins": 0.15,
        "apd": 0.10,
        "who_ictrp": 0.50,
        "iuphar": 0.15,
        "pdbe": 0.10,
    },
    "peptide": {
        "clinical_protocol": 0.50,
        "literature": 0.75,
        "peptide_identity": 0.95,
        "web_context": 0.40,
        "dbaasp": 0.95,
        "chembl": 0.85,
        "rcsb_pdb": 0.90,
        "ebi_proteins": 0.95,
        "apd": 0.95,
        "who_ictrp": 0.30,
        "iuphar": 0.85,
        "pdbe": 0.85,
    },
    "sequence": {
        "clinical_protocol": 0.10,
        "literature": 0.30,
        "peptide_identity": 0.95,
        "web_context": 0.15,
        "dbaasp": 0.90,
        "chembl": 0.60,
        "rcsb_pdb": 0.85,
        "ebi_proteins": 0.95,
        "apd": 0.90,
        "who_ictrp": 0.10,
        "iuphar": 0.40,
        "pdbe": 0.80,
    },
}


class BaseResearchAgent(ABC):
    """Abstract base class for all research agents."""

    agent_name: str = "base"
    sources: list[str] = []

    @abstractmethod
    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        """Execute research for a given NCT ID and return structured results."""
        ...

    def compute_quality_score(self, source_name: str, has_content: bool = True) -> float:
        """Compute a quality score for a citation based on source reliability."""
        base = SOURCE_WEIGHTS.get(source_name, 0.5)
        if not has_content:
            base *= 0.5
        return round(min(base, 1.0), 3)


class BaseAnnotationAgent(ABC):
    """Abstract base class for annotation agents (LLM-driven field annotators)."""

    field_name: str = "base"

    @abstractmethod
    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        """Produce an annotation for self.field_name using gathered research."""
        ...

    def relevance_weight(self, agent_name: str) -> float:
        """How relevant a given research agent is to this annotation field."""
        return FIELD_RELEVANCE.get(self.field_name, {}).get(agent_name, 0.5)

    async def get_edam_guidance(self, nct_id: str,
                                evidence_text: str) -> str:
        """Retrieve EDAM guidance block for this annotation call.

        Returns a formatted guidance string to prepend to the LLM prompt,
        or empty string if EDAM is unavailable or has no relevant memories.
        EDAM failures are never fatal.
        """
        try:
            from app.services.memory import memory_store
            return await memory_store.build_guidance(
                nct_id=nct_id,
                field_name=self.field_name,
                evidence_text=evidence_text,
            )
        except Exception:
            return ""

    def build_structured_evidence(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        max_citations: int = 30,
        max_snippet_chars: int = 250,
    ) -> tuple[str, list[SourceCitation]]:
        """Build structured, section-grouped evidence text for LLM consumption.

        Instead of dumping all citations in a flat weight-sorted list, this
        organizes evidence into labeled sections that match how annotation
        agents need to reason about the data. This helps 8B models find
        the right information without scanning through irrelevant citations.

        Returns (evidence_text, cited_sources_list).
        """
        # Collect citations grouped by semantic category
        sections: dict[str, list[tuple[SourceCitation, float]]] = {
            "TRIAL METADATA": [],       # ClinicalTrials.gov, WHO ICTRP, OpenFDA
            "PUBLISHED RESULTS": [],     # PubMed, PMC, Europe PMC
            "DRUG/PEPTIDE DATA": [],     # ChEMBL, UniProt, DRAMP, IUPHAR
            "ANTIMICROBIAL DATA": [],    # DBAASP, APD
            "STRUCTURAL DATA": [],       # RCSB PDB, PDBe, EBI Proteins
            "WEB SOURCES": [],           # DuckDuckGo
        }

        _SOURCE_TO_SECTION = {
            "clinicaltrials_gov": "TRIAL METADATA",
            "who_ictrp": "TRIAL METADATA",
            "pubmed": "PUBLISHED RESULTS",
            "pmc": "PUBLISHED RESULTS",
            "pmc_bioc": "PUBLISHED RESULTS",
            "europe_pmc": "PUBLISHED RESULTS",
            "semantic_scholar": "PUBLISHED RESULTS",
            "chembl": "DRUG/PEPTIDE DATA",
            "uniprot": "DRUG/PEPTIDE DATA",
            "dramp": "DRUG/PEPTIDE DATA",
            "iuphar": "DRUG/PEPTIDE DATA",
            "dbaasp": "ANTIMICROBIAL DATA",
            "apd": "ANTIMICROBIAL DATA",
            "rcsb_pdb": "STRUCTURAL DATA",
            "pdbe": "STRUCTURAL DATA",
            "ebi_proteins": "STRUCTURAL DATA",
            "duckduckgo": "WEB SOURCES",
            "openfda": "TRIAL METADATA",
        }

        # Extract intervention names for relevance filtering
        _intervention_names: set[str] = set()
        for result in research_results:
            if result.agent_name == "clinical_protocol" and result.raw_data:
                protocol = result.raw_data.get("protocol_section", {})
                arms_mod = protocol.get("armsInterventionsModule", {})
                for interv in arms_mod.get("interventions", []):
                    name = interv.get("name", "")
                    if name:
                        _intervention_names.add(name.lower())

        def _is_relevant_to_trial(citation: SourceCitation) -> bool:
            """Check if a database result is actually about our intervention
            rather than a fuzzy text-search false positive.

            IntAct searching "Peptide T" returned CFTR, MAPT, HTT — generic
            high-connectivity proteins with no relation to the trial. IUPHAR
            searching "Peptide T" returned GLP-1, PYY — different peptides.
            This filter catches those by checking if the citation mentions
            any of the actual intervention names.
            """
            # Always keep trial metadata and published results — they're NCT-specific
            section = _SOURCE_TO_SECTION.get(citation.source_name, "")
            if section in ("TRIAL METADATA", "PUBLISHED RESULTS"):
                return True
            # For database results, check relevance
            if not _intervention_names:
                return True  # No names to filter against
            snippet_lower = (citation.snippet or "").lower()
            title_lower = (citation.title or "").lower()
            ident_lower = (citation.identifier or "").lower()
            combined = f"{snippet_lower} {title_lower} {ident_lower}"
            return any(name in combined for name in _intervention_names)

        for result in research_results:
            weight = self.relevance_weight(result.agent_name)
            for citation in result.citations:
                section = _SOURCE_TO_SECTION.get(
                    citation.source_name, "WEB SOURCES"
                )
                sections[section].append((citation, weight))

        # Sort within each section by weight, then truncate
        for section in sections.values():
            section.sort(key=lambda x: x[1], reverse=True)

        # Deduplicate and filter low-value citations
        seen_snippets: set[str] = set()

        def _is_duplicate(citation: SourceCitation) -> bool:
            key = (citation.snippet or "")[:60].lower()
            if key in seen_snippets:
                return True
            seen_snippets.add(key)
            return False

        def _is_noise(citation: SourceCitation) -> bool:
            """Filter out citations that waste LLM tokens without adding
            information: negative search results, empty JSON responses,
            irrelevant fuzzy matches from broad text searches."""
            snippet = (citation.snippet or "").lower()

            # Negative search results — searched but found nothing useful
            if "no exact match" in snippet or "no results found" in snippet:
                return True
            if "searched: true" in snippet and "found: false" in snippet:
                return True

            # Empty or near-empty snippets
            if len(snippet.strip()) < 15:
                return True

            # JSON/dict artifacts that leaked into snippets
            if snippet.count("{") > 3 or snippet.count("[") > 4:
                return True

            return False

        # Build text with section headers, budget-limited per section.
        # Budgets scale with max_citations so server profile (50 cites)
        # gets proportionally more per section than mac_mini (20-30).
        budget_per_section = {
            "TRIAL METADATA": max(max_citations // 3, 6),
            "PUBLISHED RESULTS": max(max_citations // 4, 5),
            "DRUG/PEPTIDE DATA": max(max_citations // 4, 4),
            "ANTIMICROBIAL DATA": max(max_citations // 6, 3),
            "STRUCTURAL DATA": max(max_citations // 8, 2),
            "WEB SOURCES": max(max_citations // 10, 2),
        }

        lines = [f"Trial: {nct_id}\n"]
        cited_sources: list[SourceCitation] = []
        total_used = 0

        for section_name in [
            "TRIAL METADATA",
            "PUBLISHED RESULTS",
            "DRUG/PEPTIDE DATA",
            "ANTIMICROBIAL DATA",
            "STRUCTURAL DATA",
            "WEB SOURCES",
        ]:
            cites = sections[section_name]
            if not cites:
                continue

            budget = budget_per_section.get(section_name, 3)
            if total_used >= max_citations:
                break

            section_lines = []
            section_count = 0
            for citation, _ in cites:
                if section_count >= budget or total_used >= max_citations:
                    break
                if _is_noise(citation) or _is_duplicate(citation):
                    continue
                if not _is_relevant_to_trial(citation):
                    continue
                # Truncate long snippets to keep total evidence compact
                snippet = citation.snippet or ""
                if len(snippet) > max_snippet_chars:
                    snippet = snippet[:max_snippet_chars].rsplit(" ", 1)[0] + "..."
                line = (
                    f"[{citation.source_name}] "
                    f"{citation.identifier or ''}: "
                    f"{snippet}"
                )
                section_lines.append(line)
                cited_sources.append(citation)
                section_count += 1
                total_used += 1

            if section_lines:
                lines.append(f"\n=== {section_name} ===")
                lines.extend(section_lines)

        evidence_text = "\n".join(lines)
        return evidence_text, cited_sources
