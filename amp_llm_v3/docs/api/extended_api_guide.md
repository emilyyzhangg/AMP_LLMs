# Extended API Integration Guide
## Requires Meilisearch and Swirl setup on remote

### Swirl Setup on Host

# install VM onto Mac Host
brew install multipass
multipass launch --name docker-vm --mem 4G --disk 40G
multipass exec docker-vm -- bash -c "curl -fsSL https://get.docker.com | sh"
multipass exec docker-vm -- sudo usermod -aG docker ubuntu
multipass shell docker-vm


# Pull Swirl image
docker pull swirlai/swirl-search:latest

# Create data directory
mkdir -p ~/swirl_data

# Run Swirl
# docker_compose.yml
version: "3.9"

services:
  swirl:
    image: swirlai/swirl-search:latest
    container_name: swirl
    restart: unless-stopped
    ports:
      - "9000:9000"
    volumes:
      - ./swirl_data:/data
    command: python3 manage.py runserver 0.0.0.0:9000


# Test
curl http://localhost:9000/api/health



## Overview

Your NCT lookup now supports 6 additional external APIs for comprehensive research:

1. **Meilisearch** - Fast semantic search engine
2. **Swirl** - Metasearch aggregator
3. **OpenFDA** - FDA drug events & labels
4. **Health Canada** - Canadian clinical trials
5. **DuckDuckGo** - Privacy-focused web search
6. **SERP API** - Google & Google Scholar results

## Quick Start

### Step 1: Install New Dependencies

```bash
pip install duckduckgo-search
```

### Step 2: Copy New Files

1. Create `data/api_clients.py` - Copy from **api_clients_module** artifact
2. Update `data/async_nct_lookup.py` - Copy from **enhanced_nct_lookup** artifact
3. Create `.env` file - Copy from **api_config_example** artifact

### Step 3: Configure API Keys (Optional)

Edit `.env` file:

```bash
# Required for Google search
SERPAPI_KEY=your_key_here

# Required for Meilisearch (if using)
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_KEY=your_key

# Others work without keys
```

### Step 4: Test

```bash
python main.py
# Select: NCT Lookup (option 4)
# Enter NCT number
# Choose: Use extended API search? y
```

## API Details

### 1. Meilisearch (Optional - Requires Setup)

**Purpose**: Fast semantic search of clinical trial database

**Setup**:
```bash
# Install Meilisearch
curl -L https://install.meilisearch.com | sh

# Run
./meilisearch --master-key="your_master_key"
```

**Configuration**:
```bash
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_KEY=your_master_key
```

**Use Case**: Search your own indexed clinical trials database

### 2. Swirl (Optional - Requires Setup)

**Purpose**: Metasearch across multiple sources simultaneously

**Setup**:
```bash
# Install via Docker
docker pull swirlai/swirl-search

# Run
docker run -p 9000:9000 swirlai/swirl-search
```

**Configuration**:
```bash
SWIRL_URL=http://localhost:9000
```

**Use Case**: Aggregate results from Google, PubMed, arXiv in one search

### 3. OpenFDA (No Setup Required)

**Purpose**: FDA adverse event reports and drug labels

**Setup**: None - public API

**Features**:
- Adverse event reports
- Drug labeling information
- Manufacturing data
- Recall information

**Use Case**: Safety and regulatory information for drugs in trials

### 4. Health Canada (No Setup Required)

**Purpose**: Canadian clinical trials database

**Setup**: None - public API

**Features**:
- Canadian trial registrations
- Regulatory status in Canada
- Cross-reference with NCT numbers

**Use Case**: Find related Canadian trials

### 5. DuckDuckGo (No Setup Required)

**Purpose**: Privacy-focused web search

**Setup**: Install library (done in requirements.txt)

**Features**:
- No API key needed
- No rate limiting
- Privacy-preserving
- Web search results

**Use Case**: General web search for trial information

### 6. SERP API (Requires API Key)

**Purpose**: Google and Google Scholar results

**Setup**:
1. Sign up at https://serpapi.com/
2. Get API key (free tier: 100 searches/month)
3. Add to `.env`:
   ```bash
   SERPAPI_KEY=your_key_here
   ```

**Features**:
- Google search results
- Google Scholar results
- Structured data extraction
- No proxies needed

**Use Case**: Academic papers and general web presence

## Usage Examples

### Basic Usage (All APIs)

```bash
$ python main.py
Select: 4 (NCT Lookup)

Enter NCT number: NCT04043065
Use extended API search? y
Select: 1 (All APIs)

# Output shows results from all sources
```

### Selective API Usage

```bash
Enter NCT number: NCT04043065
Use extended API search? y
Select: 6 (Custom selection)
APIs: openfda, duckduckgo, serpapi

# Only searches OpenFDA, DuckDuckGo, and SERP API
```

### No Extended Search

```bash
Enter NCT number: NCT04043065
Use extended API search? n

# Only searches ClinicalTrials.gov, PubMed, PMC (original behavior)
```

## API Response Structure

Each API returns data in the result under `extended_apis`:

```python
{
    'nct_id': 'NCT04043065',
    'sources': {
        'clinical_trials': {...},
        'pubmed': {...},
        'pmc': {...}
    },
    'extended_apis': {
        'meilisearch': {
            'hits': [...]
        },
        'openfda_events_LEAP-2': {
            'results': [...]
        },
        'openfda_labels_LEAP-2': {
            'results': [...]
        },
        'health_canada': {
            'results': [...]
        },
        'duckduckgo': {
            'results': [...]
        },
        'serpapi_google': {
            'organic_results': [...]
        },
        'serpapi_scholar': {
            'organic_results': [...]
        }
    }
}
```

## Customization

### Add New Search Parameters

Edit `data/api_clients.py`, modify `APIManager.search_all()`:

```python
async def search_all(
    self,
    title: str,
    authors: List[str],
    nct_id: str = None,
    interventions: List[str] = None,
    conditions: List[str] = None,  # ADD NEW
    sponsors: List[str] = None,     # ADD NEW
    enabled_apis: List[str] = None
):
    # Use new parameters in API calls
    if 'meilisearch' in enabled_apis:
        query = f"{title} {' '.join(conditions)}"  # Use conditions
        tasks.append(self.meilisearch.search(query, authors))
```

Then update `data/async_nct_lookup.py` to extract and pass new parameters.

### Change Result Limits

Edit `.env`:

```bash
API_MAX_RESULTS=20  # Get 20 results instead of 10
```

Or modify `SearchConfig` in `data/api_clients.py`:

```python
@dataclass
class SearchConfig:
    max_results: int = 20  # Changed from 10
```

### Add Custom API

1. Create new client class in `data/api_clients.py`:

```python
class MyCustomAPIClient:
    def __init__(self, config: SearchConfig):
        self.config = config
    
    async def search(self, title: str, authors: List[str]):
        # Your implementation
        pass
```

2. Add to `APIManager`:

```python
class APIManager:
    def __init__(self, config: Optional[SearchConfig] = None):
        # ... existing clients ...
        self.my_custom = MyCustomAPIClient(self.config)
    
    async def search_all(self, ...):
        if 'my_custom' in enabled_apis:
            tasks.append(self.my_custom.search(title, authors))
            task_names.append('my_custom')
```

## Troubleshooting

### "Library not installed" for DuckDuckGo

```bash
pip install duckduckgo-search
```

### "API key not configured" for SERP API

1. Get key at https://serpapi.com/
2. Add to `.env`:
   ```bash
   SERPAPI_KEY=your_key_here
   ```

### Meilisearch connection refused

1. Check if running:
   ```bash
   curl http://localhost:7700
   ```

2. Start Meilisearch:
   ```bash
   ./meilisearch
   ```

### OpenFDA returns no results

This is normal - OpenFDA only has data for drugs with adverse events or labels in their system. Not all interventions will have data.

### Health Canada API slow/timeout

Increase timeout in `.env`:

```bash
API_TIMEOUT=30  # Increase from 15 seconds
```

## Performance Tips

### Concurrent Execution

All APIs run concurrently (async), so total time ≈ slowest API, not sum of all.

### Selective Searching

Only enable APIs you need:

```python
# Fast: Only free, no-setup APIs
enabled_apis = ['openfda', 'duckduckgo', 'health_canada']

# Comprehensive: All APIs (slower, requires setup)
enabled_apis = None  # All
```

### Caching Results

Consider adding caching to avoid repeat API calls:

```python
# In api_clients.py
import json
from pathlib import Path

cache_dir = Path('api_cache')
cache_dir.mkdir(exist_ok=True)

async def search(self, title: str, authors: List[str]):
    cache_key = hashlib.md5(f"{title}{authors}".encode()).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"
    
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    
    # ... do actual search ...
    result = await self._do_search(title, authors)
    
    cache_file.write_text(json.dumps(result))
    return result
```

## API Rate Limits

| API | Free Tier | Rate Limit | Notes |
|-----|-----------|------------|-------|
| OpenFDA | Yes | 240 req/min | No key needed |
| Health Canada | Yes | Unknown | No key needed |
| DuckDuckGo | Yes | ~100 req/hour | Soft limit |
| SERP API | 100 req/month | 1 req/sec | Requires key |
| Meilisearch | Self-hosted | Unlimited | Your instance |
| Swirl | Self-hosted | Unlimited | Your instance |

## Security Notes

### API Keys

- Never commit `.env` file to git
- Add to `.gitignore`:
  ```
  .env
  .env.local
  .env.*.local
  ```

### Sensitive Data

- API responses may contain personal information
- Be careful when sharing result files
- Consider anonymizing before distribution

## Next Steps

1. ✅ Install dependencies
2. ✅ Copy new files
3. ✅ Configure API keys (optional)
4. ✅ Test with sample NCT number
5. 📊 Review results
6. 🔧 Customize as needed

---

**Need help?** Check the logs: `amp_llm.log`
