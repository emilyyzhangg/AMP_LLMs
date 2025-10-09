"""
Clinical Trial Research Assistant LLM Runner
WITH PERSISTENT CONNECTION - Maintains single aiohttp session throughout entire session

Version: 2.2 - Persistent Connection
"""
import asyncio
import aiohttp
import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from colorama import Fore, Style
from config import get_logger, get_config
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
# PERSISTENT SESSION MANAGER
# ==============================================================================

class OllamaSessionManager:
    """
    Manages persistent aiohttp session for Ollama API calls.
    Keeps connection alive throughout research session.
    """
    
    def __init__(self, host: str, port: int = 11434):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.connector: Optional[aiohttp.TCPConnector] = None
    
    async def __aenter__(self):
        """Start persistent session."""
        await self.start_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close session on exit."""
        await self.close_session()
    
    async def start_session(self):
        """Initialize persistent session with keepalive."""
        if self.session and not self.session.closed:
            return  # Already started
        
        # Create connector with keepalive settings
        self.connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            limit=100,
            force_close=False,  # CRITICAL: Keep connections alive
            enable_cleanup_closed=True,
            keepalive_timeout=300  # 5 minutes keepalive
        )
        
        # Create session
        self.session = aiohttp.ClientSession(connector=self.connector)
        
        logger.info(f"Started persistent Ollama session: {self.base_url}")
    
    async def close_session(self):
        """Close persistent session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Closed persistent Ollama session")
    
    async def is_alive(self) -> bool:
        """Check if session is alive."""
        if not self.session or self.session.closed:
            return False
        
        try:
            # Quick health check
            async with self.session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
        except:
            return False
    
    async def send_prompt(
        self, 
        model: str, 
        prompt: str, 
        max_retries: int = 3
    ) -> str:
        """
        Send prompt using persistent session.
        Automatically reconnects if needed.
        """
        if not self.session or self.session.closed:
            await self.start_session()
        
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
            }
        }
        
        logger.info(f"Sending {len(prompt)} characters to {model}")
        print(f"📤 Sending prompt to Ollama...")
        print(f"   Length: {len(prompt)} chars")
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Longer timeout for LLM responses (5 minutes)
                timeout = aiohttp.ClientTimeout(
                    total=300,  # 5 minutes total
                    connect=30,  # 30 seconds to connect
                    sock_read=300  # 5 minutes to read response
                )
                
                async with self.session.post(url, json=payload, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response = data.get('response', '')
                        
                        logger.info(f"Received response: {len(response)} characters")
                        print(f"✅ Received response: {len(response)} chars")
                        
                        return response
                    else:
                        error_text = await resp.text()
                        logger.error(f"API error {resp.status}: {error_text}")
                        return f"Error: API returned status {resp.status}"
                        
            except asyncio.TimeoutError:
                last_error = "Request timed out after 5 minutes"
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Timeout")
                if attempt < max_retries - 1:
                    print(f"⚠️  Timeout, retrying... ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(2)
                    continue
                else:
                    logger.error(last_error)
                    return f"Error: {last_error}"
                    
            except aiohttp.ServerDisconnectedError:
                last_error = "Server disconnected"
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Server disconnected")
                
                # Try to restart session
                if attempt < max_retries - 1:
                    print(f"⚠️  Connection lost, reconnecting... ({attempt + 1}/{max_retries})")
                    await self.close_session()
                    await asyncio.sleep(2)
                    await self.start_session()
                    continue
                else:
                    logger.error(last_error)
                    return f"Error: {last_error}. Please check if Ollama is still running."
                    
            except aiohttp.ClientConnectorError:
                last_error = f"Cannot connect to Ollama at {self.host}:{self.port}"
                logger.error(last_error)
                
                # Try to restart session
                if attempt < max_retries - 1:
                    print(f"⚠️  Connection error, reconnecting... ({attempt + 1}/{max_retries})")
                    await self.close_session()
                    await asyncio.sleep(2)
                    await self.start_session()
                    continue
                else:
                    return f"Error: {last_error}. Check if SSH tunnel is still active."
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error sending prompt: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    print(f"⚠️  Error occurred, retrying... ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(2)
                    continue
                else:
                    return f"Error: {e}"
        
        return f"Error: {last_error}"


# ==============================================================================
# HELPER FUNCTION: Parse LLM response to dictionary
# ==============================================================================

def parse_extraction_to_dict(llm_response: str) -> dict:
    """Parse LLM extraction response into structured dictionary."""
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
            value = value.strip('`').strip()
            
            # Filter placeholder text
            placeholder_patterns = [
                r'^\[.*\]$',
                r'NCT########',
                r'\[value from list\]',
                r'\[YYYY-MM-DD\]',
            ]
            
            is_placeholder = any(re.match(p, value) for p in placeholder_patterns)
            
            if is_placeholder:
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
                if value and value.lower() != 'n/a':
                    items = [item.strip() for item in value.split(',')]
                    items = [item for item in items if item and item != 'N/A' and 
                            not item.startswith('[') and not item.endswith('...]')]
                    result[field] = items
                else:
                    result[field] = []
            elif field in ('classification_evidence', 'dramp_evidence', 'subsequent_evidence'):
                if value and value.lower() != 'n/a' and not value.startswith('['):
                    if ',' in value:
                        result[field] = [item.strip() for item in value.split(',')]
                    else:
                        result[field] = [value] if value else []
                else:
                    result[field] = []
            else:
                if value.lower() == 'n/a' or value.startswith('['):
                    result[field] = ""
                else:
                    result[field] = value
    
    return result


# ==============================================================================
# MAIN CLASS (Updated to use persistent session)
# ==============================================================================

class ClinicalTrialResearchAssistant:
    """Enhanced LLM runner with RAG integration and persistent connection."""
    
    def __init__(self, database_path: Path):
        """Initialize research assistant."""
        self.rag = ClinicalTrialRAG(database_path)
        self.rag.db.build_index()
        self.model_name = "ct-research-assistant"
        self.session_manager: Optional[OllamaSessionManager] = None
    
    async def extract_from_nct(self, nct_id: str) -> str:
        """Extract structured data from specific NCT trial."""
        extraction = self.rag.db.extract_structured_data(nct_id)
        
        if not extraction:
            return f"NCT number {nct_id} not found in database."
        
        context = extraction.to_formatted_string()
        
        prompt = f"""You are extracting structured clinical trial data. Use the information below to fill in the extraction format.

CRITICAL RULES:
1. Use ACTUAL values from the data below, NOT placeholders
2. For missing data, write exactly: N/A
3. Use EXACT values from validation lists
4. Do NOT wrap response in code blocks

Trial Data:
{context}

Now provide a complete extraction following the exact format specified in your system prompt."""

        try:
            response = await self.session_manager.send_prompt(self.model_name, prompt)
            
            if not response or len(response.strip()) < 50:
                return f"Could not extract data for {nct_id}. Response too short or empty."
            
            return response
            
        except Exception as e:
            logger.error(f"Error extracting {nct_id}: {e}", exc_info=True)
            return f"Error: {e}"
    
    async def query_with_rag(self, query: str, max_trials: int = 10) -> str:
        """Answer query using RAG system with custom trial limit."""
        context = self.rag.get_context_for_llm(query, max_trials=max_trials)
        
        prompt = f"""You are a clinical trial research assistant. Use the trial data below to answer the question.

Question: {query}

{context}

Provide a clear, well-structured answer based on the trial data above."""

        try:
            response = await self.session_manager.send_prompt(self.model_name, prompt)
            
            if not response:
                return "Error: No response from LLM"
            
            return response
            
        except Exception as e:
            logger.error(f"Error in query: {e}", exc_info=True)
            return f"Error: {e}"
    
    async def ensure_model_exists(self, ssh, models: List[str]) -> bool:
        """Check if custom model exists, create if not."""
        if self.model_name in models:
            await aprint(Fore.GREEN + f"✅ Using existing model: {self.model_name}")
            logger.info(f"Found existing model: {self.model_name}")
            return True
        
        await aprint(Fore.YELLOW + f"\n🔧 Custom model '{self.model_name}' not found")
        await aprint(Fore.CYAN + "This is a one-time setup to create a specialized model.")
        
        create = await ainput(Fore.GREEN + f"Create '{self.model_name}' now? (y/n) [y]: ")
            
        if create.strip().lower() in ('n', 'no'):
            await aprint(Fore.YELLOW + "Skipped. You can use a base model instead.")
            return False
            
        await aprint(Fore.CYAN + f"\n📋 Available base models:")
        for i, model in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}) {model}")
            
        choice = await ainput(Fore.GREEN + f"Select base model [1]: ")
        
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
                return False
            
            await aprint(Fore.GREEN + f"✅ Found Modelfile at: {modelfile_path}")
            
            with open(modelfile_path, 'r', encoding='utf-8') as f:
                modelfile_content = f.read()
            
            modelfile_content = re.sub(
                r'^FROM\s+\S+',
                f'FROM {base_model}',
                modelfile_content,
                flags=re.MULTILINE
            )
            
            await aprint(Fore.CYAN + f"📤 Uploading Modelfile to remote server...")
            
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
            
            await aprint(Fore.CYAN + f"🔨 Building model (this may take 1-2 minutes)...")
            
            try:
                result = await ssh.run(
                    f'bash -l -c "ollama create {self.model_name} -f {temp_modelfile}"',
                    check=False
                )
                
                await ssh.run(f'rm -f {temp_modelfile}', check=False)
                
                if result.exit_status == 0:
                    await aprint(Fore.GREEN + f"\n✅ Success! Model '{self.model_name}' created!")
                    logger.info(f"Created model {self.model_name} from {base_model}")
                    return True
                else:
                    await aprint(Fore.RED + f"\n❌ Model creation failed!")
                    if result.stderr:
                        await aprint(Fore.RED + f"Error: {result.stderr}")
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
# MAIN WORKFLOW (Updated with persistent session)
# ==============================================================================

async def run_ct_research_assistant(ssh):
    """Main research assistant workflow with persistent connection."""
    # Suppress asyncssh logging
    asyncssh_logger = logging.getLogger('asyncssh')
    asyncssh_logger.setLevel(logging.WARNING)
    
    await aprint(Fore.CYAN + Style.BRIGHT + "\n=== 🔬 Clinical Trial Research Assistant ===")
    await aprint(Fore.WHITE + "RAG-powered intelligent analysis of clinical trial database\n")
    
    db_path_input = await ainput(
        Fore.CYAN + "Enter path to clinical trial database (JSON file or directory) [./ct_database]: "
    )
    db_path = Path(db_path_input.strip() or "./ct_database")
    
    if not db_path.exists():
        await aprint(Fore.RED + f"❌ Database path not found: {db_path}")
        return
    
    await aprint(Fore.YELLOW + "Initializing research assistant...")
    assistant = ClinicalTrialResearchAssistant(db_path)
    
    await aprint(Fore.GREEN + f"✅ Indexed {len(assistant.rag.db.trials)} clinical trials")
    
    try:
        host = ssh._host if hasattr(ssh, '_host') else config.network.default_ip
    except:
        host = config.network.default_ip
    
    # Setup Ollama connection
    await aprint(Fore.CYAN + f"\n🔗 Connecting to Ollama at {host}:11434...")
    
    # Import the list_remote_models_api function
    from llm.async_llm_utils import list_remote_models_api
    
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
        return
    
    await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s) on remote server")
    
    model_ready = await assistant.ensure_model_exists(ssh, models)
    
    if not model_ready:
        await aprint(Fore.YELLOW + "\n⚠️  Custom model not available. Choose a base model instead:")
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
    
    # START PERSISTENT SESSION
    await aprint(Fore.CYAN + "🔌 Starting persistent connection...")
    assistant.session_manager = OllamaSessionManager(host)
    await assistant.session_manager.start_session()
    await aprint(Fore.GREEN + "✅ Persistent connection established!")
    
    await aprint(Fore.CYAN + "\n💡 Research Assistant Commands:")
    await aprint(Fore.CYAN + "   • 'search <query>' - Search database and analyze trials")
    await aprint(Fore.CYAN + "   • 'extract <NCT>' - Extract structured data from specific trial")
    await aprint(Fore.CYAN + "   • 'save <NCT>' - Extract and save directly as JSON")
    await aprint(Fore.CYAN + "   • 'query <question> [--limit N]' - Ask question (default limit: 10)")
    await aprint(Fore.CYAN + "   • 'stats' - Show database statistics")
    await aprint(Fore.CYAN + "   • 'validate' - Show valid values for all fields")
    await aprint(Fore.CYAN + "   • 'status' - Check connection status")
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
                
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                # STATUS command - check connection health
                if command == 'status':
                    is_alive = await assistant.session_manager.is_alive()
                    if is_alive:
                        await aprint(Fore.GREEN + "✅ Connection is healthy")
                    else:
                        await aprint(Fore.RED + "❌ Connection is down")
                        await aprint(Fore.YELLOW + "Attempting to reconnect...")
                        await assistant.session_manager.start_session()
                        is_alive = await assistant.session_manager.is_alive()
                        if is_alive:
                            await aprint(Fore.GREEN + "✅ Reconnected successfully")
                        else:
                            await aprint(Fore.RED + "❌ Reconnection failed")
                    continue
                
                # SEARCH command
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
                    
                    analyze = await ainput(Fore.CYAN + "\nAnalyze these trials with AI? (y/n): ")
                    
                    if analyze.lower() in ('y', 'yes'):
                        await aprint(Fore.YELLOW + "\n🤔 Analyzing trials...")
                        response = await assistant.query_with_rag(args)
                        
                        if not response or response.startswith("Error:"):
                            await aprint(Fore.RED + f"\n{response}\n")
                        else:
                            await aprint(Fore.GREEN + "\n📊 Analysis:\n")
                            await aprint(Fore.WHITE + response + "\n")
                
                # EXTRACT command
                elif command == 'extract':
                    if not args:
                        await aprint(Fore.RED + "Usage: extract <NCT_NUMBER>")
                        continue
                    
                    nct = args.upper().strip()
                    await aprint(Fore.YELLOW + f"\n📋 Extracting data for {nct}...")
                    
                    response = await assistant.extract_from_nct(nct)
                    
                    if not response or response.startswith("Error:") or response.startswith("NCT number") or response.startswith("Could not"):
                        await aprint(Fore.RED + f"\n{response}\n")
                    else:
                        await aprint(Fore.GREEN + "\n📊 Structured Extraction:")
                        await aprint(Fore.WHITE + response)
                        
                        save_choice = await ainput(Fore.CYAN + "\nSave this extraction? (json/txt/no) [no]: ")
                        save_choice = save_choice.strip().lower()
                        
                        if save_choice in ('json', 'txt'):
                            default_filename = f"{nct}_extraction"
                            filename = await ainput(Fore.CYAN + f"Filename (without extension) [{default_filename}]: ")
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
                                else:
                                    with open(output_path, 'w', encoding='utf-8') as f:
                                        f.write(response)
                                    
                                    await aprint(Fore.GREEN + f"✅ Saved as text: {output_path}")
                                
                                logger.info(f"Saved extraction to {output_path}")
                                
                            except Exception as e:
                                await aprint(Fore.RED + f"❌ Error saving: {e}")
                                logger.error(f"Error saving extraction: {e}", exc_info=True)
                
                # SAVE command
                elif command == 'save':
                    if not args:
                        await aprint(Fore.RED + "Usage: save <NCT_NUMBER>")
                        continue
                    
                    nct = args.upper().strip()
                    await aprint(Fore.YELLOW + f"\n💾 Extracting and saving {nct}...")
                    
                    response = await assistant.extract_from_nct(nct)
                    
                    if not response or response.startswith("Error:"):
                        await aprint(Fore.RED + f"\n{response}\n")
                        continue
                    
                    try:
                        extraction_dict = parse_extraction_to_dict(response)
                        
                        default_filename = f"{nct}_extraction"
                        filename = await ainput(Fore.CYAN + f"Filename [{default_filename}]: ")
                        filename = filename.strip() or default_filename
                        
                        output_dir = Path('output')
                        output_dir.mkdir(exist_ok=True)
                        output_path = output_dir / f"{filename}.json"
                        
                        with open(output_path, 'w', encoding='utf-8') as f:
                            json.dump(extraction_dict, f, indent=2, ensure_ascii=False)
                        
                        await aprint(Fore.GREEN + f"\n✅ Saved to: {output_path}")
                        
                    except Exception as e:
                        await aprint(Fore.RED + f"❌ Error: {e}")
                
                # QUERY command
                elif command == 'query':
                    if not args:
                        await aprint(Fore.RED + "Usage: query <question> [--limit N]")
                        continue
                    
                    max_trials = 10
                    query_text = args
                    
                    if '--limit' in args:
                        parts = args.split('--limit')
                        query_text = parts[0].strip()
                        try:
                            limit_str = parts[1].strip().split()[0]
                            max_trials = int(limit_str)
                        except (ValueError, IndexError):
                            await aprint(Fore.YELLOW + "Invalid --limit value, using default (10)")
                    
                    await aprint(Fore.YELLOW + f"\n🤔 Processing query (max {max_trials} trials)...")
                    response = await assistant.query_with_rag(query_text, max_trials=max_trials)
                    
                    if not response or response.startswith("Error:"):
                        await aprint(Fore.RED + f"\n{response}\n")
                    else:
                        await aprint(Fore.GREEN + "\n💡 Answer:\n")
                        await aprint(Fore.WHITE + response + "\n")
                
                # STATS command
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
                
                # VALIDATE command
                elif command == 'validate':
                    await aprint(Fore.CYAN + "\n📋 Valid Values for All Fields:\n")
                    
                    await aprint(Fore.GREEN + "Study Status:")
                    for status in ["NOT_YET_RECRUITING", "RECRUITING", "ENROLLING_BY_INVITATION",
                                  "ACTIVE_NOT_RECRUITING", "COMPLETED", "SUSPENDED",
                                  "TERMINATED", "WITHDRAWN", "UNKNOWN"]:
                        await aprint(Fore.WHITE + f"  • {status}")
                    
                    await aprint(Fore.GREEN + "\nPhases:")
                    for phase in ["EARLY_PHASE1", "PHASE1", "PHASE1|PHASE2",
                                 "PHASE2", "PHASE2|PHASE3", "PHASE3", "PHASE4"]:
                        await aprint(Fore.WHITE + f"  • {phase}")
                    
                    await aprint(Fore.GREEN + "\nClassification:")
                    for cls in ["AMP(infection)", "AMP(other)", "Other"]:
                        await aprint(Fore.WHITE + f"  • {cls}")
                    
                    await aprint(Fore.GREEN + "\nOutcome:")
                    for outcome in ["Positive", "Withdrawn", "Terminated",
                                   "Failed - completed trial", "Recruiting",
                                   "Unknown", "Active, not recruiting"]:
                        await aprint(Fore.WHITE + f"  • {outcome}")
                    
                    await aprint("")
                
                # DEFAULT: Treat as query
                else:
                    max_trials = 10
                    query_text = user_input
                    
                    if '--limit' in user_input:
                        parts = user_input.split('--limit')
                        query_text = parts[0].strip()
                        try:
                            limit_str = parts[1].strip().split()[0]
                            max_trials = int(limit_str)
                        except (ValueError, IndexError):
                            pass
                    
                    await aprint(Fore.YELLOW + f"\n🤔 Processing query (max {max_trials} trials)...")
                    response = await assistant.query_with_rag(query_text, max_trials=max_trials)
                    
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
    
    finally:
        # CLOSE PERSISTENT SESSION
        await aprint(Fore.YELLOW + "\n🔌 Closing persistent connection...")
        if assistant.session_manager:
            await assistant.session_manager.close_session()
        
        if tunnel_listener:
            try:
                tunnel_listener.close()
                await aprint(Fore.YELLOW + "Closed SSH tunnel")
            except Exception as e:
                logger.error(f"Error closing tunnel: {e}")
        
        await aprint(Fore.GREEN + "✅ Research assistant closed cleanly")