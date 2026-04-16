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

v21 changes:
  - _deterministic_delivery_mode: filter intervention_names to EXPERIMENTAL arm only
    using armGroups[type=EXPERIMENTAL].label -> interventions[armGroupLabels] mapping.
    Falls back to all interventions if no arm type data available (older records).
  - PASS1_SYSTEM: explicit instruction to focus on experimental arm route only,
    ignore placebo/comparator/background arm routes.
  - PASS2_SYSTEM Rule 6: clarified multi-route applies to experimental drugs only.

v24 changes:
  - Simplified from ~18 granular categories to 4: Injection/Infusion, Oral,
    Topical, Other. Removed all sub-category distinctions (no more
    IV vs Subcutaneous/Intradermal vs Intramuscular, no Oral-Tablet vs
    Oral-Capsule, etc.). All deterministic mappings, LLM prompts, and
    parse functions updated to output only the 4 simplified categories.

v38 changes:
  - Post-LLM "not specified" override: when Pass 1 says route is not
    specified/not found across all sources but Pass 2 outputs Injection/Infusion,
    force to Other. Fixes LLM ignoring the "do NOT guess" instruction.
  - Radiotracer/imaging deterministic Other returns now set skip_verification=True
    to prevent reconciler from overriding evidence-based deterministic decisions.
"""

import re
import logging
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.delivery_mode")

VALID_VALUES = [
    "Injection/Infusion",
    "Oral",
    "Topical",
    "Other",
]

# Pass 1: Extract ALL route evidence from every source
PASS1_SYSTEM = """You are a clinical pharmacology route-of-administration extraction specialist.

Your task: Search ALL available evidence to find how this drug is administered. Check EVERY source — do NOT stop at the first mention. Different sources may have different levels of specificity.

Extract the following:

1. PROTOCOL ROUTE: What does the ClinicalTrials.gov protocol say about route of administration?
   IMPORTANT: Focus ONLY on the EXPERIMENTAL arm(s) containing the primary investigational drug.
   Do NOT report routes for placebo, active comparator, or standard-of-care background arms.
   Look in the EXPERIMENTAL arm intervention description and the overall protocol description. Quote the exact text.
   If the EXPERIMENTAL arm contains MULTIPLE drugs, report the route for EACH drug separately.
   Do not merge or omit routes for any drug — include oral, topical, and injection routes for
   every drug in the arm, even if they differ.

2. FDA/DRUG LABEL ROUTE: Does any evidence mention an FDA-approved route, drug label route, or prescribing information route? (e.g., "for subcutaneous use", "administered intravenously"). FDA labels are MORE SPECIFIC and MORE RELIABLE than protocol text.

3. LITERATURE ROUTE: Do any PubMed/PMC publications describe how this drug is administered? Quote relevant excerpts.

4. DATABASE ROUTE: Do ChEMBL, UniProt, DRAMP, or other database entries mention route or formulation information?

5. DRUG FORMULATION: Is the drug described as a tablet, capsule, solution, suspension, cream, gel, powder, spray, patch, inhaler, or other formulation? The formulation strongly implies the route.

6. ROUTE CATEGORY: Based on ALL sources above, determine which of these 4 categories the route falls into:
   - Injection/Infusion: IV, intramuscular, subcutaneous, intradermal, intravitreal, any injection or infusion
   - Oral: tablet, capsule, food, drink, any oral route
   - Topical: cream, gel, spray, wash, powder, strip, any topical application
   - Other: inhalation, intranasal, or anything that does not fit the above three

Format your response EXACTLY as:
Protocol Route: [quote or "not specified"]
FDA/Label Route: [quote or "not found"]
Literature Route: [quote or "not found"]
Database Route: [info or "not found"]
Drug Formulation: [formulation or "not specified"]
Most Specific Route: [your determination]"""

# Pass 2: Classify into one of the 4 valid values
PASS2_SYSTEM = """You are a delivery mode classification specialist. You have extracted route-of-administration evidence. Now classify it into EXACTLY ONE delivery mode.

The route facts you extracted:
{pass1_output}

VALID VALUES (choose exactly one):

- Injection/Infusion: IV, intravenous, intramuscular, subcutaneous, intradermal, intravitreal, any injection or infusion route
- Oral: tablet, capsule, food, drink, any oral route
- Topical: cream, gel, spray, wash, powder, strip, any topical application
- Other: inhalation, intranasal, or anything that does not fit the above three categories

CLASSIFICATION RULES:
1. USE THE MOST SPECIFIC SOURCE. FDA label > Literature > Protocol text > Database.
2. Any injection, infusion, IV, IM, SC, intradermal, intravitreal → "Injection/Infusion".
3. Any oral route (tablet, capsule, by mouth, food, drink) → "Oral".
4. Any topical route (cream, gel, ointment, spray, wash, powder, strip, patch, lotion) → "Topical".
5. Inhalation, intranasal, nasal spray, nebulizer, or anything else → "Other".
6. Nutritional formula/shake = Oral. Nasal spray = Other (not Topical).
7. MULTI-ROUTE TRIALS: If the trial tests multiple EXPERIMENTAL drugs that use DIFFERENT routes
   (e.g., one experimental drug given IV and another given orally), list ALL routes comma-separated
   in the same order as the experimental drugs appear.
   Do NOT list the route of placebo, active comparator, or standard-of-care arms.
8. If no route evidence was found from ANY source, classify as "Other" — do NOT guess.

Format your response EXACTLY as:
Delivery Mode: [one of the 4 valid values, exactly as written — or comma-separated if multi-route]
Evidence: [cite which source determined the route]
Reasoning: [brief explanation]"""


# --------------------------------------------------------------------------- #
#  OpenFDA route → delivery mode mapping (v9)
# --------------------------------------------------------------------------- #

_OPENFDA_ROUTE_MAP = {
    "oral": "Oral", "intravenous": "Injection/Infusion",
    "subcutaneous": "Injection/Infusion",
    "intramuscular": "Injection/Infusion",
    "intradermal": "Injection/Infusion",
    "topical": "Topical", "nasal": "Other",
    "intranasal": "Other", "inhalation": "Other",
    "respiratory (inhalation)": "Other", "ophthalmic": "Topical",
    "transdermal": "Topical",
    "intrathecal": "Injection/Infusion",
    "intraperitoneal": "Injection/Infusion",
}

_PROTOCOL_ROUTE_KEYWORDS = {
    # Injection/Infusion (all sub-routes map to single category)
    "subcutaneous": "Injection/Infusion",
    "sub-q": "Injection/Infusion",
    "sc injection": "Injection/Infusion",
    "subcutaneous injection": "Injection/Infusion",
    "subcutaneous infusion": "Injection/Infusion",
    "given subcutaneously": "Injection/Infusion",
    "administered subcutaneously": "Injection/Infusion",
    "intradermal": "Injection/Infusion",
    "intramuscular": "Injection/Infusion",
    "im injection": "Injection/Infusion",
    "intramuscular injection": "Injection/Infusion",
    "injected intramuscularly": "Injection/Infusion",
    "given intramuscularly": "Injection/Infusion",
    "administered intramuscularly": "Injection/Infusion",
    "intravenous": "Injection/Infusion",
    "iv infusion": "Injection/Infusion", "iv push": "Injection/Infusion", "iv drip": "Injection/Infusion",
    "intravenous infusion": "Injection/Infusion", "intravenous injection": "Injection/Infusion",
    "administered intravenously": "Injection/Infusion", "given intravenously": "Injection/Infusion",
    "infused intravenously": "Injection/Infusion",
    "continuous infusion": "Injection/Infusion", "infusion at": "Injection/Infusion",
    "ng/kg/min": "Injection/Infusion", "ug/kg/min": "Injection/Infusion", "mg/kg/min": "Injection/Infusion",
    "mcg/kg/min": "Injection/Infusion", "units/kg/hr": "Injection/Infusion",
    " iv ": "Injection/Infusion", " im ": "Injection/Infusion",
    "sc injection": "Injection/Infusion",
    "sc administration": "Injection/Infusion",
    "sc dose": "Injection/Infusion",
    "auto-injector": "Injection/Infusion",
    "autoinjector": "Injection/Infusion",
    "pen injector": "Injection/Infusion",
    "intravitreal": "Injection/Infusion",
    # Oral (v32: expanded — standalone formulation keywords for multi-route detection)
    "oral tablet": "Oral", "oral capsule": "Oral",
    "oral administration": "Oral", "oral dose": "Oral",
    "oral formulation": "Oral", "oral solution": "Oral",
    "oral suspension": "Oral",
    "by mouth": "Oral", "taken orally": "Oral",
    "administered orally": "Oral", "given orally": "Oral",
    "tablet": "Oral", "capsule": "Oral",
    # Other (intranasal / inhalation)
    "intranasal": "Other", "nasal spray": "Other",
    "inhalation": "Other", "nebulizer": "Other", "nebuliser": "Other",
    # Topical (v31: tightened — require "topical" qualifier or explicit formulation)
    "topical cream": "Topical", "topical gel": "Topical",
    "topical ointment": "Topical", "topical application": "Topical",
    "applied topically": "Topical",
    "mouthwash": "Topical", "mouth rinse": "Topical",
    # v38b: skin prick/skin test REMOVED from injection keywords.
    # Allergy skin prick tests are classified as "Other" by R1 annotators
    # (diagnostic procedure, not therapeutic drug delivery).
    # Previously caused false positives on allergen peptide trials (NCT01719133).
}

_DRUG_CLASS_ROUTES = {
    "semaglutide": "Injection/Infusion",
    "liraglutide": "Injection/Infusion",
    "exenatide": "Injection/Infusion",
    "dulaglutide": "Injection/Infusion",
    "tirzepatide": "Injection/Infusion",
    "insulin": "Injection/Infusion",
    "teriparatide": "Injection/Infusion",
    "abaloparatide": "Injection/Infusion",
    "apraglutide": "Injection/Infusion",
    "teduglutide": "Injection/Infusion",
    "enfuvirtide": "Injection/Infusion",
    "colistin": "Injection/Infusion", "colistimethate": "Injection/Infusion", "daptomycin": "Injection/Infusion",
    "vancomycin": "Injection/Infusion", "teicoplanin": "Injection/Infusion", "aviptadil": "Injection/Infusion",
    "peptide t": "Other", "dapta": "Other",
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
    v31: Radiotracer detection, multi-route oral scan, intervention description
    route extraction, protocol-over-OpenFDA priority.
    """
    intervention_names: list[str] = []
    intervention_descs: list[str] = []  # v31: intervention descriptions for formulation detection
    intervention_types: list[str] = []  # v31: DRUG, BIOLOGICAL, PROCEDURE, etc.
    found_routes: dict[str, tuple[float, bool, list]] = {}  # value → (confidence, skip_verify, evidence)

    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol":
            continue
        if result.raw_data:
            proto = result.raw_data.get("protocol_section", result.raw_data.get("protocolSection", {}))
            arms_mod = proto.get("armsInterventionsModule", {})
            # v21: Identify experimental arm labels to restrict intervention_names to
            # primary investigational drugs only. Falls back to all interventions if
            # no arm type data is available (older CT.gov records).
            arm_groups = arms_mod.get("armGroups", [])
            experimental_labels: set[str] = {
                ag.get("label", "") for ag in arm_groups
                if ag.get("type", "").upper() == "EXPERIMENTAL"
            }
            for interv in arms_mod.get("interventions", []):
                name = interv.get("name", "")
                if not name:
                    continue
                arm_labels = interv.get("armGroupLabels", [])
                # Include if: arm is experimental, or no arm type info available
                if not experimental_labels or any(lbl in experimental_labels for lbl in arm_labels):
                    intervention_names.append(name.lower().strip())
                    desc = interv.get("description", "")
                    if desc:
                        intervention_descs.append(desc.lower().strip())
                    intervention_types.append(interv.get("type", "").upper())

    # v31: Radiotracer / imaging agent detection.
    # PET/SPECT tracers are injected IV but humans classify delivery as "Other"
    # because they're diagnostic, not therapeutic drug delivery.
    _RADIOTRACER_PATTERNS = ["[68ga]", "[18f]", "[99mtc]", "[111in]", "[64cu]",
                             "[90y]", "[177lu]", "68ga-", "18f-", "99mtc-"]
    for name in intervention_names:
        if any(pat in name for pat in _RADIOTRACER_PATTERNS):
            logger.info(f"  delivery_mode: radiotracer detected ('{name}') → Other (skip_verification=True)")
            return FieldAnnotation(
                field_name="delivery_mode", value="Other", confidence=0.90,
                reasoning=f"[Deterministic v38] Radiotracer/imaging agent detected: '{name}'",
                evidence=[], model_name="deterministic", skip_verification=True,
            )
    if "PROCEDURE" in intervention_types and any(
        kw in " ".join(intervention_names) for kw in ["pet", "spect", "imaging", "tracer"]
    ):
        logger.info("  delivery_mode: imaging procedure detected → Other (skip_verification=True)")
        return FieldAnnotation(
            field_name="delivery_mode", value="Other", confidence=0.85,
            reasoning="[Deterministic v38] Imaging/diagnostic procedure detected",
            evidence=[], model_name="deterministic", skip_verification=True,
        )

    # v31: Scan intervention descriptions for oral formulations.
    # Catches multi-drug trials where one drug is oral (tablet/capsule)
    # that the keyword scan on citations would miss.
    _ORAL_FORMULATION_KEYWORDS = ["tablet", "capsule", "oral", "by mouth", "taken orally"]
    _TOPICAL_FORMULATION_KEYWORDS = ["hydrogel", "applied to", "topical application",
                                      "applied topically", "mucosal application",
                                      "eye drop", "ophthalmic drop", "ophthalmic solution",
                                      "transdermal patch", "patch applied", "dental",
                                      "applied to tooth", "applied to teeth", "enamel",
                                      "topical gel", "topical cream", "topical ointment"]
    # v36: Nasal/inhaled delivery from intervention descriptions
    _NASAL_FORMULATION_KEYWORDS = ["nasal spray", "nasal powder", "intranasal",
                                    "nasal administration", "nasal delivery",
                                    "inhaler", "inhalation", "nebulizer"]
    for desc in intervention_descs:
        for kw in _NASAL_FORMULATION_KEYWORDS:
            if kw in desc:
                if "Other" not in found_routes:
                    found_routes["Other"] = (0.92, False, [])
                    logger.info(f"  delivery_mode: found Other/nasal (intervention desc: '{kw}')")
                break
    for desc in intervention_descs:
        for kw in _ORAL_FORMULATION_KEYWORDS:
            if kw in desc:
                if "Oral" not in found_routes:
                    found_routes["Oral"] = (0.90, False, [])
                    logger.info(f"  delivery_mode: found Oral (intervention desc: '{kw}')")
                break
        for kw in _TOPICAL_FORMULATION_KEYWORDS:
            if kw in desc:
                if "Topical" not in found_routes:
                    found_routes["Topical"] = (0.90, False, [])
                    logger.info(f"  delivery_mode: found Topical (intervention desc: '{kw}')")
                break

    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol":
            continue
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
    # v32: "tablet" and "capsule" are ambiguous in title text — e.g. "capsule
    # endoscopy" or "tablet scoring study" — but unambiguous in arm/intervention
    # descriptions. Skip them in titles alongside the existing abbreviations.
    _AMBIGUOUS_KEYWORDS = {" iv ", " im ", " sc ", "tablet", "capsule"}

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

    # v31: If OpenFDA returned "ophthalmic" → Topical but protocol evidence
    # also mentions injection keywords, prefer injection. Many peptide
    # trials with topical/ophthalmic formulations are annotated as
    # injection by humans when the primary route is injection.
    # v32: Only drop Topical when it's Topical+Injection with no other routes.
    # If Oral (or Other) is also detected, keep all routes — it's a multi-drug trial.
    if "Topical" in found_routes and "Injection/Infusion" in found_routes:
        if len(found_routes) == 2:  # Only Topical + Injection, no other routes
            # v35: If multiple interventions exist, preserve both routes —
            # they likely represent different drugs in a multi-drug trial
            if len(intervention_names) > 1:
                logger.info(
                    f"  delivery_mode: preserving Topical+Injection — "
                    f"{len(intervention_names)} interventions detected"
                )
            else:
                topical_conf = found_routes["Topical"][0]
                injection_conf = found_routes["Injection/Infusion"][0]
                # v33: Changed >= to > — equal confidence (e.g. both 0.95 from
                # OpenFDA) should preserve both routes for multi-drug trials
                if injection_conf > topical_conf:
                    del found_routes["Topical"]
                    logger.info("  delivery_mode: dropped Topical in favor of Injection/Infusion (injection priority)")

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

    # v38b: ALL deterministic "Other" returns skip verification.
    # The reconciler consistently overrides correct "Other" to "Injection/Infusion"
    # for intranasal, nasal spray, and unspecified-route trials — hallucinating
    # that these are "parenteral" or "typically injected". This caused 3/9
    # delivery disagreements in v37b validation. Deterministic Other is backed
    # by specific keyword matches (nasal, radiotracer, imaging) and should not
    # be second-guessed by the reconciler.
    is_other = value == "Other"
    skip = is_other or (not (len(routes_list) > 1) and all_skip)

    return FieldAnnotation(
        field_name="delivery_mode", value=value, confidence=min_conf,
        reasoning=f"[Deterministic v38] Collected {len(routes_list)} route(s) from all citations",
        evidence=all_evidence[:5], model_name="deterministic",
        skip_verification=skip,
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
            primary_model = "qwen3:14b"
        else:
            primary_model = None
            for model_key, model_cfg in config.verification.models.items():
                if model_cfg.role == "annotator":
                    primary_model = model_cfg.name
                    break
            if not primary_model:
                primary_model = "qwen3:14b"

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
                value="Other",
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

        # v38: Post-LLM "not specified" override.
        # When Pass 1 reports no route evidence from ANY source but the LLM
        # still guesses Injection/Infusion, force to Other. The PASS2 prompt
        # says "do NOT guess" but small LLMs frequently ignore this rule,
        # defaulting to Injection/Infusion for peptide/vaccine trials.
        #
        # v38b: Fixed markdown parsing — LLM outputs headers like
        # "#### Protocol Route:\n The trial...does not specify..." with
        # content on the NEXT line(s). The regex now grabs multi-line content
        # up to the next section header.
        if value == "Injection/Infusion":
            p1_lower = pass1_text.lower()
            _NO_EVIDENCE_MARKERS = ["not specified", "not found", "no specific",
                                     "does not specify", "does not provide",
                                     "no mention", "not mentioned", "not available",
                                     "no information", "not provided", "no explicit",
                                     "no evidence", "no route", "not stated",
                                     "does not state", "not explicitly"]

            # v38b: Multi-line section extraction — handles both formats:
            #   "Protocol Route: not specified"  (single-line)
            #   "#### Protocol Route:\nThe trial does not specify..."  (markdown)
            # Grab everything from the header to the next section header.
            _SECTION_HEADERS = [
                "protocol route", "fda/label route", "fda route",
                "literature route", "database route",
                "drug formulation", "most specific route", "route category",
            ]
            _SECTION_BOUNDARY = "|".join(re.escape(h) for h in _SECTION_HEADERS)

            def _extract_section(header: str) -> str:
                """Extract section content, handling both single-line and markdown formats."""
                # Strip markdown formatting (####, **, etc.) for matching
                pattern = rf"(?:#{{1,6}}\s*)?(?:\*\*)?{re.escape(header)}(?:\*\*)?:?\s*(.+?)(?={_SECTION_BOUNDARY}|\Z)"
                m = re.search(pattern, p1_lower, re.DOTALL)
                return m.group(1).strip() if m else ""

            def _is_no_evidence(section_text: str) -> bool:
                if not section_text:
                    return True
                return any(marker in section_text for marker in _NO_EVIDENCE_MARKERS)

            proto_text = _extract_section("protocol route")
            fda_text = _extract_section("fda/label route") or _extract_section("fda route")
            lit_text = _extract_section("literature route")

            no_protocol = _is_no_evidence(proto_text)
            no_fda = _is_no_evidence(fda_text)
            no_lit = _is_no_evidence(lit_text)

            # v39: Track override so we can set skip_verification — when all 3
            # sources confirm no evidence, the reconciler should not second-guess.
            not_specified_override = False
            if no_protocol and no_fda and no_lit:
                logger.info(
                    f"  delivery_mode: v39 not-specified override — "
                    f"Pass 1 found no route evidence from any source, "
                    f"forcing Injection/Infusion → Other (skip_verification=True)"
                )
                value = "Other"
                not_specified_override = True

        reasoning = f"[Pass 1 route extraction] {pass1_text[:400]}\n[Pass 2 classification] {pass2_text[:300]}"
        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
            skip_verification=not_specified_override if value == "Other" else False,
        )

    def _infer_from_pass1(self, pass1_text: str) -> str:
        """Fallback: infer delivery mode from Pass 1 extraction if Pass 2 fails."""
        lower = pass1_text.lower()

        # Check for explicit route mentions across all sources
        if any(kw in lower for kw in ["intravenous", " iv ", "iv infusion", "iv push",
                                       "subcutaneous", " sc ", "sub-q", "intradermal",
                                       "intramuscular", " im ", "intravitreal",
                                       "injection", "infusion", "parenteral"]):
            return "Injection/Infusion"
        if any(kw in lower for kw in ["oral", "by mouth", "tablet", "capsule"]):
            return "Oral"
        if any(kw in lower for kw in ["topical", "cream", "gel", "ointment",
                                       "patch", "mouthwash", "lotion"]):
            return "Topical"

        return "Other"

    def _parse_value(self, text: str) -> str:
        match = re.search(r"Delivery Mode:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if not match:
            return "Other"

        raw = match.group(1).strip()

        # v17: Handle comma-separated multi-route values from LLM
        if "," in raw:
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            parsed = [self._parse_single_value(p) for p in parts]
            # Deduplicate while preserving order (v24: dedup all values equally)
            seen = set()
            unique = []
            for v in parsed:
                if v not in seen:
                    seen.add(v)
                    unique.append(v)
            if unique:
                return ", ".join(unique)
            return "Other"

        return self._parse_single_value(raw)

    def _parse_single_value(self, raw: str) -> str:
        """Parse a single delivery mode value (not comma-separated).

        v24: Maps any value to one of 4 categories: Injection/Infusion, Oral, Topical, Other.
        """
        lower = raw.lower().strip()

        # Exact match first (case-insensitive)
        for valid in VALID_VALUES:
            if valid.lower() == lower:
                return valid

        # Injection/Infusion — any injection, IV, infusion, or specific sub-route
        if any(kw in lower for kw in ["iv", "intravenous", "intramuscular", "subcutaneous",
                                       "intradermal", "intravitreal", "injection", "infusion",
                                       "parenteral"]):
            return "Injection/Infusion"

        # Oral — any oral route or formulation
        if any(kw in lower for kw in ["oral", "tablet", "capsule", "food", "drink",
                                       "by mouth"]):
            return "Oral"

        # Topical — v31: tightened keywords. Removed overly broad terms
        # ("strip", "spray", "powder") that triggered false positives for
        # dental strips, skin prick tests, and ophthalmic solutions.
        # Only match when "topical" is explicit or formulation is unambiguous.
        if any(kw in lower for kw in ["topical", "cream", "gel", "ointment",
                                       "patch", "mouthwash", "mouth rinse",
                                       "lotion"]):
            return "Topical"

        return "Other"

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]
