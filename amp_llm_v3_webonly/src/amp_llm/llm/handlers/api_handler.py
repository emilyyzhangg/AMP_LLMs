"""
LLM API Mode Handler (Option 2) - Main entry point.
Uses HTTP API for reliable communication.
"""
from colorama import Fore, Style

from amp_llm.cli.async_io import ainput, aprint
from amp_llm.config import get_logger
from amp_llm.llm.utils.session import OllamaSessionManager
from .menu import show_interactive_menu
from .helpers import select_or_create_model, show_no_models_help, show_connection_help
from .interactive import run_interactive_session

logger = get_logger(__name__)


async def run_llm_entrypoint_api(ssh_manager):
    """
    Enhanced LLM workflow with interactive menu options (API Mode).
    
    Features:
    - Paste mode for multi-line input
    - File loading from output/ directory
    - Custom model building
    - Automatic SSH tunneling
    
    Args:
        ssh_manager: SSHManager instance
    """
    await aprint(Fore.CYAN + "\n=== 🤖 LLM Workflow (API Mode) ===")
    await aprint(Fore.YELLOW + "Enhanced with file loading and interactive features\n")
    
    # Get remote host and SSH connection
    remote_host = ssh_manager.host if hasattr(ssh_manager, 'host') else 'localhost'
    ssh_connection = ssh_manager.connection if hasattr(ssh_manager, 'connection') else None
    
    await aprint(Fore.CYAN + f"Connecting to Ollama at {remote_host}:11434...")
    
    try:
        async with OllamaSessionManager(remote_host, 11434, ssh_connection) as session:
            await aprint(Fore.GREEN + "✅ Connected to Ollama!")
            
            if session._using_tunnel:
                await aprint(Fore.CYAN + "   (via SSH tunnel)")
            
            # List available models
            models = await session.list_models()
            
            if not models:
                await show_no_models_help(ssh_manager)
                return
            
            await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s)\n")
            
            # Model selection with custom model option
            selected_model = await select_or_create_model(
                session, 
                models, 
                ssh_connection
            )
            
            if not selected_model:
                await aprint(Fore.RED + "❌ No model selected")
                return
            
            # Display current configuration
            await _display_config(selected_model)
            
            # Show interactive menu
            await show_interactive_menu()
            
            # Run interactive session
            await run_interactive_session(session, selected_model, ssh_manager)
            
    except KeyboardInterrupt:
        await aprint(Fore.YELLOW + "\n\n⚠️ LLM session interrupted (Ctrl+C). Returning to main menu...")
        logger.info("LLM session interrupted by user")
    except ConnectionError as e:
        await aprint(Fore.RED + f"❌ Connection failed: {e}")
        logger.error(f"Connection error: {e}")
        await show_connection_help(ssh_manager, remote_host)
    except Exception as e:
        await aprint(Fore.RED + f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)


async def _display_config(selected_model: str):
    """Display current LLM configuration."""
    await aprint(Fore.GREEN + Style.BRIGHT + "\n" + "="*60)
    await aprint(Fore.GREEN + Style.BRIGHT + "  🤖 CURRENT CONFIGURATION")
    await aprint(Fore.GREEN + Style.BRIGHT + "="*60)
    await aprint(Fore.WHITE + f"  Model: {selected_model}")
    
    # Check if it's the research assistant
    if "ct-research-assistant" in selected_model:
        await aprint(Fore.CYAN + "  Type: Clinical Trial Research Assistant")
        await aprint(Fore.CYAN + "  Features: RAG, Structured Extraction, Trial Analysis")
    else:
        await aprint(Fore.CYAN + "  Type: Base LLM (General Purpose)")
        await aprint(Fore.CYAN + "  Features: General Q&A, Code, Analysis")
    
    await aprint(Fore.GREEN + "="*60 + "\n")