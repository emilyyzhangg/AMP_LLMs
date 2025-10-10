"""
Enhanced LLM workflow handlers with interactive menu and file loading.
Includes paste mode, file loading, and trial-specific operations.

REPLACE THE ENTIRE CONTENTS of src/amp_llm/llm/handlers.py with this file.
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
from amp_llm.llm.utils.interactive import (
    handle_paste_command,
    handle_load_command,
    list_output_files,
    show_pwd,
)

logger = get_logger(__name__)


# ============================================================================
# MAIN FUNCTION: LLM API MODE (OPTION 2)
# ============================================================================

async def run_llm_entrypoint_api(ssh_manager):
    """
    Enhanced LLM workflow with interactive menu options (API Mode).
    
    Features:
    - Paste mode for multi-line input
    - File loading from output/ directory
    - Trial-specific questions
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
                await _show_no_models_help(ssh_manager)
                return
            
            await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s)\n")
            
            # Model selection with custom model option
            selected_model = await _select_or_create_model(
                session, 
                models, 
                ssh_connection
            )
            
            if not selected_model:
                await aprint(Fore.RED + "❌ No model selected")
                return
            
            # Display current configuration
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
            
            # Show interactive menu
            await _show_interactive_menu()
            
            # Run interactive session
            await _run_enhanced_interactive_session(
                session, 
                selected_model,
                ssh_manager
            )
            
    except KeyboardInterrupt:
        await aprint(Fore.YELLOW + "\n\n⚠️ LLM session interrupted (Ctrl+C). Returning to main menu...")
        logger.info("LLM session interrupted by user")
    except ConnectionError as e:
        await aprint(Fore.RED + f"❌ Connection failed: {e}")
        logger.error(f"Connection error: {e}")
        await _show_connection_help(ssh_manager, remote_host)
    except Exception as e:
        await aprint(Fore.RED + f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)


# ============================================================================
# LEGACY FUNCTION: SSH TERMINAL MODE (OPTION 3)
# ============================================================================

async def run_llm_entrypoint_ssh(ssh_connection):
    """
    Legacy LLM workflow using SSH terminal (Option 3).
    
    NOTE: This is deprecated in favor of API mode (Option 2).
    Kept for backward compatibility.
    
    Args:
        ssh_connection: Active SSH connection
    """
    await aprint(Fore.CYAN + "\n=== 🤖 LLM Workflow (SSH Terminal Mode) ===")
    await aprint(Fore.YELLOW + "⚠️  NOTE: This is legacy mode. API mode (Option 2) is recommended.\n")
    
    try:
        # List available models via SSH
        await aprint(Fore.CYAN + "Checking available models...")
        
        result = await ssh_connection.run(
            'bash -lc "ollama list"',
            check=False,
            term_type=None
        )
        
        if result.exit_status != 0:
            await aprint(Fore.RED + "❌ Failed to list models")
            await aprint(Fore.YELLOW + "Make sure Ollama is installed and running on remote host")
            return
        
        # Parse models from output
        output = result.stdout.strip()
        lines = output.split('\n')[1:]  # Skip header
        models = []
        
        for line in lines:
            if line.strip():
                parts = line.split()
                if parts:
                    models.append(parts[0])
        
        if not models:
            await aprint(Fore.RED + "❌ No models found")
            await _show_no_models_help(None)
            return
        
        await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s):")
        for i, model in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}. {model}")
        
        # Select model
        choice = await ainput(Fore.GREEN + "\nSelect model [1]: ")
        choice = choice.strip() or "1"
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                model = models[idx]
            else:
                model = models[0]
        elif choice in models:
            model = choice
        else:
            model = models[0]
        
        await aprint(Fore.GREEN + f"✅ Using model: {model}\n")
        await aprint(Fore.YELLOW + "💡 Type your prompts. Type 'exit' to return to main menu.\n")
        
        # Interactive loop
        while True:
            try:
                prompt = await ainput(Fore.GREEN + "LLM >>> " + Fore.WHITE)
                prompt = prompt.strip()
                
                if not prompt:
                    continue
                
                if prompt.lower() in ('exit', 'quit', 'main menu'):
                    await aprint(Fore.YELLOW + "Returning to main menu...")
                    break
                
                # Send prompt via SSH
                await aprint(Fore.YELLOW + "\n🤔 Generating response...")
                
                # Escape prompt for shell
                escaped_prompt = prompt.replace("'", "'\\''")
                
                result = await ssh_connection.run(
                    f'bash -lc "ollama run {model} \'{escaped_prompt}\'"',
                    check=False,
                    term_type=None
                )
                
                if result.exit_status == 0:
                    response = result.stdout.strip()
                    await aprint(Fore.GREEN + "\n🧠 Response:")
                    await aprint(Fore.WHITE + response + "\n")
                else:
                    await aprint(Fore.RED + f"\n❌ Error: {result.stderr}")
                
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\n⚠️ Interrupted. Type 'exit' to quit...")
                continue
            except EOFError:
                await aprint(Fore.YELLOW + "\nEOF detected. Returning to main menu...")
                break
            except Exception as e:
                await aprint(Fore.RED + f"\n❌ Error: {e}")
                logger.error(f"SSH LLM error: {e}", exc_info=True)
        
    except KeyboardInterrupt:
        await aprint(Fore.YELLOW + "\n\n⚠️ SSH LLM session interrupted. Returning to main menu...")
        logger.info("SSH LLM session interrupted by user")
    except Exception as e:
        await aprint(Fore.RED + f"❌ Error: {e}")
        logger.error(f"SSH LLM error: {e}", exc_info=True)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _select_or_create_model(session, models: list, ssh_connection) -> str:
    """
    Select base LLM, then optionally create Research Assistant model.
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
        
        if await _build_custom_model(
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


async def _show_interactive_menu():
    """Display interactive menu options."""
    await aprint(Fore.CYAN + Style.BRIGHT + "\n" + "="*60)
    await aprint(Fore.CYAN + Style.BRIGHT + "  💬 INTERACTIVE LLM SESSION")
    await aprint(Fore.CYAN + Style.BRIGHT + "="*60 + Style.RESET_ALL)
    
    await aprint(Fore.YELLOW + "\n💡 Available Commands:")
    await aprint(Fore.WHITE + "  📋 File Operations:")
    await aprint(Fore.CYAN + "    • 'load <filename>' - Load file from output/")
    await aprint(Fore.CYAN + "    • 'paste' - Multi-line paste mode")
    await aprint(Fore.CYAN + "    • 'ls' or 'dir' - List files")
    
    await aprint(Fore.WHITE + "\n  ℹ️  Information:")
    await aprint(Fore.CYAN + "    • 'help' - Show this menu")
    await aprint(Fore.CYAN + "    • 'models' - List available models")
    
    await aprint(Fore.WHITE + "\n  🚪 Exit:")
    await aprint(Fore.CYAN + "    • 'exit', 'quit', 'main menu' - Return to main menu")
    await aprint(Fore.YELLOW + "    • Ctrl+C - Interrupt and return")
    
    await aprint(Fore.CYAN + "\n" + "="*60 + "\n")


async def _run_enhanced_interactive_session(session, model: str, ssh_manager):
    """Run enhanced interactive session with all features."""
    while True:
        try:
            prompt = await ainput(Fore.GREEN + "LLM >>> " + Fore.WHITE)
            
            if prompt is None:
                prompt = ""
            prompt = prompt.strip()
            
            if not prompt:
                continue
            
            # Check for exit commands
            if prompt.lower() in ("exit", "quit", "main menu"):
                await aprint(Fore.YELLOW + "Returning to main menu...")
                break
            
            # Handle special commands
            if await _handle_special_command(prompt, session, model, ssh_manager):
                continue
            
            # Regular prompt to LLM
            await aprint(Fore.YELLOW + f"\n🤔 Generating response...")
            
            try:
                response = await session.send_prompt(
                    model=model,
                    prompt=prompt,
                    temperature=0.7,
                    max_retries=3
                )
                
                if response.startswith("Error:"):
                    await aprint(Fore.RED + f"\n{response}")
                else:
                    await aprint(Fore.GREEN + "\n🧠 Response:")
                    await aprint(Fore.WHITE + response + "\n")
                    
            except Exception as e:
                await aprint(Fore.RED + f"\n❌ Error: {e}")
                logger.error(f"Generation error: {e}", exc_info=True)
                
        except KeyboardInterrupt:
            await aprint(Fore.YELLOW + "\n\n⚠️ Interrupted. Type 'exit' to quit...")
            continue
        except EOFError:
            await aprint(Fore.YELLOW + "\nEOF detected. Returning to main menu...")
            break


async def _handle_special_command(prompt: str, session, model: str, ssh_manager) -> bool:
    """Handle special commands. Returns True if command was handled."""
    prompt_lower = prompt.lower()
    
    # Help command
    if prompt_lower in ('help', '?', '!help'):
        await _show_interactive_menu()
        return True
    
    # Directory listing
    if prompt_lower in ('ls', 'dir', 'list'):
        await list_output_files(aprint)
        return True
    
    # Show working directory
    if prompt_lower in ('pwd', 'cwd'):
        await show_pwd(aprint)
        return True
    
    # Paste mode
    if prompt_lower == 'paste':
        pasted = await handle_paste_command(ainput, aprint)
        if pasted:
            await aprint(Fore.YELLOW + f"\n🤔 Sending to LLM...")
            response = await session.send_prompt(model=model, prompt=pasted)
            if not response.startswith("Error:"):
                await aprint(Fore.GREEN + "\n🧠 Response:")
                await aprint(Fore.WHITE + response + "\n")
            else:
                await aprint(Fore.RED + f"\n{response}")
        return True
    
    # Load file
    if prompt_lower.startswith('load '):
        final_prompt = await handle_load_command(prompt, ainput, aprint, logger)
        if final_prompt:
            await aprint(Fore.YELLOW + f"\n🤔 Processing file...")
            response = await session.send_prompt(model=model, prompt=final_prompt)
            if not response.startswith("Error:"):
                await aprint(Fore.GREEN + "\n🧠 Response:")
                await aprint(Fore.WHITE + response + "\n")
            else:
                await aprint(Fore.RED + f"\n{response}")
        return True
    
    # List models
    if prompt_lower in ('models', 'list models'):
        models = await session.list_models()
        await aprint(Fore.CYAN + f"\n📋 Available models ({len(models)}):")
        for i, m in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}. {m}")
        await aprint("")
        return True
    
    return False


async def _build_custom_model(ssh_connection, model_name: str, available_models: list, selected_base_model: str = None) -> bool:
    """Build custom model from Modelfile."""
    await aprint(Fore.CYAN + "🔨 Building custom model...")
    
    # Find Modelfile
    modelfile_path = _find_modelfile()
    if not modelfile_path:
        await aprint(Fore.RED + "❌ Modelfile not found!")
        return False
    
    try:
        modelfile_content = modelfile_path.read_text()
    except Exception as e:
        await aprint(Fore.RED + f"❌ Cannot read Modelfile: {e}")
        return False
    
    # Use provided base model
    base_model = selected_base_model or available_models[0]
    
    # Update Modelfile
    import re
    updated_modelfile = re.sub(
        r'^FROM\s+\S+',
        f'FROM {base_model}',
        modelfile_content,
        flags=re.MULTILINE
    )
    
    # Upload and build
    temp_path = f"/tmp/amp_modelfile_{int(time.time())}.modelfile"
    
    try:
        async with ssh_connection.start_sftp_client() as sftp:
            async with sftp.open(temp_path, 'w') as f:
                await f.write(updated_modelfile)
        
        result = await ssh_connection.run(
            f'bash -l -c "ollama create {model_name} -f {temp_path}"',
            check=False,
            term_type=None 
        )
        
        await ssh_connection.run(f'rm -f {temp_path}', check=False, term_type=None)
        
        return result.exit_status == 0
            
    except Exception as e:
        await aprint(Fore.RED + f"❌ Build error: {e}")
        logger.error(f"Build error: {e}", exc_info=True)
        return False


def _find_modelfile():
    """Find Modelfile in expected locations."""
    search_paths = [
        Path("Modelfile"),
        Path("amp_llm/Modelfile"),
        Path("../Modelfile"),
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    return None


async def _show_no_models_help(ssh_manager):
    """Show help when no models found."""
    await aprint(Fore.RED + "❌ No models found on remote server")
    await aprint(Fore.YELLOW + "\nTo install models:")
    await aprint(Fore.WHITE + "  1. SSH to remote server")
    await aprint(Fore.WHITE + "  2. Run: ollama pull llama3.2")
    await aprint(Fore.WHITE + "  3. Run: ollama list (to verify)")


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