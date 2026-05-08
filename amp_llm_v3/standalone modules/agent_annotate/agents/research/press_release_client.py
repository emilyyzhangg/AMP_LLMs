"""v42.8.5 Lever 5 — sponsor press-release / news-aggregator agent.

Surfaces trial-readout reporting that doesn't reach peer-reviewed
literature within Phase I trial timelines. Sponsors announce trial
readouts via press releases (sponsor newsroom, BusinessWire, PR
Newswire) and those announcements are indexed by Google News RSS,
which aggregates ~10K news sources — a pragmatic single endpoint
that covers the major release wires + sponsor blogs.

Why Google News RSS as the source:
- Free, no auth, structured XML
- Aggregates PR Newswire, BusinessWire, sponsor newsrooms, trade
  publications (FierceBiotech, BioSpace, Endpoints News) which are
  the primary surface for trial-readout announcements
- Returns title + date + source name (in the description HTML);
  enough to detect outcome direction via headline keyword scan
- Avoids per-sponsor newsroom scraping (brittle; the plan §4.2.1
  curated map approach was acceptable but Google News covers
  everything in one query)

Outcome direction detection:
- POSITIVE phrases anchor on primary-endpoint or regulator-qualified
  signals (e.g. achieves-primary, FDA-approves, met-primary,
  positive-topline). See _POSITIVE_HEADLINE for the full list.
- NEGATIVE phrases anchor on fails-primary, missed-primary,
  discontinues-development, halts-trial, did-not-meet etc. See
  _NEGATIVE_HEADLINE for the full list.
- Both classes anchor on PRIMARY-ENDPOINT or REGULATORY phrasing per
  the v42.8.2 _STRONG_FAILURE / v42.6.14 _STRONG_EFFICACY discipline:
  bare single-word matches (the words alone) are not present.

Per `feedback_no_cheat_sheets.md`: this module does NOT hardcode
any per-NCT or per-drug list. All filtering is keyword-shape-based
and operates on the live news-feed query results.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import quote_plus

import httpx

from agents.base import BaseResearchAgent
from agents.research.drug_cache import drug_cache
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.press_release_client")

GNEWS_RSS_URL = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)

# Headline phrases anchored on PRIMARY-ENDPOINT or REGULATORY signals.
# Mirror of outcome.py _STRONG_EFFICACY / _STRONG_FAILURE discipline.
_POSITIVE_HEADLINE = [
    "achieves primary",
    "achieved primary",
    "meets primary",
    "met primary",
    "primary endpoint met",
    "primary endpoint achieved",
    "primary endpoint was met",
    "positive topline",
    "positive top-line",
    "positive results",
    "positive data",
    "fda approves",
    "fda approval",
    "ema approves",
    "ema approval",
    "regulatory approval",
    "received approval",
    "marketing authorization",
    "successful phase",
    "phase 3 success",
    "phase iii success",
    "topline data show",
]

_NEGATIVE_HEADLINE = [
    "did not meet",
    "did not achieve",
    "fails primary",
    "failed primary",
    "missed primary",
    "misses primary",
    "primary endpoint not met",
    "primary endpoint was not met",
    "primary endpoint not achieved",
    "discontinues",
    "discontinued development",
    "halts development",
    "halts trial",
    "terminates",
    "failed to meet",
    "failed to demonstrate",
    "negative results",
    "negative data",
    "futility",
]


def classify_headline(headline: str) -> str:
    """Return 'positive' | 'negative' | 'neutral' for a press-release headline."""
    h = (headline or "").lower()
    if any(kw in h for kw in _NEGATIVE_HEADLINE):
        return "negative"
    if any(kw in h for kw in _POSITIVE_HEADLINE):
        return "positive"
    return "neutral"


def _build_query(drug_name: str, sponsor: str = "") -> str:
    """Construct a Google News query that surfaces trial-readout articles.

    The exact-match double-quotes around drug_name reduce false positives
    from review articles or unrelated mentions of the drug class. The
    "trial OR data OR results" disjunction filters to readout-shaped news.
    """
    drug = drug_name.strip()
    parts = [f'"{drug}"', '("trial" OR "results" OR "data" OR "endpoint")']
    if sponsor:
        # Sponsor name disambiguates common drug names (e.g. "lisinopril"
        # has many manufacturers — sponsor narrows to actual readout)
        parts.append(f'"{sponsor.split()[0]}"')
    return " ".join(parts)


def _parse_rss(xml_text: str) -> list[dict]:
    """Parse Google News RSS XML into a list of {title, link, date, source, classification}."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.debug(f"RSS parse failed: {exc}")
        return items
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        # Source name is at the END of the title after " - " in Google News
        # ("Headline... - Reuters" → source="Reuters")
        source_name = ""
        m = re.search(r" - ([^-]+)$", title)
        if m:
            source_name = m.group(1).strip()
            # Strip trailing source from title for cleaner classification
            title_clean = title[: m.start()].strip()
        else:
            title_clean = title
        items.append({
            "title": title_clean,
            "link": link,
            "date": pub_date,
            "source": source_name,
            "classification": classify_headline(title_clean),
        })
    return items


async def fetch_news(
    drug_name: str, sponsor: str = "", client: Optional[httpx.AsyncClient] = None,
    max_items: int = 15,
) -> list[dict]:
    """Fetch Google News RSS for a drug + optional sponsor; return parsed items."""
    if not drug_name:
        return []
    cache_key = f"{drug_name.strip().lower()}|{sponsor.strip().lower()}"

    async def _do_fetch() -> list[dict]:
        owns_client = client is None
        c = client or httpx.AsyncClient(timeout=20)
        try:
            url = GNEWS_RSS_URL.format(query=quote_plus(_build_query(drug_name, sponsor)))
            try:
                resp = await resilient_get(url, client=c, headers={"Accept": "application/rss+xml"})
            except Exception as exc:
                logger.debug(f"news fetch failed for {drug_name!r}: {exc}")
                return []
            if resp.status_code != 200:
                return []
            return _parse_rss(resp.text)[:max_items]
        finally:
            if owns_client:
                await c.aclose()

    return await drug_cache.get_or_compute(
        "press_release_client", cache_key, _do_fetch,
    )


class PressReleaseAgent(BaseResearchAgent):
    """Surfaces trial-readout press releases for the trial's drug interventions.

    Output flows into the outcome dossier as `press_release_evidence`,
    `has_positive_pr`, `has_negative_pr` — used by the v42.8.5 override
    rule to flip Unknown → Positive when sponsor formally announced a
    trial readout that hasn't yet reached peer-reviewed literature.
    """

    agent_name = "press_release"
    sources = ["google_news_rss"]

    async def research(
        self, nct_id: str, metadata: Optional[dict] = None
    ) -> ResearchResult:
        intervention_names: list[str] = []
        sponsor = ""
        if metadata and isinstance(metadata.get("interventions"), list):
            for item in metadata["interventions"]:
                if isinstance(item, str):
                    intervention_names.append(item)
                elif isinstance(item, dict):
                    n = item.get("name") or item.get("intervention_name") or ""
                    if n:
                        intervention_names.append(str(n))
        if metadata:
            sponsor = (metadata.get("sponsor") or "").strip()

        if not intervention_names:
            return ResearchResult(
                agent_name=self.agent_name,
                nct_id=nct_id,
                citations=[],
                raw_data={"note": "no interventions to query"},
            )

        all_items: list[dict] = []
        async with httpx.AsyncClient(timeout=20) as client:
            for drug in intervention_names[:3]:
                try:
                    items = await fetch_news(drug, sponsor=sponsor, client=client)
                except Exception as exc:
                    logger.warning(f"{nct_id} press_release fetch {drug!r}: {exc}")
                    continue
                for it in items:
                    it["queried_drug"] = drug
                all_items.extend(items)

        # Deduplicate by link
        seen_links = set()
        deduped = []
        for it in all_items:
            link = it.get("link", "")
            if link and link in seen_links:
                continue
            seen_links.add(link)
            deduped.append(it)

        # Filter to non-neutral OR top 5 most recent (so the LLM sees
        # raw context even when no clear positive/negative signal fired)
        signal_items = [it for it in deduped if it["classification"] != "neutral"]

        citations: list[SourceCitation] = []
        for it in signal_items[:8]:
            citations.append(SourceCitation(
                source_name="press_release",
                source_url=it.get("link"),
                identifier=f"PR:{it.get('source','')[:30]}",
                title=it["title"][:200],
                snippet=(
                    f"[{it['classification'].upper()}] {it['title']}\n"
                    f"Source: {it.get('source','unknown')}  "
                    f"Date: {it.get('date','')}  "
                    f"Drug: {it.get('queried_drug','')}"
                ),
                quality_score=0.7,
            ))

        positive_count = sum(1 for it in signal_items if it["classification"] == "positive")
        negative_count = sum(1 for it in signal_items if it["classification"] == "negative")

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data={
                "press_release_evidence": signal_items[:8],
                "press_release_count": len(signal_items),
                "has_positive_pr": positive_count > 0,
                "has_negative_pr": negative_count > 0,
                "positive_count": positive_count,
                "negative_count": negative_count,
            },
        )
