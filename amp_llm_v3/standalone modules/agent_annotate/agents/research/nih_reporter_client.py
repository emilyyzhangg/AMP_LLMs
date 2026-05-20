"""
NIH RePORTER Research Agent (v42.7.6, 2026-04-26).

Queries NIH RePORTER for funded research grants associated with a drug
or peptide intervention. RePORTER indexes grants from NIH, AHRQ, CDC,
and FDA — i.e. the full footprint of US federally funded health
research. Grant abstracts often discuss the same drug a clinical trial
is testing.

Why this matters for the pipeline:
  Drug intervention names that match RePORTER projects tell us the
  intervention is the subject of academic / federally-funded research.
  Even better: a project's end_date and the absence of follow-on grants
  is a weak signal that the drug program may have been discontinued
  (the converse is stronger — ongoing funding implies an active drug
  program). Funding context is orthogonal to SEC EDGAR (sponsor
  disclosures) and FDA Drugs (regulatory approval), so the three sources
  triangulate.

API:
  POST https://api.reporter.nih.gov/v2/projects/search
  Documentation: https://api.reporter.nih.gov/

The criteria field that *actually* filters is ``advanced_text_search``;
the documented ``clinical_trial_ids`` filter silently no-ops (returns
the entire 2.9M-row corpus). NCT IDs themselves rarely appear in grant
abstracts, so we search by intervention name (drug/biologic) rather
than by NCT.

Free, no key. No documented rate limit; we make at most 3 requests per
trial during the per-intervention loop.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx

from agents.base import BaseResearchAgent
from agents.research.drug_cache import drug_cache
from agents.research.resolved_names import extract_interventions, query_names
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.nih_reporter")

NIH_REPORTER_URL = "https://api.reporter.nih.gov/v2/projects/search"

_INCLUDE_FIELDS = [
    "ProjectNum", "ContactPiName", "OrganizationName", "ProjectTitle",
    "FiscalYear", "AwardAmount", "ProjectStartDate", "ProjectEndDate",
    "AwardNoticeDate", "AbstractText",
]


_SKIP = {"placebo", "saline", "vehicle", "normal saline", "standard of care"}


def _drug_interventions(metadata: Optional[dict]) -> list[dict]:
    """DRUG/BIOLOGICAL interventions with their Lever-4 resolved names.

    Keeps the type filter (bare-string items with no type included) and drops
    placebo/vehicle; carries ``resolved`` canonical names for query fallback.
    """
    out: list[dict] = []
    for interv in extract_interventions(metadata):
        if interv["name"].lower() in _SKIP:
            continue
        if interv["type"] and interv["type"] not in ("DRUG", "BIOLOGICAL"):
            continue
        out.append(interv)
    return out


def _extract_intervention_names(metadata: Optional[dict]) -> list[str]:
    """Backward-compatible flat-name view (raw names only)."""
    return [i["name"] for i in _drug_interventions(metadata)]


class NIHRePORTERClient(BaseResearchAgent):
    """Search NIH RePORTER for federally funded grants on a drug intervention."""

    agent_name = "nih_reporter"
    sources = ["nih_reporter"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations: list = []
        raw_data: dict = {}
        # v42.9 (P1): fall back to Lever-4 resolved canonical names so a trial
        # code with no grants under it still matches the funded generic name.
        interventions = _drug_interventions(metadata)

        if not interventions:
            return ResearchResult(
                agent_name=self.agent_name, nct_id=nct_id,
                citations=[], raw_data={"note": "No interventions to search"},
            )

        async with httpx.AsyncClient(
            timeout=20,
            headers={"Content-Type": "application/json"},
        ) as client:
            for interv in interventions[:3]:
                per = None
                for nm in query_names(interv):
                    async def compute(intv=nm):
                        return await self._fetch_intervention(client, intv)

                    if drug_cache.is_enabled():
                        candidate = await drug_cache.get_or_compute(
                            self.agent_name, nm, compute,
                        )
                    else:
                        candidate = await compute()

                    per = candidate
                    if candidate["citations"]:
                        break  # raw name or first resolved name that hits wins

                if per:
                    citations.extend(per["citations"])
                    raw_data.update(per["raw_data"])

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _fetch_intervention(self, client: httpx.AsyncClient, intervention: str) -> dict:
        """Search RePORTER for one drug name. Pure function of name."""
        citations: list = []
        raw_data: dict = {}

        body = {
            "criteria": {
                "advanced_text_search": {
                    "operator": "and",
                    "search_field": "all",
                    "search_text": intervention,
                },
            },
            "limit": 5,
            "include_fields": _INCLUDE_FIELDS,
        }
        try:
            resp = await client.post(NIH_REPORTER_URL, json=body)
            if resp.status_code != 200:
                raw_data[f"nih_reporter_{intervention}_status"] = resp.status_code
                return {"citations": citations, "raw_data": raw_data}

            data = resp.json()
            results = data.get("results", []) or []
            total = data.get("meta", {}).get("total", len(results))
            raw_data[f"nih_reporter_{intervention}_count"] = total

            for project in results[:3]:
                proj_num = project.get("project_num", "")
                title = (project.get("project_title") or "").strip()
                pi = (project.get("contact_pi_name") or "").strip()
                org = (project.get("organization") or {}).get("org_name") \
                    if isinstance(project.get("organization"), dict) \
                    else (project.get("organization_name") or "")
                fiscal_year = project.get("fiscal_year", "")
                award = project.get("award_amount", "")
                start = (project.get("project_start_date") or "")[:10]
                end = (project.get("project_end_date") or "")[:10]

                snippet_parts = [
                    f"Project: {proj_num}",
                    f"PI: {pi}",
                    f"Organization: {org}",
                    f"Fiscal year: {fiscal_year}",
                ]
                if award:
                    snippet_parts.append(f"Award: ${award:,}" if isinstance(award, int) else f"Award: ${award}")
                if start:
                    snippet_parts.append(f"Start: {start}")
                if end:
                    snippet_parts.append(f"End: {end}")
                if total > 1:
                    snippet_parts.append(f"({total} total NIH-funded projects matching '{intervention}')")

                project_url = (
                    f"https://reporter.nih.gov/search/results/?text_terms={intervention.replace(' ', '+')}"
                )
                citations.append(SourceCitation(
                    source_name="nih_reporter",
                    source_url=project_url,
                    identifier=f"NIH:{proj_num}" if proj_num else f"NIH:{intervention}",
                    title=f"{title or 'NIH Project'} ({pi or org or 'unknown PI'})",
                    snippet="\n".join(snippet_parts),
                    quality_score=self.compute_quality_score("nih_reporter"),
                    retrieved_at=datetime.utcnow().isoformat(),
                ))

            raw_data[f"nih_reporter_{intervention}_funded"] = bool(results)

        except Exception as e:
            logger.warning(f"NIH RePORTER search failed for {intervention!r}: {e}")
            raw_data[f"nih_reporter_{intervention}_error"] = str(e)

        return {"citations": citations, "raw_data": raw_data}
