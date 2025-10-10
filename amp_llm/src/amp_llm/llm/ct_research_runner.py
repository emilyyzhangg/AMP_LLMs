"""
Clinical Trial Research Assistant - Enhanced with Auto-Tunneling
Version: 3.1 - Automatic SSH Tunnel Management

UPDATED: Simplified connection management with automatic tunneling.

Changes from original:
- Added ssh_connection parameter to list_remote_models_api
- Added ssh_connection parameter to OllamaSessionManager
- Removed manual tunnel creation code
- Removed manual tunnel cleanup code
- Simplified connection flow (~25 lines removed)
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional
from colorama import Fore, Style
from config import get_logger, get_config
from data.clinical_trial_rag import ClinicalTrialRAG
from llm.session_manager import OllamaSessionManager
from llm.command_handler import CommandHandler

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
    """
    Enhanced LLM runner with RAG integration and automatic tunneling.
    
    This class delegates to:
    - Session management → OllamaSessionManager (with auto-tunneling)
    - Command handling → CommandHandler
    - Response parsing → response_parser module
    - Validation → validation_config module
    """
    
    def __init__(self, database_path: Path):
        """Initialize research assistant."""
        self.rag = ClinicalTrialRAG(database_path)
        self.rag.db.build_index()
        self.model_name = "ct-research-assistant"
        self.session_manager: Optional[OllamaSessionManager] = None
        self.command_handler: Optional[CommandHandler] = None
    
    async def extract_from_nct(self, nct_id: str) -> str:
        """
        Extract structured data from specific NCT trial.
        
        Args:
            nct_id: NCT number
            
        Returns:
            Formatted extraction text
        """
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
        """
        Answer query using RAG system.
        
        Args:
            query: User question
            max_trials: Maximum number of trials to include
            
        Returns:
            LLM answer
        """
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
    
    async def ensure_model_exists(self, ssh, models: list) -> bool:
        """
        Check if custom model exists, create if not.
        
        Args:
            ssh: SSH connection
            models: List of available models
            
        Returns:
            True if model ready, False otherwise
        """
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
        
        # Model creation using model_builder
        from llm.model_builder import ensure_model_exists as build_model
        return await build_model(ssh, self.model_name, models)


async def run_ct_research_assistant(ssh):
    """
    Main research assistant workflow.
    
    UPDATED: Now uses automatic SSH tunneling - much simpler!
    
    Args:
        ssh: SSH connection
    """
    # Suppress asyncssh logging
    asyncssh_logger = logging.getLogger('asyncssh')
    asyncssh_logger.setLevel(logging.WARNING)
    
    await aprint(Fore.CYAN + Style.BRIGHT + "\n=== 🔬 Clinical Trial Research Assistant ===")
    await aprint(Fore.WHITE + "RAG-powered intelligent analysis of clinical trial database\n")
    
    # Setup database
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
    
    # Setup Ollama connection
    try:
        host = ssh._host if hasattr(ssh, '_host') else config.network.default_ip
    except:
        host = config.network.default_ip
    
    await aprint(Fore.CYAN + f"\n🔗 Connecting to Ollama at {host}:11434...")
    
    from llm.async_llm_utils import list_remote_models_api
    
    # ============================================================================
    # CHANGE #1: Added ssh_connection=ssh parameter
    # This automatically handles tunneling if direct connection fails!
    # All the manual tunnel code below is removed.
    # ============================================================================
    models = await list_remote_models_api(host, ssh_connection=ssh)
    
    if not models:
        await aprint(Fore.RED + "❌ Cannot connect to Ollama on remote server")
        return
    
    await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s) on remote server")
    
    # Ensure model exists
    model_ready = await assistant.ensure_model_exists(ssh, models)
    
    if not model_ready:
        # Fallback to base model selection
        await aprint(Fore.YELLOW + "\n⚠️  Custom model not available. Choose a base model instead:")
        models = await list_remote_models_api(host, ssh_connection=ssh)
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
    
    # ============================================================================
    # CHANGE #2: Added ssh_connection=ssh parameter to OllamaSessionManager
    # The session manager now handles tunnel creation/cleanup automatically!
    # All the manual tunnel_listener code is removed.
    # ============================================================================
    await aprint(Fore.CYAN + "🔌 Starting persistent connection...")
    assistant.session_manager = OllamaSessionManager(
        host=host,
        ssh_connection=ssh  # <-- ADDED THIS PARAMETER
    )
    await assistant.session_manager.start_session()
    # ^ This will automatically create tunnel if direct connection fails!
    
    await aprint(Fore.GREEN + "✅ Persistent connection established!")
    
    # Initialize command handler
    assistant.command_handler = CommandHandler(assistant)
    
    # Show initial help
    await assistant.command_handler.cmd_help()
    
    # Main command loop
    try:
        while True:
            try:
                user_input = await ainput(Fore.GREEN + "Research >>> " + Fore.WHITE)
                
                # Handle command
                should_continue = await assistant.command_handler.handle_command(user_input)
                
                if not should_continue:
                    break
                    
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to quit.")
                continue
            except Exception as e:
                await aprint(Fore.RED + f"Error: {e}")
                logger.error(f"Error in research assistant: {e}", exc_info=True)
    
    # ============================================================================
    # CHANGE #3: Removed manual tunnel cleanup
    # The session manager's close_session() now handles tunnel cleanup!
    # ============================================================================
    finally:
        # CLOSE PERSISTENT SESSION
        await aprint(Fore.YELLOW + "\n🔌 Closing persistent connection...")
        if assistant.session_manager:
            await assistant.session_manager.close_session()
            # ^ This now automatically closes the tunnel if one was created!
        
        await aprint(Fore.GREEN + "✅ Research assistant closed cleanly")


# Backward compatibility alias
async def run_ct_research_assistant_v2(ssh):
    """Alias for backward compatibility."""
    await run_ct_research_assistant(ssh)