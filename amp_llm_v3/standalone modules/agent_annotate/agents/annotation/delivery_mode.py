"""
Delivery Mode Annotation Agent.

Determines how the drug/intervention is administered.

v10 changes:
  - Expanded deterministic keyword search to ALL citation sources (not just
    clinicaltrials_gov), catching routes in literature, arm descriptions, etc.
  - Added keywords for IV/IM/SC abbreviations and administered/given phrases.
  - Upgraded mac_mini model from 8B to 14B — 8B ignores Pass 1 evidence in
    Pass 2, causing "Other/Unspecified" defaults when route info was found.
  - clinical_protocol.py now extracts detailedDescription and armGroups as
    citations, feeding more route info into the deterministic path.

v17 changes:
  - Multi-route collection: deterministic path now collects ALL distinct routes
    across all citations instead of returning on the first keyword match.
    Produces comma-separated values for multi-drug multi-route trials.
  - False positive prevention: exclude trial title/briefTitle text from
    keyword matching. " iv " in "Grade II to IV (MAGIC)" is disease grading,
    not a route. Title citations are identified by section_name == "title".
  - _parse_value updated to handle comma-separated multi-route values.
"""

import re
import logging
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.delivery_mode")

VALID_VALUES = [
    "Injection/Infusion - Intramuscular",
    "Injection/Infusion - Other/Unspecified",
    "Injection/Infusion - Subcutaneous/Intradermal",
    "IV",
    "Intranasal",
    "Oral - Tablet",
    "Oral - Capsule",
    "Oral - Food",
    "Oral - Drink",
    "Oral - Unspecified",
    "Topical - Cream/Gel",
    "Topical - Powder",
    "Topical - Spray",
    "Topical - Strip/Covering",
    "Topical - Wash",
    "Topical - Unspecified",
    "Other/Unspecified",
    "Inhalation",
]

# Pass 1: Extract ALL route evidence from every source
PASS1_SYSTEM = """You are a clinical pharmacology route-of-administration extraction specialist.

Your task: Search ALL available evidence to find how this drug is administered. Check EVERY source — do NOT stop at the first mention. Different sources may have different levels of specificity.

Extract the following:

1. PROTOCOL ROUTE: What does the ClinicalTrials.gov protocol say about route of administration? Look in intervention description, arm group descriptions, and detailed description. Quote the exact text.

2. FDA/DRUG LABEL ROUTE: Does any evidence mention an FDA-approved route, drug label route, or prescribing information route? (e.g., "for subcutaneous use", "administered intravenously"). FDA labels are MORE SPECIFIC and MORE RELIABLE than protocol text.

3. LITERATURE ROUTE: Do any PubMed/PMC publications describe how this drug is administered? Quote relevant excerpts.

4. DATABASE ROUTE: Do ChEMBL, UniProt, DRAMP, or other database entries mention route or formulation information?

5. DRUG FORMULATION: Is the drug described as a tablet, capsule, solution, suspension, cream, gel, powder, spray, patch, inhaler, or other formulation? The formulation strongly implies the route.

6. SPECIFICITY LEVEL: Based on ALL sources above, what is the MOST SPECIFIC route you can determine?
   - If ANY source says "subcutaneous" or "SC" → the route is subcutaneous
   - If ANY source says "intramuscular" or "IM" → the route is intramuscular
   - If ANY source says "intravenous" or "IV" → the route is IV
   - If NONE specify beyond "injection" → route is unspecified injection

Format your response EXACTLY as:
Protocol Route: [quote or "not specified"]
FDA/Label Route: [quote or "not found"]
Literature Route: [quote or "not found"]
Database Route: [info or "not found"]
Drug Formulation: [formulation or "not specified"]
Most Specific Route: [your determination]"""

# Pass 2: Classify into one of the 18 valid values
PASS2_SYSTEM = """You are a delivery mode classification specialist. You have extracted route-of-administration evidence. Now classify it into EXACTLY ONE delivery mode.

The route facts you extracted:
{pass1_output}

VALID VALUES (choose exactly one):

Injection/Infusion:
- IV: Intravenous (IV push, IV drip, IV infusion)
- Injection/Infusion - Intramuscular: IM injection (ONLY if "intramuscular" or "IM" explicitly stated)
- Injection/Infusion - Subcutaneous/Intradermal: SC, sub-Q, or intradermal (ONLY if explicitly stated)
- Injection/Infusion - Other/Unspecified: Any other injection route OR injection without IM/SC/IV specified

Intranasal: Nasal spray, nasal drops (NOT topical spray)
Inhalation: Inhaler, nebulizer, inhaled

Oral:
- Oral - Tablet, Oral - Capsule, Oral - Food, Oral - Drink, Oral - Unspecified

Topical:
- Topical - Cream/Gel, Topical - Powder, Topical - Spray, Topical - Strip/Covering, Topical - Wash, Topical - Unspecified

Other/Unspecified: Does not fit any category above

CLASSIFICATION RULES:
1. USE THE MOST SPECIFIC SOURCE. FDA label > Literature > Protocol text > Database.
2. If FDA/Label Route specifies "subcutaneous" but Protocol just says "injection" → use Subcutaneous/Intradermal.
3. If Literature says "administered intravenously" but Protocol is vague → use IV.
4. ONLY use "Injection/Infusion - Other/Unspecified" when NO source specifies IM, SC, or IV.
5. Nutritional formula/shake = Oral - Drink. Nasal spray = Intranasal (not Topical - Spray).
6. MULTI-ROUTE TRIALS: If the trial tests multiple active drugs that use DIFFERENT routes
   (e.g., one drug given IV and another given orally), list ALL routes comma-separated in the
   same order as the drugs appear. Do NOT list multiple routes for a single drug, and do NOT
   list the placebo/comparator route separately.
7. PEPTIDE VACCINES AND CANCER TRIALS: Peptide vaccines (cancer vaccines, anti-tumor peptides,
   immunotherapy peptides) are NOT administered intranasally. If the protocol does not explicitly
   specify the route for a peptide vaccine or cancer immunotherapy, use
   "Injection/Infusion - Other/Unspecified", NOT Intranasal.
8. AMBIGUITY BIAS: When route evidence is only INDIRECT (implied by product type, inferred from
   context, or described only as "injection" / "administered" without an explicit IM/SC/IV qualifier),
   use "Injection/Infusion - Other/Unspecified" rather than guessing a specific route. A route
   keyword must appear EXPLICITLY in the evidence text — do not infer SC because the drug is a
   peptide, or IV because the dose is in mg/kg. Specificity without explicit evidence is worse
   than Other/Unspecified.

Format your response EXACTLY as:
Delivery Mode: [one of the 18 valid values, exactly as written — or comma-separated if multi-route]
Evidence: [cite which source determined the route]
Reasoning: [brief explanation]"""


# --------------------------------------------------------------------------- #
#  OpenFDA route → delivery mode mapping (v9)
# --------------------------------------------------------------------------- #

_OPENFDA_ROUTE_MAP = {
    "oral": "Oral - Unspecified", "intravenous": "IV",
    "subcutaneous": "Injection/Infusion - Subcutaneous/Intradermal",
    "intramuscular": "Injection/Infusion - Intramuscular",
    "intradermal": "Injection/Infusion - Subcutaneous/Intradermal",
    "topical": "Topical - Unspecified", "nasal": "Intranasal",
    "intranasal": "Intranasal", "inhalation": "Inhalation",
    "respiratory (inhalation)": "Inhalation", "ophthalmic": "Topical - Unspecified",
    "transdermal": "Topical - Strip/Covering",
    "intrathecal": "Injection/Infusion - Other/Unspecified",
    "intraperitoneal": "Injection/Infusion - Other/Unspecified",
}

_PROTOCOL_ROUTE_KEYWORDS = {
    # Specific route terms (highest priority — check these first)
    "subcutaneous": "Injection/Infusion - Subcutaneous/Intradermal",
    "sub-q": "Injection/Infusion - Subcutaneous/Intradermal",
    "sc injection": "Injection/Infusion - Subcutaneous/Intradermal",
    "subcutaneous injection": "Injection/Infusion - Subcutaneous/Intradermal",
    "subcutaneous infusion": "Injection/Infusion - Subcutaneous/Intradermal",
    "given subcutaneously": "Injection/Infusion - Subcutaneous/Intradermal",
    "administered subcutaneously": "Injection/Infusion - Subcutaneous/Intradermal",
    "intradermal": "Injection/Infusion - Subcutaneous/Intradermal",
    "intramuscular": "Injection/Infusion - Intramuscular",
    "im injection": "Injection/Infusion - Intramuscular",
    "intramuscular injection": "Injection/Infusion - Intramuscular",
    "injected intramuscularly": "Injection/Infusion - Intramuscular",
    "given intramuscularly": "Injection/Infusion - Intramuscular",
    "administered intramuscularly": "Injection/Infusion - Intramuscular",
    "intravenous": "IV",
    "iv infusion": "IV", "iv push": "IV", "iv drip": "IV",
    "intravenous infusion": "IV", "intravenous injection": "IV",
    "administered intravenously": "IV", "given intravenously": "IV",
    "infused intravenously": "IV",
    # v12: continuous infusion patterns → IV
    "continuous infusion": "IV", "infusion at": "IV",
    "ng/kg/min": "IV", "ug/kg/min": "IV", "mg/kg/min": "IV",
    "mcg/kg/min": "IV", "units/kg/hr": "IV",
    # Abbreviations (space-padded to avoid false matches)
    # Note: bare " sc " excluded — too ambiguous (" sc " appears in "SC study", "SC phase", etc.)
    " iv ": "IV", " im ": "Injection/Infusion - Intramuscular",
    "sc injection": "Injection/Infusion - Subcutaneous/Intradermal",
    "sc administration": "Injection/Infusion - Subcutaneous/Intradermal",
    "sc dose": "Injection/Infusion - Subcutaneous/Intradermal",
    "auto-injector": "Injection/Infusion - Subcutaneous/Intradermal",
    "autoinjector": "Injection/Infusion - Subcutaneous/Intradermal",
    "pen injector": "Injection/Infusion - Subcutaneous/Intradermal",
    # Oral
    "oral tablet": "Oral - Tablet", "oral capsule": "Oral - Capsule",
    # Intranasal / Inhalation
    "intranasal": "Intranasal", "nasal spray": "Intranasal",
    "inhalation": "Inhalation", "nebulizer": "Inhalation", "nebuliser": "Inhalation",
    # Topical
    "topical cream": "Topical - Cream/Gel", "topical gel": "Topical - Cream/Gel",
    "mouthwash": "Topical - Wash", "mouth rinse": "Topical - Wash",
}

_DRUG_CLASS_ROUTES = {
    "semaglutide": "Injection/Infusion - Subcutaneous/Intradermal",
    "liraglutide": "Injection/Infusion - Subcutaneous/Intradermal",
    "exenatide": "Injection/Infusion - Subcutaneous/Intradermal",
    "dulaglutide": "Injection/Infusion - Subcutaneous/Intradermal",
    "tirzepatide": "Injection/Infusion - Subcutaneous/Intradermal",
    "insulin": "Injection/Infusion - Subcutaneous/Intradermal",
    "teriparatide": "Injection/Infusion - Subcutaneous/Intradermal",
    "abaloparatide": "Injection/Infusion - Subcutaneous/Intradermal",
    "apraglutide": "Injection/Infusion - Subcutaneous/Intradermal",
    "teduglutide": "Injection/Infusion - Subcutaneous/Intradermal",
    "enfuvirtide": "Injection/Infusion - Subcutaneous/Intradermal",
    "colistin": "IV", "colistimethate": "IV", "daptomycin": "IV",
    "vancomycin": "IV", "teicoplanin": "IV", "aviptadil": "IV",
    "peptide t": "Intranasal", "dapta": "Intranasal",
}


# v17: Citation section names that should be excluded from keyword matching.
# Title text contains disease grading ("Grade II to IV") which false-positives
# the " iv " keyword.
_TITLE_SECTIONS = {"title", "briefTitle", "officialTitle", "brief_title", "official_title"}


def _is_title_citation(citation) -> bool:
    """Check if a citation is from the trial title (should skip ambiguous keywords)."""
    section = getattr(citation, "section_name", "") or ""
    return section.lower().replace("_", "") in {s.lower().replace("_", "") for s in _TITLE_SECTIONS}


def _extract_deterministic_route(research_results: list) -> FieldAnnotation | None:
    """Extract delivery route deterministically from OpenFDA and protocol data.

    v17: Collects ALL distinct routes across all citations instead of returning
    on the first match. Produces comma-separated values for multi-route trials.
    Excludes title text from ambiguous keyword matching.
    """
    intervention_names: list[str] = []
    found_routes: dict[str, tuple[float, bool, list]] = {}  # value → (confidence, skip_verify, evidence)

    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol":
            continue
        if result.raw_data:
            proto = result.raw_data.get("protocol_section", result.raw_data.get("protocolSection", {}))
            arms_mod = proto.get("armsInterventionsModule", {})
            for interv in arms_mod.get("interventions", []):
                name = interv.get("name", "")
                if name:
                    intervention_names.append(name.lower().strip())
        for citation in result.citations:
            if citation.source_name == "openfda":
                snippet_lower = citation.snippet.lower()
                if intervention_names and not any(iname in snippet_lower for iname in intervention_names):
                    continue
                for openfda_route, delivery_value in _OPENFDA_ROUTE_MAP.items():
                    if f"route: {openfda_route}" in snippet_lower or f"route\": \"{openfda_route}" in snippet_lower:
                        if delivery_value not in found_routes:
                            found_routes[delivery_value] = (0.95, True, [citation])
                            logger.info(f"  delivery_mode: found {delivery_value} (OpenFDA: '{openfda_route}')")

        # Also check raw_data for structured OpenFDA route info
        if result.raw_data:
            openfda_results = result.raw_data.get("openfda_results", [])
            if isinstance(openfda_results, list):
                for fda_item in openfda_results:
                    if isinstance(fda_item, dict):
                        openfda_block = fda_item.get("openfda", {})
                        fda_names = openfda_block.get("generic_name", []) + openfda_block.get("brand_name", [])
                        fda_names_lower = [n.lower() for n in fda_names if isinstance(n, str)]
                        if intervention_names and fda_names_lower:
                            if not any(iname in fn or fn in iname for iname in intervention_names for fn in fda_names_lower):
                                continue
                        routes = openfda_block.get("route", [])
                        if isinstance(routes, list):
                            for route_str in routes:
                                route_lower = route_str.lower().strip()
                                if route_lower in _OPENFDA_ROUTE_MAP:
                                    delivery_value = _OPENFDA_ROUTE_MAP[route_lower]
                                    if delivery_value not in found_routes:
                                        found_routes[delivery_value] = (0.95, True, [])
                                        logger.info(f"  delivery_mode: found {delivery_value} (OpenFDA raw_data: '{route_str}')")

    # v17: Search ALL citations, collecting all routes instead of returning on first match
    # Ambiguous short keywords (" iv ", " im ", " sc ") are skipped for title citations
    _AMBIGUOUS_KEYWORDS = {" iv ", " im ", " sc "}

    for result in research_results:
        if result.error:
            continue
        for citation in result.citations:
            snippet_lower = citation.snippet.lower()
            is_title = _is_title_citation(citation)
            for keyword, delivery_value in _PROTOCOL_ROUTE_KEYWORDS.items():
                if keyword in snippet_lower:
                    # v17: Skip ambiguous abbreviation keywords in title text
                    if is_title and keyword in _AMBIGUOUS_KEYWORDS:
                        logger.debug(f"  delivery_mode: skipping '{keyword}' in title (false-positive risk)")
                        continue
                    if delivery_value not in found_routes:
                        is_structured = citation.source_name in ("clinicaltrials_gov", "openfda")
                        conf = 0.95 if is_structured else 0.85
                        skip = is_structured
                        found_routes[delivery_value] = (conf, skip, [citation])
                        logger.info(f"  delivery_mode: found {delivery_value} (keyword: '{keyword}' in {citation.source_name})")

    # Drug-class defaults (lowest priority — only if no other routes found)
    if not found_routes:
        for name in intervention_names:
            for drug_name, delivery_value in _DRUG_CLASS_ROUTES.items():
                if drug_name in name or name in drug_name:
                    logger.info(f"  delivery_mode: drug-class default → {delivery_value} (drug: '{name}')")
                    return FieldAnnotation(
                        field_name="delivery_mode", value=delivery_value, confidence=0.7,
                        reasoning=f"[Deterministic v9] Drug-class default for '{name}' (matched '{drug_name}').",
                        evidence=[], model_name="deterministic", skip_verification=False,
                    )

    if not found_routes:
        return None

    # Build the result — single route or comma-separated multi-route
    routes_list = sorted(found_routes.keys())
    value = ", ".join(routes_list)
    # Use the lowest confidence and most conservative skip_verification
    min_conf = min(r[0] for r in found_routes.values())
    all_skip = all(r[1] for r in found_routes.values())
    all_evidence = []
    for r in found_routes.values():
        all_evidence.extend(r[2])

    multi_tag = f" ({len(routes_list)} routes)" if len(routes_list) > 1 else ""
    logger.info(f"  delivery_mode: deterministic → {value}{multi_tag}")
    return FieldAnnotation(
        field_name="delivery_mode", value=value, confidence=min_conf,
        reasoning=f"[Deterministic v17] Collected {len(routes_list)} route(s) from all citations",
        evidence=all_evidence[:5], model_name="deterministic",
        skip_verification=not (len(routes_list) > 1) and all_skip,  # Always verify multi-route
    )


class DeliveryModeAgent(BaseAnnotationAgent):
    """Determines drug delivery mode using two-pass route investigation."""

    field_name = "delivery_mode"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        # v9: Try deterministic route extraction first
        det_result = _extract_deterministic_route(research_results)
        if det_result is not None:
            return det_result

        from app.services.config_service import config_service

        _config = config_service.get()
        is_server = _config.orchestrator.hardware_profile == "server"
        max_cites = 35 if is_server else 20
        max_snippet = 500 if is_server else 250

        # Build structured evidence — trial metadata and drug data
        # sections contain the route-of-administration information
        evidence_text, cited_sources = self.build_structured_evidence(
            nct_id, research_results,
            max_citations=max_cites,
            max_snippet_chars=max_snippet,
        )

        # --- EDAM guidance injection ---
        edam_guidance = await self.get_edam_guidance(nct_id, evidence_text)
        if edam_guidance:
            evidence_text = edam_guidance + "\n\n" + evidence_text

        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        config = config_service.get()
        profile = config.orchestrator.hardware_profile

        # v10: Use 14B on all profiles — 8B ignores Pass 1 evidence in Pass 2,
        # causing "Other/Unspecified" defaults when route info was extracted.
        if profile in ("mac_mini", "server"):
            primary_model = "qwen2.5:14b"
        else:
            primary_model = None
            for model_key, model_cfg in config.verification.models.items():
                if model_cfg.role == "annotator":
                    primary_model = model_cfg.name
                    break
            if not primary_model:
                primary_model = "qwen2.5:14b"

        # --- Pass 1: Extract route evidence from all sources ---
        try:
            logger.info(f"  delivery_mode: Pass 1 — extracting route evidence for {nct_id}")
            pass1_response = await ollama_client.generate(
                model=primary_model,
                prompt=evidence_text,
                system=PASS1_SYSTEM,
                temperature=config.ollama.field_temperatures.get("delivery_mode", config.ollama.temperature),
            )
            pass1_text = pass1_response.get("response", "")
        except Exception as e:
            return FieldAnnotation(
                field_name=self.field_name,
                value="Other/Unspecified",
                confidence=0.0,
                reasoning=f"Pass 1 LLM call failed: {e}",
                evidence=[],
                model_name=primary_model,
            )

        # --- Pass 2: Classify route into valid value ---
        try:
            logger.info(f"  delivery_mode: Pass 2 — classifying route for {nct_id}")
            pass2_prompt = PASS2_SYSTEM.format(pass1_output=pass1_text)
            pass2_response = await ollama_client.generate(
                model=primary_model,
                prompt=pass2_prompt + "\n\nOriginal evidence:\n" + evidence_text,
                temperature=config.ollama.field_temperatures.get("delivery_mode", config.ollama.temperature),
            )
            pass2_text = pass2_response.get("response", "")
        except Exception as e:
            # Fallback: infer from Pass 1
            value = self._infer_from_pass1(pass1_text)
            return FieldAnnotation(
                field_name=self.field_name,
                value=value,
                confidence=0.3,
                reasoning=f"Pass 2 failed ({e}), inferred from pass 1: {pass1_text[:300]}",
                evidence=cited_sources[:10],
                model_name=primary_model,
            )

        value = self._parse_value(pass2_text)
        reasoning = f"[Pass 1 route extraction] {pass1_text[:400]}\n[Pass 2 classification] {pass2_text[:300]}"
        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

    def _infer_from_pass1(self, pass1_text: str) -> str:
        """Fallback: infer delivery mode from Pass 1 extraction if Pass 2 fails."""
        lower = pass1_text.lower()

        # Check for explicit route mentions across all sources
        if any(kw in lower for kw in ["intravenous", " iv ", "iv infusion", "iv push"]):
            return "IV"
        if any(kw in lower for kw in ["subcutaneous", " sc ", "sub-q", "intradermal"]):
            return "Injection/Infusion - Subcutaneous/Intradermal"
        if any(kw in lower for kw in ["intramuscular", " im "]):
            return "Injection/Infusion - Intramuscular"
        if any(kw in lower for kw in ["intranasal", "nasal spray", "nasal drop"]):
            return "Intranasal"
        if any(kw in lower for kw in ["inhalation", "inhaler", "nebulizer", "inhaled"]):
            return "Inhalation"
        if any(kw in lower for kw in ["tablet"]):
            return "Oral - Tablet"
        if any(kw in lower for kw in ["capsule"]):
            return "Oral - Capsule"
        if any(kw in lower for kw in ["oral", "by mouth"]):
            return "Oral - Unspecified"
        if any(kw in lower for kw in ["injection", "infusion", "parenteral"]):
            return "Injection/Infusion - Other/Unspecified"
        if any(kw in lower for kw in ["cream", "gel", "ointment", "topical"]):
            return "Topical - Cream/Gel"

        return "Other/Unspecified"

    def _parse_value(self, text: str) -> str:
        match = re.search(r"Delivery Mode:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if not match:
            return "Other/Unspecified"

        raw = match.group(1).strip()

        # v17: Handle comma-separated multi-route values from LLM
        if "," in raw:
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            parsed = [self._parse_single_value(p) for p in parts]
            # Deduplicate while preserving order
            seen = set()
            unique = []
            for v in parsed:
                if v not in seen and v != "Other/Unspecified":
                    seen.add(v)
                    unique.append(v)
            if unique:
                return ", ".join(unique)
            return "Other/Unspecified"

        return self._parse_single_value(raw)

    def _parse_single_value(self, raw: str) -> str:
        """Parse a single delivery mode value (not comma-separated)."""
        lower = raw.lower().strip()

        # Exact match first (case-insensitive)
        for valid in VALID_VALUES:
            if valid.lower() == lower:
                return valid

        # Fuzzy matching by category

        # IV — check before general injection to avoid misclassification
        if lower in ("iv", "intravenous") or "intravenous" in lower:
            return "IV"

        # Injection/Infusion subtypes
        if "intramuscular" in lower:
            return "Injection/Infusion - Intramuscular"
        if "subcutaneous" in lower or "intradermal" in lower:
            return "Injection/Infusion - Subcutaneous/Intradermal"
        if "injection" in lower or "infusion" in lower:
            return "Injection/Infusion - Other/Unspecified"

        # Intranasal
        if "intranasal" in lower or "nasal" in lower:
            return "Intranasal"

        # Inhalation
        if "inhalation" in lower or "inhale" in lower or "nebuliz" in lower or "inhaler" in lower:
            return "Inhalation"

        # Oral subtypes
        if "oral" in lower or "tablet" in lower or "capsule" in lower or "food" in lower or "drink" in lower:
            if "tablet" in lower:
                return "Oral - Tablet"
            if "capsule" in lower:
                return "Oral - Capsule"
            if "food" in lower:
                return "Oral - Food"
            if "drink" in lower:
                return "Oral - Drink"
            return "Oral - Unspecified"

        # Topical subtypes
        if "topical" in lower or "cream" in lower or "gel" in lower or "ointment" in lower or "powder" in lower or "spray" in lower or "strip" in lower or "covering" in lower or "bandage" in lower or "dressing" in lower or "patch" in lower or "wash" in lower or "rinse" in lower or "mouthwash" in lower or "lotion" in lower:
            if "cream" in lower or "gel" in lower or "ointment" in lower or "lotion" in lower:
                return "Topical - Cream/Gel"
            if "powder" in lower:
                return "Topical - Powder"
            if "spray" in lower:
                return "Topical - Spray"
            if "strip" in lower or "covering" in lower or "bandage" in lower or "dressing" in lower or "patch" in lower:
                return "Topical - Strip/Covering"
            if "wash" in lower or "rinse" in lower or "mouthwash" in lower or "irrigat" in lower:
                return "Topical - Wash"
            return "Topical - Unspecified"

        return "Other/Unspecified"

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
