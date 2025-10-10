"""
LLM workflow handlers with custom model building support.
Includes Modelfile-based personality customization.
"""
import asyncio
import time
from pathlib import Path
from colorama import Fore, Style

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.config import get_logger
from amp_llm.llm.utils.session import OllamaSessionManager

logger = get_logger(__name__)


async def run_llm_entrypoint_api(ssh_manager):
    """
    LLM workflow using Ollama API with automatic tunneling and model building.
    
    This version includes:
    - Automatic SSH tunneling
    - Custom model creation from Modelfile
    - Interactive model selection
    
    Args:
        ssh_manager: SSHManager instance
    """
    await aprint(Fore.CYAN + "\n=== 🤖 LLM Workflow (API Mode) ===")
    await aprint(Fore.YELLOW + "Using Ollama HTTP API (recommended)")
    
    # Get remote host and SSH connection
    remote_host = ssh_manager.host if hasattr(ssh_manager, 'host') else 'localhost'
    ssh_connection = ssh_manager.connection if hasattr(ssh_manager, 'connection') else None
    
    await aprint(Fore.CYAN + f"Connecting to Ollama at {remote_host}:11434...")
    
    # Use enhanced session manager with automatic tunneling
    try:
        async with OllamaSessionManager(remote_host, 11434, ssh_connection) as session:
            await aprint(Fore.GREEN + "✅ Connected to Ollama!")
            
            # Show if using tunnel
            if session._using_tunnel:
                await aprint(Fore.CYAN + "   (via SSH tunnel)")
            
            # List available models
            models = await session.list_models()
            
            if not models:
                await _show_no_models_help(ssh_manager)
                return
            
            # Check for custom model or offer to create one
            custom_model_name = "ct-research-assistant"  # Your custom model name
            selected_model = None
            
            if custom_model_name in models:
                # Custom model exists
                await aprint(Fore.GREEN + f"✅ Found custom model: {custom_model_name}")
                use_custom = await ainput(Fore.CYAN + f"Use '{custom_model_name}'? (y/n) [y]: ")
                
                if use_custom.strip().lower() not in ('n', 'no'):
                    selected_model = custom_model_name
            else:
                # Offer to create custom model
                await aprint(Fore.YELLOW + f"\n🔧 Custom model '{custom_model_name}' not found")
                await aprint(Fore.CYAN + "Would you like to create it with your Modelfile?")
                create_custom = await ainput(Fore.GREEN + "Create custom model? (y/n) [y]: ")
                
                if create_custom.strip().lower() not in ('n', 'no'):
                    # Build custom model
                    if ssh_connection:
                        model_created = await _build_custom_model(
                            ssh_connection,
                            custom_model_name,
                            models
                        )
                        
                        if model_created:
                            # Refresh model list
                            models = await session.list_models()
                            selected_model = custom_model_name
                        else:
                            await aprint(Fore.YELLOW + "Falling back to base model selection...")
                    else:
                        await aprint(Fore.RED + "❌ SSH connection required to build custom models")
                        await aprint(Fore.YELLOW + "Falling back to base model selection...")
            
            # If no custom model selected, let user choose
            if not selected_model:
                selected_model = await _select_model_interactive(models)
                
                if not selected_model:
                    return  # User cancelled
            
            await aprint(Fore.GREEN + f"✅ Selected: {selected_model}")
            
            # Run interactive session
            await _run_interactive_session(session, selected_model)
            
    except ConnectionError as e:
        await aprint(Fore.RED + f"❌ Connection failed: {e}")
        logger.error(f"Connection error: {e}")
        await _show_connection_help(ssh_manager, remote_host)
    except Exception as e:
        await aprint(Fore.RED + f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)


async def _build_custom_model(ssh_connection, model_name: str, available_models: list) -> bool:
    """
    Build custom model from Modelfile.
    
    Args:
        ssh_connection: SSH connection
        model_name: Name for custom model
        available_models: List of available base models
        
    Returns:
        True if successful
    """
    await aprint(Fore.CYAN + "\n🏗️  Building Custom Model")
    await aprint(Fore.YELLOW + "This is a one-time setup to create a specialized assistant.")
    
    # Find Modelfile
    modelfile_path = _find_modelfile()
    
    if not modelfile_path:
        await aprint(Fore.RED + "❌ Modelfile not found!")
        await aprint(Fore.YELLOW + "Expected location: project root (Modelfile)")
        await aprint(Fore.CYAN + "\nCreate one with:")
        await aprint(Fore.WHITE + "  python scripts/generate_modelfile.py")
        return False
    
    await aprint(Fore.GREEN + f"✅ Found Modelfile: {modelfile_path}")
    
    # Read Modelfile
    try:
        modelfile_content = modelfile_path.read_text()
    except Exception as e:
        await aprint(Fore.RED + f"❌ Cannot read Modelfile: {e}")
        return False
    
    # Select base model
    await aprint(Fore.CYAN + f"\n📋 Available base models:")
    for i, model in enumerate(available_models, 1):
        await aprint(Fore.WHITE + f"  {i}. {model}")
    
    choice = await ainput(Fore.GREEN + "Select base model [1]: ")
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
        await aprint(Fore.YELLOW + f"Model '{choice}' not found, using first model")
        base_model = available_models[0]
    
    await aprint(Fore.CYAN + f"\n🔨 Building '{model_name}' from '{base_model}'...")
    
    # Update FROM line in Modelfile
    updated_modelfile = _update_modelfile_base(modelfile_content, base_model)
    
    # Upload Modelfile
    temp_path = f"/tmp/amp_modelfile_{int(time.time())}.modelfile"
    
    try:
        await aprint(Fore.CYAN + "📤 Uploading Modelfile...")
        
        async with ssh_connection.start_sftp_client() as sftp:
            async with sftp.open(temp_path, 'w') as f:
                await f.write(updated_modelfile)
        
        await aprint(Fore.GREEN + f"✅ Uploaded to {temp_path}")
        
    except Exception as e:
        await aprint(Fore.RED + f"❌ Upload failed: {e}")
        logger.error(f"SFTP error: {e}")
        return False
    
    # Build model
    try:
        await aprint(Fore.CYAN + "🏗️  Building model (this may take 1-2 minutes)...")
        await aprint(Fore.YELLOW + "   Please wait...")
        
        result = await ssh_connection.run(
            f'bash -l -c "ollama create {model_name} -f {temp_path}"',
            check=False,
            term_type=None 
        )
        
        # Cleanup
        await ssh_connection.run(f'rm -f {temp_path}', 
            check=False,
            term_type=None 
        )
        
        if result.exit_status == 0:
            await aprint(Fore.GREEN + f"\n✅ Success! Model '{model_name}' created!")
            await aprint(Fore.CYAN + f"   Base: {base_model}")
            await aprint(Fore.CYAN + f"   Name: {model_name}")
            return True
        else:
            await aprint(Fore.RED + "\n❌ Model creation failed!")
            if result.stderr:
                await aprint(Fore.RED + f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        await aprint(Fore.RED + f"❌ Build error: {e}")
        logger.error(f"Build error: {e}", exc_info=True)
        
        # Cleanup on error
        try:
            await ssh_connection.run(f'rm -f {temp_path}', 
            check=False,
            term_type=None 
        )
        except:
            pass
        
        return False


def _find_modelfile() -> Path:
    """
    Find Modelfile in expected locations.
    
    Returns:
        Path to Modelfile or None if not found
    """
    search_paths = [
        Path("Modelfile"),  # Project root
        Path("amp_llm/Modelfile"),  # amp_llm directory
        Path("../Modelfile"),  # Parent directory
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    return None


def _update_modelfile_base(modelfile_content: str, base_model: str) -> str:
    """
    Update FROM line in Modelfile.
    
    Args:
        modelfile_content: Original Modelfile content
        base_model: New base model name
        
    Returns:
        Updated Modelfile content
    """
    import re
    
    # Replace FROM line
    updated = re.sub(
        r'^FROM\s+\S+',
        f'FROM {base_model}',
        modelfile_content,
        flags=re.MULTILINE
    )
    
    return updated


async def _select_model_interactive(models: list) -> str:
    """
    Interactive model selection.
    
    Args:
        models: List of available models
        
    Returns:
        Selected model name or None if cancelled
    """
    await aprint(Fore.CYAN + f"\n📋 Available models ({len(models)}):")
    for i, model in enumerate(models, 1):
        await aprint(Fore.WHITE + f"  {i}. {model}")
    
    while True:
        choice = await ainput(Fore.GREEN + "\nSelect model (number or name, or 'exit'): ")
        choice = choice.strip()
        
        if choice.lower() in ('exit', 'quit', 'back', 'main menu'):
            await aprint(Fore.YELLOW + "Returning to main menu...")
            return None
        
        # Try as number
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx]
        # Try as model name
        elif choice in models:
            return choice
        
        await aprint(Fore.RED + "Invalid choice. Try again.")


async def _run_interactive_session(session: OllamaSessionManager, model: str):
    """
    Run interactive LLM session.
    
    Args:
        session: Connected session manager
        model: Model name to use
    """
    await aprint(Fore.CYAN + "\n💬 Interactive Mode")
    await aprint(Fore.YELLOW + "Type your prompts (or 'exit' to return)")
    
    while True:
        try:
            prompt = await ainput(Fore.GREEN + "\nPrompt >>> " + Style.RESET_ALL)
            prompt = prompt.strip()
            
            if not prompt:
                continue
            
            if prompt.lower() in ('exit', 'quit', 'back', 'main menu'):
                await aprint(Fore.YELLOW + "Returning to main menu...")
                break
            
            # Generate response
            await aprint(Fore.YELLOW + "\n🤔 Generating...")
            
            response = await session.send_prompt(
                model=model,
                prompt=prompt,
                temperature=0.7
            )
            
            await aprint(Fore.CYAN + "\n📝 Response:")
            await aprint(Fore.WHITE + response)
            
        except KeyboardInterrupt:
            await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to return.")
            continue
        except Exception as e:
            await aprint(Fore.RED + f"\n❌ Error: {e}")
            logger.error(f"Generation error: {e}", exc_info=True)


async def _show_no_models_help(ssh_manager):
    """Show help when no models are found."""
    await aprint(Fore.RED + "❌ No models found on remote server")
    await aprint(Fore.YELLOW + "Install models using: ollama pull <model_name>")
    await aprint(Fore.CYAN + "\nTroubleshooting:")
    await aprint(Fore.WHITE + "  1. SSH to remote host:")
    if hasattr(ssh_manager, 'username') and hasattr(ssh_manager, 'host'):
        await aprint(Fore.WHITE + f"     ssh {ssh_manager.username}@{ssh_manager.host}")
    await aprint(Fore.WHITE + "  2. Check Ollama status:")
    await aprint(Fore.WHITE + "     systemctl status ollama")
    await aprint(Fore.WHITE + "  3. List models:")
    await aprint(Fore.WHITE + "     ollama list")
    await aprint(Fore.WHITE + "  4. Pull a base model:")
    await aprint(Fore.WHITE + "     ollama pull llama3.2")


async def _show_connection_help(ssh_manager, remote_host: str):
    """Show help when connection fails."""
    await aprint(Fore.RED + "❌ Cannot connect to Ollama")
    await aprint(Fore.CYAN + "\nTroubleshooting:")
    await aprint(Fore.WHITE + "  1. Check if Ollama is running:")
    username = ssh_manager.username if hasattr(ssh_manager, 'username') else 'user'
    await aprint(Fore.WHITE + f"     ssh {username}@{remote_host}")
    await aprint(Fore.WHITE + "     systemctl status ollama")
    await aprint(Fore.WHITE + "  2. Test Ollama API:")
    await aprint(Fore.WHITE + "     curl http://localhost:11434/api/tags")
    await aprint(Fore.WHITE + "  3. Start Ollama if not running:")
    await aprint(Fore.WHITE + "     sudo systemctl start ollama")


async def run_llm_entrypoint_ssh(ssh_manager):
    """
    LLM workflow using SSH terminal (legacy method).
    
    Args:
        ssh_manager: SSHManager instance
    """
    await aprint(Fore.YELLOW + "\n⚠️  SSH Terminal Mode (Legacy)")
    await aprint(Fore.YELLOW + "This method is deprecated. Use API mode for better reliability.")
    await aprint(Fore.CYAN + "\n💡 Tip: API mode supports custom model building with Modelfiles!")