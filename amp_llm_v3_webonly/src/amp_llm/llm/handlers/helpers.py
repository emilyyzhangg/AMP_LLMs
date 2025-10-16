"""
Helper functions for LLM handlers.
Model selection, connection help, etc.
"""
import time
from pathlib import Path
from colorama import Fore

from amp_llm.cli.async_io import ainput, aprint
from amp_llm.config import get_logger

logger = get_logger(__name__)


async def select_or_create_model(session, models: list, ssh_connection) -> str:
    """
    Select base LLM, then optionally create Research Assistant model.
    
    Returns:
        Selected model name or None
    """
    # Filter out custom models - show only base models
    base_models = [m for m in models if not m.startswith('ct-research-assistant') 
                   and not m.startswith('amp-assistant')]
    
    if not base_models:
        await aprint(Fore.RED + "❌ No base models available")
        return None
    
    await aprint(Fore.CYAN + f"\n📋 Available base models:")
    for i, model in enumerate(base_models, 1):
        marker = "→" if i == 1 else " "
        await aprint(Fore.WHITE + f"  {marker} {i}) {model}")
    
    # User selects base model
    choice = await ainput(Fore.GREEN + "Select base model [1]: ")
    choice = choice.strip() or "1"
    
    selected_base = None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(base_models):
            selected_base = base_models[idx]
    elif choice in base_models:
        selected_base = choice
    
    if not selected_base:
        await aprint(Fore.YELLOW + "Invalid selection, using first model")
        selected_base = base_models[0]
    
    await aprint(Fore.GREEN + f"✅ Selected base: {selected_base}\n")
    
    # Ask about Research Assistant
    build_assistant = await ainput(
        Fore.CYAN + 
        "Build Research Assistant model from this base? (y/n) [n]: "
    )
    build_assistant = build_assistant.strip().lower()
    
    if build_assistant in ('y', 'yes'):
        model_name = "ct-research-assistant:latest"
        await aprint(Fore.CYAN + f"\n🔬 Building Research Assistant model...")
        
        if await build_custom_model(
            ssh_connection, 
            model_name, 
            base_models, 
            selected_base_model=selected_base
        ):
            await aprint(Fore.GREEN + f"\n✅ Created: {model_name}")
            return model_name
        else:
            await aprint(Fore.YELLOW + f"\n⚠️  Model creation failed, using base")
            return selected_base
    else:
        return selected_base


async def build_custom_model(
    ssh_connection, 
    model_name: str, 
    available_models: list, 
    selected_base_model: str = None
) -> bool:
    """
    Build custom model from Modelfile.
    
    Returns:
        True if successful
    """
    from amp_llm.llm.models.builder import build_custom_model as builder
    
    return await builder(
        ssh_connection,
        model_name,
        available_models,
        selected_base_model=selected_base_model
    )


async def show_no_models_help(ssh_manager):
    """Show help when no models found."""
    await aprint(Fore.RED + "❌ No models found on remote server")
    await aprint(Fore.YELLOW + "\nTo install models:")
    await aprint(Fore.WHITE + "  1. SSH to remote server")
    await aprint(Fore.WHITE + "  2. Run: ollama pull llama3.2")
    await aprint(Fore.WHITE + "  3. Run: ollama list (to verify)")


async def show_connection_help(ssh_manager, remote_host: str):
    """Show help when connection fails."""
    await aprint(Fore.RED + "❌ Cannot connect to Ollama")
    await aprint(Fore.CYAN + "\nTroubleshooting:")
    await aprint(Fore.WHITE + "  1. Check if Ollama is running:")
    username = ssh_manager.username if hasattr(ssh_manager, 'username') else 'user'
    await aprint(Fore.WHITE + f"     ssh {username}@{remote_host}")
    await aprint(Fore.WHITE + "     systemctl status ollama")
    await aprint(Fore.WHITE + "  2. Test Ollama API:")
    await aprint(Fore.WHITE + "     curl http://localhost:11434/api/tags")