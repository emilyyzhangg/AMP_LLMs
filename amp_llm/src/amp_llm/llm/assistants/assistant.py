# amp_llm/src/amp_llm/llm/research/assistant.py
"""
Clinical Trial Research Assistant with RAG and command handling.
Combines model building, RAG, and interactive commands.
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional
from colorama import Fore, Style

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.config import get_logger, get_config
from amp_llm.llm.session_manager import OllamaSessionManager

# Will import these if they exist
try:
    from amp_llm.data.clinical_trial_rag import ClinicalTrialRAG
    HAS_RAG = True
except ImportError:
    HAS_RAG = False
    
try:
    from amp_llm.llm.research.commands import CommandHandler
    HAS_COMMANDS = True
except ImportError:
    HAS_COMMANDS = False

logger = get_logger(__name__)
config = get_config()


class ClinicalTrialResearchAssistant:
    """
    Research Assistant with RAG integration and command handling.
    
    Features:
    - Automatic model building from Modelfile
    - RAG-powered context retrieval
    - Interactive command system
    - Structured data extraction
    """
    
    def __init__(self, database_path: Path):
        """
        Initialize research assistant.
        
        Args:
            database_path: Path to JSON database
        """
        if not HAS_RAG:
            raise ImportError(
                "RAG system not available. "
                "Make sure amp_llm.data.clinical_trial_rag exists."
            )
        
        self.rag = ClinicalTrialRAG(database_path)
        self.rag.db.build_index()
        
        self.model_name = "ct-research-assistant"  # Custom model name
        self.session_manager: Optional[OllamaSessionManager] = None
        self.command_handler: Optional[CommandHandler] = None
    
    async def run(self, ssh_connection, remote_host: str):
        """
        Main entry point for research assistant.
        
        Args:
            ssh_connection: SSH connection
            remote_host: Remote host IP
        """
        await aprint(Fore.CYAN + Style.BRIGHT + "\n=== 🔬 Clinical Trial Research Assistant ===")
        await aprint(Fore.WHITE + "RAG-powered intelligent analysis of clinical trial database\n")
        
        await aprint(Fore.GREEN + f"✅ Indexed {len(self.rag.db.trials)} clinical trials")
        
        # Setup Ollama connection with automatic tunneling
        await aprint(Fore.CYAN + f"\n🔗 Connecting to Ollama at {remote_host}:11434...")
        
        try:
            async with OllamaSessionManager(remote_host, 11434, ssh_connection) as session:
                self.session_manager = session
                
                await aprint(Fore.GREEN + "✅ Connected to Ollama!")
                if session._using_tunnel:
                    await aprint(Fore.CYAN + "   (via SSH tunnel)")
                
                # List models
                models = await session.list_models()
                
                if not models:
                    await self._show_no_models_help()
                    return
                
                await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s)")
                
                # Ensure custom model exists
                model_ready = await self._ensure_model_exists(ssh_connection, models)
                
                if not model_ready:
                    # Fallback to base model selection
                    await aprint(Fore.YELLOW + "\n⚠️  Custom model not available")
                    await aprint(Fore.CYAN + "Select a base model instead:")
                    
                    for i, model in enumerate(models, 1):
                        await aprint(Fore.WHITE + f"  {i}. {model}")
                    
                    choice = await ainput(Fore.GREEN + "Select model [1]: ")
                    choice = choice.strip()
                    
                    if choice.isdigit() and 0 < int(choice) <= len(models):
                        self.model_name = models[int(choice) - 1]
                    elif choice in models:
                        self.model_name = choice
                    else:
                        self.model_name = models[0]
                    
                    await aprint(Fore.YELLOW + f"Using: {self.model_name}")
                
                await aprint(Fore.GREEN + f"\n✅ Using model: {self.model_name}")
                
                # Initialize command handler
                if HAS_COMMANDS:
                    self.command_handler = CommandHandler(self)
                    await self.command_handler.cmd_help()
                else:
                    await aprint(Fore.YELLOW + "⚠️  Command handler not available")
                    await aprint(Fore.YELLOW + "Using basic Q&A mode")
                
                # Main interaction loop
                await self._interaction_loop()
                
        except ConnectionError as e:
            await aprint(Fore.RED + f"❌ Connection failed: {e}")
            logger.error(f"Connection error: {e}")
        except Exception as e:
            await aprint(Fore.RED + f"❌ Error: {e}")
            logger.error(f"Research assistant error: {e}", exc_info=True)
    
    async def _interaction_loop(self):
        """Main interaction loop with command handling."""
        while True:
            try:
                user_input = await ainput(Fore.GREEN + "\nResearch >>> " + Style.RESET_ALL)
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                # Handle commands if available
                if HAS_COMMANDS and self.command_handler:
                    should_continue = await self.command_handler.handle_command(user_input)
                    if not should_continue:
                        break
                else:
                    # Basic Q&A mode
                    if user_input.lower() in ('exit', 'quit', 'main menu'):
                        await aprint(Fore.YELLOW + "Returning to main menu...")
                        break
                    
                    # Simple query
                    await aprint(Fore.YELLOW + "\n🤔 Processing query...")
                    response = await self.query_with_rag(user_input)
                    
                    await aprint(Fore.CYAN + "\n📝 Response:")
                    await aprint(Fore.WHITE + response)
                    
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to quit.")
                continue
            except Exception as e:
                await aprint(Fore.RED + f"\n❌ Error: {e}")
                logger.error(f"Interaction error: {e}", exc_info=True)
    
    async def _ensure_model_exists(self, ssh_connection, available_models: list) -> bool:
        """
        Check if custom model exists, create if not.
        
        Args:
            ssh_connection: SSH connection
            available_models: List of available models
            
        Returns:
            True if model ready
        """
        if self.model_name in available_models:
            await aprint(Fore.GREEN + f"✅ Found custom model: {self.model_name}")
            return True
        
        await aprint(Fore.YELLOW + f"\n🔧 Custom model '{self.model_name}' not found")
        await aprint(Fore.CYAN + "Would you like to create it with your Modelfile?")
        
        create = await ainput(Fore.GREEN + "Create custom model? (y/n) [y]: ")
        
        if create.strip().lower() in ('n', 'no'):
            await aprint(Fore.YELLOW + "Skipped. Will use base model instead.")
            return False
        
        # Import model builder
        try:
            from amp_llm.llm.models.builder import build_custom_model
        except ImportError:
            await aprint(Fore.RED + "❌ Model builder not available")
            await aprint(Fore.YELLOW + "Install model builder or use base model")
            return False
        
        # Build the model
        success = await build_custom_model(
            ssh_connection,
            self.model_name,
            available_models
        )
        
        if success:
            # Refresh model list
            models = await self.session_manager.list_models()
            return self.model_name in models
        
        return False
    
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
    
    async def _show_no_models_help(self):
        """Show help when no models found."""
        await aprint(Fore.RED + "❌ No models found on remote server")
        await aprint(Fore.YELLOW + "\nInstall models on remote server:")
        await aprint(Fore.WHITE + "  1. SSH to remote server")
        await aprint(Fore.WHITE + "  2. Run: ollama pull llama3.2")
        await aprint(Fore.WHITE + "  3. Verify: ollama list")