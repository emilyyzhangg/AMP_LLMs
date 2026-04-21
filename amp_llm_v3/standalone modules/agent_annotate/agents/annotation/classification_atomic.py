"""
Classification Annotation Agent — Atomic decomposition (v42, B2).

Shadow-mode sibling of ClassificationAgent. Binary AMP vs Other decision via
three atomic Y/N questions on the trial's protocol plus deterministic registry
hits from peptide_identity research agents (DRAMP, APD, UniProt antimicrobial
annotation).

Design mirrors outcome_atomic's 4-tier structure:

  Tier 0 (deterministic):
    - DRAMP hit for any trial intervention → AMP
    - APD hit → AMP
    - UniProt entry with "antimicrobial" keyword in snippet → AMP
  Tier 1b (one LLM call per trial, not per pub):
    Q1. Does the trial's intervention include a defined peptide sequence?
    Q2. Is the stated mechanism antimicrobial (kills or inhibits a pathogen)?
    Q3. Is the indication or primary endpoint an infectious disease or a
        microbial outcome?
  Tier 3 (aggregator):
    R1. Tier 0 registry hit → AMP (0.95)
    R2. 3/3 YES → AMP (0.90)
    R3. ≥2 YES, 0 NO → AMP (0.80)
    R4. 3/3 NO → Other (0.90)
    R5. ≥2 NO, 0 YES → Other (0.80)
    R6. default → Other (0.55) — binary fallback, no Unknown in this field

No drug-name cheat sheets. No hardcoded lists of known AMPs. Tier 0 hits come
from database agents that search public registries at job time. Tier 1b asks
the LLM reading-comprehension questions, not "is this an AMP".

Stored as field_name="classification_atomic". Gated by
config.orchestrator.classification_atomic_shadow (default OFF).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.annotation import FieldAnnotation
from app.models.research import ResearchResult

logger = logging.getLogger("agent_annotate.annotation.classification_atomic")

VALID_VALUES = ["AMP", "Other"]

# Default Tier 1b model. qwen3:14b is already the primary annotator and
# has proven reliable on reading-comprehension + decision tasks.
_DEFAULT_ATOMIC_MODEL = "qwen3:14b"


# ---- Tier 0: deterministic registry hits --------------------------------- #

@dataclass
class RegistryHits:
    """Structural signals that strongly imply AMP classification."""
    dramp: list[str] = field(default_factory=list)       # list of DRAMP IDs
    apd: list[str] = field(default_factory=list)         # list of APD IDs
    dbaasp: list[str] = field(default_factory=list)      # list of DBAASP IDs
    uniprot_antimicrobial: list[str] = field(default_factory=list)  # UniProt IDs with AMP annotation

    @property
    def any_hit(self) -> bool:
        return bool(self.dramp or self.apd or self.dbaasp or self.uniprot_antimicrobial)


def extract_registry_hits(research_results: list[ResearchResult]) -> RegistryHits:
    """Collect deterministic AMP registry signals from peptide_identity,
    dbaasp, and apd research agents.

    A hit in any of these databases is a structural AMP signal:
      - DRAMP:   dedicated antimicrobial peptide database
      - APD:     Antimicrobial Peptide Database
      - DBAASP:  DataBase of Antimicrobial Activity and Structure of Peptides
      - UniProt: entry whose snippet contains 'antimicrobial' (the curated
                 annotation token used for AMP entries).

    Identification is structural: matches on citation.source_name (preferred)
    or on parent result.agent_name when source_name is absent. This makes the
    extractor robust to minor field-name variations across research-agent
    implementations without hardcoding drug names.
    """
    hits = RegistryHits()
    for result in research_results:
        if result.error:
            continue
        agent = (result.agent_name or "").lower()
        if agent not in ("peptide_identity", "apd", "dbaasp"):
            continue
        for citation in result.citations or []:
            src = (citation.source_name or "").lower()
            ident = (citation.identifier or "").strip()
            snippet = (citation.snippet or "").lower()
            # Prefer explicit source_name; fall back to agent name when absent.
            effective_src = src or agent
            if effective_src == "dramp" and ident:
                hits.dramp.append(ident)
            elif effective_src == "apd" and ident:
                hits.apd.append(ident)
            elif effective_src == "dbaasp" and ident:
                hits.dbaasp.append(ident)
            elif effective_src == "uniprot" and ident and "antimicrobial" in snippet:
                hits.uniprot_antimicrobial.append(ident)
    return hits


# ---- Tier 1b: single LLM call with atomic Y/N questions ------------------ #

ATOMIC_PROMPT = """You are reading a clinical trial description to answer atomic questions about its intervention. Answer each question based ONLY on what the description says. Do not infer beyond the text. If the description does not contain the information, answer UNCLEAR.

Trial identifier: {nct_id}
Intervention name(s): {drug_names}

Trial description:
---
{protocol_text}
---

Questions:
Q1. Does the trial's intervention include a defined peptide sequence (an amino-acid sequence of any length, or a named peptide biological agent)?
    Answer: YES | NO | UNCLEAR
Q2. Is the stated mechanism of action antimicrobial — i.e. directly kills, inhibits growth of, or disrupts a pathogen (bacterium, virus, fungus, parasite)? Host-defense peptides that recruit immune cells against pathogens also count as YES.
    Answer: YES | NO | UNCLEAR
Q3. Is the primary indication or primary endpoint an infectious disease or a microbial outcome (e.g. bacterial load, pathogen clearance, infection cure)?
    Answer: YES | NO | UNCLEAR

Return ONLY a single JSON object in this exact shape, no prose before or after:
{{
  "q1_has_peptide_sequence": "YES|NO|UNCLEAR",
  "q2_antimicrobial_mechanism": "YES|NO|UNCLEAR",
  "q3_infection_indication": "YES|NO|UNCLEAR",
  "evidence_quote": "<ONE verbatim quote from the description supporting the strongest YES answer, ≤30 words. Empty string if no YES.>"
}}"""


@dataclass
class AtomicAnswers:
    q1_has_peptide_sequence: str = "UNCLEAR"
    q2_antimicrobial_mechanism: str = "UNCLEAR"
    q3_infection_indication: str = "UNCLEAR"
    evidence_quote: str = ""

    def yes_count(self) -> int:
        return sum(1 for v in (self.q1_has_peptide_sequence,
                               self.q2_antimicrobial_mechanism,
                               self.q3_infection_indication) if v == "YES")

    def no_count(self) -> int:
        return sum(1 for v in (self.q1_has_peptide_sequence,
                               self.q2_antimicrobial_mechanism,
                               self.q3_infection_indication) if v == "NO")


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_answers(text: str) -> AtomicAnswers:
    """Lenient JSON parse. Malformed → all UNCLEAR."""
    if not text:
        return AtomicAnswers()
    t = text.strip()
    payload: Optional[dict] = None
    try:
        payload = json.loads(t)
    except json.JSONDecodeError:
        m = _JSON_OBJ_RE.search(t)
        if m:
            try:
                payload = json.loads(m.group(0))
            except json.JSONDecodeError:
                payload = None
    if not payload:
        return AtomicAnswers()

    def norm(v):
        if not isinstance(v, str):
            return "UNCLEAR"
        v = v.strip().upper().replace(" ", "_").replace("-", "_")
        return v if v in ("YES", "NO", "UNCLEAR") else "UNCLEAR"

    return AtomicAnswers(
        q1_has_peptide_sequence=norm(payload.get("q1_has_peptide_sequence", "")),
        q2_antimicrobial_mechanism=norm(payload.get("q2_antimicrobial_mechanism", "")),
        q3_infection_indication=norm(payload.get("q3_infection_indication", "")),
        evidence_quote=str(payload.get("evidence_quote", "") or "")[:300],
    )


# ---- Protocol text extraction -------------------------------------------- #

def _extract_protocol_text(research_results: list[ResearchResult], max_chars: int = 2400) -> tuple[str, list[str]]:
    """Pull the clinical_protocol description + condition + intervention names.

    Returns (protocol_text, drug_names). Text is capped at max_chars so the
    atomic prompt stays compact.
    """
    drug_names: list[str] = []
    text_parts: list[str] = []
    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol" or not result.raw_data:
            continue
        proto = result.raw_data.get(
            "protocol_section",
            result.raw_data.get("protocolSection", {}),
        )
        id_mod = proto.get("identificationModule", {})
        title = (id_mod.get("briefTitle") or id_mod.get("officialTitle") or "").strip()
        if title:
            text_parts.append(f"Title: {title}")

        desc_mod = proto.get("descriptionModule", {})
        brief_summary = (desc_mod.get("briefSummary") or "").strip()
        if brief_summary:
            text_parts.append(f"Summary: {brief_summary}")
        detailed = (desc_mod.get("detailedDescription") or "").strip()
        if detailed:
            text_parts.append(f"Description: {detailed}")

        conditions_mod = proto.get("conditionsModule", {})
        conds = conditions_mod.get("conditions", []) or []
        if conds:
            text_parts.append(f"Conditions: {', '.join(c for c in conds if c)}")

        arms_mod = proto.get("armsInterventionsModule", {})
        for interv in arms_mod.get("interventions", []) or []:
            name = (interv.get("name") or "").strip()
            if name:
                drug_names.append(name)
                itype = (interv.get("type") or "").strip()
                idesc = (interv.get("description") or "").strip()
                if itype or idesc:
                    text_parts.append(f"Intervention ({name}, {itype}): {idesc[:400]}")

        outcomes_mod = proto.get("outcomesModule", {})
        primaries = outcomes_mod.get("primaryOutcomes", []) or []
        for po in primaries[:3]:
            measure = (po.get("measure") or "").strip()
            if measure:
                text_parts.append(f"Primary outcome: {measure}")

    body = "\n\n".join(text_parts)
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + " …"
    return body, drug_names


# ---- Aggregator ---------------------------------------------------------- #

@dataclass
class ClassificationAgg:
    value: str
    rule_name: str
    rule_description: str
    confidence: float
    trace: list[str] = field(default_factory=list)


def aggregate(hits: RegistryHits, answers: AtomicAnswers) -> ClassificationAgg:
    """Apply R1–R6 in order, first match wins."""
    trace = [
        f"registry: dramp={len(hits.dramp)} apd={len(hits.apd)} "
        f"dbaasp={len(hits.dbaasp)} uniprot_amp={len(hits.uniprot_antimicrobial)}",
        f"atomic: q1={answers.q1_has_peptide_sequence} "
        f"q2={answers.q2_antimicrobial_mechanism} q3={answers.q3_infection_indication}",
    ]

    if hits.any_hit:
        sources = []
        if hits.dramp: sources.append(f"DRAMP[{','.join(hits.dramp[:3])}]")
        if hits.apd: sources.append(f"APD[{','.join(hits.apd[:3])}]")
        if hits.dbaasp: sources.append(f"DBAASP[{','.join(hits.dbaasp[:3])}]")
        if hits.uniprot_antimicrobial:
            sources.append(f"UniProt-AMP[{','.join(hits.uniprot_antimicrobial[:3])}]")
        return ClassificationAgg(
            value="AMP",
            rule_name="R1",
            rule_description=f"registry hit: {' + '.join(sources)}",
            confidence=0.95,
            trace=trace + [f"R1 fired: deterministic registry hit"],
        )

    yes = answers.yes_count()
    no = answers.no_count()

    if yes == 3:
        return ClassificationAgg(
            value="AMP", rule_name="R2",
            rule_description="3/3 atomic YES",
            confidence=0.90,
            trace=trace + ["R2 fired: all three questions YES"],
        )
    if no == 3:
        return ClassificationAgg(
            value="Other", rule_name="R4",
            rule_description="3/3 atomic NO",
            confidence=0.90,
            trace=trace + ["R4 fired: all three questions NO"],
        )
    if yes >= 2 and no == 0:
        return ClassificationAgg(
            value="AMP", rule_name="R3",
            rule_description=f"{yes}/3 YES, 0 NO",
            confidence=0.80,
            trace=trace + [f"R3 fired: {yes} YES, 0 NO"],
        )
    if no >= 2 and yes == 0:
        return ClassificationAgg(
            value="Other", rule_name="R5",
            rule_description=f"{no}/3 NO, 0 YES",
            confidence=0.80,
            trace=trace + [f"R5 fired: {no} NO, 0 YES"],
        )

    # Default: binary fallback. Without clear signals, classification is Other
    # because AMP carries a specific claim that requires affirmative evidence.
    return ClassificationAgg(
        value="Other", rule_name="R6",
        rule_description="mixed/unclear atomic answers; default Other",
        confidence=0.55,
        trace=trace + [f"R6 fired: {yes} YES, {no} NO, {3-yes-no} UNCLEAR → default Other"],
    )


# ---- Agent --------------------------------------------------------------- #

class ClassificationAtomicAgent(BaseAnnotationAgent):
    """v42 atomic sibling of ClassificationAgent.

    Runs in shadow mode under field_name="classification_atomic". The
    orchestrator skips this agent unless
    config.orchestrator.classification_atomic_shadow is True.
    """

    field_name = "classification_atomic"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        # Tier 0
        hits = extract_registry_hits(research_results)

        # Tier 1b — one LLM call on protocol text
        protocol_text, drug_names = _extract_protocol_text(research_results)
        answers = AtomicAnswers()
        model_used = ""
        llm_error = ""
        if protocol_text and not hits.any_hit:
            # Skip LLM if registry already decided — Tier 0 short-circuit.
            config = config_service.get()
            model = (
                getattr(config.orchestrator, "classification_atomic_model", None)
                or _DEFAULT_ATOMIC_MODEL
            )
            model_used = model
            prompt = ATOMIC_PROMPT.format(
                nct_id=nct_id,
                drug_names=", ".join(drug_names) if drug_names else "(none listed)",
                protocol_text=protocol_text,
            )
            try:
                resp = await ollama_client.generate(
                    model=model,
                    prompt=prompt,
                    temperature=0.0,
                )
                raw = resp.get("response", "") if isinstance(resp, dict) else str(resp)
                answers = _parse_answers(raw)
            except Exception as e:
                llm_error = f"assessor_exception: {e}"
                logger.warning("classification_atomic %s LLM failed: %s", nct_id, e)

        agg = aggregate(hits, answers)

        reasoning_lines = [
            f"[ATOMIC-CLS {agg.rule_name}] {agg.value} (conf={agg.confidence:.2f})",
            f"  rule: {agg.rule_description}",
        ]
        reasoning_lines.extend(f"  {line}" for line in agg.trace)
        if answers.evidence_quote:
            reasoning_lines.append(f"  quote: \"{answers.evidence_quote[:120]}\"")
        if llm_error:
            reasoning_lines.append(f"  llm_error: {llm_error}")

        return FieldAnnotation(
            field_name=self.field_name,
            value=agg.value,
            confidence=agg.confidence,
            reasoning="\n".join(reasoning_lines),
            evidence=[],
            model_name=f"atomic-cls-{model_used}" if model_used else "atomic-cls-deterministic",
            skip_verification=True,
            evidence_grade="deterministic" if agg.rule_name == "R1" else "llm",
        )
