# Main ReadMe

#
# External API Setup Guide

This guide explains how to set up and use the external APIs with `nct_lookup`.

## Quick Start

### Install Required Libraries

```bash
# Required for DuckDuckGo
pip install duckduckgo-search

# Optional: For async console I/O
pip install aioconsole
```

### Environment Variables

Create a `.env` file in your project root:

```bash
# SERP API (for Google and Google Scholar searches)
SERPAPI_KEY=your_serpapi_key_here

# Meilisearch (if using local instance)
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_KEY=your_meilisearch_key_here

# Swirl (if using local instance)
SWIRL_URL=http://localhost:8000
```

## Supported APIs

### 1. DuckDuckGo (FREE) ✅

**Status**: Fully operational, no API key required

**Installation**:
```bash
pip install duckduckgo-search
```

**Features**:
- Free web search
- No rate limits
- No API key required
- Returns title, URL, and snippet

**Usage in nct_lookup**:
- Automatically enabled when `duckduckgo-search` is installed
- Select "DuckDuckGo" when prompted for API selection

### 2. SERP API (PAID) ✅

**Status**: Fully operational, requires API key

**Setup**:
1. Sign up at [https://serpapi.com](https://serpapi.com)
2. Get your API key from the dashboard
3. Set environment variable: `export SERPAPI_KEY=your_key_here`

**Features**:
- Google Search results
- Google Scholar results
- Structured data extraction
- 100 free searches/month on free tier

**Usage in nct_lookup**:
- Set `SERPAPI_KEY` environment variable
- Select "SERP API" when prompted

### 3. OpenFDA (FREE) ✅

**Status**: Fully operational, no API key required

**Features**:
- Drug adverse event reports
- Drug label information
- No authentication required
- Rate limited to 240 requests/minute

**Usage in nct_lookup**:
- Automatically enabled
- Works with drug/intervention names from trials

### 4. Health Canada (FREE) ⚠️

**Status**: Endpoint may vary, check current API documentation

**Features**:
- Canadian clinical trial database
- Public API (no key required)

**Note**: The Health Canada API endpoint structure may change. Verify the current endpoint at:
[https://health-products.canada.ca/api/documentation](https://health-products.canada.ca/api/documentation)

### 5. Meilisearch (SELF-HOSTED) 🔧

**Status**: Requires local setup

**Setup**:
```bash
# Install Meilisearch
curl -L https://install.meilisearch.com | sh

# Run Meilisearch
./meilisearch --master-key="YOUR_MASTER_KEY"

# Set environment variables
export MEILISEARCH_URL=http://localhost:7700
export MEILISEARCH_KEY=YOUR_MASTER_KEY
```

**Usage**:
- Index your clinical trial data first
- Enable in nct_lookup searches

### 6. Swirl (SELF-HOSTED) 🔧

**Status**: Requires local setup

**Setup**:
```bash
# Clone Swirl
git clone https://github.com/swirlai/swirl-search.git
cd swirl-search

# Follow Swirl installation instructions
# Default runs on http://localhost:8000
```

## Using APIs with nct_lookup

### Basic Usage

```python
# Run the NCT lookup tool
python -m amp_llm.data.nct_lookup

# When prompted:
# 1. Enter NCT number(s)
# 2. Choose whether to use extended API search (y/n)
# 3. Select which APIs to use:
#    - All (default)
#    - Core only (OpenFDA, DuckDuckGo)
#    - Custom selection
```

### Example Session

```
Enter NCT number(s): NCT04327206

Use extended API search? (y/n) [n]: y

Available APIs:
  1) All (default)
  2) Core only (OpenFDA, DuckDuckGo)
  3) Custom selection

Select [1]: 2

🔍 Processing 1 NCT number(s)...
🔍 DuckDuckGo: Searching web...
✅ DuckDuckGo: Found 8 result(s)
🔍 OpenFDA: Searching adverse events for 'Drug: Hydroxychloroquine'...
✅ OpenFDA: Found 245 adverse event report(s)
```

## API Selection Recommendations

### For Quick Searches (No Setup Required)
- **DuckDuckGo**: Free, fast, no API key
- **OpenFDA**: Free, reliable for drug information

### For Comprehensive Research (With API Key)
- **SERP API**: Best quality Google results
- **Google Scholar**: Academic paper discovery
- **DuckDuckGo**: Supplementary web results
- **OpenFDA**: Drug safety information

### For Advanced Users (Self-Hosted)
- **Meilisearch**: Custom semantic search on your data
- **Swirl**: Metasearch across multiple providers

## Troubleshooting

### DuckDuckGo Errors

**Error**: `ImportError: No module named 'duckduckgo_search'`

**Solution**:
```bash
pip install duckduckgo-search
```

**Error**: `DuckDuckGo rate limit exceeded`

**Solution**: Wait a few seconds and retry. DuckDuckGo implements automatic rate limiting.

### SERP API Errors

**Error**: `SERP API: API key not configured`

**Solution**:
```bash
# Set environment variable
export SERPAPI_KEY=your_key_here

# Or add to .env file
echo "SERPAPI_KEY=your_key_here" >> .env
```

**Error**: `SERP API: Error 429`

**Solution**: You've exceeded your monthly quota. Check your SERP API dashboard.

### OpenFDA Errors

**Error**: `OpenFDA: Error 404`

**Solution**: This is normal - it means no data found for the drug name. The API continues working.

**Error**: `OpenFDA: Error 429`

**Solution**: Rate limit exceeded (240 requests/minute). Wait a minute and retry.

## API Response Examples

### DuckDuckGo Response
```json
{
  "results": [
    {
      "title": "Study Title - ClinicalTrials.gov",
      "url": "https://clinicaltrials.gov/study/NCT12345678",
      "snippet": "Brief description of the study..."
    }
  ]
}
```

### SERP API Response
```json
{
  "organic_results": [
    {
      "position": 1,
      "title": "Study Results Published",
      "link": "https://example.com/study-results",
      "snippet": "Detailed study findings...",
      "source": "PubMed"
    }
  ]
}
```

### OpenFDA Response
```json
{
  "results": [
    {
      "patient": {
        "drug": [
          {
            "medicinalproduct": "HYDROXYCHLOROQUINE",
            "drugindication": "COVID-19"
          }
        ]
      },
      "serious": 1,
      "receivedate": "20200415"
    }
  ]
}
```

## Rate Limits Summary

| API | Rate Limit | Authentication |
|-----|-----------|----------------|
| DuckDuckGo | Auto-limited | None |
| SERP API | 100/month (free tier) | API Key |
| OpenFDA | 240/minute | None |
| Health Canada | Unknown | None |
| Meilisearch | Self-hosted | Optional |
| Swirl | Self-hosted | Optional |

## Best Practices

1. **Start with free APIs**: Test with DuckDuckGo and OpenFDA first
2. **Batch searches**: Process multiple NCTs in one session to minimize API calls
3. **Cache results**: Results are automatically saved to `ct_database/`
4. **Use specific APIs**: Don't enable all APIs if you only need web search
5. **Monitor quotas**: Check SERP API dashboard regularly if using paid tier

## Getting Help

- **DuckDuckGo Search**: [GitHub Issues](https://github.com/deedy5/duckduckgo_search/issues)
- **SERP API**: [Documentation](https://serpapi.com/docs)
- **OpenFDA**: [API Basics](https://open.fda.gov/apis/)
- **Project Issues**: [Create an issue](https://github.com/your-repo/issues)

## Future APIs (Planned)

- PubMed Central Full Text API
- EudraCT (European trials database)
- WHO ICTRP (International trials registry)
- Semantic Scholar API