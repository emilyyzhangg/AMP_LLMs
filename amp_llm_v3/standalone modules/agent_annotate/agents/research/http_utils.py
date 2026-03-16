"""
Shared HTTP utilities for research agents.

Provides per-host rate limiting and retry with exponential backoff.
Designed for Phase 1 parallel research where many trials hit the
same APIs concurrently.

Rate limits (approximate):
  NCBI E-utilities: 3/sec without key, 10/sec with key
  Semantic Scholar: 100 req/5min (~0.33/sec)
  Europe PMC: generous, undocumented
  ClinicalTrials.gov: generous but can throttle
  OpenFDA: 240/min without key
  UniProt: undocumented, moderate
"""

import asyncio
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("agent_annotate.research.http")

# Per-host concurrency semaphores — lazily initialized so they bind
# to the running event loop, not to import-time state.
_HOST_SEMAPHORES: dict[str, asyncio.Semaphore] = {}

# Check for NCBI API key to set appropriate concurrency
try:
    from app.config import PUBMED_API_KEY
except ImportError:
    PUBMED_API_KEY = ""

_HOST_LIMITS = {
    "eutils.ncbi.nlm.nih.gov": 8 if PUBMED_API_KEY else 3,
    "api.semanticscholar.org": 3,
    "www.ebi.ac.uk": 10,
    "clinicaltrials.gov": 8,
    "api.fda.gov": 4,
    "rest.uniprot.org": 5,
    "api.duckduckgo.com": 3,
    "serpapi.com": 5,
    "dbaasp.org": 5,
    "search.rcsb.org": 8,
    "data.rcsb.org": 8,
}
_DEFAULT_CONCURRENCY = 10


def _get_host_semaphore(host: str) -> asyncio.Semaphore:
    """Get or create a per-host semaphore (lazy init for event-loop safety)."""
    if host not in _HOST_SEMAPHORES:
        limit = _HOST_LIMITS.get(host, _DEFAULT_CONCURRENCY)
        _HOST_SEMAPHORES[host] = asyncio.Semaphore(limit)
    return _HOST_SEMAPHORES[host]


async def resilient_get(
    url: str,
    *,
    client: httpx.AsyncClient,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float | None = None,
    max_retries: int = 3,
) -> httpx.Response:
    """HTTP GET with per-host rate limiting and retry with backoff.

    - 429: retries with Retry-After header or exponential backoff
    - 5xx: retries with exponential backoff
    - Timeout/connection errors: retries with exponential backoff
    - 4xx (non-429): returns immediately, no retry

    Semaphore is released between retries so other requests to the
    same host can proceed while this one waits.
    """
    host = urlparse(url).hostname or "unknown"
    sem = _get_host_semaphore(host)

    kwargs: dict = {"params": params, "headers": headers}
    if timeout is not None:
        kwargs["timeout"] = timeout

    last_resp = None

    for attempt in range(max_retries + 1):
        try:
            async with sem:
                resp = await client.get(url, **kwargs)
            last_resp = resp

            if resp.status_code < 400:
                return resp

            # Rate limited — retry with backoff
            if resp.status_code == 429:
                if attempt < max_retries:
                    delay = _parse_retry_after(resp, attempt)
                    logger.warning(
                        f"Rate limited by {host} (429), "
                        f"retry in {delay:.1f}s ({attempt+1}/{max_retries+1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning(f"Rate limited by {host}, exhausted {max_retries} retries")
                return resp

            # Server error — retry with backoff
            if resp.status_code >= 500:
                if attempt < max_retries:
                    delay = 2 ** attempt
                    logger.warning(
                        f"Server error {resp.status_code} from {host}, "
                        f"retry in {delay}s ({attempt+1}/{max_retries+1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                return resp

            # Other 4xx — don't retry
            return resp

        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            if attempt < max_retries:
                delay = 2 ** attempt
                logger.warning(
                    f"{type(e).__name__} to {host}, "
                    f"retry in {delay}s ({attempt+1}/{max_retries+1})"
                )
                await asyncio.sleep(delay)
                continue
            raise

    # Shouldn't reach here, but return last response if we do
    if last_resp is not None:
        return last_resp
    raise RuntimeError(f"resilient_get exhausted retries for {url}")


def _parse_retry_after(resp: httpx.Response, attempt: int) -> float:
    """Parse Retry-After header, falling back to exponential backoff."""
    raw = resp.headers.get("Retry-After", "")
    try:
        return min(float(raw), 60)
    except (ValueError, TypeError):
        return min(2 ** attempt, 30)
