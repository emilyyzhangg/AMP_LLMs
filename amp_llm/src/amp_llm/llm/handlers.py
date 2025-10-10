"""
LLM workflow handlers and entry points.
FIXED: Proper SSH manager handling for remote host detection.
"""
import asyncio
from colorama import Fore, Style

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.config import get_logger

# Import clients from correct location
from amp_llm.llm.clients.ollama_api import OllamaAPIClient
from amp_llm.llm.clients.ollama_ssh import OllamaSSHClient

logger = get_logger(__name__)


async def run_llm_entrypoint_api(ssh_manager):
    """
    LLM workflow using Ollama API (HTTP).
    FIXED: Now properly extracts remote host from SSHManager.
    
    Args:
        ssh_manager: SSHManager instance (not the raw connection)
    """
    await aprint(Fore.CYAN + "\n=== 🤖 LLM Workflow (API Mode) ===")
    await aprint(Fore.YELLOW + "Using Ollama HTTP API (recommended)")
    
    # FIXED: Properly get remote host from SSHManager
    if hasattr(ssh_manager, 'host') and ssh_manager.host:
        remote_host = ssh_manager.host
    else:
        # Fallback to localhost if no SSH connection
        remote_host = 'localhost'
        await aprint(Fore.YELLOW + "⚠️  No SSH connection - using localhost")
    
    await aprint(Fore.CYAN + f"Connecting to Ollama at {remote_host}:11434...")
    
    # Create API client
    try:
        async with OllamaAPIClient(host=remote_host, port=11434) as client:
            await aprint(Fore.GREEN + "✅ Connected to Ollama API")
            
            # List available models
            models = await client.list_models()
            
            if not models:
                await aprint(Fore.RED + "❌ No models found on remote server")
                await aprint(Fore.YELLOW + "Install models using: ollama pull <model_name>")
                await aprint(Fore.CYAN + "\nTroubleshooting:")
                await aprint(Fore.WHITE + "  1. Check if Ollama is running on remote host:")
                await aprint(Fore.WHITE + f"     ssh {ssh_manager.username}@{remote_host}")
                await aprint(Fore.WHITE + "     systemctl status ollama")
                await aprint(Fore.WHITE + "  2. Try: ollama list")
                await aprint(Fore.WHITE + "  3. If no models: ollama pull llama3.2")
                return
            
            await aprint(Fore.CYAN + f"\n📋 Available models ({len(models)}):")
            for i, model in enumerate(models, 1):
                await aprint(Fore.WHITE + f"  {i}. {model}")
            
            # Model selection
            while True:
                choice = await ainput(Fore.GREEN + "\nSelect model (number or name): ")
                choice = choice.strip()
                
                if choice.lower() in ('exit', 'quit', 'back', 'main menu'):
                    await aprint(Fore.YELLOW + "Returning to main menu...")
                    return
                
                # Try as number
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(models):
                        selected_model = models[idx]
                        break
                # Try as model name
                elif choice in models:
                    selected_model = choice
                    break
                else:
                    await aprint(Fore.RED + "Invalid choice. Try again.")
            
            await aprint(Fore.GREEN + f"✅ Selected: {selected_model}")
            
            # Interactive prompt loop
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
                    
                    response = await client.generate(
                        model=selected_model,
                        prompt=prompt,
                        temperature=0.7
                    )
                    
                    await aprint(Fore.CYAN + "\n📝 Response:")
                    await aprint(Fore.WHITE + response)
                    
                except KeyboardInterrupt:
                    await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to return.")
                    continue
                except Exception as e:
                    await aprint(Fore.RED + f"❌ Error: {e}")
                    logger.error(f"LLM API error: {e}", exc_info=True)
    
    except Exception as e:
        await aprint(Fore.RED + f"❌ Failed to connect to Ollama API: {e}")
        await aprint(Fore.CYAN + "\nTroubleshooting:")
        await aprint(Fore.WHITE + f"  • Is Ollama running on {remote_host}?")
        await aprint(Fore.WHITE + f"  • Can you reach port 11434?")
        await aprint(Fore.WHITE + f"  • Try: ssh {ssh_manager.username if hasattr(ssh_manager, 'username') else 'user'}@{remote_host} 'curl http://localhost:11434/api/tags'")
        logger.error(f"Ollama API connection error: {e}", exc_info=True)


async def run_llm_entrypoint_ssh(ssh_connection):
    """
    LLM workflow using SSH terminal interaction.
    Legacy method - has potential issues with text fragmentation.
    
    Args:
        ssh_connection: Active SSH connection (asyncssh object)
    """
    await aprint(Fore.CYAN + "\n=== 🤖 LLM Workflow (SSH Terminal) ===")
    await aprint(Fore.YELLOW + "⚠️  Using SSH terminal mode (legacy)")
    await aprint(Fore.YELLOW + "Note: API mode is recommended for better reliability\n")
    
    # Create SSH client
    client = OllamaSSHClient(ssh_connection)
    
    try:
        # List available models
        await aprint(Fore.CYAN + "📋 Fetching available models...")
        models = await client.list_models()
        
        if not models:
            await aprint(Fore.RED + "❌ No models found on remote server")
            await aprint(Fore.YELLOW + "Install models using: ollama pull <model_name>")
            return
        
        await aprint(Fore.GREEN + f"✅ Found {len(models)} model(s):")
        for i, model in enumerate(models, 1):
            await aprint(Fore.WHITE + f"  {i}. {model}")
        
        # Model selection
        while True:
            choice = await ainput(Fore.GREEN + "\nSelect model (number or name): ")
            choice = choice.strip()
            
            if choice.lower() in ('exit', 'quit', 'back', 'main menu'):
                await aprint(Fore.YELLOW + "Returning to main menu...")
                return
            
            # Try as number
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    selected_model = models[idx]
                    break
            # Try as model name
            elif choice in models:
                selected_model = choice
                break
            else:
                await aprint(Fore.RED + "Invalid choice. Try again.")
        
        await aprint(Fore.GREEN + f"✅ Selected: {selected_model}")
        await aprint(Fore.CYAN + "Starting model (this may take a moment)...")
        
        # Start model
        await client.start_model(selected_model)
        await aprint(Fore.GREEN + "✅ Model started")
        
        # Interactive prompt loop
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
                
                response = await client.generate(selected_model, prompt)
                
                await aprint(Fore.CYAN + "\n📝 Response:")
                await aprint(Fore.WHITE + response)
                
            except KeyboardInterrupt:
                await aprint(Fore.YELLOW + "\n\nInterrupted. Type 'exit' to return.")
                continue
            except Exception as e:
                await aprint(Fore.RED + f"❌ Error: {e}")
                logger.error(f"LLM SSH error: {e}", exc_info=True)
    
    except Exception as e:
        await aprint(Fore.RED + f"❌ Failed to start LLM workflow: {e}")
        logger.error(f"LLM SSH workflow error: {e}", exc_info=True)
    
    finally:
        # Cleanup
        try:
            await client.cleanup()
        except:
            pass


# Alias for backward compatibility
run_llm_entrypoint = run_llm_entrypoint_ssh