# AMP_LLM v3.0

**Clinical Trial Research Assistant with RAG-Powered LLM Integration**

A comprehensive Python application for clinical trial research, featuring advanced LLM capabilities, extensive API integrations, and intelligent data extraction.

---

## 🌟 Features

### Core Capabilities
- **🔐 SSH Management**: Secure remote connections with automatic tunneling
- **🤖 LLM Integration**: Direct Ollama API access with custom model support
- **🧬 Clinical Trial RAG**: Retrieval-Augmented Generation for trial analysis
- **🔍 Multi-API Search**: 10+ external APIs for comprehensive research
- **📊 Data Extraction**: Structured clinical trial data extraction
- **💾 Export Options**: JSON, CSV, and text output formats

### External API Integration
1. **Literature Sources**
   - PubMed (NCBI E-utilities)
   - PubMed Central (PMC) with full-text access
   - Semantic Scholar (AI-powered search)
   - Google Scholar (via SERP API)

2. **Clinical Trial Databases**
   - ClinicalTrials.gov (US)
   - EudraCT (European Union)
   - WHO ICTRP (International)
   - Health Canada

3. **Drug Safety**
   - OpenFDA (adverse events & labels)

4. **Web Search**
   - DuckDuckGo (privacy-focused)
   - Google Search (via SERP API)

5. **Custom Search**
   - Meilisearch (semantic search)
   - Swirl (metasearch aggregator)

---

## 📋 Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Main Menu Options](#main-menu-options)
4. [Workflows](#workflows)
5. [Research Assistant](#research-assistant)
6. [API Configuration](#api-configuration)
7. [Custom Models](#custom-models)
8. [Troubleshooting](#troubleshooting)
9. [Development](#development)

---

## 🚀 Installation

### Prerequisites
- Python 3.8+
- SSH access to remote server with Ollama
- Git

### Setup

```bash
# Clone repository
git clone <repository-url>
cd amp_llm_v3

# Run main.py (auto-creates virtual environment)
python main.py
```

The application will:
1. ✅ Create virtual environment (`llm_env/`)
2. ✅ Install dependencies from `requirements.txt`
3. ✅ Generate `Modelfile` if missing
4. ✅ Launch the application

### Manual Setup (Optional)

```bash
# Create virtual environment
python -m venv llm_env

# Activate
# Windows:
llm_env\Scripts\activate
# Unix/Mac:
source llm_env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your API keys
```

---

## ⚡ Quick Start

### First Run

```bash
python main.py
```

**Startup Flow:**
1. Environment validation
2. Modelfile generation
3. SSH connection prompt
4. Main menu display

### SSH Connection

```
Enter remote host IP [100.99.162.98]: <IP>
Enter SSH username [emilyzhang]: <username>
Enter SSH password: <password>
```

**💡 Tip**: Default values shown in `[brackets]` - press Enter to use them.

---

## 📑 Main Menu Options

```
=== Main Menu ===

1. Interactive Shell
   Direct SSH terminal access

2. LLM Workflow (API Mode) ← RECOMMENDED
   HTTP API with enhanced features

3. LLM Workflow (SSH Terminal)
   Legacy terminal mode

4. NCT Lookup
   Search clinical trials + ALL APIs

5. Clinical Trial Research Assistant ← RECOMMENDED
   RAG-powered intelligent analysis

6. Exit
   Quit application
```

### 💡 Recommended Workflow

**For Research**: Start with **Option 5** (Research Assistant)
**For Data Collection**: Use **Option 4** (NCT Lookup)
**For LLM Chat**: Use **Option 2** (LLM API Mode)

---

## 🔬 Workflows

### 1. Interactive Shell

**Purpose**: Direct terminal access to remote server

```bash
Select: 1

# Example commands:
Research >>> ls
Research >>> cd /path/to/data
Research >>> ollama list
Research >>> exit  # Returns to main menu
```

**Features:**
- Auto-detects remote shell (bash/zsh)
- Full command execution
- Clean output display
- `Ctrl+C` returns to menu safely

---

### 2. LLM Workflow (API Mode) 🌟

**Purpose**: Interactive LLM chat with advanced features

```bash
Select: 2

✅ Connected to Ollama!
✅ Found 14 model(s)

📋 Available base models:
  → 1) llama3.2
    2) mistral
    3) llama3:8b

Select base model [1]: 1

✅ Selected base: llama3.2

Build Research Assistant model from this base? (y/n) [n]: n

✅ Using base model: llama3.2

============================================================
  🤖 CURRENT CONFIGURATION
============================================================
  Model: llama3.2
  Type: Base LLM (General Purpose)
  Features: General Q&A, Code, Analysis
============================================================

# Interactive session starts
LLM >>> <your question>
```

#### Available Commands

**File Operations:**
```bash
load <filename>              # Load file from output/
load <filename> <question>   # Load and ask
paste                        # Multi-line input mode
ls                          # List files in output/
dir                         # Same as ls
pwd                         # Show working directory
```

**Trial Operations:**
```bash
trial <NCT>                 # Load trial data
extract <NCT>               # Extract structured data
compare <NCT1> <NCT2>       # Compare two trials
```

**System:**
```bash
help                        # Show commands
models                      # List available models
exit                        # Return to main menu
```

#### Example Session

```bash
LLM >>> load NCT04043065_extraction.json
✅ Loaded NCT04043065_extraction.json
Preview:
{
  "nct_number": "NCT04043065",
  "study_title": "A Leap to Understand..."
}

Ask a question: What is the study about?

🤔 Generating response...

🧠 Response:
This study investigates the glucoregulatory 
effects of LEAP-2, an antimicrobial peptide...
```

---

### 3. LLM Workflow (SSH Terminal)

**Purpose**: Legacy terminal-based LLM interaction

**⚠️ Note**: Deprecated. Use API Mode (Option 2) instead.

---

### 4. NCT Lookup 📊

**Purpose**: Comprehensive clinical trial search across ALL APIs

```bash
Select: 4

Enter NCT number(s): NCT04043065, NCT12345678

Use extended API search? (y/n) [y]: y

Available API Collections:
  [1] All APIs (Comprehensive)
  [2] Literature Only
  [3] Clinical Databases
  [4] Drug Safety
  [5] Web Search
  [6] Custom Selection

Select [1-6]: 1

🔍 Processing 2 NCT number(s)...
```

#### Search Results Include:

**Core Data:**
- ✅ ClinicalTrials.gov study details
- ✅ PubMed publications
- ✅ PMC articles

**Extended APIs (when enabled):**
- 📄 PMC Full Text articles
- 🇪🇺 EudraCT trials
- 🌍 WHO ICTRP trials
- 🤖 Semantic Scholar papers
- 💊 OpenFDA drug safety data
- 🍁 Health Canada trials
- 🔍 Google Search results
- 🦆 DuckDuckGo results
- 🧬 Uniprot results
- 📊 Meilisearch hits
- 🔄 Swirl metasearch

#### Save Options

```bash
Save results? (txt/csv/json/none): json
Filename [nct_results_2_studies]: my_research

💾 Results saved to output/my_research.json
```

---

### 5. Clinical Trial Research Assistant 🧬

**Purpose**: RAG-powered intelligent analysis of trial database

#### Setup Requirements

1. **Database Directory:**
   ```bash
   mkdir ct_database
   # Add JSON files (one per trial)
   cp trials/*.json ct_database/
   ```

2. **JSON Format:**
   ```json
   {
     "nct_id": "NCT########",
     "sources": {
       "clinical_trials": { "data": {...} },
       "pubmed": {...},
       "pmc": {...}
     }
   }
   ```

#### Starting the Assistant

```bash
Select: 5

✅ Indexed 150 clinical trials
🔗 Connecting to Ollama...
✅ Connected to Ollama!
✅ Found 14 model(s)

# Scenario 1: Research Assistant already exists
✅ Found existing model: ct-research-assistant:latest

Use existing 'ct-research-assistant:latest'? (y/n/rebuild) [y]: y

✅ Using existing Research Assistant model

# Scenario 2: Building new Research Assistant
⚠️  Custom model not found

🔬 Research Assistant Setup
Building specialized clinical trial research model...

📋 Select base model for Research Assistant:
  → 1) llama3.2
    2) mistral
    3) llama3:8b

Select base model [1]: 1

✅ Selected: llama3.2

🔨 Building 'ct-research-assistant:latest' from 'llama3.2'...
📤 Uploading Modelfile...
🏗️ Building model (1-2 minutes)...

✅ Research Assistant Ready!
   Model: ct-research-assistant:latest
   Base LLM: llama3.2
   Capabilities: RAG, Extraction, Analysis
```

#### Model Selection Workflow

**For LLM Workflow (Option 2):**

```bash
# Step 1: Select base LLM
📋 Available base models:
  1) llama3.2
  2) mistral
  3) llama3:8b

Select base model [1]: 2

# Step 2: Optional Research Assistant
Build Research Assistant model from this base? (y/n) [n]: y

# Step 3: Model builds automatically
🔨 Building 'ct-research-assistant:latest' from 'mistral'...
✅ Created: ct-research-assistant:latest

# Step 4: Configuration displayed
============================================================
  🤖 CURRENT CONFIGURATION
============================================================
  Model: ct-research-assistant:latest
  Type: Clinical Trial Research Assistant
  Features: RAG, Structured Extraction, Trial Analysis
============================================================
```

**For Research Assistant (Option 5):**

```bash
# If model exists:
✅ Found existing model: ct-research-assistant:latest
Use existing? (y/n/rebuild) [y]: y

# If building new:
📋 Select base model for Research Assistant:
  1) llama3.2
  2) mistral

Select base model [1]: 1
🔨 Building from llama3.2...
✅ Research Assistant Ready!
```

**Key Points:**
- ✅ Base models shown separately from custom models
- ✅ Clear separation: first select LLM, then decide on Research Assistant
- ✅ Configuration displayed after selection
- ✅ Existing models can be reused or rebuilt

#### Research Commands

```bash
💡 Research Assistant Commands:

search <query>              # Search database
extract <NCT>              # Extract structured data
save <NCT>                 # Extract and save to JSON
query <question>           # Ask with RAG retrieval
stats                      # Database statistics
validate                   # Show valid field values
status                     # Connection status
help                       # Show commands
exit                       # Return to main menu
```

#### Example Research Session

**Search and Analyze:**
```bash
Research >>> search LEAP-2 peptide diabetes

Found 3 trial(s):
  • NCT04043065
  • NCT05123456
  • NCT05789012

Analyze these trials with AI? (y/n): y

🤔 Analyzing trials...

📊 Analysis:
These three trials investigate LEAP-2, an antimicrobial
peptide, for its glucoregulatory effects in type 2 
diabetes. NCT04043065 is a Phase 2 completed study...
```

**Extract Specific Trial:**
```bash
Research >>> extract NCT04043065

📋 Extracting data for NCT04043065...

📊 Structured Extraction:
NCT Number: NCT04043065
Study Title: A Leap to Understand Glucoregulatory Effects...
Study Status: COMPLETED
Phases: PHASE2
Classification: AMP
Delivery Mode: IV
Outcome: Positive
Peptide: True

Save this extraction? (json/txt/no): json
Filename [NCT04043065_extraction]: 

✅ Saved to output/NCT04043065_extraction.json
```

**Database Statistics:**
```bash
Research >>> stats

📊 Database Statistics:
  Total trials: 150
  Peptide trials: 42

  By Status:
    COMPLETED: 65
    RECRUITING: 45
    TERMINATED: 15
    WITHDRAWN: 10
    ACTIVE_NOT_RECRUITING: 15
```

**Query with Context:**
```bash
Research >>> query What peptide trials target infections?

🤔 Processing query (max 10 trials)...

💡 Answer:
Based on the database, 18 antimicrobial peptide trials
specifically target infections. Key trials include:

1. NCT03012345 - LL-37 for sepsis (Phase 3)
2. NCT04567890 - HBD-3 for wound infections (Phase 2)
3. NCT05123456 - Pexiganan for diabetic foot (Phase 2)

These trials focus on bacterial infections, with
delivery modes including IV infusion and topical
application...
```

---

## 🔑 API Configuration

### Environment Variables

Create `.env` file in project root:

```bash
# SSH Settings
SSH_DEFAULT_IP=100.99.162.98
SSH_DEFAULT_USERNAME=emilyzhang

# SERP API (Google Search)
SERPAPI_KEY=your_serpapi_key_here

# Semantic Scholar (optional)
SEMANTIC_SCHOLAR_API_KEY=your_key_here

# NCBI (PubMed - optional for higher rate limits)
NCBI_API_KEY=your_ncbi_key_here

# Meilisearch (if self-hosting)
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_KEY=your_master_key

# Swirl (if self-hosting)
SWIRL_URL=http://localhost:8000

# Output Settings
OUTPUT_DIR=output
LOG_FILE=amp_llm.log
LOG_LEVEL=INFO
```

### API Keys (How to Get)

**SERP API** (Google Search):
1. Sign up: https://serpapi.com
2. Free tier: 100 searches/month
3. Copy API key to `.env`

**Semantic Scholar** (Optional):
1. Sign up: https://www.semanticscholar.org/product/api
2. Increases rate limit
3. Free for research use

**NCBI E-utilities** (Optional):
1. Create NCBI account
2. Go to: https://www.ncbi.nlm.nih.gov/account/settings/
3. Increases rate limit to 10 req/sec

### API Status

| API | Auth Required | Rate Limit | Cost |
|-----|---------------|------------|------|
| ClinicalTrials.gov | No | Unlimited | Free |
| PubMed | No (key optional) | 3/sec | Free |
| PMC Full Text | No | 3/sec | Free |
| OpenFDA | No | 240/min | Free |
| DuckDuckGo | No | ~100/hour | Free |
| Health Canada | No | Unknown | Free |
| WHO ICTRP | No | Unknown | Free |
| EudraCT | No | Unknown | Free |
| Semantic Scholar | Optional | 100/5min (5000 with key) | Free |
| SERP API | Yes | 100/month (free tier) | Paid |
| Meilisearch | Optional | Unlimited | Self-hosted |
| Swirl | No | Unlimited | Self-hosted |

---

## 🎨 Custom Models

### Modelfile Structure

The `Modelfile` defines custom model behavior:

```dockerfile
FROM llama3.2

SYSTEM """You are a Clinical Trial Data Extraction Specialist.
Extract structured information from clinical trial JSON data.

## OUTPUT FORMAT
[Detailed format specifications]

## VALIDATION RULES
[Field validation rules]

## EXTRACTION GUIDELINES
[Step-by-step extraction process]
"""

PARAMETER temperature 0.15
PARAMETER top_p 0.9
PARAMETER num_ctx 8192
```

### Creating Custom Models

**Automatic Creation** (Recommended):
- Research Assistant (Option 5) prompts for creation
- Automatically uploads Modelfile
- Builds on remote server

**Manual Creation** (Advanced):
```bash
# SSH to remote server
ssh user@remote

# Create model
ollama create ct-research-assistant -f Modelfile

# Verify
ollama list
```

### Customizing Modelfile

**Adjust Temperature** (creativity vs accuracy):
```dockerfile
PARAMETER temperature 0.3   # More factual (recommended)
PARAMETER temperature 0.7   # More creative
```

**Increase Context Window**:
```dockerfile
PARAMETER num_ctx 16384   # Double the context
```

**Add Domain Knowledge**:
```dockerfile
SYSTEM """[Existing system prompt]

## Additional Domain Knowledge:
- Focus on antimicrobial peptides
- Prioritize Phase 2/3 trials
- Flag safety concerns
"""
```

### Model Management

**Understanding Model Types:**

1. **Base Models** (e.g., llama3.2, mistral)
   - General-purpose LLMs
   - Used directly or as foundation for custom models
   - Installed via `ollama pull <model>`

2. **Research Assistant** (ct-research-assistant:latest)
   - Custom model built from Modelfile
   - Specialized for clinical trial extraction
   - Built on top of a base model

**Workflow:**
```
Base Model (mistral)
        ↓
   [Modelfile applied]
        ↓
Research Assistant (ct-research-assistant:latest)
```

**List Models:**
```bash
# In LLM Workflow
LLM >>> models

📋 Available models (14):
  1. ct-research-assistant:latest  # Custom
  2. llama3.2                      # Base
  3. mistral                       # Base
  ...
```

**During Selection:**
- Only base models shown for selection
- Custom models filtered out to avoid confusion
- After selection, option to build Research Assistant

**Delete Model:**
```bash
# SSH to remote
ssh user@remote
ollama rm ct-research-assistant:latest
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. "No models found"

**Problem**: Ollama has no models installed

**Solution**:
```bash
# SSH to remote server
ssh user@remote

# Pull a model
ollama pull llama3.2

# Verify
ollama list
```

#### 2. "Cannot connect to Ollama"

**Problem**: Ollama not running or unreachable

**Solution**:
```bash
# SSH to remote
ssh user@remote

# Check Ollama status
systemctl status ollama

# Start if needed
systemctl start ollama

# Test API
curl http://localhost:11434/api/tags
```

#### 3. "SSH connection failed"

**Problem**: Cannot establish SSH connection

**Solution**:
- Verify IP address is correct
- Check username/password
- Ensure SSH server is running
- Check firewall rules

#### 4. "Modelfile not found"

**Problem**: Modelfile missing from project

**Solution**:
```bash
# Generate Modelfile
python scripts/generate_modelfile.py

# Or create manually in project root
touch Modelfile
# Add content from template
```

#### 5. "Database not found" (Research Assistant)

**Problem**: `ct_database/` directory missing

**Solution**:
```bash
# Create directory
mkdir ct_database

# Add JSON files
cp /path/to/trials/*.json ct_database/

# Verify
ls ct_database/
```

#### 6. "Extended API search failed"

**Problem**: API keys not configured or rate limits

**Solution**:
- Check `.env` file has API keys
- Verify API keys are valid
- Wait if rate limited
- Use selective API search (avoid "All")

#### 7. "Model creation failed"

**Problem**: Ollama cannot build model

**Causes & Solutions**:

**Base model selection issue:**
```bash
# Make sure to select from base models only
# System now automatically filters custom models

✅ Available base models:
  1) llama3.2    # ✅ Good
  2) mistral     # ✅ Good
  
❌ Don't select:
  ct-research-assistant:latest  # Filtered out automatically
```

**Insufficient disk space:**
```bash
ssh user@remote
df -h   # Check disk space
# Need ~5-10GB free
```

**Base model missing:**
```bash
ssh user@remote
ollama list        # Check available models
ollama pull llama3.2   # Pull if missing
```

**Permission issues:**
```bash
# Check Ollama service
systemctl status ollama

# Restart if needed
systemctl restart ollama
```

**Wrong Modelfile:**
```bash
# Ensure Modelfile exists in project root
ls -la Modelfile

# Regenerate if needed
python scripts/generate_modelfile.py
```

#### 8. "Ctrl+C doesn't work"

**Problem**: Application hangs on interrupt

**Solution**:
- Press Ctrl+C twice rapidly
- Application now properly handles interrupts
- Should return to main menu cleanly

### Debug Mode

**Enable detailed logging:**
```bash
# In .env
LOG_LEVEL=DEBUG

# Run application
python main.py

# Check logs
tail -f amp_llm.log
```

### Getting Help

1. **Check logs**: `amp_llm.log`
2. **Run validation**: `python scripts/validate_setup.py`
3. **Check connection**: Verify SSH and Ollama access
4. **Review docs**: `docs/` directory has detailed guides

---

## 👩‍💻 Development

### Project Structure

```
amp_llm_v3/
├── main.py                 # Entry point
├── Modelfile              # Custom model definition
├── requirements.txt       # Python dependencies
├── .env.example          # Environment template
├── .gitignore            # Git exclusions
│
├── src/amp_llm/          # Main package
│   ├── __init__.py
│   ├── __main__.py
│   │
│   ├── config/           # Configuration
│   │   ├── settings.py   # App settings
│   │   ├── logging.py    # Logging setup
│   │   └── validation.py # Data validation
│   │
│   ├── core/             # Core application
│   │   ├── app.py        # Main application
│   │   ├── menu.py       # Menu system
│   │   ├── ssh_manager.py # SSH management
│   │   ├── lifecycle.py  # App lifecycle
│   │   └── exceptions.py # Custom exceptions
│   │
│   ├── cli/              # CLI utilities
│   │   ├── formatters.py # Output formatting
│   │   ├── prompts.py    # User input
│   │   └── validators.py # Input validation
│   │
│   ├── network/          # Network utilities
│   │   ├── ssh.py        # SSH connection
│   │   ├── shell.py      # Interactive shell
│   │   └── ping.py       # Host ping
│   │
│   ├── llm/              # LLM integration
│   │   ├── handlers.py   # LLM workflows
│   │   ├── clients/      # API clients
│   │   ├── models/       # Model management
│   │   ├── utils/        # LLM utilities
│   │   └── assistants/   # Research assistant
│   │
│   └── data/             # Data operations
│       ├── nct_lookup.py # NCT search
│       ├── clinical_trials/ # Trial data
│       │   ├── fetchers/ # API fetchers
│       │   └── rag.py    # RAG system
│       └── external_apis/ # External APIs
│           ├── api_clients.py
│           ├── pmc_fulltext.py
│           ├── eudract.py
│           ├── who_ictrp.py
│           └── semantic_scholar.py
│
├── scripts/              # Utility scripts
│   ├── setup.py         # Environment setup
│   ├── generate_modelfile.py
│   └── validate_setup.py
│
├── docs/                 # Documentation
│   ├── README.md
│   ├── api/             # API docs
│   ├── guides/          # User guides
│   └── setup/           # Setup instructions
│
├── tests/               # Test suite
│   └── unit/            # Unit tests
│
├── output/              # Generated output
├── ct_database/         # Trial database
└── llm_env/             # Virtual environment
```

### Adding New Features

**1. New API Client:**
```python
# src/amp_llm/data/external_apis/my_api.py

class MyAPIClient:
    def __init__(self, timeout=30, max_results=10):
        self.timeout = timeout
        self.max_results = max_results
    
    async def search(self, query: str):
        # Implementation
        pass
```

**2. New Command:**
```python
# In src/amp_llm/llm/assistants/commands.py

async def cmd_mycommand(self, args: str):
    """Handle my custom command."""
    # Implementation
    pass

# Register in __init__
self.commands['mycommand'] = self.cmd_mycommand
```

**3. New Menu Item:**
```python
# In main menu registration

self.add_item(
    "7",
    "My New Feature",
    self._create_interrupt_safe_handler(
        my_handler_function,
        "My Feature"
    ),
    description="Description of feature",
)
```

### Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=src/amp_llm tests/

# Specific test
pytest tests/unit/cli/test_validators.py
```

### Code Style

```bash
# Format code
black src/

# Lint
ruff check src/

# Type checking
mypy src/
```

---

## 📊 Data Formats

### Clinical Trial Extraction Format

```
NCT Number: NCT04043065
Study Title: A Leap to Understand Glucoregulatory Effects...
Study Status: COMPLETED
Brief Summary: This clinical study is a multi-center...
Conditions: Type 2 Diabetes, Rheumatology
Interventions/Drug: Biological: LEAP-2, Other: Placebo
Phases: PHASE2
Enrollment: 124
Start Date: 2025-06-18
Completion Date: 2028-11
Classification: AMP
  Evidence: Study involves antimicrobial peptide for metabolism
Delivery Mode: IV
Sequence: N/A
DRAMP Name: LEAP-2
  Evidence: DRAMP database entry for LEAP-2
Study IDs: PMID:12345678, PMC:PMC7654321
Outcome: Positive
Reason for Failure: N/A
Subsequent Trial IDs: N/A
Peptide: True
Comments: Phase 2 trial investigating metabolic effects
```

### Validation Rules

**Study Status:**
- NOT_YET_RECRUITING
- RECRUITING
- ACTIVE_NOT_RECRUITING
- COMPLETED
- TERMINATED
- WITHDRAWN
- SUSPENDED
- UNKNOWN

**Phases:**
- EARLY_PHASE1
- PHASE1
- PHASE1|PHASE2
- PHASE2
- PHASE2|PHASE3
- PHASE3
- PHASE4

**Classification:**
- AMP - Antimicrobial peptide
- Other - Peptide that is not antimicrobial

**Outcome:**
- Positive
- Failed - completed trial
- Terminated
- Withdrawn
- Recruiting
- Active, not recruiting
- Unknown

---

## 🎯 Best Practices

### For Research

1. **Start with Research Assistant** (Option 5)
2. **Build trial database** with NCT Lookup (Option 4)
3. **Use structured extraction** for systematic analysis
4. **Export data** for external tools (Excel, R, Python)

### For Data Collection

1. **Use NCT Lookup** with "All APIs" for comprehensive data
2. **Batch process** multiple NCTs in one session
3. **Save results** as JSON for programmatic access
4. **Check extended APIs** for additional context

### For Model Customization

1. **Start with default** Modelfile
2. **Test thoroughly** with sample trials
3. **Adjust temperature** based on use case:
   - 0.1-0.3: Factual extraction
   - 0.4-0.6: Balanced analysis
   - 0.7+: Creative synthesis
4. **Keep backups** of working Modelfiles

### For Performance

1. **Use API Mode** (not SSH terminal) for LLM
2. **Enable selective APIs** instead of "All"
3. **Close unused connections**
4. **Monitor logs** for errors

---

## 📝 Changelog

### v3.0.0 (2025-01-10)

**Major Features:**
- ✨ Clinical Trial Research Assistant with RAG
- ✨ 10+ external API integrations
- ✨ Custom model building from Modelfile
- ✨ Enhanced LLM workflow with file loading
- ✨ Comprehensive interrupt handling

**New APIs:**
- PMC Full Text access
- EudraCT (European trials)
- WHO ICTRP (international trials)
- Semantic Scholar (AI-powered)

**Improvements:**
- ✅ **Fixed model selection workflow** - clear separation of base LLM selection and Research Assistant creation
- ✅ **Configuration display** - shows current model and capabilities
- ✅ **Base model filtering** - custom models excluded from selection to reduce confusion
- Automatic SSH tunneling
- Persistent Ollama sessions
- Graceful shutdown handling
- Enhanced error messages
- Improved validation

**Bug Fixes:**
- Fixed async shutdown warnings
- Fixed model creation on zsh
- Fixed interrupt handling in all workflows
- Fixed file loading paths
- **Fixed confusing model selection prompt** (removed "Create custom model" option from list)

---

## 📜 License

**Amphoraxe Life Sciences Inc.**

---

## 🙏 Acknowledgments

- **Ollama** - Local LLM runtime
- **NCBI** - PubMed/PMC access
- **OpenFDA** - Drug safety data
- **Semantic Scholar** - Academic search
- **asyncssh** - SSH connectivity
- **aiohttp** - Async HTTP

---

## 📧 Support

For issues, questions, or contributions:
- Check `amp_llm.log` for errors
- Review documentation in `docs/`
- Run validation: `python scripts/validate_setup.py`

---

**Version**: 3.0.0  
**Last Updated**: 2025-01-10  
**Python**: 3.8+  
**Platform**: Windows, macOS, Linux