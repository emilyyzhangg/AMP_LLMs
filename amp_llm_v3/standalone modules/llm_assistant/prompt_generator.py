"""
Prompt Generator for Clinical Trial Analysis
============================================

Generates LLM prompts from API search results for structured data extraction.
"""
import json
from typing import Dict, Any, List, Optional
from pathlib import Path


class PromptGenerator:
    """
    Generate LLM prompts from clinical trial search results.
    """
    
    def __init__(self):
        """Initialize prompt generator."""
        self.modelfile_template = self._load_modelfile_template()
    
    def _load_modelfile_template(self) -> str:
        """Load the Modelfile template."""
        return """# Clinical Trial Research Assistant Modelfile Template

FROM llama3.2

SYSTEM \"\"\"You are a Clinical Trial Data Extraction Specialist. Extract structured information from clinical trial JSON data.

## OUTPUT FORMAT

Format your response EXACTLY like this (use actual data, NOT placeholders):

NCT Number: NCT07013110
Study Title: An Artificial Intelligence-powered Approach to Precision Immunotherapy
Study Status: RECRUITING
Brief Summary: This clinical study is a multi-center, randomized study...
Conditions: Rheumatoid Arthritis, Rheumatology
Interventions/Drug: Biological: dnaJP1, Other: Hydroxychloroquine, Placebo
Phases: PHASE2
Enrollment: 124
Start Date: 2025-06-18
Completion Date: 2028-11
Classification: AMP

  Evidence: Study involves antimicrobial peptide for non-infection purposes
Delivery Mode: Oral
Sequence: FVQWFSKFLGKIEPDVSQVQDPNDYEPF
DRAMP Name: dnaJP1

  Evidence: DRAMP database entry for dnaJP1
Study IDs: PMC:11855921
Outcome: Recruiting
Reason for Failure: N/A
Subsequent Trial IDs: N/A

  Evidence: N/A
Peptide: True
Comments: Early-phase trial investigating immunotherapy effects

## CRITICAL RULES

1. Use ACTUAL data from the trial, NOT placeholder text like [title here] or [PHASE#]
2. Do NOT wrap response in markdown code blocks (no ```)
3. Write values directly without brackets [ ]
4. For missing data, write exactly: N/A
5. Use EXACT values from validation lists below

## VALID VALUES

<!-- VALIDATION_RULES_PLACEHOLDER -->

## EXTRACTION GUIDELINES

**Status to Outcome mapping:**
<!-- OUTCOME_MAPPING_PLACEHOLDER -->

**Peptide detection:**
Look for:
<!-- PEPTIDE_KEYWORDS_PLACEHOLDER -->

**Classification logic:**
- If antimicrobial peptide → AMP
- If a peptide but not an antimicrobial peptide → Other

**DO NOT:**
- Use placeholder text like [title here], [PHASE#], [condition1, condition2]
- Wrap output in code blocks
- Include brackets in actual data
- Leave fields blank (use N/A instead)

**DO:**
- Extract actual values from the JSON
- Write values directly without formatting
- Use exact validation list values
- Provide clear evidence for classifications

Now extract the clinical trial data following this exact format with actual data.\"\"\"

# Optimized parameters
PARAMETER temperature 0.15
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER repeat_penalty 1.2
PARAMETER num_ctx 8192
PARAMETER num_predict 2048

# Stop sequences
PARAMETER stop "<|eot_id|>"
PARAMETER stop "<|end_of_text|>"
PARAMETER stop "</s>"
"""
    
    def generate_extraction_prompt(
        self,
        search_results: Dict[str, Any],
        nct_id: str
    ) -> str:
        """
        Generate extraction prompt from search results.
        
        Args:
            search_results: Complete search results from NCTSearchEngine
            nct_id: NCT number
            
        Returns:
            Formatted prompt for LLM extraction
        """
        sections = []
        
        # Add header
        sections.append(f"# Clinical Trial Data Extraction: {nct_id}")
        sections.append("\nExtract structured information from the following data sources:\n")
        
        # Section 1: ClinicalTrials.gov Data
        ct_data = self._format_clinical_trials_data(search_results)
        if ct_data:
            sections.append("## 1. ClinicalTrials.gov Data")
            sections.append(ct_data)
        
        # Section 2: PubMed Articles
        pubmed_data = self._format_pubmed_data(search_results)
        if pubmed_data:
            sections.append("\n## 2. PubMed Literature")
            sections.append(pubmed_data)
        
        # Section 3: PMC Full-Text Articles
        pmc_data = self._format_pmc_data(search_results)
        if pmc_data:
            sections.append("\n## 3. PubMed Central Articles")
            sections.append(pmc_data)
        
        # Section 4: PMC BioC Data
        bioc_data = self._format_bioc_data(search_results)
        if bioc_data:
            sections.append("\n## 4. BioC Annotated Data")
            sections.append(bioc_data)
        
        # Section 5: Extended API Data (if available)
        extended_data = self._format_extended_data(search_results)
        if extended_data:
            sections.append("\n## 5. Extended Web & Database Search")
            sections.append(extended_data)
        
        # Add extraction instructions
        sections.append("\n## EXTRACTION TASK")
        sections.append("""
Using ALL the data above, extract the clinical trial information following the exact format specified in your system prompt.

CRITICAL REMINDERS:
- Use ACTUAL data from above, NOT placeholders
- For missing information, write exactly: N/A
- Use exact validation list values
- Provide evidence for classifications
- Do NOT wrap response in code blocks

Begin extraction now:
""")
        
        return "\n".join(sections)
    
    def _format_clinical_trials_data(self, results: Dict[str, Any]) -> str:
        """Format ClinicalTrials.gov data."""
        ct_source = results.get("sources", {}).get("clinical_trials", {})
        
        if not ct_source.get("success"):
            return "Clinical trial data not available."
        
        ct_data = ct_source.get("data", {})
        protocol = ct_data.get("protocolSection", {})
        
        lines = []
        
        # Identification
        ident = protocol.get("identificationModule", {})
        lines.append(f"**NCT ID:** {ident.get('nctId', 'N/A')}")
        lines.append(f"**Title:** {ident.get('officialTitle') or ident.get('briefTitle', 'N/A')}")
        lines.append(f"**Brief Title:** {ident.get('briefTitle', 'N/A')}")
        
        # Status
        status_mod = protocol.get("statusModule", {})
        lines.append(f"**Overall Status:** {status_mod.get('overallStatus', 'N/A')}")
        lines.append(f"**Start Date:** {status_mod.get('startDateStruct', {}).get('date', 'N/A')}")
        lines.append(f"**Completion Date:** {status_mod.get('completionDateStruct', {}).get('date', 'N/A')}")
        
        # Description
        desc_mod = protocol.get("descriptionModule", {})
        brief_summary = desc_mod.get("briefSummary", "N/A")
        if len(brief_summary) > 500:
            brief_summary = brief_summary[:500] + "..."
        lines.append(f"**Brief Summary:** {brief_summary}")
        
        # Conditions
        cond_mod = protocol.get("conditionsModule", {})
        conditions = cond_mod.get("conditions", [])
        lines.append(f"**Conditions:** {', '.join(conditions) if conditions else 'N/A'}")
        
        # Interventions
        arms_int = protocol.get("armsInterventionsModule", {})
        interventions = arms_int.get("interventions", [])
        if interventions:
            int_strings = []
            for intv in interventions[:5]:  # Limit to 5
                int_type = intv.get("type", "")
                int_name = intv.get("name", "")
                int_strings.append(f"{int_type}: {int_name}")
            lines.append(f"**Interventions:** {', '.join(int_strings)}")
        else:
            lines.append("**Interventions:** N/A")
        
        # Design
        design_mod = protocol.get("designModule", {})
        phases = design_mod.get("phases", [])
        lines.append(f"**Phases:** {', '.join(phases) if phases else 'N/A'}")
        
        enrollment_info = design_mod.get("enrollmentInfo", {})
        lines.append(f"**Enrollment:** {enrollment_info.get('count', 'N/A')}")
        
        # References
        refs_mod = protocol.get("referencesModule", {})
        references = refs_mod.get("references", [])
        if references:
            lines.append("\n**References:**")
            for i, ref in enumerate(references[:5], 1):
                pmid = ref.get("pmid", "")
                citation = ref.get("citation", "")
                if pmid:
                    lines.append(f"  {i}. PMID: {pmid}")
                if citation:
                    lines.append(f"     {citation[:200]}...")
        
        return "\n".join(lines)
    
    def _format_pubmed_data(self, results: Dict[str, Any]) -> str:
        """Format PubMed data."""
        pubmed_source = results.get("sources", {}).get("pubmed", {})
        
        if not pubmed_source.get("success"):
            return "PubMed data not available."
        
        pubmed_data = pubmed_source.get("data", {})
        articles = pubmed_data.get("articles", [])
        
        if not articles:
            return "No PubMed articles found."
        
        lines = []
        lines.append(f"**Total Articles Found:** {pubmed_data.get('total_found', 0)}")
        lines.append(f"**Search Strategy:** {pubmed_data.get('search_strategy', 'N/A')}\n")
        
        for i, article in enumerate(articles[:5], 1):  # Limit to 5
            lines.append(f"### Article {i}")
            lines.append(f"**PMID:** {article.get('pmid', 'N/A')}")
            lines.append(f"**Title:** {article.get('title', 'N/A')}")
            lines.append(f"**Journal:** {article.get('journal', 'N/A')}")
            lines.append(f"**Year:** {article.get('year', 'N/A')}")
            
            authors = article.get("authors", [])
            if authors:
                lines.append(f"**Authors:** {', '.join(authors[:3])}")
            
            abstract = article.get("abstract", "")
            if abstract:
                if len(abstract) > 500:
                    abstract = abstract[:500] + "..."
                lines.append(f"**Abstract:** {abstract}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_pmc_data(self, results: Dict[str, Any]) -> str:
        """Format PMC data."""
        pmc_source = results.get("sources", {}).get("pmc", {})
        
        if not pmc_source.get("success"):
            return "PMC data not available."
        
        pmc_data = pmc_source.get("data", {})
        articles = pmc_data.get("articles", [])
        
        if not articles:
            return "No PMC articles found."
        
        lines = []
        lines.append(f"**Total Articles Found:** {pmc_data.get('total_found', 0)}")
        lines.append(f"**Search Strategy:** {pmc_data.get('search_strategy', 'N/A')}\n")
        
        for i, article in enumerate(articles[:5], 1):
            lines.append(f"### PMC Article {i}")
            lines.append(f"**PMCID:** {article.get('pmcid', 'N/A')}")
            lines.append(f"**PMID:** {article.get('pmid', 'N/A')}")
            lines.append(f"**Title:** {article.get('title', 'N/A')}")
            lines.append(f"**Journal:** {article.get('journal', 'N/A')}")
            lines.append(f"**Year:** {article.get('year', 'N/A')}")
            
            abstract = article.get("abstract", "")
            if abstract:
                if len(abstract) > 500:
                    abstract = abstract[:500] + "..."
                lines.append(f"**Abstract:** {abstract}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_bioc_data(self, results: Dict[str, Any]) -> str:
        """Format BioC data with key annotations."""
        bioc_source = results.get("sources", {}).get("pmc_bioc", {})
        
        if not bioc_source.get("success"):
            return "BioC data not available."
        
        bioc_data = bioc_source.get("data", {})
        articles = bioc_data.get("articles", [])
        
        if not articles:
            return "No BioC annotated articles found."
        
        lines = []
        lines.append(f"**Total BioC Articles:** {bioc_data.get('total_fetched', 0)}/{bioc_data.get('total_found', 0)}")
        lines.append(f"**Sources:** PubMed: {bioc_data.get('sources', {}).get('pubmed', 0)}, PMC: {bioc_data.get('sources', {}).get('pmc', 0)}\n")
        
        for i, article in enumerate(articles[:3], 1):  # Limit to 3 due to size
            lines.append(f"### BioC Article {i}")
            lines.append(f"**ID:** {article.get('pmid', 'N/A')}")
            
            bioc_content = article.get("bioc_data", {})
            
            # Extract collection info
            collection = bioc_content.get("collection", {})
            if collection:
                lines.append(f"**Source:** {collection.get('source', 'N/A')}")
            
            # Extract document info
            documents = bioc_content.get("documents", [])
            if documents:
                doc = documents[0]
                
                # Get passages with annotations
                passages = doc.get("passages", [])
                if passages:
                    lines.append("\n**Key Content:**")
                    
                    for j, passage in enumerate(passages[:3], 1):
                        passage_type = passage.get("infons", {}).get("type", "text")
                        text = passage.get("text", "")
                        
                        if text and len(text) > 300:
                            text = text[:300] + "..."
                        
                        if text:
                            lines.append(f"\n*{passage_type.title()}:*")
                            lines.append(text)
                        
                        # Show annotations if present
                        annotations = passage.get("annotations", [])
                        if annotations:
                            lines.append("\n*Annotations:*")
                            for ann in annotations[:5]:  # Limit to 5
                                ann_type = ann.get("infons", {}).get("type", "")
                                ann_text = ann.get("text", "")
                                if ann_type and ann_text:
                                    lines.append(f"  - {ann_type}: {ann_text}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_extended_data(self, results: Dict[str, Any]) -> str:
        """Format extended API search data (DuckDuckGo, SERP, Scholar, OpenFDA)."""
        extended_source = results.get("sources", {}).get("extended", {})
        
        if not extended_source:
            return ""
        
        lines = []
        has_data = False
        
        # DuckDuckGo Web Search
        ddg = extended_source.get("duckduckgo", {})
        if ddg.get("success"):
            has_data = True
            ddg_data = ddg.get("data", {})
            ddg_results = ddg_data.get("results", [])
            
            lines.append("### DuckDuckGo Web Search")
            lines.append(f"**Total Results:** {ddg_data.get('total_found', 0)}")
            lines.append(f"**Query:** {ddg_data.get('query', 'N/A')}\n")
            
            for i, result in enumerate(ddg_results[:5], 1):
                lines.append(f"**Result {i}:**")
                lines.append(f"  Title: {result.get('title', 'N/A')}")
                lines.append(f"  URL: {result.get('url', 'N/A')}")
                snippet = result.get('snippet', '')
                if snippet:
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
                    lines.append(f"  Snippet: {snippet}")
                lines.append("")
        
        # Google Search (SERP API)
        serp = extended_source.get("serpapi", {})
        if serp.get("success"):
            has_data = True
            serp_data = serp.get("data", {})
            serp_results = serp_data.get("results", [])
            
            lines.append("\n### Google Search Results")
            lines.append(f"**Total Results:** {serp_data.get('total_found', 0)}")
            lines.append(f"**Query:** {serp_data.get('query', 'N/A')}\n")
            
            for i, result in enumerate(serp_results[:5], 1):
                lines.append(f"**Result {i}:**")
                lines.append(f"  Title: {result.get('title', 'N/A')}")
                lines.append(f"  URL: {result.get('url', 'N/A')}")
                snippet = result.get('snippet', '')
                if snippet:
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
                    lines.append(f"  Snippet: {snippet}")
                lines.append("")
        
        # Google Scholar
        scholar = extended_source.get("scholar", {})
        if scholar.get("success"):
            has_data = True
            scholar_data = scholar.get("data", {})
            scholar_results = scholar_data.get("results", [])
            
            lines.append("\n### Google Scholar Results")
            lines.append(f"**Total Results:** {scholar_data.get('total_found', 0)}")
            lines.append(f"**Query:** {scholar_data.get('query', 'N/A')}\n")
            
            for i, result in enumerate(scholar_results[:5], 1):
                lines.append(f"**Result {i}:**")
                lines.append(f"  Title: {result.get('title', 'N/A')}")
                lines.append(f"  URL: {result.get('url', 'N/A')}")
                
                cited_by = result.get('cited_by')
                if cited_by:
                    lines.append(f"  Cited by: {cited_by}")
                
                snippet = result.get('snippet', '')
                if snippet:
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
                    lines.append(f"  Snippet: {snippet}")
                lines.append("")
        
        # OpenFDA Drug Database
        openfda = extended_source.get("openfda", {})
        if openfda.get("success"):
            has_data = True
            fda_data = openfda.get("data", {})
            fda_results = fda_data.get("results", [])
            
            lines.append("\n### OpenFDA Drug Database")
            lines.append(f"**Total Results:** {fda_data.get('total_found', 0)}")
            lines.append(f"**Query:** {fda_data.get('query', 'N/A')}\n")
            
            for i, result in enumerate(fda_results[:3], 1):  # Limit to 3 due to size
                lines.append(f"**Drug {i}:**")
                
                # OpenFDA structure
                openfda_info = result.get("openfda", {})
                
                # Brand and generic names
                brand_names = openfda_info.get("brand_name", [])
                if brand_names:
                    lines.append(f"  Brand Name(s): {', '.join(brand_names[:3])}")
                
                generic_names = openfda_info.get("generic_name", [])
                if generic_names:
                    lines.append(f"  Generic Name(s): {', '.join(generic_names[:3])}")
                
                # Manufacturer
                manufacturers = openfda_info.get("manufacturer_name", [])
                if manufacturers:
                    lines.append(f"  Manufacturer: {manufacturers[0]}")
                
                # Product type
                product_types = openfda_info.get("product_type", [])
                if product_types:
                    lines.append(f"  Product Type: {', '.join(product_types)}")
                
                # Route
                routes = openfda_info.get("route", [])
                if routes:
                    lines.append(f"  Route: {', '.join(routes[:3])}")
                
                # Indications (if available)
                indications = result.get("indications_and_usage", [])
                if indications and isinstance(indications, list) and len(indications) > 0:
                    indication_text = indications[0]
                    if len(indication_text) > 400:
                        indication_text = indication_text[:400] + "..."
                    lines.append(f"  Indications: {indication_text}")
                
                # Warnings (if available)
                warnings = result.get("warnings", [])
                if warnings and isinstance(warnings, list) and len(warnings) > 0:
                    warning_text = warnings[0]
                    if len(warning_text) > 300:
                        warning_text = warning_text[:300] + "..."
                    lines.append(f"  Warnings: {warning_text}")
                
                lines.append("")
        
        if not has_data:
            return ""
        
        return "\n".join(lines)
    
    def generate_rag_query_prompt(
        self,
        query: str,
        search_results: Dict[str, Any]
    ) -> str:
        """
        Generate RAG-style prompt for answering queries.
        
        Args:
            query: User's question
            search_results: Search results context
            
        Returns:
            Formatted prompt for LLM
        """
        sections = []
        
        sections.append("# Clinical Trial Research Query")
        sections.append(f"\n**User Question:** {query}\n")
        
        sections.append("## Available Data\n")
        
        # Add condensed data from all sources
        ct_data = self._format_clinical_trials_data(search_results)
        if ct_data:
            sections.append("### ClinicalTrials.gov")
            sections.append(ct_data)
        
        pubmed_data = self._format_pubmed_data(search_results)
        if pubmed_data:
            sections.append("\n### PubMed Literature")
            sections.append(pubmed_data)
        
        pmc_data = self._format_pmc_data(search_results)
        if pmc_data:
            sections.append("\n### PMC Articles")
            sections.append(pmc_data)
        
        bioc_data = self._format_bioc_data(search_results)
        if bioc_data:
            sections.append("\n### BioC Annotations")
            sections.append(bioc_data)
        
        # Add extended data if available
        extended_data = self._format_extended_data(search_results)
        if extended_data:
            sections.append("\n### Extended Search Results")
            sections.append(extended_data)
        
        sections.append("\n## Task")
        sections.append("""
Based on the clinical trial data and literature provided above, answer the user's question.

Guidelines:
- Provide a clear, evidence-based answer
- Cite specific data points when possible
- If information is missing, state that clearly
- Use professional medical/scientific language
- Organize your response logically

Your answer:
""")
        
        return "\n".join(sections)
    
    def save_prompt(self, prompt: str, output_path: Path):
        """Save generated prompt to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(prompt, encoding="utf-8")