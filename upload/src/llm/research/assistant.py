# ============================================================================
# src/amp_llm/llm/research/assistant.py
# ============================================================================
"""
Main research assistant orchestrator.
"""
from pathlib import Path
from typing import Optional
from colorama import Fore

from amp_llm.config.settings import get_logger
from amp_llm.data.clinical_trials.rag import ClinicalTrialRAG
from amp_llm.llm.utils.session import OllamaSessionManager
from .commands import CommandHandler

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

logger = get_logger(__name__)


class ClinicalTrialResearchAssistant:
    """RAG-powered clinical trial research assistant."""
    
    def __init__(self, database_path: Path):
        """
        Initialize research assistant.
        
        Args:
            database_path: Path to clinical trial database
        """
        self.rag = ClinicalTrialRAG(database_path)
        self.rag.db.build_index()
        
        self.model_name = "ct-research-assistant"
        self.session_manager: Optional[OllamaSessionManager] = None
        self.command_handler: Optional[CommandHandler] = None
        
        logger.info(f"Initialized with {len(self.rag.db.trials)} trials")
    
    async def extract_from_nct(self, nct_id: str) -> str:
        """
        Extract structured data from trial.
        
        Args:
            nct_id: NCT number
            
        Returns:
            Formatted extraction text
        """
        extraction = self.rag.db.extract_structured_data(nct_id)
        
        if not extraction:
            return f"NCT number {nct_id} not found in database."
        
        context = extraction.to_formatted_string()
        
        prompt = f"""Extract structured clinical trial data from the information below.

Trial Data:
{context}

Provide a complete extraction following your format."""
        
        try:
            response = await self.session_manager.send_prompt(
                self.model_name,
                prompt
            )
            
            if not response or len(response.strip()) < 50:
                return f"Could not extract data for {nct_id}."
            
            return response
            
        except Exception as e:
            logger.error(f"Extraction error for {nct_id}: {e}")
            return f"Error: {e}"
    
    async def query_with_rag(
        self,
        query: str,
        max_trials: int = 10
    ) -> str:
        """
        Answer query using RAG.
        
        Args:
            query: User question
            max_trials: Max trials to include in context
            
        Returns:
            Answer
        """
        context = self.rag.get_context_for_llm(query, max_trials=max_trials)
        
        prompt = f"""Answer the following question using the clinical trial data provided.

Question: {query}

{context}

Provide a clear, structured answer based on the data above."""
        
        try:
            response = await self.session_manager.send_prompt(
                self.model_name,
                prompt
            )
            
            if not response:
                return "Error: No response from LLM"
            
            return response
            
        except Exception as e:
            logger.error(f"Query error: {e}")
            return f"Error: {e}"
    
    async def run(self, ssh_connection, host: str):
        """
        Run research assistant interactive session.
        
        Args:
            ssh_connection: SSH connection for model building
            host: Ollama API host
        """
        await aprint(Fore.CYAN + "\n=== 🔬 Research Assistant ===")
        await aprint(Fore.GREEN + f"✅ {len(self.rag.db.trials)} trials indexed")
        
        # Initialize session manager
        await aprint(Fore.CYAN + "🔌 Connecting to Ollama...")
        self.session_manager = OllamaSessionManager(host)
        await self.session_manager.start_session()
        await aprint(Fore.GREEN + "✅ Connected!")
        
        # Initialize command handler
        self.command_handler = CommandHandler(self)
        
        # Show help
        await self.command_handler.cmd_help()
        
        # Main loop
        try:
            while True:
                try:
                    user_input = await ainput(
                        Fore.GREEN + "Research >>> " + Fore.WHITE
                    )
                    
                    should_continue = await self.command_handler.handle_command(
                        user_input
                    )
                    
                    if not should_continue:
                        break
                
                except KeyboardInterrupt:
                    await aprint(Fore.YELLOW + "\nInterrupted. Type 'exit' to quit.")
                    continue
                except Exception as e:
                    await aprint(Fore.RED + f"Error: {e}")
                    logger.error(f"Loop error: {e}", exc_info=True)
        
        finally:
            # Cleanup
            await aprint(Fore.YELLOW + "\n🔌 Closing connection...")
            if self.session_manager:
                await self.session_manager.close_session()
            await aprint(Fore.GREEN + "✅ Goodbye!")