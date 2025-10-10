"""
LLM SSH Terminal Mode Handler (Option 3) - Legacy mode.
Uses SSH terminal directly - less reliable than API mode.
"""
from colorama import Fore

from amp_llm.cli.async_io import ainput, aprint
from amp_llm.config import get_logger
from .helpers import show_no_models_help

logger = get_logger(__name__)


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
            await show_no_models_help(None)
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