"""
EudraCT (EU Drug Regulating Authorities Clinical Trials Database) API Client
Access to European clinical trials registry.

API Documentation: https://eudract.ema.europa.eu/
Note: EudraCT does not have an official public API. This client scrapes the public portal
or uses the CTIS (Clinical Trials Information System) API where available.
"""
import aiohttp
import asyncio
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
import re

from amp_llm.config import get_logger

logger = get_logger(__name__)


class EudraCTClient:
    """
    EudraCT (European Clinical Trials Database) client.
    
    Searches European clinical trials registry and fetches trial information.
    """
    
    def __init__(self, timeout: int = 30, max_results: int = 10):
        """
        Initialize EudraCT client.
        
        Args:
            timeout: Request timeout in seconds
            max_results: Maximum results to return
        """
        # EudraCT public search portal
        self.base_url = "https://www.clinicaltrialsregister.eu"
        self.search_url = f"{self.base_url}/ctr-search/search"
        
        # CTIS (new system) API endpoint
        self.ctis_url = "https://euclinicaltrials.eu/ctis-public-api"
        
        self.timeout = timeout
        self.max_results = max_results
    
    async def search(
        self,
        query: str = None,
        eudract_number: str = None,
        disease: str = None,
        sponsor: str = None
    ) -> Dict[str, Any]:
        """
        Search EudraCT database.
        
        Args:
            query: General search query
            eudract_number: Specific EudraCT number (e.g., "2020-001234-12")
            disease: Disease/condition
            sponsor: Sponsor name
            
        Returns:
            Dictionary with search results
        """
        print(f"🔍 EudraCT: Searching European trials database...")
        
        # Build search parameters
        params = {}
        
        if eudract_number:
            params['query'] = eudract_number
            print(f"   Searching for EudraCT number: {eudract_number}")
        elif query:
            params['query'] = query
            print(f"   Searching for: {query[:100]}")
        
        if disease:
            params['disease'] = disease
        
        if sponsor:
            params['sponsor'] = sponsor
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.search_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={'User-Agent': 'Mozilla/5.0 (Research Bot)'}
                ) as resp:
                    if resp.status == 200:
                        html_content = await resp.text()
                        
                        # Parse HTML results
                        results = self._parse_search_results(html_content)
                        
                        print(f"✅ EudraCT: Found {len(results)} trial(s)")
                        logger.info(f"EudraCT search returned {len(results)} results")
                        
                        return {
                            "results": results[:self.max_results],
                            "total_count": len(results)
                        }
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ EudraCT: Error {resp.status}")
                        logger.warning(f"EudraCT search error {resp.status}: {error_text[:200]}")
                        return {"results": [], "error": f"http_error_{resp.status}"}
        
        except asyncio.TimeoutError:
            print(f"⚠️ EudraCT: Search timed out")
            return {"results": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ EudraCT: Search error: {e}")
            logger.error(f"EudraCT search error: {e}")
            return {"results": [], "error": str(e)}
    
    async def fetch_trial_details(self, eudract_number: str) -> Dict[str, Any]:
        """
        Fetch detailed information for a specific EudraCT trial.
        
        Args:
            eudract_number: EudraCT number (format: YYYY-NNNNNN-NN)
            
        Returns:
            Dictionary with trial details
        """
        # Validate format
        if not re.match(r'\d{4}-\d{6}-\d{2}', eudract_number):
            print(f"⚠️ EudraCT: Invalid format for {eudract_number}")
            return {"error": "invalid_format", "eudract_number": eudract_number}
        
        print(f"🔍 EudraCT: Fetching details for {eudract_number}...")
        
        # Construct trial detail URL
        detail_url = f"{self.base_url}/ctr-search/trial/{eudract_number}/results"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    detail_url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={'User-Agent': 'Mozilla/5.0 (Research Bot)'}
                ) as resp:
                    if resp.status == 200:
                        html_content = await resp.text()
                        
                        # Parse trial details
                        details = self._parse_trial_details(html_content, eudract_number)
                        
                        print(f"✅ EudraCT: Retrieved details for {eudract_number}")
                        logger.info(f"Retrieved EudraCT trial {eudract_number}")
                        
                        return details
                    elif resp.status == 404:
                        print(f"ℹ️ EudraCT: Trial {eudract_number} not found")
                        return {"error": "not_found", "eudract_number": eudract_number}
                    else:
                        print(f"⚠️ EudraCT: Error {resp.status}")
                        return {"error": f"http_error_{resp.status}", "eudract_number": eudract_number}
        
        except asyncio.TimeoutError:
            print(f"⚠️ EudraCT: Fetch timed out for {eudract_number}")
            return {"error": "timeout", "eudract_number": eudract_number}
        except Exception as e:
            print(f"❌ EudraCT: Fetch error for {eudract_number}: {e}")
            logger.error(f"EudraCT fetch error: {e}")
            return {"error": str(e), "eudract_number": eudract_number}
    
    async def search_by_nct(self, nct_id: str) -> Dict[str, Any]:
        """
        Search EudraCT for trials that may be related to an NCT number.
        
        Args:
            nct_id: NCT number
            
        Returns:
            Dictionary with potential matches
        """
        print(f"🔍 EudraCT: Searching for trials related to {nct_id}...")
        
        # Try searching for the NCT ID directly
        results = await self.search(query=nct_id)
        
        if results.get("results"):
            print(f"✅ Found {len(results['results'])} potential match(es)")
        else:
            print(f"ℹ️ No direct matches for {nct_id} in EudraCT")
        
        return results
    
    async def search_ctis(self, query: str) -> Dict[str, Any]:
        """
        Search the newer CTIS (Clinical Trials Information System) API.
        
        Args:
            query: Search query
            
        Returns:
            Dictionary with CTIS search results
        """
        print(f"🔍 EudraCT/CTIS: Searching CTIS database...")
        
        url = f"{self.ctis_url}/studies"
        params = {
            "query": query,
            "size": self.max_results
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        studies = data.get("studies", [])
                        print(f"✅ CTIS: Found {len(studies)} trial(s)")
                        logger.info(f"CTIS search returned {len(studies)} results")
                        
                        return {
                            "results": studies,
                            "total_count": data.get("totalCount", len(studies))
                        }
                    else:
                        print(f"⚠️ CTIS: Error {resp.status}")
                        return {"results": [], "error": f"http_error_{resp.status}"}
        
        except Exception as e:
            print(f"❌ CTIS: Search error: {e}")
            logger.error(f"CTIS search error: {e}")
            return {"results": [], "error": str(e)}
    
    def _parse_search_results(self, html_content: str) -> List[Dict[str, Any]]:
        """
        Parse HTML search results from EudraCT.
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            List of trial dictionaries
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            results = []
            
            # Find all trial result rows
            # Note: HTML structure may vary; this is a basic implementation
            trial_rows = soup.find_all('div', class_='result')
            
            if not trial_rows:
                # Alternative: look for table rows
                trial_rows = soup.find_all('tr', class_='trial-row')
            
            for row in trial_rows[:self.max_results]:
                trial = {}
                
                # Extract EudraCT number
                eudract_link = row.find('a', href=re.compile(r'/ctr-search/trial/'))
                if eudract_link:
                    href = eudract_link.get('href', '')
                    match = re.search(r'(\d{4}-\d{6}-\d{2})', href)
                    if match:
                        trial['eudract_number'] = match.group(1)
                
                # Extract title
                title_elem = row.find('span', class_='title') or row.find('h3')
                if title_elem:
                    trial['title'] = title_elem.get_text(strip=True)
                
                # Extract sponsor
                sponsor_elem = row.find('span', class_='sponsor')
                if sponsor_elem:
                    trial['sponsor'] = sponsor_elem.get_text(strip=True)
                
                # Extract status
                status_elem = row.find('span', class_='status')
                if status_elem:
                    trial['status'] = status_elem.get_text(strip=True)
                
                if trial:
                    results.append(trial)
            
            return results
        
        except Exception as e:
            logger.error(f"Error parsing EudraCT search results: {e}")
            return []
    
    def _parse_trial_details(self, html_content: str, eudract_number: str) -> Dict[str, Any]:
        """
        Parse detailed trial information from HTML.
        
        Args:
            html_content: Raw HTML content
            eudract_number: EudraCT number
            
        Returns:
            Dictionary with trial details
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            details = {
                "eudract_number": eudract_number,
                "source": "eudract"
            }
            
            # Extract title
            title_elem = soup.find('h1') or soup.find('span', class_='trial-title')
            if title_elem:
                details['title'] = title_elem.get_text(strip=True)
            
            # Extract sponsor
            sponsor_label = soup.find(text=re.compile(r'Sponsor', re.I))
            if sponsor_label:
                sponsor_elem = sponsor_label.find_next('td') or sponsor_label.find_next('span')
                if sponsor_elem:
                    details['sponsor'] = sponsor_elem.get_text(strip=True)
            
            # Extract medical condition
            condition_label = soup.find(text=re.compile(r'Medical condition', re.I))
            if condition_label:
                condition_elem = condition_label.find_next('td') or condition_label.find_next('span')
                if condition_elem:
                    details['condition'] = condition_elem.get_text(strip=True)
            
            # Extract disease
            disease_label = soup.find(text=re.compile(r'Disease', re.I))
            if disease_label:
                disease_elem = disease_label.find_next('td') or disease_label.find_next('span')
                if disease_elem:
                    details['disease'] = disease_elem.get_text(strip=True)
            
            # Extract status
            status_label = soup.find(text=re.compile(r'Trial Status', re.I))
            if status_label:
                status_elem = status_label.find_next('td') or status_label.find_next('span')
                if status_elem:
                    details['status'] = status_elem.get_text(strip=True)
            
            # Extract start date
            start_label = soup.find(text=re.compile(r'Start date', re.I))
            if start_label:
                start_elem = start_label.find_next('td') or start_label.find_next('span')
                if start_elem:
                    details['start_date'] = start_elem.get_text(strip=True)
            
            # Extract phase
            phase_label = soup.find(text=re.compile(r'Phase', re.I))
            if phase_label:
                phase_elem = phase_label.find_next('td') or phase_label.find_next('span')
                if phase_elem:
                    details['phase'] = phase_elem.get_text(strip=True)
            
            # Extract therapeutic area
            area_label = soup.find(text=re.compile(r'Therapeutic area', re.I))
            if area_label:
                area_elem = area_label.find_next('td') or area_label.find_next('span')
                if area_elem:
                    details['therapeutic_area'] = area_elem.get_text(strip=True)
            
            return details
        
        except Exception as e:
            logger.error(f"Error parsing EudraCT trial details: {e}")
            return {
                "eudract_number": eudract_number,
                "error": f"parse_error: {str(e)}"
            }
    
    async def batch_fetch(self, eudract_numbers: List[str]) -> Dict[str, Any]:
        """
        Fetch multiple trials concurrently.
        
        Args:
            eudract_numbers: List of EudraCT numbers
            
        Returns:
            Dictionary mapping EudraCT numbers to trial details
        """
        print(f"🔍 EudraCT: Batch fetching {len(eudract_numbers)} trial(s)...")
        
        tasks = [
            self.fetch_trial_details(eudract_num)
            for eudract_num in eudract_numbers
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Organize results
        batch_results = {}
        success_count = 0
        
        for eudract_num, result in zip(eudract_numbers, results):
            if isinstance(result, Exception):
                logger.error(f"Batch fetch failed for {eudract_num}: {result}")
                batch_results[eudract_num] = {"error": str(result)}
            else:
                batch_results[eudract_num] = result
                if "error" not in result:
                    success_count += 1
        
        print(f"✅ EudraCT: Successfully fetched {success_count}/{len(eudract_numbers)}")
        
        return batch_results