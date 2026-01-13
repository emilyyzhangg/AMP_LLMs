"""
Improved Prompt Generator for Clinical Trial Analysis
======================================================

Enhanced with:
- Few-shot examples for each field
- Chain-of-thought reasoning prompts
- Clearer decision logic
- Fixed sequence extraction
- Better outcome determination
"""
import json
from typing import Dict, Any, List, Optional
from pathlib import Path


class ImprovedPromptGenerator:
    """
    Generate enhanced LLM prompts from clinical trial search results.
    
    Key improvements:
    - Few-shot examples embedded in system prompt
    - Explicit chain-of-thought reasoning
    - Clearer decision trees for each field
    - Fixed UniProt sequence extraction
    """
    
    def __init__(self):
        """Initialize prompt generator."""
        self.modelfile_template = self._load_modelfile_template()
    
    def _load_modelfile_template(self) -> str:
        """Load the improved Modelfile template."""
        return """# Improved Clinical Trial Research Assistant Modelfile Template

FROM llama3.2

SYSTEM \"\"\"You are a Clinical Trial Data Annotation Specialist with expertise in peptide therapeutics. Your task is to extract structured information from clinical trial data with HIGH ACCURACY.

# REQUIRED OUTPUT FORMAT

You MUST respond in EXACTLY this format with NO deviations:

```
NCT Number: [exact NCT ID from data]
Study Title: [exact title from data]
Study Status: [exact status from data]
Brief Summary: [first 200 chars of summary]
Conditions: [comma-separated conditions]
Interventions/Drug: [type: name format]
Phases: [exact phase from data]
Enrollment: [number]
Start Date: [YYYY-MM-DD or YYYY-MM]
Completion Date: [YYYY-MM-DD or YYYY-MM]

Classification: [AMP or Other]
  Reasoning: [your step-by-step reasoning]
  Evidence: [specific evidence from the data]

Delivery Mode: [Injection/Infusion, Topical, Oral, or Other]
  Reasoning: [your step-by-step reasoning]
  Evidence: [specific evidence from the data]

Sequence: [amino acid sequence in one-letter code, or N/A]
  Evidence: [source of sequence or why N/A]

Study IDs: [PMID:12345 or DOI:10.xxxx format, pipe-separated if multiple]

Outcome: [Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown]
  Reasoning: [your step-by-step reasoning]
  Evidence: [specific evidence from the data]

Reason for Failure: [only if Outcome is Withdrawn/Terminated/Failed, else N/A]
  Evidence: [specific evidence if applicable]

Peptide: [True or False]
  Reasoning: [your step-by-step reasoning]
  Evidence: [specific evidence from the data]

Comments: [any additional relevant observations]
```

# DECISION LOGIC WITH EXAMPLES

## 1. PEPTIDE DETERMINATION (True/False)

**Definition**: A peptide is a short chain of amino acids (typically 2-100 amino acids). 

**TRUE if**:
- Drug name contains "peptide" or known peptide drug names
- Intervention described as peptide-based therapeutic
- Drug is on DRAMP (peptide database)
- UniProt shows protein with <200 amino acids
- Literature describes amino acid sequence

**FALSE if**:
- Drug is a monoclonal antibody (mAb, -mab suffix)
- Drug is a full-length protein (>200 aa)
- Drug is a small molecule (non-amino acid based)
- Drug is a vaccine without peptide epitopes
- Drug is gene therapy or cell therapy

**Examples**:
- "LL-37 derivative" → Peptide: True (known AMP)
- "Nisin" → Peptide: True (known peptide antibiotic)
- "Pembrolizumab" → Peptide: False (monoclonal antibody)
- "Metformin" → Peptide: False (small molecule)
- "Insulin glargine" → Peptide: True (51 aa hormone)

## 2. CLASSIFICATION (AMP vs Other)

**First check**: Is this a peptide? If Peptide=False, Classification should still be determined but will typically be "Other" for non-peptides.

**AMP (Antimicrobial Peptide) if**:
- Peptide has direct antimicrobial activity (kills bacteria, fungi, viruses)
- Peptide modulates immune response against pathogens
- Peptide is listed in DRAMP database as antimicrobial
- Literature describes antimicrobial mechanism
- Drug targets infectious disease, wound healing with antimicrobial intent

**Other if**:
- Peptide for cancer (unless antimicrobial mechanism)
- Peptide for metabolic disease
- Peptide for autoimmune conditions (unless antimicrobial)
- Peptide hormone replacement
- Any non-peptide drug

**Examples**:
- "LL-37 for wound healing" → Classification: AMP (antimicrobial peptide)
- "Defensin analog for bacterial infection" → Classification: AMP
- "GLP-1 analog for diabetes" → Classification: Other (metabolic peptide)
- "Thymosin alpha-1 for cancer" → Classification: Other (immunomodulator, not antimicrobial)
- "Nisin for bacterial infection" → Classification: AMP

## 3. DELIVERY MODE

**Decision Tree**:
1. Check intervention descriptions for explicit route
2. Check arm group descriptions
3. Check trial title/summary
4. Infer from intervention type if not stated

**Injection/Infusion**:
- Keywords: IV, intravenous, SC, subcutaneous, IM, intramuscular, injection, infusion, bolus, drip
- Default for: Most biologicals, peptides without other indication

**Topical**:
- Keywords: topical, dermal, cream, ointment, gel, spray (skin), patch, varnish, rinse, mouthwash, eye drops, nasal spray, wound dressing
- Context: Skin conditions, wound care, oral/dental, ophthalmic

**Oral**:
- Keywords: oral, tablet, capsule, pill, by mouth, PO, solution (drink), syrup
- Note: Most peptides degrade orally - only choose if explicitly stated

**Other**:
- Inhalation, rectal, vaginal, implant, or unclear/multiple routes

**Examples**:
- "Subcutaneous injection once weekly" → Delivery Mode: Injection/Infusion
- "Topical gel applied to wound site" → Delivery Mode: Topical
- "Oral capsule twice daily" → Delivery Mode: Oral
- "Intravitreal injection" → Delivery Mode: Injection/Infusion
- "Inhaled formulation" → Delivery Mode: Other

## 4. OUTCOME

**Active**: Status is RECRUITING, NOT_YET_RECRUITING, ENROLLING_BY_INVITATION, ACTIVE_NOT_RECRUITING, or AVAILABLE
→ Outcome: Active (trial still ongoing)

**Withdrawn**: Status is WITHDRAWN
→ Outcome: Withdrawn (never started enrollment)

**Terminated**: Status is TERMINATED
→ Outcome: Terminated (stopped early)

**Completed** (requires analysis):
- If hasResults=true AND primary endpoints met with statistical significance → Outcome: Positive
- If hasResults=true AND primary endpoints NOT met OR safety issues → Outcome: Failed - completed trial
- If hasResults=false OR no outcome data available → Outcome: Unknown

**SUSPENDED, WITHHELD, NO_LONGER_AVAILABLE**: → Outcome: Unknown

**Examples**:
- Status: RECRUITING → Outcome: Active
- Status: COMPLETED, hasResults: true, "met primary endpoint" → Outcome: Positive
- Status: COMPLETED, hasResults: true, "failed to show efficacy" → Outcome: Failed - completed trial
- Status: COMPLETED, hasResults: false → Outcome: Unknown
- Status: TERMINATED, whyStopped: "lack of efficacy" → Outcome: Terminated

## 5. REASON FOR FAILURE

**Only complete if Outcome is**: Withdrawn, Terminated, or Failed - completed trial
**Otherwise**: N/A

**Categories**:
- Business reasons: funding, sponsorship, company decision, strategic, acquisition
- Ineffective for purpose: lack of efficacy, failed endpoints, no benefit
- Toxic/unsafe: adverse events, safety concerns, toxicity
- Due to covid: COVID-19 related delays or issues
- Recruitment issues: enrollment problems, difficulty recruiting, low accrual

**Use whyStopped field** when available. Otherwise infer from context.

## 6. SEQUENCE EXTRACTION

**Where to find sequences**:
1. UniProt results - look for "sequence" field with actual amino acid letters
2. DRAMP database entries - check for sequence information
3. PubMed/PMC article abstracts - may contain sequences
4. BioC annotations - may have sequence entities

**Format rules**:
- Use standard one-letter amino acid code: ACDEFGHIKLMNPQRSTVWY
- Include modifications in parentheses: (Ac)KLRRR or KLRRR(NH2)
- D-amino acids in lowercase: kLrRr
- Multiple sequences separated by pipe: KLRRR|GWFKKR
- If sequence not found in data: N/A

**Example sequences**:
- LL-37: LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES
- Nisin: ITSISLCTPGCKTGALMGCNMKTATCHCSIHVSK

**IMPORTANT**: Only report sequences you actually find in the provided data. Do NOT guess or hallucinate sequences.

# CRITICAL RULES

1. ALWAYS follow the exact output format shown above
2. ALWAYS include Reasoning for Classification, Delivery Mode, Outcome, and Peptide
3. NEVER guess sequences - only report if found in data, otherwise N/A
4. NEVER skip fields - use N/A for missing data
5. Do NOT wrap output in markdown code blocks
6. Use ONLY the valid values specified for each field
7. Base all decisions on evidence from the provided data

Now analyze the clinical trial data and produce your annotation.\"\"\"

# Optimized parameters for accuracy
PARAMETER temperature 0.1
PARAMETER top_p 0.85
PARAMETER top_k 30
PARAMETER repeat_penalty 1.15
PARAMETER num_ctx 16384
PARAMETER num_predict 3000

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
        
        # Add header with clear task
        sections.append(f"# CLINICAL TRIAL ANNOTATION TASK: {nct_id}")
        sections.append("""
Analyze the following clinical trial data carefully. For each field requiring classification, 
think through the decision logic step by step before providing your answer.

---
# DATA SOURCES
""")
        
        # Section 1: ClinicalTrials.gov Data (most authoritative)
        ct_data = self._format_clinical_trials_data(search_results)
        if ct_data:
            sections.append("\n## PRIMARY SOURCE: ClinicalTrials.gov")
            sections.append(ct_data)
        
        # Section 2: UniProt Data (for sequence and protein info)
        uniprot_data = self._format_uniprot_data(search_results)
        if uniprot_data:
            sections.append("\n## PROTEIN DATABASE: UniProt")
            sections.append(uniprot_data)
        
        # Section 3: DRAMP/Extended Data
        extended_data = self._format_extended_data(search_results)
        if extended_data:
            sections.append("\n## EXTENDED SEARCH RESULTS")
            sections.append(extended_data)
        
        # Section 4: PubMed Articles
        pubmed_data = self._format_pubmed_data(search_results)
        if pubmed_data:
            sections.append("\n## LITERATURE: PubMed")
            sections.append(pubmed_data)
        
        # Section 5: PMC Full-Text Articles
        pmc_data = self._format_pmc_data(search_results)
        if pmc_data:
            sections.append("\n## LITERATURE: PubMed Central")
            sections.append(pmc_data)
        
        # Section 6: PMC BioC Data
        bioc_data = self._format_bioc_data(search_results)
        if bioc_data:
            sections.append("\n## ANNOTATED DATA: BioC")
            sections.append(bioc_data)
        
        # Add final instruction
        sections.append("""
---
# YOUR TASK

Based on ALL the data provided above, complete the annotation following the EXACT format 
specified in your instructions. Remember to:

1. Include step-by-step REASONING for Classification, Delivery Mode, Outcome, and Peptide
2. Only report Sequence if you find actual amino acid sequences in the data
3. Use evidence from the specific data sources when available
4. If data is missing or unclear, state N/A with brief explanation

Begin your annotation now:
""")
        
        return "\n".join(sections)
    
    def _format_clinical_trials_data(self, results: Dict[str, Any]) -> str:
        """Format ClinicalTrials.gov data with key fields highlighted."""
        ct_source = results.get("sources", {}).get("clinical_trials", {})
        
        if not ct_source.get("success"):
            return "Clinical trial data not available."
        
        ct_data = ct_source.get("data", {})
        protocol = ct_data.get("protocolSection", {})
        has_results = ct_data.get("hasResults", False)
        
        lines = []
        
        # Identification
        ident = protocol.get("identificationModule", {})
        lines.append(f"**NCT ID:** {ident.get('nctId', 'N/A')}")
        lines.append(f"**Official Title:** {ident.get('officialTitle') or ident.get('briefTitle', 'N/A')}")
        lines.append(f"**Brief Title:** {ident.get('briefTitle', 'N/A')}")
        
        # Status - CRITICAL for Outcome determination
        status_mod = protocol.get("statusModule", {})
        lines.append(f"\n**[CRITICAL FOR OUTCOME]**")
        lines.append(f"**Overall Status:** {status_mod.get('overallStatus', 'N/A')}")
        lines.append(f"**Has Results:** {has_results}")
        why_stopped = status_mod.get('whyStopped', '')
        if why_stopped:
            lines.append(f"**Why Stopped:** {why_stopped}")
        lines.append(f"**Start Date:** {status_mod.get('startDateStruct', {}).get('date', 'N/A')}")
        lines.append(f"**Completion Date:** {status_mod.get('completionDateStruct', {}).get('date', 'N/A')}")
        
        # Description
        desc_mod = protocol.get("descriptionModule", {})
        brief_summary = desc_mod.get("briefSummary", "N/A")
        if len(brief_summary) > 800:
            brief_summary = brief_summary[:800] + "..."
        lines.append(f"\n**Brief Summary:** {brief_summary}")
        
        detailed_desc = desc_mod.get("detailedDescription", "")
        if detailed_desc and len(detailed_desc) > 100:
            if len(detailed_desc) > 600:
                detailed_desc = detailed_desc[:600] + "..."
            lines.append(f"\n**Detailed Description:** {detailed_desc}")
        
        # Conditions
        cond_mod = protocol.get("conditionsModule", {})
        conditions = cond_mod.get("conditions", [])
        lines.append(f"\n**Conditions:** {', '.join(conditions) if conditions else 'N/A'}")
        
        keywords = cond_mod.get("keywords", [])
        if keywords:
            lines.append(f"**Keywords:** {', '.join(keywords)}")
        
        # Interventions - CRITICAL for Peptide, Classification, Delivery Mode
        arms_int = protocol.get("armsInterventionsModule", {})
        interventions = arms_int.get("interventions", [])
        if interventions:
            lines.append(f"\n**[CRITICAL FOR PEPTIDE/DELIVERY MODE]**")
            lines.append("**Interventions:**")
            for intv in interventions[:5]:
                int_type = intv.get("type", "")
                int_name = intv.get("name", "")
                int_desc = intv.get("description", "")
                lines.append(f"  - Type: {int_type}")
                lines.append(f"    Name: {int_name}")
                if int_desc:
                    if len(int_desc) > 400:
                        int_desc = int_desc[:400] + "..."
                    lines.append(f"    Description: {int_desc}")
        else:
            lines.append("**Interventions:** N/A")
        
        # Arm Groups - may contain delivery mode info
        arm_groups = arms_int.get("armGroups", [])
        if arm_groups:
            lines.append("\n**Arm Groups:**")
            for arm in arm_groups[:4]:
                label = arm.get("label", "")
                arm_type = arm.get("type", "")
                arm_desc = arm.get("description", "")
                lines.append(f"  - {label} ({arm_type})")
                if arm_desc:
                    if len(arm_desc) > 300:
                        arm_desc = arm_desc[:300] + "..."
                    lines.append(f"    Description: {arm_desc}")
        
        # Design
        design_mod = protocol.get("designModule", {})
        phases = design_mod.get("phases", [])
        lines.append(f"\n**Phases:** {', '.join(phases) if phases else 'N/A'}")
        
        enrollment_info = design_mod.get("enrollmentInfo", {})
        lines.append(f"**Enrollment:** {enrollment_info.get('count', 'N/A')}")
        
        # Outcomes - helpful for outcome determination
        outcomes_mod = protocol.get("outcomesModule", {})
        primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
        if primary_outcomes:
            lines.append("\n**Primary Outcomes:**")
            for i, outcome in enumerate(primary_outcomes[:3], 1):
                measure = outcome.get("measure", "")
                lines.append(f"  {i}. {measure}")
        
        # References
        refs_mod = protocol.get("referencesModule", {})
        references = refs_mod.get("references", [])
        if references:
            lines.append("\n**References (for Study IDs):**")
            for i, ref in enumerate(references[:5], 1):
                pmid = ref.get("pmid", "")
                ref_type = ref.get("type", "")
                citation = ref.get("citation", "")
                if pmid:
                    lines.append(f"  {i}. PMID: {pmid} ({ref_type})")
                elif citation:
                    lines.append(f"  {i}. {citation[:150]}...")
        
        return "\n".join(lines)
    
    def _format_uniprot_data(self, results: Dict[str, Any]) -> str:
        """
        Format UniProt data with ACTUAL SEQUENCES extracted.
        
        This is critical for sequence annotation - the original code only
        extracted sequence length, not the actual sequence!
        """
        extended_source = results.get("sources", {}).get("extended", {})
        if not extended_source:
            return ""
        
        uniprot = extended_source.get("uniprot", {})
        if not uniprot.get("success"):
            return ""
        
        uniprot_data = uniprot.get("data", {})
        uniprot_results = uniprot_data.get("results", [])
        
        if not uniprot_results:
            return ""
        
        lines = []
        lines.append(f"**Total UniProt Results:** {len(uniprot_results)}")
        lines.append(f"**Query:** {uniprot_data.get('query', 'N/A')}\n")
        
        for i, result in enumerate(uniprot_results[:5], 1):
            lines.append(f"### Protein {i}")
            
            # Accession
            accession = result.get("primaryAccession", "")
            if accession:
                lines.append(f"**Accession:** {accession}")
            
            # Entry name
            entry_name = result.get("uniProtkbId", "")
            if entry_name:
                lines.append(f"**Entry Name:** {entry_name}")
            
            # Protein name
            protein_desc = result.get("proteinDescription", {})
            rec_name = protein_desc.get("recommendedName", {})
            full_name = rec_name.get("fullName", {}).get("value", "")
            if full_name:
                lines.append(f"**Protein Name:** {full_name}")
            
            # Organism
            organism = result.get("organism", {})
            organism_name = organism.get("scientificName", "")
            if organism_name:
                lines.append(f"**Organism:** {organism_name}")
            
            # CRITICAL: Extract actual sequence, not just length!
            sequence_info = result.get("sequence", {})
            seq_length = sequence_info.get("length", 0)
            seq_value = sequence_info.get("value", "")  # The actual amino acid sequence!
            
            if seq_value:
                lines.append(f"\n**[SEQUENCE DATA - USE FOR ANNOTATION]**")
                lines.append(f"**Sequence Length:** {seq_length} amino acids")
                # Include full sequence if short enough, otherwise truncate with note
                if len(seq_value) <= 200:
                    lines.append(f"**Sequence:** {seq_value}")
                else:
                    lines.append(f"**Sequence (first 200 aa):** {seq_value[:200]}...")
                    lines.append(f"**Note:** Full sequence is {seq_length} aa - this may indicate a protein rather than peptide if >100 aa")
            elif seq_length:
                lines.append(f"**Sequence Length:** {seq_length} aa (sequence not retrieved)")
            
            # Function
            comments = result.get("comments", [])
            for comment in comments:
                if comment.get("commentType") == "FUNCTION":
                    func_texts = comment.get("texts", [])
                    if func_texts:
                        func_text = func_texts[0].get("value", "")
                        if len(func_text) > 400:
                            func_text = func_text[:400] + "..."
                        lines.append(f"**Function:** {func_text}")
                    break
            
            # Keywords - may indicate antimicrobial activity
            result_keywords = result.get("keywords", [])
            if result_keywords:
                keyword_values = [kw.get("name", "") for kw in result_keywords[:10]]
                if keyword_values:
                    lines.append(f"**Keywords:** {', '.join(keyword_values)}")
            
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
            
            lines.append("### Web Search Results")
            lines.append(f"**Query:** {ddg_data.get('query', 'N/A')}\n")
            
            for i, result in enumerate(ddg_results[:5], 1):
                lines.append(f"**Result {i}:**")
                lines.append(f"  Title: {result.get('title', 'N/A')}")
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
            
            lines.append("\n### FDA Drug Database")
            
            for i, result in enumerate(fda_results[:3], 1):
                lines.append(f"**Drug {i}:**")
                
                openfda_info = result.get("openfda", {})
                
                brand_names = openfda_info.get("brand_name", [])
                if brand_names:
                    lines.append(f"  Brand Name(s): {', '.join(brand_names[:3])}")
                
                generic_names = openfda_info.get("generic_name", [])
                if generic_names:
                    lines.append(f"  Generic Name(s): {', '.join(generic_names[:3])}")
                
                # Route - IMPORTANT for Delivery Mode
                routes = openfda_info.get("route", [])
                if routes:
                    lines.append(f"  **Route of Administration:** {', '.join(routes[:3])}")
                
                # Product type
                product_types = openfda_info.get("product_type", [])
                if product_types:
                    lines.append(f"  Product Type: {', '.join(product_types)}")
                
                lines.append("")
        
        # Google Scholar
        scholar = extended_source.get("scholar", {})
        if scholar.get("success"):
            has_data = True
            scholar_data = scholar.get("data", {})
            scholar_results = scholar_data.get("results", [])
            
            lines.append("\n### Academic Literature (Google Scholar)")
            
            for i, result in enumerate(scholar_results[:3], 1):
                lines.append(f"**Paper {i}:**")
                lines.append(f"  Title: {result.get('title', 'N/A')}")
                snippet = result.get('snippet', '')
                if snippet:
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
                    lines.append(f"  Snippet: {snippet}")
                lines.append("")
        
        if not has_data:
            return ""
        
        return "\n".join(lines)
    
    def _format_pubmed_data(self, results: Dict[str, Any]) -> str:
        """Format PubMed data with focus on relevant content."""
        pubmed_source = results.get("sources", {}).get("pubmed", {})
        
        if not pubmed_source.get("success"):
            return ""
        
        pubmed_data = pubmed_source.get("data", {})
        articles = pubmed_data.get("articles", [])
        
        if not articles:
            return ""
        
        lines = []
        lines.append(f"**Total Articles Found:** {pubmed_data.get('total_found', 0)}")
        lines.append(f"**Search Strategy:** {pubmed_data.get('search_strategy', 'N/A')}\n")
        
        for i, article in enumerate(articles[:4], 1):
            lines.append(f"### Article {i}")
            lines.append(f"**PMID:** {article.get('pmid', 'N/A')}")
            lines.append(f"**Title:** {article.get('title', 'N/A')}")
            lines.append(f"**Journal:** {article.get('journal', 'N/A')}")
            lines.append(f"**Year:** {article.get('year', 'N/A')}")
            
            abstract = article.get("abstract", "")
            if abstract:
                if len(abstract) > 600:
                    abstract = abstract[:600] + "..."
                lines.append(f"**Abstract:** {abstract}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_pmc_data(self, results: Dict[str, Any]) -> str:
        """Format PMC data."""
        pmc_source = results.get("sources", {}).get("pmc", {})
        
        if not pmc_source.get("success"):
            return ""
        
        pmc_data = pmc_source.get("data", {})
        articles = pmc_data.get("articles", [])
        
        if not articles:
            return ""
        
        lines = []
        lines.append(f"**Total PMC Articles Found:** {pmc_data.get('total_found', 0)}\n")
        
        for i, article in enumerate(articles[:3], 1):
            lines.append(f"### PMC Article {i}")
            lines.append(f"**PMCID:** {article.get('pmcid', 'N/A')}")
            lines.append(f"**PMID:** {article.get('pmid', 'N/A')}")
            lines.append(f"**Title:** {article.get('title', 'N/A')}")
            
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
            return ""
        
        bioc_data = bioc_source.get("data", {})
        articles = bioc_data.get("articles", [])
        
        if not articles:
            return ""
        
        lines = []
        lines.append(f"**Total BioC Articles:** {bioc_data.get('total_fetched', 0)}/{bioc_data.get('total_found', 0)}\n")
        
        for i, article in enumerate(articles[:2], 1):
            lines.append(f"### BioC Article {i}")
            lines.append(f"**ID:** {article.get('pmid', 'N/A')}")
            
            bioc_content = article.get("bioc_data", {})
            documents = bioc_content.get("documents", [])
            
            if documents:
                doc = documents[0]
                passages = doc.get("passages", [])
                
                if passages:
                    lines.append("\n**Key Content:**")
                    
                    for j, passage in enumerate(passages[:2], 1):
                        passage_type = passage.get("infons", {}).get("type", "text")
                        text = passage.get("text", "")
                        
                        if text and len(text) > 400:
                            text = text[:400] + "..."
                        
                        if text:
                            lines.append(f"\n*{passage_type.title()}:*")
                            lines.append(text)
                        
                        # Show annotations - may contain sequence info
                        annotations = passage.get("annotations", [])
                        if annotations:
                            relevant_anns = []
                            for ann in annotations[:5]:
                                ann_type = ann.get("infons", {}).get("type", "")
                                ann_text = ann.get("text", "")
                                if ann_type and ann_text:
                                    relevant_anns.append(f"{ann_type}: {ann_text}")
                            if relevant_anns:
                                lines.append(f"\n*Annotations:* {'; '.join(relevant_anns)}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def generate_rag_query_prompt(
        self,
        query: str,
        search_results: Dict[str, Any]
    ) -> str:
        """Generate RAG-style prompt for answering queries."""
        sections = []
        
        sections.append("# Clinical Trial Research Query")
        sections.append(f"\n**User Question:** {query}\n")
        sections.append("## Available Data\n")
        
        ct_data = self._format_clinical_trials_data(search_results)
        if ct_data:
            sections.append("### ClinicalTrials.gov")
            sections.append(ct_data)
        
        uniprot_data = self._format_uniprot_data(search_results)
        if uniprot_data:
            sections.append("\n### UniProt Protein Data")
            sections.append(uniprot_data)
        
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


# For backwards compatibility, create an alias
PromptGenerator = ImprovedPromptGenerator