# Clinical Trial Research Assistant

🔬 **RAG-powered AI assistant for extracting and analyzing clinical trial data from JSON databases**

## Quick Start (3 Minutes)

### 1. Copy Files
```bash
# Copy 3 files to your Claude_Async_Version/
Modelfile                      → project root
data/clinical_trial_rag.py     → data/
llm/ct_research_runner.py      → llm/
```

### 2. Setup Database
```bash
mkdir ct_database
cp your_nct_files/*.json ct_database/
```

### 3. Update main.py
```python
# Add import
from llm.ct_research_runner import run_ct_research_assistant

# Add menu option 5
elif choice in ("5", "research"):
    await run_ct_research_assistant(self.ssh_connection)
```

### 4. Run
```bash
python main.py
# Select option 5
```

## Features

✅ **Automatic Extraction**: 20+ structured fields from each trial  
✅ **Universal Model Support**: Works with ANY Ollama model  
✅ **Local Modelfile**: Kept locally, auto-uploaded when needed  
✅ **Smart Search**: By NCT, condition, drug, keyword  
✅ **Evidence Linking**: Tracks sources for classifications  
✅ **Peptide Detection**: Identifies AMP-related trials  
✅ **Export**: JSON/CSV for Excel analysis  

## Extracted Fields

```
✓ NCT Number              ✓ Classification + Evidence
✓ Title & Status          ✓ Delivery Mode
✓ Summary                 ✓ Sequence
✓ Conditions              ✓ DRAMP Name + Evidence
✓ Interventions/Drugs     ✓ Study IDs (PMID, DOI, PMC)
✓ Phases                  ✓ Outcome
✓ Enrollment              ✓ Failure Reason
✓ Start/End Dates         ✓ Subsequent Trials + Evidence
                          ✓ Peptide (Yes/No)
                          ✓ AI Comments
```

## Commands

```bash
search <query>          # Find trials in database
extract <NCT>           # Get structured extraction
query <question>        # Ask with auto-retrieval
load <file>             # Analyze JSON file
export <NCT,NCT>        # Export to JSON/CSV
stats                   # Show database statistics
exit                    # Return to main menu
```

## Example Usage

```
Research >>> search LEAP-2

Found 1 trial(s):
  • NCT04043065

Analyze? y

[AI provides complete structured extraction with all fields]

Research >>> export NCT04043065

Format: csv
Filename: leap2_trial
✅ Exported to output/leap2_trial.csv
```

## How Model Creation Works

**First run only** (1-2 minutes):
1. System checks for `ct-research-assistant` model
2. If not found, shows available base models
3. You select one (e.g., llama3.2)
4. Modelfile auto-uploads via SFTP
5. Custom model builds on remote server
6. Model persists for future use

**Subsequent runs**: Uses existing model instantly!

## Files Overview

| File | Purpose |
|------|---------|
| `Modelfile` | AI behavior definition (local) |
| `clinical_trial_rag.py` | Database indexing & extraction |
| `ct_research_runner.py` | Main assistant logic |

## Documentation

- `INTEGRATION_GUIDE.md` - Technical details
- `QUICK_START.md` - Examples & workflows  
- `MODELFILE_SETUP.md` - Customization guide
- `COMPLETE_SETUP_SUMMARY.md` - Full overview
- `test_setup.py` - Verify installation

## Verify Setup

```bash
python test_setup.py
```

Should show:
```
✅ PASS - Imports
✅ PASS - Files
✅ PASS - Modelfile
✅ PASS - Database
✅ PASS - Rag

🎉 All checks passed!
```

## Requirements

- Python 3.8+
- asyncssh, aiohttp, aioconsole, colorama
- SSH access to remote server with Ollama
- JSON clinical trial database

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Modelfile not found | Place in project root (where main.py is) |
| No trials found | Add JSON files to `ct_database/` |
| Model creation fails | Check `ollama list` on remote, pull base model |
| Poor extractions | Lower temperature in Modelfile (0.1) |

## Customization

**Add fields** → Edit `ClinicalTrialExtraction` class  
**Change AI behavior** → Edit `Modelfile` SYSTEM section  
**Enhanced search** → Modify `search()` method  
**New commands** → Add to command handler  

## Architecture

```
User → Research Assistant → RAG System → JSON Database
         ↓                      ↑
    Ollama (Remote)    ←────────┘
    Custom Model
    (from local Modelfile)
```

## JSON Format

Your files should match this structure:
```json
{
  "nct_id": "NCT########",
  "sources": {
    "clinical_trials": {
      "data": {
        "protocolSection": {
          "identificationModule": {...},
          "statusModule": {...},
          "descriptionModule": {...},
          "conditionsModule": {...},
          "armsInterventionsModule": {...}
        }
      }
    },
    "pubmed": {"pmids": [...], "studies": [...]},
    "pmc": {"pmcids": [...], "summaries": [...]}
  }
}
```

See `nctload.txt` for complete example.

## License

Part of AMP_LLM project.

## Support

- Run `python test_setup.py` for diagnostics
- Check `amp_llm.log` for errors
- Enable debug: `LOG_LEVEL=DEBUG python main.py`

---

**Ready to start?** → `python main.py` → Option 5 → Start researching! 🚀
