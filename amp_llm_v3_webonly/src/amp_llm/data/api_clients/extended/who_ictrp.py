"""
WHO ICTRP (International Clinical Trials Registry Platform) API Client
Access to WHO's international trials registry aggregating data from multiple registries.

API Documentation: https://www.who.int/clinical-trials-registry-platform
"""
import aiohttp
import asyncio
from typing import Dict, List, Any, Optional
from xml.etree import ElementTree as ET
import re

from amp_llm.config import get_logger

logger = get_logger(__name__)


class WHOICTRPClient:
    """
    WHO ICTRP (International Clinical Trials Registry Platform) client.
    
    Aggregates clinical trial data from registries worldwide including:
    - ClinicalTrials.gov (USA)
    - EudraCT (Europe)
    - ANZCTR (Australia/New Zealand)
    - ISRCTN (UK)
    - CTRI (India)
    - And many more...
    """
    
    def __init__(self, timeout: int = 30, max_results: int = 10):
        """
        Initialize WHO ICTRP client.
        
        Args:
            timeout: Request timeout in seconds
            max_results: Maximum results to return
        """
        # WHO ICTRP search portal
        self.base_url = "https://trialsearch.who.int"
        self.api_url = f"{self.base_url}/api"
        
        # Alternative: Direct trial search
        self.search_url = f"{self.base_url}/Trial2.aspx"
        
        self.timeout = timeout
        self.max_results = max_results
    
    async def search(
        self,
        query: str = None,
        condition: str = None,
        intervention: str = None,
        recruitment_status: str = None,
        country: str = None
    ) -> Dict[str, Any]:
        """
        Search WHO ICTRP database.
        
        Args:
            query: General search query
            condition: Specific condition/disease
            intervention: Intervention/drug name
            recruitment_status: Status filter (e.g., "recruiting")
            country: Country filter
            
        Returns:
            Dictionary with search results
        """
        print(f"🔍 WHO ICTRP: Searching international trials registry...")
        
        # Build search parameters
        params = {
            "SearchTermStat": "1"  # Advanced search
        }
        
        if query:
            params['ConditionValue'] = query
            print(f"   Query: {query[:100]}")
        
        if condition:
            params['ConditionValue'] = condition
            print(f"   Condition: {condition}")
        
        if intervention:
            params['InterventionValue'] = intervention
            print(f"   Intervention: {intervention}")
        
        if recruitment_status:
            params['RecruitmentStatus'] = recruitment_status
        
        if country:
            params['CountryValue'] = country
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.search_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Research Bot)',
                        'Accept': 'application/json, text/html'
                    }
                ) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get('Content-Type', '')
                        
                        if 'json' in content_type:
                            # JSON response
                            data = await resp.json()
                            results = self._parse_json_results(data)
                        else:
                            # HTML response - parse it
                            html_content = await resp.text()
                            results = self._parse_html_results(html_content)
                        
                        print(f"✅ WHO ICTRP: Found {len(results)} trial(s)")
                        logger.info(f"WHO ICTRP search returned {len(results)} results")
                        
                        return {
                            "results": results[:self.max_results],
                            "total_count": len(results)
                        }
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ WHO ICTRP: Error {resp.status}")
                        logger.warning(f"WHO ICTRP error {resp.status}: {error_text[:200]}")
                        return {"results": [], "error": f"http_error_{resp.status}"}
        
        except asyncio.TimeoutError:
            print(f"⚠️ WHO ICTRP: Search timed out")
            return {"results": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ WHO ICTRP: Search error: {e}")
            logger.error(f"WHO ICTRP search error: {e}")
            return {"results": [], "error": str(e)}
    
    async def fetch_trial_details(self, trial_id: str) -> Dict[str, Any]:
        """
        Fetch detailed information for a specific trial.
        
        Args:
            trial_id: Trial identifier (can be NCT, EudraCT, ISRCTN, etc.)
            
        Returns:
            Dictionary with trial details
        """
        print(f"🔍 WHO ICTRP: Fetching details for {trial_id}...")
        
        # Construct detail URL
        detail_url = f"{self.search_url}?TrialID={trial_id}"
        
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
                        details = self._parse_trial_details(html_content, trial_id)
                        
                        print(f"✅ WHO ICTRP: Retrieved details for {trial_id}")
                        logger.info(f"Retrieved WHO ICTRP trial {trial_id}")
                        
                        return details
                    elif resp.status == 404:
                        print(f"ℹ️ WHO ICTRP: Trial {trial_id} not found")
                        return {"error": "not_found", "trial_id": trial_id}
                    else:
                        print(f"⚠️ WHO ICTRP: Error {resp.status}")
                        return {"error": f"http_error_{resp.status}", "trial_id": trial_id}
        
        except asyncio.TimeoutError:
            print(f"⚠️ WHO ICTRP: Fetch timed out for {trial_id}")
            return {"error": "timeout", "trial_id": trial_id}
        except Exception as e:
            print(f"❌ WHO ICTRP: Fetch error for {trial_id}: {e}")
            logger.error(f"WHO ICTRP fetch error: {e}")
            return {"error": str(e), "trial_id": trial_id}
    
    async def search_by_nct(self, nct_id: str) -> Dict[str, Any]:
        """
        Search WHO ICTRP for a specific NCT trial.
        
        Args:
            nct_id: NCT number
            
        Returns:
            Dictionary with trial information
        """
        print(f"🔍 WHO ICTRP: Searching for {nct_id}...")
        
        # WHO ICTRP includes ClinicalTrials.gov data
        results = await self.search(query=nct_id)
        
        if results.get("results"):
            print(f"✅ Found {len(results['results'])} result(s) for {nct_id}")
        else:
            print(f"ℹ️ No results for {nct_id} in WHO ICTRP")
        
        return results
    
    async def get_trial_registries(self) -> List[Dict[str, str]]:
        """
        Get list of registries included in WHO ICTRP.
        
        Returns:
            List of registry information
        """
        registries = [
            {
                "name": "ClinicalTrials.gov",
                "country": "USA",
                "prefix": "NCT",
                "url": "https://clinicaltrials.gov"
            },
            {
                "name": "EU Clinical Trials Register",
                "country": "EU",
                "prefix": "EudraCT",
                "url": "https://www.clinicaltrialsregister.eu"
            },
            {
                "name": "ISRCTN Registry",
                "country": "UK",
                "prefix": "ISRCTN",
                "url": "https://www.isrctn.com"
            },
            {
                "name": "ANZCTR",
                "country": "Australia/New Zealand",
                "prefix": "ACTRN",
                "url": "https://www.anzctr.org.au"
            },
            {
                "name": "CTRI",
                "country": "India",
                "prefix": "CTRI",
                "url": "http://ctri.nic.in"
            },
            {
                "name": "ChiCTR",
                "country": "China",
                "prefix": "ChiCTR",
                "url": "http://www.chictr.org.cn"
            },
            {
                "name": "DRKS",
                "country": "Germany",
                "prefix": "DRKS",
                "url": "https://www.drks.de"
            },
            {
                "name": "JPRN",
                "country": "Japan",
                "prefix": "JPRN",
                "url": "https://rctportal.niph.go.jp"
            },
            {
                "name": "KCT",
                "country": "South Korea",
                "prefix": "KCT",
                "url": "https://cris.nih.go.kr"
            },
            {
                "name": "NTR",
                "country": "Netherlands",
                "prefix": "NTR",
                "url": "https://www.trialregister.nl"
            },
            {
                "name": "PACTR",
                "country": "Pan-Africa",
                "prefix": "PACTR",
                "url": "https://pactr.samrc.ac.za"
            },
            {
                "name": "ReBec",
                "country": "Brazil",
                "prefix": "RBR",
                "url": "http://www.ensaiosclinicos.gov.br"
            },
            {
                "name": "RPCEC",
                "country": "Cuba",
                "prefix": "RPCEC",
                "url": "http://registroclinico.sld.cu"
            },
            {
                "name": "SLCTR",
                "country": "Sri Lanka",
                "prefix": "SLCTR",
                "url": "https://slctr.lk"
            },
            {
                "name": "TCTR",
                "country": "Thailand",
                "prefix": "TCTR",
                "url": "http://www.clinicaltrials.in.th"
            }
        ]
        
        return registries
    
    async def search_multi_registry(
        self,
        title: str,
        condition: str = None
    ) -> Dict[str, Any]:
        """
        Search across all registries in WHO ICTRP.
        
        Args:
            title: Study title
            condition: Medical condition
            
        Returns:
            Dictionary with aggregated results from all registries
        """
        print(f"🔍 WHO ICTRP: Multi-registry search...")
        
        results = await self.search(
            query=title,
            condition=condition
        )
        
        if results.get("results"):
            # Group by registry
            by_registry = {}
            for trial in results["results"]:
                registry = trial.get("registry", "Unknown")
                if registry not in by_registry:
                    by_registry[registry] = []
                by_registry[registry].append(trial)
            
            print(f"✅ Found trials across {len(by_registry)} registries")
            for registry, trials in by_registry.items():
                print(f"   {registry}: {len(trials)} trial(s)")
            
            results["by_registry"] = by_registry
        
        return results
    
    def _parse_json_results(self, data: Dict) -> List[Dict[str, Any]]:
        """Parse JSON response from WHO ICTRP API."""
        try:
            if isinstance(data, dict):
                trials = data.get('trials', data.get('results', []))
            elif isinstance(data, list):
                trials = data
            else:
                return []
            
            results = []
            for trial in trials:
                result = {
                    "trial_id": trial.get("TrialID"),
                    "title": trial.get("PublicTitle"),
                    "scientific_title": trial.get("ScientificTitle"),
                    "condition": trial.get("Condition"),
                    "intervention": trial.get("Intervention"),
                    "registry": trial.get("SourceRegister"),
                    "recruitment_status": trial.get("RecruitmentStatus"),
                    "countries": trial.get("Countries"),
                    "date_registration": trial.get("DateRegistration"),
                    "primary_sponsor": trial.get("PrimarySponsor"),
                    "url": trial.get("url")
                }
                results.append(result)
            
            return results
        
        except Exception as e:
            logger.error(f"Error parsing WHO ICTRP JSON: {e}")
            return []
    
    def _parse_html_results(self, html_content: str) -> List[Dict[str, Any]]:
        """Parse HTML search results from WHO ICTRP."""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'html.parser')
            results = []
            
            # Find trial result divs/rows
            trial_divs = soup.find_all('div', class_='trial-result')
            
            if not trial_divs:
                # Try table rows
                trial_divs = soup.find_all('tr', class_='trial')
            
            for div in trial_divs[:self.max_results]:
                trial = {}
                
                # Extract trial ID
                id_elem = div.find('a', href=re.compile(r'TrialID='))
                if id_elem:
                    href = id_elem.get('href', '')
                    match = re.search(r'TrialID=([^&]+)', href)
                    if match:
                        trial['trial_id'] = match.group(1)
                    trial['url'] = f"{self.base_url}/{href}" if not href.startswith('http') else href
                
                # Extract title
                title_elem = div.find('span', class_='title') or div.find('h3')
                if title_elem:
                    trial['title'] = title_elem.get_text(strip=True)
                
                # Extract registry
                registry_elem = div.find('span', class_='registry')
                if registry_elem:
                    trial['registry'] = registry_elem.get_text(strip=True)
                
                # Extract status
                status_elem = div.find('span', class_='status')
                if status_elem:
                    trial['recruitment_status'] = status_elem.get_text(strip=True)
                
                # Extract condition
                condition_elem = div.find('span', class_='condition')
                if condition_elem:
                    trial['condition'] = condition_elem.get_text(strip=True)
                
                if trial:
                    results.append(trial)
            
            return results
        
        except Exception as e:
            logger.error(f"Error parsing WHO ICTRP HTML: {e}")
            return []
    
    def _parse_trial_details(self, html_content: str, trial_id: str) -> Dict[str, Any]:
        """Parse trial details from HTML."""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            details = {
                "trial_id": trial_id,
                "source": "who_ictrp"
            }
            
            # Extract from labeled fields
            labels = [
                ('Public title', 'title'),
                ('Scientific title', 'scientific_title'),
                ('Condition', 'condition'),
                ('Intervention', 'intervention'),
                ('Primary sponsor', 'primary_sponsor'),
                ('Recruitment status', 'recruitment_status'),
                ('Countries', 'countries'),
                ('Date of registration', 'date_registration'),
                ('Target size', 'target_size'),
                ('Study type', 'study_type'),
                ('Phase', 'phase'),
                ('Primary outcome', 'primary_outcome')
            ]
            
            for label_text, field_name in labels:
                label = soup.find(text=re.compile(label_text, re.I))
                if label:
                    value_elem = label.find_next('td') or label.find_next('div')
                    if value_elem:
                        details[field_name] = value_elem.get_text(strip=True)
            
            return details
        
        except Exception as e:
            logger.error(f"Error parsing WHO ICTRP trial details: {e}")
            return {
                "trial_id": trial_id,
                "error": f"parse_error: {str(e)}"
            }
    
    async def batch_fetch(self, trial_ids: List[str]) -> Dict[str, Any]:
        """
        Fetch multiple trials concurrently.
        
        Args:
            trial_ids: List of trial IDs
            
        Returns:
            Dictionary mapping trial IDs to details
        """
        print(f"🔍 WHO ICTRP: Batch fetching {len(trial_ids)} trial(s)...")
        
        tasks = [
            self.fetch_trial_details(trial_id)
            for trial_id in trial_ids
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Organize results
        batch_results = {}
        success_count = 0
        
        for trial_id, result in zip(trial_ids, results):
            if isinstance(result, Exception):
                logger.error(f"Batch fetch failed for {trial_id}: {result}")
                batch_results[trial_id] = {"error": str(result)}
            else:
                batch_results[trial_id] = result
                if "error" not in result:
                    success_count += 1
        
        print(f"✅ WHO ICTRP: Successfully fetched {success_count}/{len(trial_ids)}")
        
        return batch_results