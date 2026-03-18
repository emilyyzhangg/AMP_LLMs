"""
Web Context Research Agent.

Searches DuckDuckGo for broader context about clinical trials and their
outcomes.

Uses the DuckDuckGo HTML lite endpoint (https://lite.duckduckgo.com/lite/)
which returns actual web search results, unlike the Instant Answer API
(api.duckduckgo.com) which only returns encyclopedia/Wikipedia snippets
and produces 0 results for clinical trial NCT IDs.
"""

import logging
import re
from html import unescape
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.web_context")

DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"

# Regex patterns for parsing DDG lite HTML results.
# Each result is a table row with a link and a snippet.
_RESULT_LINK_RE = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*class="result-link"[^>]*>([^<]*)</a>',
    re.IGNORECASE,
)
_RESULT_SNIPPET_RE = re.compile(
    r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    clean = re.sub(r"<[^>]+>", "", text)
    return unescape(clean).strip()


def _parse_ddg_lite_results(html: str) -> list[dict]:
    """Parse DuckDuckGo lite HTML into a list of {url, title, snippet} dicts."""
    results: list[dict] = []

    # The lite page structures results as table rows. Each result has:
    # 1. A row with the link (class="result-link")
    # 2. A row with the snippet (class="result-snippet")
    links = _RESULT_LINK_RE.findall(html)
    snippets = _RESULT_SNIPPET_RE.findall(html)

    for i, (url, title) in enumerate(links):
        snippet = _strip_html(snippets[i]) if i < len(snippets) else ""
        title_clean = _strip_html(title)
        if url and title_clean:
            results.append({
                "url": url,
                "title": title_clean,
                "snippet": snippet,
            })

    # Fallback: if the structured parsing above found nothing, try a broader
    # approach — extract all <a> tags that look like external result links.
    if not results:
        broad_links = re.findall(
            r'<a[^>]+href="(https?://[^"]+)"[^>]*>\s*([^<]+?)\s*</a>',
            html,
            re.IGNORECASE,
        )
        # Filter out DDG internal links
        for url, title in broad_links:
            if "duckduckgo.com" in url:
                continue
            title_clean = _strip_html(title)
            if title_clean and len(title_clean) > 5:
                results.append({
                    "url": url,
                    "title": title_clean,
                    "snippet": "",
                })

    return results


class WebContextAgent(BaseResearchAgent):
    """Gathers broader web context about a clinical trial."""

    agent_name = "web_context"
    sources = ["duckduckgo"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Build search query
        query_parts = [nct_id]
        if metadata:
            if metadata.get("title"):
                query_parts.append(metadata["title"][:80])
            elif metadata.get("conditions"):
                query_parts.extend(metadata["conditions"][:2])

        search_query = " ".join(query_parts)

        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
        ) as client:
            try:
                # DuckDuckGo HTML lite endpoint — returns actual web search results
                resp = await client.post(
                    DDG_LITE_URL,
                    data={"q": search_query},
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": "Mozilla/5.0 (compatible; research-agent/1.0)",
                        "Referer": "https://lite.duckduckgo.com/",
                    },
                    timeout=15,
                )
                if resp.status_code == 200:
                    html = resp.text
                    results = _parse_ddg_lite_results(html)
                    raw_data["duckduckgo_result_count"] = len(results)
                    raw_data["duckduckgo_html_length"] = len(html)

                    for result in results[:5]:
                        url = result["url"]
                        title = result["title"]
                        snippet = result["snippet"]

                        citations.append(SourceCitation(
                            source_name="duckduckgo",
                            source_url=url,
                            identifier=nct_id,
                            title=title[:200],
                            snippet=snippet[:500] if snippet else f"Web result for: {search_query}",
                            quality_score=self.compute_quality_score("duckduckgo"),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))

                    if not results:
                        logger.info(
                            "DuckDuckGo lite returned HTML (%d bytes) but no results parsed for: %s",
                            len(html), search_query,
                        )
                        raw_data["duckduckgo_note"] = "HTML returned but no results parsed"
                else:
                    raw_data["duckduckgo_status"] = resp.status_code
                    logger.warning(
                        "DuckDuckGo lite returned status %d for: %s",
                        resp.status_code, search_query,
                    )

            except Exception as e:
                logger.warning("DuckDuckGo search failed: %s", e)
                raw_data["duckduckgo_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )
