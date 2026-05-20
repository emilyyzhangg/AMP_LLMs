"""
Epitope resolver — recover vaccine/epitope peptide sequences the rest of the
pipeline can't reach.

Why this exists
---------------
The dominant sequence-field miss class is tumor-antigen / viral T-cell epitopes
used in cancer and HIV vaccines (e.g. gp100, p53, MAGE). Those short peptides do
not live in the databases we query (DBAASP/APD are antimicrobial; ChEMBL/UniProt
index whole drugs/proteins, not vaccine epitopes), and they are not in the
abstracts we fetch — so the agent returns N/A.

But the trial PROTOCOL frequently names the antigen and the exact residue range,
e.g. "gp100:209-217 and gp100:280-288 peptides", "p53:264-272 wild type peptide".
When it does, the epitope is exactly ``UniProt(antigen)[start:end]`` — a
deterministic slice of the canonical protein at the residues the protocol itself
specifies. That is a precise, single-answer retrieval: it does NOT enumerate an
antigen's whole epitope set (which would game the set-containment sequence
scorer), it returns the one peptide the protocol describes.

Limitations (by design):
- Anchor-modified epitopes (e.g. gp100:209-217(210M)) differ from the wild-type
  slice by the engineered residue and will not match — acceptable.
- Position numbering follows the canonical (precursor) UniProt sequence; trials
  that number from the mature chain will be off and are dropped by the sanity
  checks rather than mis-resolved.
"""

from __future__ import annotations

import re
from typing import Optional

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"

# An MHC class-I epitope is ~8-11 aa; class-II / synthetic-long-peptides run
# longer. Anything outside this window is almost certainly not an epitope range
# (it's a dose range, a date, a cohort size, etc.).
_MIN_EPITOPE_LEN = 7
_MAX_EPITOPE_LEN = 35

# Tokens that look like an antigen but are actually generic words; never treat
# these as a protein to resolve.
_STOP_ANTIGENS = {
    "phase", "day", "days", "week", "weeks", "month", "months", "year", "years",
    "dose", "doses", "cohort", "arm", "group", "age", "aged", "grade", "stage",
    "page", "table", "figure", "section", "version", "part", "step", "cycle",
    "hour", "hours", "minute", "minutes", "patient", "patients", "subject",
    "subjects", "site", "sites", "visit", "mg", "kg", "ml", "study",
}

# Antigen tokens longer than this are almost always prose, not a gene/antigen.
_MAX_ANTIGEN_LEN = 24

# Peptide HORMONES and their fragments use peptide-relative numbering by
# convention — "GLP-1(7-36)" means residues 7-36 of the GLP-1 peptide, NOT of
# the proglucagon precursor. Slicing the UniProt precursor at those positions
# yields the WRONG sequence. These are already handled correctly (with the right
# numbering) by sequence.py's _KNOWN_SEQUENCES, so the epitope resolver must skip
# them. The resolver is scoped to genuine tumor/viral antigens (gp100, p53,
# HER-2, MAGE, NY-ESO-1, …) whose epitopes ARE numbered on the precursor.
_HORMONE_ANTIGENS = {
    "glp1", "glp", "gip", "exendin", "exenatide", "glucagon", "oxyntomodulin",
    "insulin", "proinsulin", "cpeptide", "pyy", "peptideyy", "npy", "amylin",
    "pramlintide", "angiotensin", "bradykinin", "calcitonin", "pth", "pthrp",
    "teriparatide", "secretin", "somatostatin", "ghrelin", "leptin", "vip",
    "ll37", "cathelicidin", "natriuretic", "bnp", "anp", "cnp", "substancep",
    "vasopressin", "oxytocin", "gnrh", "lhrh",
}


def _is_hormone_antigen(antigen: str) -> bool:
    """True for peptide-hormone antigen tokens (peptide-relative numbering)."""
    norm = re.sub(r"[^a-z0-9]", "", antigen.lower())
    # GLP-2 is a hormone too ("glp2"); the bare "glp" entry covers glp-1/glp-2.
    return norm in _HORMONE_ANTIGENS or norm.startswith("glp")

# Two adjacency patterns, both high-precision:
#   <antigen>:<start>-<end>            e.g. gp100:209-217
#   <antigen> (<start>-<end>)          e.g. p53 (264-272)   /  p53:264 - 272
_COLON_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9\-]{0,23})\s*:\s*(\d{1,4})\s*[-–]\s*(\d{1,4})"
)
_PAREN_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9\-]{0,23})\s*(?:peptide\s*)?\(\s*(\d{1,4})\s*[-–]\s*(\d{1,4})\s*\)"
)


def extract_epitope_specs(text: str) -> list[tuple[str, int, int]]:
    """Find (antigen, start, end) epitope specifications in protocol text.

    Only accepts antigen-adjacent residue ranges (colon- or paren-delimited) with
    a plausible epitope length. De-duplicated, order-preserving.
    """
    if not text:
        return []
    specs: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int, int]] = set()
    for rx in (_COLON_RE, _PAREN_RE):
        for m in rx.finditer(text):
            antigen = m.group(1).strip().strip("-")
            try:
                start, end = int(m.group(2)), int(m.group(3))
            except (ValueError, TypeError):
                continue
            if not antigen or antigen.lower() in _STOP_ANTIGENS:
                continue
            if len(antigen) < 2 or len(antigen) > _MAX_ANTIGEN_LEN:
                continue
            # Skip peptide hormones — their "(7-36)" notation is peptide-relative,
            # not precursor-relative, so a UniProt slice would be wrong. The
            # _KNOWN_SEQUENCES path handles these with the correct numbering.
            if _is_hormone_antigen(antigen):
                continue
            # Must be a forward range of plausible epitope length.
            if not (start < end):
                continue
            length = end - start + 1
            if not (_MIN_EPITOPE_LEN <= length <= _MAX_EPITOPE_LEN):
                continue
            key = (antigen.lower(), start, end)
            if key in seen:
                continue
            seen.add(key)
            specs.append((antigen, start, end))
    return specs


async def _uniprot_canonical_sequence(
    antigen: str, client: httpx.AsyncClient
) -> Optional[tuple[str, str]]:
    """Resolve an antigen name to (accession, canonical_sequence) for human.

    Prefers reviewed (Swiss-Prot) entries and a gene/name match with the antigen
    token, so "p53" → P04637 (not p73) and "gp100" → P40967.
    """
    resp = await resilient_get(
        UNIPROT_SEARCH_URL,
        client=client,
        params={
            "query": f"{antigen} AND organism_id:9606 AND reviewed:true",
            "fields": "accession,gene_names,protein_name,sequence",
            "format": "json",
            "size": 5,
        },
    )
    if resp.status_code != 200:
        return None
    results = resp.json().get("results", []) or []
    if not results:
        return None
    a_low = antigen.lower().replace("-", "")

    def _entry_seq(e):
        return (e.get("sequence", {}) or {}).get("value", "")

    # Prefer an entry whose gene name or protein name contains the antigen token.
    for e in results:
        genes = " ".join(
            g.get("geneName", {}).get("value", "")
            for g in (e.get("genes", []) or [])
        ).lower().replace("-", "")
        pd = e.get("proteinDescription", {}) or {}
        pname = (
            (pd.get("recommendedName", {}) or {}).get("fullName", {}) or {}
        ).get("value", "").lower().replace("-", "")
        if a_low and (a_low in genes or a_low in pname):
            seq = _entry_seq(e)
            if seq:
                return e.get("primaryAccession", ""), seq
    # Fall back to the top reviewed hit.
    seq = _entry_seq(results[0])
    if seq:
        return results[0].get("primaryAccession", ""), seq
    return None


async def resolve_epitope(
    antigen: str, start: int, end: int, client: httpx.AsyncClient
) -> Optional[dict]:
    """Resolve one (antigen, start, end) spec to a sliced epitope sequence."""
    resolved = await _uniprot_canonical_sequence(antigen, client)
    if not resolved:
        return None
    accession, seq = resolved
    if end > len(seq):
        return None  # position numbering doesn't fit this isoform — drop it
    epitope = seq[start - 1:end]  # 1-based inclusive
    if len(epitope) < _MIN_EPITOPE_LEN:
        return None
    return {
        "antigen": antigen,
        "accession": accession,
        "start": start,
        "end": end,
        "sequence": epitope,
    }


class EpitopeResolverAgent(BaseResearchAgent):
    """Resolve protocol-specified epitope ranges to exact peptide sequences."""

    agent_name = "epitope_resolver"
    sources = ["epitope_resolver"]

    async def research(
        self, nct_id: str, metadata: Optional[dict] = None
    ) -> ResearchResult:
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        # Pull every text field the orchestrator makes available: intervention
        # names/descriptions, title, and the protocol summary/description.
        text_parts: list[str] = []
        if metadata:
            text_parts.append(str(metadata.get("title", "") or ""))
            text_parts.append(str(metadata.get("brief_summary", "") or ""))
            text_parts.append(str(metadata.get("detailed_description", "") or ""))
            for iv in (metadata.get("interventions", []) or []):
                if isinstance(iv, dict):
                    text_parts.append(str(iv.get("name", "") or ""))
                    text_parts.append(str(iv.get("description", "") or ""))
                elif isinstance(iv, str):
                    text_parts.append(iv)
        text = "\n".join(p for p in text_parts if p)

        specs = extract_epitope_specs(text)
        if not specs:
            return ResearchResult(
                agent_name=self.agent_name, nct_id=nct_id,
                citations=[], raw_data={"note": "No epitope specs in protocol text"},
            )

        from datetime import datetime
        resolved_seqs: list[dict] = []
        async with httpx.AsyncClient(timeout=20) as client:
            for antigen, start, end in specs[:6]:
                try:
                    r = await resolve_epitope(antigen, start, end, client)
                except Exception:
                    r = None
                if not r:
                    continue
                resolved_seqs.append(r)
                citations.append(SourceCitation(
                    source_name="epitope_resolver",
                    source_url=f"https://www.uniprot.org/uniprotkb/{r['accession']}/entry",
                    identifier=f"{r['accession']}:{start}-{end}",
                    title=f"{antigen} {start}-{end} epitope ({len(r['sequence'])} aa)",
                    snippet=(
                        f"{antigen} residues {start}-{end} of UniProt {r['accession']} "
                        f"= {r['sequence']}"
                    ),
                    quality_score=self.compute_quality_score("epitope_resolver"),
                    retrieved_at=datetime.utcnow().isoformat(),
                ))

        if resolved_seqs:
            raw_data["epitope_resolver_sequences"] = resolved_seqs
        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )
