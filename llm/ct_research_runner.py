"""
Clinical Trial Research Assistant LLM Runner
Complete version with all fixes applied:
- Save to JSON/TXT feature
- Proper error handling
- Return statements fixed
- None-safe printing

Version: 2.0 - Production Ready
"""
import asyncio
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from colorama import Fore, Style
from config import get_logger, get_config
from llm.async_llm_utils import list_remote_models_api, send_to_ollama_api
from data.clinical_trial_rag import ClinicalTrialRAG

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

logger = get_logger(__name__)
config = get_config()


# ==============================================================================
# HELPER FUNCTION: Parse LLM response to dictionary
# ==============================================================================

"""
Improved parse_extraction_to_dict function
Handles code blocks and placeholder text better
"""

def parse_extraction_to_dict(llm_response: str) -> dict:
    """
    Parse LLM extraction response into structured dictionary.
    Handles markdown code blocks and filters out placeholder text.
    """
    # Initialize result
    result = {
        "nct_number": "",
        "study_title": "",
        "study_status": "",
        "brief_summary": "",
        "conditions": [],
        "interventions": [],
        "phases": [],
        "enrollment": 0,
        "start_date": "",
        "completion_date": "",
        "classification": "",
        "classification_evidence": [],
        "delivery_mode": "",
        "sequence": "",
        "dramp_name": "",
        "dramp_evidence": [],
        "study_ids": [],
        "outcome": "",
        "failure_reason": "",
        "subsequent_trial_ids": [],
        "subsequent_evidence": [],
        "is_peptide": False,
        "comments": ""
    }
    
    # Remove markdown code blocks
    llm_response = re.sub(r'```[\w]*\n', '', llm_response)
    llm_response = re.sub(r'```', '', llm_response)
    
    # Define regex patterns
    patterns = {
        'nct_number': r'NCT Number:\s*(.+?)(?:\n|$)',
        'study_title': r'Study Title:\s*(.+?)(?:\n|$)',
        'study_status': r'Study Status:\s*(.+?)(?:\n|$)',
        'brief_summary': r'Brief Summary:\s*(.+?)(?:\nConditions:|$)',
        'conditions': r'Conditions:\s*(.+?)(?:\n|$)',
        'interventions': r'Interventions/Drug:\s*(.+?)(?:\n|$)',
        'phases': r'Phases:\s*(.+?)(?:\n|$)',
        'enrollment': r'Enrollment:\s*(\d+)',
        'start_date': r'Start Date:\s*(.+?)(?:\n|$)',
        'completion_date': r'Completion Date:\s*(.+?)(?:\n|$)',
        'classification': r'Classification:\s*(.+?)(?:\n|$)',
        'classification_evidence': r'Classification.*?Evidence:\s*(.+?)(?:\nDelivery Mode:|$)',
        'delivery_mode': r'Delivery Mode:\s*(.+?)(?:\n|$)',
        'sequence': r'Sequence:\s*(.+?)(?:\n|$)',
        'dramp_name': r'DRAMP Name:\s*(.+?)(?:\n|$)',
        'dramp_evidence': r'DRAMP.*?Evidence:\s*(.+?)(?:\nStudy IDs:|$)',
        'study_ids': r'Study IDs:\s*(.+?)(?:\n|$)',
        'outcome': r'Outcome:\s*(.+?)(?:\n|$)',
        'failure_reason': r'Reason for Failure:\s*(.+?)(?:\n|$)',
        'subsequent_trial_ids': r'Subsequent Trial IDs:\s*(.+?)(?:\n|$)',
        'subsequent_evidence': r'Subsequent.*?Evidence:\s*(.+?)(?:\nPeptide:|$)',
        'is_peptide': r'Peptide:\s*(.+?)(?:\n|$)',
        'comments': r'Comments:\s*(.+?)(?:\n```|$)',
    }
    
    # Extract each field
    for field, pattern in patterns.items():
        match = re.search(pattern, llm_response, re.DOTALL | re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            
            # Clean up
            value = value.strip('`').strip()
            
            # FILTER OUT PLACEHOLDER TEXT
            placeholder_patterns = [
                r'^\[.*\]$',  # [title here], [PHASE#], etc.
                r'NCT########',  # Placeholder NCT
                r'\[value from list\]',
                r'\[YYYY-MM-DD\]',
            ]
            
            is_placeholder = any(re.match(p, value) for p in placeholder_patterns)
            
            if is_placeholder:
                # Skip placeholder, use empty/default value
                if field == 'is_peptide':
                    result[field] = False
                elif field == 'enrollment':
                    result[field] = 0
                elif field in ('conditions', 'interventions', 'phases', 'study_ids', 
                              'subsequent_trial_ids', 'classification_evidence', 
                              'dramp_evidence', 'subsequent_evidence'):
                    result[field] = []
                else:
                    result[field] = ""
                continue
            
            # Parse based on field type
            if field == 'is_peptide':
                result[field] = value.lower() in ('true', 'yes')
            
            elif field == 'enrollment':
                try:
                    result[field] = int(value)
                except:
                    result[field] = 0
            
            elif field in ('conditions', 'interventions', 'phases', 'study_ids', 
                          'subsequent_trial_ids'):
                # Split comma-separated lists
                if value and value.lower() != 'n/a':
                    # Split by comma
                    items = [item.strip() for item in value.split(',')]
                    # Filter out placeholders and N/A
                    items = [
                        item for item in items 
                        if item and 
                        item != 'N/A' and 
                        not item.startswith('[') and 
                        not item.endswith('...]')
                    ]
                    result[field] = items
                else:
                    result[field] = []
            
            elif field in ('classification_evidence', 'dramp_evidence', 'subsequent_evidence'):
                # Evidence fields
                if value and value.lower() != 'n/a' and not value.startswith('['):
                    if ',' in value:
                        result[field] = [item.strip() for item in value.split(',')]
                    else:
                        result[field] = [value] if value else []
                else:
                    result[field] = []
            
            else:
                # String fields
                if value.lower() == 'n/a' or value.startswith('['):
                    result[field] = ""
                else:
                    result[field] = value
    
    return result


# ==============================================================================
# MAIN CLASS
# ==============================================================================

class ClinicalTrialResearchAssistant:
    """Enhanced LLM runner with RAG integration and save feature."""
    
    def __init__(self, database_path: Path):
        """Initialize research assistant."""
        self.rag = ClinicalTrialRAG(database_path)
        self.rag.db.build_index()
        self.model_name = "ct-research-assistant"
    
    async def ensure_model_exists(self, ssh, host: str, models: List[str]) -> bool:
        """
        Check if custom model exists, create if not.
        FIXED: Immediate return if exists, clearer prompts.
        """
        # IMMEDIATE CHECK - If exists, done!
        if self.model_name in models:
            await aprint(Fore.GREEN + f"✅ Using existing model: {self.model_name}")
            logger.info(f"Found existing model: {self.model_name}")
            return True
        
        # Not found - offer to create
        await aprint(Fore.YELLOW + f"\n🔧 Custom model '{self.model_name}' not found")
        await aprint(Fore.CYAN + "This is a one-time setup to create a specialized model.")
        
        create = await ainput(
            Fore.GREEN + f"Create '{self.model_name}' now? (y/n) [y]: "
        )
        
        if create.strip().lower() in ('n', 'no'):
            await aprint(Fore.YELLOW + "Skipped. You can use a base model instead.")
            return False
        
        # Show available base models
        await aprint(Fore.CYAN + f"\n📋 Available base models:")
        for i, model in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}) {model}")
        
        # Select base model
        choice = await ainput(
            Fore.GREEN + f"Select base model [1]: "
        )
        
        # Parse choice
        base_model = None
        choice = choice.strip()
        
        if not choice:
            base_model = models[0] if models else 'llama3:8b'
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                base_model = models[idx]
            else:
                await aprint(Fore.RED + "Invalid selection, using first available model")
                base_model = models[0] if models else 'llama3:8b'
        else:
            if choice in models:
                base_model = choice
            else:
                await aprint(Fore.YELLOW + f"Model '{choice}' not found, using '{models[0] if models else 'llama3:8b'}'")
                base_model = models[0] if models else 'llama3:8b'
        
        await aprint(Fore.CYAN + f"\n🏗️  Building '{self.model_name}' from base model '{base_model}'...")
        
        try:
            # Find local Modelfile
            search_paths = [
                Path(__file__).parent.parent / "Modelfile",
                Path(__file__).parent / "Modelfile",
                Path.cwd() / "Modelfile",
                Path.cwd() / "Claude_Async_Version" / "Modelfile",
            ]
            
            modelfile_path = None
            for path in search_paths:
                if path.exists():
                    modelfile_path = path
                    break
            
            if not modelfile_path:
                await aprint(Fore.RED + "❌ Modelfile not found!")
                await aprint(Fore.YELLOW + "Searched in:")
                for path in search_paths:
                    await aprint(Fore.YELLOW + f"  • {path}")
                return False
            
            await aprint(Fore.GREEN + f"✅ Found Modelfile at: {modelfile_path}")
            
            # Read and modify Modelfile
            with open(modelfile_path, 'r', encoding='utf-8') as f:
                modelfile_content = f.read()
            
            # Replace FROM line
            modelfile_content = re.sub(
                r'^FROM\s+\S+',
                f'FROM {base_model}',
                modelfile_content,
                flags=re.MULTILINE
            )
            
            await aprint(Fore.CYAN + f"📝 Replaced 'FROM' line with: FROM {base_model}")
            await aprint(Fore.CYAN + f"📤 Uploading Modelfile to remote server...")
            
            # Upload via SFTP
            import time
            temp_modelfile = f"/tmp/ct_modelfile_{int(time.time())}.modelfile"
            
            try:
                async with ssh.start_sftp_client() as sftp:
                    async with sftp.open(temp_modelfile, 'w') as remote_file:
                        await remote_file.write(modelfile_content)
                
                await aprint(Fore.GREEN + f"✅ Uploaded to {temp_modelfile}")
            except Exception as e:
                await aprint(Fore.RED + f"❌ SFTP upload failed: {e}")
                logger.error(f"SFTP error: {e}", exc_info=True)
                return False
            
            # Create model - USE BASH LOGIN SHELL
            await aprint(Fore.CYAN + f"🔨 Building model (this may take 1-2 minutes)...")
            await aprint(Fore.YELLOW + "    Please wait...")
            
            try:
                result = await ssh.run(
                    f'bash -l -c "ollama create {self.model_name} -f {temp_modelfile}"',
                    check=False
                )
                
                # Cleanup
                await ssh.run(f'rm -f {temp_modelfile}', check=False)
                
                if result.exit_status == 0:
                    await aprint(Fore.GREEN + f"\n✅ Success! Model '{self.model_name}' created!")
                    await aprint(Fore.CYAN + f"    Base: {base_model}")
                    await aprint(Fore.CYAN + f"    Name: {self.model_name}")
                    await aprint(Fore.CYAN + f"    Ready to use! 🚀")
                    logger.info(f"Created model {self.model_name} from {base_model}")
                    return True
                else:
                    await aprint(Fore.RED + f"\n❌ Model creation failed!")
                    await aprint(Fore.RED + f"Exit code: {result.exit_status}")
                    
                    if result.exit_status == 127:
                        await aprint(Fore.YELLOW + "\n💡 The 'ollama' command was not found.")
                        await aprint(Fore.YELLOW + "   Add ollama to PATH or create symlink")
                    
                    if result.stderr:
                        await aprint(Fore.RED + f"Error: {result.stderr}")
                    if result.stdout:
                        await aprint(Fore.YELLOW + f"Output: {result.stdout}")
                    return False
                    
            except Exception as e:
                await aprint(Fore.RED + f"❌ Error running ollama command: {e}")
                logger.error(f"Ollama create error: {e}", exc_info=True)
                await ssh.run(f'rm -f {temp_modelfile}', check=False)
                return False
                
        except Exception as e:
            await aprint(Fore.RED + f"❌ Unexpected error: {e}")
            logger.error(f"Model creation error: {e}", exc_info=True)
            return False


# ==============================================================================
# MAIN WORKFLOW
# ==============================================================================

# ==============================================================================
# MAIN WORKFLOW - FIXED VERSION
# ==============================================================================

async def run_ct_research_assistant(ssh):
    """Main research assistant workflow with FIXED model selection."""
    await aprint(Fore.CYAN + Style.BRIGHT + "\n=== 🔬 Clinical Trial Research Assistant ===")
    await aprint(Fore.WHITE + "RAG-powered intelligent analysis of clinical trial database\n")
    
    # Setup database path
    db_path_input = await ainput(
        Fore.CYAN + "Enter path to clinical trial database (JSON file or directory) [./ct_database]: "
    )
    db_path = Path(db_path_input.strip() or "./ct_database")
    
    if not db_path.exists():
        await aprint(Fore.RED + f"❌ Database path not found: {db_path}")
        await aprint(Fore.YELLOW + "Please ensure your JSON database exists at the specified path")
        return
    
    # Initialize assistant
    await aprint(Fore.YELLOW + "Initializing research assistant...")
    assistant = ClinicalTrialResearchAssistant(db_path)
    
    await aprint(Fore.GREEN + f"✅ Indexed {len(assistant.rag.db.trials)} clinical trials")
    
    # Get host and setup connection
    try:
        host = ssh._host if hasattr(ssh, '_host') else config.network.default_ip
    except:
        host = config.network.default_ip
    
    # Setup tunnel if needed
    await aprint(Fore.CYAN + f"\n🔗 Connecting to Ollama at {host}:11434...")
    models = await list_remote_models_api(host)
    tunnel_listener = None
    
    if not models:
        await aprint(Fore.YELLOW + "⚠️  Direct connection failed. Setting up SSH tunnel...")
        try:
            tunnel_listener = await ssh.forward_local_port('', 11434, 'localhost', 11434)
            await asyncio.sleep(1)
            host = 'localhost'
            models = await list_remote_models_api(host)
            await aprint(Fore.GREEN + "✅ SSH tunnel established successfully")
        except Exception as e:
            await aprint(Fore.RED + f"❌ Failed to setup tunnel: {e}")
            logger.error(f"Tunnel error: {e}", exc_info=True)
            return
    
    if not models:
        await aprint(Fore.RED + "❌ Cannot connect to Ollama on remote server")
        await aprint(Fore.YELLOW + "Please ensure Ollama is running: ollama list")
        return
    
    await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s) on remote server")
    
    # FIXED: Single model check and setup
    model_ready = await assistant.ensure_model_exists(ssh, host, models)
    
    if not model_ready:
        # Model creation failed or was cancelled - offer fallback
        await aprint(Fore.YELLOW + "\n⚠️  Custom model not available. Choose a base model instead:")
        
        # Refresh model list
        models = await list_remote_models_api(host)
        for i, m in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}) {m}")
        
        choice = await ainput(Fore.GREEN + "Select model to use: ")
        choice = choice.strip()
        
        if choice.isdigit() and 0 < int(choice) <= len(models):
            assistant.model_name = models[int(choice) - 1]
        elif choice in models:
            assistant.model_name = choice
        else:
            assistant.model_name = models[0] if models else "llama3:8b"
            await aprint(Fore.YELLOW + f"Using: {assistant.model_name}")
    
    await aprint(Fore.GREEN + f"\n✅ Using model: {assistant.model_name}")
    
    # [REST OF THE WORKFLOW - Commands, interaction loop, etc.]
    # Main interaction loop
    await aprint(Fore.CYAN + "\n💡 Research Assistant Commands:")
    await aprint(Fore.CYAN + "   • 'search <query>' - Search database and analyze trials")
    await aprint(Fore.CYAN + "   • 'extract <NCT>' - Extract structured data from specific trial")
    await aprint(Fore.CYAN + "   • 'save <NCT>' - Extract and save directly as JSON")
    await aprint(Fore.CYAN + "   • 'query <question>' - Ask question with auto-retrieval")
    await aprint(Fore.CYAN + "   • 'load <file>' - Load JSON file and analyze")
    await aprint(Fore.CYAN + "   • 'export <NCT1,NCT2,...>' - Export trials to JSON/CSV")
    await aprint(Fore.CYAN + "   • 'stats' - Show database statistics")
    await aprint(Fore.CYAN + "   • 'validate' - Show valid values for all fields")
    await aprint(Fore.CYAN + "   • 'exit' - Return to main menu\n")
    
    try:
        while True:
            try:
                user_input = await ainput(Fore.GREEN + "Research >>> " + Fore.WHITE)
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ('exit', 'quit', 'main menu'):
                    await aprint(Fore.YELLOW + "Returning to main menu...")
                    break
                
                # Parse command
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                # ============================================================
                # SEARCH COMMAND
                # ============================================================
                if command == 'search':
                    if not args:
                        await aprint(Fore.RED + "Usage: search <query>")
                        continue
                    
                    await aprint(Fore.YELLOW + f"\n🔍 Searching for: {args}")
                    nct_ids = assistant.rag.db.search(args)
                    
                    if not nct_ids:
                        await aprint(Fore.RED + "No trials found matching query")
                        continue
                    
                    await aprint(Fore.GREEN + f"Found {len(nct_ids)} trial(s):")
                    for nct in nct_ids:
                        await aprint(Fore.CYAN + f"  • {nct}")
                    
                    analyze = await ainput(
                        Fore.CYAN + "\nAnalyze these trials with AI? (y/n): "
                    )
                    
                    if analyze.lower() in ('y', 'yes'):
                        await aprint(Fore.YELLOW + "\n🤔 Analyzing trials...")
                        response = await assistant.query_with_rag(host, args)
                        
                        # FIXED: Check for None or error
                        if not response or response.startswith("Error:"):
                            await aprint(Fore.RED + f"\n{response}\n")
                        else:
                            await aprint(Fore.GREEN + "\n📊 Analysis:\n")
                            await aprint(Fore.WHITE + response + "\n")
                
                # ============================================================
                # EXTRACT COMMAND
                # ============================================================
                elif command == 'extract':
                    if not args:
                        await aprint(Fore.RED + "Usage: extract <NCT_NUMBER>")
                        continue
                    
                    nct = args.upper().strip()
                    await aprint(Fore.YELLOW + f"\n📋 Extracting data for {nct}...")
                    
                    response = await assistant.extract_from_nct(host, nct)
                    
                    # FIXED: Check for None or error
                    if not response or response.startswith("Error:") or response.startswith("NCT number") or response.startswith("Could not"):
                        await aprint(Fore.RED + f"\n{response}\n")
                    else:
                        await aprint(Fore.GREEN + "\n📊 Structured Extraction:\n")
                        await aprint(Fore.WHITE + response + "\n")
                        
                        # Ask to save
                        save_choice = await ainput(
                            Fore.CYAN + "Save this extraction? (json/txt/no) [no]: "
                        )
                        save_choice = save_choice.strip().lower()
                        
                        if save_choice in ('json', 'txt'):
                            default_filename = f"{nct}_extraction"
                            filename = await ainput(
                                Fore.CYAN + f"Filename (without extension) [{default_filename}]: "
                            )
                            filename = filename.strip() or default_filename
                            
                            output_dir = Path('output')
                            output_dir.mkdir(exist_ok=True)
                            output_path = output_dir / f"{filename}.{save_choice}"
                            
                            try:
                                if save_choice == 'json':
                                    extraction_dict = parse_extraction_to_dict(response)
                                    
                                    with open(output_path, 'w', encoding='utf-8') as f:
                                        json.dump(extraction_dict, f, indent=2, ensure_ascii=False)
                                    
                                    await aprint(Fore.GREEN + f"✅ Saved as JSON: {output_path}")
                                    
                                    preview = json.dumps(extraction_dict, indent=2)[:300]
                                    await aprint(Fore.CYAN + "\n📄 Preview:")
                                    await aprint(Fore.WHITE + preview + "...\n")
                                    
                                else:  # txt
                                    with open(output_path, 'w', encoding='utf-8') as f:
                                        f.write(response)
                                    
                                    await aprint(Fore.GREEN + f"✅ Saved as text: {output_path}")
                                
                                logger.info(f"Saved extraction to {output_path}")
                                
                            except Exception as e:
                                await aprint(Fore.RED + f"❌ Error saving: {e}")
                                logger.error(f"Error saving extraction: {e}", exc_info=True)
                
                # ============================================================
                # SAVE COMMAND
                # ============================================================
                elif command == 'save':
                    if not args:
                        await aprint(Fore.RED + "Usage: save <NCT_NUMBER>")
                        continue
                    
                    nct = args.upper().strip()
                    await aprint(Fore.YELLOW + f"\n💾 Extracting and saving {nct}...")
                    
                    response = await assistant.extract_from_nct(host, nct)
                    
                    # FIXED: Check for errors before parsing
                    if not response or response.startswith("Error:") or response.startswith("NCT number") or response.startswith("Could not"):
                        await aprint(Fore.RED + f"\n{response}\n")
                        continue
                    
                    try:
                        extraction_dict = parse_extraction_to_dict(response)
                        
                        default_filename = f"{nct}_extraction"
                        filename = await ainput(
                            Fore.CYAN + f"Filename [{default_filename}]: "
                        )
                        filename = filename.strip() or default_filename
                        
                        output_dir = Path('output')
                        output_dir.mkdir(exist_ok=True)
                        output_path = output_dir / f"{filename}.json"
                        
                        with open(output_path, 'w', encoding='utf-8') as f:
                            json.dump(extraction_dict, f, indent=2, ensure_ascii=False)
                        
                        await aprint(Fore.GREEN + f"\n✅ Saved to: {output_path}")
                        
                        preview_lines = json.dumps(extraction_dict, indent=2).split('\n')[:15]
                        preview = '\n'.join(preview_lines)
                        await aprint(Fore.CYAN + "\n📄 Preview:")
                        await aprint(Fore.WHITE + preview + "\n  ...\n")
                        
                    except Exception as e:
                        await aprint(Fore.RED + f"❌ Error: {e}")
                        logger.error(f"Error in save command: {e}", exc_info=True)
                
                # ============================================================
                # QUERY COMMAND
                # ============================================================
                elif command == 'query':
                    if not args:
                        await aprint(Fore.RED + "Usage: query <question>")
                        continue
                    
                    await aprint(Fore.YELLOW + f"\n🤔 Processing query...")
                    response = await assistant.query_with_rag(host, args)
                    
                    # FIXED: Check for None or error
                    if not response or response.startswith("Error:"):
                        await aprint(Fore.RED + f"\n{response}\n")
                    else:
                        await aprint(Fore.GREEN + "\n💡 Answer:\n")
                        await aprint(Fore.WHITE + response + "\n")
                
                # ============================================================
                # STATS COMMAND
                # ============================================================
                elif command == 'stats':
                    total = len(assistant.rag.db.trials)
                    await aprint(Fore.CYAN + f"\n📊 Database Statistics:")
                    await aprint(Fore.WHITE + f"  Total trials: {total}")
                    
                    status_counts = {}
                    peptide_count = 0
                    
                    for nct, trial in assistant.rag.db.trials.items():
                        try:
                            extraction = assistant.rag.db.extract_structured_data(nct)
                            if extraction:
                                status = extraction.study_status
                                status_counts[status] = status_counts.get(status, 0) + 1
                                if extraction.is_peptide:
                                    peptide_count += 1
                        except:
                            pass
                    
                    await aprint(Fore.WHITE + f"  Peptide trials: {peptide_count}")
                    await aprint(Fore.CYAN + "\n  By Status:")
                    for status, count in sorted(status_counts.items()):
                        await aprint(Fore.WHITE + f"    {status}: {count}")
                    
                    await aprint("")
                
                # ============================================================
                # VALIDATE COMMAND
                # ============================================================
                elif command == 'validate':
                    from data.clinical_trial_rag import (
                        StudyStatus, Phase, Classification, 
                        DeliveryMode, Outcome, FailureReason
                    )
                    
                    await aprint(Fore.CYAN + "\n📋 Valid Values for All Fields:\n")
                    
                    await aprint(Fore.GREEN + "Study Status (choose ONE):")
                    for status in StudyStatus:
                        await aprint(Fore.WHITE + f"  • {status.value}")
                    
                    await aprint(Fore.GREEN + "\nPhases (can be multiple):")
                    for phase in Phase:
                        await aprint(Fore.WHITE + f"  • {phase.value}")
                    
                    await aprint(Fore.GREEN + "\nClassification (choose ONE):")
                    for cls in Classification:
                        await aprint(Fore.WHITE + f"  • {cls.value}")
                    
                    await aprint(Fore.GREEN + "\nDelivery Mode (choose ONE):")
                    for mode in DeliveryMode:
                        await aprint(Fore.WHITE + f"  • {mode.value}")
                    
                    await aprint(Fore.GREEN + "\nOutcome (choose ONE):")
                    for outcome in Outcome:
                        await aprint(Fore.WHITE + f"  • {outcome.value}")
                    
                    await aprint(Fore.GREEN + "\nReason for Failure (choose ONE if applicable):")
                    for reason in FailureReason:
                        await aprint(Fore.WHITE + f"  • {reason.value}")
                    
                    await aprint(Fore.GREEN + "\nPeptide:")
                    await aprint(Fore.WHITE + "  • True")
                    await aprint(Fore.WHITE + "  • False")
                    await aprint("")
                
                # ============================================================
                # EXPORT COMMAND
                # ============================================================
                elif command == 'export':
                    if not args:
                        await aprint(Fore.RED + "Usage: export <NCT1,NCT2,...>")
                        continue
                    
                    nct_list = [n.strip().upper() for n in args.split(',')]
                    
                    fmt = await ainput(
                        Fore.CYAN + "Export format (json/csv) [json]: "
                    )
                    fmt = fmt.strip().lower() or 'json'
                    
                    if fmt not in ('json', 'csv'):
                        await aprint(Fore.RED + "Invalid format. Use 'json' or 'csv'")
                        continue
                    
                    default_name = f"ct_export_{len(nct_list)}_trials"
                    filename = await ainput(
                        Fore.CYAN + f"Filename [{default_name}]: "
                    )
                    filename = filename.strip() or default_name
                    
                    output_path = Path('output') / f"{filename}.{fmt}"
                    output_path.parent.mkdir(exist_ok=True)
                    
                    await aprint(Fore.YELLOW + f"Exporting {len(nct_list)} trial(s)...")
                    
                    try:
                        assistant.rag.export_extractions(nct_list, output_path, fmt)
                        await aprint(Fore.GREEN + f"✅ Exported to {output_path}")
                    except Exception as e:
                        await aprint(Fore.RED + f"❌ Export failed: {e}")
                
                # ============================================================
                # LOAD COMMAND
                # ============================================================
                elif command == 'load':
                    if not args:
                        await aprint(Fore.RED + "Usage: load <filename>")
                        continue
                    
                    file_path = Path(args.strip())
                    
                    search_paths = [
                        file_path,
                        Path('output') / file_path.name,
                        Path('.') / file_path.name,
                    ]
                    
                    found = None
                    for path in search_paths:
                        if path.exists() and path.is_file():
                            found = path
                            break
                    
                    if not found:
                        await aprint(Fore.RED + f"❌ File not found: {args}")
                        continue
                    
                    try:
                        with open(found, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        await aprint(Fore.GREEN + f"✅ Loaded {found.name} ({len(content)} chars)")
                        
                        action = await ainput(
                            Fore.CYAN + "Analyze as trial data? (y/n): "
                        )
                        
                        if action.lower() in ('y', 'yes'):
                            try:
                                trial_data = json.loads(content)
                                nct = trial_data.get('nct_id') or assistant.rag.db._extract_nct_from_data(trial_data)
                                
                                if nct:
                                    await aprint(Fore.YELLOW + f"\n📋 Analyzing {nct}...")
                                    response = await assistant.extract_from_nct(host, nct)
                                else:
                                    prompt = f"Analyze this clinical trial data:\n\n{content[:4000]}"
                                    response = await send_to_ollama_api(host, assistant.model_name, prompt)
                                
                                if response:
                                    await aprint(Fore.GREEN + "\n📊 Analysis:\n")
                                    await aprint(Fore.WHITE + response + "\n")
                                else:
                                    await aprint(Fore.RED + "❌ No response from LLM\n")
                                
                            except json.JSONDecodeError:
                                await aprint(Fore.RED + "❌ File is not valid JSON")
                    
                    except Exception as e:
                        await aprint(Fore.RED + f"❌ Error: {e}")
                
                # ============================================================
                # DIRECT QUERY (no command prefix)
                # ============================================================
                else:
                    await aprint(Fore.YELLOW + "\n🤔 Processing query...")
                    response = await assistant.query_with_rag(host, user_input)
                    
                    # FIXED: Check for None or error
                    if not response or response.startswith("Error:"):
                        await aprint(Fore.RED + f"\n{response}\n")
                    else:
                        await aprint(Fore.GREEN + "\n💡 Answer:\n")
                        await aprint(Fore.WHITE + response + "\n")
            
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to quit.")
                continue
            except Exception as e:
                await aprint(Fore.RED + f"Error: {e}")
                logger.error(f"Error in research assistant: {e}", exc_info=True)
            pass
    finally:
        # Cleanup
        if tunnel_listener:
            try:
                tunnel_listener.close()
                await aprint(Fore.YELLOW + "Closed SSH tunnel")
            except Exception as e:
                logger.error(f"Error closing tunnel: {e}")