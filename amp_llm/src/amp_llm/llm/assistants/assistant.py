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
    from amp_llm.llm.assistants.commands import CommandHandler
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
        
        self.model_name = "ct-research-assistant:latest"  # Custom model name
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
        Shows base model information when custom model is found.
        
        Args:
            ssh_connection: SSH connection
            available_models: List of available models
            
        Returns:
            True if model ready
        """
        model_variants = [
            self.model_name,
            f"{self.model_name}:latest"
        ]
        
        # Check if custom model exists
        model_found = any(variant in available_models for variant in model_variants)
        
        if model_found:
            await aprint(Fore.GREEN + f"✅ Found existing model: {self.model_name}")
            
            # Get model information to show base model
            model_info = await self._get_model_info(ssh_connection, self.model_name)
            
            if model_info:
                await aprint(Fore.CYAN + f"   Built from: {model_info['base_model']}")
                await aprint(Fore.CYAN + f"   Size: {model_info['size']}")
                
                if model_info.get('modified'):
                    await aprint(Fore.CYAN + f"   Modified: {model_info['modified']}")
            
            # Ask if user wants to use it or rebuild
            use_existing = await ainput(
                Fore.CYAN + 
                f"\nUse existing '{self.model_name}'? (y=use / n=rebuild / s=skip and select base model) [y]: "
            )
            
            choice = use_existing.strip().lower()
            
            if choice in ('', 'y', 'yes'):
                # Use existing model
                logger.info(f"Using existing model: {self.model_name}")
                return True
            
            elif choice in ('s', 'skip'):
                # Skip to base model selection
                await aprint(Fore.YELLOW + "Skipping custom model, will select base model instead")
                return False
            
            elif choice in ('n', 'no'):
                # Rebuild the model
                await aprint(Fore.YELLOW + f"\n🔄 Rebuilding '{self.model_name}'...")
                
                # Continue to model creation below
                pass
            else:
                # Invalid input, default to using existing
                await aprint(Fore.YELLOW + "Invalid input, using existing model")
                return True
        
        # Model doesn't exist or user wants to rebuild
        if not model_found:
            await aprint(Fore.YELLOW + f"\n🔧 Custom model '{self.model_name}' not found")
        
        await aprint(Fore.CYAN + "Select a base model to create the custom model")
        
        # Show available base models for selection
        await aprint(Fore.CYAN + f"\n📋 Available base models:")
        for i, model in enumerate(available_models, 1):
            marker = "→" if model == available_models[0] else " "
            await aprint(Fore.WHITE + f"  {marker} {i}) {model}")
        
        choice = await ainput(Fore.GREEN + "Select base model by number or name [1]: ")
        choice = choice.strip()
        
        # Parse choice
        base_model = None
        if not choice:
            base_model = available_models[0]
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(available_models):
                base_model = available_models[idx]
            else:
                await aprint(Fore.YELLOW + "Invalid selection, using first model")
                base_model = available_models[0]
        elif choice in available_models:
            base_model = choice
        else:
            # Try to find partial match
            matches = [m for m in available_models if choice.lower() in m.lower()]
            if matches:
                base_model = matches[0]
                await aprint(Fore.CYAN + f"Using closest match: {base_model}")
            else:
                await aprint(Fore.YELLOW + f"Model '{choice}' not found, using first model")
                base_model = available_models[0]
        
        await aprint(Fore.CYAN + f"\n🔨 Building '{self.model_name}' from '{base_model}'...")
        
        # Model creation using model_builder
        from amp_llm.llm.models.builder import build_custom_model
        
        success = await build_custom_model(
            ssh_connection,
            self.model_name,
            available_models,
            selected_base_model=base_model
        )
        
        if success:
            await aprint(Fore.GREEN + f"✅ Model '{self.model_name}' created successfully!")
            return True
        else:
            await aprint(Fore.RED + f"❌ Failed to create '{self.model_name}'")
            return False
        
async def _get_model_info(self, ssh_connection, model_name: str) -> dict:
    """
    Get information about a model from Ollama.
    
    Args:
        ssh_connection: SSH connection
        model_name: Name of model to inspect
        
    Returns:
        Dictionary with model info or None if error
    """
    try:
        # Run ollama show command to get model info
        result = await ssh_connection.run(
            f'bash -l -c "ollama show {model_name} --modelfile"',
            check=False
        )
        
        if result.exit_status == 0 and result.stdout:
            modelfile = result.stdout
            
            # Parse the FROM line to get base model
            base_model = "unknown"
            for line in modelfile.split('\n'):
                if line.strip().startswith('FROM'):
                    base_model = line.split('FROM', 1)[1].strip()
                    break
            
            # Get model size
            result_list = await ssh_connection.run(
                f'bash -l -c "ollama list | grep {model_name}"',
                check=False
            )
            
            size = "unknown"
            modified = None
            
            if result_list.exit_status == 0 and result_list.stdout:
                # Parse output: NAME    SIZE    MODIFIED
                parts = result_list.stdout.split()
                if len(parts) >= 3:
                    size = parts[1]
                    # Modified time is the rest
                    if len(parts) >= 4:
                        modified = ' '.join(parts[2:])
            
            return {
                'base_model': base_model,
                'size': size,
                'modified': modified
            }
        
        else:
            logger.warning(f"Could not get info for {model_name}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting model info: {e}", exc_info=True)
        return None