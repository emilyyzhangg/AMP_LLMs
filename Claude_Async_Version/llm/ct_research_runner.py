"""
Clinical Trial Research Assistant LLM Runner
Integrates RAG system with Ollama API for intelligent trial analysis.
"""
import asyncio
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


class ClinicalTrialResearchAssistant:
    """Enhanced LLM runner with RAG integration."""
    
    def __init__(self, database_path: Path):
        """
        Initialize research assistant.
        
        Args:
            database_path: Path to clinical trial JSON database
        """
        self.rag = ClinicalTrialRAG(database_path)
        self.rag.db.build_index()
        self.model_name = "ct-research-assistant"  # Custom model name
        
    async def ensure_model_exists(self, ssh, host: str, models: List[str]) -> bool:
        """
        Check if custom model exists, create if not using local Modelfile.
        
        Args:
            ssh: SSH connection
            host: Ollama host (localhost if tunneled)
            models: List of available models on remote
            
        Returns:
            True if model is ready, False otherwise
        """
        # Check if custom model already exists
        if self.model_name in models:
            await aprint(Fore.GREEN + f"✅ Custom model '{self.model_name}' already exists")
            return True
        
        await aprint(Fore.YELLOW + f"\n🔧 Custom model '{self.model_name}' not found. Let's create it!")
        
        # Show available base models
        await aprint(Fore.CYAN + f"\n📋 Available base models on remote server:")
        for i, model in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}) {model}")
        
        # Let user select base model
        await aprint(Fore.CYAN + f"\n💡 The custom model will be built on top of one of these.")
        choice = await ainput(
            Fore.GREEN + f"Select base model by number or name [{models[0] if models else 'llama3.2'}]: "
        )
        
        # Parse choice
        base_model = None
        choice = choice.strip()
        
        if not choice:
            base_model = models[0] if models else 'llama3.2'
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                base_model = models[idx]
            else:
                await aprint(Fore.RED + "Invalid selection, using first available model")
                base_model = models[0] if models else 'llama3.2'
        else:
            # Direct name entry
            if choice in models:
                base_model = choice
            else:
                await aprint(Fore.YELLOW + f"Model '{choice}' not found, using '{models[0] if models else 'llama3.2'}'")
                base_model = models[0] if models else 'llama3.2'
        
        await aprint(Fore.CYAN + f"\n🏗️  Building '{self.model_name}' from '{base_model}'...")
        
        try:
            # Find local Modelfile - check multiple locations
            search_paths = [
                Path(__file__).parent.parent / "Modelfile",  # Project root
                Path(__file__).parent / "Modelfile",         # llm directory
                Path.cwd() / "Modelfile",                    # Current directory
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
                await aprint(Fore.CYAN + "\n💡 Place 'Modelfile' in your project root directory")
                return False
            
            await aprint(Fore.GREEN + f"✅ Found Modelfile at: {modelfile_path}")
            
            # Read local Modelfile
            with open(modelfile_path, 'r', encoding='utf-8') as f:
                modelfile_content = f.read()
            
            # Replace FROM line with selected base model
            import re
            modelfile_content = re.sub(
                r'^FROM\s+\S+',
                f'FROM {base_model}',
                modelfile_content,
                flags=re.MULTILINE
            )
            
            await aprint(Fore.CYAN + f"📤 Uploading Modelfile to remote server...")
            
            # Create temporary path on remote
            import time
            temp_modelfile = f"/tmp/ct_modelfile_{int(time.time())}.modelfile"
            
            # Upload via SFTP
            try:
                async with ssh.start_sftp_client() as sftp:
                    async with sftp.open(temp_modelfile, 'w') as remote_file:
                        await remote_file.write(modelfile_content)
                
                await aprint(Fore.GREEN + f"✅ Uploaded to {temp_modelfile}")
            except Exception as e:
                await aprint(Fore.RED + f"❌ SFTP upload failed: {e}")
                logger.error(f"SFTP error: {e}", exc_info=True)
                return False
            
            # Create model on remote server
            await aprint(Fore.CYAN + f"🔨 Building model (this may take 1-2 minutes)...")
            await aprint(Fore.YELLOW + "    Please wait...")
            
            try:
                # Run ollama create command
                result = await ssh.run(
                    f'ollama create {self.model_name} -f {temp_modelfile}',
                    check=False
                )
                
                # Cleanup temp file
                await ssh.run(f'rm -f {temp_modelfile}', check=False)
                
                if result.exit_status == 0:
                    await aprint(Fore.GREEN + f"\n✅ Success! Model '{self.model_name}' created!")
                    await aprint(Fore.CYAN + f"    Base: {base_model}")
                    await aprint(Fore.CYAN + f"    Name: {self.model_name}")
                    return True
                else:
                    await aprint(Fore.RED + f"\n❌ Model creation failed!")
                    await aprint(Fore.RED + f"Exit code: {result.exit_status}")
                    if result.stderr:
                        await aprint(Fore.RED + f"Error: {result.stderr}")
                    if result.stdout:
                        await aprint(Fore.YELLOW + f"Output: {result.stdout}")
                    return False
                    
            except Exception as e:
                await aprint(Fore.RED + f"❌ Error running ollama command: {e}")
                logger.error(f"Ollama create error: {e}", exc_info=True)
                # Try to cleanup
                await ssh.run(f'rm -f {temp_modelfile}', check=False)
                return False
                
        except Exception as e:
            await aprint(Fore.RED + f"❌ Unexpected error: {e}")
            logger.error(f"Model creation error: {e}", exc_info=True)
            return False
    
    async def query_with_rag(
        self, 
        host: str, 
        user_query: str,
        auto_retrieve: bool = True
    ) -> str:
        """
        Query LLM with RAG-enhanced context.
        
        Args:
            host: Ollama host
            user_query: User's question
            auto_retrieve: Whether to automatically retrieve relevant trials
            
        Returns:
            LLM response
        """
        # Build prompt with RAG context
        if auto_retrieve:
            # Retrieve relevant trials
            context = self.rag.get_context_for_llm(user_query, max_trials=5)
            
            enhanced_prompt = f"""Context: Clinical trial database information
            
{context}

User Query: {user_query}

Please analyze the clinical trial(s) above and provide a comprehensive answer using the structured format. Extract all requested fields and provide evidence-based analysis."""
        else:
            # Direct query without retrieval
            enhanced_prompt = user_query
        
        # Send to LLM
        response = await send_to_ollama_api(
            host=host,
            model=self.model_name,
            prompt=enhanced_prompt
        )
        
        return response
    
    async def extract_from_nct(
        self,
        host: str,
        nct_number: str,
        validate: bool = True
    ) -> str:
        """
        Extract structured data from specific NCT number.
        
        Args:
            host: Ollama host
            nct_number: NCT number to extract
            validate: Whether to show validation warnings
            
        Returns:
            Structured extraction
        """
        # Get trial data
        trial_data = self.rag.db.get_trial(nct_number)
        
        if not trial_data:
            return f"NCT number {nct_number} not found in database."
        
        # Get structured extraction
        extraction = self.rag.db.extract_structured_data(nct_number)
        
        if not extraction:
            return f"Could not extract data from {nct_number}"
        
        # Validate extraction
        if validate:
            errors = extraction.get_validation_errors()
            if errors:
                await aprint(Fore.YELLOW + "\n⚠️  Validation warnings:")
                for error in errors:
                    await aprint(Fore.YELLOW + f"  • {error}")
                await aprint("")
        
        # Format as prompt for LLM refinement
        import json
        trial_json = json.dumps(trial_data, indent=2)
        
        prompt = f"""Extract and analyze this clinical trial data in the structured format:

Raw Trial Data (JSON):
```json
{trial_json}
```

CRITICAL: You MUST use exact values from the validation lists for:
- Study Status (NOT_YET_RECRUITING, RECRUITING, etc.)
- Phases (EARLY_PHASE1, PHASE1, PHASE2, etc.)
- Classification (AMP(infection), AMP(other), or Other)
- Delivery Mode (Injection/Infusion - Intramuscular, IV, Oral - Tablet, etc.)
- Outcome (Positive, Withdrawn, Terminated, etc.)
- Reason for Failure (Business Reason, Ineffective for purpose, etc.)
- Peptide (True or False)

Please provide a complete structured extraction following the template format. Include analysis and evidence where available."""
        
        response = await send_to_ollama_api(
            host=host,
            model=self.model_name,
            prompt=prompt
        )
        
        return response


async def run_ct_research_assistant(ssh):
    """Main research assistant workflow."""
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
    
    # Get host
    try:
        host = ssh._host if hasattr(ssh, '_host') else config.network.default_ip
    except:
        host = config.network.default_ip
    
    # Setup tunnel if needed
    models = await list_remote_models_api(host)
    tunnel_listener = None
    
    if not models:
        await aprint(Fore.YELLOW + "Setting up SSH tunnel...")
        try:
            tunnel_listener = await ssh.forward_local_port('', 11434, 'localhost', 11434)
            await asyncio.sleep(1)
            host = 'localhost'
            models = await list_remote_models_api(host)
            await aprint(Fore.GREEN + "✅ SSH tunnel established")
        except Exception as e:
            await aprint(Fore.RED + f"Failed to setup tunnel: {e}")
            return
    
    if not models:
        await aprint(Fore.RED + "❌ Cannot connect to Ollama on remote server")
        await aprint(Fore.YELLOW + "Please ensure Ollama is running: ollama list")
        return
    
    # Ensure custom model exists (pass models list)
    model_ready = await assistant.ensure_model_exists(ssh, host, models)
    
    if not model_ready:
        await aprint(Fore.YELLOW + "\n⚠️  Could not create custom model. Let's use a base model instead.")
        
        # Refresh models list in case something changed
        models = await list_remote_models_api(host)
        await aprint(Fore.CYAN + "\nAvailable models:")
        for i, m in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}) {m}")
        
        choice = await ainput(Fore.GREEN + "Select model to use: ")
        choice = choice.strip()
        
        if choice.isdigit() and 0 < int(choice) <= len(models):
            assistant.model_name = models[int(choice) - 1]
        elif choice in models:
            assistant.model_name = choice
        else:
            assistant.model_name = models[0] if models else "llama3.2"
            await aprint(Fore.YELLOW + f"Using: {assistant.model_name}")
    
    await aprint(Fore.GREEN + f"\n✅ Using model: {assistant.model_name}")
    
    # Main interaction loop
    await aprint(Fore.CYAN + "\n💡 Research Assistant Commands:")
    await aprint(Fore.CYAN + "   • 'search <query>' - Search database and analyze trials")
    await aprint(Fore.CYAN + "   • 'extract <NCT>' - Extract structured data from specific trial")
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
                
                # Handle commands
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                # Search command
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
                    
                    # Ask if user wants analysis
                    analyze = await ainput(
                        Fore.CYAN + "\nAnalyze these trials with AI? (y/n): "
                    )
                    
                    if analyze.lower() in ('y', 'yes'):
                        await aprint(Fore.YELLOW + "\n🤔 Analyzing trials...")
                        response = await assistant.query_with_rag(host, args)
                        await aprint(Fore.GREEN + "\n📊 Analysis:\n")
                        await aprint(Fore.WHITE + response + "\n")
                
                # Extract command
                elif command == 'extract':
                    if not args:
                        await aprint(Fore.RED + "Usage: extract <NCT_NUMBER>")
                        continue
                    
                    nct = args.upper().strip()
                    await aprint(Fore.YELLOW + f"\n📋 Extracting data for {nct}...")
                    
                    response = await assistant.extract_from_nct(host, nct)
                    await aprint(Fore.GREEN + "\n📊 Structured Extraction:\n")
                    await aprint(Fore.WHITE + response + "\n")
                
                # Query command
                elif command == 'query':
                    if not args:
                        await aprint(Fore.RED + "Usage: query <question>")
                        continue
                    
                    await aprint(Fore.YELLOW + f"\n🤔 Processing query...")
                    response = await assistant.query_with_rag(host, args)
                    await aprint(Fore.GREEN + "\n💡 Answer:\n")
                    await aprint(Fore.WHITE + response + "\n")
                
                # Load file command
                elif command == 'load':
                    if not args:
                        await aprint(Fore.RED + "Usage: load <filename>")
                        continue
                    
                    file_path = Path(args.strip())
                    
                    # Search for file
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
                        
                        # Ask what to do with it
                        action = await ainput(
                            Fore.CYAN + "Analyze as trial data? (y/n): "
                        )
                        
                        if action.lower() in ('y', 'yes'):
                            import json
                            try:
                                trial_data = json.loads(content)
                                nct = trial_data.get('nct_id') or assistant.rag.db._extract_nct_from_data(trial_data)
                                
                                if nct:
                                    await aprint(Fore.YELLOW + f"\n📋 Analyzing {nct}...")
                                    response = await assistant.extract_from_nct(host, nct)
                                else:
                                    # Generic analysis
                                    prompt = f"Analyze this clinical trial data and extract all relevant information:\n\n{content[:4000]}"
                                    response = await send_to_ollama_api(host, assistant.model_name, prompt)
                                
                                await aprint(Fore.GREEN + "\n📊 Analysis:\n")
                                await aprint(Fore.WHITE + response + "\n")
                                
                            except json.JSONDecodeError:
                                await aprint(Fore.RED + "❌ File is not valid JSON")
                    
                    except Exception as e:
                        await aprint(Fore.RED + f"❌ Error: {e}")
                
                # Export command
                elif command == 'export':
                    if not args:
                        await aprint(Fore.RED + "Usage: export <NCT1,NCT2,...>")
                        continue
                    
                    nct_list = [n.strip().upper() for n in args.split(',')]
                    
                    # Ask for format
                    fmt = await ainput(
                        Fore.CYAN + "Export format (json/csv) [json]: "
                    )
                    fmt = fmt.strip().lower() or 'json'
                    
                    if fmt not in ('json', 'csv'):
                        await aprint(Fore.RED + "Invalid format. Use 'json' or 'csv'")
                        continue
                    
                    # Ask for filename
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
                
                # Stats command
                elif command == 'stats':
                    total = len(assistant.rag.db.trials)
                    await aprint(Fore.CYAN + f"\n📊 Database Statistics:")
                    await aprint(Fore.WHITE + f"  Total trials: {total}")
                    
                    # Count by status
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
                
                # Validate command - show valid values
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
                
                # Direct query (no command prefix)
                else:
                    await aprint(Fore.YELLOW + "\n🤔 Processing query...")
                    response = await assistant.query_with_rag(host, user_input)
                    await aprint(Fore.GREEN + "\n💡 Answer:\n")
                    await aprint(Fore.WHITE + response + "\n")
            
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to quit.")
                continue
            except Exception as e:
                await aprint(Fore.RED + f"Error: {e}")
                logger.error(f"Error in research assistant: {e}", exc_info=True)
    
    finally:
        # Cleanup
        if tunnel_listener:
            try:
                tunnel_listener.close()
                await aprint(Fore.YELLOW + "Closed SSH tunnel")
            except Exception as e:
                logger.error(f"Error closing tunnel: {e}")